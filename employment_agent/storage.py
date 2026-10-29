"""Local report history and narrowly scoped general-rule research hints."""

import copy
import hashlib
import json
import re
import threading
import uuid
from pathlib import Path


_SECRET_FIELDS = {"api_key", "openai_api_key", "authorization", "session_token", "token"}
_RULE_KEY_FIELDS = ("country", "nationality", "subdivision", "employment_model")


def _without_credentials(value):
    if isinstance(value, dict):
        return {key: _without_credentials(item) for key, item in value.items()
                if key.lower() not in _SECRET_FIELDS}
    if isinstance(value, list):
        return [_without_credentials(item) for item in value]
    return value


class ReportStore:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.reports = self.directory / "reports"
        self.rules = self.directory / "rules"
        self.reports.mkdir(parents=True, exist_ok=True)
        self.rules.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    @staticmethod
    def _rule_key(query):
        values = {key: str(query.get(key, "")).strip().casefold() for key in _RULE_KEY_FIELDS}
        encoded = json.dumps(values, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _eligible(query):
        return query.get("query_mode") == "rules" and not query.get("details", "").strip()

    @staticmethod
    def _write(path, text):
        temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            temporary.write_text(text, encoding="utf-8")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def save(self, report, markdown):
        clean = _without_credentials(copy.deepcopy(report))
        report_id = uuid.uuid4().hex
        with self._lock:
            self._write(self.reports / f"{report_id}.md", markdown)
            self._write(self.reports / f"{report_id}.json", json.dumps(clean, ensure_ascii=False, indent=2))
            query = clean.get("query", {})
            if clean.get("mode") == "live" and self._eligible(query):
                card = {key: clean[key] for key in (
                    "jurisdiction", "as_of_date", "scope", "findings", "sources", "generated_at",
                    "verification_notes") if key in clean}
                card["reuse_notice"] = "历史研究线索；当前查询须重新核验适用规则、原文和生效日期。"
                self._write(self.rules / f"{self._rule_key(query)}.json",
                            json.dumps(card, ensure_ascii=False, indent=2))
        return {"id": report_id, "report": clean, "markdown": markdown}

    def get(self, report_id):
        if not re.fullmatch(r"[0-9a-f]{32}", report_id):
            raise ValueError("无效的报告编号。")
        with self._lock:
            report = json.loads((self.reports / f"{report_id}.json").read_text(encoding="utf-8"))
            markdown = (self.reports / f"{report_id}.md").read_text(encoding="utf-8")
        return {"id": report_id, "report": report, "markdown": markdown}

    def list_reports(self):
        items = []
        with self._lock:
            for path in self.reports.glob("*.json"):
                if not re.fullmatch(r"[0-9a-f]{32}", path.stem):
                    continue
                try:
                    report = json.loads(path.read_text(encoding="utf-8"))
                    if not isinstance(report, dict):
                        continue
                    items.append({"id": path.stem, **{key: report.get(key, "") for key in
                        ("jurisdiction", "generated_at", "mode", "provider", "summary")}})
                except (OSError, ValueError):
                    continue
        return sorted(items, key=lambda item: item["generated_at"], reverse=True)[:100]

    def get_prior_rules(self, query):
        if not self._eligible(query):
            return None
        path = self.rules / f"{self._rule_key(query)}.json"
        try:
            with self._lock:
                card = json.loads(path.read_text(encoding="utf-8"))
            return card if isinstance(card, dict) else None
        except (OSError, ValueError):
            return None
