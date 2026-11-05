# GradPath UX recovery map (Nov 2026)

## Audit findings

**Before the recovery**
- 13 dashboards were all in one Grafana folder (`GradPath`).
- Every app page showed all 7 filters: school, state, major, CIP, credential, school type and data year. Data year has only one value.
- Each page had two navigation menus: a text-panel nav bar and Grafana's "All GradPath pages" dropdown.
- Navigation icons were emoji, and the nav wrapped across lines on small screens.

**My Plan: privacy problem.** The results lived in Grafana. Personal financial values travelled as `var-*` URL parameters (13 hidden URL variables): savings, borrowing, salaries, tuition and so on. Those values end up in browser history and in any shared link.

**What Grafana can and can't do here**
- Kiosk mode (`?kiosk`) in Grafana 13 hides the sidebar and top bar, but every filter box stays visible.
- Text panels strip `<style>`, `<svg>`, `<script>` and form controls. That rules out:
  - a responsive menu
  - hiding empty panels until a selection is made
  - removable filter chips
  - moving focus to the page heading
- Embedding was blocked: `allow_embedding = false`, which sends `X-Frame-Options: deny`.
- Data sources: a single JSON API datasource (`gradpath-api`), pointing at FastAPI on port 8000.
- Query parameters: each panel passes the shared variables as `params` (`${var}`), and "All" is sent as `__all`.
- localStorage: `gradpath.plan.v1`, written by the old form at `/plan`.

**Decision.** The student product moves to one app on port 8000. It renders its own navigation, filters, empty states and the planner. Grafana stays the chart engine: its existing chart queries are embedded with `d-solo` (one panel, no Grafana chrome).

## Recovery map

### Product (port 8000)

| Existing file | Responsibility | Action |
|---|---|---|
| `src/api.py`, `src/app_routes.py` | JSON API used by every view | **Retain**. Add `POST /plan/calculate`, so financial inputs travel in a request body instead of a URL. Serve the product pages. |
| `src/plan_calc.py`, `pipeline/agents/repayment_timeline_agent.py` | Plan formulas and the repayment timeline | **Retain unchanged** (no formula defects found). |
| `src/prepare_data.py`, `src/build_reference_data.py`, `data/processed/*` | Scorecard pipeline, directory and the verified tax data | **Retain unchanged**. |
| `static/plan.html` | Single long planning form | **Retire**. A copy is in `grafana/backup/pre-ux-recovery-2026-11-05/plan_form_v1.html`. It is replaced by the 4-step walkthrough in `static/app/`. |
| — | Student product shell | **New**: `static/app/index.html`, `app.css`, `app.js`, `pages.js`, `plan.js` |

### Grafana (port 3000)

| Existing file | Responsibility | Action |
|---|---|---|
| `grafana/build_dashboards.py` | Generates every dashboard | **Simplify**:<br>- drop the duplicate "All GradPath pages" links<br>- keep only the relevant filters on detail views<br>- write the embed manifest<br>- write dashboards into per-folder directories |
| `gradpath-overview`, `-schools`, `-states`, `-graphs`, `-help` | Old Grafana page versions | **Move** to the **GradPath Legacy** folder. Superseded by the product; kept for reference. |
| `gradpath-my-plan` | Plan results driven by URL parameters | **Move** to **GradPath Legacy**, with a privacy warning banner. |
| `gradpath-graph-*` (5) | Chart detail dashboards | **Move** to **GradPath Detail Views**. The product embeds their main chart. |
| `gradpath_main.json`, `gradpath_tax.json` | Classic dashboards | **Move** to **GradPath Legacy**. |
| — | Grafana home page | **New**: `gradpath-start` launcher in the `GradPath` folder. It points students to the product and admins to the folders. |
| `provisioning/dashboards/gradpath.yaml` | One folder provider | **Simplify** into three providers, one per folder. |
| `start.sh` | Launcher | **Retain**. Add `allow_embedding`, and make Grafana's home the launcher. |

UIDs are preserved for every existing dashboard.

## Outcome

| Area | Result |
|---|---|
| Navigation | One product nav (Overview, My Plan, Schools, Graphs, States, Help) with SVG icons, `aria-current` on the current page, one line on desktop and a menu below 960 px. The "All GradPath pages" dropdown is removed from every dashboard. |
| Filters | Each page shows only the filters it uses (see README). Data year is shown as a label. |
| Overview | Decision-first: a title, three choices with one action each, and four metrics that appear only after a selection. |
| My Plan | `/plan` (steps 1–3), `/plan/review`, `/plan/results`, `/plan/edit`. Answers stay in localStorage and are sent to `POST /plan/calculate`, never in a URL. Empty state shown until the required answers are in. |
| Schools | Ranked results first; details only after a school is selected; Add to My Plan and Compare another school. |
| States | The state picker comes first. With no state chosen, the page lists the verified states. Every fact shows its tax year, source and verification date. |
| Graphs | Five question cards. Each detail page has a conclusion, the embedded chart, a table version, the source and Back to Graphs. |
| Help | Seven accordion sections with a table of contents; one limitations list; no file paths. |
| Responsive | All 13 page states checked at 1440/1024/768/390 px: no overflow, targets of at least 44 px, no clipped titles. |
| Formulas | Unchanged. No calculation defects were found during the recovery. |
