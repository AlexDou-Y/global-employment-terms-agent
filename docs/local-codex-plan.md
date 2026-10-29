# 本机 Codex 模式实施计划

**目标：** 用户选择“本机 Codex”后，无需在网页输入 API Key，复用本机 Codex 的已有认证生成五主题研究报告。用户已确认采用此方案。

**架构：** 本地 Python 服务以参数列表和标准输入启动 `codex exec`，获取 JSONL 工具轨迹和符合现有 Schema 的最终结果。API 模式继续使用原研究模块；两种模式共享来源限制、场景匹配、历史与导出。

**技术：** Python 标准库、Codex CLI 非交互模式、现有 HTML/JavaScript；不读取或复制认证文件，不启动登录流程、不修改使用者的全局配置。当前服务额外注册本项目只读网页 MCP，以兼容没有内置网页搜索的模型服务。

## 交互与接口

- 网页默认 `provider=codex`；可切换 `provider=openai`。仅 OpenAI 模式需要网页 API Key。
- `/api/config` 增加 `default_provider`、`codex`（installed、auth_status、auth_mode、message、version）与 `codex_default_model`；不返回凭据或 CLI 原始认证输出。
- 本机模式默认不传模型参数，沿用使用者配置。可选 `CODEX_MODEL` 或网页指定模型。现有 `OPENAI_MODEL` 只用于 API 模式。
- `POST /api/research` 接收 provider。未知值拒绝；缺失值按服务默认值选择；任何失败均不自动切换为收费 API 模式。
- 报告记录 provider，并在页面与 Markdown 中显示。原始查询条件不包含认证数据。
- 未安装 CLI 时提示安装并执行 `codex login`；未认证时提示本人在终端完成登录；探测只能证明配置存在，实际权限以研究调用为准。

## 调用与证据边界

- 使用 `--sandbox read-only`、`--ephemeral`、`--json`、`--output-schema`、`--output-last-message`，显式启用实时搜索；使用临时工作目录。
- 不使用 shell 拼接执行。国家、国籍和补充事实仅通过 stdin 作为数据发送。
- 禁用本次调用中与网页研究无关的 shell、apps、plugins、hooks、computer use、browser use、memories 与 multi-agent 能力；保留已有认证和模型提供商设置。
- 设置总运行超时、输出上限；错误返回安全中文提示，不回传包含凭据的日志，不保留原始会话。
- CLI 版本的事件结构可能不同。只接受本次真实工具轨迹支持的来源与打开记录；最终模型文本中的 URL 不能冒充工具证据。缺乏详细来源轨迹时降级，而不是伪造“已核验”。

## 任务

- [x] 核对官方接口与本机 CLI，并进行有限真实试跑，确认认证与事件格式。
- [x] 新增 `codex_backend.py` 及失败优先测试：命令构造、认证脱敏、超时、失败事件、假引用与输出结构。
- [x] 增加服务端 provider 分发及 HTTP 回归测试，保证 Codex 无 Key 可调用、API 模式仍要求 Key。
- [x] 网页增加运行方式选择、Codex 状态、模型与认证提示，验证模式切换、演示和错误处理。
- [x] 更新说明、配置模板与验证记录；在可用认证下完成真实研究或明确记录实际阻碍。
- [x] 独立评审、完整测试、浏览器核对，发布 GitHub 并更新本地 ZIP。

## 依据

- https://developers.openai.com/codex/auth
- https://developers.openai.com/codex/noninteractive
- https://developers.openai.com/codex/cli/reference
