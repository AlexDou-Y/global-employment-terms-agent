"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const state = { config: null, busy: false, timer: null, startedAt: 0, activeReport: null, provider: "codex", providerChosen: false, models: { codex: "", openai: "" }, modelEdited: { codex: false, openai: false } };
  const providerLabels = { codex: "本机 Codex", openai: "OpenAI API" };
  const topicNames = {
    fixed_term_allowed: "固定期限合同是否允许",
    fixed_term_duration: "合同期限限制",
    renewal_conversion: "续签与无固定期限转化",
    probation: "试用期约定",
    probation_termination: "试用期绩效不符解除",
  };
  const ruleLabels = { supported: "已找到依据", partial: "依据不完整", unverified: "尚未核实", conflict: "依据存在冲突" };
  const applicationLabels = { general_rule: "通用规则", conditional: "有条件适用", meets_conditions: "按已知事实符合条件", does_not_meet: "按已知事实不符合条件", insufficient_info: "个案信息不足", not_applicable: "不适用于本场景" };
  const sourceLabels = { official: "官方（AI 分类）", professional: "专业机构", vendor: "供应商", other: "其他来源" };
  const employmentLabels = { unspecified: "尚未确定", direct: "当地实体直接雇佣", eor: "EOR 名义雇主", expatriate: "跨境外派", other: "其他安排" };
  const queryModeLabels = { rules: "通用规则研究", case: "具体个案判断" };
  const text = (value, fallback = "") => typeof value === "string" ? value : (typeof value === "number" ? String(value) : fallback);
  const list = (value) => Array.isArray(value) ? value : [];

  function element(tag, className, value) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (value !== undefined) node.textContent = text(value);
    return node;
  }

  function safeUrl(value) {
    try {
      const url = new URL(value);
      return ["https:", "http:"].includes(url.protocol) ? url.href : null;
    } catch { return null; }
  }

  function reportPath(id) {
    return "/api/reports/" + encodeURIComponent(text(id));
  }

  function dateLabel(value) {
    if (!value) return "时间未提供";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? text(value) : date.toLocaleString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  }

  function addTextList(parent, values, emptyText) {
    const entries = list(values).filter((item) => typeof item === "string" && item.trim());
    if (!entries.length) {
      if (emptyText) parent.append(element("p", "empty-note", emptyText));
      return;
    }
    const ul = element("ul", "text-list");
    entries.forEach((entry) => ul.append(element("li", "", entry)));
    parent.append(ul);
  }

  async function request(path, options = {}) {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 15 * 60 * 1000);
    try {
      const response = await fetch(path, { ...options, signal: controller.signal, cache: "no-store" });
      let data;
      try { data = await response.json(); }
      catch { throw new Error("服务返回了无法读取的响应，请确认本地服务正常运行后重试。"); }
      if (!response.ok) throw new Error(text(data.error, "请求失败，请稍后重试。"));
      return data;
    } catch (error) {
      if (error.name === "AbortError") throw new Error("请求等待超时。请检查本地服务状态，再重试；历史列表可能已有保存的报告。");
      if (error instanceof TypeError) throw new Error("无法连接本地服务。请确认服务仍在运行，再重试。");
      throw error;
    } finally { window.clearTimeout(timeout); }
  }

  async function loadConfig() {
    try {
      const config = await request("/api/config");
      if (!config || typeof config.session_token !== "string" || !config.session_token) throw new Error("未能取得服务会话，请重新启动本地服务后刷新页面。");
      state.config = config;
      if (!state.providerChosen) state.provider = config.default_provider === "openai" ? "openai" : "codex";
      if (!state.modelEdited.codex) state.models.codex = text(config.codex_default_model);
      if (!state.modelEdited.openai) state.models.openai = text(config.default_model);
      $("provider").value = state.provider;
      $("model").value = state.models[state.provider];
      $("api-key").placeholder = config.api_key_configured ? "已使用服务环境密钥，可按需覆盖" : "sk-…";
      $("api-key-help").textContent = config.api_key_configured ? "服务环境已配置密钥；此处可留空。填写的密钥仅用于本次请求。" : "密钥仅用于本次请求，不保存到浏览器或报告。";
      updateRuntime();
      $("config-notice").hidden = true;
      return config;
    } catch (error) {
      state.config = null;
      updateRuntime();
      $("connection-badge").textContent = "连接未就绪";
      $("connection-badge").className = "connection-badge missing";
      $("runtime-status").textContent = "暂未取得运行环境状态。请确认本地服务正常运行后刷新页面。";
      $("runtime-status").className = "field-help runtime-status missing";
      $("config-notice").textContent = error.message;
      $("config-notice").hidden = false;
      throw error;
    }
  }

  function updateRuntime() {
    const codexMode = state.provider === "codex";
    const config = state.config;
    $("api-key-field").hidden = codexMode;
    $("api-key").disabled = codexMode;
    $("model-optional").hidden = !codexMode;
    $("model").placeholder = codexMode ? "留空，沿用本机 Codex 设置" : "填写模型名称";
    $("model-help").textContent = codexMode ? "可留空沿用本机设置，或填写当前 Codex 可用的模型名称。" : "请使用支持 Responses API 联网搜索的模型。";
    $("request-note").textContent = codexMode ? "联网核验会将填写的信息发送至模型服务商。复用本机 Codex 认证，受对应账号或服务用量限制。" : "联网核验会将填写的信息发送至模型服务商，API 用量由服务商计费。";
    let badge = "读取中";
    let status = codexMode ? "正在检查本机 Codex 状态…" : "正在读取 API 连接设置…";
    let tone = "";
    if (config && codexMode) {
      const codex = config.codex || {};
      if (codex.installed === false) {
        badge = "未检测到安装";
        status = "未检测到本机 Codex。请先在终端运行 npm install -g @openai/codex 安装，再运行 codex login 登录；完成后重启本地服务并刷新页面。";
        tone = "missing";
      } else if (codex.auth_status === "not_configured") {
        badge = "待登录配置";
        status = "已检测到本机 Codex，尚未检测到认证配置。请本人在终端运行 codex login，完成后刷新页面。";
        tone = "missing";
      } else if (codex.installed === true && codex.auth_status === "configured") {
        badge = "已检测到配置";
        const auth = codex.auth_mode === "chatgpt" ? "ChatGPT 登录" : codex.auth_mode === "api_key" ? "API Key 认证" : "认证";
        status = "已检测到本机 Codex 的" + auth + "配置，无需在网页填写密钥。实际权限与用量可用性以本次调用结果为准。";
        tone = "ready";
      } else {
        badge = "状态待确认";
        status = "暂未确认本机 Codex 认证状态。可在终端运行 codex login status 检查；如需登录，请运行 codex login，完成后刷新页面。";
        tone = "missing";
      }
    } else if (config) {
      badge = config.api_key_configured ? "密钥已配置" : "待填写密钥";
      status = config.api_key_configured ? "已检测到服务环境密钥，可直接发起 API 请求；实际可用性以调用结果为准。" : "请展开“模型与连接设置”填写本次请求使用的 API Key。";
      tone = config.api_key_configured ? "ready" : "missing";
    }
    $("connection-badge").textContent = badge;
    $("connection-badge").className = "connection-badge " + tone;
    $("runtime-status").textContent = status;
    $("runtime-status").className = "field-help runtime-status " + tone;
  }

  function showError(message) {
    $("request-error-text").textContent = text(message, "请求未完成，请重试。");
    $("request-error").hidden = false;
    $("request-error").scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function setBusy(busy, mode = "live") {
    state.busy = busy;
    $("research-button").disabled = busy;
    $("demo-button").disabled = busy;
    $("history-refresh").disabled = busy;
    $("provider").disabled = busy;
    $("model").disabled = busy;
    $("research-form").setAttribute("aria-busy", String(busy));
    $("request-status").hidden = !busy;
    $("report-panel").classList.toggle("busy-report", busy);
    window.clearInterval(state.timer);
    state.timer = null;
    if (busy) {
      $("request-error").hidden = true;
      $("request-status-title").textContent = mode === "demo" ? "正在载入演示报告" : mode === "history" ? "正在读取历史报告" : "正在通过" + providerLabels[state.provider] + "联网核验";
      $("request-status-message").textContent = mode === "live" ? "正在检索来源并整理报告，可能需要数分钟。请保持页面打开。" : "正在从本地服务读取报告。";
      state.startedAt = Date.now();
      $("elapsed-time").textContent = "";
      state.timer = window.setInterval(() => {
        const seconds = Math.floor((Date.now() - state.startedAt) / 1000);
        $("elapsed-time").textContent = seconds >= 60 ? "已等待 " + Math.floor(seconds / 60) + " 分 " + seconds % 60 + " 秒" : "已等待 " + seconds + " 秒";
      }, 1000);
    }
  }

  function collectQuery() {
    return {
      country: $("country").value.trim(), nationality: $("nationality").value.trim(),
      subdivision: $("subdivision").value.trim(), employment_model: $("employment-model").value,
      query_mode: $("query-mode").value, as_of_date: $("as-of-date").value,
      details: $("details").value.trim(),
    };
  }

  async function runResearch(mode) {
    if (state.busy) return;
    if (mode === "live" && !$("research-form").reportValidity()) return;
    setBusy(true, mode);
    try {
      const config = state.config || await loadConfig();
      const payload = mode === "demo" ? {} : collectQuery();
      if (mode === "live") {
        payload.provider = state.provider;
        payload.model = $("model").value.trim();
        if (state.provider === "openai") {
          const key = $("api-key").value.trim();
          if (!key && !config.api_key_configured) {
            $("runtime-settings").open = true;
            $("api-key").focus();
            throw new Error("OpenAI API 模式需要 API Key。请在“模型与连接设置”中填写，或选择已配置的本机 Codex。演示报告无需密钥。");
          }
          payload.api_key = key;
          payload.model = payload.model || text(config.default_model);
        }
        $("api-key").value = "";
      }
      const data = await request(mode === "demo" ? "/api/demo" : "/api/research", {
        method: "POST", headers: { "Content-Type": "application/json", "X-Session-Token": config.session_token }, body: JSON.stringify(payload),
      });
      renderReport(data);
      await loadHistory();
    } catch (error) { showError(error.message); }
    finally { setBusy(false); }
  }

  function addSection(parent, title, entries, emptyText) {
    const card = element("section", "content-card");
    const heading = element("div", "section-heading");
    heading.append(element("h3", "", title));
    card.append(heading);
    addTextList(card, entries, emptyText);
    parent.append(card);
  }

  function renderFinding(finding, index, sourceTargets) {
    const card = element("article", "topic-card");
    const heading = element("div", "finding-heading");
    heading.append(element("span", "finding-number", String(index + 1).padStart(2, "0")), element("h4", "", topicNames[finding.topic] || "核验主题"));
    const status = Object.hasOwn(ruleLabels, finding.rule_status) ? finding.rule_status : "unverified";
    heading.append(element("span", "status-label " + status, ruleLabels[status]));
    card.append(heading, element("p", "rule-summary", text(finding.rule_summary, "暂未提供结论。")));
    const application = element("div", "application-box");
    application.append(element("strong", "", applicationLabels[finding.application_status] || "适用状态未提供"), element("p", "", text(finding.application_note, "请结合具体事实确认适用性。")));
    card.append(application);
    const details = element("details", "finding-details");
    details.append(element("summary", "", "适用条件、例外与依据"));
    const columns = element("div", "two-columns");
    const conditions = element("div");
    conditions.append(element("h5", "small-heading", "适用条件"));
    addTextList(conditions, finding.conditions, "未列明，仍需结合场景确认。");
    const exceptions = element("div");
    exceptions.append(element("h5", "small-heading", "例外与限制"));
    addTextList(exceptions, finding.exceptions, "未列明例外，不等于不存在例外。");
    columns.append(conditions, exceptions);
    details.append(columns);
    card.append(details);
    const evidence = element("div", "evidence-links");
    evidence.append(element("span", "", "关联依据"));
    const ids = list(finding.evidence_ids);
    if (!ids.length) evidence.append(element("span", "", "暂未关联来源"));
    ids.forEach((id) => {
      const target = sourceTargets.get(id);
      if (!target) { evidence.append(element("span", "", text(id) + "（来源未列明）")); return; }
      const link = element("a", "evidence-link", id);
      link.href = "#" + target;
      link.addEventListener("click", () => { const source = $(target); if (source) source.open = true; });
      evidence.append(link);
    });
    card.append(evidence);
    return card;
  }

  function renderSource(source, index, target) {
    const card = element("details", "source-card");
    card.id = target;
    const heading = element("summary");
    heading.append(element("span", "source-id", text(source.id, "S" + (index + 1))), element("span", "source-title", text(source.title, "未命名来源")));
    card.append(heading);
    const meta = element("div", "source-meta");
    meta.append(element("span", "source-pill", sourceLabels[source.source_type] || "类型未提供"), element("span", "source-pill", source.observed_in_search === true ? "搜索轨迹中出现" : "搜索轨迹未确认"), element("span", "source-pill " + (source.opened_by_tool === true ? "opened" : ""), source.opened_by_tool === true ? "工具已读取内容" : "正文读取未确认"));
    card.append(meta);
    const body = element("div", "source-body");
    const facts = element("dl");
    [["发布机构", source.publisher], ["具体位置", source.locator], ["生效日期", source.effective_date], ["访问日期", source.accessed_on]].forEach(([label, value]) => {
      facts.append(element("dt", "", label), element("dd", "", text(value, "未提供")));
    });
    if (source.document_type === "pdf") {
      const pages = list(source.pages_read).filter((page) => Number.isInteger(page) && page > 0);
      const total = Number.isInteger(source.total_pages) && source.total_pages > 0 ? String(source.total_pages) : "未知";
      facts.append(element("dt", "", "PDF 已读页码"), element("dd", "", pages.join("、") || "未记录"), element("dt", "", "PDF 总页数"), element("dd", "", total));
    }
    body.append(facts);
    if (source.document_type === "pdf") body.append(element("p", "card-note", "页码仅表示已读取选定页的可提取文本，不代表全文完整读取。"));
    const url = safeUrl(source.url);
    if (url) {
      const link = element("a", "", "打开来源链接 ↗");
      link.href = url; link.target = "_blank"; link.rel = "noopener noreferrer";
      body.append(link);
    } else body.append(element("p", "card-note", "未提供可打开的 http / https 来源链接。"));
    if (source.excerpt) body.append(element("blockquote", "source-excerpt", source.excerpt));
    card.append(body);
    return card;
  }

  function renderQueryContext(report) {
    const query = report.query && typeof report.query === "object" ? report.query : {};
    function queryValue(key, labels) {
      if (!Object.hasOwn(query, key) || query[key] === null || query[key] === undefined) return "未提供";
      const value = text(query[key]).trim();
      if (!value) return "未填写";
      return labels && Object.hasOwn(labels, value) ? labels[value] : value;
    }
    const card = element("section", "content-card report-query");
    card.setAttribute("aria-labelledby", "report-query-title");
    const heading = element("div", "section-heading");
    const title = element("h3", "", "本报告查询条件");
    title.id = "report-query-title";
    heading.append(title, element("span", "count", "只读"));
    card.append(heading, element("p", "card-note", "以下为生成此报告时保存的场景信息，与左侧正在编辑的内容独立。"));
    const facts = element("dl", "report-query-grid");
    [
      ["实际工作国家／地区", "country"], ["员工国籍", "nationality"],
      ["州／省／城市", "subdivision"], ["用工安排", "employment_model", employmentLabels],
      ["研究范围", "query_mode", queryModeLabels], ["规则适用日期", "as_of_date"],
    ].forEach(([label, key, labels]) => {
      const item = element("div", "report-query-item");
      item.append(element("dt", "", label), element("dd", "", queryValue(key, labels)));
      facts.append(item);
    });
    card.append(facts);
    const details = element("details", "report-query-details");
    details.append(element("summary", "", "补充事实"), element("p", "", queryValue("details")));
    card.append(details);
    return card;
  }

  function renderReport(data) {
    if (!data || !data.report || typeof data.report !== "object" || !data.id || !["live", "demo"].includes(data.report.mode)) throw new Error("报告数据不完整或研究模式未确认，请重试或查看本地服务日志。");
    const report = data.report;
    state.activeReport = data.id;
    const panel = $("report-panel");
    const content = document.createDocumentFragment();
    const demo = report.mode === "demo";
    if (demo) content.append(element("div", "demo-notice", "虚构地区演示 · 本报告仅用于展示结构，不代表任何国家或地区的现行法律，不可用于实际用工决定。"));
    const header = element("header", "report-header");
    const topline = element("div", "report-topline");
    topline.append(element("span", "report-kicker", "EMPLOYMENT RESEARCH REPORT"), element("span", "mode-badge" + (demo ? " demo" : ""), demo ? "演示报告" : report.research_incomplete === true ? "部分研究 · 恢复整理" : "联网研究报告"));
    header.append(topline, element("h2", "", text(report.jurisdiction, "用工规则研究")), element("p", "report-summary", report.summary));
    const meta = element("div", "report-meta");
    meta.append(element("span", "", "规则日期 " + text(report.as_of_date, "未提供")), element("span", "", "生成于 " + dateLabel(report.generated_at)));
    if (!demo && Object.hasOwn(providerLabels, report.provider)) meta.append(element("span", "", "运行方式 " + providerLabels[report.provider]));
    if (report.scope) meta.append(element("span", "", report.scope));
    header.append(meta);
    content.append(header, renderQueryContext(report));
    if (list(report.assumptions).length) {
      const assumptions = element("details", "assumptions-details");
      assumptions.append(element("summary", "", "本次研究的前提与范围（" + report.assumptions.length + "）"));
      addTextList(assumptions, report.assumptions);
      content.append(assumptions);
    }
    const toolbar = element("div", "report-toolbar");
    toolbar.append(element("h3", "", "五项规则核验"));
    const downloads = element("div", "download-actions");
    [["Markdown", "/markdown"], ["JSON", "/json"]].forEach(([label, suffix]) => {
      const link = element("a", "button button-small button-quiet", "↓ " + label);
      link.href = reportPath(data.id) + suffix; link.setAttribute("download", "");
      downloads.append(link);
    });
    toolbar.append(downloads); content.append(toolbar);
    const sourceTargets = new Map();
    list(report.sources).forEach((source, i) => sourceTargets.set(source.id, "report-source-" + i));
    const findings = list(report.findings);
    Object.keys(topicNames).forEach((topic, index) => {
      const finding = findings.find((item) => item && item.topic === topic) || { topic, rule_status: "unverified", rule_summary: "本项未返回有效结论。", application_status: "insufficient_info" };
      content.append(renderFinding(finding, index, sourceTargets));
    });
    addSection(content, "仍需补充或确认", report.follow_up_questions, "本次报告未列出追问；仍请核对前提与场景是否完整。");
    addSection(content, "HR 后续行动", report.hr_actions, "本次报告未列出后续行动。");
    const sources = element("section", "content-card");
    const sourceHeading = element("div", "section-heading");
    sourceHeading.append(element("h3", "", "来源与研究记录"), element("span", "count", String(list(report.sources).length)));
    sources.append(sourceHeading, element("p", "card-note", "“已找到依据”是研究证据状态，不等于法律审核通过。发现来源链接不等于已读取内容；已读取内容不等于已取得支持本项结论的条文。搜索摘要不计为已读正文。"));
    const sourceList = element("div", "sources-list");
    list(report.sources).forEach((source, i) => sourceList.append(renderSource(source, i, "report-source-" + i)));
    if (!list(report.sources).length) sourceList.append(element("p", "empty-note", "报告未返回可追溯来源。"));
    sources.append(sourceList);
    if (list(report.verification_notes).length) {
      const notes = element("details", "assumptions-details");
      notes.append(element("summary", "", "核验说明"));
      addTextList(notes, report.verification_notes);
      sources.append(notes);
    }
    if (report.model || typeof report.web_search_count === "number") {
      const runInfo = [report.model ? "研究模型：" + text(report.model) : "", typeof report.web_search_count === "number" ? "记录到的搜索调用：" + report.web_search_count : ""].filter(Boolean).join(" · ");
      sources.append(element("p", "card-note", runInfo));
    }
    content.append(sources);
    panel.replaceChildren(content);
    $("welcome-panel").hidden = true;
    panel.hidden = false;
    panel.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function openHistory(id) {
    if (state.busy) return;
    setBusy(true, "history");
    try { renderReport(await request(reportPath(id))); }
    catch (error) { showError(error.message); }
    finally { setBusy(false); }
  }

  async function loadHistory() {
    $("history-error").hidden = true;
    try {
      const data = await request("/api/reports");
      const reports = list(data.reports);
      $("history-count").textContent = String(reports.length);
      const fragment = document.createDocumentFragment();
      if (!reports.length) fragment.append(element("p", "empty-note", "还没有报告。完成核验或查看演示后，报告会出现在这里。"));
      reports.forEach((report) => {
        if (!report || !report.id) return;
        const button = element("button", "history-item"); button.type = "button";
        button.append(element("strong", "", text(report.jurisdiction, "未命名报告")), element("p", "", text(report.summary, "点击查看完整报告")));
        const metadata = element("small", "", dateLabel(report.generated_at));
        const modeLabel = report.mode === "demo" ? "虚构演示" : report.research_incomplete === true ? "部分研究 · 恢复整理" : Object.hasOwn(providerLabels, report.provider) ? "联网研究 · " + providerLabels[report.provider] : "联网研究";
        metadata.append(element("span", "history-mode" + (report.mode === "demo" ? " demo" : ""), modeLabel));
        button.append(metadata);
        button.addEventListener("click", () => openHistory(report.id));
        fragment.append(button);
      });
      $("history-list").replaceChildren(fragment);
    } catch (error) {
      $("history-error").textContent = "历史报告暂时无法读取：" + error.message;
      $("history-error").hidden = false;
      if (!$("history-list").querySelector("button")) $("history-list").replaceChildren(element("p", "empty-note", "可在服务恢复后刷新列表。"));
    }
  }

  const today = new Date();
  $("as-of-date").value = [today.getFullYear(), String(today.getMonth() + 1).padStart(2, "0"), String(today.getDate()).padStart(2, "0")].join("-");
  $("provider").addEventListener("change", () => {
    state.models[state.provider] = $("model").value;
    state.provider = $("provider").value === "openai" ? "openai" : "codex";
    state.providerChosen = true;
    $("model").value = state.models[state.provider];
    if (state.provider === "codex") $("api-key").value = "";
    updateRuntime();
  });
  $("model").addEventListener("input", () => {
    state.models[state.provider] = $("model").value;
    state.modelEdited[state.provider] = true;
  });
  $("research-form").addEventListener("submit", (event) => { event.preventDefault(); runResearch("live"); });
  $("research-form").addEventListener("invalid", (event) => { const details = event.target.closest("details"); if (details) details.open = true; }, true);
  $("demo-button").addEventListener("click", () => runResearch("demo"));
  $("history-toggle").addEventListener("click", () => {
    const panel = $("history-panel"); panel.hidden = !panel.hidden;
    $("history-toggle").setAttribute("aria-expanded", String(!panel.hidden));
    if (!panel.hidden) panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  });
  $("history-refresh").addEventListener("click", loadHistory);
  window.addEventListener("pagehide", () => { $("api-key").value = ""; window.clearInterval(state.timer); });
  Promise.allSettled([loadConfig(), loadHistory()]);
})();
