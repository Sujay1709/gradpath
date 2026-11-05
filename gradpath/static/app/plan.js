// My Plan: four-step walkthrough, review and results. Answers stay in this browser
// (localStorage) and are sent to the local calculator in a request body, never a URL.
import { $, esc, icon, money, num, band, api, apiPost, navigate, announce, table, errorBox, infoBox, loading,
         confirmAction } from "./app.js";

const KEY = "gradpath.plan.v2";
const EXAMPLE = { school: "186380", school_label: "Rutgers University-New Brunswick — New Brunswick, NJ",
  major: "", credential: "Bachelor's Degree", in_state: "yes", start_year: "2027", grad_year: "2031",
  savings: "4000", contribution: "1500", grants: "6000", existing_debt: "0", borrowing: "5500", tuition: "", living: "13000",
  rate: "", occupation: "Example student (fictional)", work_state: "NJ", salary_low: "42000", salary_mid: "", salary_high: "72000",
  repay_pct: "10" };

// ── storage ────────────────────────────────────────────────────────────────
function load() {
  try {
    const v2 = JSON.parse(localStorage.getItem(KEY) || "null");
    if (v2) return v2;
    const v1 = JSON.parse(localStorage.getItem("gradpath.plan.v1") || "null");   // migrate the old single form
    return v1 ? { draft: v1, completedAt: null, updatedAt: null } : { draft: {}, completedAt: null, updatedAt: null };
  } catch { return { draft: {}, completedAt: null, updatedAt: null }; }
}
function save(state) {
  state.updatedAt = new Date().toISOString();
  try { localStorage.setItem(KEY, JSON.stringify(state)); localStorage.removeItem("gradpath.plan.v1"); } catch { /* private mode */ }
}
function clearAll() { try { localStorage.removeItem(KEY); localStorage.removeItem("gradpath.plan.v1"); } catch { /* ignore */ } }

export function planStatus() {
  const s = load();
  if (s.completedAt && missingRequired(s.draft, {}).length === 0) return "complete";
  return Object.values(s.draft || {}).some((v) => v) ? "draft" : "none";
}
/** Used by Schools → "Add to My Plan". Keeps other answers; resets the program if the school changed. */
export function addToPlan({ school, school_label, major, credential }) {
  const s = load();
  const changed = s.draft.school !== school;
  s.draft = { ...s.draft, school, school_label, major: major || (changed ? "" : s.draft.major),
              credential: credential || (changed ? "" : s.draft.credential) };
  if (changed) { s.draft.tuition = s.draft.tuition_auto ? "" : s.draft.tuition; }
  s.completedAt = null;
  save(s);
}

// ── field definitions ──────────────────────────────────────────────────────
const STEPS = ["School", "Costs and savings", "Career", "Review"];
const F = {
  school: { step: 1, label: "School", required: true, recovery: "Start typing your school's name and pick it from the suggestions." },
  major: { step: 1, label: "Major or program" },
  credential: { step: 1, label: "Credential" },
  in_state: { step: 1, label: "Residency" },
  start_year: { step: 1, label: "Start year", required: true, int: true, min: 2000, max: 2045, example: "2027" },
  grad_year: { step: 1, label: "Expected graduation year", required: true, int: true, min: 2000, max: 2055, example: "2031" },
  savings: { step: 2, label: "Current savings", money: true, min: 0, max: 2000000, example: "4000" },
  contribution: { step: 2, label: "Savings you add each year", money: true, min: 0, max: 500000, example: "1500" },
  grants: { step: 2, label: "Scholarships and grants per year", money: true, min: 0, max: 500000, example: "6000" },
  existing_debt: { step: 2, label: "Existing student-loan balance", money: true, min: 0, max: 2000000, example: "0" },
  borrowing: { step: 2, label: "Expected borrowing per year", money: true, required: true, min: 0, max: 500000, example: "5500",
               recovery: "Enter how much you expect to borrow each year. Enter 0 if you won't borrow." },
  tuition: { step: 2, label: "Tuition and fees per year", money: true, min: 0, max: 500000, example: "11000", requiredUnlessAuto: "tuition",
             recovery: "This school doesn't publish tuition. Enter an estimate from its website." },
  living: { step: 2, label: "Living expenses per year", money: true, required: true, min: 0, max: 500000, example: "13000",
            recovery: "Enter an estimate for housing, food, books and transport, for example 13000." },
  rate: { step: 2, label: "Loan interest rate (%)", min: 0, max: 25, example: "6.52" },
  occupation: { step: 3, label: "Intended occupation" },
  work_state: { step: 3, label: "State you expect to work in" },
  salary_low: { step: 3, label: "Conservative starting salary", money: true, min: 0, max: 2000000, example: "40000" },
  salary_mid: { step: 3, label: "Expected starting salary", money: true, min: 0, max: 2000000, example: "52000", requiredUnlessAuto: "salary",
                recovery: "No Scorecard earnings match this program. Enter the salary you expect, for example 52000." },
  salary_high: { step: 3, label: "Aspirational starting salary", money: true, min: 0, max: 2000000, example: "70000" },
  repay_pct: { step: 3, label: "Share of salary for loan payments (%)", min: 1, max: 50, example: "10" },
};
const clean = (v) => String(v ?? "").trim().replace(/[$,%\s]/g, "");

