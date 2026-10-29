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

    def test_recovered_report_explains_interrupted_research_before_findings(self):
        report = make_demo_report()
        report.update(mode="live", research_incomplete=True, recovery_reason="research_timeout",
                      summary="已读材料已整理，最新判例仍待确认。")
        text = render_markdown(report)
        notice = "本报告依据中断前实际读取的材料恢复整理，未完成核查项仍待确认。"
        self.assertIn(notice, text)
        self.assertLess(text.index(notice), text.index("## 范围与结论"))
        self.assertIn(report["summary"], text)
        self.assertEqual(len(report["findings"]), 5)

    def test_recovery_notice_is_not_added_to_demo_or_unflagged_live_report(self):
        for mode, incomplete in [("demo", True), ("live", False), ("live", "true")]:
            with self.subTest(mode=mode, incomplete=incomplete):
                report = make_demo_report()
                report.update(mode=mode, research_incomplete=incomplete)
                self.assertNotIn("依据中断前实际读取的材料恢复整理", render_markdown(report))

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
        self.assertIn("正文读取未确认", text)
        self.assertIn("官方（AI 分类）", text)
        self.assertIn("2026-10-29", text)
        self.assertIn("生效", text)

    def test_read_page_does_not_assert_legal_text_was_obtained(self):
        report = make_demo_report()
        report["sources"] = [{"id": "S1", "title": "Regulation detail page", "url": "https://example.test/regulation", "publisher": "Authority", "source_type": "official", "locator": "Document metadata", "excerpt": "Document title and publication date only", "effective_date": "unknown", "accessed_on": "2026-10-29", "observed_in_search": True, "opened_by_tool": True, "document_type": "html"}]
        text = render_markdown(report)
        self.assertIn("工具已读取内容", text)
        self.assertIn("发现来源链接不等于已读取内容", text)
        self.assertIn("已读取内容不等于已取得支持本项结论的条文", text)
        self.assertIn("Document metadata", text)
        self.assertNotIn("打开原文", text)
        self.assertNotIn("PDF 已读页码", text)

    def test_pdf_exports_selected_page_coverage_without_claiming_full_text_read(self):
        report = make_demo_report()
        report["sources"] = [{"id": "S1", "title": "Regulation PDF", "url": "https://example.test/regulation.pdf", "publisher": "Authority", "source_type": "official", "locator": "Article 4, page 7", "excerpt": "Selected provision", "effective_date": "unknown", "accessed_on": "2026-10-29", "observed_in_search": True, "opened_by_tool": True, "document_type": "pdf", "pages_read": [2, 7], "total_pages": 35, "text_extraction": "pdf_text"}]
        text = render_markdown(report)
        self.assertIn("- PDF 已读页码：2、7", text)
        self.assertIn("- PDF 总页数：35", text)
        self.assertIn("Article 4, page 7", text)
        self.assertIn("Selected provision", text)
        self.assertIn("搜索摘要不计为已读正文", text)
        self.assertIn("不代表全文完整读取", text)
        self.assertNotIn("打开原文", text)

    def test_unsafe_links_and_html_not_emitted(self):
        report = make_demo_report()
        report["summary"] = "<script>alert('x')</script>"
        report["sources"] = [{"id": "S1", "title": "Bad", "url": "javascript:alert(1)", "publisher": "", "source_type": "other", "locator": "", "excerpt": "", "effective_date": "unknown", "accessed_on": "unknown", "observed_in_search": False, "opened_by_tool": False}]
        text = render_markdown(report)
        self.assertNotIn("<script>", text)
        self.assertNotIn("javascript:", text)


if __name__ == "__main__":
    unittest.main()
