const records = [
  {
    id: "exp-001",
    name: "刘言溪",
    graduationYear: "2024",
    entryGrade: "2020",
    education: "本科",
    college: "信息工程学院",
    major: "软件工程",
    majorFamily: "计算机类",
    region: "四川省",
    city: "成都市",
    organization: "双流区人民政府",
    position: "乡镇综合管理岗",
    sourceTitle: "从软件工程到基层一线：我的四川选调经验",
    sourceDate: "2024-05-18",
    articleType: "海报帖",
    reviewStatus: "已核验",
    posterTone: "poster-indigo",
    evidence: [
      { field: "专业", text: "2020级软件工程专业，本科毕业。", method: "OCR 片段 · 置信度 0.96" },
      { field: "地区 / 单位", text: "现就职于成都市双流区人民政府，参与基层工作。", method: "原文片段 · 置信度 0.93" },
      { field: "届别", text: "2024届毕业生经验分享。", method: "文章元数据 · 置信度 0.99" }
    ],
    tags: ["本科", "软件工程", "四川省", "基层"],
    reasons: ["专业族匹配", "地区匹配", "基层意图匹配"]
  },
  {
    id: "exp-002",
    name: "周嘉禾",
    graduationYear: "2023",
    entryGrade: "2020",
    education: "硕士",
    college: "计算机学院",
    major: "计算机科学与技术",
    majorFamily: "计算机类",
    region: "重庆市",
    city: "重庆市",
    organization: "重庆市某市级部门",
    position: "综合管理岗",
    sourceTitle: "在城市与基层之间：计算机硕士的选调选择",
    sourceDate: "2023-11-06",
    articleType: "文本帖",
    reviewStatus: "已核验",
    posterTone: "poster-terracotta",
    evidence: [
      { field: "学历 / 专业", text: "计算机学院，计算机科学与技术专业硕士。", method: "正文片段 · 置信度 0.98" },
      { field: "地区 / 单位", text: "毕业后进入重庆市某市级部门工作。", method: "正文片段 · 置信度 0.94" },
      { field: "岗位", text: "岗位名称记录为综合管理岗。", method: "人工复核 · 置信度 0.91" }
    ],
    tags: ["硕士", "计算机类", "重庆市", "综合管理"],
    reasons: ["专业族匹配", "学历匹配", "单位信息匹配"]
  },
  {
    id: "exp-003",
    name: "赵清妍",
    graduationYear: "2024",
    entryGrade: "2020",
    education: "本科",
    college: "公共管理学院",
    major: "信息管理",
    majorFamily: "信息管理类",
    region: "陕西省",
    city: "汉中市",
    organization: "汉中市某县单位",
    position: "",
    sourceTitle: "把专业带到县域：一名信息管理学生的选调记录",
    sourceDate: "2024-06-22",
    articleType: "海报帖",
    reviewStatus: "待复核",
    posterTone: "poster-sage",
    evidence: [
      { field: "专业", text: "公共管理学院信息管理专业，本科背景。", method: "OCR 片段 · 置信度 0.88" },
      { field: "地区 / 单位", text: "工作地点为陕西省汉中市，任职单位为某县单位。", method: "OCR 片段 · 置信度 0.84" },
      { field: "岗位", text: "原始海报未明确写出岗位名称。", method: "缺失声明 · 不做常识补全" }
    ],
    tags: ["本科", "信息管理", "陕西省", "县域基层"],
    reasons: ["学历匹配", "地区语义匹配", "基层意图匹配"]
  }
];

const westRegions = ["四川省", "重庆市", "陕西省"];
const state = {
  view: "home",
  mode: "ai",
  query: "",
  role: "guest",
  aiAvailable: true,
  noTrace: false,
  compare: new Set(),
  filters: { year: "", education: "", region: "" },
  currentResults: [...records],
  currentPlan: [],
  detailId: null
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
}

function displayName(record) {
  return state.role === "guest" ? "匿名校友" : record.name;
}

