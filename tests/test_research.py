import copy
import json
import unittest
from unittest.mock import patch
import urllib.error

try:
    from employment_agent.research import ResearchError, run_research
except ImportError:
    run_research = None
    ResearchError = RuntimeError


TOPICS = ["fixed_term_allowed", "fixed_term_duration", "renewal_conversion", "probation", "probation_termination"]
QUERY = {"country": "Test jurisdiction", "nationality": "Test nationality", "as_of_date": "2026-10-29"}
OFFICIAL_URL = "https://labor.example.test/act"


def report_fixture():
    return {
        "jurisdiction": "Test jurisdiction", "jurisdiction_country": QUERY["country"],
        "jurisdiction_subdivision": "", "as_of_date": QUERY["as_of_date"],
        "scope": "Fictional test fixture", "summary": "Fixture only",
        "assumptions": [], "follow_up_questions": ["Confirm employer"], "hr_actions": ["Obtain local review"],
        "findings": [{"topic": topic, "rule_status": "supported", "rule_summary": "Fictional test statement", "application_status": "general_rule", "application_note": "Only a general rule", "conditions": [], "exceptions": [], "evidence_ids": ["S1"]} for topic in TOPICS],
        "sources": [{"id": "S1", "title": "Fictional test source", "url": OFFICIAL_URL, "publisher": "Test authority", "source_type": "official", "locator": "Article 1", "excerpt": "Fictional test text", "effective_date": "2020-01-01", "accessed_on": "2026-10-29"}],
    }


def researched_response(opened=True, search=True):
    output = []
    if search:
        output.append({"type": "web_search_call", "status": "completed", "action": {"type": "search", "sources": [{"type": "url", "url": OFFICIAL_URL}]}})
    if opened:
        output.append({"type": "web_search_call", "status": "completed", "action": {"type": "open_page", "url": OFFICIAL_URL}})
    output.append({"type": "message", "content": [{"type": "output_text", "text": "Fictional research transcript", "annotations": [{"type": "url_citation", "url": OFFICIAL_URL, "title": "Test source"}]}]})
    return {"status": "completed", "output": output}


