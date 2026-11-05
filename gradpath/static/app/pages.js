// GradPath pages: Overview, Schools, Graphs, graph detail, States, Help.
import {
  $, esc, icon, money, num, ratio, band, api, setContext, hrefWith, readContext, navigate, announce,
  table, errorBox, infoBox, loading, DATA_YEAR, FILTER_KEYS,
} from "./app.js";
import { addToPlan, planStatus } from "./plan.js";

// ── Shared filter panel (page-specific fields, chips, clear) ────────────────
const FIELD_LABELS = { school: "School", major: "Major", state: "State", credential: "Credential",
                       cip: "CIP code", school_type: "School type" };

async function optionLists(ctx, keys) {
  const want = new Set(keys);
  const filt = { school: ctx.school, state: ctx.state, credential: ctx.credential, school_type: ctx.school_type };
  const [schools, majors, states, credentials, cips, types] = await Promise.all([
    want.has("school") || ctx.school ? api("/options/schools") : [],
    want.has("major") || ctx.major ? api("/options/majors", filt) : [],
    want.has("state") || ctx.state ? api("/options/states") : [],
    want.has("credential") || ctx.credential ? api("/options/credentials") : [],
    want.has("cip") || ctx.cip ? api("/options/cips", { ...filt, major: ctx.major }) : [],
    want.has("school_type") || ctx.school_type ? api("/options/school_types") : [],
  ]);
  return { school: schools, major: majors, state: states.filter((o) => o.value !== "__all"),
           credential: credentials, cip: cips, school_type: types };
}

function fieldHTML(key, ctx, lists) {
  const id = `f-${key}`;
  if (key === "school") {
    const current = lists.school.find((o) => o.value === ctx.school);
    return `<div class="field"><label for="${id}">School</label>
      <input id="${id}" type="search" list="dl-schools" autocomplete="off" placeholder="Type a name or a state code, e.g. TX"
        value="${esc(current ? current.text : "")}" aria-describedby="${id}-err">
      <datalist id="dl-schools">${lists.school.map((o) => `<option value="${esc(o.text)}">`).join("")}</datalist>
      <div class="field__error" id="${id}-err" role="alert"></div></div>`;
  }
  const opts = lists[key].map((o) => `<option value="${esc(o.value)}" ${o.value === ctx[key] ? "selected" : ""}>${esc(o.text)}</option>`).join("");
  return `<div class="field"><label for="${id}">${FIELD_LABELS[key]}</label>
    <select id="${id}"><option value="">Any ${FIELD_LABELS[key].toLowerCase()}</option>${opts}</select></div>`;
}

function chipLabel(key, ctx, lists) {
  const hit = (lists[key] || []).find((o) => o.value === ctx[key]);
  return `${FIELD_LABELS[key]}: ${hit ? hit.text : String(ctx[key]).replace(/\.$/, "")}`;
}

/**
 * Render filters into `el`. `primary`/`advanced` list the fields this page needs; others are
 * kept in the URL (so context survives) but not shown. Calls onChange(ctx) after every change.
 */
async function filterPanel(el, ctx, { primary, advanced = [], onChange, heading = "Filter results" }) {
  const shown = [...primary, ...advanced];
  const lists = await optionLists(ctx, shown);
  const advOpen = advanced.some((k) => ctx[k]);
  const active = shown.filter((k) => ctx[k]);
  el.innerHTML = `<form class="filters" role="search" aria-label="${esc(heading)}" novalidate>
      <div class="filters__row ${primary.length >= 4 ? "filters__row--4" : ""}">${primary.map((k) => fieldHTML(k, ctx, lists)).join("")}</div>
      ${advanced.length ? `<details class="disclosure" ${advOpen ? "open" : ""}><summary>More filters</summary>
        <div class="filters__row">${advanced.map((k) => fieldHTML(k, ctx, lists)).join("")}</div></details>` : ""}
      <p class="meta" style="margin:var(--space-3) 0 0">Data year: ${DATA_YEAR}</p>
    </form>
    <div class="chips" aria-label="Active filters">${active.map((k) => `<span class="chip"><span>${esc(chipLabel(k, ctx, lists))}</span>
        <button type="button" data-remove="${k}" aria-label="Remove ${esc(FIELD_LABELS[k])} filter">${icon("i-close")}</button></span>`).join("")}
      ${active.length ? `<button type="button" class="button button--ghost" data-clear>Clear filters</button>` : ""}</div>`;

  const apply = async (next, focusId) => {
    if (next.school && next.school !== ctx.school) {          // a school decides its state
      const st = await api("/options/states", { school: next.school });
      if (st.length && st[0].value !== "__all") next.state = st[0].value;
    }
    setContext(next);
    await filterPanel(el, next, { primary, advanced, onChange, heading });
    if (focusId) { const f = $(`#${focusId}`, el); if (f) f.focus(); }
    onChange(next);
  };
  el.querySelectorAll("select").forEach((s) => s.addEventListener("change", () => {
    const key = s.id.slice(2);
    const next = { ...ctx, [key]: s.value || undefined };
    if (key === "major") delete next.cip;
    apply(next, s.id);
  }));
  const schoolInput = $("#f-school", el);
  if (schoolInput) {
    schoolInput.addEventListener("change", () => {
      const v = schoolInput.value.trim();
      const err = $("#f-school-err", el);
      if (!v) { schoolInput.removeAttribute("aria-invalid"); err.textContent = ""; if (ctx.school) apply({ ...ctx, school: undefined }, "f-school"); return; }
      const hit = lists.school.find((o) => o.text === v);
      if (!hit) {
        schoolInput.setAttribute("aria-invalid", "true");
        err.textContent = `No school is named “${v}”. Pick a school from the suggestions as you type, or clear the box.`;
        return;
      }
      schoolInput.removeAttribute("aria-invalid"); err.textContent = "";
      apply({ ...ctx, school: hit.value }, "f-school");
    });
  }
  el.querySelectorAll("[data-remove]").forEach((b) => b.addEventListener("click", () => {
    const next = { ...ctx }; delete next[b.dataset.remove];
    apply(next, shown.includes(b.dataset.remove) ? `f-${b.dataset.remove}` : null);
    announce(`${FIELD_LABELS[b.dataset.remove]} filter removed`);
  }));
  const clear = $("[data-clear]", el);
  if (clear) clear.addEventListener("click", () => { const next = {}; FILTER_KEYS.forEach((k) => { if (!shown.includes(k) && ctx[k]) next[k] = ctx[k]; }); apply(next, `f-${primary[0]}`); announce("Filters cleared"); });
  return lists;
}

