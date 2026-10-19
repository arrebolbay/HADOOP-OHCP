/* global fetch */
"use strict";

const EXAMPLES = [
  { tag: "示例 1", icon: "📈", title: "TOP5 城市年均浓度",
    text: "找出2024年PM2.5年均浓度最高的5个城市，画出月度变化曲线" },
  { tag: "示例 2", icon: "🥧", title: "省份超标占比",
    text: "筛选PM2.5超标记录，统计各省份超标天数占比" },
  { tag: "示例 3", icon: "☀️", title: "夏季臭氧超标",
    text: "统计北京市夏季臭氧O3超标总天数" },
  { tag: "追问", icon: "🧠", title: "多轮记忆",
    text: "再看这几个城市的PM10超标情况" },
  { tag: "告警", icon: "⚡", title: "突变检测",
    text: "检测北京市PM2.5异常突变，标记污染突发时段" },
  { tag: "专业版", icon: "📊", title: "专业统计模板",
    text: "统计北京市冬季PM2.5超标天数（专业版）" },
];

const state = { busy: false, hasChat: false };

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

function esc(text) {
  return String(text == null ? "" : text)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function fmt(n) {
  if (n == null || Number.isNaN(Number(n))) return "—";
  return Number(n).toLocaleString("zh-CN");
}

function setPill(el, text, cls) {
  el.textContent = text;
  el.className = "pill" + (cls ? " " + cls : "");
}

/* ------------------------- 初始化 ------------------------- */
document.addEventListener("DOMContentLoaded", () => {
  renderExamples();
  bindEvents();
  loadHealth();
  loadOverview();
});

function bindEvents() {
  $("#composer").addEventListener("submit", (event) => {
    event.preventDefault();
    ask();
  });
  $("#question").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      ask();
    }
  });
  $("#resetBtn").addEventListener("click", resetMemory);
  $("#aboutBtn").addEventListener("click", openAbout);
  $("#aboutClose").addEventListener("click", closeAbout);
  $("#aboutModal").addEventListener("click", (event) => {
    if (event.target.dataset.close || event.target.id === "aboutModal") closeAbout();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeAbout();
  });
}

function openAbout() {
  const modal = $("#aboutModal");
  modal.classList.add("open");
  modal.setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";
}

function closeAbout() {
  const modal = $("#aboutModal");
  modal.classList.remove("open");
  modal.setAttribute("aria-hidden", "true");
  document.body.style.overflow = "";
}

function renderExamples() {
  const sidebar = $("#examples");
  sidebar.innerHTML = EXAMPLES.map((item) => `
    <button class="example" type="button" data-question="${esc(item.text)}">
      <span class="tag">${esc(item.tag)}</span>${esc(item.title)}
    </button>`).join("");
  sidebar.querySelectorAll(".example").forEach((btn) => {
    btn.addEventListener("click", () => {
      $("#question").value = btn.dataset.question;
      ask();
    });
  });

  const cards = EXAMPLES.slice(0, 3);
  $("#welcomeCards").innerHTML = cards.map((item) => `
    <div class="welcome-card" data-question="${esc(item.text)}">
      <div class="icon">${item.icon}</div>
      <h4>${esc(item.title)}</h4>
      <p>${esc(item.text)}</p>
    </div>`).join("");
  $$(".welcome-card").forEach((card) => {
    card.addEventListener("click", () => {
      $("#question").value = card.dataset.question;
      ask();
    });
  });
}

/* ------------------------- 概览 / 状态 ------------------------- */
async function loadHealth() {
  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    const dataPill = $("#pill-data");
    if (data.data.available) {
      setPill(dataPill, `数据 ${data.data.chunks} 个分片`, "ok");
    } else {
      setPill(dataPill, "数据未就绪", "bad");
    }
    const mysqlPill = $("#pill-mysql");
    if (data.mysql.connected) {
      setPill(mysqlPill, `MySQL ${fmt(data.mysql.fact_rows)} 行`, "ok");
    } else {
      setPill(mysqlPill, "MySQL 未连接", "warn");
    }
    const plannerPill = $("#pill-planner");
    const label = data.planner_mode === "rule" ? "规则规划器"
      : (data.llm_ready ? "双模 · LLM 就绪" : "双模 · 规则兜底");
    setPill(plannerPill, label, data.llm_ready ? "ok" : "warn");
  } catch (err) {
    setPill($("#pill-data"), "服务未连接", "bad");
  }
}

