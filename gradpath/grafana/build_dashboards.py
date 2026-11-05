"""
Generate every GradPath Grafana dashboard from one place.

    python3 grafana/build_dashboards.py          # write JSON into grafana/dashboards/
    python3 grafana/build_dashboards.py --check  # validate without writing

Navigation, shared variables, page headers and footers are defined once here,
so all pages stay consistent. The output JSON is committed; Grafana's file
provisioner (provisioning/dashboards/gradpath.yaml) loads it into the
"GradPath" folder.
"""
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "dashboards")
CLASSIC_MAIN = os.path.join(OUT, "gradpath_main.json")
CLASSIC_TAX = os.path.join(OUT, "gradpath_tax.json")

DS = {"type": "marcusolsson-json-datasource", "uid": "gradpath-api"}
API_BASE = "http://localhost:8000"          # FastAPI (serves the My Plan form)
APP_TAG = "gradpath-app"
SOURCE_URL = "https://collegescorecard.ed.gov/data/"
DATA_YEAR = "2021–22 completers (earnings measured 2023–24)"

SHARED = ["school", "state", "major", "cip", "credential", "school_type", "data_year"]
PLAN_VARS = ["in_state", "start_year", "grad_year", "savings", "contribution", "grants", "existing_debt",
             "borrowing", "rate", "tuition", "living", "occupation", "work_state", "salary_low", "salary_mid",
             "salary_high", "repay_pct"]

PAGES = [  # (label, uid, icon)
    ("Overview", "gradpath-overview", "🏠"),
    ("My Plan", "gradpath-my-plan", "🧭"),
    ("Schools", "gradpath-schools", "🏫"),
    ("States & Taxes", "gradpath-states", "🗺️"),
    ("Graphs", "gradpath-graphs", "📊"),
    ("Help", "gradpath-help", "❓"),
]
GRAPHS = [  # (uid, title, icon, one-line description)
    ("gradpath-graph-debt-earnings", "Debt vs. Earnings", "⚖️",
     "Every program as a dot: what graduates borrowed against what they earned."),
    ("gradpath-graph-rankings", "Degree ROI Rankings", "🏆",
     "Programs ranked by lowest debt-to-earnings ratio and by highest earnings."),
    ("gradpath-graph-programs", "Program Comparison", "🧪",
     "Majors side by side: typical earnings and typical debt."),
    ("gradpath-graph-states", "State Comparison", "📍",
     "How earnings and debt for matching programs differ by state."),
    ("gradpath-graph-credentials", "Credential-Level Comparison", "🎓",
     "Certificates, associate's and bachelor's degrees compared."),
]

# Okabe–Ito colour-blind-safe palette
C_PUBLIC, C_NONPROFIT, C_FORPROFIT, C_REF = "#0072B2", "#E69F00", "#CC79A7", "#8C8C8C"
C_EARN, C_DEBT = "#0072B2", "#D55E00"
ACTIVE_BG = "#2F5FD0"

GREEN_YELLOW_RED = {"mode": "absolute", "steps": [
    {"color": "green", "value": None}, {"color": "#EAB839", "value": 0.5}, {"color": "red", "value": 1.0}]}


# ── URL helpers ──────────────────────────────────────────────────────────────

def shared_qs(exclude=()):
    return "&".join(f"${{{v}:queryparam}}" for v in SHARED if v not in exclude)


def page_url(uid):
    return f"/d/{uid}?{shared_qs()}"


def plan_form_url(extra=""):
    q = "&".join(f"{v}=${{{v}:percentencode}}" for v in SHARED)
    return f"{API_BASE}/plan?{q}{extra}"


def nav_href(uid):
    # "My Plan" goes through the form, which reopens the student's saved answers
    return plan_form_url("&resume=1") if uid == "gradpath-my-plan" else page_url(uid)


# ── Panel builders ───────────────────────────────────────────────────────────

class Page:
    """Collects panels for one dashboard, assigning ids and grid positions."""

    def __init__(self):
        self.panels, self.y, self.x, self.row_h, self._id = [], 0, 0, 0, 0

    def next_id(self):
        self._id += 1
        return self._id

    def add(self, panel, w=24, h=4, container=None):
        if self.x + w > 24:
            self.newline()
        panel["id"] = self.next_id()
        panel["gridPos"] = {"x": self.x, "y": self.y, "w": w, "h": h}
        (container if container is not None else self.panels).append(panel)
        self.x += w
        self.row_h = max(self.row_h, h)
        return panel

    def newline(self):
        if self.x:
            self.y += self.row_h
        self.x, self.row_h = 0, 0

    def row(self, title, collapsed=False):
        self.newline()
        r = {"type": "row", "title": title, "collapsed": collapsed, "panels": []}
        self.add(r, 24, 1)
        self.newline()
        return r["panels"] if collapsed else None


def text(content, title="", mode="markdown", transparent=False, description=""):
    return {"type": "text", "title": title, "transparent": transparent, "description": description,
            "options": {"mode": mode, "content": content,
                        "code": {"language": "plaintext", "showLineNumbers": False, "showMiniMap": False}}}


def target(path, fields, ref="A", extra_params=(), plan=False, group_by=None):
    params = [[v, f"${{{v}}}"] for v in SHARED]
    if plan:
        params += [[v, f"${{{v}}}"] for v in PLAN_VARS]
    params += [list(p) for p in extra_params]
    t = {"refId": ref, "datasource": DS, "method": "GET", "urlPath": path, "params": params,
         "cacheDurationSeconds": 60,
         "fields": [{"jsonPath": f"$[*].{name}", "name": name, **({"type": typ} if typ else {})}
                    for name, typ in fields]}
    if group_by:
        t["experimentalGroupByField"] = group_by
    return t


def money(name, label):
    """Full dollar amounts in tables ("36,425"), since currencyUSD shortens them to "$36K"."""
    return {"matcher": {"id": "byName", "options": name},
            "properties": [{"id": "unit", "value": "locale"}, {"id": "decimals", "value": 0},
                           {"id": "displayName", "value": f"{label} ($)"}]}


def rename(name, label, *props):
    return {"matcher": {"id": "byName", "options": name},
            "properties": [{"id": "displayName", "value": label}, *props]}


def ratio(name="debt_to_earnings", label="Debt ÷ earnings", cell=True):
    props = [{"id": "decimals", "value": 2}, {"id": "displayName", "value": label},
             {"id": "thresholds", "value": GREEN_YELLOW_RED}, {"id": "color", "value": {"mode": "thresholds"}}]
    if cell:
        props.append({"id": "custom.cellOptions", "value": {"type": "color-background", "mode": "basic"}})
    return {"matcher": {"id": "byName", "options": name}, "properties": props}


def hidden(name):
    return {"matcher": {"id": "byName", "options": name}, "properties": [{"id": "custom.hidden", "value": True}]}


def link_cell(name, label, title="Open"):
    return rename(name, label, {"id": "links", "value": [{"title": title, "url": "${__value.raw}",
                                                          "targetBlank": True}]})