function posterMarkup(record, large = false) {
  const masked = state.role === "guest";
  return `<div class="${large ? "poster-large" : "poster-thumb"} ${record.posterTone}">
    <div class="poster-grid"></div><span class="poster-kicker">选调经验分享 / 2024</span>
    <strong>${masked ? "匿名校友" : escapeHtml(record.name)}</strong>
    <small>${masked ? "游客视图 · 敏感信息已脱敏" : `${escapeHtml(record.college)} · ${escapeHtml(record.major)}`}</small>
    <span class="poster-shape"></span>${masked ? `<span class="poster-redact ${large ? "large" : ""}"></span><span class="poster-redact ${large ? "large" : ""} second"></span>` : ""}
  </div>`;
}

function setView(view) {
  state.view = view;
  if (view === "home") {
    state.filters = { year: "", education: "", region: "" };
    ["#resultsYearFilter", "#resultsEducationFilter", "#resultsRegionFilter"].forEach((selector) => { $(selector).value = ""; });
    ["#homeYearFilter", "#homeEducationFilter", "#homeRegionFilter"].forEach((selector) => { $(selector).value = ""; });
  }
  $$(".view").forEach((item) => item.classList.toggle("active", item.id === `${view}View`));
  $$(".nav-link").forEach((item) => item.classList.toggle("is-active", item.dataset.action === view || (view === "home" && item.dataset.action === "home")));
  window.scrollTo({ top: 0, behavior: "smooth" });
  if (view === "compare") renderCompare();
  if (view === "space") renderSpace();
}

function normalizeQuery(value) {
  return value.trim().replace(/[，。！？、；：|/]+/g, " ").replace(/\s+/g, " ");
}

function parseQuery(query) {
  const normalized = normalizeQuery(query);
  const plan = [];
  if (!normalized) return [{ label: "最新发布", type: "condition", value: "" }, { label: "已核验优先", type: "condition", value: "" }];
  if (/本科/.test(normalized)) plan.push({ label: "学历：本科", type: "condition", value: "本科", key: "education" });
  if (/硕士/.test(normalized)) plan.push({ label: "学历：硕士", type: "condition", value: "硕士", key: "education" });
  if (/博士/.test(normalized)) plan.push({ label: "学历：博士", type: "condition", value: "博士", key: "education" });
  const yearMatch = normalized.match(/20\d{2}/);
  if (yearMatch) plan.push({ label: `届别：${yearMatch[0]}`, type: "condition", value: yearMatch[0], key: "year" });
  if (/计算机|软件工程/.test(normalized)) plan.push({ label: "专业族：计算机类", type: "condition", value: "计算机类", key: "majorFamily" });
  if (/信息管理/.test(normalized)) plan.push({ label: "专业：信息管理", type: "condition", value: "信息管理", key: "major" });
  const region = ["四川省", "重庆市", "陕西省"].find((item) => normalized.includes(item) || normalized.includes(item.slice(0, 2)));
  if (region) plan.push({ label: `地区：${region.replace("省", "").replace("市", "")}`, type: "condition", value: region, key: "region" });
  if (/西部/.test(normalized)) plan.push({ label: "地区：西部地区", type: "condition", value: "西部地区", key: "west" });
  if (/基层|乡镇|街道|县域|县区/.test(normalized)) plan.push({ label: "意图：基层党政机关", type: "intent", value: "基层" });
  if (!plan.some((item) => item.key === "majorFamily" || item.key === "major") && /专业/.test(normalized)) plan.push({ label: "补充关键词：专业", type: "condition", value: "专业" });
  if (!plan.length) plan.push({ label: `关键词：${normalized.slice(0, 12)}`, type: "condition", value: normalized });
  return plan;
}

function getSearchTerms(query) {
  const normalized = normalizeQuery(query).toLowerCase();
  const known = ["软件工程", "计算机科学与技术", "计算机", "信息管理", "四川", "重庆", "陕西", "西部", "基层", "乡镇", "县域", "综合管理", "本科", "硕士", "博士", "选调"];
  const matched = known.filter((term) => normalized.includes(term.toLowerCase()));
  const loose = normalized.split(" ").filter((term) => term.length > 1 && !matched.some((knownTerm) => knownTerm.includes(term)));
  return [...new Set([...matched, ...loose])];
}

function matchesStructured(record) {
  if (state.filters.year && record.graduationYear !== state.filters.year) return false;
  if (state.filters.education && record.education !== state.filters.education) return false;
  if (state.filters.region && record.region !== state.filters.region) return false;
  return true;
}