async function loadOverview() {
  try {
    const res = await fetch("/api/overview");
    const data = await res.json();
    if (!data.available) {
      $("#stats").innerHTML = `<div class="stat"><span class="stat-value">—</span><span class="stat-label">${esc(data.message || "数据未就绪")}</span></div>`;
      return;
    }
    const s = data.stats;
    $("#datasetYear").textContent = s.year;
    $("#stats").innerHTML = [
      ["数据行数", fmt(s.rows)],
      ["城市 / 省份", `${fmt(s.cities)} / ${fmt(s.provinces)}`],
      ["按月分片", fmt(s.chunks)],
      ["时间范围", `${s.date_min} ~ ${s.date_max}`],
    ].map(([label, value]) => `
      <div class="stat"><span class="stat-value">${esc(value)}</span>
      <span class="stat-label">${esc(label)}</span></div>`).join("");

    $("#topCities").innerHTML = data.top_cities.map((row) => `
      <li class="${row.exceeded ? "exceed" : ""}">
        <b>${esc(row.city)}</b><span>${row.value} μg/m³</span></li>`).join("");

    const maxDays = Math.max(...data.province_top.map((p) => p.exceed_days), 1);
    $("#provinceTop").innerHTML = data.province_top.map((p) => `
      <div class="province-row">
        <span>${esc(p.province)}</span>
        <span class="bar"><i style="width:${Math.max(4, p.exceed_days / maxDays * 100)}%"></i></span>
        <span class="val">${fmt(p.exceed_days)}</span>
      </div>`).join("");

    const c = data.cleaning || {};
    const tests = data.tests || {};
    $("#miniMetrics").innerHTML = [
      ["清洗填充", fmt(c.filled)],
      ["超标城市-天", fmt(data.total_exceed_days)],
      ["自动化测试", tests.available ? `${fmt(tests.ran)} 项${tests.passed ? " 全过" : ""}` : "未运行"],
      ["数据来源", "真实监测"],
    ].map(([label, value]) => `<div><b>${esc(value)}</b>${esc(label)}</div>`).join("");
  } catch (err) {
    console.warn(err);
  }
}

/* ------------------------- 提问 ------------------------- */
let WELCOME_HTML = "";

async function ask() {
  const input = $("#question");
  const question = input.value.trim();
  if (!question || state.busy) return;

  if (!WELCOME_HTML) WELCOME_HTML = $("#welcome") ? $("#welcome").outerHTML : "";
  const welcome = $("#welcome");
  if (welcome) welcome.remove();

  state.busy = true;
  setBusy(true);
  addUser(question);
  input.value = "";
  const loading = addLoading();

  const mode = (document.querySelector('input[name="planner"]:checked') || {}).value || "auto";
  try {
    const res = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, planner: mode }),
    });
    const data = await res.json();
    loading.remove();
    if (!res.ok || data.error) {
      addError(data.error || `请求失败（HTTP ${res.status}）`);
      return;
    }
    addAssistant(data);
    state.hasChat = true;
  } catch (err) {
    loading.remove();
    addError("网络错误：" + err.message);
  } finally {
    state.busy = false;
    setBusy(false);
    scrollBottom();
  }
}

function setBusy(busy) {
  const btn = $("#sendBtn");
  btn.disabled = busy;
  btn.querySelector(".btn-label").textContent = busy ? "分析中…" : "开始分析";
  $("#question").disabled = busy;
}

function addUser(text) {
  const div = document.createElement("div");
  div.className = "msg user";
  div.innerHTML = `<div class="bubble">${esc(text)}</div>`;
  $("#messages").appendChild(div);
  scrollBottom();
}

function addLoading() {
  const div = document.createElement("div");
  div.className = "msg assistant";
  div.innerHTML = `<div class="panel"><div class="loading">
    <span class="dots"><i></i><i></i><i></i></span>
    Agent 正在规划任务并调度本地工具（读取 → 清洗 → 聚合 → 判定 → 绘图 → 校验）…
  </div></div>`;
  $("#messages").appendChild(div);
  scrollBottom();
  return div;
}

function addError(message) {
  const div = document.createElement("div");
  div.className = "msg assistant";
  div.innerHTML = `<div class="panel"><div class="loading" style="color:#b91c1c">
    ⚠ ${esc(message)}</div></div>`;
  $("#messages").appendChild(div);
  scrollBottom();
}

function scrollBottom() {
  const box = $("#messages");
  box.scrollTop = box.scrollHeight;
}

/* ------------------------- 渲染回答 ------------------------- */
function parseAnswer(text) {
  const sections = [];
  let current = { title: "分析结论", lines: [] };
  String(text || "").split(/\r?\n/).forEach((raw) => {
    const line = raw.trim();
    if (!line) return;
    const match = line.match(/^【(.+?)】\s*(.*)$/);
    if (match) {
      if (current.lines.length) sections.push(current);
      current = { title: match[1], lines: match[2] ? [match[2]] : [] };
    } else {
      current.lines.push(line);
    }
  });
  if (current.lines.length) sections.push(current);
  return sections;
}