def stat(title, path, field, unit=None, decimals=0, description="", plan=False, no_value="—",
         text_mode="value", extra_params=(), typ=None):
    fc = {"defaults": {"noValue": no_value, "color": {"mode": "fixed", "fixedColor": "text"}}, "overrides": []}
    if unit:
        fc["defaults"]["unit"] = unit
    if decimals is not None:
        fc["defaults"]["decimals"] = decimals
    return {"type": "stat", "title": title, "description": description, "datasource": DS,
            "targets": [target(path, [(field, typ)], plan=plan, extra_params=extra_params)],
            "fieldConfig": fc,
            "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": f"/^{field}$/", "values": False},
                        "orientation": "auto", "textMode": text_mode, "colorMode": "none",
                        "graphMode": "none", "justifyMode": "auto", "wideLayout": True,
                        "showPercentChange": False}}


def table(title, path, fields, overrides, description="", plan=False, extra_params=(),
          no_value="No matching records — try widening the filters.", transformations=None, wrap=False):
    defaults = {"noValue": no_value, "custom": {"align": "auto", "filterable": True,
                                                "cellOptions": {"type": "auto", "wrapText": wrap}}}
    return {"type": "table", "title": title, "description": description, "datasource": DS,
            "targets": [target(path, fields, plan=plan, extra_params=extra_params)],
            "fieldConfig": {"defaults": defaults, "overrides": overrides},
            "options": {"showHeader": True, "cellHeight": "sm", "footer": {"show": False}, "sortBy": []},
            "transformations": transformations or []}


def facts_table(title, path, fields_labels, description="", plan=False, no_value="Nothing selected yet.",
                extra_params=()):
    """One API row shown as a two-column 'Detail | Value' card (Transpose)."""
    organize = {"id": "organize", "options": {
        "indexByName": {f: i for i, (f, _) in enumerate(fields_labels)},
        "renameByName": {f: label for f, label in fields_labels}}}
    transpose = {"id": "transpose", "options": {"firstFieldName": "Detail", "restFieldsName": "Value"}}
    p = table(title, path, [(f, "string") for f, _ in fields_labels], [], description=description, plan=plan,
              transformations=[organize, transpose], no_value=no_value, wrap=True, extra_params=extra_params)
    p["fieldConfig"]["defaults"]["custom"]["filterable"] = False
    p["options"]["showHeader"] = False
    return p


def barchart(title, path, x_field, series, description="", horizontal=True, extra_params=(), legend=True):
    """series: list of (field, label, colour)."""
    overrides = [{"matcher": {"id": "byName", "options": f},
                  "properties": [{"id": "displayName", "value": label},
                                 {"id": "color", "value": {"mode": "fixed", "fixedColor": colour}}]}
                 for f, label, colour in series]
    return {"type": "barchart", "title": title, "description": description, "datasource": DS,
            "targets": [target(path, [(x_field, None)] + [(f, "number") for f, _, _ in series],
                               extra_params=extra_params)],
            "fieldConfig": {"defaults": {"unit": "currencyUSD", "decimals": 0, "noValue": "No data for these filters",
                                         "custom": {"fillOpacity": 85, "lineWidth": 0, "axisPlacement": "auto"}},
                            "overrides": overrides},
            "options": {"xField": x_field, "orientation": "horizontal" if horizontal else "vertical",
                        "barRadius": 0.05, "groupWidth": 0.75, "barWidth": 0.9, "showValue": "never",
                        "xTickLabelRotation": 0, "xTickLabelSpacing": 0, "stacking": "none",
                        "legend": {"showLegend": legend, "displayMode": "list", "placement": "bottom", "calcs": []},
                        "tooltip": {"mode": "multi", "sort": "none"}}}


# ── Shared page parts ────────────────────────────────────────────────────────

def nav_panel(active_uid):
    pill = ("display:inline-block;padding:6px 14px;border-radius:999px;text-decoration:none;font-size:14px;"
            "line-height:20px;white-space:nowrap;")
    off = pill + "background:rgba(128,128,128,0.16);color:inherit;"
    on = pill + f"background:{ACTIVE_BG};color:#ffffff;font-weight:600;"
    links = []
    for label, uid, icon in PAGES:
        cur = ' aria-current="page"' if uid == active_uid else ""
        style = on if uid == active_uid else off
        links.append(f'<a href="{nav_href(uid)}" style="{style}"{cur}>{icon} {label}</a>')
    html = (
        '<nav aria-label="GradPath pages" style="display:flex;flex-wrap:wrap;gap:6px;align-items:center;">'
        f'<a href="{page_url("gradpath-overview")}" style="font-weight:700;font-size:17px;text-decoration:none;'
        'color:inherit;margin-right:10px;white-space:nowrap;">🎓 GradPath</a>'
        + "".join(links) + "</nav>"
    )
    return text(html, mode="html", transparent=True)


def header(title, subtitle, back_to_graphs=False):
    back = (f'<a href="{page_url("gradpath-graphs")}" style="text-decoration:none;font-size:14px;">← Back to Graphs</a>'
            if back_to_graphs else "")
    html = (f'<div>{back}<h1 style="font-size:30px;line-height:1.2;margin:2px 0 4px;font-weight:700;">{title}</h1>'
            f'<p style="font-size:15px;opacity:0.8;margin:0;max-width:75ch;">{subtitle}</p></div>')
    return text(html, mode="html", transparent=True)


def active_filters():
    return text("**Showing:** School: **${school:text}** · State: **${state:text}** · Major: **${major:text}** · "
                "CIP: **${cip:text}** · Credential: **${credential:text}** · School type: **${school_type:text}** · "
                "Data year: **${data_year:text}**  \nChange these in the boxes at the top of the page — they follow "
                "you to every GradPath page.", transparent=True)


def footer(extra=""):
    return text(f"<small>📘 **Source:** U.S. Department of Education, [College Scorecard]({SOURCE_URL}) — Field of Study "
                f"and Institution files (release 2026-10-05). **Data year:** {DATA_YEAR}. {extra} Historical outcomes, "
                f"not guarantees. [How these numbers work →]({page_url('gradpath-help')})</small>", transparent=True)


def option_var(name, label, path, deps=(), hide=0):
    query = {"method": "GET", "urlPath": path, "cacheDurationSeconds": 300,
             "params": [[d, f"${{{d}}}"] for d in deps],
             "fields": [{"jsonPath": "$[*].text", "name": "text"}, {"jsonPath": "$[*].value", "name": "value"}],
             "experimentalVariableTextField": "text", "experimentalVariableValueField": "value"}
    return {"name": name, "label": label, "type": "query", "datasource": DS, "query": query,
            "definition": path, "refresh": 1, "includeAll": True, "allValue": "__all", "multi": False,
            "current": {"selected": True, "text": "All", "value": "$__all"}, "options": [], "sort": 0,
            "hide": hide, "skipUrlSync": False, "allowCustomValue": False}


def shared_variables():
    # Dependency order has no cycles: credential, school_type → state → major → cip → school
    return [
        option_var("school", "School (type to search)", "/options/schools",
                   deps=("state", "school_type", "credential", "major", "cip")),
        option_var("state", "State", "/options/states", deps=("school_type", "credential")),
        option_var("major", "Major", "/options/majors", deps=("state", "school_type", "credential")),
        option_var("cip", "CIP code", "/options/cips", deps=("state", "school_type", "credential", "major")),
        option_var("credential", "Credential", "/options/credentials"),
        option_var("school_type", "School type", "/options/school_types"),
        option_var("data_year", "Data year", "/options/data_years"),
    ]