function validateField(key, draft, auto) {
  const f = F[key], raw = draft[key] ?? "", v = clean(raw);
  const needed = f.required || (f.requiredUnlessAuto && !auto[f.requiredUnlessAuto]);
  if (key === "school") return draft.school ? "" : `${f.label} is required. ${f.recovery}`;
  if (v === "") return needed ? `${f.label} is required. ${f.recovery || `Enter a value, for example ${f.example}.`}` : "";
  if (["occupation", "work_state", "major", "credential", "in_state"].includes(key)) return "";
  const n = Number(v);
  if (!Number.isFinite(n)) return `“${raw}” isn't a number. Enter digits only, for example ${f.example}.`;
  if (f.int && !Number.isInteger(n)) return `Enter a whole year, for example ${f.example}.`;
  if (n < f.min || n > f.max) return `${f.label} must be between ${f.money ? money(f.min) : f.min} and ${f.money ? money(f.max) : f.max}. Check for an extra zero.`;
  if (key === "grad_year" && draft.start_year && n <= Number(clean(draft.start_year)))
    return "Graduation must come after the start year. Change one of the two years.";
  return "";
}
function missingRequired(draft, auto) {
  return Object.keys(F).filter((k) => (F[k].required || (F[k].requiredUnlessAuto && !auto[F[k].requiredUnlessAuto])) && validateField(k, draft, auto));
}

/** Scorecard values that fill blanks: published tuition, historical salary, school state. */
async function autoValues(draft) {
  if (!draft.school) return {};
  try {
    const q = { school: draft.school, major: draft.major, credential: draft.credential, in_state: draft.in_state || "yes" };
    const [[est], states] = await Promise.all([api("/plan/estimate", q), api("/options/states", { school: draft.school })]);
    return {
      tuition: est.tuition_source.startsWith("Scorecard") ? est.annual_tuition_used : null,
      tuition_note: est.tuition_source.replace(/ — editable$/, "").replace("Scorecard published", "published"),
      salary: est.expected_salary_source.startsWith("Scorecard") ? est.expected_salary_used : null,
      state: states[0] && states[0].value !== "__all" ? states[0].value : null,
    };
  } catch { return {}; }
}

// ── walkthrough ───────────────────────────────────────────────────────────
function progress(step) {
  return `<p class="meta" style="margin:0">Step ${step} of 4</p>
    <ol class="progress" aria-label="Plan progress">${STEPS.map((s, i) => `<li class="${i + 1 < step ? "is-done" : ""}" ${i + 1 === step ? 'aria-current="step"' : ""}>
      <span>${i + 1}. ${s}</span><span class="visually-hidden">${i + 1 < step ? " (done)" : i + 1 === step ? " (current)" : ""}</span></li>`).join("")}</ol>`;
}

const label = (key, hint = "") => {
  const f = F[key];
  const tag = f.required ? `<span class="req">Required</span>` : f.requiredUnlessAuto ? `<span class="req">Required if not filled in for you</span>` : `<span class="opt">Optional</span>`;
  return `<label for="p-${key}">${esc(f.label)}${tag}</label>${hint ? `<span class="field__hint" id="p-${key}-hint">${hint}</span>` : ""}`;
};
const numField = (key, draft, hint = "", auto = "") => `<div class="field">${label(key, hint)}
  <input id="p-${key}" name="${key}" inputmode="decimal" autocomplete="off" value="${esc(draft[key] ?? "")}"
    aria-describedby="p-${key}-err ${hint ? `p-${key}-hint` : ""} p-${key}-auto">
  <div class="field__auto" id="p-${key}-auto">${auto}</div>
  <div class="field__error" id="p-${key}-err"></div></div>`;