function matchesPlan(record, plan) {
  return plan.every((item) => {
    if (item.key === "education" && record.education !== item.value) return false;
    if (item.key === "year" && record.graduationYear !== item.value) return false;
    if (item.key === "region" && record.region !== item.value) return false;
    if (item.key === "west" && !westRegions.includes(record.region)) return false;
    return true;
  });
}

function scoreRecord(record, query, plan) {
  const text = [record.name, record.education, record.college, record.major, record.majorFamily, record.region, record.city, record.organization, record.position, record.sourceTitle, record.articleType, ...record.tags].join(" ").toLowerCase();
  if (!matchesStructured(record) || !matchesPlan(record, plan)) return -1;
  let score = query ? 0 : 1;
  const terms = getSearchTerms(query);
  terms.forEach((term) => {
    if (text.includes(term.toLowerCase())) score += 2;
    if (record.majorFamily === "计算机类" && ["计算机", "软件工程"].includes(term)) score += 1;
    if (term === "西部" && westRegions.includes(record.region)) score += 2;
    if (["基层", "乡镇", "县域"].includes(term) && /基层|乡镇|县/.test(`${record.organization}${record.position}${record.tags.join("")}`)) score += 2;
  });
  plan.forEach((item) => {
    if (item.key === "education" && record.education === item.value) score += 2;
    if (item.key === "year" && record.graduationYear === item.value) score += 2;
    if (item.key === "region" && record.region === item.value) score += 2;
    if (item.key === "west" && westRegions.includes(record.region)) score += 2;
    if (item.key === "majorFamily" && record.majorFamily === item.value) score += 2;
    if (item.key === "major" && record.major === item.value) score += 2;
    if (item.value === "基层" && /基层|乡镇|县/.test(`${record.organization}${record.position}${record.tags.join("")}`)) score += 2;
  });
  return query && score === 0 ? -1 : score;
}

function runSearch(query = $("#homeSearchInput").value) {
  state.query = normalizeQuery(query);
  state.currentPlan = parseQuery(state.query);
  const ranked = records.map((record) => ({ record, score: scoreRecord(record, state.query, state.currentPlan) })).filter((item) => item.score >= 0).sort((a, b) => b.score - a.score || Number(b.record.graduationYear) - Number(a.record.graduationYear));
  state.currentResults = ranked.map((item) => item.record);
  setView("results");
  renderResults();
}

function renderPlan() {
  $("#queryPlanChips").innerHTML = state.currentPlan.map((item) => `<span class="plan-chip ${item.type === "intent" ? "intent" : ""}">${escapeHtml(item.label)}${item.value ? `<em>×</em>` : ""}</span>`).join("");
}

function answerText() {
  const result = state.currentResults;
  if (!result.length) return "当前资料库未找到足够信息，下面保留了你的查询条件，建议放宽一个筛选项后继续。";
  const undergraduate = result.filter((record) => record.education === "本科").length;
  const master = result.filter((record) => record.education === "硕士").length;
  const regions = [...new Set(result.map((record) => record.region.replace("省", "").replace("市", "")))];
  const missingPosition = result.filter((record) => !record.position).length;
  const educationText = [undergraduate ? `本科 ${undergraduate} 条` : "", master ? `硕士 ${master} 条` : ""].filter(Boolean).join("、");
  return `当前快照中找到 <b>${result.length} 条</b>相关记录，${educationText || "学历信息已整理"}；结果覆盖 ${regions.join("、")}。${missingPosition ? `其中 ${missingPosition} 条来源未明确岗位名称，系统保留为“未提供”，没有根据常识补全。` : "岗位字段均有来源片段可以核验。"}`;
}

function renderAnswer() {
  const panel = $("#aiAnswerPanel");
  const degraded = $("#degradedBanner");
  if (state.mode === "ai" && state.aiAvailable) {
    panel.hidden = false;
    panel.innerHTML = `<div class="answer-head"><span class="answer-label"><span>✦</span>Evidence-RAG 摘要</span><span class="answer-confidence">基于 ${state.currentResults.length} 条证据</span></div><p class="answer-copy">${answerText()}</p><div class="evidence-links"><span>可核验来源</span>${state.currentResults.slice(0, 3).map((record, index) => `<button class="evidence-link" data-action="open-detail" data-id="${record.id}">E${index + 1} · ${escapeHtml(record.region.replace("省", "").replace("市", ""))}案例</button>`).join("")}</div>`;
    degraded.hidden = true;
  } else if (state.mode === "ai" && !state.aiAvailable) {
    panel.hidden = true;
    degraded.hidden = false;
  } else {
    panel.hidden = true;
    degraded.hidden = true;
  }
}