def textbox(name, label, default="", hide=2):
    return {"name": name, "label": label, "type": "textbox", "query": default, "hide": hide,
            "current": {"text": default, "value": default},
            "options": [{"selected": True, "text": default, "value": default}]}


def dashboard(uid, title, page: Page, extra_vars=(), description=""):
    return {
        "uid": uid, "title": title, "description": description, "tags": ["gradpath", APP_TAG],
        "editable": True, "graphTooltip": 0, "schemaVersion": 39, "version": 1, "refresh": "",
        "time": {"from": "now-6h", "to": "now"}, "timepicker": {"hidden": True}, "timezone": "browser",
        "fiscalYearStartMonth": 0, "liveNow": False, "weekStart": "",
        "annotations": {"list": []},
        "links": [{"title": "All GradPath pages", "type": "dashboards", "tags": [APP_TAG], "asDropdown": True,
                   "includeVars": True, "keepTime": False, "targetBlank": False, "icon": "external link"}],
        "templating": {"list": shared_variables() + list(extra_vars)},
        "panels": page.panels,
    }


def card_html(icon, title, body, preview, href, cta="Open"):
    return (f'<div style="display:flex;flex-direction:column;height:100%;gap:6px;">'
            f'<div style="font-size:18px;font-weight:700;">{icon} {title}</div>'
            f'<div style="font-size:14px;opacity:0.85;">{body}</div>'
            f'<div style="font-size:13px;padding:6px 10px;border-radius:6px;background:rgba(128,128,128,0.12);">'
            f'{preview}</div>'
            f'<div style="margin-top:auto;"><a href="{href}" style="display:inline-block;padding:7px 16px;'
            f'border-radius:8px;background:{ACTIVE_BG};color:#ffffff;text-decoration:none;font-weight:600;'
            f'font-size:14px;">{cta} →</a></div></div>')


def fix_json_paths(panel):
    """Classic stats used "$.field", which matches nothing because every endpoint returns a list."""
    for t in panel.get("targets", []):
        for fl in t.get("fields", []):
            jp = fl.get("jsonPath", "")
            if jp.startswith("$.") and not jp.startswith("$.["):
                fl["jsonPath"] = "$[*]." + jp[2:]


_CLASSIC = None


def classic_panels():
    global _CLASSIC
    if _CLASSIC is None:
        with open(CLASSIC_MAIN) as f:
            _CLASSIC = {p["id"]: p for p in json.load(f)["panels"]}
    return _CLASSIC


def moved(panel_id, title=None, description=None):
    """Copy a Classic panel and make its query follow the shared filters."""
    p = copy.deepcopy(classic_panels()[panel_id])
    for t in p.get("targets", []):
        path, _, query = t["urlPath"].partition("?")
        t["urlPath"] = path
        fixed = [kv.split("=", 1) for kv in query.split("&") if "=" in kv]
        t["params"] = [[v, f"${{{v}}}"] for v in SHARED] + fixed
    fix_json_paths(p)
    if title:
        p["title"] = title
    if description:
        p["description"] = description
    p.pop("gridPos", None)
    return p


# ── Pages ────────────────────────────────────────────────────────────────────

def overview():
    pg = Page()
    pg.add(nav_panel("gradpath-overview"), 24, 2)
    pg.add(header("GradPath", "See what past graduates earned and borrowed, then plan your own path. "
                              "Start with the filters at the top — they follow you to every page."), 24, 3)
    pg.add(text("### Your selection\n**School:** ${school:text}  \n**Major:** ${major:text}  \n"
                "**State:** ${state:text} · **Credential:** ${credential:text} · "
                "**School type:** ${school_type:text}"), 24, 4)
    summary = "/metrics/summary_stats"
    pg.add(stat("Matching schools", summary, "matching_schools",
                description="Schools with at least one program that matches your filters."), 5, 4)
    pg.add(stat("Matching programs", summary, "matching_programs",
                description="School × major × credential combinations with published earnings and debt."), 5, 4)
    for pid, title, desc in [
        (4, "Median earnings", "The middle value of program-level median earnings, 2 years after completion."),
        (5, "Median debt", "The middle value of program-level median federal loan debt at completion."),
    ]:
        p = moved(pid, title, desc)
        p["options"]["colorMode"] = "none"
        p["fieldConfig"]["defaults"]["noValue"] = "—"
        pg.add(p, 5, 4)
    p = moved(6, "Median debt ÷ earnings", "Median of each program's debt divided by its earnings. "
                                            "0.5 means debt equals half a year of earnings.")
    p["options"]["colorMode"] = "none"
    p["fieldConfig"]["defaults"].update({"decimals": 2, "noValue": "—"})
    pg.add(p, 4, 4)

    cards = [
        ("🏫", "Explore Schools", "Search by school name, compare programs and see each school's address.",
         "Filters now: ${state:text} · ${school_type:text}", page_url("gradpath-schools")),
        ("📊", "Compare Graphs", "Five focused charts, from debt vs. earnings to state and credential comparisons.",
         f"Data: {DATA_YEAR}", page_url("gradpath-graphs")),
        ("🧭", "Build My Plan", "Enter savings, aid and borrowing to estimate your debt and payoff range.",
         "Your answers stay in this browser", plan_form_url("&resume=1")),
        ("🗺️", "Explore State Taxes", "Income-tax facts for 10 verified states, each with its tax year and source.",
         "Tax year 2025 · 10 verified states", page_url("gradpath-states")),
        ("❓", "Learn About the Data", "How medians, debt and ratios work — and what they cannot tell you.",
         "Source: U.S. Dept. of Education", page_url("gradpath-help")),
    ]
    for i, (icon, title, body, preview, href) in enumerate(cards):
        pg.add(text(card_html(icon, title, body, preview, href), mode="html"), 5 if i < 4 else 4, 7)
    pg.add(text("⚠️ **Historical estimates only — not salary guarantees.** Figures describe past completers who "
                "received federal aid; small programs are hidden for privacy.", transparent=True), 24, 2)
    pg.add(footer(), 24, 2)
    return dashboard("gradpath-overview", "GradPath — Overview", pg,
                     description="GradPath home: summary of matching programs and links to every page.")


def graphs_landing():
    pg = Page()
    pg.add(nav_panel("gradpath-graphs"), 24, 2)
    pg.add(header("Graphs", "Pick a question. Each graph opens on its own page with an explanation of what it "
                            "shows."), 24, 3)
    pg.add(active_filters(), 24, 2)
    for uid, title, icon, desc in GRAPHS:
        pg.add(text(card_html(icon, title, desc, "Uses your current filters", page_url(uid), "Open graph"),
                    mode="html"), 8, 6)
    pg.add(footer(), 24, 2)
    return dashboard("gradpath-graphs", "GradPath — Graphs", pg)


