"""Loopback-only HTTP service. Credentials remain in process memory."""

import argparse
import json
import os
import re
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .storage import ReportStore


DEFAULT_MODEL = "gpt-5.5"
MAX_BODY_BYTES = 65536
STATIC_DIR = Path(__file__).parent / "static"


def read_env_file(path):
    """Read only supported plain key/value settings; never expand or execute text."""
    values = {}
    try:
        lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
    except FileNotFoundError:
        return values
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if key not in {"OPENAI_API_KEY", "OPENAI_MODEL", "EMPLOYMENT_AGENT_PROVIDER", "CODEX_MODEL"}:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def create_server(*, port=8765, data_dir="data", api_key="", model=DEFAULT_MODEL,
                  default_provider="codex", codex_model="", research_fn=None,
                  codex_fn=None, codex_status_fn=None, render_fn=None, demo_fn=None):
    if default_provider not in {"codex", "openai"}:
        raise ValueError("默认运行方式必须是 codex 或 openai。")
    store = ReportStore(data_dir)
    session_token = secrets.token_urlsafe(32)
    research_slots = threading.BoundedSemaphore(2)

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(30)

        def log_message(self, fmt, *args):
            # Request paths and errors may contain user material; don't log them.
            pass

        def _send(self, status, body, content_type="application/json; charset=utf-8", filename=None):
            # Windows may reset a connection closed with unread request bytes,
            # hiding a useful 4xx response. Drain modest rejected local requests.
            if status >= 400 and not getattr(self, "_body_read", False) and self.command == "POST":
                try:
                    unread = int(self.headers.get("Content-Length", "0"))
                    if 0 < unread <= 1024 * 1024:
                        self.connection.settimeout(2)
                        self.rfile.read(unread)
                except (ValueError, OSError):
                    pass
                self._body_read = True
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False)
            encoded = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; "
                             "style-src 'self'; img-src 'self' data:; connect-src 'self'; "
                             "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            try:
                self.wfile.write(encoded)
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                pass

        def _local_request(self):
            allowed_hosts = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            host = self.headers.get("Host", "").lower()
            origin = self.headers.get("Origin")
            if host not in allowed_hosts or (origin is not None and origin not in
                                            {"http://" + item for item in allowed_hosts}):
                self._send(403, {"error": "仅允许从本机应用页面访问。"})
                return False
            if self.headers.get("Sec-Fetch-Site") == "cross-site":
                self._send(403, {"error": "不接受来自其他网站的请求。"})
                return False
            return True

        def do_GET(self):
            if not self._local_request():
                return
            path = urlsplit(self.path).path
            if path == "/api/config":
                from .codex_backend import get_codex_status
                try:
                    codex_status = (codex_status_fn or get_codex_status)()
                except Exception:
                    codex_status = {"installed": False, "auth_status": "unknown", "auth_mode": "unknown",
                                    "version": "", "message": "暂时无法检查本机 Codex，请确认安装后刷新页面。"}
                return self._send(200, {"default_model": model, "api_key_configured": bool(api_key),
                                        "default_provider": default_provider, "codex_default_model": codex_model,
                                        "codex": codex_status,
                                        "session_token": session_token})
            if path == "/api/reports":
                return self._send(200, {"reports": store.list_reports()})
            match = re.fullmatch(r"/api/reports/([0-9a-f]{32})(?:/(markdown|json))?", path)
            if match:
                try:
                    item = store.get(match.group(1))
                except (OSError, ValueError):
                    return self._send(404, {"error": "报告不存在或已损坏。"})
                if match.group(2) == "markdown":
                    return self._send(200, item["markdown"], "text/markdown; charset=utf-8",
                                      f"employment-report-{item['id']}.md")
                if match.group(2) == "json":
                    return self._send(200, item["report"], filename=f"employment-report-{item['id']}.json")
                return self._send(200, item)
            asset_map = {"/": ("index.html", "text/html; charset=utf-8"),
                         "/index.html": ("index.html", "text/html; charset=utf-8"),
                         "/app.css": ("app.css", "text/css; charset=utf-8"),
                         "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                         "/static/app.css": ("app.css", "text/css; charset=utf-8"),
                         "/static/app.js": ("app.js", "text/javascript; charset=utf-8")}
            if path in asset_map:
                name, content_type = asset_map[path]
                try:
                    return self._send(200, (STATIC_DIR / name).read_bytes(), content_type)
                except OSError:
                    return self._send(404, {"error": "网页文件未安装完整，请重新下载项目。"})
            self._send(404, {"error": "未找到该资源。"})

        def do_POST(self):
            if not self._local_request():
                return
            if not secrets.compare_digest(self.headers.get("X-Session-Token", ""), session_token):
                return self._send(403, {"error": "会话已失效，请刷新页面后重试。"})
            path = urlsplit(self.path).path
            if path not in {"/api/research", "/api/demo"}:
                return self._send(404, {"error": "未找到该接口。"})
            if self.headers.get("Content-Type", "").split(";", 1)[0].strip() != "application/json":
                return self._send(415, {"error": "请求需要使用 JSON 格式。"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return self._send(400, {"error": "请求长度无效。"})
            if length < 0 or length > MAX_BODY_BYTES:
                self.close_connection = True
                return self._send(413, {"error": "输入过长，请缩短补充信息。"})
            try:
                raw_body = self.rfile.read(length)
                self._body_read = True
                body = json.loads(raw_body.decode("utf-8"))
                if not isinstance(body, dict):
                    raise ValueError()
            except (ValueError, UnicodeError, TimeoutError):
                return self._send(400, {"error": "请求内容不是有效的 JSON 对象。"})
            if not research_slots.acquire(blocking=False):
                return self._send(429, {"error": "已有研究任务运行中，请稍后重试。"})
            try:
                from .reports import render_markdown
                from .validation import normalize_query
                from .research import ResearchError, run_research
                from .demo import make_demo_report

                renderer = render_fn or render_markdown
                if path == "/api/demo":
                    # Always use a fictional jurisdiction regardless of the form's live country.
                    result = (demo_fn or make_demo_report)()
                else:
                    query = normalize_query(body)
                    provider = body.get("provider", default_provider)
                    if not isinstance(provider, str) or provider not in {"codex", "openai"}:
                        raise ValueError("运行方式必须是 codex 或 openai。")
                    selected_model = body.get("model", "")
                    if not isinstance(selected_model, str):
                        raise ValueError("模型名称格式无效。")
                    selected_model = selected_model.strip() or (codex_model if provider == "codex" else model)
                    if selected_model and not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,119}", selected_model):
                        raise ValueError("模型名称格式无效。")
                    prior_rules = store.get_prior_rules(query)
                    if provider == "codex":
                        from .codex_backend import run_codex_research
                        result = (codex_fn or run_codex_research)(query, model=selected_model or None,
                                                                prior_rules=prior_rules)
                    else:
                        request_key = body.get("api_key", "")
                        if not isinstance(request_key, str) or len(request_key) > 1024:
                            raise ValueError("API Key 格式无效。")
                        request_key = request_key.strip() or api_key
                        if not request_key:
                            return self._send(400, {"error": "API 模式需要 API Key；也可切换为本机 Codex 模式。"})
                        result = (research_fn or run_research)(query, api_key=request_key, model=selected_model,
                                                               prior_rules=prior_rules)
                    result["provider"] = provider
                item = store.save(result, renderer(result))
                return self._send(200, item)
            except ValueError as exc:
                return self._send(400, {"error": str(exc)})
            except ResearchError as exc:
                return self._send(502, {"error": str(exc)})
            except OSError:
                return self._send(500, {"error": "本地文件写入失败，请检查数据目录权限及可用空间。"})
            except Exception:
                return self._send(500, {"error": "处理失败，未保存不完整结果。请检查配置后重试。"})
            finally:
                research_slots.release()

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description="海外劳动合同与试用期核验 Agent（本地运行）")
    parser.add_argument("--port", type=int, default=8765, help="本地端口，默认 8765")
    parser.add_argument("--data-dir", default="data", help="本地报告目录，默认 ./data")
    args = parser.parse_args(argv)
    if not 0 < args.port < 65536:
        parser.error("端口必须在 1 到 65535 之间")
    settings = read_env_file(Path.cwd() / ".env")
    key = os.environ.get("OPENAI_API_KEY", settings.get("OPENAI_API_KEY", "")).strip()
    model = os.environ.get("OPENAI_MODEL", settings.get("OPENAI_MODEL", DEFAULT_MODEL)).strip() or DEFAULT_MODEL
    provider = os.environ.get("EMPLOYMENT_AGENT_PROVIDER", settings.get("EMPLOYMENT_AGENT_PROVIDER", "codex")).strip()
    codex_model = os.environ.get("CODEX_MODEL", settings.get("CODEX_MODEL", "")).strip()
    try:
        server = create_server(port=args.port, data_dir=args.data_dir, api_key=key, model=model,
                               default_provider=provider, codex_model=codex_model)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"启动失败：{exc}\n可通过 --port 8766 选择其他端口。\n")
    print(f"Open http://127.0.0.1:{server.server_port}")
    print("Press Ctrl+C to stop. API keys are never written to reports.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        from .codex_backend import cancel_active_runs
        cancel_active_runs()
        server.server_close()


if __name__ == "__main__":
    main()