const params = (ctx, keys = FILTER_KEYS) => Object.fromEntries(keys.filter((k) => ctx[k]).map((k) => [k, ctx[k]]));

// ── Overview ──────────────────────────────────────────────────────────────
export async function overviewPage(main, ctx) {
  const plan = planStatus();
  const planLabel = plan === "complete" ? "View my plan" : plan === "draft" ? "Continue my plan" : "Start my plan";
  const planHref = plan === "complete" ? "/plan/results" : "/plan";
  main.innerHTML = `
    <header class="page-header">
      <h1>Plan your degree with real outcomes and your own assumptions.</h1>
      <p class="lead">GradPath uses U.S. Department of Education data on what graduates earned and borrowed, plus the numbers you enter, to help you compare options and plan.</p>
    </header>
    <section aria-label="Main choices" class="grid grid--3">
      ${choice("i-school", "Explore schools and programs", "Search 4,043 schools and 320 majors and rank them by earnings and student debt.", hrefWith("/schools", ctx), "Explore schools")}
      ${choice("i-chart", "Compare debt and earnings", "See whether typical earnings can support typical debt, by program, state or credential.", hrefWith("/graphs", ctx), "Compare outcomes")}
      ${choice("i-plan", "Build my financial plan", "Estimate your funding gap, monthly loan payment and when you could be debt-free.", planHref, planLabel, true)}
    </section>
    <section class="section" aria-labelledby="lookup-h">
      <h2 id="lookup-h">Look up outcomes</h2>
      <div id="ov-filters">${loading("Loading filters")}</div>
      <div id="ov-results" class="section" aria-live="polite"></div>
    </section>`;
  const results = $("#ov-results", main);
  const show = async (c) => {
    if (!["school", "major", "state", "credential", "school_type"].some((k) => c[k])) {
      results.innerHTML = infoBox("Choose a school, major or state above to see median earnings and student debt for that selection.");
      return;
    }
    results.innerHTML = loading("Loading outcomes");
    try {
      const [s] = await api("/metrics/summary_stats", params(c));
      if (!s.matching_programs) { results.innerHTML = infoBox("No programs with published earnings and student debt match these filters. Remove a filter to widen the search."); return; }
      const months = s.median_debt_to_earnings * 12;
      results.innerHTML = `<div class="grid grid--4">
          ${kpi("Matching programs", num(s.matching_programs), `${num(s.matching_schools)} schools`)}
          ${kpi("Median earnings", money(s.median_earnings_overall), "2 years after finishing")}
          ${kpi("Median student debt", money(s.median_debt_overall), "Federal loans borrowed at the school")}
          ${kpi("Debt-to-earnings ratio", band(s.median_debt_to_earnings), `Debt ≈ ${months.toFixed(1)} months of earnings`)}
        </div>
        <p class="actions" style="margin-top:var(--space-4)"><a class="link-action" href="${esc(hrefWith("/schools", c))}" data-link>See these programs ${icon("i-next")}</a></p>`;
    } catch (e) { results.innerHTML = errorBox(`Couldn't load outcomes (${esc(e.message)}). Try again in a moment.`); }
  };
  await filterPanel($("#ov-filters", main), ctx, { primary: ["school", "major", "state"], advanced: ["credential", "school_type"], onChange: show, heading: "Look up outcomes" });
  show(ctx);
}

const choice = (ic, title, text, href, cta, primary = false) => `
  <article class="card card--choice">
    <span class="card__icon">${icon(ic)}</span>
    <h2>${esc(title)}</h2><p>${esc(text)}</p>
    <a class="button ${primary ? "button--primary" : "button--secondary"}" href="${esc(href)}" data-link>${esc(cta)}</a>
  </article>`;
