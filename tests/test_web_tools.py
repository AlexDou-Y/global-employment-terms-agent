import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

try:
    from employment_agent import web_tools as web
except ImportError:
    web = None


PUBLIC_IP = "8.8.8.8"


def public_resolver(host, port):
    return [PUBLIC_IP]


class Transport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, *, timeout, max_bytes, addresses):
        self.calls.append((url, timeout, max_bytes, addresses))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def page(body, content_type="text/html; charset=utf-8", status=200, **headers):
    return status, {"Content-Type": content_type, **headers}, body.encode("utf-8") if isinstance(body, str) else body


class WebToolTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(web, "Controlled web tools are not implemented")

    def read(self, url="https://law.example/rule", *, transport=None, resolver=public_resolver):
        return web.read_web_page(url, transport=transport, resolver=resolver)

    def search(self, query="fixed term law", *, transport=None, **kwargs):
        return web.search_web(query, transport=transport, resolver=public_resolver, **kwargs)

    def test_search_parses_real_xml_and_escapes_query(self):
        transport = Transport(page('<rss><channel><item><title>A &amp; B</title><link>https://law.example/rule?a=1&amp;b=2</link><description>Actual &lt;b&gt;text&lt;/b&gt;</description></item></channel></rss>', "application/rss+xml"))
        result = self.search('日本 law &amp; "test"', transport=transport)
        self.assertEqual(result["results"], [{"title": "A & B", "url": "https://law.example/rule?a=1&b=2", "snippet": "Actual text"}])
        self.assertNotIn("error", result)
        parsed = urlsplit(transport.calls[0][0])
        self.assertEqual(parsed.netloc, "www.bing.com")
        self.assertEqual(parse_qs(parsed.query)["q"], ['日本 law &amp; "test"'])
        self.assertEqual(parse_qs(parsed.query)["format"], ["rss"])
        self.assertEqual(transport.calls[0][1:3], (15, 1024 * 1024))
        self.assertEqual(transport.calls[0][3], (PUBLIC_IP,))

    def test_search_empty_results_are_not_invented(self):
        result = self.search(transport=Transport(page("<rss><channel/></rss>", "text/xml")))
        self.assertEqual(result["results"], [])
        self.assertNotIn("error", result)

    def test_search_limit_and_unsafe_result_urls(self):
        items = '<item><title>x</title><link>file:///secret</link></item>' + ''.join(f'<item><title>Result {i}</title><link>https://law.example/{i}</link></item>' for i in range(20))
        result = self.search(max_results=10, transport=Transport(page(f"<rss><channel>{items}</channel></rss>", "text/xml")))
        self.assertEqual(len(result["results"]), 10)
        self.assertTrue(all(item["url"].startswith("https://") for item in result["results"]))

    def test_search_rejects_invalid_inputs_before_network(self):
        transport = Transport()
        for query, max_results in [("", 5), ("x" * 401, 5), ("law", 11), ("law", True), (42, 5)]:
            with self.subTest(query=str(query)[:20], max_results=max_results):
                self.assertIn("error", self.search(query, max_results=max_results, transport=transport))
        self.assertEqual(transport.calls, [])

    def test_search_rejects_malformed_xml_and_entities(self):
        for body in ["not XML", '<!DOCTYPE rss [<!ENTITY x "value">]><rss><channel>&x;</channel></rss>']:
            with self.subTest(body=body):
                self.assertIn("error", self.search(transport=Transport(page(body, "text/xml"))))

    def test_html_extracts_title_body_without_active_or_navigation_content(self):
        transport = Transport(page('<html><head><title>法规 &amp; 条款</title><style>hide</style></head><body><nav>menu</nav><script>secret()</script><main><h1>合同</h1><p>第一条：真实规则。</p></main><footer>footer</footer></body></html>'))
        result = self.read(transport=transport)
        self.assertEqual(result["title"], "法规 & 条款")
        self.assertIn("第一条：真实规则。", result["text"])
        for hidden in ["hide", "menu", "secret", "footer"]:
            self.assertNotIn(hidden, result["text"])
        self.assertFalse(result["truncated"])
        self.assertNotIn("error", result)

    def test_table_cells_preserve_separate_legal_numbers(self):
        result = self.read(transport=Transport(page('<table><tr><th>期限</th><th>次数</th></tr><tr><td>2</td><td>3</td></tr></table>')))
        self.assertEqual(result["text"], "期限 次数 2 3")
        self.assertNotIn("23", result["text"])
        self.assertFalse(result["truncated"])

    def test_paragraphs_and_list_items_are_separated_without_splitting_inline_text(self):
        result = self.read(transport=Transport(page('<p>第<strong>2</strong>条</p><p>期限为<span>3</span>个月。</p><ul><li>2</li><li>3</li></ul>')))
        self.assertEqual(result["text"], "第2条 期限为3个月。 2 3")

    def test_block_boundaries_separate_numbers_without_optional_closing_tags(self):
        result = self.read(transport=Transport(page('<table><tr><td>2<td>3</table><p>4<p>5<ul><li>6<li>7</ul>')))
        self.assertEqual(result["text"], "2 3 4 5 6 7")

    def test_plain_text_and_header_charset_are_supported(self):
        result = self.read(transport=Transport(page("劳动法规".encode("gb18030"), "text/plain; charset=gb18030")))
        self.assertEqual(result["text"], "劳动法规")

    def test_html_meta_charset_is_supported(self):
        result = self.read(transport=Transport(page('<meta charset="gb18030"><p>劳动法规</p>'.encode("gb18030"), "text/html")))
        self.assertEqual(result["text"], "劳动法规")

    def test_visible_links_are_resolved_in_document_order_and_never_fetched(self):
        body = '<a href="/law">劳动法规</a><a href="../rules"> Rules </a><a href="/law">duplicate</a><a href="javascript:alert(1)">bad</a><a href="https://user:secret@law.example">credentials</a><a href="http://127.0.0.1">private</a><script><a href="/script">hidden</a></script><a href="/empty"></a><p>Actual law text</p>'
        transport = Transport(page(body))
        result = self.read(transport=transport)
        self.assertEqual(result["links"], [{"title": "劳动法规", "url": "https://law.example/law"}, {"title": "Rules", "url": "https://law.example/rules"}])
        self.assertEqual(len(transport.calls), 1)

    def test_navigation_links_are_available_even_when_navigation_text_is_omitted(self):
        result = self.read(transport=Transport(page('<nav><a href="/legislation">Legislation</a></nav><main>Official home</main><footer><a href="/contact">Contact</a></footer>')))
        self.assertEqual(result["text"], "Official home")
        self.assertEqual(result["links"], [{"title": "Legislation", "url": "https://law.example/legislation"}, {"title": "Contact", "url": "https://law.example/contact"}])

    def test_visible_link_limit_is_100_and_plain_text_has_no_links(self):
        result = self.read(transport=Transport(page(''.join(f'<a href="/{i}">Link {i}</a>' for i in range(120)))))
        self.assertEqual(len(result["links"]), 100)
        self.assertEqual(result["links"][-1]["url"], "https://law.example/99")
        self.assertEqual(self.read(transport=Transport(page("Text", "text/plain")))["links"], [])

    def test_default_https_handler_uses_supported_runtime_connection_options(self):
        handler = web._PublicHTTPSHandler((PUBLIC_IP,))
        request = object()
        with patch.object(handler, "do_open", return_value="response") as opener:
            self.assertEqual(handler.https_open(request), "response")
        self.assertEqual(opener.call_args.kwargs["addresses"], (PUBLIC_IP,))

    def test_connection_uses_validated_ip_and_retains_hostname_for_tls(self):
        context = Mock()
        sock = Mock()
        with patch("employment_agent.web_tools.socket.create_connection", return_value=sock) as connect:
            connection = web._PublicHTTPSConnection("law.example", addresses=(PUBLIC_IP,), timeout=15, context=context)
            connection.connect()
        self.assertEqual(connect.call_args.args[0], (PUBLIC_IP, 443))
        self.assertEqual(context.wrap_socket.call_args.kwargs["server_hostname"], "law.example")

    def test_character_limit_is_reported_as_truncated(self):
        result = self.read(transport=Transport(page("x" * 28001, "text/plain")))
        self.assertEqual(len(result["text"]), 28000)
        self.assertTrue(result["truncated"])

    def test_pdf_empty_text_and_http_errors_fail_without_fabricating_body(self):
        for response in [page(b"%PDF", "application/pdf"), page("<script>only script</script>"), page("Not found", status=404)]:
            with self.subTest(response=response):
                result = self.read(transport=Transport(response))
                self.assertIn("error", result)
                self.assertEqual(result["text"], "")

    def test_response_byte_limits_are_enforced_with_injected_transport(self):
        self.assertIn("error", self.read(transport=Transport(page(b"x" * (2 * 1024 * 1024 + 1), "text/plain"))))
        self.assertIn("error", self.search(transport=Transport(page(b"x" * (1024 * 1024 + 1), "text/xml"))))

    def test_sensitive_transport_errors_are_not_disclosed(self):
        result = self.read(transport=Transport(OSError("C:/private/auth.json sk-secret")))
        self.assertIn("error", result)
        self.assertNotIn("private", json.dumps(result))
        self.assertNotIn("sk-secret", json.dumps(result))

    def test_invalid_schemes_credentials_and_local_hosts_are_rejected(self):
        transport = Transport()
        for url in ["file:///etc/passwd", "ftp://law.example", "https://user:secret@law.example", "http://localhost", "http://a.localhost", "http://127.0.0.1", "http://169.254.169.254/latest", "http://[::1]", "http://[fe80::1%25eth0]", "https://law.example/\nheader", "https://law.example:0/"]:
            with self.subTest(url=url):
                self.assertIn("error", self.read(url, transport=transport))
        self.assertEqual(transport.calls, [])

    def test_unicode_path_is_encoded_before_transport(self):
        transport = Transport(page("Law", "text/plain"))
        result = self.read("https://law.example/法规?q=劳动#section", transport=transport)
        self.assertNotIn("error", result)
        self.assertEqual(transport.calls[0][0], "https://law.example/%E6%B3%95%E8%A7%84?q=%E5%8A%B3%E5%8A%A8")

    def test_stdio_nonstandard_numbers_and_surrogate_ids_do_not_crash(self):
        instream = io.StringIO('{"jsonrpc":"2.0","id":NaN,"method":"ping"}\n' + '{"jsonrpc":"2.0","id":"\\ud800","method":"ping"}\n')
        outstream = io.StringIO()
        web.serve(instream, outstream)
        lines = outstream.getvalue().splitlines()
        self.assertEqual(len(lines), 2)
        for line in lines:
            line.encode("utf-8", errors="strict")
            self.assertIn("error", json.loads(line))

    def test_all_dns_addresses_must_be_public(self):
        transport = Transport()
        for addresses in [["10.0.0.1"], [PUBLIC_IP, "192.168.1.1"], ["::1"], [], ["not-an-ip"]]:
            with self.subTest(addresses=addresses):
                result = self.read(transport=transport, resolver=lambda h, p: addresses)
                self.assertIn("error", result)
        self.assertEqual(transport.calls, [])

    def test_redirect_is_validated_before_second_request(self):
        transport = Transport((302, {"Location": "http://internal.example/secret"}, b""))
        result = self.read(transport=transport, resolver=lambda host, port: ["10.0.0.2"] if host == "internal.example" else [PUBLIC_IP])
        self.assertIn("error", result)
        self.assertEqual(len(transport.calls), 1)

    def test_redirect_to_file_and_metadata_is_rejected(self):
        for destination in ["file:///secret", "http://169.254.169.254/", "http://user:pass@law.example/"]:
            transport = Transport((301, {"Location": destination}, b""))
            self.assertIn("error", self.read(transport=transport))
            self.assertEqual(len(transport.calls), 1)

    def test_public_redirect_returns_final_url_and_original_url(self):
        transport = Transport((302, {"Location": "/actual"}, b""), page("Actual text", "text/plain"))
        result = self.read(transport=transport)
        self.assertEqual(result["url"], "https://law.example/actual")
        self.assertEqual(result["requested_url"], "https://law.example/rule")
        self.assertEqual(result["text"], "Actual text")

    def test_redirect_limit_is_enforced(self):
        transport = Transport(*[(302, {"Location": f"/redirect-{i}"}, b"") for i in range(7)])
        self.assertIn("error", self.read(transport=transport))
        self.assertEqual(len(transport.calls), 7)

    def test_protocol_initialization_and_readonly_tools(self):
        for version in ["2024-11-05", "2025-03-26", "2025-06-18"]:
            response = web.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": version}})
            self.assertEqual(response["result"]["protocolVersion"], version)
            self.assertEqual(response["result"]["serverInfo"]["name"], "employment_web")
        tools = web.handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
        self.assertEqual({tool["name"] for tool in tools}, {"search_web", "read_web_page"})
        for tool in tools:
            self.assertTrue(tool["annotations"]["readOnlyHint"])
            self.assertTrue(tool["annotations"]["openWorldHint"])

    def test_protocol_call_has_matching_text_and_structured_result(self):
        request = {"jsonrpc": "2.0", "id": "x", "method": "tools/call", "params": {"name": "read_web_page", "arguments": {"url": "https://law.example"}}}
        result = web.handle_request(request, transport=Transport(page("True text", "text/plain")), resolver=public_resolver)["result"]
        self.assertEqual(json.loads(result["content"][0]["text"]), result["structuredContent"])
        self.assertFalse(result.get("isError", False))

    def test_protocol_failure_is_error_and_never_leaks_raw_exception(self):
        request = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "read_web_page", "arguments": {"url": "http://localhost"}}}
        result = web.handle_request(request, transport=Transport(), resolver=public_resolver)["result"]
        self.assertTrue(result["isError"])
        self.assertIn("error", result["structuredContent"])

    def test_protocol_method_errors_ping_and_notifications(self):
        self.assertIsNone(web.handle_request({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        self.assertEqual(web.handle_request({"jsonrpc": "2.0", "id": 1, "method": "ping"})["result"], {})
        self.assertEqual(web.handle_request({"jsonrpc": "2.0", "id": 1, "method": "unknown"})["error"]["code"], -32601)
        self.assertEqual(web.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "unknown"}})["error"]["code"], -32602)
        self.assertEqual(web.handle_request([])["error"]["code"], -32600)

    def test_stdio_outputs_only_json_protocol_and_can_run_standalone(self):
        input_text = '\n'.join([json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}), 'not-json', json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})]) + '\n'
        result = subprocess.run([sys.executable, str(Path(web.__file__).resolve())], input=input_text, text=True, encoding="utf-8", capture_output=True, timeout=10, cwd=Path(web.__file__).resolve().parent.parent.parent)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        lines = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["result"], {})
        self.assertEqual(lines[1]["error"]["code"], -32700)


if __name__ == "__main__":
    unittest.main()
