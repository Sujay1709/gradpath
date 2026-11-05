// GradPath app shell: routing, navigation, shared context and UI helpers.
import { overviewPage, schoolsPage, graphsPage, graphDetailPage, statesPage, helpPage } from "./pages.js";
import { planStepPage, planReviewPage, planResultsPage } from "./plan.js";

export const DATA_YEAR = "Graduates of 2021–22, earnings measured 2023–24";
export const FILTER_KEYS = ["school", "major", "state", "credential", "cip", "school_type"];

const NAV = [
  { path: "/", label: "Overview", icon: "i-home", carry: FILTER_KEYS },
  { path: "/plan", label: "My Plan", icon: "i-plan", carry: [] },
  { path: "/schools", label: "Schools", icon: "i-school", carry: FILTER_KEYS },
  { path: "/graphs", label: "Graphs", icon: "i-chart", carry: ["major", "state", "credential", "school", "cip", "school_type"] },
  { path: "/states", label: "States", icon: "i-map", carry: ["state"] },
  { path: "/help", label: "Help", icon: "i-help", carry: [] },
];

const ROUTES = [
  [/^\/$/, overviewPage, "/"],
  [/^\/schools$/, schoolsPage, "/schools"],
  [/^\/graphs$/, graphsPage, "/graphs"],
  [/^\/graphs\/([a-z-]+)$/, graphDetailPage, "/graphs"],
  [/^\/states$/, statesPage, "/states"],
  [/^\/help$/, helpPage, "/help"],
  [/^\/plan$/, planStepPage, "/plan"],
  [/^\/plan\/edit$/, (el, ctx) => { history.replaceState(null, "", "/plan?step=1"); return planStepPage(el, ctx); }, "/plan"],
  [/^\/plan\/review$/, planReviewPage, "/plan"],
  [/^\/plan\/results$/, planResultsPage, "/plan"],
];

// ── tiny DOM + formatting helpers ─────────────────────────────────────────
export const $ = (sel, root = document) => root.querySelector(sel);
export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export const icon = (id, cls = "icon") => `<svg class="${cls}" aria-hidden="true"><use href="#${id}"/></svg>`;
export const money = (v, cents = false) => (v === null || v === undefined || Number.isNaN(v)) ? "—"
  : `$${Number(v).toLocaleString("en-US", { minimumFractionDigits: cents ? 2 : 0, maximumFractionDigits: cents ? 2 : 0 })}`;
export const num = (v) => (v === null || v === undefined) ? "—" : Number(v).toLocaleString("en-US");
export const ratio = (v) => (v === null || v === undefined) ? "—" : Number(v).toFixed(2);

/** Debt-to-earnings shown with words and a shape, never colour alone. */
export function band(v) {
  if (v === null || v === undefined) return "—";
  const [cls, word] = v < 0.5 ? ["low", "Lower"] : v < 1 ? ["mid", "Moderate"] : ["high", "Higher"];
  return `<span class="band band--${cls}">${ratio(v)} <span class="visually-hidden">(</span>${word}<span class="visually-hidden">)</span></span>`;
}

export function announce(msg) {
  const a = $("#announcer");
  a.textContent = "";
  setTimeout(() => { a.textContent = msg; }, 50);
}

// ── API ──────────────────────────────────────────────────────────────────
const cache = new Map();
export async function api(path, params = {}) {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== "") q.set(k, v); });
  const url = `${path}${q.toString() ? "?" + q : ""}`;
  if (!cache.has(url)) {
    cache.set(url, fetch(url, { headers: { Accept: "application/json" } }).then((r) => {
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      return r.json();
    }).catch((e) => { cache.delete(url); throw e; }));
  }
  return cache.get(url);
}
export async function apiPost(path, body) {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body) });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

// ── Context: non-personal filters live in the page URL so pages can share them ──
export function readContext() {
  const q = new URLSearchParams(location.search);
  const ctx = {};
  FILTER_KEYS.forEach((k) => { if (q.get(k)) ctx[k] = q.get(k); });
  return ctx;
}
export function hrefWith(path, ctx, keys = FILTER_KEYS) {
  const q = new URLSearchParams();
  keys.forEach((k) => { if (ctx[k]) q.set(k, ctx[k]); });
  return q.toString() ? `${path}?${q}` : path;
}
export function setContext(ctx, { replace = false } = {}) {
  const extra = new URLSearchParams(location.search);
  FILTER_KEYS.forEach((k) => extra.delete(k));
  const q = new URLSearchParams();
  FILTER_KEYS.forEach((k) => { if (ctx[k]) q.set(k, ctx[k]); });
  extra.forEach((v, k) => q.set(k, v));
  const url = q.toString() ? `${location.pathname}?${q}` : location.pathname;
  history[replace ? "replaceState" : "pushState"](null, "", url);
  renderNav();
}