const kpi = (label, value, note = "") => `<div class="card kpi"><span class="kpi__label">${esc(label)}</span>
  <span class="kpi__value">${value}</span>${note ? `<span class="kpi__note">${esc(note)}</span>` : ""}</div>`;

// ── Schools ───────────────────────────────────────────────────────────────
const SORTS = { debt_to_earnings: "Lowest debt-to-earnings", median_earnings: "Highest earnings", median_debt: "Lowest student debt" };

export async function schoolsPage(main, ctx) {
  main.innerHTML = `
    <header class="page-header"><h1>Schools and programs</h1>
      <p class="lead">Search by school, major or state. Results are ranked by how student debt compares with earnings.</p></header>
    <div id="sc-filters">${loading("Loading filters")}</div>
    <div id="sc-detail"></div>
    <section class="section" aria-labelledby="results-h">
      <div class="actions actions--split"><h2 id="results-h" style="margin:0">Ranked results</h2>
        <div class="field" style="min-width:220px"><label for="sc-sort">Sort by</label>
          <select id="sc-sort">${Object.entries(SORTS).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select></div></div>
      <p class="meta" id="sc-count" aria-live="polite"></p>
      <div id="sc-results">${loading("Loading results")}</div>
    </section>`;
  let limit = 25;
  let c = ctx;
  const sortSel = $("#sc-sort", main);

  const showResults = async () => {
    const box = $("#sc-results", main);
    box.innerHTML = loading("Loading results");
    try {
      const [rows, [s]] = await Promise.all([api("/schools/table", { ...params(c), limit, sort: sortSel.value }), api("/metrics/summary_stats", params(c))]);
      $("#sc-count", main).textContent = `Showing ${num(rows.length)} of ${num(s.matching_programs)} matching programs. ${DATA_YEAR}.`;
      box.innerHTML = table({
        caption: `Programs ranked by ${SORTS[sortSel.value].toLowerCase()}`,
        empty: "No programs match these filters. Remove a filter or choose “Any” to widen the search.",
        columns: [
          { label: "#", key: "rank", num: true },
          { label: "School", html: (r) => `<button type="button" class="table-button" data-school="${esc(r.institution_id)}">${esc(r.school)}</button>` },
          { label: "Program", key: "program" }, { label: "Credential", key: "credential" },
          { label: "Location", key: "city_state" },
          { label: "Median earnings", num: true, value: (r) => money(r.median_earnings) },
          { label: "Median student debt", num: true, value: (r) => money(r.median_debt) },
          { label: "Debt ÷ earnings", num: true, html: (r) => band(r.debt_to_earnings) },
          { label: "Graduates measured", num: true, value: (r) => num(r.cohort_size) },
        ], rows }) + (rows.length >= limit && rows.length < s.matching_programs
          ? `<p class="actions" style="margin-top:var(--space-4)"><button type="button" class="button button--secondary" id="sc-more">Show 25 more</button></p>` : "");
      box.querySelectorAll("[data-school]").forEach((b) => b.addEventListener("click", () => selectSchool(b.dataset.school)));
      const more = $("#sc-more", box);
      if (more) more.addEventListener("click", () => { limit += 25; showResults().then(() => announce(`Showing ${limit} results`)); });
    } catch (e) { box.innerHTML = errorBox(`Couldn't load results (${esc(e.message)}).`); }
  };

  const showDetail = async () => {
    const box = $("#sc-detail", main);
    if (!c.school) { box.innerHTML = ""; return; }
    box.innerHTML = `<section class="section">${loading("Loading school details")}</section>`;
    try {
      const q = { school: c.school, major: c.major, credential: c.credential };
      const [[d], progs] = await Promise.all([api("/schools/detail", q), api("/schools/programs", q)]);
      box.innerHTML = `<section class="section card" aria-labelledby="sd-h">
        <div class="actions actions--split" style="align-items:flex-start">
          <div class="school-card"><h2 id="sd-h" tabindex="-1">${esc(d.school_name)}</h2>
            <span>${esc(d.address)} · ${esc(d.city_state_zip)}</span>
            <span class="meta">${esc(d.school_type || "")} · Address from College Scorecard</span></div>
          <div class="actions">
            <button type="button" class="button button--primary" data-add-school>${icon("i-plus")}Add to My Plan</button>
            <button type="button" class="button button--secondary" data-compare>Compare another school</button></div></div>
        <div class="grid grid--4" style="margin-top:var(--space-4)">
          ${kpi("Median earnings", money(d.median_earnings), "Matching programs")}
          ${kpi("Median student debt", money(d.median_debt), "Matching programs")}
          ${kpi("Debt-to-earnings ratio", band(d.debt_to_earnings))}
          ${kpi("Graduates measured", num(d.total_cohort), `${num(d.matching_programs)} matching programs`)}
        </div>
        <h3 style="margin-top:var(--space-5)">Programs at this school</h3>
        ${table({ caption: `Programs at ${d.school_name}`, empty: "No programs match the current major or credential filter.",
          columns: [{ label: "Program", key: "program" }, { label: "Credential", key: "credential" },
            { label: "Median earnings", num: true, value: (r) => money(r.median_earnings) },
            { label: "Median student debt", num: true, value: (r) => money(r.median_debt) },
            { label: "Debt ÷ earnings", num: true, html: (r) => band(r.debt_to_earnings) },
            { label: "Graduates measured", num: true, value: (r) => num(r.cohort_size) },
            { label: "Plan", html: (r, i) => `<button type="button" class="table-button" data-add-program="${esc(r.major_value)}" data-cred="${esc(r.credential)}">Add to My Plan</button>` }],
          rows: progs })}
        <p class="meta" style="margin-top:var(--space-3)">Source: ${esc(d.outcomes_source)}.</p></section>`;
      const add = (major, credential) => { addToPlan({ school: c.school, school_label: `${d.school_name} — ${d.city_state_zip.replace(/ \d{5}.*$/, "")}`, major, credential });
        navigate("/plan?step=1"); announce(`${d.school_name} added to My Plan`); };
      $("[data-add-school]", box).addEventListener("click", () => add(c.major, c.credential));
      box.querySelectorAll("[data-add-program]").forEach((b) => b.addEventListener("click", () => add(b.dataset.addProgram, b.dataset.cred)));
      $("[data-compare]", box).addEventListener("click", async () => {
        const next = { ...c }; delete next.school; c = next; setContext(next);
        await filterPanel($("#sc-filters", main), next, filterSpec);
        showDetail(); showResults();
        const f = $("#f-school", main); if (f) f.focus();
      });
    } catch (e) { box.innerHTML = errorBox(`Couldn't load this school (${esc(e.message)}).`); }
  };

  const selectSchool = async (id) => {
    const st = await api("/options/states", { school: id });
    c = { ...c, school: id, ...(st[0] && st[0].value !== "__all" ? { state: st[0].value } : {}) };
    setContext(c);
    await filterPanel($("#sc-filters", main), c, filterSpec);
    await showDetail();
    const h = $("#sd-h", main); if (h) h.focus();
    showResults();
  };
  const filterSpec = { primary: ["school", "major", "state", "credential"], advanced: ["cip", "school_type"],
                       heading: "Filter schools", onChange: (next) => { c = next; limit = 25; showDetail(); showResults(); } };
  sortSel.addEventListener("change", () => { limit = 25; showResults(); });
  await filterPanel($("#sc-filters", main), c, filterSpec);
  showDetail();
  showResults();
}

