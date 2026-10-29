# 验证记录

日期：2026-10-29。版本：0.2.0，默认使用本机 Codex，初期研究工具。

## v0.2 本机 Codex 验证

- Windows、Python 3.13.12、Codex CLI 0.164.0-alpha.11.1：121 项离线测试全部通过，包含 39 项 Codex 适配、33 项只读网页工具测试及原有研究、服务和存储测试。
- 真实认证和工具调用：复用本机已有认证，无需在网页填写 API Key；一次搜索、读取新加坡人力部官方页面及结构化响应约 20 秒完成。
- 真实五问报告：使用“新加坡、中国籍、当地实体直接雇佣、2026-10-29”的通用规则场景完成研究并保存 JSON/Markdown，耗时约 222 秒；记录 2 次搜索、14 次工具调用和 7 个来源，其中 6 个有成功读取正文的记录、1 个未确认读取。
- 五个主题均保留“部分支持”，未将缺少生效日期或未读取法规原文的事项升级为充分支持。此验证证明调用链与证据状态处理可用，不等于所有法律子项已完成专业复核。
- 浏览器已核对默认 Codex 模式、认证配置提示、API Key 隐藏，以及切换 API 模式后的独立模型和密钥输入。
- 已复核：失败工具调用不能算有效证据；表格相邻数字保持分隔；正常关闭服务会清理本程序启动的活跃 CLI/MCP 进程树，不影响用户其他会话。
- 本机认证实际为既有 API Key 配置模式；未改变用户认证，也未现场切换至 ChatGPT 登录。ChatGPT 登录复用方式依据官方文档及状态解析测试，实际可用性受使用者账号权限和额度约束。

第一轮完整研究曾触发 300 秒超时。当前每次调用显式不加载项目说明、使用 medium 推理设置，并提示最多 14 次检索/读取；仍保留 300 秒硬超时。检索次数是模型指令预算，执行时间上限由程序控制。

当前网络能力边界：自带搜索使用公开 Bing RSS，结果为空时可沿实际官方网页链接继续查找；不支持 PDF 正文，HTML 正文最多 28,000 字符并标记截断。无法读取的内容保持待核验。

## v0.1 基础验证记录

- Windows、Python 3.13.12：46 项离线单元/集成测试通过，覆盖研究 API 模拟响应、来源追溯、证据不足降级、国家/州省与日期匹配、五主题完整性、拒答/截断、密钥处理、HTTP 请求限制、本地历史与规则卡。
- JavaScript：`node --check employment_agent/static/app.js` 通过。
- 浏览器：实际打开本地页面，运行无密钥演示，验证五主题、原查询条件、演示标识和缺少 API Key 提示；窄屏页面无可见截断问题。
- HTTP：演示、历史、Markdown/JSON 下载及无效请求处理通过；演示可在禁止网络调用的测试条件下完成。
- 包构建：生成 Python wheel，并核对服务、研究模块及全部网页资源包含在包中。
- 独立 Skill：`quick_validate.py` 通过；公开文档相对链接、UTF-8 与模拟 JSON 检查通过。
- 独立规格评审：修复混合证据误标充分支持、辖区错配未拒绝、历史报告缺少原查询条件三项问题后复核通过。
- 独立代码评审：修复个案“不适用”结论未随证据或事实不足降级的问题，新增回归后复核通过；Python 3.10 语法兼容检查通过。

## 仍未验证的范围

- 可选的“OpenAI API”直连模式未执行真实成功请求；v0.2 已实测的是本机 Codex 模式，二者分别记录。
- 模型的来源官方属性分类、摘录忠实度、法律现行性及个案解释需要后续真实场景评估；程序性来源轨迹检查不等于法律审查。
- GitHub Actions 的 Windows / Ubuntu 与 Python 3.10 / 3.13 测试矩阵已保存为 `docs/ci/offline-tests.yml` 模板。当前发布凭据无法创建工作流，未启用远端执行，因此不声称 Linux 或 Python 3.10 运行测试已通过。

## 复现

```bash
python -m unittest discover -s tests -v
node --check employment_agent/static/app.js
python -m employment_agent
```

网页打开 `http://127.0.0.1:8765`，可选择“查看演示”，或默认使用本机 Codex。安装 Codex 并由本人完成登录后，网页复用其已有认证；只有切换“OpenAI API”模式才需要网页密钥或 OPENAI_API_KEY。

## API 实现依据

- [OpenAI Web search](https://developers.openai.com/api/docs/guides/tools-web-search)
- [OpenAI Structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [Codex Authentication](https://developers.openai.com/codex/auth)
- [Codex Non-interactive mode](https://developers.openai.com/codex/noninteractive)

API 模式采用 Responses API；本机模式采用 Codex exec 与本项目只读 MCP。接口可用性仍受账户权限、模型能力、网络与服务更新影响。
