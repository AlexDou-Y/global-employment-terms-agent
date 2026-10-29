"""Bounded, offline PDF text extraction and physical-page evidence navigation.

Search returns discovery snippets, never complete evidence. Read the returned
physical page numbers separately to obtain the selected-page text. PDF reading
order is provided by pypdf and does not establish visual layout or OCR accuracy.

The CLI is intended to run in a short-lived child process with a caller-enforced
timeout. Checks between pages cannot interrupt a pathological parser operation.
No PDF actions, attachments, scripts, or URLs are executed or fetched.
"""

import argparse
import io
import json
import re
import sys
import time

from pypdf import PdfReader


MAX_PDF_BYTES = 20 * 1024 * 1024
MAX_DOCUMENT_PAGES = 1500
DEFAULT_READ_PAGES = 5
MAX_SELECTED_PAGES = 12
MAX_TEXT_CHARS = 28000
MAX_SEARCH_CHARS = 200
MAX_SEARCH_TERMS = 8
MAX_SEARCH_HITS = 30
MAX_SCAN_CHARS = 4_000_000
MAX_SCAN_SECONDS = 12
MAX_PAGE_STREAM_BYTES = 8 * 1024 * 1024
MAX_PAGE_TEXT_CHARS = 500_000
OCR_ERROR = "PDF未提取到可读文字，可能为扫描件，需要OCR"


class PDFError(Exception):
    """Fixed user-facing messages only; never include parser exception text."""


def _search_terms(search):
    if (not isinstance(search, str) or len(search) > MAX_SEARCH_CHARS
            or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\ud800-\udfff]", search)):
        raise PDFError("PDF搜索词须为不超过200个字符的文本。")
    if not search.strip():
        return []
    alternatives = search.split("|")
    if len(alternatives) > MAX_SEARCH_TERMS:
        raise PDFError("PDF搜索最多支持8个以 | 分隔的替代词。")
    terms = list(dict.fromkeys(" ".join(term.split()).casefold() for term in alternatives if term.strip()))
    if not terms:
        raise PDFError("PDF搜索词不能为空。")
    return terms


def _page_text(page):
    # The process timeout remains necessary: decoding a content stream itself
    # may be costly before its expanded size can be checked.
    contents = page.get_contents()
    if contents is not None and len(contents.get_data()) > MAX_PAGE_STREAM_BYTES:
        raise PDFError("PDF页面内容超过安全解析上限。")
    text = page.extract_text() or ""
    if len(text) > MAX_PAGE_TEXT_CHARS:
        raise PDFError("PDF页面文字超过安全解析上限。")
    # Preserve paragraph boundaries and legal numbering. Remove unsupported
    # control bytes and invalid Unicode, which cannot be JSON UTF-8 evidence.
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\ud800-\udfff]", "", text)
    return text.strip()


def _snippet(text, terms):
    normalized = " ".join(text.split())
    folded = normalized.casefold()
    positions = [folded.find(term) for term in terms]
    positions = [pos for pos in positions if pos >= 0]
    if not positions:
        return None
    folded_position = min(positions)
    # Casefold may expand a character (for example, German sharp s). Map the
    # earliest folded match back to its source index before choosing context.
    source_position, consumed = 0, 0
    for source_position, character in enumerate(normalized):
        if consumed + len(character.casefold()) > folded_position:
            break
        consumed += len(character.casefold())
    start = max(0, source_position - 220)
    end = min(len(normalized), source_position + 650)
    return ("..." if start else "") + normalized[start:end] + ("..." if end < len(normalized) else "")


def _read_pages(reader, result):
    assembled, remaining = [], MAX_TEXT_CHARS
    has_readable_text = False
    for number in result["selected_pages"]:
        try:
            text = _page_text(reader.pages[number - 1])
        except Exception:
            text = ""
            result["page_errors"].append({"page": number, "error": "PDF页面解析失败或超过安全上限。"})
        if not text:
            result["unreadable_pages"].append(number)
        else:
            has_readable_text = True
        prefix = ("\n\n" if assembled else "") + f"[PDF page {number}]\n"
        available = max(0, remaining - len(prefix))
        returned = text[:available]
        block = (prefix + returned)[:remaining]
        if len(returned) < len(text) or len(block) < len(prefix):
            result["truncated"] = True
        result["pages"].append({"page": number, "text": returned})
        assembled.append(block)
        remaining -= len(block)
    result["text"] = "".join(assembled)
    result["truncated"] |= bool(result["unreadable_pages"])
    result["full_document"] = (result["page_start"] == 1
                                and result["page_end"] == result["total_pages"]
                                and not result["truncated"])
    if not has_readable_text:
        result["text"] = ""
        result["error"] = "PDF页面解析失败或超过安全上限。" if result["page_errors"] else OCR_ERROR


