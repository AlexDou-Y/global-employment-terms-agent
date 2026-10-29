"""Offline extraction checks using explicitly fictional, in-memory PDFs."""

import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

try:
    from employment_agent import pdf_reader as pdf
except ImportError:
    pdf = None


def make_pdf(*texts, password=None):
    """Build real PDF text streams; these examples make no legal claims."""
    writer = PdfWriter()
    font = writer._add_object(DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    }))
    for text in texts:
        page = writer.add_blank_page(width=612, height=792)
        if not text:
            continue
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
        })
        safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 50 700 Td ({safe}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    if password is not None:
        writer.encrypt(password)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


class PDFReaderTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(pdf, "PDF reader is not implemented")

    def test_default_read_is_first_five_pages_with_physical_page_numbers(self):
        result = pdf.extract_pdf(make_pdf(*(f"Fictional page {n}" for n in range(1, 8))))
        self.assertNotIn("error", result)
        self.assertEqual(result["content_type"], "pdf")
        self.assertEqual(result["total_pages"], 7)
        self.assertEqual((result["page_start"], result["page_end"]), (1, 5))
        self.assertEqual(result["selected_pages"], [1, 2, 3, 4, 5])
        self.assertEqual([page["page"] for page in result["pages"]], [1, 2, 3, 4, 5])
        self.assertIn("[PDF page 5]\nFictional page 5", result["text"])
        self.assertNotIn("page 6", result["text"])
        self.assertFalse(result["truncated"])
        self.assertFalse(result["full_document"])

    def test_explicit_range_returns_complete_selected_evidence(self):
        result = pdf.extract_pdf(make_pdf("cover", "Pasal 12 PKWT: fictional five years", "annex"), page_start=2, page_end=2)
        self.assertEqual(result["selected_pages"], [2])
        self.assertEqual(result["pages"], [{"page": 2, "text": "Pasal 12 PKWT: fictional five years"}])
        self.assertFalse(result["truncated"])
        self.assertFalse(result["full_document"])

    def test_whole_short_document_is_marked_complete(self):
        result = pdf.extract_pdf(make_pdf("A", "B"))
        self.assertTrue(result["full_document"])
        self.assertFalse(result["truncated"])
        self.assertEqual(result["unreadable_pages"], [])

    def test_invalid_page_ranges_are_errors(self):
        body = make_pdf(*("text" for _ in range(14)))
        for kwargs in [{"page_start": 0}, {"page_start": True}, {"page_start": "1"},
                       {"page_start": 15}, {"page_end": 15}, {"page_end": False},
                       {"page_start": 3, "page_end": 2}, {"page_end": 13}]:
            with self.subTest(kwargs=kwargs):
                result = pdf.extract_pdf(body, **kwargs)
                self.assertIn("error", result)
                self.assertEqual(result["text"], "")

    def test_default_range_is_capped_at_end_of_document(self):
        result = pdf.extract_pdf(make_pdf("A", "B", "C"), page_start=3)
        self.assertEqual(result["selected_pages"], [3])
        self.assertFalse(result["truncated"])

    def test_text_and_page_text_obey_total_output_cap(self):
        result = pdf.extract_pdf(make_pdf("A" * 30000, "tail"))
        self.assertEqual(len(result["text"]), 28000)
        self.assertLessEqual(sum(len(p["text"]) for p in result["pages"]), 28000)
        self.assertTrue(result["truncated"])
        self.assertFalse(result["full_document"])

    def test_blank_pdf_has_explicit_ocr_error(self):
        result = pdf.extract_pdf(make_pdf("", ""))
        self.assertEqual(result["error"], "PDF未提取到可读文字，可能为扫描件，需要OCR")
        self.assertEqual(result["text"], "")
        self.assertFalse(result["full_document"])
        self.assertEqual(result["unreadable_pages"], [1, 2])

    def test_mixed_blank_pages_are_not_presented_as_complete(self):
        result = pdf.extract_pdf(make_pdf("text", ""))
        self.assertNotIn("error", result)
        self.assertEqual(result["unreadable_pages"], [2])
        self.assertTrue(result["truncated"])
        self.assertFalse(result["full_document"])

    def test_search_finds_later_pages_and_returns_navigation_snippets(self):
        texts = [f"Fictional cover {n}" for n in range(8)]
        texts[6] = "Pasal   12. PKWT fictional maximum 5 years."
        result = pdf.extract_pdf(make_pdf(*texts), search="pasal 12|PKWT")
        self.assertNotIn("error", result)
        self.assertTrue(result["search_mode"])
        self.assertEqual(result["matched_pages"], [7])
        self.assertEqual(result["pages_searched"], 8)
        self.assertTrue(result["search_complete"])
        self.assertEqual(result["hits"][0]["page"], 7)
        self.assertIn("PKWT fictional maximum 5 years", result["hits"][0]["snippet"])
        self.assertIn("[PDF page 7]", result["text"])
        self.assertTrue(result["truncated"])
        self.assertFalse(result["full_document"])
        self.assertEqual(result["pages"], [])

    def test_search_is_literal_casefolded_and_deduplicates_alternatives(self):
        result = pdf.extract_pdf(make_pdf("PKWT appears", "a.*b literal", "axxb"), search=" PKWT |pkwt|a.*b ")
        self.assertEqual(result["search_terms"], ["pkwt", "a.*b"])
        self.assertEqual(result["matched_pages"], [1, 2])
        self.assertIn("literal", result["search_strategy"])

    def test_no_hits_are_explicit_and_do_not_imply_absent_legal_rule(self):
        result = pdf.extract_pdf(make_pdf("Fictional unrelated article"), search="PKWT")
        self.assertNotIn("error", result)
        self.assertEqual(result["hits"], [])
        self.assertEqual(result["matched_pages"], [])
        self.assertEqual(result["pages_searched"], 1)
        self.assertEqual(result["text"], "")
        self.assertIn("不能据此认定", result["message"])

    def test_search_blank_document_reports_ocr(self):
        result = pdf.extract_pdf(make_pdf("", ""), search="PKWT")
        self.assertIn("需要OCR", result["error"])
        self.assertFalse(result["search_complete"])

    def test_search_coverage_includes_unreadable_pages(self):
        result = pdf.extract_pdf(make_pdf("PKWT", ""), search="PKWT")
        self.assertEqual(result["unreadable_pages"], [2])
        self.assertEqual(result["pages_searched"], 2)
        self.assertFalse(result["search_complete"])

    def test_search_explicit_range_does_not_claim_full_document_search(self):
        result = pdf.extract_pdf(make_pdf("cover", "PKWT", "PKWT"), page_start=2, page_end=2, search="PKWT")
        self.assertEqual(result["matched_pages"], [2])
        self.assertEqual(result["pages_searched"], 1)
        self.assertTrue(result["search_complete"])
        self.assertFalse(result["whole_document_searched"])

    def test_search_hit_limit_is_reported_as_partial(self):
        result = pdf.extract_pdf(make_pdf(*("PKWT" for _ in range(35))), search="PKWT")
        self.assertEqual(len(result["hits"]), 30)
        self.assertFalse(result["search_complete"])
        self.assertFalse(result["whole_document_searched"])
        self.assertLess(result["pages_searched"], 35)

    def test_search_character_budget_stops_with_honest_coverage(self):
        with patch.object(pdf, "MAX_SCAN_CHARS", 20):
            result = pdf.extract_pdf(make_pdf("Fictional long unrelated page", "PKWT"), search="PKWT")
        self.assertEqual(result["hits"], [])
        self.assertFalse(result["search_complete"])
        self.assertLess(result["pages_searched"], 2)

    def test_invalid_queries_are_safe_errors(self):
        for query in [12, None, "x" * 201, "a|b|c|d|e|f|g|h|i", "|", "a\x00b", "\ud800"]:
            with self.subTest(query=repr(query)):
                result = pdf.extract_pdf(make_pdf("text"), search=query)
                self.assertIn("error", result)
                self.assertEqual(result["text"], "")
                json.dumps(result, ensure_ascii=False).encode("utf-8")

    def test_encrypted_and_malformed_pdfs_fail_safely(self):
        for body in [make_pdf("private", password="secret"), b"%PDF-1.7\nmalformed private-file sk-secret", b"", "not bytes"]:
            with self.subTest(body_type=type(body).__name__):
                result = pdf.extract_pdf(body)
                self.assertIn("error", result)
                self.assertEqual(result["text"], "")
                self.assertNotIn("private-file", json.dumps(result))
                self.assertNotIn("sk-secret", json.dumps(result))

    def test_byte_and_document_page_limits(self):
        with patch.object(pdf, "MAX_PDF_BYTES", 20):
            self.assertIn("error", pdf.extract_pdf(make_pdf("text")))
        with patch.object(pdf, "MAX_DOCUMENT_PAGES", 2):
            result = pdf.extract_pdf(make_pdf("A", "B", "C"))
        self.assertIn("error", result)

    def test_cli_accepts_bytes_and_emits_only_utf8_json(self):
        result = subprocess.run(
            [sys.executable, str(Path(pdf.__file__).resolve()), "--page-start", "2", "--page-end", "2"],
            input=make_pdf("cover", "PKWT fictional example"), capture_output=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0)
        data = json.loads(result.stdout.decode("utf-8"))
        self.assertNotIn("error", data)
        self.assertEqual(data["selected_pages"], [2])
        self.assertIn("PKWT fictional example", data["text"])


if __name__ == "__main__":
    unittest.main()
