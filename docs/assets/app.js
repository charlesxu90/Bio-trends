/* Bio-trend static browser. Vanilla JS, no build step.
   Loads data/manifest.json + data/trends.json, lazy-loads paper shards. */

const DATA = "data/";
const PAGE = 20;

const state = {
  manifest: null,
  trends: [],
  papers: [],        // all paper records, flattened across shards
  group: null,
  period: null,
  shown: PAGE,
};

const $ = (sel) => document.querySelector(sel);
const el = (tag, cls, text) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
};

async function getJSON(path) {
  const resp = await fetch(DATA + path);
  if (!resp.ok) throw new Error(`${path}: ${resp.status}`);
  return resp.json();
}

// ---- init -------------------------------------------------------------------
async function init() {
  try {
    [state.manifest, state.trends] = await Promise.all([
      getJSON("manifest.json"),
      getJSON("trends.json"),
    ]);
  } catch (err) {
    $("#trend-panel").innerHTML = `<p class="loading">Could not load data (${err.message}). Run <code>bio-trend refresh</code> first.</p>`;
    return;
  }
  buildHeroStats();
  buildTrendPicker();
  buildFilters();
  await loadAllPapers();
  renderPapers();
}

// ---- hero -------------------------------------------------------------------
function buildHeroStats() {
  const m = state.manifest;
  const total = m.shards.reduce((s, x) => s + x.count, 0);
  const stats = [
    [m.journals.length, "journals"],
    [total.toLocaleString(), "articles"],
    [m.topics.length, "topics"],
    [m.periods.length, "months"],
  ];
  const box = $("#hero-stats");
  for (const [num, label] of stats) {
    const s = el("div", "stat");
    s.append(el("div", "stat__num", String(num)), el("div", "stat__label", label));
    box.append(s);
  }
}

// ---- trends -----------------------------------------------------------------
function buildTrendPicker() {
  const groups = [...new Set(state.trends.map((t) => t.group))].sort();
  const row = $("#group-pills");
  groups.forEach((g, i) => {
    const pill = el("button", "pill", g);
    pill.type = "button";
    pill.setAttribute("aria-pressed", i === 0 ? "true" : "false");
    pill.addEventListener("click", () => selectGroup(g));
    row.append(pill);
  });
  if (groups.length) selectGroup(groups[0]);
}

function selectGroup(group) {
  state.group = group;
  for (const p of $("#group-pills").children)
    p.setAttribute("aria-pressed", String(p.textContent === group));

  const periods = state.trends
    .filter((t) => t.group === group)
    .map((t) => t.period)
    .sort();
  const row = $("#period-pills");
  row.innerHTML = "";
  periods.forEach((per) => {
    const pill = el("button", "pill", per);
    pill.type = "button";
    pill.addEventListener("click", () => selectPeriod(per));
    row.append(pill);
  });
  if (periods.length) selectPeriod(periods[periods.length - 1]);
}

function selectPeriod(period) {
  state.period = period;
  for (const p of $("#period-pills").children)
    p.setAttribute("aria-pressed", String(p.textContent === period));
  renderTrend();
}

function renderTrend() {
  const t = state.trends.find((x) => x.group === state.group && x.period === state.period);
  const panel = $("#trend-panel");
  panel.innerHTML = "";
  if (!t) return;
  const counts = t.counts || {};
  const max = Math.max(1, ...t.top.map((k) => counts[k] || 0));
  panel.append(
    trendCard("top", "Top topics", t.top, counts, max),
    trendCard("emerging", "Emerging", t.emerging, counts, max),
    trendCard("fading", "Fading", t.fading, counts, max),
  );
}

function trendCard(kind, title, topics, counts, max) {
  const card = el("div", `trend-card trend-card--${kind}`);
  card.append(el("h3", "trend-card__title", title));
  if (!topics.length) {
    card.append(el("p", "trend-empty", "Needs a prior month to compare."));
    return card;
  }
  const list = el("ul", "trend-list");
  for (const topic of topics) {
    const c = counts[topic] || 0;
    const row = el("li", "trend-row");
    const name = el("button", "trend-row__name", topic);
    name.type = "button";
    name.addEventListener("click", () => jumpToTopic(topic));
    const bar = el("span", "trend-row__bar");
    bar.style.width = `${Math.max(8, (c / max) * 90)}px`;
    row.append(name, bar, el("span", "trend-row__val", String(c)));
    list.append(row);
  }
  card.append(list);
  return card;
}

