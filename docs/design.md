# 海外劳动合同与试用期核验 Agent

本项目提供可公开复用的本地网页工具和独立 Agent 指令。用户输入实际工作国家/地区、员工国籍，查询固定期限合同、期限、续签转化、试用期和绩效不符解除五类规则。进一步个案判断按需补充雇主、工作地、合同历史、日期与绩效事实。

## v0.2 架构

- Python 3.10+ 标准库实现本地服务，默认只监听 127.0.0.1；无前端构建或第三方 Python 运行依赖。
- 静态 HTML/CSS/JavaScript 提供中文表单、模拟演示、实时查询、条件追问、来源查看、历史报告与 Markdown/JSON 下载。
- 默认通过本机 Codex CLI 非交互模式执行联网研究，复用 CLI 已有认证，无需在网页填 API Key。可选直连 OpenAI Responses API 模式继续保留。两种模式均输出同一严格 JSON 结构；每次实时查询都会联网，缓存仅作为研究线索。
- 程序核查真实搜索调用、来源链、完整的五个主题、输入与日期一致性；模型整理不等于独立法律复核。
- 结果与规则卡保存在使用者本地 data/，不进入 Git；运行方式随报告记录。直连 API Key 来自本地配置、环境变量或当前请求，不写入报告、不回传。
- 可复制的 prompts/agent-instructions.md 与 skills/global-employment-terms/SKILL.md 支持具备联网能力的其他 AI 助手；没有联网能力时必须说明能力缺口。

## 业务边界

明确区分通用规则与个案判断、法律与供应商政策、单次与累计期限、初签与续签、自动转化与员工请求、试用期延期与暂停、内部考核结论与合法解除依据。记录证据状态和场景适用状态；未知不能推定允许。每项结论关联真实研究来源；无官方依据不能标记充分支持。来源类别与解释由 AI 提取，不宣称程序已完成法律签批。

个案信息随查询发送至所选模式的模型服务，并保存在本地报告；仅 query_mode=rules 且 details 为空的通用规则查询自动进入可复用规则卡。两种实时模式均不可用时，仍可运行无需 CLI、密钥或网络的虚构地区演示，不把示例当作任何国家法律。

## 运行方式与凭据

- `EMPLOYMENT_AGENT_PROVIDER` 默认 `codex`，另一个合法值为 `openai`。未知值拒绝；任何失败都不自动切换运行方式。
- `CODEX_MODEL` 默认空，空值不向 CLI 传模型参数，沿用用户的 Codex 配置；网页可为单次查询指定模型。`OPENAI_MODEL` 默认 `gpt-5.5`，只用于直连 API。
- 本机模式从 `PATH` 查找 Codex CLI，通过 CLI 获取安装和认证状态。程序不读取、复制或回传 `auth.json`，不启动登录、不修改用户全局配置。首次使用由本人按官方说明安装并执行 `codex login`。
- 安装与认证状态是就绪提示，只能证明 CLI 或认证配置可被发现；实际模型权限、搜索能力、网络、余额和额度以真实调用为准。用量与费用遵循用户现有 Codex 认证及服务设置。
- 直连 API 模式要求 `OPENAI_API_KEY` 或请求内 `api_key`。本机 Codex 模式不使用该运行设置；认证由 CLI 自行处理。

## 本机 Codex 执行与证据边界

服务使用参数列表与 stdin 启动 `codex exec`，不将国家、国籍或补充事实拼接为 shell 命令。每次调用在临时目录运行，使用 `--sandbox read-only`、`--ephemeral`、`--json`、`--output-schema` 和 `--output-last-message`，启用实时搜索；关闭与研究无关的 shell、apps、plugins、hooks、computer use、browser use、memories 与 multi-agent 能力，保留现有认证和模型服务设置。

调用有总超时和输出上限；只返回安全中文错误，不返回原始认证输出、敏感日志或持久化原始会话。只读执行限制不改变模型服务的数据处理规则。