// ── Graphs ────────────────────────────────────────────────────────────────
const GRAPHS = {
  "debt-earnings": { icon: "i-scatter", q: "Can earnings support the typical debt?",
    text: "Each dot is a program: what graduates borrowed against what they earned.",
    how: "Across: median student debt. Up: median earnings two years after finishing. Dot colour: school type (amber public, red private nonprofit, dark brown private for-profit). The dashed line marks earnings equal to debt; dots above it earned more in a year than they owed." },
  rankings: { icon: "i-rank", q: "Which programs rank best on the selected metric?",
    text: "Program types ranked by lowest debt-to-earnings or by highest earnings.",
    how: "Each row groups the same major, credential and school type across matching schools and takes the median. Debt ÷ earnings below 0.5 means debt is under half a year of earnings." },
  programs: { icon: "i-chart", q: "How do programs compare?",
    text: "The most common majors side by side: typical earnings and typical student debt.",
    how: "Orange bars: median earnings two years after finishing. Dark red bars: median student debt. Only majors offered by at least 3 matching programs are shown." },
  states: { icon: "i-map", q: "How do states compare?",
    text: "Typical earnings and debt for matching programs in each state.",
    how: "Orange bars: median earnings. Dark red bars: median student debt. A state's figure mixes many schools and majors and is not adjusted for cost of living." },
  credentials: { icon: "i-layers", q: "How do credential levels compare?",
    text: "Certificates, associate's, bachelor's and graduate credentials compared.",
    how: "Orange bars: median earnings. Dark red bars: median student debt. Credentials take different amounts of time, so compare debt with that in mind." },
};
const GRAPH_FILTERS = { primary: ["major", "state", "credential"], advanced: ["school", "cip", "school_type"] };

export async function graphsPage(main, ctx) {
  main.innerHTML = `<header class="page-header"><h1>Graphs</h1>
      <p class="lead">Pick a question. Each graph opens with a plain-language summary and a table you can read instead of the chart.</p></header>
    <div id="gr-filters">${loading("Loading filters")}</div>
    <section class="section grid grid--3" aria-label="Graph questions" id="gr-cards"></section>`;
  const cards = (c) => { $("#gr-cards", main).innerHTML = Object.entries(GRAPHS).map(([slug, g]) => `
    <article class="card card--choice"><span class="card__icon">${icon(g.icon)}</span>
      <h2>${esc(g.q)}</h2><p>${esc(g.text)}</p>
      <a class="button button--secondary" href="${esc(hrefWith(`/graphs/${slug}`, c))}" data-link>Open graph</a></article>`).join(""); };
  cards(ctx);
  await filterPanel($("#gr-filters", main), ctx, { ...GRAPH_FILTERS, heading: "Filter graphs", onChange: cards });
}

