import json
import tempfile
import unittest
from pathlib import Path

from employment_agent.storage import ReportStore


def report(query_mode="rules", details=""):
    return {"jurisdiction": "示例地区", "mode": "live", "generated_at": "2026-10-29T00:00:00Z",
            "as_of_date": "2026-10-29", "summary": "来源待核验", "findings": [], "sources": [],
            "query": {"country": "示例地区", "nationality": "示例国籍", "subdivision": "",
                      "employment_model": "direct", "query_mode": query_mode,
                      "as_of_date": "2026-10-29", "details": details}}


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = ReportStore(Path(self.temp.name))

    def test_saved_report_roundtrip_and_history(self):
        data = report()
        data["provider"] = "codex"
        item = self.store.save(data, "# 报告\n中文")
        self.assertEqual(self.store.get(item["id"])["markdown"], "# 报告\n中文")
        self.assertEqual(self.store.list_reports()[0]["id"], item["id"])
        self.assertEqual(self.store.list_reports()[0]["provider"], "codex")

    def test_credential_fields_never_persist(self):
        data = report()
        data["api_key"] = "secret-should-never-be-written"
        data["query"]["api_key"] = "secret-should-never-be-written"
        self.store.save(data, "# 安全报告")
        for path in Path(self.temp.name).rglob("*.json"):
            self.assertNotIn("secret-should-never-be-written", path.read_text(encoding="utf-8"))

    def test_only_general_live_rules_are_reused(self):
        data = report()
        self.store.save(data, "# 报告")
        self.assertEqual(self.store.get_prior_rules(data["query"])["jurisdiction"], "示例地区")
        self.assertIsNone(self.store.get_prior_rules(report("case")["query"]))
        self.assertIsNone(self.store.get_prior_rules(report(details="个人场景")["query"]))

    def test_case_demo_and_details_do_not_create_rule_cards(self):
        data = report("case")
        self.store.save(data, "case")
        data = report()
        data["mode"] = "demo"
        self.store.save(data, "demo")
        self.store.save(report(details="个人场景"), "details")
        self.assertEqual(list((Path(self.temp.name) / "rules").glob("*.json")), [])

    def test_path_traversal_is_rejected(self):
        with self.assertRaises(ValueError):
            self.store.get("../../secret")

    def test_corrupt_history_does_not_hide_good_reports(self):
        self.store.save(report(), "# 报告")
        (Path(self.temp.name) / "reports" / ("a" * 32 + ".json")).write_text("{", encoding="utf-8")
        self.assertEqual(len(self.store.list_reports()), 1)


if __name__ == "__main__":
    unittest.main()