function renderResults() {
  renderPlan();
  renderAnswer();
  $("#resultCount").textContent = state.currentResults.length;
  $("#distributionCount").textContent = state.currentResults.length;
  $("#traceLabel").hidden = !state.noTrace;
  $("#searchDescriptor").textContent = state.query ? `“${state.query}” · 已发布快照 · 按相关度排序` : "已发布快照 · 最新记录优先";
  const list = $("#resultsList");
  $("#emptyResults").hidden = Boolean(state.currentResults.length);
  list.innerHTML = state.currentResults.map((record) => {
    const added = state.compare.has(record.id);
    const statusClass = record.reviewStatus === "待复核" ? "review" : "";
    return `<article class="result-card"><div>${posterMarkup(record)}</div><div class="result-body"><div class="result-topline"><strong>${escapeHtml(displayName(record))}</strong><span>·</span><span>${record.graduationYear} 届</span></div><span class="result-title">${escapeHtml(record.sourceTitle)}</span><p class="result-subline">${escapeHtml(record.region)} ${escapeHtml(record.city)} · ${escapeHtml(record.organization)}</p><div class="result-tags">${record.tags.slice(0, 4).map((tag, index) => `<span class="record-tag ${index < 2 ? "accent" : ""}">${escapeHtml(tag)}</span>`).join("")}</div><div class="match-reasons">${record.reasons.map((reason) => `<span>${escapeHtml(reason)}</span>`).join("")}</div></div><div class="result-actions"><span class="status-badge ${statusClass}"><i></i>${escapeHtml(record.reviewStatus)}</span><div class="result-action-buttons"><button class="compare-button ${added ? "is-added" : ""}" data-action="toggle-compare" data-id="${record.id}">${added ? "已加入" : "+ 对比"}</button><button class="detail-button" data-action="open-detail" data-id="${record.id}">详情 →</button></div></div></article>`;
  }).join("");
  renderBars();
  updateCompareCount();
}

function renderBars() {
  const buildBars = (values, target) => {
    const max = Math.max(...values.map((item) => item.count), 1);
    $(target).innerHTML = values.length ? values.map((item) => `<div class="bar-item"><span>${escapeHtml(item.label)}</span><div class="bar-track"><div class="bar-fill" style="width:${Math.round(item.count / max * 100)}%"></div></div><b>${item.count}</b></div>`).join("") : `<span class="muted-text">暂无分布数据</span>`;
  };
  const regionGroups = {};
  state.currentResults.forEach((record) => {
    const label = record.region.replace("省", "").replace("市", "");
    regionGroups[label] = (regionGroups[label] || 0) + 1;
  });
  const regions = Object.entries(regionGroups).map(([label, count]) => ({ label, count }));
  const regionFallback = ["四川", "重庆", "陕西"].map((label) => ({ label, count: state.currentResults.filter((r) => r.region.startsWith(label)).length })).filter((item) => item.count);
  const education = ["本科", "硕士", "博士"].map((label) => ({ label, count: state.currentResults.filter((r) => r.education === label).length })).filter((item) => item.count);
  buildBars(regions.length ? regions : regionFallback, "#regionBars");
  buildBars(education, "#educationBars");
}

function updateCompareCount() {
  const count = state.compare.size;
  $("#compareCount").textContent = count;
  $("#resultsCompareCount").textContent = count;
}

function toggleCompare(id) {
  if (state.compare.has(id)) state.compare.delete(id);
  else if (state.compare.size >= 4) return showToast("对比台最多放入 4 条记录");
  else state.compare.add(id);
  updateCompareCount();
  if (state.view === "results") renderResults();
  showToast(state.compare.has(id) ? "已加入对比台" : "已从对比台移除");
}