export async function planStepPage(main) {
  const step = Math.min(3, Math.max(1, Number(new URLSearchParams(location.search).get("step")) || 1));
  const state = load();
  const d = state.draft;
  main.innerHTML = `<header class="page-header"><h1>Build my plan</h1>
      <p class="lead">Answer what you know. Leave optional boxes blank and GradPath will say which values it filled in for you.</p>
      ${progress(step)}</header>
    <div id="p-summary"></div>
    <form id="p-form" novalidate><div class="card"><h2>${esc(STEPS[step - 1])}</h2><div id="p-fields">${loading("Loading questions")}</div></div>
      <div class="actions actions--split step-footer">
        ${step > 1 ? `<a class="button button--secondary" href="/plan?step=${step - 1}" data-link>${icon("i-back")}Back</a>` : "<span></span>"}
        <button class="button button--primary" type="submit">${step < 3 ? "Continue" : "Review my answers"}${icon("i-next")}</button>
      </div></form>
    <div class="secondary-zone">
      <span class="meta" id="p-saved" aria-live="polite">${state.updatedAt ? "Draft saved on this device." : "Your answers save automatically on this device."}</span>
      <span class="actions">${step === 1 ? `<button type="button" class="button button--ghost" id="p-example">Use example student</button>` : ""}
        <button type="button" class="button button--danger-text" id="p-clear">${icon("i-trash")}Clear plan</button></span>
    </div>`;
  let auto = await autoValues(d);
  const fieldsEl = $("#p-fields", main);

  const renderFields = async () => {
    if (step === 1) {
      const schools = await api("/options/schools");
      let progs = [];
      if (d.school) { try { progs = await api("/schools/programs", { school: d.school }); } catch { progs = []; } }
      const majors = [...new Map(progs.map((p) => [p.major_value, p.program])).entries()];
      const creds = [...new Set(progs.map((p) => p.credential))];
      let card = "";
      if (d.school) {
        try { const [sd] = await api("/schools/detail", { school: d.school });
          card = `<div class="notice notice--info">${icon("i-school")}<div><strong>${esc(sd.school_name)}</strong><br>${esc(sd.address)} · ${esc(sd.city_state_zip)} · ${esc(sd.school_type || "")}
            <br><span class="meta">Address from College Scorecard.</span></div></div>`; } catch { card = ""; }
      }
      fieldsEl.innerHTML = `<div class="form-grid">
        <div class="field span-2">${label("school", "Type part of the name or a state code, e.g. TX.")}
          <input id="p-school" type="search" list="p-dl-schools" autocomplete="off" value="${esc(d.school_label || "")}" aria-describedby="p-school-hint p-school-err">
          <datalist id="p-dl-schools">${schools.map((o) => `<option value="${esc(o.text)}">`).join("")}</datalist>
          <div class="field__error" id="p-school-err"></div></div>
        <div class="span-2">${card}</div>
        <div class="field">${label("major", d.school ? "Programs with published outcomes at this school." : "Choose a school first.")}
          <select id="p-major" ${d.school ? "" : "disabled"} aria-describedby="p-major-hint"><option value="">Any program at this school</option>
          ${majors.map(([v, t]) => `<option value="${esc(v)}" ${v === d.major ? "selected" : ""}>${esc(t)}</option>`).join("")}</select></div>
        <div class="field">${label("credential")}
          <select id="p-credential" ${d.school ? "" : "disabled"}><option value="">Any credential</option>
          ${creds.map((c) => `<option ${c === d.credential ? "selected" : ""}>${esc(c)}</option>`).join("")}</select></div>
        <fieldset class="field span-2"><legend>Residency <span class="opt">Optional</span></legend>
          <div class="radio-row"><label><input type="radio" name="in_state" value="yes" ${d.in_state !== "no" ? "checked" : ""}> In-state</label>
          <label><input type="radio" name="in_state" value="no" ${d.in_state === "no" ? "checked" : ""}> Out-of-state</label></div>
          <span class="field__hint">Used to pick the published tuition for your school.</span></fieldset>
        ${numField("start_year", d, "The year you start classes.")}
        ${numField("grad_year", d, "Usually 4 years after starting a bachelor's degree, 2 for an associate's.")}
      </div>`;
      const sInput = $("#p-school", fieldsEl);
      sInput.addEventListener("change", async () => {
        const hit = schools.find((o) => o.text === sInput.value.trim());
        const err = $("#p-school-err", fieldsEl);
        if (!sInput.value.trim()) { d.school = ""; d.school_label = ""; persist(); return; }
        if (!hit) { sInput.setAttribute("aria-invalid", "true"); err.innerHTML = `${icon("i-alert")}<span>No school is named “${esc(sInput.value)}”. ${F.school.recovery}</span>`; return; }
        sInput.removeAttribute("aria-invalid"); err.textContent = "";
        if (hit.value !== d.school) { d.major = ""; d.credential = ""; }
        d.school = hit.value; d.school_label = hit.text; persist();
        auto = await autoValues(d); await renderFields(); $("#p-major", fieldsEl).focus();
        announce(`${hit.text} selected. Programs updated.`);
      });
      ["major", "credential"].forEach((k) => $(`#p-${k}`, fieldsEl).addEventListener("change", async (e) => { d[k] = e.target.value; persist(); auto = await autoValues(d); }));
      fieldsEl.querySelectorAll('input[name="in_state"]').forEach((r) => r.addEventListener("change", async () => { d.in_state = r.value; persist(); auto = await autoValues(d); }));
    } else if (step === 2) {
      const tuitionAuto = auto.tuition != null ? `Leave blank to use ${money(auto.tuition)}: ${esc(auto.tuition_note)}.` : "";
      fieldsEl.innerHTML = `<p class="meta">Enter yearly amounts in dollars. Per-year amounts repeat for every year you're in school.</p><div class="form-grid">
        ${numField("tuition", d, "Published tuition and fees, or your own estimate.", tuitionAuto)}
        ${numField("living", d, "Housing, food, books and transport.")}
        ${numField("grants", d, "Free money you don't repay.")}
        ${numField("savings", d, "What you have saved today.")}
        ${numField("contribution", d, "Before and during school.")}
        ${numField("borrowing", d, "Federal or private student loans per year.")}
        ${numField("existing_debt", d, "Loans you already have.")}
        ${numField("rate", d, "", "Leave blank to use 6.52%, the 2026–27 federal undergraduate loan rate.")}
      </div>`;
    } else {
      const states = (await api("/options/states")).filter((s) => s.value !== "__all");
      if (!d.work_state && auto.state) { d.work_state = auto.state; d.work_state_auto = true; persist(); }
      const salaryAuto = auto.salary != null ? `Leave blank to use ${money(auto.salary)}, the historical median for your program (College Scorecard).` : "";
      fieldsEl.innerHTML = `<p class="meta">Three salaries show a range instead of one guess. Only the expected salary is needed.</p><div class="form-grid">
        <div class="field">${label("occupation")}<input id="p-occupation" name="occupation" maxlength="80" value="${esc(d.occupation || "")}" placeholder="e.g. Registered nurse"></div>
        <div class="field">${label("work_state")}<select id="p-work_state" aria-describedby="p-work_state-auto"><option value="">Not sure yet</option>
          ${states.map((s) => `<option value="${s.value}" ${s.value === d.work_state ? "selected" : ""}>${esc(s.text)}</option>`).join("")}</select>
          <div class="field__auto" id="p-work_state-auto">${d.work_state_auto && d.work_state === auto.state ? `Filled in with your school's state (${esc(auto.state)}). Change it if you plan to work elsewhere.` : ""}</div></div>
        ${numField("salary_low", d, "A salary you're fairly sure you could beat.")}
        ${numField("salary_mid", d, "Your best guess.", salaryAuto)}
        ${numField("salary_high", d, "A strong outcome, not a promise.")}
        ${numField("repay_pct", d, "", "Leave blank to put 10% of your salary toward loans (never less than the standard payment).")}
      </div>`;
      $("#p-work_state", fieldsEl).addEventListener("change", (e) => { d.work_state = e.target.value; d.work_state_auto = false; persist(); $("#p-work_state-auto", fieldsEl).textContent = ""; });
    }
    fieldsEl.querySelectorAll("input[name]:not([type=radio])").forEach((inp) => {
      inp.addEventListener("input", () => { d[inp.name] = inp.value; persistSoon(); });
      inp.addEventListener("blur", () => showError(inp.name));
    });
  };

  const showError = (key) => {
    const msg = validateField(key, d, auto), input = $(`#p-${key}`, main), err = $(`#p-${key}-err`, main);
    if (!input || !err) return msg;
    input.setAttribute("aria-invalid", msg ? "true" : "false");
    err.innerHTML = msg ? `${icon("i-alert")}<span>${esc(msg)}</span>` : "";
    return msg;
  };
  let timer;
  const persist = () => { state.completedAt = null; save(state); $("#p-saved", main).textContent = "Draft saved on this device."; };
  const persistSoon = () => { clearTimeout(timer); timer = setTimeout(persist, 400); };

  await renderFields();
  $("#p-form", main).addEventListener("submit", (e) => {
    e.preventDefault(); persist();
    const errors = Object.keys(F).filter((k) => F[k].step === step).map((k) => [k, showError(k)]).filter(([, m]) => m);
    const box = $("#p-summary", main);
    if (errors.length) {
      box.innerHTML = `<div class="notice notice--error" role="alert" tabindex="-1" id="p-errors">${icon("i-alert")}<div><strong>${errors.length === 1 ? "One answer needs" : `${errors.length} answers need`} attention:</strong>
        <ul>${errors.map(([k, m]) => `<li><a href="#p-${k}">${esc(m)}</a></li>`).join("")}</ul></div></div>`;
      $("#p-errors", box).focus(); return;
    }
    box.innerHTML = "";
    navigate(step < 3 ? `/plan?step=${step + 1}` : "/plan/review");
  });
  const ex = $("#p-example", main);
  if (ex) ex.addEventListener("click", async () => { Object.assign(d, EXAMPLE); persist(); auto = await autoValues(d); await renderFields();
    announce("Example student loaded. It is fictional; check each step or go straight to review."); });
  $("#p-clear", main).addEventListener("click", () => clearPlan());
}

async function clearPlan() {
  if (await confirmAction("Clear your plan?", "This deletes all your saved answers from this browser. You can't undo this.", "Clear plan")) {
    clearAll(); announce("Your plan was cleared."); navigate("/plan?step=1");
  }
}

// ── review ────────────────────────────────────────────────────────────────
const show = (k, d) => {
  const v = d[k];
  if (v === undefined || v === null || String(v).trim() === "") return `<span class="meta">Not entered</span>`;
  if (k === "in_state") return v === "no" ? "Out-of-state" : "In-state";
  if (F[k] && F[k].money) return money(Number(clean(v)));
  if (k === "rate" || k === "repay_pct") return `${esc(clean(v))}%`;
  if (k === "major") return esc(String(v).replace(/\.$/, ""));
  return esc(v);
};

export async function planReviewPage(main) {
  const state = load(), d = state.draft;
  const auto = await autoValues(d);
  const missing = missingRequired(d, auto);
  const group = (title, step, keys) => `<section class="card review-group" aria-labelledby="rv-${step}">
      <div><h2 id="rv-${step}">${title}</h2><dl class="facts">${keys.map((k) => `<dt>${esc(k === "school" ? "School" : F[k].label)}</dt><dd>${k === "school" ? esc(d.school_label || "") || '<span class="meta">Not entered</span>' : show(k, d)}</dd>`).join("")}</dl></div>
      <a class="button button--secondary" href="/plan?step=${step}" data-link aria-label="Edit ${title}">${icon("i-edit")}Edit</a></section>`;
  const assumptions = [
    !clean(d.tuition) && auto.tuition != null ? `Tuition: ${money(auto.tuition)} from College Scorecard (${esc(auto.tuition_note)}).` : null,
    !clean(d.salary_mid) && auto.salary != null ? `Expected salary: ${money(auto.salary)}, the historical median for your program.` : null,
    !clean(d.rate) ? "Interest rate: 6.52%, the 2026–27 federal undergraduate loan rate." : null,
    !clean(d.repay_pct) ? "Loan payments: 10% of salary, never less than the standard 10-year payment." : null,
    "Costs stay the same each year; savings don't grow; loans build simple interest until repayment starts 6 months after a May graduation.",
  ].filter(Boolean);
  main.innerHTML = `<header class="page-header"><h1>Review your answers</h1>
      <p class="lead">Check each group. Edit anything before we calculate.</p>${progress(4)}</header>
    ${missing.length ? `<div class="notice notice--warning" role="alert">${icon("i-alert")}<div><strong>Some required answers are missing:</strong>
      <ul>${missing.map((k) => `<li><a href="/plan?step=${F[k].step}" data-link>${esc(k === "school" ? "School" : F[k].label)}</a></li>`).join("")}</ul></div></div>` : ""}
    <div class="stack section">
      ${group("Education", 1, ["school", "major", "credential", "in_state", "start_year", "grad_year"])}
      ${group("Funding", 2, ["tuition", "living", "grants", "savings", "contribution", "borrowing", "existing_debt", "rate"])}
      ${group("Career", 3, ["occupation", "work_state", "salary_low", "salary_mid", "salary_high", "repay_pct"])}
      <section class="card" aria-labelledby="rv-assume"><h2 id="rv-assume">Assumptions GradPath will use</h2>
        <ul>${assumptions.map((a) => `<li>${a}</li>`).join("")}</ul></section>
    </div>
    <div class="actions actions--split step-footer">
      <a class="button button--secondary" href="/plan?step=3" data-link>${icon("i-back")}Back</a>
      <button type="button" class="button button--primary" id="rv-calc" ${missing.length ? "disabled aria-describedby=\"rv-why\"" : ""}>Calculate my plan${icon("i-next")}</button>
    </div>
    ${missing.length ? `<p class="meta" id="rv-why" style="text-align:right">Add the missing answers to calculate.</p>` : ""}
    <div class="secondary-zone"><span class="meta">Saved only on this device.</span>
      <button type="button" class="button button--danger-text" id="rv-clear">${icon("i-trash")}Clear plan</button></div>`;
  $("#rv-calc", main).addEventListener("click", () => { state.completedAt = new Date().toISOString(); save(state); navigate("/plan/results"); });
  $("#rv-clear", main).addEventListener("click", () => clearPlan());
}

/** Notes come from the calculator; drop reference codes and editor hints students don't need. */
const studentText = (t) => t.replace(/ \(FSA [^)]*\)/g, "").replace(/ — editable/g, "").replace(/ %:/g, ":")
  .replace(/^Loan interest rate: Assumed /, "Loan interest rate: ").replace(/Scorecard /g, "College Scorecard ");

