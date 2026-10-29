"""Strict provider schema and local validation of the same report contract."""

TOPICS = (
    "fixed_term_allowed", "fixed_term_duration", "renewal_conversion",
    "probation", "probation_termination",
)
TOPIC_LABELS = {
    "fixed_term_allowed": "固定期限合同是否允许",
    "fixed_term_duration": "固定期限合同期限",
    "renewal_conversion": "续签与无固定期限转化",
    "probation": "试用期设置与延长",
    "probation_termination": "试用期绩效不符与解除",
}
RULE_STATUSES = ("supported", "partial", "unverified", "conflict")
APPLICATION_STATUSES = (
    "general_rule", "conditional", "meets_conditions", "does_not_meet",
    "insufficient_info", "not_applicable",
)


def _object(properties):
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


def _string(enum=None):
    result = {"type": "string"}
    if enum is not None:
        result["enum"] = list(enum)
    return result


def _strings():
    return {"type": "array", "items": _string()}


REPORT_SCHEMA = _object({
    "jurisdiction": _string(), "jurisdiction_country": _string(),
    "jurisdiction_subdivision": _string(), "as_of_date": _string(), "scope": _string(),
    "summary": _string(), "assumptions": _strings(),
    "follow_up_questions": _strings(), "hr_actions": _strings(),
    "findings": {"type": "array", "minItems": 5, "maxItems": 5, "items": _object({
        "topic": _string(TOPICS), "rule_status": _string(RULE_STATUSES),
        "rule_summary": _string(), "application_status": _string(APPLICATION_STATUSES),
        "application_note": _string(), "conditions": _strings(),
        "exceptions": _strings(), "evidence_ids": _strings(),
    })},
    "sources": {"type": "array", "items": _object({
        "id": _string(), "title": _string(), "url": _string(), "publisher": _string(),
        "source_type": _string(("official", "professional", "vendor", "other")),
        "locator": _string(), "excerpt": _string(), "effective_date": _string(),
        "accessed_on": _string(),
    })},
})


def validate_report(report):
    """Reject malformed reports even if a transport bypassed strict output mode."""
    def visit(value, schema, path):
        kind = schema["type"]
        if kind == "object":
            if not isinstance(value, dict) or set(value) != set(schema["properties"]):
                raise ValueError(f"报告对象字段错误：{path}")
            for key, child in schema["properties"].items():
                visit(value[key], child, f"{path}.{key}")
        elif kind == "array":
            if not isinstance(value, list):
                raise ValueError(f"报告数组类型错误：{path}")
            if not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", 300):
                raise ValueError(f"报告数组长度错误：{path}")
            for index, item in enumerate(value):
                visit(item, schema["items"], f"{path}[{index}]")
        elif kind == "string":
            if not isinstance(value, str) or len(value) > 50000:
                raise ValueError(f"报告文本类型或长度错误：{path}")
            if "enum" in schema and value not in schema["enum"]:
                raise ValueError(f"报告状态不在允许范围内：{path}")
    visit(report, REPORT_SCHEMA, "report")
    if {finding["topic"] for finding in report["findings"]} != set(TOPICS):
        raise ValueError("报告必须完整覆盖五个不同主题。")
    identifiers = [source["id"] for source in report["sources"]]
    if any(not identifier.strip() for identifier in identifiers) or len(set(identifiers)) != len(identifiers):
        raise ValueError("来源标识必须非空且唯一。")
    for field in ("jurisdiction", "as_of_date", "scope", "summary"):
        if not report[field].strip():
            raise ValueError(f"报告字段不得为空：{field}")
    if any(not item["rule_summary"].strip() or not item["application_note"].strip() for item in report["findings"]):
        raise ValueError("各主题必须说明规则和适用边界。")
    return report