function renderCompare() {
  const selected = records.filter((record) => state.compare.has(record.id));
  const container = $("#compareContent");
  if (selected.length < 2) {
    container.innerHTML = `<div class="compare-empty"><div class="compare-empty-icon">⊞</div><h3>${selected.length ? "再选一条，就可以开始比较" : "对比台还是空的"}</h3><p>先在结果卡片上点击“+ 对比”，把你关心的案例放进同一张表。</p><div class="suggested-records">${records.map((record) => `<button class="suggested-record" data-action="toggle-compare-and-stay" data-id="${record.id}">${state.compare.has(record.id) ? "✓ " : "+ "}${escapeHtml(displayName(record))} · ${escapeHtml(record.region)}</button>`).join("")}</div></div>`;
    return;
  }
  const fieldRows = [
    ["案例", ...selected.map((record) => `${displayName(record)} · ${record.graduationYear}届`)],
    ["学历", ...selected.map((record) => record.education || "未提供")],
    ["学院", ...selected.map((record) => record.college || "未提供")],
    ["专业", ...selected.map((record) => record.major || "未提供")],
    ["地区", ...selected.map((record) => `${record.region} ${record.city}`)],
    ["单位", ...selected.map((record) => record.organization || "未提供")],
    ["岗位", ...selected.map((record) => record.position || "未提供")],
    ["来源状态", ...selected.map((record) => record.reviewStatus)]
  ];
  const headers = fieldRows[0].slice(1).map((label, index) => `<th>${escapeHtml(label)}<small>${escapeHtml(selected[index].major)}</small></th>`).join("");
  const body = fieldRows.slice(1).map((row) => `<tr><th>${escapeHtml(row[0])}</th>${row.slice(1).map((value) => `<td class="${value === "未提供" ? "missing" : ""}">${escapeHtml(value)}</td>`).join("")}</tr>`).join("");
  const regions = [...new Set(selected.map((record) => record.region))].map((region) => region.replace("省", "").replace("市", "")).join("、");
  container.innerHTML = `<div class="compare-summary"><div class="compare-summary-card"><span>已选案例</span><b>${selected.length} 条</b></div><div class="compare-summary-card"><span>覆盖地区</span><b>${[...new Set(selected.map((record) => record.region))].length} 个</b></div><div class="compare-summary-card"><span>资料完整度</span><b>${Math.round(selected.reduce((total, record) => total + (record.position ? 1 : .78), 0) / selected.length * 100)}%</b></div></div><div class="compare-table-wrap"><table class="compare-table"><thead><tr><th>字段</th>${headers}</tr></thead><tbody>${body}</tbody></table></div><div class="compare-insight"><b>✦ 基于当前表格事实的差异摘要</b><p>这 ${selected.length} 条记录覆盖 ${escapeHtml(regions)}，学历包含 ${[...new Set(selected.map((record) => record.education))].join("、")}。${selected.some((record) => !record.position) ? "其中有记录未公开岗位名称，已明确标注为“未提供”；其余差异可点击详情回到字段级证据。" : "每条记录都提供了岗位字段，可继续按地区和单位类型比较。"}</p></div>`;
}

function renderSpace() {
  $("#spaceRoleNote").textContent = state.role === "guest" ? "游客预览空间" : state.role === "admin" ? "管理员空间" : "校内用户空间";
  $("#spaceNoTraceSwitch").className = state.noTrace ? "switch-off" : "switch-on";
}

