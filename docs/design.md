# 海外劳动合同与试用期核验 Agent

本项目提供可公开复用的本地网页工具和独立 Agent 指令。用户输入实际工作国家/地区、员工国籍，查询固定期限合同、期限、续签转化、试用期和绩效不符解除五类规则。进一步个案判断按需补充雇主、工作地、合同历史、日期与绩效事实。

## 第一版架构

- Python 3.10+ 标准库实现本地服务，默认只监听 127.0.0.1；无前端构建或第三方 Python 运行依赖。
- 静态 HTML/CSS/JavaScript 提供中文表单、模拟演示、实时查询、条件追问、来源查看、历史报告与 Markdown/JSON 下载。
- OpenAI Responses API 执行真实联网研究，然后将研究记录整理为严格 JSON；模型名称可配置。每次实时查询都会联网，缓存仅作为研究线索。
- 程序核查真实搜索调用、来源链、完整的五个主题、输入与日期一致性；模型整理不等于独立法律复核。
- 结果与规则卡保存在使用者本地 data/，不进入 Git；API Key 来自环境变量或当前请求，不持久化、不回传。
- 可复制的 prompts/agent-instructions.md 与 skills/global-employment-terms/SKILL.md 支持具备联网能力的其他 AI 助手；没有联网能力时必须说明能力缺口。

## 业务边界

明确区分通用规则与个案判断、法律与供应商政策、单次与累计期限、初签与续签、自动转化与员工请求、试用期延期与暂停、内部考核结论与合法解除依据。记录证据状态和场景适用状态；未知不能推定允许。每项结论关联真实研究来源；无官方依据不能标记充分支持。来源类别与解释由 AI 提取，不宣称程序已完成法律签批。

个案信息留在本地报告；只允许通用规则报告进入可复用规则卡。无实时 API Key 时提供明确标注的虚构地区演示，不把示例当作任何国家法律。

## 稳定接口

输入字段：country、nationality（必填），subdivision、employment_model（unspecified/direct/eor/expatriate/other）、query_mode（rules/case）、as_of_date（YYYY-MM-DD）、details（可选补充）。API Key 和 model 属于运行设置，不进入上述场景记录。

结构化报告字段：

```text
jurisdiction, jurisdiction_country, jurisdiction_subdivision, as_of_date, scope, summary: string
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

jurisdiction_country、jurisdiction_subdivision 必须分别精确等于输入 country、subdivision，否则拒绝报告，不能把错误辖区的答案写入规则卡。jurisdiction 是便于阅读的展示名称。

研究模块增加非模型生成的运行信息：mode（live/demo）、generated_at、model、query、verification_notes、web_search_count；每个来源附 observed_in_search 与 opened_by_tool（仅表示工具轨迹明确出现 open_page）。程序不能把“在搜索来源列表中出现”解释成“已读取原文”。无法确认原文读取的来源要降级对应结论并说明。界面展示只读的原始查询条件，避免将历史结果误用于当前表单里的新场景。

HTTP 接口：GET /api/config（默认模型、密钥是否就绪、session_token），POST /api/research（输入及可选 api_key/model），POST /api/demo（演示），GET /api/reports（历史列表），GET /api/reports/{id}（完整报告），GET /api/reports/{id}/markdown（下载），GET /api/reports/{id}/json（下载）。POST 需 X-Session-Token；外部 Origin/Host 拒绝。成功研究返回 {id, report, markdown}，错误返回 {error}。第一版请求同步执行，前端明确提示研究可能需要数分钟；不虚构进度百分比。

## 验收

使用固定模拟 API 响应检验：伪造来源、没有实际搜索、缺失主题、非官方或未打开来源、一般规则被写成个案结论、过期日期、拒答/截断、上游超时。离线演示、HTTP 请求校验、凭据不落盘、历史下载和规则复用应独立测试。真实联网调用和法务解释质量必须单独披露验证范围。

发布：独立 Git 仓库、MIT 许可、中文 README、跨平台启动说明、公开模拟样例、贡献说明、自动测试工作流模板（启用需要相应 GitHub 权限）。用户已选择公开 GitHub 项目和“本地网页＋可复制指令”的交付形式。