def structured_response(report=None):
    return {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(report or report_fixture()), "annotations": []}]}]}


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(run_research, "Research engine is not implemented")

    def run_fixture(self, report=None, first=None, query=None):
        responses = [first or researched_response(), structured_response(report)]
        calls = []
        def transport(payload, api_key):
            calls.append(copy.deepcopy(payload))
            self.assertEqual(api_key, "test-key")
            return responses.pop(0)
        result = run_research(query or QUERY, "test-key", transport=transport)
        return result, calls

    def test_two_phase_research_and_runtime_metadata(self):
        result, calls = self.run_fixture()
        self.assertEqual(len(calls), 2)
        first, second = calls
        self.assertFalse(first["store"])
        self.assertFalse(second["store"])
        self.assertEqual(first["tools"][0]["type"], "web_search")
        self.assertTrue(first["tools"][0]["external_web_access"])
        self.assertEqual(first["tool_choice"], "required")
        self.assertIn("web_search_call.action.sources", first["include"])
        self.assertNotIn("tools", second)
        self.assertTrue(second["text"]["format"]["strict"])
        self.assertEqual(second["text"]["format"]["type"], "json_schema")
        self.assertEqual(result["mode"], "live")
        self.assertEqual(result["model"], "gpt-5.5")
        self.assertEqual(result["web_search_count"], 1)
        self.assertTrue(result["sources"][0]["observed_in_search"])
        self.assertTrue(result["sources"][0]["opened_by_tool"])
        self.assertEqual(result["findings"][0]["rule_status"], "supported")
        self.assertTrue(result["verification_notes"])
        self.assertNotIn("test-key", json.dumps(result))

    def test_schema_requires_every_object_field_and_no_extras(self):
        _, calls = self.run_fixture()
        schema = calls[1]["text"]["format"]["schema"]
        def check(node):
            if isinstance(node, dict):
                if node.get("type") == "object":
                    self.assertFalse(node["additionalProperties"])
                    self.assertEqual(set(node["required"]), set(node["properties"]))
                for value in node.values():
                    check(value)
            elif isinstance(node, list):
                for value in node:
                    check(value)
        check(schema)

    def test_exact_jurisdiction_fields_allow_translated_display_name(self):
        report = report_fixture()
        report.update({"jurisdiction": "任意中文展示名称", "jurisdiction_country": QUERY["country"], "jurisdiction_subdivision": "Test province"})
        result, _ = self.run_fixture(report, query={**QUERY, "subdivision": " Test province "})
        self.assertEqual(result["jurisdiction_country"], QUERY["country"])
        self.assertEqual(result["jurisdiction_subdivision"], "Test province")
        self.assertEqual(result["jurisdiction"], "任意中文展示名称")

    def test_mismatched_or_missing_jurisdiction_identity_is_rejected(self):
        for field, value in [("jurisdiction_country", "Different country"), ("jurisdiction_subdivision", "Different province"), ("jurisdiction_country", None), ("jurisdiction_subdivision", None)]:
            report = report_fixture()
            report.update({"jurisdiction_country": QUERY["country"], "jurisdiction_subdivision": ""})
            if value is None:
                del report[field]
            else:
                report[field] = value
            with self.subTest(field=field, value=value):
                with self.assertRaises(ResearchError):
                    self.run_fixture(report)

    def test_missing_or_unfinished_actual_search_is_rejected(self):
        fixtures = [researched_response(search=False), researched_response()]
        fixtures[1]["output"][0]["status"] = "in_progress"
        for first in fixtures:
            with self.subTest(first=first):
                with self.assertRaises(ResearchError):
                    self.run_fixture(first=first)

    def test_generated_url_is_not_a_valid_source(self):
        report = report_fixture()
        report["sources"][0]["url"] = "https://invented.example.test/law"
        result, _ = self.run_fixture(report)
        self.assertEqual(result["sources"], [])
        self.assertEqual(result["findings"][0]["evidence_ids"], [])
        self.assertEqual(result["findings"][0]["rule_status"], "unverified")

    def test_unopened_or_nonofficial_or_unknown_effectivity_downgrades(self):
        scenarios = [(researched_response(opened=False), None, None)]
        for field, value in [("source_type", "vendor"), ("effective_date", "unknown"), ("locator", ""), ("excerpt", "")]:
            scenarios.append((researched_response(), field, value))
        for first, field, value in scenarios:
            report = report_fixture()
            if field:
                report["sources"][0][field] = value
            with self.subTest(field=field):
                result, _ = self.run_fixture(report, first)
                self.assertNotEqual(result["findings"][0]["rule_status"], "supported")
                self.assertTrue(result["verification_notes"])

    def test_citation_without_source_list_still_records_observed_url(self):
        first = researched_response()
        first["output"][0]["action"]["sources"] = []
        result, _ = self.run_fixture(first=first)
        self.assertEqual(result["findings"][0]["rule_status"], "supported")

    def test_open_page_without_citation_or_search_source_is_not_observed(self):
        first = researched_response()
        first["output"][0]["action"]["sources"] = []
        first["output"][2]["content"][0]["annotations"] = []
        result, _ = self.run_fixture(first=first)
        self.assertEqual(result["findings"][0]["rule_status"], "unverified")
        self.assertEqual(result["sources"], [])

    def test_unknown_evidence_id_is_removed_and_flagged(self):
        report = report_fixture()
        report["findings"][0]["evidence_ids"] = ["missing"]
        result, _ = self.run_fixture(report)
        self.assertEqual(result["findings"][0]["rule_status"], "unverified")
        self.assertEqual(result["findings"][0]["evidence_ids"], [])

    def test_general_rules_do_not_become_definitive_case_advice(self):
        report = report_fixture()
        report["findings"][0]["application_status"] = "meets_conditions"
        report["findings"][0]["application_note"] = "You can dismiss now"
        result, _ = self.run_fixture(report)
        self.assertEqual(result["findings"][0]["application_status"], "general_rule")
        self.assertNotIn("dismiss", result["findings"][0]["application_note"])

    def test_wrong_as_of_date_topics_types_or_extra_fields_rejected(self):
        reports = []
        report = report_fixture(); report["as_of_date"] = "2025-01-01"; reports.append(report)
        report = report_fixture(); report["findings"].pop(); reports.append(report)
        report = report_fixture(); report["findings"][1]["topic"] = TOPICS[0]; reports.append(report)
        report = report_fixture(); report["assumptions"] = "bad"; reports.append(report)
        report = report_fixture(); report["secret"] = "extra"; reports.append(report)
        report = report_fixture(); report["sources"][0]["source_type"] = "courtish"; reports.append(report)
        for report in reports:
            with self.subTest(report=str(report)[:150]):
                with self.assertRaises(ResearchError):
                    self.run_fixture(report)

    def test_refusal_incomplete_and_invalid_json_rejected(self):
        broken = [
            {"status": "incomplete", "output": []},
            {"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "No"}]}]},
            {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": "not json"}]}]},
        ]
        for response in broken:
            calls = [researched_response(), response]
            with self.subTest(response=response):
                with self.assertRaises(ResearchError):
                    run_research(QUERY, "test-key", transport=lambda p, k: calls.pop(0))

    def test_transport_error_does_not_leak_credential_or_body(self):
        def fail(payload, api_key):
            raise TimeoutError("test-key private provider response")
        with self.assertRaises(ResearchError) as caught:
            run_research(QUERY, "test-key", transport=fail)
        self.assertNotIn("test-key", str(caught.exception))
        self.assertNotIn("private", str(caught.exception))

    def test_rules_cache_cannot_replace_live_search(self):
        calls = []
        def transport(payload, key):
            calls.append(payload)
            return researched_response(search=False)
        with self.assertRaises(ResearchError):
            run_research(QUERY, "test-key", prior_rules=report_fixture(), transport=transport)
        self.assertEqual(len(calls), 1)

    def test_malformed_provider_shapes_return_safe_research_errors(self):
        invalid = [
            {"status": "completed", "output": None},
            {"status": "completed", "output": [{"type": "message", "content": None}]},
            {"status": "completed", "output": [{"type": "web_search_call", "status": "completed", "action": None}]},
            {"status": "completed", "output": [{"type": "web_search_call", "status": "completed", "action": {"type": "search", "sources": None}}]},
        ]
        for response in invalid:
            with self.subTest(response=response):
                with self.assertRaises(ResearchError):
                    run_research(QUERY, "test-key", transport=lambda p, k: response)

    def test_future_effectivity_and_placeholder_locator_not_fully_supported(self):
        for field, value in [("effective_date", "2030-01-01"), ("locator", "unknown"), ("excerpt", "待核验")]:
            report = report_fixture()
            report["sources"][0][field] = value
            result, _ = self.run_fixture(report)
            self.assertEqual(result["findings"][0]["rule_status"], "partial")

    def test_every_cited_official_source_must_meet_evidence_requirements(self):
        second_url = "https://labor.example.test/amendment"
        for opened, effective_date in [(False, "2020-01-01"), (True, "unknown")]:
            report = report_fixture()
            second = {**report["sources"][0], "id": "S2", "url": second_url, "effective_date": effective_date}
            report["sources"].append(second)
            report["findings"][0]["evidence_ids"].append("S2")
            first = researched_response()
            first["output"][0]["action"]["sources"].append({"type": "url", "url": second_url})
            if opened:
                first["output"].append({"type": "web_search_call", "status": "completed", "action": {"type": "open_page", "url": second_url}})
            with self.subTest(opened=opened, effective_date=effective_date):
                result, _ = self.run_fixture(report, first)
                self.assertEqual(result["findings"][0]["rule_status"], "partial")
                self.assertEqual(result["findings"][1]["rule_status"], "supported")

    def test_unverified_or_downgraded_findings_qualify_summary(self):
        for status in ["partial", "unverified", "conflict"]:
            report = report_fixture()
            report["findings"][0]["rule_status"] = status
            result, _ = self.run_fixture(report)
            self.assertTrue(result["summary"].startswith("【程序核查限制】"))
            self.assertIn("不能视为全部规则已确认", result["summary"])
            self.assertIn("固定期限合同是否允许", result["summary"])

    def test_professional_auxiliary_does_not_replace_or_invalidate_complete_official(self):
        report = report_fixture()
        auxiliary_url = "https://professional.example.test/comment"
        report["sources"].append({**report["sources"][0], "id": "S2", "url": auxiliary_url, "source_type": "professional", "effective_date": "unknown"})
        report["findings"][0]["evidence_ids"].append("S2")
        first = researched_response()
        first["output"][0]["action"]["sources"].append({"type": "url", "url": auxiliary_url})
        result, _ = self.run_fixture(report, first)
        self.assertEqual(result["findings"][0]["rule_status"], "supported")
        report["findings"][0]["evidence_ids"] = ["S2"]
        result, _ = self.run_fixture(report, first)
        self.assertEqual(result["findings"][0]["rule_status"], "unverified")

    def test_case_without_facts_cannot_meet_conditions(self):
        report = report_fixture()
        report["findings"][0]["application_status"] = "meets_conditions"
        result, _ = self.run_fixture(report, query={**QUERY, "query_mode": "case"})
        self.assertEqual(result["findings"][0]["application_status"], "insufficient_info")

    def test_case_not_applicable_requires_complete_evidence_and_facts(self):
        for details, rule_status in [("", "partial"), ("", "supported"), ("Known case facts", "partial")]:
            report = report_fixture()
            report["findings"][0]["rule_status"] = rule_status
            report["findings"][0]["application_status"] = "not_applicable"
            with self.subTest(details=details, rule_status=rule_status):
                result, _ = self.run_fixture(report, query={**QUERY, "query_mode": "case", "details": details})
                self.assertEqual(result["findings"][0]["application_status"], "insufficient_info")

    def test_http_transport_endpoint_timeout_and_error_redaction(self):
        class ForbiddenBody:
            def read(self, *args):
                raise AssertionError("Provider error bodies must not be read")
            def close(self):
                pass
        error = urllib.error.HTTPError("https://api.openai.com/v1/responses", 401, "private body", {}, ForbiddenBody())
        with patch("urllib.request.urlopen", side_effect=error) as request:
            with self.assertRaises(ResearchError) as caught:
                run_research(QUERY, "test-key")
        self.assertNotIn("private", str(caught.exception))
        sent = request.call_args.args[0]
        self.assertEqual(sent.full_url, "https://api.openai.com/v1/responses")
        self.assertEqual(sent.get_method(), "POST")
        self.assertEqual(request.call_args.kwargs["timeout"], 180)
        self.assertEqual(sent.get_header("Authorization"), "Bearer test-key")

    def test_second_phase_receives_only_locked_observed_context(self):
        responses = [researched_response(), structured_response()]
        calls = []
        def transport(payload, key):
            calls.append(payload)
            return responses.pop(0)
        run_research(QUERY, "test-key", prior_rules={"summary": "untrusted cache"}, transport=transport)
        context = json.loads(calls[1]["input"])
        self.assertEqual(set(context), {"query", "locked_research", "observed_sources"})
        self.assertNotIn("untrusted cache", calls[1]["input"])


if __name__ == "__main__":
    unittest.main()
