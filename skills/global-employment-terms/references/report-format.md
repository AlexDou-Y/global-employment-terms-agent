# 输出格式与证据状态

## 研究范围

说明实际工作国家/地区、省州、国籍、雇主/用工模式、通用规则或个案模式、核验基准日和实际检索日。未知字段写“未提供”；时间不明的法规效力写“待核验”。不要把今天访问页面的日期写成法规生效日期。

## 摘要与五项核验表

先用简短摘要回答核心问题并指出关键限制，再逐项展示：

| 主题 | 规则结论 | 规则证据状态 | 适用条件与例外 | 个案适用状态及说明 | 来源编号 |
| --- | --- | --- | --- | --- | --- |
| 固定期限合同是否允许 | 按已读取依据填写 | 见下方定义 | 包含人员和使用条件 | 规则研究填“通用规则” | 关联具体来源 |
| 固定期限合同期限 | 明确单次/累计及单位 | 同上 | 计算口径和例外 | 不得补造合同事实 | 同上 |
| 续签与无固定期限转化 | 区分不同触发机制 | 同上 | 次数/间隔/期限等 | 条件不足写“信息不足” | 同上 |
| 试用期 | 区分初签、续签、延长、暂停 | 同上 | 上限、约定及人员条件 | 说明缺少何种事实 | 同上 |
| 试用期绩效不符解除 | 不将内部不通过等同合法解除 | 同上 | 事由、证据、程序、给付、保护 | 明确需核实的动作条件 | 同上 |

“有依据”表示在本次研究范围内有足够可定位的适用官方原文支持，**不表示法律签批**。若只读到专业材料、官方页面未打开、条文不完整或日期不明，使用“部分支持”或“待核验”；实质冲突尚未解决使用“存在冲突”。

通用规则报告不写“该员工满足条件”。个案“有条件适用”须写出条件；“满足条件”须指出已提供的相应事实；“不满足条件”须指出冲突事实；“信息不足”须说明缺失事实；“不适用”须给出依据和排除理由。

## 来源清单

对实际使用的每个来源记录：

- 编号、标题、发布者、完整 URL、类别（官方/专业/供应商/其他）。类别是研究判断，不是认证结论。
- 条号/章节/段落及支持结论的必要短摘录；原文和译文有重要差异时保留原文术语。
- 版本/生效日期、检索或访问日期；未知照实标注。
- 是否在搜索中发现、是否由工具打开、是否读到相关原文；访问受限、摘要或缺页情况。
- 支持哪些主题，以及仍无法支撑的部分。

不要编造链接、摘录、发布者、条号或访问经历。来源多不代表证据充分；同源转载不算独立交叉验证。

## 假设、待确认与下一步

分开列出事实缺失、证据缺口和解释争议，并说明对结论的影响。仅追问会改变判断的问题。HR 下一步明确材料、负责人类型和需要确认的事项；分别标记“可准备”“待核实”“待法务/顾问确认”，不将建议写成已批准的执行方案。

## 需要 JSON 时

可采用以下字段映射，内容必须与人类可读报告一致：

```text
jurisdiction, as_of_date, scope, summary: string
assumptions, follow_up_questions, hr_actions: string[]
findings: exactly five entries {
  topic: fixed_term_allowed | fixed_term_duration | renewal_conversion | probation | probation_termination,
  rule_status: supported | partial | unverified | conflict,
  rule_summary: string,
  application_status: general_rule | conditional | meets_conditions | does_not_meet | insufficient_info | not_applicable,
  application_note: string,
  conditions, exceptions, evidence_ids: string[]
}
sources: [{id, title, url, publisher, source_type, locator, excerpt, effective_date, accessed_on}]
source_type: official | professional | vendor | other
```

映射：有依据=supported；部分支持=partial；待核验=unverified；存在冲突=conflict。通用规则=general_rule；有条件适用=conditional；满足条件=meets_conditions；不满足条件=does_not_meet；信息不足=insufficient_info；不适用=not_applicable。

工具轨迹字段必须来自实际调用记录而非让模型自证。没有可用轨迹时，在报告说明“无法核实工具轨迹”；不得伪造 `opened_by_tool` 等状态。使用此技能的不同助手不必具备本项目网页程序的相同接口。