function renderSection(section) {
  const lines = section.lines.map((line) => {
    const numbered = line.match(/^(\d+)\.\s*(.*)$/);
    if (numbered) {
      return `<div class="line item"><span class="idx">${numbered[1]}.</span>
        <span>${esc(numbered[2])}</span></div>`;
    }
    const bullet = line.match(/^[-•]\s+(.*)$/);
    if (bullet) {
      return `<div class="line item"><span class="idx">•</span>
        <span>${esc(bullet[1])}</span></div>`;
    }
    let cls = "line";
    if (section.title.includes("感悟")) cls += " eco";
    else if (section.title.includes("数据来源")) cls += " muted-line";
    else if (line.includes("超标")) cls += " warn";
    return `<div class="${cls}">${esc(line)}</div>`;
  }).join("");
  return `<section class="answer-section"><h3>${esc(section.title)}</h3>
    <div class="lines">${lines}</div></section>`;
}

function renderTrace(trace, elapsed) {
  if (!trace || !trace.length) return "";
  const items = trace.map((item) => {
    const args = item.args && Object.keys(item.args).length
      ? `<span class="trace-time">${esc(JSON.stringify(item.args))}</span>` : "";
    return `<div class="trace-item ${item.ok ? "" : "fail"}">
      <div class="trace-index">${item.step}</div>
      <div class="trace-main">
        <div class="trace-action"><code>${esc(item.action)}</code>${args}
          <span class="trace-time">${item.elapsed_s}s</span></div>
        <div class="trace-thought">Thought：${esc(item.thought || "—")}</div>
        <div class="trace-obs">${esc(item.observation)}</div>
      </div></div>`;
  }).join("");
  return `<details class="trace">
    <summary>ReAct 决策轨迹 · ${trace.length} 个工具步骤 · ${elapsed || "—"}s</summary>
    <div class="trace-body">${items}</div></details>`;
}

function renderCharts(charts) {
  if (!charts || !charts.length) return "";
  const cards = charts.map((chart) => `
    <div class="chart-card">
      <a href="${esc(chart.url)}" target="_blank" rel="noopener">
        <img src="${esc(chart.url)}" alt="${esc(chart.title)}" loading="lazy">
      </a>
      <div class="caption"><span>${esc(chart.title)}</span><span>点击查看原图</span></div>
    </div>`).join("");
  return `<section class="answer-section"><h3>图表输出</h3>
    <div class="charts">${cards}</div></section>`;
}

function renderValidation(validation) {
  if (!validation) return "";
  const checks = (validation.checks || []).map((check) => `
    <span class="check ${check.passed ? "" : "bad"}" title="${esc(check.detail)}">
      ${check.passed ? "✓" : "✗"} ${esc(check.name)}</span>`).join("");
  return `<div class="validation">${checks}</div>`;
}

function addAssistant(data) {
  const wrap = document.createElement("div");
  wrap.className = "msg assistant";

  const validation = data.validation;
  const validChip = validation
    ? `<span class="meta-chip ${validation.passed === validation.total ? "ok" : "bad"}">
         校验 ${validation.passed}/${validation.total}</span>` : "";
  const sections = parseAnswer(data.answer)
    .filter((section) => section.title !== "图表输出")
    .map(renderSection).join("");
  const cities = (data.slots && data.slots.cities)
    || (data.memory && data.memory.last_cities) || [];
  const memoryChip = cities.length
    ? `<span class="meta-chip">记忆：${esc(cities.slice(0, 5).join("、"))}</span>` : "";

  wrap.innerHTML = `<div class="panel">
    <div class="assistant-head">
      <span class="who"><span class="avatar">AQ</span>空气质量分析 Agent</span>
      <span class="meta-chip">${esc(data.planner || "auto")}</span>
      <span class="meta-chip">${esc(data.intent || "分析")}</span>
      <span class="meta-chip">${data.elapsed_s || 0}s · ${(data.trace || []).length} 步</span>
      ${validChip}${memoryChip}
    </div>
    ${sections}
    ${renderCharts(data.charts)}
    ${renderValidation(validation)}
    ${renderTrace(data.trace, data.elapsed_s)}
  </div>`;
  $("#messages").appendChild(wrap);
  scrollBottom();
}

/* ------------------------- 重置记忆 ------------------------- */
async function resetMemory() {
  try {
    await fetch("/api/reset", { method: "POST" });
    $("#messages").innerHTML = WELCOME_HTML || "";
    $$(".welcome-card").forEach((card) => {
      card.addEventListener("click", () => {
        $("#question").value = card.dataset.question;
        ask();
      });
    });
    state.hasChat = false;
    addToast("多轮记忆已清空");
  } catch (err) {
    addToast("重置失败：" + err.message);
  }
}

function addToast(message) {
  const toast = document.createElement("div");
  toast.textContent = message;
  toast.style.cssText = "position:fixed;left:50%;bottom:28px;transform:translateX(-50%);" +
    "background:#0f172a;color:#fff;padding:9px 16px;border-radius:999px;font-size:12px;" +
    "z-index:99;box-shadow:0 10px 24px rgba(15,23,42,.25);opacity:0;transition:.2s";
  document.body.appendChild(toast);
  requestAnimationFrame(() => { toast.style.opacity = "1"; });
  setTimeout(() => {
    toast.style.opacity = "0";
    setTimeout(() => toast.remove(), 220);
  }, 1800);
}