def graph_page(uid, title, intro, explain, build_main, extras=None):
    pg = Page()
    pg.add(nav_panel("gradpath-graphs"), 24, 2)
    pg.add(header(title, intro, back_to_graphs=True), 24, 4)
    pg.add(active_filters(), 24, 2)
    pg.add(build_main(), 24, 15)
    pg.add(text(explain + "\n\n*Tip: use the panel menu → **Inspect → Data** to see or download the numbers behind "
                          "this chart.*", title="How to read this graph"), 24, 6)
    if extras:
        extras(pg)
    pg.add(footer(), 24, 2)
    return dashboard(uid, f"GradPath — {title}", pg)


def scatter_panel():
    xy_series = [
        ("Public", "earnings_public"), ("Private, nonprofit", "earnings_private_nonprofit"),
        ("Private, for-profit", "earnings_private_for_profit"),
    ]
    series = [{"name": {"fixed": name}, "frame": {"matcher": {"id": "byIndex", "options": 0}},
               "x": {"matcher": {"id": "byName", "options": "median_debt"}},
               "y": {"matcher": {"id": "byName", "options": col}},
               "size": {"matcher": {"id": "byName", "options": "cohort_size"}}} for name, col in xy_series]
    series.append({"name": {"fixed": "Earnings = debt"}, "frame": {"matcher": {"id": "byIndex", "options": 1}},
                   "x": {"matcher": {"id": "byName", "options": "ref_debt"}},
                   "y": {"matcher": {"id": "byName", "options": "earnings_equal_debt"}}})
    colours = {"earnings_public": C_PUBLIC, "earnings_private_nonprofit": C_NONPROFIT,
               "earnings_private_for_profit": C_FORPROFIT}
    overrides = [{"matcher": {"id": "byName", "options": col},
                  "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": c}},
                                 {"id": "custom.axisLabel", "value": "Median earnings 2 years after completion"}]}
                 for col, c in colours.items()]
    overrides += [
        {"matcher": {"id": "byName", "options": "earnings_equal_debt"},
         "properties": [{"id": "custom.show", "value": "lines"}, {"id": "custom.lineWidth", "value": 2},
                        {"id": "custom.lineStyle", "value": {"fill": "dash", "dash": [10, 10]}},
                        {"id": "color", "value": {"mode": "fixed", "fixedColor": C_REF}}]},
        {"matcher": {"id": "byName", "options": "median_debt"},
         "properties": [{"id": "custom.axisLabel", "value": "Median debt at completion"},
                        {"id": "displayName", "value": "Median debt"}]},
        {"matcher": {"id": "byName", "options": "ref_debt"},
         "properties": [{"id": "custom.axisLabel", "value": "Median debt at completion"}]},
        {"matcher": {"id": "byName", "options": "cohort_size"},
         "properties": [{"id": "custom.pointSize", "value": {"min": 3, "max": 16}}, {"id": "unit", "value": "short"},
                        {"id": "displayName", "value": "Cohort size (graduates measured)"}]},
        {"matcher": {"id": "byName", "options": "debt_to_earnings"},
         "properties": [{"id": "unit", "value": "none"}, {"id": "decimals", "value": 2},
                        {"id": "displayName", "value": "Debt ÷ earnings"}]},
        rename("median_earnings", "Median earnings"),
        rename("school", "School"), rename("program", "Program"), rename("state", "State"),
        rename("credential", "Credential"), rename("school_type", "School type"),
    ]
    return {
        "type": "xychart", "title": "Debt vs. Earnings — one dot per program", "datasource": DS,
        "description": "X: median debt at completion. Y: median earnings 2 years after completion. Colour: school "
                       "type. Dot size: number of graduates measured. Dashed line: earnings equal debt.",
        "targets": [
            target("/metrics/scatter", [("median_debt", "number"), ("earnings_public", "number"),
                                        ("earnings_private_nonprofit", "number"),
                                        ("earnings_private_for_profit", "number"), ("cohort_size", "number"),
                                        ("median_earnings", "number"), ("debt_to_earnings", "number"),
                                        ("school", None), ("program", None), ("state", None),
                                        ("credential", None), ("school_type", None)]),
            target("/metrics/scatter_reference", [("ref_debt", "number"), ("earnings_equal_debt", "number")],
                   ref="B"),
        ],
        "fieldConfig": {"defaults": {"unit": "currencyUSD", "decimals": 0,
                                     "noValue": "No programs match these filters",
                                     "custom": {"show": "points", "pointSize": {"fixed": 5}, "fillOpacity": 55,
                                                "pointStrokeWidth": 0, "axisPlacement": "auto",
                                                "axisCenteredZero": False, "scaleDistribution": {"type": "linear"},
                                                "hideFrom": {"legend": False, "tooltip": False, "viz": False}}},
                        "overrides": overrides},
        "options": {"mapping": "manual", "series": series,
                    "legend": {"showLegend": True, "displayMode": "list", "placement": "bottom", "calcs": []},
                    "tooltip": {"mode": "single", "sort": "none"}},
    }


def debt_earnings_page():
    explain = ("- **X-axis — Median debt:** the middle amount of federal student-loan debt that graduates of the "
               "program had when they finished. It is *not* the cost of attendance.\n"
               "- **Y-axis — Median earnings:** the middle salary of graduates who were working, measured 2 years "
               "after completion.\n"
               "- **Colour — School type:** 🔵 Public · 🟠 Private, nonprofit · 🟣 Private, for-profit.\n"
               "- **Dot size — Cohort size:** how many graduates were measured. Small dots are less reliable.\n"
               "- **Dashed grey line — earnings = debt.** Dots above the line earned more in a year than they owed.\n"
               "- **Credential level** is a filter (box at the top) rather than a marker shape: Grafana's scatter "
               "chart can only draw circles and squares, which is not enough for three credential levels.\n"
               "- Hover over a dot for school, program, state, credential, earnings, debt and the ratio.")
    return graph_page("gradpath-graph-debt-earnings", "Debt vs. Earnings",
                      "Each dot is one program at one school. Higher and further left means more earnings for "
                      "less debt.", explain, scatter_panel)


def rankings_page():
    def main():
        return moved(12, "Lowest debt-to-earnings ratio — top 20 program types",
                     "Programs grouped by major, credential and school type, ranked by median debt ÷ median "
                     "earnings.")

    def extras(pg):
        pg.add(moved(11, "Highest median earnings — top 20 program types",
                     "Programs grouped by major, credential and school type, ranked by median earnings."), 24, 11)
    explain = ("- Each row groups the same **major + credential + school type** across all matching schools and "
               "takes the median.\n- **Debt ÷ earnings** = median debt ÷ median earnings. 🟢 under 0.5 · 🟡 0.5–1.0 "
               "· 🔴 1.0 or more (debt at least one year of earnings). The colours are reading aids, not a grade.\n"
               "- Click a column header to re-sort. Rankings describe past graduates, not your future salary.")
    return graph_page("gradpath-graph-rankings", "Degree ROI Rankings",
                      "Which kinds of programs left graduates with the least debt relative to what they earned?",
                      explain, main, extras)


