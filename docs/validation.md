# 验证记录

日期：2026-10-29。版本：0.1.0，初期研究工具。

## 已执行

- Windows、Python 3.13.12：46 项离线单元/集成测试通过，覆盖研究 API 模拟响应、来源追溯、证据不足降级、国家/州省与日期匹配、五主题完整性、拒答/截断、密钥处理、HTTP 请求限制、本地历史与规则卡。
- JavaScript：`node --check employment_agent/static/app.js` 通过。
- 浏览器：实际打开本地页面，运行无密钥演示，验证五主题、原查询条件、演示标识和缺少 API Key 提示；窄屏页面无可见截断问题。
- HTTP：演示、历史、Markdown/JSON 下载及无效请求处理通过；演示可在禁止网络调用的测试条件下完成。
- 包构建：生成 Python wheel，并核对服务、研究模块及全部网页资源包含在包中。
- 独立 Skill：`quick_validate.py` 通过；公开文档相对链接、UTF-8 与模拟 JSON 检查通过。
- 独立规格评审：修复混合证据误标充分支持、辖区错配未拒绝、历史报告缺少原查询条件三项问题后复核通过。
- 独立代码评审：修复个案“不适用”结论未随证据或事实不足降级的问题，新增回归后复核通过；Python 3.10 语法兼容检查通过。

## 尚未验证

- 当前开发环境没有配置 API Key，因此未执行真实 OpenAI API 成功请求，也没有声称已核验任何国家的现行法律结论。
- 模型的来源官方属性分类、摘录忠实度、法律现行性及个案解释需要后续真实场景评估；程序性来源轨迹检查不等于法律审查。
- GitHub Actions 的 Windows / Ubuntu 与 Python 3.10 / 3.13 测试矩阵已保存为 `docs/ci/offline-tests.yml` 模板。当前发布凭据无法创建工作流，未启用远端执行，因此不声称 Linux 或 Python 3.10 运行测试已通过。

## 复现

```bash
python -m unittest discover -s tests -v
node --check employment_agent/static/app.js
python -m employment_agent
```

网页打开 `http://127.0.0.1:8765`，选择“查看演示”。真实研究需自行配置具有相关模型与联网工具权限的 API Key，确认费用并选择适当的业务样例。

## API 实现依据

- [OpenAI Web search](https://developers.openai.com/api/docs/guides/tools-web-search)
- [OpenAI Structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs)

实现采用 Responses API 的 web_search、来源记录与严格结构化输出；接口可用性仍受账户权限、模型能力与服务更新影响。