// ── Navigation ────────────────────────────────────────────────────────────
function activeSection() {
  const m = ROUTES.find(([re]) => re.test(location.pathname));
  return m ? m[2] : "/";
}
export function renderNav() {
  const ctx = readContext();
  const current = activeSection();
  $("#primary-nav").innerHTML = `<ul>${NAV.map((n) => `
    <li><a href="${esc(hrefWith(n.path, ctx, n.carry))}" data-link ${n.path === current ? 'aria-current="page"' : ""}>
      ${icon(n.icon)}<span>${n.label}</span></a></li>`).join("")}</ul>`;
}
function setMenu(open) {
  $(".menu-button").setAttribute("aria-expanded", String(open));
  $("#primary-nav").classList.toggle("is-open", open);
}

export function navigate(url, { replace = false } = {}) {
  history[replace ? "replaceState" : "pushState"](null, "", url);
  render({ focus: true });
}

let renderToken = 0;
async function render({ focus = false } = {}) {
  const token = ++renderToken;
  setMenu(false);
  renderNav();
  const main = $("#main");
  const match = ROUTES.map(([re, fn]) => [re.exec(location.pathname), fn]).find(([m]) => m);
  main.innerHTML = `<div class="skeleton" aria-hidden="true"></div>`;
  try {
    if (!match) {
      main.innerHTML = `<div class="page-header"><h1 tabindex="-1">Page not found</h1>
        <p class="lead">That page doesn't exist. <a href="/" data-link>Go to the Overview</a>.</p></div>`;
    } else {
      await match[1](main, readContext(), ...match[0].slice(1));
    }
  } catch (e) {
    if (token !== renderToken) return;
    main.innerHTML = errorBox(`Something went wrong loading this page (${esc(e.message)}). Check that the GradPath API is running, then reload.`);
  }
  if (token !== renderToken) return;
  const h1 = $("h1", main);
  document.title = h1 ? `${h1.textContent.trim()} · GradPath` : "GradPath";
  if (focus && h1) {
    h1.setAttribute("tabindex", "-1");
    h1.focus({ preventScroll: false });
    window.scrollTo(0, 0);
  }
  if (focus) announce(`${document.title} loaded`);
}

// ── Shared components ─────────────────────────────────────────────────────
export const errorBox = (msg) => `<div class="notice notice--error" role="alert">${icon("i-alert")}<div>${msg}</div></div>`;
export const infoBox = (msg) => `<div class="notice notice--info">${icon("i-info")}<div>${msg}</div></div>`;
export const loading = (label = "Loading") => `<div class="skeleton" role="status" aria-label="${esc(label)}"></div>`;

/** Accessible table: horizontal scroll on wide screens, cards on phones. */
export function table({ caption, columns, rows, empty = "No matching records." }) {
  if (!rows.length) return infoBox(esc(empty));
  const head = columns.map((c) => `<th scope="col" class="${c.num ? "num" : ""}">${esc(c.label)}</th>`).join("");
  const body = rows.map((r) => `<tr>${columns.map((c) =>
    `<td data-label="${esc(c.label)}" class="${c.num ? "num" : ""}">${c.html ? c.html(r) : esc(c.value ? c.value(r) : r[c.key])}</td>`).join("")}</tr>`).join("");
  return `<div class="table-wrap" role="region" aria-label="${esc(caption)}" tabindex="0">
    <table class="table--cards"><caption>${esc(caption)}</caption><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

/** Confirm dialog; resolves true only if the user chooses the destructive action. */
export function confirmAction(title, body, okLabel = "Clear") {
  const dlg = $("#confirm-dialog");
  $("#confirm-title").textContent = title;
  $("#confirm-body").textContent = body;
  $("#confirm-ok").textContent = okLabel;
  return new Promise((resolve) => {
    dlg.addEventListener("close", () => resolve(dlg.returnValue === "confirm"), { once: true });
    dlg.showModal();
  });
}

// ── Global listeners ──────────────────────────────────────────────────────
document.addEventListener("click", (e) => {
  const a = e.target.closest("a[data-link]");
  if (!a || e.metaKey || e.ctrlKey || e.shiftKey || a.target === "_blank") return;
  const url = new URL(a.href, location.href);
  if (url.origin !== location.origin) return;
  e.preventDefault();
  if (url.pathname + url.search === location.pathname + location.search) { setMenu(false); return; }
  navigate(url.pathname + url.search + url.hash);
});
$(".menu-button").addEventListener("click", () => setMenu($(".menu-button").getAttribute("aria-expanded") !== "true"));
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && $("#primary-nav").classList.contains("is-open")) { setMenu(false); $(".menu-button").focus(); }
});
window.addEventListener("popstate", () => render({ focus: true }));
render();
