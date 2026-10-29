import inspect
import threading
import unittest
from unittest.mock import patch

try:
    from employment_agent import pdf_download as pdf
except ImportError:
    pdf = None


URL = "https://laws.example/act.pdf"
BODY = b"%PDF-1.7\n" + bytes(range(256)) * 9832


def range_response(body, start, end, *, total=None, **headers):
    end = min(end, len(body) - 1)
    data = body[start:end + 1]
    return URL, {
        "Content-Type": "application/pdf",
        "Content-Range": f"bytes {start}-{end}/{len(body) if total is None else total}",
        "Content-Length": str(len(data)),
        "ETag": '"version-1"',
        **headers,
    }, data


class PDFDownloadTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(pdf, "PDF range downloader is not implemented")

    def test_reassembles_large_file_out_of_order_without_redownloading_prefix(self):
        calls, completed = [], []
        lock, second_done = threading.Lock(), threading.Event()
        active = peak = 0

        def fetch(url, start, end):
            nonlocal active, peak
            with lock:
                calls.append((start, end))
                active += 1
                peak = max(peak, active)
            if start == 65536:
                self.assertTrue(second_done.wait(2))
            elif start > 65536:
                second_done.set()
            result = range_response(BODY, start, end)
            with lock:
                active -= 1
                completed.append(start)
            return result

        url, headers, result = pdf.download_pdf(URL, fetch)
        self.assertEqual(result, BODY)
        self.assertEqual(url, URL)
        self.assertEqual(headers["content-length"], str(len(BODY)))
        self.assertEqual(headers["content-type"], "application/pdf")
        self.assertNotIn("content-range", headers)
        self.assertLessEqual(peak, 4)
        self.assertGreater(peak, 1)
        self.assertNotEqual(completed, sorted(completed))
        intervals = sorted(calls)
        self.assertEqual(intervals[0], (0, 65535))
        self.assertEqual(sum(end - start + 1 for start, end in intervals), len(BODY))
        for previous, current in zip(intervals, intervals[1:]):
            self.assertEqual(previous[1] + 1, current[0])

    def test_accepts_small_pdf_in_first_range(self):
        body = b"%PDF-1.7\nsmall file"
        calls = []
        def fetch(url, start, end):
            calls.append((start, end))
            return range_response(body, start, end)
        self.assertEqual(pdf.download_pdf(URL, fetch)[2], body)
        self.assertEqual(len(calls), 1)

    def test_accepts_bounded_full_response_when_server_ignores_range(self):
        calls = []
        def fetch(url, start, end):
            calls.append((start, end))
            return URL, {"Content-Type": "application/octet-stream"}, BODY
        self.assertEqual(pdf.download_pdf(URL, fetch)[2], BODY)
        self.assertEqual(len(calls), 1)

    def test_rejects_full_response_without_pdf_signature(self):
        with self.assertRaises(pdf.PDFDownloadError):
            pdf.download_pdf(URL, lambda *args: (URL, {"Content-Type": "application/pdf"}, b"not pdf"))

    def test_rejects_oversized_full_response(self):
        with self.assertRaises(pdf.PDFDownloadError):
            pdf.download_pdf(URL, lambda *args: (URL, {}, BODY), max_bytes=100000)

    def test_rejects_oversized_total_before_fetching_other_chunks(self):
        calls = []
        def fetch(url, start, end):
            calls.append((start, end))
            return range_response(BODY, start, end, total=21 * 1024 * 1024)
        with self.assertRaises(pdf.PDFDownloadError):
            pdf.download_pdf(URL, fetch)
        self.assertEqual(len(calls), 1)

    def test_rejects_wrong_first_range_or_malformed_content_range(self):
        for value in ["bytes 1-65536/2517001", "bytes 0-42/*", "bytes 0-65535/2", "garbage"]:
            with self.subTest(value=value), self.assertRaises(pdf.PDFDownloadError):
                pdf.download_pdf(URL, lambda *args: (URL, {"Content-Type": "application/pdf", "Content-Range": value}, BODY[:65536]))

    def test_rejects_truncated_chunk(self):
        def fetch(url, start, end):
            final_url, headers, body = range_response(BODY, start, end)
            return final_url, headers, body[:-1] if start else body
        with self.assertRaises(pdf.PDFDownloadError):
            pdf.download_pdf(URL, fetch)

    def test_rejects_mixed_total(self):
        def fetch(url, start, end):
            return range_response(BODY, start, end, total=len(BODY) + bool(start))
        with self.assertRaises(pdf.PDFDownloadError):
            pdf.download_pdf(URL, fetch)

    def test_rejects_wrong_later_range(self):
        def fetch(url, start, end):
            return range_response(BODY, start + bool(start), end)
        with self.assertRaises(pdf.PDFDownloadError):
            pdf.download_pdf(URL, fetch)

    def test_rejects_changed_or_missing_validators(self):
        for name, changed in [("ETag", '"version-2"'), ("ETag", ""), ("Last-Modified", "Tue, 02 Jan 2024 00:00:00 GMT")]:
            with self.subTest(name=name, changed=changed):
                def fetch(url, start, end):
                    extra = {"Last-Modified": "Mon, 01 Jan 2024 00:00:00 GMT"}
                    if start:
                        extra[name] = changed
                    return range_response(BODY, start, end, **extra)
                with self.assertRaises(pdf.PDFDownloadError):
                    pdf.download_pdf(URL, fetch)

    def test_rejects_same_length_version_mix_without_reliable_validator(self):
        changed_body = BODY[:65536] + b"z" * (len(BODY) - 65536)
        for etag in (None, 'W/"version-1"', "unquoted", '"invalid"tag"'):
            with self.subTest(etag=etag):
                calls = []
                def fetch(url, start, end):
                    calls.append(start)
                    final_url, headers, body = range_response(changed_body if start else BODY, start, end)
                    headers.pop("ETag")
                    if etag is not None:
                        headers["ETag"] = etag
                    return final_url, headers, body
                with self.assertRaises(pdf.PDFDownloadError) as caught:
                    pdf.download_pdf(URL, fetch)
                self.assertIn("版本", str(caught.exception))
                self.assertEqual(calls, [0])

    def test_rejects_invalid_last_modified_without_strong_etag(self):
        for modified in ("not a date", "Mon, 32 Jan 2024 00:00:00 GMT", "Mon, 01 Jan 2024 00:00:00"):
            with self.subTest(modified=modified):
                calls = []
                def fetch(url, start, end):
                    calls.append(start)
                    final_url, headers, body = range_response(BODY, start, end)
                    headers.pop("ETag")
                    headers["Last-Modified"] = modified
                    return final_url, headers, body
                with self.assertRaises(pdf.PDFDownloadError):
                    pdf.download_pdf(URL, fetch)
                self.assertEqual(calls, [0])

    def test_same_second_last_modified_cannot_replace_strong_etag(self):
        changed_body = BODY[:65536] + b"z" * (len(BODY) - 65536)
        for etag in (None, 'W/"version-1"'):
            with self.subTest(etag=etag):
                calls = []
                def fetch(url, start, end):
                    calls.append(start)
                    final_url, headers, body = range_response(changed_body if start else BODY, start, end)
                    headers.pop("ETag")
                    headers["Last-Modified"] = "Mon, 01 Jan 2024 00:00:00 GMT"
                    if etag is not None:
                        headers["ETag"] = etag
                    return final_url, headers, body
                with self.assertRaises(pdf.PDFDownloadError):
                    pdf.download_pdf(URL, fetch)
                self.assertEqual(calls, [0])

    def test_complete_first_range_does_not_require_version_validator(self):
        body = b"%PDF-1.7\nsmall file"
        def fetch(url, start, end):
            final_url, headers, data = range_response(body, start, end)
            headers.pop("ETag")
            return final_url, headers, data
        self.assertEqual(pdf.download_pdf(URL, fetch)[2], body)

    def test_rejects_changed_final_url(self):
        def fetch(url, start, end):
            final_url, headers, body = range_response(BODY, start, end)
            return final_url + ("?v=2" if start else ""), headers, body
        with self.assertRaises(pdf.PDFDownloadError):
            pdf.download_pdf(URL, fetch)

    def test_rejects_full_response_after_partial_response(self):
        def fetch(url, start, end):
            return (URL, {"Content-Type": "application/pdf"}, BODY) if start else range_response(BODY, start, end)
        with self.assertRaises(pdf.PDFDownloadError):
            pdf.download_pdf(URL, fetch)

    def test_identifies_octet_stream_pdf_from_first_chunk_signature(self):
        def fetch(url, start, end):
            return range_response(BODY, start, end, **{"Content-Type": "application/octet-stream"})
        self.assertEqual(pdf.download_pdf(URL, fetch)[2], BODY)

    def test_rejects_non_pdf_first_chunk(self):
        body = b"<html>" + b"x" * 100000
        with self.assertRaises(pdf.PDFDownloadError):
            pdf.download_pdf(URL, lambda url, start, end: range_response(body, start, end, **{"Content-Type": "text/html"}))

    def test_fetch_errors_are_safe_and_never_return_partial_bytes(self):
        for first in (True, False):
            with self.subTest(first=first):
                def fetch(url, start, end):
                    if first or start:
                        raise OSError("SECRET token and private path")
                    return range_response(BODY, start, end)
                with self.assertRaises(pdf.PDFDownloadError) as caught:
                    pdf.download_pdf(URL, fetch)
                self.assertNotIn("SECRET", str(caught.exception))
                self.assertNotIn("private path", str(caught.exception))

    def test_cancels_remaining_work_after_first_failure(self):
        calls = []
        def fetch(url, start, end):
            calls.append(start)
            if start:
                raise OSError("failed")
            return range_response(BODY, start, end)
        with self.assertRaises(pdf.PDFDownloadError):
            pdf.download_pdf(URL, fetch, workers=1)
        self.assertEqual(calls, [0, 65536])

    def test_invalid_limits_fail_before_fetch(self):
        for values in [{"max_bytes": 0}, {"chunk_size": 0}, {"workers": 0}, {"workers": True}, {"max_bytes": 2.5}]:
            with self.subTest(values=values), self.assertRaises(pdf.PDFDownloadError):
                pdf.download_pdf(URL, lambda *args: self.fail("must not fetch"), **values)

    def test_total_timeout_returns_without_waiting_for_blocked_chunks(self):
        self.assertIn("total_timeout", inspect.signature(pdf.download_pdf).parameters)
        release, started, returned = threading.Event(), threading.Event(), threading.Event()
        outcomes = []
        calls = []
        def fetch(url, start, end):
            calls.append(start)
            if start:
                started.set()
                release.wait(2)
            return range_response(BODY, start, end)
        def run():
            try:
                outcomes.append(pdf.download_pdf(URL, fetch, workers=1, total_timeout=0.05))
            except Exception as exc:
                outcomes.append(exc)
            finally:
                returned.set()
        thread = threading.Thread(target=run, daemon=True)
        try:
            thread.start()
            self.assertTrue(started.wait(1), "No chunk request was started")
            self.assertTrue(returned.wait(0.8), "Downloader waited for a blocked request after its deadline")
            self.assertIsInstance(outcomes[0], pdf.PDFDownloadError)
            self.assertIn("超时", str(outcomes[0]))
            self.assertIn("官方", str(outcomes[0]))
            self.assertEqual(calls, [0, 65536])
        finally:
            release.set()
            thread.join(2)
        self.assertFalse(thread.is_alive())

    def test_total_timeout_includes_first_request_elapsed_time(self):
        self.assertIn("total_timeout", inspect.signature(pdf.download_pdf).parameters)
        for partial in (True, False):
            with self.subTest(partial=partial):
                current, calls = [100.0], []
                def fetch(url, start, end):
                    calls.append(start)
                    current[0] = 102.0
                    return range_response(BODY, start, end) if partial else (URL, {}, BODY)
                with patch.object(pdf.time, "monotonic", side_effect=lambda: current[0]):
                    with self.assertRaises(pdf.PDFDownloadError) as caught:
                        pdf.download_pdf(URL, fetch, total_timeout=1)
                self.assertIn("超时", str(caught.exception))
                self.assertEqual(calls, [0])

    def test_invalid_total_timeout_fails_before_fetch(self):
        self.assertIn("total_timeout", inspect.signature(pdf.download_pdf).parameters)
        for value in (0, -1, True, float("inf"), float("nan"), "100", None):
            with self.subTest(value=value), self.assertRaises(pdf.PDFDownloadError):
                pdf.download_pdf(URL, lambda *args: self.fail("must not fetch"), total_timeout=value)


if __name__ == "__main__":
    unittest.main()
