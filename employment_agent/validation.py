"""Normalize the public scenario contract without retaining runtime secrets."""

import re
from datetime import date


EMPLOYMENT_MODELS = ("unspecified", "direct", "eor", "expatriate", "other")
QUERY_MODES = ("rules", "case")


def normalize_query(data):
    if not isinstance(data, dict):
        raise ValueError("查询内容必须是 JSON 对象。")
    defaults = {
        "country": "", "nationality": "", "subdivision": "",
        "employment_model": "unspecified", "query_mode": "rules",
        "as_of_date": date.today().isoformat(), "details": "",
    }
    query = {}
    for field, default in defaults.items():
        value = data.get(field, default)
        if not isinstance(value, str):
            raise ValueError(f"{field} 必须是字符串。")
        value = value.strip()
        limit = 12000 if field == "details" else 120
        if len(value) > limit:
            raise ValueError(f"{field} 不得超过 {limit} 个字符。")
        if "\x00" in value:
            raise ValueError(f"{field} 包含无效字符。")
        query[field] = value
    if not query["country"] or not query["nationality"]:
        raise ValueError("请填写实际工作国家/地区和员工国籍。")
    if query["employment_model"] not in EMPLOYMENT_MODELS:
        raise ValueError("用工模式不在允许范围内。")
    if query["query_mode"] not in QUERY_MODES:
        raise ValueError("查询模式不在允许范围内。")
    if not query["as_of_date"]:
        query["as_of_date"] = defaults["as_of_date"]
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", query["as_of_date"]):
            raise ValueError
        date.fromisoformat(query["as_of_date"])
    except ValueError:
        raise ValueError("查询基准日期必须是有效的 YYYY-MM-DD 日期。") from None
    return query