def programs_page():
    def main():
        return barchart("Median earnings and debt by major (20 most common majors)",
                        "/metrics/group", "label",
                        [("median_earnings", "Median earnings", C_EARN), ("median_debt", "Median debt", C_DEBT)],
                        extra_params=[("by", "major"), ("sort", "programs"), ("n", "20"), ("min_programs", "3")],
                        description="The 20 majors offered by the most matching schools (at least 3 programs).")

    def extras(pg):
        nested = pg.row("Compare by school type (from the Classic dashboard)", collapsed=True)
        pg.add(moved(8), 8, 8, container=nested)
        pg.add(moved(10), 8, 8, container=nested)
        pg.add(moved(14), 8, 8, container=nested)
        pg.newline()
    explain = ("- **Bars:** 🔵 median earnings 2 years after completion and 🟠 median federal debt at completion, "
               "for each major.\n- Only majors offered by at least 3 matching programs are shown, so a single school "
               "cannot dominate.\n- Pick a State, Credential or School type at the top to compare majors within that "
               "group. Open the collapsed row below for the school-type comparison.")
    return graph_page("gradpath-graph-programs", "Program Comparison",
                      "How do typical earnings and typical debt compare across majors?", explain, main, extras)


def group_table(title, by, label):
    return table(title, "/metrics/group",
                 [("label", None), ("median_earnings", "number"), ("median_debt", "number"),
                  ("debt_to_earnings", "number"), ("programs", "number"), ("schools", "number")],
                 [rename("label", label), money("median_earnings", "Median earnings"),
                  money("median_debt", "Median debt"), ratio(), rename("programs", "Programs"),
                  rename("schools", "Schools")],
                 extra_params=[("by", by), ("sort", "median_earnings"), ("n", "60")])


def states_graph_page():
    def main():
        return barchart("Median earnings and debt by state", "/metrics/group", "name",
                        [("median_earnings", "Median earnings", C_EARN), ("median_debt", "Median debt", C_DEBT)],
                        extra_params=[("by", "state"), ("sort", "median_earnings"), ("n", "60")],
                        description="Programs are assigned to the state of the school's main campus.")

    def extras(pg):
        nested = pg.row("Table view and Classic chart", collapsed=True)
        pg.add(group_table("State comparison table", "state", "State"), 12, 12, container=nested)
        pg.add(moved(13, "Median earnings by state (Classic chart)"), 12, 12, container=nested)
        pg.newline()
    explain = ("- **Bars:** 🔵 median earnings and 🟠 median debt for matching programs in each state, highest "
               "earnings first.\n- A state's figure mixes many schools and majors; it does not mean a school in that "
               "state will pay more.\n- Earnings are not adjusted for cost of living or state taxes — see **States & "
               "Taxes** for verified tax facts.")
    return graph_page("gradpath-graph-states", "State Comparison",
                      "Where did graduates of matching programs earn more, and owe more?", explain, main, extras)


def credentials_page():
    def main():
        return barchart("Median earnings and debt by credential level", "/metrics/group", "label",
                        [("median_earnings", "Median earnings", C_EARN), ("median_debt", "Median debt", C_DEBT)],
                        extra_params=[("by", "credential"), ("sort", "median_earnings")])

    def extras(pg):
        nested = pg.row("Details and Classic charts", collapsed=True)
        pg.add(group_table("Credential comparison", "credential", "Credential"), 8, 8, container=nested)
        pg.add(moved(9), 8, 8, container=nested)
        pg.add(moved(15), 8, 8, container=nested)
        pg.newline()
    explain = ("- **Bars:** 🔵 median earnings and 🟠 median debt for each credential level among matching "
               "programs.\n- Credentials take different amounts of time, so compare debt with that in mind: a "
               "certificate can take under a year; a bachelor's degree usually four.\n- This data covers "
               "undergraduate credentials only.")
    return graph_page("gradpath-graph-credentials", "Credential-Level Comparison",
                      "How do certificates, associate's and bachelor's degrees compare on earnings and debt?",
                      explain, main, extras)


def schools_page():
    pg = Page()
    pg.add(nav_panel("gradpath-schools"), 24, 2)
    pg.add(header("Schools", "Type part of a school's name in the <b>School</b> box, or click a school name in the "
                             "table below to open its details."), 24, 3)
    pg.row("🏫 School details — ${school:text}")
    detail = "/schools/detail"
    pg.add(facts_table("School", detail, [
        ("school_name", "School"), ("address", "Address"), ("city_state_zip", "City, state, ZIP"),
        ("school_type", "Institution type"), ("matching_programs", "Matching programs"),
        ("address_source", "Address source"), ("outcomes_source", "Outcomes source")],
        description="Address and location come from the College Scorecard Institution file, joined by "
                    "institution ID.",
        no_value="Select a school in the School box above, or click a school name in the table below."), 10, 8)
    pg.add(stat("📘 Median earnings", detail, "median_earnings", "currencyUSD",
                description="Median of the matching programs' median earnings, 2 years after completion."), 7, 4)
    pg.add(stat("📘 Median debt", detail, "median_debt", "currencyUSD",
                description="Median of the matching programs' median federal debt at completion."), 7, 4)
    pg.add(stat("📘 Debt ÷ earnings", detail, "debt_to_earnings", decimals=2,
                description="Median debt divided by median earnings, per program."), 7, 4)
    pg.add(stat("📘 Graduates measured", detail, "total_cohort", "short",
                description="Total cohort size behind the earnings figures for the matching programs."), 7, 4)
    pg.newline()
    pg.add(table("Matching programs at this school", "/schools/programs",
                 [("program", None), ("cip_code", None), ("credential", None), ("median_earnings", "number"),
                  ("median_debt", "number"), ("debt_to_earnings", "number"), ("cohort_size", "number")],
                 [rename("program", "Program"), rename("cip_code", "CIP"), rename("credential", "Credential"),
                  money("median_earnings", "Median earnings"), money("median_debt", "Median debt"), ratio(),
                  rename("cohort_size", "Cohort size")],
                 no_value="Select a school to list its programs."), 24, 8)
    pg.row("📋 Ranked schools and programs")
    link = {"title": "Open details for ${__data.fields.school}",
            "url": "/d/gradpath-schools?var-school=${__data.fields.institution_id}&" + shared_qs(exclude=("school",))}
    pg.add(table("Schools ranked by debt ÷ earnings (lowest first)", "/schools/table",
                 [("rank", "number"), ("school", None), ("institution_id", None), ("school_type", None),
                  ("city_state", None), ("address", None), ("program", None), ("credential", None),
                  ("median_earnings", "number"), ("median_debt", "number"), ("debt_to_earnings", "number"),
                  ("cohort_size", "number"), ("source_year", None)],
                 [rename("rank", "#", {"id": "custom.width", "value": 50}),
                  rename("school", "School", {"id": "links", "value": [link]}, {"id": "custom.width", "value": 260}),
                  hidden("institution_id"), rename("school_type", "Type"), rename("city_state", "City, state"),
                  rename("address", "Address"), rename("program", "Program"), rename("credential", "Credential"),
                  money("median_earnings", "Median earnings"), money("median_debt", "Median debt"), ratio(),
                  rename("cohort_size", "Cohort"), rename("source_year", "Source year")],
                 description="Up to 500 programs matching your filters. Click a school name to see its details "
                             "above.",
                 extra_params=[("limit", "500")]), 24, 16)
    pg.add(text("🟢 under 0.5 · 🟡 0.5–1.0 · 🔴 1.0 or more — debt compared with one year of earnings. Colours help "
                "scanning; they are not a grade. Set **School** back to *All* to see every school again.",
                transparent=True), 24, 2)
    pg.add(footer("Addresses: College Scorecard Institution file; blank when the school did not report one."), 24, 2)
    return dashboard("gradpath-schools", "GradPath — Schools", pg)


