# Global Employment Terms Agent Implementation Plan

> For agentic workers: use superpowers:subagent-driven-development for bounded implementation tasks and review the integrated result.

**Goal:** 交付可运行、可下载复用的海外劳动合同与试用期研究工具，并发布到 GitHub。

**Architecture:** Python 标准库本地 HTTP 服务连接 Responses API，先联网研究、再整理结构化报告。核心规则校验独立于网页与存储，通用指令可复制到其他助手。

**Tech Stack:** Python 3.10+、unittest、HTML/CSS/JavaScript、OpenAI Responses API、GitHub Actions。

## Task 1: 研究与证据链

- [x] 创建 employment_agent/research.py、validation.py、reports.py、schema.py。
- [x] 先编写 tests/test_research.py、tests/test_validation.py、tests/test_reports.py，使用模拟远程响应验证真正的输出限制与失败处理，确认缺少实现时失败。
- [x] 实现输入验证、两阶段 API 调用、实际来源提取、五主题校验和 Markdown 输出。
- [x] 运行 python -m unittest discover -s tests -v，确认研究模块用例通过。

## Task 2: 网页交互

- [x] 创建 employment_agent/static/index.html、app.css、app.js。
- [x] 提供两项必填输入、可选场景字段、Key/model 设置、演示、实时研究、来源与条件、历史和下载。
- [x] 使用 textContent 渲染所有模型内容，限制来源链接为 HTTP(S)；API Key 不进浏览器持久存储。
- [x] 用 node --check employment_agent/static/app.js 检查语法，再通过实际浏览器完成演示与错误路径检查。

## Task 3: 本地服务与存储

- [x] 先编写 tests/test_server.py、tests/test_storage.py：拒绝外部 Host/Origin、无 token 请求、路径穿越；Key 不落盘；规则模式才保存规则卡。
- [x] 创建 employment_agent/server.py、storage.py、__main__.py、__init__.py 和 pyproject.toml。
- [x] 启动 python -m employment_agent --port 8765，验证 API 与下载；错误响应不包含上游密钥或原始机密内容。

## Task 4: 可复制指令与公开文档

- [x] 创建 prompts/agent-instructions.md、skills/global-employment-terms/SKILL.md 及必要引用。
- [x] 创建 README.md、LICENSE、CONTRIBUTING.md、.env.example、.gitignore、examples/input.json 和 GitHub Actions 测试模板；当前凭据不能创建工作流，模板作为普通文件发布。
- [x] 文档与实现接口一致，演示不包含真实法律结论或员工信息，说明实时调用费用、联网依赖与 AI 核验边界。

## Task 5: 整体验证与发布

- [x] 执行全部测试、浏览器演示、有效/无效请求及下载验证。
- [x] 由独立代理先检查需求覆盖，再检查质量；修复重要问题并重新验证相关场景。
- [x] 检查待提交文件清单，确认不包含本地配置、Key、员工资料或真实查询结果。
- [x] 创建独立提交，发布公开 GitHub 仓库；核对远端文件与仓库可见性，提供链接和启动方法。
