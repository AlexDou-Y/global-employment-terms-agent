"""A deliberately fictional report that can demonstrate the UI without a key."""

from datetime import datetime, timezone

from .schema import TOPICS, TOPIC_LABELS
from .validation import normalize_query


def make_demo_report(query=None):
    query = normalize_query(query or {"country": "示例地区（虚构）", "nationality": "示例国籍"})
    findings = []
    for topic in TOPICS:
        findings.append({
            "topic": topic, "rule_status": "unverified",
            "rule_summary": f"{TOPIC_LABELS[topic]}：未知。本演示没有检索法律，不提供任何真实国家的法律规则、数字或期限。",
            "application_status": "general_rule" if query["query_mode"] == "rules" else "insufficient_info",
            "application_note": "仅演示报告结构；不能用于判断具体合同、试用期或解除是否合法。",
            "conditions": ["待核验实际工作国家/地区的官方法律及适用条件。"],
            "exceptions": ["待核验当地法定例外、行业和员工类别限制。"],
            "evidence_ids": [],
        })
    return {
        "jurisdiction": "示例地区（虚构）", "jurisdiction_country": query["country"],
        "jurisdiction_subdivision": query["subdivision"], "as_of_date": query["as_of_date"],
        "scope": "虚构演示，不是输入国家/地区的法律研究；不构成法律意见。",
        "summary": "这是离线演示报告。五个主题的法律规则均为未知，所有来源均为空；实时查询可复用本机 Codex 认证，或选择自行配置密钥的 API 模式。",
        "assumptions": ["示例地区和情境仅用于展示界面。", "员工国籍本身不能决定适用劳动法。"],
        "follow_up_questions": ["实际工作地、雇主实体及用工模式是什么？", "合同初签及历次续签日期、期限和间隔是什么？", "试用期约定、绩效标准告知和评价证据是否齐备？"],
        "hr_actions": ["先核验官方法律、生效日期和适用范围。", "将供应商政策与法律要求分开记录。", "具体签约或解除前，补充事实并取得当地法务确认。"],
        "findings": findings, "sources": [], "mode": "demo",
        "generated_at": datetime.now(timezone.utc).isoformat(), "model": "demo",
        "query": query, "verification_notes": ["演示模式未调用联网搜索，未核实任何真实法律规则。"],
        "web_search_count": 0,
    }