function embedSrc(manifest, entry, c) {
  const v = (k) => (c[k] ? c[k] : (k === "state" ? "__all" : "$__all"));
  const q = new URLSearchParams({ orgId: "1", panelId: String(entry.panel_id), theme: "light" });
  ["school", "state", "major", "cip", "credential", "school_type"].forEach((k) => q.set(`var-${k}`, v(k)));
  q.set("var-data_year", "$__all");
  return `${manifest.grafana}/d-solo/${entry.uid}/?${q}`;
}

export async function graphDetailPage(main, ctx, slug) {
  const g = GRAPHS[slug];
  if (!g) { main.innerHTML = `<h1>Graph not found</h1><p><a href="/graphs" data-link>Back to Graphs</a></p>`; return; }
  let mode = "rankings";
  main.innerHTML = `<p><a class="link-action" href="${esc(hrefWith("/graphs", ctx))}" data-link id="back-link">${icon("i-back")}Back to Graphs</a></p>
    <header class="page-header"><h1>${esc(g.q)}</h1><p class="lead">${esc(g.text)}</p></header>
    <div id="gd-filters">${loading("Loading filters")}</div>
    <section class="section stack" aria-label="Graph">
      ${slug === "rankings" ? `<div class="segmented" role="group" aria-label="Rank by">
        <button type="button" aria-pressed="true" data-mode="rankings">Lowest debt ÷ earnings</button>
        <button type="button" aria-pressed="false" data-mode="rankings-earnings">Highest earnings</button></div>` : ""}
      <div class="conclusion" id="gd-conclusion" aria-live="polite">${loading("Summarising")}</div>
      <div id="gd-chart"></div>
      <p class="meta">${esc(g.how)}</p>
      <details class="accordion" id="gd-table-wrap"><summary>View the data as a table</summary><div id="gd-table"></div></details>
      <p class="meta">Source: U.S. Department of Education, College Scorecard (release Oct 2026). ${DATA_YEAR}.</p>
    </section>`;
  const manifest = await api("/static/app/embed.json");

  const draw = async (c) => {
    $("#back-link", main).setAttribute("href", hrefWith("/graphs", c));
    const entry = manifest.graphs[slug === "rankings" ? mode : slug];
    $("#gd-chart", main).innerHTML = `<iframe class="chart-frame" src="${esc(embedSrc(manifest, entry, c))}"
      title="Chart: ${esc(g.q)} (a table version follows below)" loading="lazy"></iframe>`;
    const concl = $("#gd-conclusion", main), tbl = $("#gd-table", main);
    try {
      const p = params(c);
      if (slug === "debt-earnings") {
        const [[s], rows] = await Promise.all([api("/metrics/summary_stats", p), api("/schools/table", { ...p, limit: 25 })]);
        concl.innerHTML = s.matching_programs
          ? `<p style="margin:0"><strong>Across ${num(s.matching_programs)} matching programs, the typical graduate borrowed ${money(s.median_debt_overall)} and earned ${money(s.median_earnings_overall)} two years after finishing.</strong> That debt equals about ${(s.median_debt_to_earnings * 12).toFixed(1)} months of earnings.</p>`
          : "No programs match these filters.";
        tbl.innerHTML = table({ caption: "25 matching programs with the lowest debt-to-earnings", rows, columns: [
          { label: "School", key: "school" }, { label: "Program", key: "program" }, { label: "Credential", key: "credential" },
          { label: "Median earnings", num: true, value: (r) => money(r.median_earnings) },
          { label: "Median student debt", num: true, value: (r) => money(r.median_debt) },
          { label: "Debt ÷ earnings", num: true, html: (r) => band(r.debt_to_earnings) }] });
      } else if (slug === "rankings") {
        const rows = await api(mode === "rankings" ? "/metrics/top_programs_dte" : "/metrics/top_programs_earnings", { ...p, n: 20 });
        const top = rows[0];
        concl.innerHTML = top ? `<p style="margin:0"><strong>#1: ${esc(top.cip_title.replace(/\.$/, ""))}</strong> (${esc(top.credential_level)}, ${esc(top.school_type)}): median earnings ${money(top.median_earnings)}, median student debt ${money(top.median_debt)}, debt ÷ earnings ${ratio(top.debt_to_earnings)}.</p>` : "No programs match these filters.";
        tbl.innerHTML = table({ caption: `Top 20 program types — ${mode === "rankings" ? "lowest debt ÷ earnings" : "highest earnings"}`, rows,
          columns: [{ label: "Major", value: (r) => r.cip_title.replace(/\.$/, "") }, { label: "Credential", key: "credential_level" },
            { label: "School type", key: "school_type" }, { label: "Median earnings", num: true, value: (r) => money(r.median_earnings) },
            { label: "Median student debt", num: true, value: (r) => money(r.median_debt) },
            { label: "Debt ÷ earnings", num: true, html: (r) => band(r.debt_to_earnings) }] });
      } else {
        const spec = { programs: { by: "major", sort: "programs", n: 20, min_programs: 3, noun: "major" },
                       states: { by: "state", sort: "median_earnings", n: 60, noun: "state" },
                       credentials: { by: "credential", sort: "median_earnings", noun: "credential level" } }[slug];
        const rows = await api("/metrics/group", { ...p, by: spec.by, sort: spec.sort, n: spec.n, min_programs: spec.min_programs });
        if (rows.length) {
          const hiE = rows.reduce((a, b) => (b.median_earnings > a.median_earnings ? b : a));
          const loD = rows.reduce((a, b) => (b.median_debt < a.median_debt ? b : a));
          concl.innerHTML = `<p style="margin:0"><strong>Highest median earnings: ${esc(hiE.label)} (${money(hiE.median_earnings)}).</strong> Lowest median student debt: ${esc(loD.label)} (${money(loD.median_debt)}). Based on ${rows.length} ${spec.noun}${rows.length === 1 ? "" : "s"} that match your filters.</p>`;
        } else concl.innerHTML = "No programs match these filters.";
        tbl.innerHTML = table({ caption: `By ${spec.noun}`, rows, columns: [
          { label: spec.noun[0].toUpperCase() + spec.noun.slice(1), key: "label" },
          { label: "Median earnings", num: true, value: (r) => money(r.median_earnings) },
          { label: "Median student debt", num: true, value: (r) => money(r.median_debt) },
          { label: "Debt ÷ earnings", num: true, html: (r) => band(r.debt_to_earnings) },
          { label: "Programs", num: true, value: (r) => num(r.programs) }, { label: "Schools", num: true, value: (r) => num(r.schools) }] });
      }
    } catch (e) { concl.innerHTML = errorBox(`Couldn't summarise this graph (${esc(e.message)}).`); }
  };
  main.querySelectorAll("[data-mode]").forEach((b) => b.addEventListener("click", () => {
    mode = b.dataset.mode;
    main.querySelectorAll("[data-mode]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    draw(readContext());
  }));
  await filterPanel($("#gd-filters", main), ctx, { ...GRAPH_FILTERS, heading: "Filter this graph", onChange: draw });
  draw(ctx);
}

// ── States ────────────────────────────────────────────────────────────────
export async function statesPage(main, ctx) {
  main.innerHTML = `<header class="page-header"><h1>State taxes</h1>
      <p class="lead">Verified state income-tax facts for tax year 2025, each checked on the state's official revenue website.</p></header>
    <div class="filters"><div class="field" style="max-width:460px"><label for="st-select" style="font-size:var(--text-l)">Choose a state</label>
      <select id="st-select">${loading()}</select></div></div>
    <div id="st-body" class="section" aria-live="polite">${loading("Loading states")}</div>`;
  const [states, verified] = await Promise.all([api("/options/states"), api("/states/tax_table")]);
  const vset = new Set(verified.map((v) => v.state_code));
  const all = states.filter((s) => s.value !== "__all");
  const sel = $("#st-select", main);
  sel.innerHTML = `<option value="">Select a state</option>
    <optgroup label="Verified for tax year 2025">${all.filter((s) => vset.has(s.value)).map((s) => `<option value="${s.value}">${esc(s.text)}</option>`).join("")}</optgroup>
    <optgroup label="Not yet verified">${all.filter((s) => !vset.has(s.value)).map((s) => `<option value="${s.value}">${esc(s.text)}</option>`).join("")}</optgroup>`;
  sel.value = ctx.state || "";
  const body = $("#st-body", main);
  const verifiedList = () => `<div class="grid grid--3">${verified.map((v) => `<article class="card">
      <h3>${esc(v.state_name)}</h3><p>${esc(v.rate_summary)}</p>
      <button type="button" class="button button--secondary" data-pick="${v.state_code}">View ${esc(v.state_name)}</button></article>`).join("")}</div>`;
  const metaLine = (t) => `<p class="meta" style="margin:var(--space-3) 0 0">Tax year ${esc(t.tax_year)} · Source: <a href="${esc(t.official_source_url)}" target="_blank" rel="noopener">${esc(new URL(t.official_source_url).hostname)}${icon("i-external")}</a> · Verified ${esc(t.last_verified)}</p>`;

  const show = async (code) => {
    if (!code) {
      body.innerHTML = `<h2>What you can see here</h2>
        <p>For each verified state: whether it taxes wages, its rates for tax year 2025, the standard deduction for a single filer,
        how it treats student-loan interest and education credits (when verified), an example tax estimate, and the official source.</p>
        <h2 style="margin-top:var(--space-5)">Verified states</h2>${verifiedList()}`;
      bindPicks(); return;
    }
    body.innerHTML = loading("Loading tax facts");
    const [t] = await api("/states/tax", { state: code });
    if (!t.supported.startsWith("Verified")) {
      body.innerHTML = `<div class="notice notice--warning">${icon("i-alert")}<div><strong>${esc(t.state_name)} isn't verified yet.</strong>
        GradPath only shows tax facts it has confirmed on an official state website. Check ${esc(t.state_name)}'s department of revenue, or pick a verified state below.</div></div>
        <h2 class="section">Verified states</h2>${verifiedList()}`;
      bindPicks(); return;
    }
    const confirm = t.supported !== "Verified" ? `<div class="notice notice--warning">${icon("i-info")}<div>This state's site blocks automated checks, so these figures came from the official page via a search index. Open the source to confirm.</div></div>` : "";
    body.innerHTML = `${confirm}
      <div class="grid grid--2" style="margin-top:var(--space-4)">
        <article class="card"><h2>Income tax in ${esc(t.state_name)}</h2><p><strong>${esc(t.rate_summary)}</strong></p>
          <dl class="facts"><dt>Type</dt><dd>${esc({ none: "No wage income tax", flat: "Flat rate", graduated: "Graduated rates" }[t.income_tax_type] || t.income_tax_type)}</dd>
            ${t.minimum_rate ? `<dt>Rates</dt><dd>${esc(t.minimum_rate)}%${t.maximum_rate !== t.minimum_rate ? ` to ${esc(t.maximum_rate)}%` : ""}</dd>` : ""}
            <dt>Standard deduction (single)</dt><dd>${esc(t.standard_deduction_single)}</dd></dl>${metaLine(t)}</article>
        <article class="card"><h2>Example: state tax on a salary</h2>
          <div class="field" style="max-width:260px"><label for="st-income">Example yearly salary ($)</label>
            <input id="st-income" type="number" inputmode="numeric" min="0" max="2000000" step="1000" value="50000" aria-describedby="st-income-err">
            <div class="field__error" id="st-income-err" role="alert"></div></div>
          <div id="st-est" aria-live="polite" style="margin-top:var(--space-3)"></div>${metaLine(t)}</article>
        <article class="card"><h2>Student-loan interest</h2><p>${esc(t.student_loan_interest_treatment === "Not verified" ? "Not verified for this state yet. Don't assume a deduction is available." : t.student_loan_interest_treatment)}</p>${metaLine(t)}</article>
        <article class="card"><h2>Education deductions or credits</h2><p>${esc(t.education_credit_summary === "Not verified" ? "None verified for this state yet." : t.education_credit_summary)}</p>${metaLine(t)}</article>
        <article class="card"><h2>Assumptions and notes</h2><p>${esc(t.notes)}</p><p class="meta">How it was verified: ${esc(t.verification_method)}.</p>${metaLine(t)}</article>
        <article class="card"><h2>Official source</h2><p><a class="button button--secondary" href="${esc(t.official_source_url)}" target="_blank" rel="noopener">Open the ${esc(t.state_name)} source ${icon("i-external")}</a></p>
          <p class="meta">Last verified ${esc(t.last_verified)}. Tax rules change every year; check the source before relying on these facts.</p></article>
      </div>`;
    const inc = $("#st-income", body);
    const estimate = async () => {
      const v = Number(inc.value), err = $("#st-income-err", body);
      if (inc.value === "" || !Number.isFinite(v) || v < 0 || v > 2000000) {
        inc.setAttribute("aria-invalid", "true"); err.textContent = "Enter a salary between $0 and $2,000,000, for example 50000."; return;
      }
      inc.removeAttribute("aria-invalid"); err.textContent = "";
      const [e] = await api("/states/tax_estimate", { state: code, income: v });
      $("#st-est", body).innerHTML = `<p class="kpi__value">${money(e.estimated_state_tax)} <span class="kpi__note">a year (${e.effective_rate_pct ?? 0}% effective)</span></p>
        <p class="meta">Educational estimate. ${esc(e.assumptions)}</p>`;
    };
    inc.addEventListener("change", estimate);
    estimate();
  };
  const bindPicks = () => body.querySelectorAll("[data-pick]").forEach((b) => b.addEventListener("click", () => {
    sel.value = b.dataset.pick; sel.dispatchEvent(new Event("change")); sel.focus();
  }));
  sel.addEventListener("change", () => { setContext({ ...readContext(), state: sel.value || undefined }); show(sel.value); });
  show(sel.value);
}

// ── Help ──────────────────────────────────────────────────────────────────
// built on demand: module-level calls into app.js would run before it initialises
const helpSections = () => [
  ["getting-started", "Getting started", `
    <p>GradPath helps you answer four questions:</p>
    <ol><li><strong>Which schools and programs match my interests?</strong> Use <a href="/schools" data-link>Schools</a>: search by school, major or state.</li>
    <li><strong>How do debt and earnings compare?</strong> Use <a href="/graphs" data-link>Graphs</a>.</li>
    <li><strong>What could my own funding and repayment look like?</strong> Use <a href="/plan" data-link>My Plan</a>, a four-step walkthrough.</li>
    <li><strong>How should I read the data?</strong> You're here.</li></ol>
    <p>Filters you choose (school, major, state) follow you between Overview, Schools and Graphs. Picking a school fills in its state automatically.</p>`],
  ["metrics", "Understanding the metrics", `
    <h3>Median earnings</h3><p>The middle salary of graduates who were working and not in school, two years after finishing. Half earned more, half less.</p>
    <h3>Median student debt</h3><p>The middle amount of federal student loans (Stafford and Grad PLUS) that graduates who borrowed took out at that school.
    It is not the full cost of attendance, and it leaves out private loans and loans parents take out.</p>
    <p class="notice notice--info">${icon("i-info")}<span><strong>A correction we made:</strong> earlier versions of GradPath showed loans taken out by parents (Parent PLUS) as if they were student debt. All debt figures now show the student's own federal loans, which also added more majors and graduate programs.</span></p>
    <h3>Debt-to-earnings ratio</h3><p><strong>Median student debt ÷ median earnings.</strong> 0.5 means the debt equals half a year of earnings.
    GradPath labels ratios as <em>Lower</em> (under 0.5), <em>Moderate</em> (0.5 to 1.0) or <em>Higher</em> (1.0 or more). These labels help you compare; they are not a grade.</p>`],
  ["plan", "Building a plan", `
    <p>My Plan asks about your school, your costs and savings, and your career assumptions, then estimates:</p>
    <ul><li><strong>Funding gap:</strong> tuition and living costs, minus scholarships, grants and your savings, before borrowing.</li>
    <li><strong>Debt when repayment begins:</strong> what you borrow plus interest that builds up while you're in school and for 6 months after graduating.</li>
    <li><strong>Monthly payment:</strong> the standard 10-year payment, or more if you choose to put a share of your salary toward loans.</li>
    <li><strong>Debt-free range:</strong> the month of your final payment under your conservative, expected and aspirational salaries.</li></ul>
    <details class="accordion"><summary>See the formulas</summary><div>
      <ol><li>Each year's loan is paid out in September.</li>
      <li>Interest before repayment: amount × yearly rate × months ÷ 12, for each loan, until repayment starts the November after a May graduation.</li>
      <li>Standard payment: P × r ÷ (1 − (1 + r)<sup>−120</sup>), where P is the starting balance and r is the yearly rate ÷ 12, rounded up to the cent.</li>
      <li>Each salary scenario pays the larger of the standard payment and your chosen share of salary ÷ 12 (10% unless you change it).</li>
      <li>Month by month, interest is added and the payment subtracted until the balance reaches zero. That month is the debt-free date.</li></ol>
      <p>Not included: income-driven plans, forgiveness, missed or extra payments, rate changes, and daily interest.</p></div></details>`],
  ["sources", "Data sources", `<div id="help-sources">${loading("Loading sources")}</div>`],
  ["privacy", "Privacy", `
    <ul><li>GradPath never asks for bank accounts, logins or account numbers.</li>
    <li>Your My Plan answers are saved only in this browser. They are sent to the local GradPath calculator to compute results and are not stored there.</li>
    <li>Your financial answers never appear in the page address, so they don't end up in browser history or shared links.</li>
    <li>Use <strong>Clear plan</strong> in My Plan to delete your saved answers.</li></ul>`],
  ["limitations", "Limitations", `
    <ul><li>Historical earnings don't guarantee future salary. Your occupation, employer, location and experience matter.</li>
    <li>Median student debt is not the cost of attendance.</li>
    <li>School and major don't cause a particular income.</li>
    <li>About 85% of programs have no published earnings or debt, because small groups are hidden to protect privacy.</li>
    <li>The data lags current conditions by several years.</li>
    <li>State tax rules change every year; only 10 states are verified.</li>
    <li>Everything here is educational planning information, not personal financial or tax advice.</li></ul>`],
  ["faq", "Frequently asked questions", `
    <h3>Why can't I find my school?</h3><p>It may have no programs with published earnings and debt, or a filter is hiding it. Clear the filters and search again.</p>
    <h3>Why do two schools have the same name?</h3><p>Some names repeat across states. Every school shows its city and state so you can tell them apart.</p>
    <h3>Why does my plan say "Low confidence"?</h3><p>No published record matches your school and major, so the comparison uses a broader group or none.</p>
    <h3>Can I save my plan?</h3><p>Yes. It saves automatically in this browser. Clearing your browser data removes it.</p>`],
];

export async function helpPage(main) {
  const HELP = helpSections();
  main.innerHTML = `<header class="page-header"><h1>Help</h1><p class="lead">A short guide to using GradPath and reading its numbers.</p></header>
    <nav aria-label="Help topics"><ul class="toc">${HELP.map(([id, t]) => `<li><a href="#${id}">${esc(t)}</a></li>`).join("")}</ul></nav>
    ${HELP.map(([id, t, html], i) => `<details class="accordion" id="${id}" ${i === 0 ? "open" : ""}><summary>${esc(t)}</summary><div>${html}</div></details>`).join("")}`;
  main.querySelectorAll(".toc a").forEach((a) => a.addEventListener("click", (e) => {
    e.preventDefault(); const d = $(a.getAttribute("href"), main); d.open = true; d.querySelector("summary").focus(); d.scrollIntoView();
  }));
  try {
    const src = await api("/meta/sources");
    $("#help-sources", main).innerHTML = table({ caption: "Where GradPath's data comes from", rows: src, columns: [
      { label: "Dataset", value: (r) => r.dataset_name.replace(/\s*\(.*\)$/, "") }, { label: "Organization", key: "source_organization" },
      { label: "Year", key: "source_year" }, { label: "Checked", key: "downloaded_at" },
      { label: "Link", html: (r) => `<a href="${esc(r.source_url)}" target="_blank" rel="noopener">Open${icon("i-external")}</a>` }] });
  } catch (e) { $("#help-sources", main).innerHTML = errorBox("Couldn't load the source list."); }
}