function openDetail(id) {
  const record = records.find((item) => item.id === id);
  if (!record) return;
  state.detailId = id;
  const fields = [["姓名", displayName(record), state.role === "guest" ? "游客视图已脱敏" : "授权范围内可见"], ["届别", `${record.graduationYear} 届`], ["学历", record.education], ["学院", record.college], ["专业", record.major], ["地区", `${record.region} ${record.city}`], ["单位", record.organization], ["岗位", record.position || "未提供", record.position ? "来源明确" : "原文未提供，不做补全"], ["发布时间", record.sourceDate]];
  $("#detailContent").innerHTML = `<div class="detail-main-title"><div><h2 id="detailTitle">${escapeHtml(displayName(record))} · ${escapeHtml(record.graduationYear)}届</h2><p>${escapeHtml(record.sourceTitle)}</p></div><span class="status-badge ${record.reviewStatus === "待复核" ? "review" : ""}"><i></i>${escapeHtml(record.reviewStatus)}</span></div><div class="detail-grid"><div><div class="detail-section-label">STRUCTURED FIELDS</div><div class="detail-fields">${fields.map(([label, value, note]) => `<div class="detail-field"><span>${escapeHtml(label)}</span><b class="${value === "未提供" ? "missing" : ""}">${escapeHtml(value)}</b>${note ? `<small>${escapeHtml(note)}</small>` : ""}</div>`).join("")}</div><div class="evidence-section"><div class="detail-section-label">FIELD EVIDENCE</div><div class="evidence-list">${record.evidence.map((item, index) => `<div class="evidence-item"><b>E${index + 1} · ${escapeHtml(item.field)}</b><p>“${escapeHtml(item.text)}”</p><small>${escapeHtml(item.method)}</small></div>`).join("")}</div></div></div><div><div class="detail-poster-wrap">${posterMarkup(record, true)}<div class="poster-note"><span>ⓘ</span><span>${state.role === "guest" ? "当前为游客视图：海报为服务端脱敏派生图的视觉模拟，姓名与敏感区域不可见。" : "当前为校内授权视图：可查看完整海报素材。"}</span></div></div><div class="detail-source"><small>来源 · ${escapeHtml(record.articleType)} · ${escapeHtml(record.sourceDate)}</small><a href="https://www.example.com" target="_blank" rel="noreferrer">查看学校门户原文 ↗</a></div><div class="detail-footer-actions"><button data-action="toast" data-message="已收藏（演示模式）">☆ 收藏</button><button data-action="toast" data-message="分享链接已复制（演示模式）">↗ 分享</button><button class="primary-action" data-action="toggle-compare" data-id="${record.id}">${state.compare.has(record.id) ? "✓ 已在对比" : "+ 加入对比"}</button></div></div></div>`;
  toggleModal("detailModal", true);
}

function openPlanEditor() {
  $("#planEditor").innerHTML = state.currentPlan.map((item, index) => `<span class="editable-plan-chip" data-plan-index="${index}">${escapeHtml(item.label)}<button data-action="remove-plan" data-index="${index}" aria-label="删除条件">×</button></span>`).join("");
  toggleModal("planModal", true);
}

function toggleModal(id, open) {
  const modal = $(`#${id}`);
  modal.classList.toggle("is-open", open);
  modal.setAttribute("aria-hidden", String(!open));
}

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("is-visible");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove("is-visible"), 2300);
}

function syncControls() {
  $("#roleButton").innerHTML = `${state.role === "guest" ? "游客" : state.role === "campus" ? "校内用户" : "管理员"} <span>⌄</span>`;
  [$("#aiToggle")].forEach((toggle) => toggle.classList.toggle("is-on", state.aiAvailable));
  [$("#noTraceToggle"), $("#sidebarNoTrace")].forEach((toggle) => toggle.classList.toggle("is-on", state.noTrace));
  $("#aiControlText").textContent = state.aiAvailable ? "可用 · Evidence-RAG" : "已关闭 · 自动降级到传统检索";
  $$(".role-option").forEach((button) => button.classList.toggle("is-active", button.dataset.role === state.role));
}

function toggleAi() {
  state.aiAvailable = !state.aiAvailable;
  syncControls();
  if (state.view === "results") renderResults();
  showToast(state.aiAvailable ? "AI 总结已恢复" : "AI 已关闭，系统将自动降级到传统检索");
}

function toggleNoTrace() {
  state.noTrace = !state.noTrace;
  syncControls();
  renderSpace();
  if (state.view === "results") renderResults();
  showToast(state.noTrace ? "无痕模式已开启：本次不写入个人历史" : "无痕模式已关闭");
}

function clearFilters() {
  state.filters = { year: "", education: "", region: "" };
  ["#resultsYearFilter", "#resultsEducationFilter", "#resultsRegionFilter"].forEach((selector) => { $(selector).value = ""; });
  runSearch(state.query);
}

function exportCurrent() {
  const exportRecords = state.view === "compare" ? records.filter((record) => state.compare.has(record.id)) : state.currentResults;
  const header = ["姓名（演示角色视图）", "届别", "学历", "学院", "专业", "地区", "单位", "岗位", "数据状态", "来源"];
  const rows = exportRecords.map((record) => [displayName(record), `${record.graduationYear}届`, record.education, record.college, record.major, `${record.region} ${record.city}`, record.organization, record.position || "未提供", record.reviewStatus, record.sourceTitle]);
  const csv = [header, ...rows].map((row) => row.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(",")).join("\n");
  const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "选调研-当前检索结果.csv";
  link.click();
  URL.revokeObjectURL(url);
  showToast(`已导出 ${exportRecords.length} 条整理后的结果（CSV）`);
}