// ── results ───────────────────────────────────────────────────────────────
const SERIES = [["balance_conservative", "Conservative", "var(--chart-1)", ""], ["balance_expected", "Expected", "var(--chart-2)", ""],
                ["balance_aspirational", "Aspirational", "var(--chart-3)", ""], ["balance_standard", "Standard 10-year plan", "var(--chart-ref)", "6 5"]];

function timelineChart(rows) {
  const W = 760, H = 300, L = 64, R = 16, T = 12, B = 36;
  const xs = rows.map((r) => r.year), x0 = Math.min(...xs), x1 = Math.max(...xs);
  const ymax = Math.max(...rows.flatMap((r) => SERIES.map(([k]) => r[k] || 0))) || 1;
  const sx = (x) => L + ((x - x0) / Math.max(1e-9, x1 - x0)) * (W - L - R);
  const sy = (y) => T + (1 - y / ymax) * (H - T - B);
  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * ymax);
  const step = Math.max(1, Math.ceil((x1 - x0) / 8));
  const xTicks = []; for (let y = Math.ceil(x0); y <= Math.floor(x1); y += step) xTicks.push(y);
  const lines = SERIES.filter(([k]) => rows.some((r) => r[k] != null)).map(([k, , color, dash]) =>
    `<path d="${rows.filter((r) => r[k] != null).map((r, i) => `${i ? "L" : "M"}${sx(r.year).toFixed(1)},${sy(r[k]).toFixed(1)}`).join("")}"
      fill="none" stroke="${color}" stroke-width="3" ${dash ? `stroke-dasharray="${dash}"` : ""} stroke-linejoin="round"/>`).join("");
  return `<svg class="svg-chart" viewBox="0 0 ${W} ${H}" role="img" aria-labelledby="tl-title tl-desc">
    <title id="tl-title">Loan balance over time</title>
    <desc id="tl-desc">Remaining loan balance by year for each salary scenario. A table version follows.</desc>
    ${yTicks.map((y) => `<line x1="${L}" x2="${W - R}" y1="${sy(y)}" y2="${sy(y)}" stroke="#e5dbd2"/>
      <text x="${L - 8}" y="${sy(y) + 4}" text-anchor="end" font-size="12" fill="#5b4f47">${y >= 1000 ? `$${Math.round(y / 1000)}K` : money(y)}</text>`).join("")}
    ${xTicks.map((y) => `<text x="${sx(y)}" y="${H - 12}" text-anchor="middle" font-size="12" fill="#5b4f47">${y}</text>`).join("")}
    ${lines}</svg>
    <div class="legend">${SERIES.filter(([k]) => rows.some((r) => r[k] != null)).map(([, name, color, dash]) =>
      `<span><i class="${dash ? "dashed" : ""}" style="border-color:${color}"></i>${name}</span>`).join("")}</div>`;
}