def _search_pages(reader, result, terms):
    result.update(search_mode=True, search_terms=terms,
                  search_strategy="literal alternatives separated by |; casefold and whitespace normalization",
                  hits=[], matched_pages=[], pages_searched=0, searched_pages=[],
                  search_complete=False, whole_document_searched=False,
                  search_limit_reached=False, truncated=True)
    deadline, scanned_chars, has_readable_text = time.monotonic() + MAX_SCAN_SECONDS, 0, False
    for number in result["selected_pages"]:
        if time.monotonic() >= deadline:
            result["search_limit_reached"] = True
            break
        try:
            text = _page_text(reader.pages[number - 1])
        except Exception:
            text = ""
            result["page_errors"].append({"page": number, "error": "PDF页面解析失败或超过安全上限。"})
        has_readable_text |= bool(text)
        if scanned_chars + len(text) > MAX_SCAN_CHARS or time.monotonic() >= deadline:
            result["search_limit_reached"] = True
            break
        scanned_chars += len(text)
        result["pages_searched"] += 1
        result["searched_pages"].append(number)
        if not text:
            result["unreadable_pages"].append(number)
            continue
        snippet = _snippet(text, terms)
        if snippet is not None:
            result["hits"].append({"page": number, "snippet": snippet})
            result["matched_pages"].append(number)
            if len(result["hits"]) == MAX_SEARCH_HITS and number < result["page_end"]:
                result["search_limit_reached"] = True
                break
    result["search_complete"] = (result["pages_searched"] == len(result["selected_pages"])
                                  and not result["unreadable_pages"]
                                  and not result["search_limit_reached"])
    result["whole_document_searched"] = (result["search_complete"] and result["page_start"] == 1
                                           and result["page_end"] == result["total_pages"])
    result["text"] = "\n\n".join(f"[PDF page {hit['page']}]\n{hit['snippet']}" for hit in result["hits"])[:MAX_TEXT_CHARS]
    result["message"] = ("仅返回定位片段；请按命中页码读取完整页并核对上下文。" if result["hits"]
                         else "已搜索页未命中指定字词；不能据此认定不存在相关法律规定。")
    if result["search_limit_reached"]:
        result["message"] += " 搜索达到资源或命中数量上限，可缩小页码范围继续。"
    if not has_readable_text and not result["search_limit_reached"]:
        result["error"] = "PDF页面解析失败或超过安全上限。" if result["page_errors"] else OCR_ERROR


def extract_pdf(body: bytes, *, page_start: int = 1, page_end: int | None = None, search: str = "") -> dict:
    """Return selected-page text, or bounded search snippets with coverage.

    Page numbers are one-based physical PDF pages, not printed section/page
    labels. ``truncated=False`` means all requested pages were extracted; use
    ``full_document`` separately to distinguish a subset from the whole PDF.
    Search defaults to the remaining document; plain reading defaults to five
    pages and allows an explicit range of at most twelve pages.
    """
    result = {"content_type": "pdf", "text": "", "pages": [], "total_pages": 0,
              "page_start": None, "page_end": None, "selected_pages": [],
              "truncated": False, "full_document": False, "search_mode": False,
              "unreadable_pages": [], "page_errors": []}
    try:
        terms = _search_terms(search)
        if (type(page_start) is not int or page_start < 1
                or (page_end is not None and (type(page_end) is not int or page_end < page_start))):
            raise PDFError("PDF页码须为从1开始的整数，结束页不得小于起始页。")
        if not isinstance(body, bytes) or not body or len(body) > MAX_PDF_BYTES:
            raise PDFError("PDF文件为空、格式无效或超过20MB读取上限。")
        if not body[:1024].lstrip().startswith(b"%PDF-"):
            raise PDFError("PDF文件格式无效或无法安全解析。")
        reader = PdfReader(io.BytesIO(body), strict=False)
        if reader.is_encrypted:
            raise PDFError("PDF已加密，无法读取；请提供可公开读取的未加密原文。")
        count = len(reader.pages)
        result["total_pages"] = count
        if not 1 <= count <= MAX_DOCUMENT_PAGES:
            raise PDFError("PDF页数为空或超过1500页解析上限。")
        end = page_end if page_end is not None else (count if terms else min(count, page_start + DEFAULT_READ_PAGES - 1))
        if page_start > count or end > count:
            raise PDFError("请求的PDF页码超出文件实际页数。")
        if not terms and end - page_start + 1 > MAX_SELECTED_PAGES:
            raise PDFError("每次最多读取12页PDF正文；请分段读取。")
        result.update(page_start=page_start, page_end=end, selected_pages=list(range(page_start, end + 1)))
        if terms:
            _search_pages(reader, result, terms)
        else:
            _read_pages(reader, result)
    except PDFError as exc:
        result.update(error=str(exc), text="", pages=[], full_document=False)
    except Exception:
        result.update(error="PDF文件格式无效或无法安全解析。", text="", pages=[], full_document=False)
    return result


def main():
    parser = argparse.ArgumentParser(description="Read PDF bytes from stdin and emit JSON.")
    parser.add_argument("--page-start", type=int, default=1)
    parser.add_argument("--page-end", type=int)
    parser.add_argument("--search", default="")
    args = parser.parse_args()
    result = extract_pdf(sys.stdin.buffer.read(MAX_PDF_BYTES + 1),
                         page_start=args.page_start, page_end=args.page_end, search=args.search)
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n")


if __name__ == "__main__":
    main()