function jumpToTopic(topic) {
  $("#f-topic").value = topic;
  state.shown = PAGE;
  renderPapers();
  $("#browse").scrollIntoView({ behavior: "smooth" });
}

// ---- papers -----------------------------------------------------------------
async function loadAllPapers() {
  $("#result-meta").textContent = "Loading articles…";
  const shards = await Promise.all(
    state.manifest.shards.map((s) => getJSON(s.file).catch(() => [])),
  );
  state.papers = shards.flat();
}

function buildFilters() {
  const m = state.manifest;
  fillSelect("#f-family", m.families);
  fillJournals();
  fillSelect("#f-period", [...m.periods].reverse());
  fillSelect("#f-topic", m.topics);

  $("#f-family").addEventListener("change", () => { fillJournals(); reset(); });
  for (const id of ["#f-journal", "#f-period", "#f-topic", "#f-sort"])
    $(id).addEventListener("change", reset);
  $("#f-search").addEventListener("input", debounce(reset, 180));
  $("#more-btn").addEventListener("click", () => { state.shown += PAGE; renderPapers(); });
}

function fillJournals() {
  const fam = $("#f-family").value;
  const journals = state.manifest.journals
    .filter((j) => !fam || j.family === fam)
    .map((j) => j.label);
  fillSelect("#f-journal", journals, true);
}

function fillSelect(sel, values, keepFirst) {
  const node = $(sel);
  const first = keepFirst || node.options.length ? node.options[0] : null;
  node.innerHTML = "";
  if (first) node.append(first.cloneNode(true));
  for (const v of values) node.append(new Option(v, v));
}

function reset() { state.shown = PAGE; renderPapers(); }

function filteredPapers() {
  const fam = $("#f-family").value;
  const jour = $("#f-journal").value;
  const per = $("#f-period").value;
  const topic = $("#f-topic").value;
  const q = $("#f-search").value.trim().toLowerCase();
  const sort = $("#f-sort").value;

  let out = state.papers.filter((p) => {
    if (fam && p.family !== fam) return false;
    if (jour && p.journal !== jour) return false;
    if (per && p.period !== per) return false;
    if (topic && !(p.topics || []).includes(topic)) return false;
    if (q) {
      const hay = (p.title + " " + (p.abstract || "") + " " + (p.authors || []).join(" ")).toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });

  if (sort === "citations") {
    out.sort((a, b) => (b.citations ?? -1) - (a.citations ?? -1));
  } else {
    out.sort((a, b) => (b.published || "").localeCompare(a.published || ""));
  }
  return out;
}

function renderPapers() {
  const all = filteredPapers();
  const list = $("#papers");
  list.innerHTML = "";
  const slice = all.slice(0, state.shown);
  for (const p of slice) list.append(paperCard(p));
  $("#result-meta").textContent = all.length
    ? `${all.length.toLocaleString()} article${all.length === 1 ? "" : "s"} — showing ${slice.length}`
    : "No articles match these filters.";
  $("#more-wrap").hidden = state.shown >= all.length;
}

function paperCard(p) {
  const li = el("li", "paper");
  const head = el("div", "paper__head");
  const h = el("h3", "paper__title");
  if (p.link || p.doi) {
    const a = el("a", null, p.title);
    a.href = p.link || `https://doi.org/${p.doi}`;
    a.target = "_blank";
    a.rel = "noopener";
    h.append(a);
  } else {
    h.textContent = p.title;
  }
  head.append(h);
  if (p.citations != null) head.append(el("span", "paper__cite", `${p.citations} cites`));
  li.append(head);

  const meta = el("p", "paper__meta");
  const j = el("span", "paper__journal", p.journal);
  meta.append(j);
  const bits = [];
  if (p.published) bits.push(p.published);
  if (p.authors && p.authors.length) bits.push(formatAuthors(p.authors));
  if (bits.length) meta.append(document.createTextNode(" · " + bits.join(" · ")));
  li.append(meta);

  if (p.abstract) li.append(el("p", "paper__abstract", p.abstract));

  if (p.topics && p.topics.length) {
    const tags = el("div", "paper__topics");
    for (const t of p.topics) tags.append(el("span", "tag", t));
    li.append(tags);
  }
  return li;
}

function formatAuthors(authors) {
  if (authors.length <= 3) return authors.join(", ");
  return authors.slice(0, 3).join(", ") + ` +${authors.length - 3}`;
}

function debounce(fn, ms) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

init();
