import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from employment_agent.server import create_server, read_env_file


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.calls = []
        self.codex_calls = []
        self.codex_failure = None

        def research(query, api_key, model, prior_rules=None):
            self.calls.append((query, api_key, model))
            return {"jurisdiction": query["country"], "query": query, "mode": "live",
                    "generated_at": "2026-10-29T00:00:00Z", "as_of_date": query["as_of_date"],
                    "summary": "测试", "findings": [], "sources": [], "assumptions": [],
                    "follow_up_questions": [], "hr_actions": [], "verification_notes": []}

        def codex_research(query, model=None, prior_rules=None):
            self.codex_calls.append((query, model))
            if self.codex_failure:
                raise self.codex_failure
            result = research(query, "unused", model)
            self.calls.pop()
            return result

        self.server = create_server(port=0, data_dir=self.temp.name, api_key="configured-key",
                                    research_fn=research, codex_fn=codex_research,
                                    codex_status_fn=lambda: {"installed": True, "auth_status": "configured",
                                                            "auth_mode": "chatgpt", "version": "test", "message": "配置已就绪"},
                                    render_fn=lambda r: "# 测试报告")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        self.port = self.server.server_port
        _, config, _ = self.request("GET", "/api/config")
        self.token = config["session_token"]

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, method, path, data=None, headers=None, raw=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        payload = raw if raw is not None else (json.dumps(data) if data is not None else None)
        request_headers = {"Content-Type": "application/json"}
        request_headers.update(headers or {})
        conn.request(method, path, body=payload, headers=request_headers)
        response = conn.getresponse()
        body = response.read().decode("utf-8")
        content_type = response.getheader("Content-Type", "")
        status = response.status
        conn.close()
        return status, json.loads(body) if "application/json" in content_type else body, content_type

    def test_config_never_returns_api_key(self):
        status, data, _ = self.request("GET", "/api/config")
        self.assertEqual(status, 200)
        self.assertTrue(data["api_key_configured"])
        self.assertNotIn("configured-key", json.dumps(data))
        self.assertEqual(data["default_provider"], "codex")
        self.assertEqual(data["codex"]["auth_status"], "configured")

    def test_post_requires_session_token(self):
        status, _, _ = self.request("POST", "/api/research", {"country": "X", "nationality": "Y"})
        self.assertEqual(status, 403)
        self.assertEqual(self.calls, [])

    def test_external_origin_and_host_are_rejected(self):
        for headers in [{"Origin": "https://evil.example"}, {"Host": "evil.example"}]:
            status, _, _ = self.request("GET", "/api/config", headers=headers)
            self.assertEqual(status, 403)

    def test_request_key_used_but_never_saved(self):
        status, item, _ = self.request("POST", "/api/research", {
            "country": "X", "nationality": "Y", "provider": "openai", "api_key": "transient-key", "as_of_date": "2026-10-29"
        }, {"X-Session-Token": self.token})
        self.assertEqual(status, 200, item)
        self.assertEqual(self.calls[0][1], "transient-key")
        self.assertNotIn("api_key", self.calls[0][0])
        for path in Path(self.temp.name).rglob("*"):
            if path.is_file():
                self.assertNotIn("transient-key", path.read_text(encoding="utf-8"))
        status, downloaded, _ = self.request("GET", f'/api/reports/{item["id"]}/markdown')
        self.assertEqual(status, 200)
        self.assertEqual(downloaded, "# 测试报告")

    def test_default_codex_needs_no_webpage_key_and_preserves_local_model(self):
        status, item, _ = self.request("POST", "/api/research", {
            "country": "X", "nationality": "Y", "api_key": "must-not-reach-codex"
        }, {"X-Session-Token": self.token})
        self.assertEqual(status, 200, item)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.codex_calls[0][1], None)
        self.assertNotIn("api_key", self.codex_calls[0][0])
        self.assertEqual(item["report"]["provider"], "codex")
        self.assertNotIn("must-not-reach-codex", json.dumps(item))

    def test_codex_optional_model_and_unknown_provider(self):
        headers = {"X-Session-Token": self.token}
        status, _, _ = self.request("POST", "/api/research", {
            "country": "X", "nationality": "Y", "provider": "codex", "model": "gpt-test"
        }, headers)
        self.assertEqual(status, 200)
        self.assertEqual(self.codex_calls[0][1], "gpt-test")
        for provider in ("unknown", None, 5):
            self.assertEqual(self.request("POST", "/api/research", {
                "country": "X", "nationality": "Y", "provider": provider
            }, headers)[0], 400)

    def test_codex_failure_does_not_fall_back_to_api(self):
        from employment_agent.research import ResearchError
        self.codex_failure = ResearchError("本机 Codex 调用失败，请检查认证。")
        status, _, _ = self.request("POST", "/api/research", {
            "country": "X", "nationality": "Y", "provider": "codex"
        }, {"X-Session-Token": self.token})
        self.assertEqual(status, 502)
        self.assertEqual(self.calls, [])
        self.assertEqual(len(self.codex_calls), 1)

    def test_invalid_input_does_not_start_research(self):
        status, _, _ = self.request("POST", "/api/research", {"country": "X"},
                                    {"X-Session-Token": self.token})
        self.assertEqual(status, 400)
        self.assertEqual(self.calls, [])

    def test_invalid_json_and_oversize_body(self):
        headers = {"X-Session-Token": self.token}
        self.assertEqual(self.request("POST", "/api/research", headers=headers, raw="{")[0], 400)
        self.assertEqual(self.request("POST", "/api/research", headers=headers, raw="x" * 70000)[0], 413)

    def test_no_filesystem_path_access(self):
        self.assertEqual(self.request("GET", "/../../.env")[0], 404)
        self.assertEqual(self.request("GET", "/api/reports/../../.env")[0], 404)

    def test_env_file_is_data_not_executable(self):
        path = Path(self.temp.name) / ".env"
        path.write_text('OPENAI_API_KEY="local-key"\nOPENAI_MODEL=gpt-5.5\nEMPLOYMENT_AGENT_PROVIDER=codex\nCODEX_MODEL=\nUNRELATED=ignored\n', encoding="utf-8")
        self.assertEqual(read_env_file(path), {"OPENAI_API_KEY": "local-key", "OPENAI_MODEL": "gpt-5.5", "EMPLOYMENT_AGENT_PROVIDER": "codex", "CODEX_MODEL": ""})


if __name__ == "__main__":
    unittest.main()