def states_page():
    pg = Page()
    pg.add(nav_panel("gradpath-states"), 24, 2)
    pg.add(header("States & Taxes", "Pick <b>one</b> state in the State box. GradPath shows only facts it has "
                                    "verified on the state's official revenue website, with the tax year and "
                                    "source."), 24, 3)
    tax = "/states/tax"
    pg.add(stat("State", tax, "state_name", decimals=None, no_value="Select a state"), 6, 4)
    pg.add(stat("Verification status", tax, "supported", decimals=None), 6, 4)
    pg.add(stat("Tax year", tax, "tax_year", decimals=None, typ="string"), 6, 4)
    pg.add(stat("Last verified", tax, "last_verified", decimals=None,
                description="Date GradPath last checked the official source."), 6, 4)
    pg.add(facts_table("Tax facts", tax, [
        ("rate_summary", "In plain language"), ("income_tax_type", "Income tax type"),
        ("minimum_rate", "Lowest rate (%)"), ("maximum_rate", "Highest rate (%)"),
        ("standard_deduction_single", "Standard deduction (single filer)"),
        ("student_loan_interest_treatment", "Student-loan interest"),
        ("education_credit_summary", "Education credits / deductions"),
        ("verification_method", "How it was verified"), ("notes", "Notes and assumptions")],
        description="'Not verified' means GradPath could not confirm the rule on an official source."), 14, 11)
    pg.add(table("Official source", tax, [("official_source_url", None)],
                 [link_cell("official_source_url", "Official source (click to open)")],
                 no_value="Select a verified state."), 10, 3)
    est = "/states/tax_estimate"
    ex = [("income", "${example_income}")]
    pg.add(stat("🧮 Example: estimated state income tax", est, "estimated_state_tax", "currencyUSD",
                extra_params=ex, description="Wage income only, single filer. Educational estimate."), 4, 4)
    pg.add(stat("🧮 Effective state rate", est, "effective_rate_pct", "percent", decimals=1, extra_params=ex), 3, 4)
    pg.add(stat("Tax year used", est, "tax_year", decimals=None, extra_params=ex, typ="string"), 3, 4)
    pg.add(facts_table("Assumptions for this estimate", est, [
        ("example_salary", "Example salary"), ("taxable_income", "Taxable income used"),
        ("assumptions", "Assumptions"), ("input_check", "Input check")], extra_params=ex), 10, 4)
    pg.newline()
    pg.add(table("States GradPath has verified", "/states/tax_table",
                 [("state_code", None), ("state_name", None), ("tax_year", None), ("income_tax_type", None),
                  ("rate_summary", None), ("last_verified", None), ("official_source_url", None)],
                 [rename("state_code", "Code", {"id": "custom.width", "value": 60}), rename("state_name", "State"),
                  rename("tax_year", "Tax year"), rename("income_tax_type", "Type"),
                  rename("rate_summary", "Summary"), rename("last_verified", "Verified on"),
                  link_cell("official_source_url", "Official source")],
                 description="The verified demonstration set. Other states show 'Not yet verified'.",
                 wrap=True), 24, 10)
    pg.add(text("**Important:** tax rules change every year. These are educational summaries for the tax year shown, "
                "for a single filer with wage income only — not tax advice. Rules from one state are never applied to "
                "another. California and Massachusetts figures were read from official pages through a search index "
                "because those sites block automated downloads; open their source links to confirm.",
                transparent=True), 24, 3)
    pg.add(footer(), 24, 2)
    return dashboard("gradpath-states", "GradPath — States & Taxes", pg,
                     extra_vars=[textbox("example_income", "Example salary for tax estimate ($)", "50000", hide=0)])