来源证据来自本次 stdout JSONL 中的真实搜索工具事件。最终模型文本中的 URL、搜索次数声明或“已阅读”声明均不能替代工具轨迹。CLI 版本可能只返回有限来源信息；程序按实际事件核对来源和打开记录，缺少证据时降级或拒绝结果，不补造已核验标记。两种运行方式共享五主题、场景适用、日期、来源和报告校验。

## 稳定接口

输入字段：country、nationality（必填），subdivision、employment_model（unspecified/direct/eor/expatriate/other）、query_mode（rules/case）、as_of_date（YYYY-MM-DD）、details（可选补充）。provider、api_key 和 model 属于运行设置，不进入上述场景记录。provider 缺失时使用服务默认值，显式传入时仅接受 codex/openai。

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

研究模块增加非模型生成的运行信息：mode（live/demo）、provider（实时模式为 codex/openai）、generated_at、model、query、verification_notes、web_search_count；每个来源附 observed_in_search 与 opened_by_tool（仅表示工具轨迹明确出现 open_page）。provider 属于服务端运行元数据，不要求模型生成；网页和 Markdown 均展示运行方式。程序不能把“在搜索来源列表中出现”解释成“已读取原文”。无法确认原文读取的来源要降级对应结论并说明。界面展示只读的原始查询条件，避免将历史结果误用于当前表单里的新场景。

HTTP 接口：

| 接口 | 返回或输入约定 |
| --- | --- |
| `GET /api/config` | `default_provider`、`codex_default_model`、`codex` 状态对象，保留 `default_model`（直连 API 默认模型）、`api_key_configured`、`session_token` |
| `POST /api/research` | 场景输入及可选 `provider`、`model`；`api_key` 仅用于直连 API 模式 |
| `POST /api/demo` | 虚构演示，不依赖所选实时模式或认证 |
| `GET /api/reports` | 本地历史列表 |
| `GET /api/reports/{id}` | 完整报告 |
| `GET /api/reports/{id}/markdown` | Markdown 下载 |
| `GET /api/reports/{id}/json` | JSON 下载 |

`codex` 状态对象包含 `installed`、`auth_status`、`auth_mode`、`message`、`version`；不包含凭据或原始 CLI 认证输出。POST 需 X-Session-Token；外部 Origin/Host 拒绝。成功研究返回 {id, report, markdown}，错误返回 {error}。请求同步执行，前端明确提示研究可能需要数分钟；不虚构进度百分比。

## 验收

使用固定模拟 API 响应及 Codex 进程/JSONL 事件检验：伪造来源、没有实际搜索、缺失主题、非官方或未打开来源、一般规则被写成个案结论、过期日期、拒答/截断、上游超时。另检验 CLI 命令参数、输入隔离、认证脱敏、输出上限、错误事件及无凭据回传。HTTP 回归覆盖默认与显式 provider、本机模式无网页 Key 调用、直连 API 模式 Key 要求、未知 provider 拒绝和失败不自动切换。

离线演示、HTTP 请求校验、凭据不写入报告、历史下载和规则复用应独立测试。真实 Codex 调用、直连 API 调用和法务解释质量须分别披露验证范围；安装/认证探测或离线测试通过均不能替代真实调用验证。

发布：独立 Git 仓库、MIT 许可、中文 README、跨平台启动说明、公开模拟样例、贡献说明、自动测试工作流模板（启用需要相应 GitHub 权限）。用户已选择公开 GitHub 项目和“本地网页＋可复制指令”的交付形式。

## 官方接口依据

- [Codex CLI 安装](https://developers.openai.com/codex/cli/)
- [Codex 认证](https://developers.openai.com/codex/auth)
- [Codex 非交互模式](https://developers.openai.com/codex/noninteractive)
- [Codex CLI 参数参考](https://developers.openai.com/codex/cli/reference)