document.addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  const action = button.dataset.action;
  if (button.dataset.mode) {
    state.mode = button.dataset.mode;
    $$(".mode-tab").forEach((tab) => { tab.classList.toggle("is-selected", tab.dataset.mode === state.mode); tab.setAttribute("aria-selected", String(tab.dataset.mode === state.mode)); });
    return;
  }
  if (button.dataset.query !== undefined) {
    $("#homeSearchInput").value = button.dataset.query;
    runSearch(button.dataset.query);
    return;
  }
  if (button.dataset.role) {
    state.role = button.dataset.role;
    syncControls();
    if (state.view === "results") renderResults();
    if (state.view === "space") renderSpace();
    if (state.detailId && $("#detailModal").classList.contains("is-open")) openDetail(state.detailId);
    showToast(`已切换为${state.role === "guest" ? "游客" : state.role === "campus" ? "校内用户" : "管理员"}视图`);
    return;
  }
  if (action === "home") { setView("home"); return; }
  if (action === "results") { setView("results"); return; }
  if (action === "compare") { setView("compare"); return; }
  if (action === "space") { setView("space"); return; }
  if (action === "search") { runSearch(); return; }
  if (action === "toggle-home-filters") { $("#homeFilterPanel").hidden = !$("#homeFilterPanel").hidden; return; }
  if (action === "toggle-compare" || action === "toggle-compare-and-stay") { toggleCompare(button.dataset.id); if (action === "toggle-compare-and-stay") renderCompare(); return; }
  if (action === "open-detail") { openDetail(button.dataset.id); return; }
  if (action === "close-detail") { state.detailId = null; toggleModal("detailModal", false); return; }
  if (action === "edit-plan") { openPlanEditor(); return; }
  if (action === "close-plan") { toggleModal("planModal", false); return; }
  if (action === "remove-plan") { state.currentPlan.splice(Number(button.dataset.index), 1); openPlanEditor(); return; }
  if (action === "apply-plan") { toggleModal("planModal", false); showToast("已应用修改后的理解条件"); return; }
  if (action === "open-demo-panel") { $("#demoPanel").classList.add("is-open"); $("#demoPanel").setAttribute("aria-hidden", "false"); return; }
  if (action === "close-demo-panel") { $("#demoPanel").classList.remove("is-open"); $("#demoPanel").setAttribute("aria-hidden", "true"); return; }
  if (action === "toggle-ai") { toggleAi(); return; }
  if (action === "toggle-no-trace") { toggleNoTrace(); return; }
  if (action === "clear-filters") { clearFilters(); return; }
  if (action === "clear-compare") { state.compare.clear(); updateCompareCount(); renderCompare(); showToast("对比台已清空"); return; }
  if (action === "relax-search") { state.filters = { year: "", education: "", region: "" }; $("#homeSearchInput").value = ""; runSearch(""); return; }
  if (action === "export") { exportCurrent(); return; }
  if (action === "toast") { showToast(button.dataset.message || "演示操作已触发"); return; }
});

$("#homeSearchInput").addEventListener("keydown", (event) => { if (event.key === "Enter") runSearch(); });
["#resultsYearFilter", "#resultsEducationFilter", "#resultsRegionFilter"].forEach((selector, index) => $(selector).addEventListener("change", (event) => { state.filters[["year", "education", "region"][index]] = event.target.value; runSearch(state.query); }));
$("#homeYearFilter").addEventListener("change", (event) => { state.filters.year = event.target.value; });
$("#homeEducationFilter").addEventListener("change", (event) => { state.filters.education = event.target.value; });
$("#homeRegionFilter").addEventListener("change", (event) => { state.filters.region = event.target.value; });

document.addEventListener("click", (event) => {
  if (event.target.classList.contains("modal-backdrop")) { event.target.classList.remove("is-open"); event.target.setAttribute("aria-hidden", "true"); }
});

syncControls();
renderSpace();
