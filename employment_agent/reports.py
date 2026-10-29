"""Markdown exports with explicit research and evidence boundaries."""

import html
import urllib.parse

from .schema import TOPIC_LABELS


RULE_LABELS = {"supported": "充分支持（AI 判读）", "partial": "部分支持", "unverified": "未核实", "conflict": "来源冲突"}
APPLICATION_LABELS = {"general_rule": "一般规则", "conditional": "有条件适用", "meets_conditions": "满足条件（AI 初判）", "does_not_meet": "不满足条件（AI 初判）", "insufficient_info": "信息不足", "not_applicable": "不适用"}
SOURCE_LABELS = {"official": "官方（AI 分类）", "professional": "专业解读", "vendor": "供应商政策/资料", "other": "其他"}


def _text(value):
    value = html.escape(str(value), quote=False)
    for char in ("\\", "`", "*", "_", "[", "]", "#", "|", "!"):
        value = value.replace(char, "\\" + char)
    return value.replace("\r", "").replace("\n", " ")


def _link(title, url):
    try:
        parsed = urllib.parse.urlsplit(url)
        safe = parsed.scheme in ("https", "http") and bool(parsed.hostname) and not parsed.username and not parsed.password and not any(ord(char) < 33 for char in url)
    except (TypeError, ValueError):
        safe = False
    if not safe:
        return _text(title) + "（无有效来源链接）"
    encoded = urllib.parse.quote(url, safe=":/?&=%#@+;,~.-_")
    return f"[{_text(title)}](<{encoded}>)"


def render_markdown(report):
    lines = ["# 海外劳动合同与试用期研究报告", ""]
    if report.get("mode") == "demo":
        lines.extend(["> **演示模式：虚构地区，未检索法律，不适用于任何真实国家或员工。**", ""])
    lines.extend(["> 本报告为 AI 研究辅助，不是最终法律意见或法务签批。", "",
                  f"- 地区：{_text(report['jurisdiction'])}",
                  f"- 查询国家/地区：{_text(report.get('jurisdiction_country', report.get('query', {}).get('country', '未提供')))}",
                  f"- 查询州/省：{_text(report.get('jurisdiction_subdivision') or '未提供')}",
                  f"- 规则基准日：{_text(report['as_of_date'])}",
                  f"- 生成时间：{_text(report.get('generated_at', ''))}",
                  f"- 运行方式：{_text({'codex': '本机 Codex', 'openai': 'OpenAI API'}.get(report.get('provider'), '演示' if report.get('mode') == 'demo' else '未记录'))}",
                  f"- 模型：{_text(report.get('model', ''))}",
                  f"- 已完成联网搜索：{_text(report.get('web_search_count', 0))} 次", "",
                  "## 范围与结论", "", _text(report["scope"]), "", _text(report["summary"]), ""])
    query = report.get("query", {})
    if query:
        lines.extend(["## 查询条件", ""])
        for key, label in (("country", "实际工作国家/地区"), ("subdivision", "州/省"), ("nationality", "国籍"), ("employment_model", "用工模式"), ("query_mode", "查询模式"), ("details", "补充事实")):
            lines.append(f"- {label}：{_text(query.get(key) or '未提供')}")
        lines.append("")
    for index, finding in enumerate(report["findings"], 1):
        lines.extend([f"## {index}. {TOPIC_LABELS[finding['topic']]}", "",
                      f"- 证据状态：{RULE_LABELS[finding['rule_status']]}",
                      f"- 场景适用：{APPLICATION_LABELS[finding['application_status']]}", "",
                      _text(finding["rule_summary"]), "", _text(finding["application_note"]), ""])
        for key, label in (("conditions", "适用条件"), ("exceptions", "例外与限制")):
            lines.append(f"**{label}**")
            lines.append("")
            lines.extend(f"- {_text(item)}" for item in finding[key])
            if not finding[key]:
                lines.append("- 未列明；不代表不存在。")
            lines.append("")
        lines.extend(["证据来源：" + ("、".join(_text(item) for item in finding["evidence_ids"]) or "暂无可追溯证据"), ""])
    for key, title in (("assumptions", "假设与边界"), ("follow_up_questions", "待补充问题"), ("hr_actions", "HR 后续动作"), ("verification_notes", "程序核查记录与限制")):
        lines.extend([f"## {title}", ""])
        lines.extend(f"- {_text(item)}" for item in report.get(key, []))
        if not report.get(key):
            lines.append("- 暂无列明事项。")
        lines.append("")
    lines.extend(["## 来源与证据状态", ""])
    if not report["sources"]:
        lines.extend(["暂无来源，相关法律规则未核实。", ""])
    for source in report["sources"]:
        lines.extend([f"### {_text(source['id'])} · {_link(source['title'], source['url'])}", "",
                      f"- 发布机构：{_text(source['publisher'])}",
                      f"- 类型：{SOURCE_LABELS.get(source['source_type'], '其他')}",
                      f"- 检索可追溯：{'是' if source.get('observed_in_search') else '否'}",
                      f"- 原文访问：{'工具轨迹明确打开原文；不等于人工法律核验' if source.get('opened_by_tool') else '未确认打开原文'}",
                      f"- 条文/段落定位：{_text(source['locator'] or '未知')}",
                      f"- 原文摘录：{_text(source['excerpt'] or '未知')}",
                      f"- 规则生效日期：{_text(source['effective_date'] or '未知')}",
                      f"- 访问日期：{_text(source['accessed_on'] or '未知')}", ""])
    return "\n".join(lines).rstrip() + "\n"