def plan_page():
    pg = Page()
    pg.add(nav_panel("gradpath-my-plan"), 24, 2)
    edit = plan_form_url("&" + "&".join(f"{v}=${{{v}:percentencode}}" for v in PLAN_VARS))
    pg.add(text(
        '<div style="display:flex;flex-wrap:wrap;gap:12px;align-items:flex-end;justify-content:space-between;">'
        '<div><h1 style="font-size:30px;margin:2px 0 4px;">My Plan</h1>'
        '<p style="font-size:15px;opacity:.8;margin:0;max-width:70ch;">Estimates from your own answers plus '
        'historical College Scorecard data. Nothing here is stored on a server.</p></div>'
        f'<a href="{edit}" style="display:inline-block;padding:9px 18px;border-radius:8px;background:{ACTIVE_BG};'
        'color:#fff;text-decoration:none;font-weight:600;">✏️ Edit my inputs</a></div>', mode="html",
        transparent=True), 24, 3)
    pg.add(text("**What the labels mean:** 📘 Historical College Scorecard data · ✏️ You entered · 🧮 Calculated "
                "estimate · ⚙️ Assumption · ❔ Missing information. New here? Use **Edit my inputs** to open the "
                "planning form.", transparent=True), 24, 2)

    est = "/plan/estimate"

    def s(title, field, unit="currencyUSD", desc="", decimals=0):
        if unit == "currencyUSD":
            return stat(title, est, f"{field}_display", None, decimals=None, description=desc, plan=True,
                        typ="string")
        return stat(title, est, field, unit, decimals=decimals, description=desc, plan=True)

    pg.row("📘 Your school and program")
    pg.add(facts_table("Your school", est, [
        ("school_name", "School"), ("school_address", "Address"), ("school_city_state_zip", "City, state, ZIP"),
        ("residency", "Residency (you entered)"), ("occupation", "Intended occupation (you entered)"),
        ("confidence", "Confidence in the historical comparison")], plan=True), 12, 8)
    pg.add(s("📘 Historical median earnings", "historical_median_earnings",
             desc="Median earnings 2 years after completion for matching programs. Not a salary guarantee."), 6, 4)
    pg.add(s("📘 Historical median debt", "historical_median_debt",
             desc="Median federal loan debt at completion for matching programs."), 6, 4)
    pg.add(s("📘 Matching programs", "matching_programs", unit="short"), 6, 4)
    pg.add(s("📘 Graduates measured", "historical_cohort", unit="short"), 6, 4)

    pg.row("🧮 Paying for school (estimates)")
    pg.add(s("🧮 Total estimated education cost", "total_education_cost",
             desc="(Tuition + living expenses) × years in school. Uses Scorecard tuition if you left it blank."), 6, 4)
    pg.add(s("🧮 Savings available at enrollment", "savings_at_enrollment",
             desc="Current savings + yearly contributions until you start. No investment growth assumed."), 6, 4)
    pg.add(s("✏️ Scholarships & grants total", "grants_total",
             desc="Your yearly scholarships and grants × years in school."), 6, 4)
    pg.add(s("🧮 Estimated funding gap", "funding_gap",
             desc="Cost − grants − savings at enrollment − savings added while in school. Before any borrowing."),
           6, 4)
    pg.add(s("🧮 Savings coverage", "savings_coverage_pct", unit="percent",
             desc="Share of total cost covered by your own savings (capped at 100%)."), 6, 4)
    pg.add(s("🧮 Gap left after planned borrowing", "gap_after_planned_borrowing",
             desc="Funding gap − total planned borrowing. Above zero means the plan does not yet cover all costs."),
           6, 4)
    pg.add(s("✏️ Total new borrowing", "new_borrowing_total", desc="Expected borrowing per year × years in school."),
           6, 4)
    pg.add(s("⚙️ Interest rate used", "rate_used_pct", unit="percent", decimals=2,
             desc="Your rate, or 6.52% (2026–27 federal undergraduate Direct Loan rate) if left blank."), 6, 4)

    pg.row("🧮 After graduation (estimates)")
    pg.add(s("🧮 Estimated debt when repayment starts", "debt_at_repayment_start",
             desc="Existing balance + new borrowing + simple interest that builds up in school and during a "
                  "6-month grace period."), 6, 4)
    pg.add(s("🧮 Standard 10-year monthly payment", "standard_monthly_payment",
             desc="Fixed monthly payment that clears the balance in 120 months at your interest rate."), 6, 4)
    pg.add(s("🧮 Total interest (standard 10-year plan)", "standard_total_interest",
             desc="All payments minus the starting balance on the standard plan."), 6, 4)
    pg.add(stat("🧮 Estimated debt-free date range", est, "debt_free_range", decimals=None, plan=True,
                description="Month of the final loan payment: earliest to latest across your salary scenarios. "
                            "Payments start 6 months after a May graduation."), 6, 4)
    pg.add(stat("🧮 Time to repay", est, "repayment_time_range", decimals=None, plan=True,
                description="How long the payments last, fastest to slowest scenario."), 6, 4)
    pg.add(stat("⚙️ First payment due", est, "repayment_start", decimals=None, plan=True,
                description="Assumes a May graduation and a 6-month grace period."), 6, 4)
    w = lambda px: {"id": "custom.width", "value": px}
    pg.add(table("🧮 Salary scenarios — when could you be debt-free?", "/plan/scenarios",
                 [("scenario", None), ("starting_salary", "number"), ("monthly_payment", "number"),
                  ("time_to_repay", None), ("debt_free_date", None), ("total_interest", "number"),
                  ("payment_share_of_gross_pct", "number"), ("salary_source", None),
                  ("est_state_income_tax", "number"), ("state_tax_note", None), ("months_to_debt_free", "number")],
                 [rename("scenario", "Scenario", w(120)), money("starting_salary", "Starting salary"),
                  rename("monthly_payment", "Monthly payment ($)", {"id": "unit", "value": "locale"},
                         {"id": "decimals", "value": 2}, w(150)),
                  rename("time_to_repay", "Time to repay", w(130)),
                  rename("debt_free_date", "Final payment", w(130)),
                  money("total_interest", "Total interest"),
                  rename("payment_share_of_gross_pct", "% of gross pay",
                         {"id": "unit", "value": "percent"}, {"id": "decimals", "value": 1}, w(120)),
                  rename("salary_source", "Where the salary came from", w(230)),
                  money("est_state_income_tax", "Est. state income tax / yr"),
                  rename("state_tax_note", "State tax note"), hidden("months_to_debt_free")],
                 description="Payment = the larger of the 10-year standard payment and your chosen share of salary. "
                             "Final payment = month of the last payment; payments start 6 months after graduation.",
                 plan=True, wrap=True), 24, 8)
    pg.add(table("⚙️ Assumptions, ❔ missing information and ⚠️ input checks", "/plan/notes",
                 [("type", None), ("detail", None)],
                 [rename("type", "Type", {"id": "custom.width", "value": 220}), rename("detail", "Detail")],
                 plan=True, wrap=True), 24, 12)
    pg.add(text("These are **educational estimates**, not financial or tax advice. Historical earnings do not "
                "guarantee future salary; your occupation, location, employer and experience will matter.",
                transparent=True), 24, 2)
    pg.add(footer(), 24, 2)

    quick = {"savings": "Savings now ($)", "borrowing": "Borrow per year ($)", "rate": "Loan rate (%)",
             "salary_mid": "Expected salary ($)"}
    labels = {"in_state": "In-state? (yes/no)", "start_year": "Start year", "grad_year": "Graduation year",
              "contribution": "Savings added per year", "grants": "Grants per year",
              "existing_debt": "Existing loans", "tuition": "Tuition per year", "living": "Living costs per year",
              "occupation": "Occupation", "work_state": "Work state (e.g. TX)", "salary_low": "Conservative salary",
              "salary_high": "Aspirational salary", "repay_pct": "% of salary to loans", **quick}
    plan_vars = [textbox(v, labels[v], "", hide=0 if v in quick else 2) for v in PLAN_VARS]
    return dashboard("gradpath-my-plan", "GradPath — My Plan", pg, extra_vars=plan_vars,
                     description="Personal planning estimates. Inputs live only in the page URL and this browser.")


