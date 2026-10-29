import unittest

try:
    from employment_agent.demo import make_demo_report
    from employment_agent.reports import render_markdown
except ImportError:
    make_demo_report = render_markdown = None


class ReportExportTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(make_demo_report, "Demo report is not implemented")
        self.assertIsNotNone(render_markdown, "Markdown report is not implemented")

    def test_demo_never_asserts_real_law(self):
        report = make_demo_report({"country": "Japan", "nationality": "China"})
        self.assertEqual(report["mode"], "demo")
        self.assertIn("虚构", report["jurisdiction"])
        self.assertEqual(report["sources"], [])
        self.assertEqual(len(report["findings"]), 5)
        self.assertTrue(all(x["rule_status"] == "unverified" for x in report["findings"]))
        self.assertTrue(all(x["evidence_ids"] == [] for x in report["findings"]))
        self.assertEqual(report["web_search_count"], 0)

    def test_markdown_contains_five_topics_followups_and_demo_warning(self):
        text = render_markdown(make_demo_report())
        for label in ["演示", "虚构", "固定期限", "续签", "试用期", "解除", "待补充", "HR", "未核实"]:
            self.assertIn(label, text)

    def test_demo_preserves_exact_query_jurisdiction_identity_and_exports_it(self):
        report = make_demo_report({"country": " Japan ", "nationality": "China", "subdivision": " Tokyo "})
        self.assertEqual(report.get("jurisdiction_country"), "Japan")
        self.assertEqual(report.get("jurisdiction_subdivision"), "Tokyo")
        text = render_markdown(report)
        self.assertIn("- 查询国家/地区：Japan", text)
        self.assertIn("- 查询州/省：Tokyo", text)

    def test_sources_render_metadata_and_safe_links(self):
        report = make_demo_report()
        report["sources"] = [{"id": "S1", "title": "Law [test]", "url": "https://example.test/law?q=a&b=c", "publisher": "Authority", "source_type": "official", "locator": "Article 1", "excerpt": "Text", "effective_date": "unknown", "accessed_on": "2026-10-29", "observed_in_search": True, "opened_by_tool": False}]
        text = render_markdown(report)
        self.assertIn("https://example.test/law", text)
        self.assertIn("Article 1", text)
        self.assertIn("未确认打开原文", text)
        self.assertIn("2026-10-29", text)
        self.assertIn("生效", text)

    def test_unsafe_links_and_html_not_emitted(self):
        report = make_demo_report()
        report["summary"] = "<script>alert('x')</script>"
        report["sources"] = [{"id": "S1", "title": "Bad", "url": "javascript:alert(1)", "publisher": "", "source_type": "other", "locator": "", "excerpt": "", "effective_date": "unknown", "accessed_on": "unknown", "observed_in_search": False, "opened_by_tool": False}]
        text = render_markdown(report)
        self.assertNotIn("<script>", text)
        self.assertNotIn("javascript:", text)


if __name__ == "__main__":
    unittest.main()