export async function planResultsPage(main) {
  const state = load(), d = state.draft;
  const auto = await autoValues(d);
  if (!state.completedAt || missingRequired(d, auto).length) {
    main.innerHTML = `<header class="page-header"><h1>Your plan</h1></header>
      <div class="empty"><h2>No plan yet</h2>
        <p>Add your school and financial assumptions to calculate your funding and repayment scenarios.</p>
        <a class="button button--primary" href="/plan${Object.values(d).some(Boolean) ? "/edit" : ""}" data-link>Start my plan</a></div>`;
    return;
  }
  main.innerHTML = `<header class="page-header"><h1>Your plan</h1><p class="lead">${esc(d.school_label || "")}${d.major ? ` · ${esc(String(d.major).replace(/\.$/, ""))}` : ""}${d.credential ? ` · ${esc(d.credential)}` : ""}</p>
      <div class="actions"><a class="button button--secondary" href="/plan/edit" data-link>${icon("i-edit")}Edit plan</a></div></header>
    <div id="rs-body">${loading("Calculating your plan")}</div>`;
  let r;
  try {
    const body = Object.fromEntries(Object.keys(F).map((k) => [k, clean(d[k]) === "" ? null : String(d[k]).trim()]));
    r = await apiPost("/plan/calculate", body);
  } catch (e) { $("#rs-body", main).innerHTML = errorBox(`We couldn't calculate your plan (${esc(e.message)}). Check that GradPath is running, then try again.`); return; }
  const e = r.estimate, sc = r.scenarios.filter((s) => s.starting_salary);
  const pays = sc.map((s) => s.monthly_payment);
  const warn = r.notes.filter((n) => n.type.includes("Input check"));
  const missing = r.notes.filter((n) => n.type.includes("Missing"));
  const assumptions = r.notes.filter((n) => n.type.includes("Assumption"));
  const inputs = r.notes.filter((n) => n.type.includes("You entered"));
  const tag = (t, cls) => `<span class="tag tag--${cls}">${t}</span>`;
  const card = (title, value, note, hl = false) => `<div class="card kpi ${hl ? "card--highlight" : ""}">${tag("Estimate", "estimate")}
    <span class="kpi__label">${esc(title)}</span><span class="kpi__value">${value}</span><span class="kpi__note">${note}</span></div>`;
  const yearly = r.timeline.filter((row, i) => i === 0 || /^Oct /.test(row.month) || i === r.timeline.length - 1);
  $("#rs-body", main).innerHTML = `
    ${warn.length ? `<div class="notice notice--warning" role="alert">${icon("i-alert")}<div><strong>Check these answers:</strong><ul>${warn.map((w) => `<li>${esc(w.detail)}</li>`).join("")}</ul>
      <a href="/plan/edit" data-link>Edit my answers</a></div></div>` : ""}
    <section aria-label="Key results" class="grid grid--4 section">
      ${card("Estimated funding gap", money(e.funding_gap), `Total cost ${money(e.total_education_cost)} minus grants and savings, before borrowing.`)}
      ${card("Debt when repayment begins", money(e.debt_at_repayment_start), `In ${esc(e.repayment_start)}, including ${money(e.accrued_interest_before_repayment)} of interest built up in school.`)}
      ${card("Estimated monthly payment", `${money(e.standard_monthly_payment, true)}<span class="kpi__note"> /month</span>`, pays.length ? `Standard 10-year payment. Your scenarios: ${money(Math.min(...pays), true)} to ${money(Math.max(...pays), true)}.` : "Standard 10-year payment.")}
      ${card("Estimated debt-free range", esc(e.debt_free_range), esc(e.repayment_time_range), true)}
    </section>
    ${e.debt_at_repayment_start > 0 ? `<section class="section card" aria-labelledby="tl-h"><h2 id="tl-h">Loan balance over time</h2>
      ${timelineChart(r.timeline)}
      <details class="accordion" style="margin-top:var(--space-4)"><summary>View the balance as a table</summary><div>
      ${table({ caption: "Remaining balance each October", rows: yearly, columns: [{ label: "Month", key: "month" },
        ...SERIES.filter(([k]) => r.timeline.some((x) => x[k] != null)).map(([k, n]) => ({ label: n, num: true, value: (x) => money(x[k]) }))] })}</div></details></section>` : ""}
    <section class="section" aria-labelledby="sc-h"><h2 id="sc-h">Salary scenarios</h2>
      ${table({ caption: "Repayment under each starting salary", rows: r.scenarios, columns: [
        { label: "Scenario", key: "scenario" }, { label: "Starting salary", num: true, value: (s) => money(s.starting_salary) },
        { label: "Salary source", value: (s) => s.salary_source },
        { label: "Monthly payment", num: true, value: (s) => s.monthly_payment == null ? "—" : money(s.monthly_payment, true) },
        { label: "Share of pay", num: true, value: (s) => s.payment_share_of_gross_pct == null ? "—" : `${s.payment_share_of_gross_pct}%` },
        { label: "Time to repay", key: "time_to_repay" }, { label: "Final payment", key: "debt_free_date" },
        { label: "Total interest", num: true, value: (s) => money(s.total_interest) },
        { label: "Est. state income tax / yr", num: true, value: (s) => money(s.est_state_income_tax) }] })}
      <p class="meta">State tax: ${esc((r.scenarios.find((s) => s.state_tax_note) || {}).state_tax_note || "")}.</p></section>
    <section class="section" aria-labelledby="more-h"><h2 id="more-h">More details</h2><div class="grid grid--4">
      <div class="card kpi">${tag("Estimate", "estimate")}<span class="kpi__label">Savings coverage</span><span class="kpi__value">${e.savings_coverage_pct ?? "—"}%</span><span class="kpi__note">Share of total cost paid from your savings.</span></div>
      <div class="card kpi">${tag("Estimate", "estimate")}<span class="kpi__label">Total interest (standard plan)</span><span class="kpi__value">${money(e.standard_total_interest)}</span><span class="kpi__note">Over 10 years of payments.</span></div>
      <div class="card kpi">${tag("Your input", "input")}<span class="kpi__label">Scholarships and grants</span><span class="kpi__value">${money(e.grants_total)}</span><span class="kpi__note">Across ${e.years_in_school} years.</span></div>
      <div class="card kpi">${tag("Scorecard data", "data")}<span class="kpi__label">Historical median earnings</span><span class="kpi__value">${money(e.historical_median_earnings)}</span><span class="kpi__note">${esc(e.confidence)}</span></div>
    </div></section>
    <section class="section grid grid--2" aria-label="Assumptions and missing information">
      <div class="card"><h2>Important assumptions</h2><ul>${assumptions.map((a) => `<li>${esc(studentText(a.detail))}</li>`).join("")}</ul></div>
      <div class="card"><h2>Missing information</h2>${missing.length ? `<ul>${missing.map((m) => `<li>${esc(m.detail)}</li>`).join("")}</ul><a href="/plan/edit" data-link>Add these answers</a>` : "<p>Nothing important is missing.</p>"}
        ${inputs.length ? `<h3 style="margin-top:var(--space-4)">Values you entered</h3><ul>${inputs.map((m) => `<li>${esc(m.detail.replace(": You entered", ""))}</li>`).join("")}</ul>` : ""}</div>
    </section>
    <details class="accordion section"><summary>See how this estimate was calculated</summary><div>
      <ol>${r.explanation.map((s) => `<li><strong>${esc(s.title)}.</strong> ${esc(s.detail)}</li>`).join("")}</ol>
      ${r.milestones.length ? table({ caption: "Repayment milestones", rows: r.milestones, columns: [{ label: "When", key: "date" }, { label: "Scenario", key: "scenario" },
        { label: "Milestone", key: "milestone" }, { label: "Balance left", num: true, value: (m) => money(m.balance_left) }, { label: "Interest paid so far", num: true, value: (m) => money(m.interest_paid_so_far) }] }) : ""}
    </div></details>
    <div class="secondary-zone"><span class="meta">Your answers are saved only on this device and never appear in the page address. Historical data: College Scorecard. Educational estimates, not financial advice.</span>
      <button type="button" class="button button--danger-text" id="rs-clear">${icon("i-trash")}Clear plan</button></div>`;
  $("#rs-clear", main).addEventListener("click", () => clearPlan());
}