def help_page():
    pg = Page()
    pg.add(nav_panel("gradpath-help"), 24, 2)
    pg.add(header("Help & Methodology", "How to use GradPath, where the numbers come from, and what they cannot "
                                        "tell you."), 24, 3)
    pg.add(text("""### How to use each page
| Page | What it is for |
|---|---|
| 🏠 **Overview** | A summary of everything matching your filters, with shortcuts to each page. |
| 🧭 **My Plan** | Enter savings, aid, borrowing and salary guesses; see cost, debt and payoff estimates. |
| 🏫 **Schools** | Search schools, rank programs, and open a school's address and program details. |
| 🗺️ **States & Taxes** | Verified income-tax facts for 10 states, with tax year and official source. |
| 📊 **Graphs** | Five charts; each opens on its own page with an explanation. |
| ❓ **Help** | This page. |

### Search and filters
- The boxes at the top (School, State, Major, CIP code, Credential, School type, Data year) are **shared**: your choices follow you to every page through the navigation bar.
- **School** is searchable: click it and type part of a name, e.g. *"state univ"*. The list narrows to schools matching your other filters.
- Choose **All** to remove a filter. If a page says *No data*, that filter combination has no published records — widen it.
- In the Schools table, click a school's name to open its details."""), 12, 15)
    pg.add(moved(17, "How the metrics are calculated"), 12, 8)
    pg.add(text("""### The three career scenarios (My Plan)
- **Conservative** — a starting salary you are fairly sure you could beat.
- **Expected** — your best guess. If blank, GradPath uses the historical median for your school and major, labelled as such.
- **Aspirational** — a strong outcome, not a promise.

Monthly payment is the larger of the 10-year standard payment and the share of salary you choose (10% by default). Payoff dates are worked out month by month with a fixed interest rate."""), 12, 7)
    pg.add(text(f"""### Median earnings
The middle salary of graduates who were working and not enrolled, measured **2 years after completion** (`EARN_MDN_HI_2YR`). Half earned more, half less.

### Median debt
The middle amount of **federal** student-loan debt at completion (`DEBT_ALL_PP_ANY_MDN`). It is **not** the cost of attendance and leaves out private loans and Parent PLUS loans.

### Debt-to-earnings ratio
`median debt ÷ median earnings`. **0.5** means debt equal to half a year of earnings. Colour bands: 🟢 under 0.5 · 🟡 0.5–1.0 · 🔴 1.0 or more. They help scanning; they are not a grade.

### Data years
- Program outcomes: **{DATA_YEAR}** (College Scorecard release 2026-10-05, downloaded 2026-11-02).
- School addresses: College Scorecard Institution file, same release.
- State taxes: **tax year 2025**, verified 2026-11-04.
- Default loan rate: **6.52%**, federal undergraduate Direct Loans first disbursed July 1, 2026–June 30, 2027."""),
           12, 15)
    pg.add(text("""### Tax-data methodology
- Each state's facts were checked on that state's **official revenue website** (or official booklet). The URL and date are stored with every row in `state_tax_reference.csv`.
- A field is filled only when the official page states it; otherwise it shows **Not verified**. GradPath never copies one state's rules to another.
- California and Massachusetts official pages block automated downloads, so their figures were read through a search index of those official pages. Open their source links to confirm.
- Estimates assume a single filer with wage income only, use the verified standard deduction, and ignore credits and local taxes.

### Privacy
- GradPath does not ask for bank accounts, logins or account numbers.
- **My Plan** answers are kept in your browser (localStorage) and in the page address. The API computes estimates on request and does not save them. Use *Clear my answers* on the form to remove them.
- Sharing a My Plan link shares the numbers in it."""), 12, 12)
    pg.add(table("Data sources", "/meta/sources",
                 [("dataset_name", None), ("source_organization", None), ("source_year", None),
                  ("downloaded_at", None), ("source_url", None), ("important_limitations", None)],
                 [rename("dataset_name", "Dataset"), rename("source_organization", "Organization"),
                  rename("source_year", "Year"), rename("downloaded_at", "Downloaded / verified"),
                  link_cell("source_url", "Link", "Open source"),
                  rename("important_limitations", "Limitations")], wrap=True,
                 description="From data/processed/data_source_registry.csv"), 24, 10)
    pg.add(moved(18, "Important caveats"), 12, 10)
    pg.add(text("""### Known limitations
- Historical earnings **do not guarantee** future salary.
- Median debt is **not the same as cost of attendance**.
- School and major **do not cause** a particular income.
- Some records are **suppressed for privacy** (about 96% of raw rows have no published earnings or debt).
- Data **lags** current market conditions by several years.
- **State tax rules change** over time; only 10 states are verified.
- **Company, occupation, location and experience** affect earnings.
- Estimates are **educational planning information**, not personalized financial or tax advice.
- Only undergraduate credentials appear in the cleaned data.
- 74 schools in the Field of Study file are missing from the Institution file, so their state and address show as *Not reported*."""),
           12, 10)
    pg.add(text("""### Frequently asked questions
**Why is my school missing?** It may have no programs with published earnings *and* debt, or it is filtered out — set the filters to *All*.

**Why are two schools with the same name listed?** Some names repeat across states; the list shows city and state to tell them apart.

**Why does My Plan say "Low" confidence?** No published record matches your school and major, so the comparison uses a broader group or none.

**Can I save my plan?** It is saved in this browser automatically. Bookmark the My Plan page to keep a copy of the numbers.

**Where did the old dashboard go?** It still works: [GradPath — Classic](/d/gradpath-main) and [Tax Bracket AI — Classic](/d/gradpath-tax). The Classic tax dashboard uses 2024 rates and a model trained on synthetic data, so the new pages do not rely on it."""),
           24, 9)
    pg.add(footer(), 24, 2)
    return dashboard("gradpath-help", "GradPath — Help & Methodology", pg)


# ── Classic dashboards: banner only, panels untouched ────────────────────────

BANNER_ID = 900


def patch_classic(path, title_suffix=" (Classic)"):
    with open(path) as f:
        d = json.load(f)
    if not any(p.get("id") == BANNER_ID for p in d["panels"]):
        for p in d["panels"]:
            p["gridPos"]["y"] += 2
        d["panels"].insert(0, {
            "id": BANNER_ID, "type": "text", "title": "", "transparent": True,
            "gridPos": {"x": 0, "y": 0, "w": 24, "h": 2},
            "options": {"mode": "markdown", "content":
                        "🆕 **This is the Classic GradPath dashboard, kept unchanged for reference.** The new app has "
                        "navigation, school search, verified state taxes and a planner: "
                        "**[Open GradPath Overview →](/d/gradpath-overview)**"}})
    for p in d["panels"]:
        fix_json_paths(p)
    if not d["title"].endswith(title_suffix):
        d["title"] += title_suffix
    d["tags"] = sorted(set(d.get("tags", [])) | {"gradpath-classic"})
    return d


# ── Build / check ────────────────────────────────────────────────────────────

def build_all():
    dashboards = {
        "gradpath-overview.json": overview(),
        "gradpath-my-plan.json": plan_page(),
        "gradpath-schools.json": schools_page(),
        "gradpath-states.json": states_page(),
        "gradpath-graphs.json": graphs_landing(),
        "gradpath-help.json": help_page(),
        "gradpath-graph-debt-earnings.json": debt_earnings_page(),
        "gradpath-graph-rankings.json": rankings_page(),
        "gradpath-graph-programs.json": programs_page(),
        "gradpath-graph-states.json": states_graph_page(),
        "gradpath-graph-credentials.json": credentials_page(),
    }
    dashboards["gradpath_main.json"] = patch_classic(CLASSIC_MAIN)
    dashboards["gradpath_tax.json"] = patch_classic(CLASSIC_TAX)
    return dashboards


def all_panels(panels):
    for p in panels:
        yield p
        yield from all_panels(p.get("panels", []))


def check(dashboards):
    problems, uids = [], {}
    for name, d in dashboards.items():
        if d["uid"] in uids:
            problems.append(f"duplicate uid {d['uid']} in {name} and {uids[d['uid']]}")
        uids[d["uid"]] = name
        ids = [p["id"] for p in all_panels(d["panels"])]
        if len(ids) != len(set(ids)):
            problems.append(f"{name}: duplicate panel ids")
        if APP_TAG in d.get("tags", []):
            var_names = {v["name"] for v in d["templating"]["list"]}
            missing = set(SHARED) - var_names
            if missing:
                problems.append(f"{name}: missing shared variables {sorted(missing)}")
            first = d["panels"][0]
            if not (first["type"] == "text" and "GradPath pages" in first["options"]["content"]):
                problems.append(f"{name}: first panel is not the navigation bar")
            if first["gridPos"]["y"] != 0:
                problems.append(f"{name}: navigation bar is not at the top")
        json.dumps(d)
    return problems


def main():
    dashboards = build_all()
    problems = check(dashboards)
    if problems:
        print("\n".join(problems))
        sys.exit(1)
    if "--check" in sys.argv:
        print(f"OK: {len(dashboards)} dashboards valid")
        return
    for name, d in dashboards.items():
        with open(os.path.join(OUT, name), "w") as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
            f.write("\n")
        n = sum(1 for _ in all_panels(d["panels"]))
        print(f"wrote {name:38s} uid={d['uid']:30s} panels={n}")


if __name__ == "__main__":
    main()
