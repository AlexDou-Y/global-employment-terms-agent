"""Bounded PDF range assembly; the caller supplies all network and URL policy.

``fetch_range(url, start, end)`` must return (final_url, headers, bytes), with
inclusive byte offsets. It must enforce safe redirects, response-size limits,
and a per-call timeout, and must be safe to call from multiple threads.
No incomplete document is returned. Running requests cannot be interrupted by
Python's thread pool; on failure pending work is cancelled and running requests
finish under the fetcher's own timeout.
"""

import math
import re
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait


class PDFDownloadError(Exception):
    """Fixed safe diagnostics without URLs, response text or network details."""


def _request(fetch_range, url, start, end, max_bytes):
    try:
        final_url, headers, body = fetch_range(url, start, end)
        headers = {str(key).lower(): str(value).strip() for key, value in headers.items()}
    except Exception:
        raise PDFDownloadError("PDF 分段下载失败，请稍后重试。") from None
    if not isinstance(final_url, str) or not final_url or not isinstance(body, bytes):
        raise PDFDownloadError("PDF 下载响应格式无效。")
    if not body or len(body) > max_bytes:
        raise PDFDownloadError("PDF 下载为空或超过读取大小上限。")
    declared = headers.get("content-length")
    if declared is not None and declared != str(len(body)):
        raise PDFDownloadError("PDF 响应长度与实际下载内容不一致。")
    return final_url, headers, body


def _range_total(headers, body, start, end, max_bytes):
    match = re.fullmatch(r"bytes\s+(\d+)-(\d+)/(\d+)", headers.get("content-range", ""), re.IGNORECASE)
    if match is None:
        raise PDFDownloadError("PDF 分段响应缺少有效的字节范围。")
    try:
        actual_start, actual_end, total = map(int, match.groups())
    except ValueError:
        raise PDFDownloadError("PDF 分段响应的字节范围无效。") from None
    if total <= 0 or total > max_bytes:
        raise PDFDownloadError("PDF 文件超过读取大小上限或长度无效。")
    if (actual_start != start or actual_end != min(end, total - 1)
            or actual_end < actual_start or len(body) != actual_end - actual_start + 1):
        raise PDFDownloadError("PDF 分段范围或内容长度不一致。")
    return total


def _document_headers(headers, total):
    result = dict(headers)
    result.pop("content-range", None)
    result["content-length"] = str(total)
    result["content-type"] = "application/pdf"
    return result


def _has_version_validator(headers):
    # Weak tags and second-resolution modification dates cannot establish
    # byte-for-byte identity across separate range responses.
    return re.fullmatch(r'"[\x21\x23-\x7e\x80-\xff]*"', headers.get("etag", "")) is not None


def _remaining_time(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise PDFDownloadError("PDF 下载超时，可选择其他官方镜像或较小文件后重试。")
    return remaining


def download_pdf(url, fetch_range, *, max_bytes=20 * 1024 * 1024,
                 chunk_size=512 * 1024, workers=4, total_timeout=100):
    """Return a complete PDF as ``(final_url, lowercase_headers, bytes)``.

    Probe the first 64 KiB, then download remaining ranges with bounded parallel
    requests. A range-ignoring server is accepted only when its first response
    contains a bounded full document beginning with the PDF signature. For range
    responses, the initial MIME type or signature identifies the document; later
    chunks require a strong ETag and are validated against the initial URL,
    total size and both HTTP validators. The deadline includes time spent in
    the first request, which is bounded by the fetcher's own request timeout.
    Concurrent waits stop at the deadline without waiting for running requests.
    """
    if any(type(value) is not int or value <= 0 for value in (max_bytes, chunk_size, workers)):
        raise PDFDownloadError("PDF 下载大小、分段大小和并发数必须为正整数。")
    if type(total_timeout) not in (int, float):
        raise PDFDownloadError("PDF 下载总超时必须为有限正数。")
    try:
        timeout_seconds = float(total_timeout)
    except OverflowError:
        raise PDFDownloadError("PDF 下载总超时必须为有限正数。") from None
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise PDFDownloadError("PDF 下载总超时必须为有限正数。")

    deadline = time.monotonic() + timeout_seconds
    probe_end = min(65536, max_bytes) - 1
    final_url, headers, prefix = _request(fetch_range, url, 0, probe_end, max_bytes)
    _remaining_time(deadline)
    if "content-range" not in headers:
        if not prefix.startswith(b"%PDF-"):
            raise PDFDownloadError("服务器未返回可识别的完整 PDF 文件。")
        return final_url, _document_headers(headers, len(prefix)), prefix

    total = _range_total(headers, prefix, 0, probe_end, max_bytes)
    mime = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if mime != "application/pdf" and not prefix.startswith(b"%PDF-"):
        raise PDFDownloadError("服务器未返回可识别的 PDF 文件。")
    if len(prefix) == total:
        return final_url, _document_headers(headers, total), prefix
    if not _has_version_validator(headers):
        raise PDFDownloadError("PDF 缺少可靠的文件版本标识，无法安全合并分段内容。")

    validators = tuple(headers.get(name) for name in ("etag", "last-modified"))
    chunks = {0: prefix}
    offsets = iter(range(len(prefix), total, chunk_size))
    executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="pdf-range")
    pending = {}
    complete = False

    def submit_next():
        _remaining_time(deadline)
        start = next(offsets, None)
        if start is None:
            return False
        end = min(start + chunk_size, total) - 1
        future = executor.submit(_request, fetch_range, final_url, start, end, max_bytes)
        pending[future] = (start, end)
        return True

    try:
        for _ in range(workers):
            if not submit_next():
                break
        while pending:
            done, _ = wait(pending, timeout=_remaining_time(deadline), return_when=FIRST_COMPLETED)
            _remaining_time(deadline)
            if not done:
                raise PDFDownloadError("PDF 下载超时，可选择其他官方镜像或较小文件后重试。")
            for future in done:
                start, end = pending.pop(future)
                chunk_url, chunk_headers, body = future.result()
                chunk_total = _range_total(chunk_headers, body, start, end, max_bytes)
                chunk_validators = tuple(chunk_headers.get(name) for name in ("etag", "last-modified"))
                if chunk_url != final_url or chunk_total != total or chunk_validators != validators:
                    raise PDFDownloadError("PDF 文件地址、长度或版本在下载期间发生变化，请重试。")
                chunks[start] = body
            for _ in done:
                if not submit_next():
                    break
        complete = True
    except PDFDownloadError:
        raise
    except Exception:
        raise PDFDownloadError("PDF 分段下载失败，请稍后重试。") from None
    finally:
        for future in pending:
            future.cancel()
        executor.shutdown(wait=complete, cancel_futures=True)

    cursor, ordered = 0, []
    for start in sorted(chunks):
        if start != cursor:
            raise PDFDownloadError("PDF 下载分段不完整。")
        ordered.append(chunks[start])
        cursor += len(chunks[start])
    if cursor != total:
        raise PDFDownloadError("PDF 下载总长度不完整。")
    document = b"".join(ordered)
    _remaining_time(deadline)
    return final_url, _document_headers(headers, total), document
