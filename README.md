# GradPath — Degree ROI & Student Planning

GradPath is a small local app, built on Grafana, that helps students compare U.S. college programs by
**median earnings** and **median debt** (U.S. Department of Education College Scorecard). It also shows
verified **state income-tax facts** and lets students build a **personal plan** for savings, borrowing
and loan payoff.

> ⚠️ Historical outcomes for past completers who received federal aid — **not salary guarantees** and not
> financial or tax advice.

## Links

**Repository:** https://github.com/Sujay1709/gradpath

**Open GradPath:** **http://localhost:8000**. This is the student app, and it needs no login.

| Page | Link | What it's for |
|---|---|---|
| Overview | http://localhost:8000/ | Three main choices, plus outcome lookup by school, major or state |
| My Plan | http://localhost:8000/plan | 4-step walkthrough → review → results (funding gap, debt, payment, debt-free range) |
| Schools | http://localhost:8000/schools | Search and rank programs; open a school; add it to My Plan |
| Graphs | http://localhost:8000/graphs | Five questions, each with a chart, a plain-language summary and a table |
| States | http://localhost:8000/states | Verified tax-year-2025 facts for 10 states, with sources |
| Help | http://localhost:8000/help | Getting started, metrics, building a plan, sources, privacy, limitations, FAQ |

Admin and analyst views are in Grafana at http://localhost:3000, organised into three folders:

| Folder | Contents |
|---|---|
| **GradPath** | A "Start here" launcher (Grafana's home page) |
| **GradPath Detail Views** | The five chart dashboards that the app embeds |
| **GradPath Legacy** | The earlier Grafana page versions (Overview, My Plan, Schools, States, Graphs, Help) and the Classic dashboards, kept for reference |

API docs: http://localhost:8000/docs. The `localhost` links only work on the computer running GradPath.

---

## Architecture (Nov 2026 UX recovery)

```
Browser ──► GradPath app (FastAPI, port 8000)
            ├─ static/app/  one app: nav, page-specific filters, empty states, 4-step planner
            ├─ JSON API     /metrics, /options, /schools, /states, /plan/calculate (POST)
            └─ embeds charts from Grafana (port 3000) with d-solo: one panel, no Grafana menus
Grafana ──► JSON API datasource → the same FastAPI endpoints
```

- **Why an app on port 8000?** Grafana text panels strip `<style>`, `<svg>` and scripts, and kiosk mode still
  shows every filter box. The student pages need a responsive menu, panels hidden until a selection is made,
  removable filter chips and focus management, so they live in the app. Grafana stays the chart engine: the
  app embeds the existing chart queries unchanged.
- **Privacy.** My Plan answers are stored only in the browser (`localStorage`, key `gradpath.plan.v2`) and are
  sent to `POST /plan/calculate` in the request body. Financial values never appear in a URL, browser history
  or a shared link, and the server neither stores nor caches them. The old Grafana My Plan, which put values in
  the URL, is in **GradPath Legacy** with a warning.
- **Filters per page.**

  | Page | Filters |
  |---|---|
  | Overview | School, major, state; *More filters*: credential, school type |
  | Schools | School, major, state, credential; *More filters*: CIP code, school type |
  | Graphs | Major, state, credential; *More filters*: school, CIP code, school type |
  | States | State, plus an example income |
  | Help, My Plan | No dataset filters |

  There is only one data year, so it is shown as a label rather than a filter. School, major and state carry
  over between Overview, Schools and Graphs through the page address, and picking a school fills in its state.
- **Accessibility.**
  - Skip link; the current page is announced (`aria-current`); focus moves to the heading on every navigation.
  - Tap targets of at least 44 px; visible focus rings; tables scroll or become cards on phones.
  - Every chart has a table version; the debt-to-earnings label uses words and a shape, not colour alone.
  - Respects reduced-motion preferences; text pairs meet WCAG AA contrast.
- **Checked layouts.** Every page at 1440, 1024, 768 and 390 px, with no horizontal overflow and the nav on
  one line on desktop or a single menu below 960 px.

Before and after screenshots are in `gradpath/docs/screenshots/`. The audit and the recovery map are in
`gradpath/docs/ux_recovery_map.md`.

## Setup (first time)

Prerequisites: macOS with [Homebrew](https://brew.sh) and Python 3.11+.

```bash
# 1. Python packages
pip3 install -r gradpath/requirements.txt --break-system-packages

# 2. Grafana + JSON API datasource plugin
brew install grafana
grafana cli \
  --homepath /opt/homebrew/opt/grafana/share/grafana \
  --pluginsDir /opt/homebrew/var/lib/grafana/plugins \
  plugins install marcusolsson-json-datasource
```

In the Grafana config, point `[paths] provisioning` at `gradpath/grafana/provisioning`. The config is
`/opt/homebrew/etc/grafana/grafana.ini`, which is the one `start.sh` uses. An example is in
`gradpath/grafana/grafana.ini`.

---

## Refresh the data

Run these from the repo root.

```bash
cd gradpath
python3 src/prepare_data.py            # Field of Study CSV → data/processed/degree_roi_clean.parquet
python3 src/build_reference_data.py    # school_directory, degree_roi_latest, data_source_registry, plan demo
python3 grafana/build_dashboards.py    # regenerate all dashboard JSON (Grafana reloads within ~10 s)
python3 tests/test_gradpath.py         # unit tests (stdlib unittest, no extra packages)
cd ..

# The API caches responses in memory, so restart it to serve the refreshed data
pkill -f "uvicorn api:app"
(cd gradpath && nohup python3 -m uvicorn api:app --app-dir src --port 8000 > api.log 2>&1 &)

# Then stress-test the running API (≈5 seconds; exit code 1 on any problem)
python3 gradpath/tests/stress_plan.py
```

`tests/stress_plan.py` runs four checks against the running API:
1. It replays every dashboard query under four filter scenarios.
2. It runs real schools from all 9 school-type × credential categories through My Plan with five input
   profiles, and checks every debt, payment, payoff month and date range against an independent loan simulator.
3. It confirms that cached and compressed responses match fresh ones.
4. It enforces latency and throughput budgets.

Options: `--quick` (3 schools per category), `--per-category 40`, `--seed 11`, `--skip-perf`.

To use a newer College Scorecard download, put the files in `dataset/…` and update the paths and the
`SCORECARD_*` constants in `gradpath/src/config.py`.

## Start and open

```bash
./start.sh
open http://localhost:8000
```

`start.sh` builds any missing data, starts the FastAPI backend on port 8000 and starts Grafana on port 3000.
If Grafana is already running, it keeps the running instance.

If you change the API code, restart it:

```bash
pkill -f "uvicorn api:app"
cd gradpath && python3 -m uvicorn api:app --app-dir src --port 8000
```

---

## How the debt-free timeline is calculated

1. **Borrowing.** Your yearly loan is paid out each September you're in school, plus any existing balance.
2. **Interest before repayment.** Each loan builds simple interest from the month it is paid out until
   repayment starts: `amount × rate × months ÷ 12`.
3. **Starting balance.** Borrowed + that interest, in the November after a May graduation (6-month grace).
4. **Standard payment.** `P × r ÷ (1 − (1 + r)^−120)`, with `r` = yearly rate ÷ 12, rounded up to the cent.
5. **Payment per salary scenario.** The larger of the standard payment and your chosen share of salary ÷ 12
   (10% by default).
6. **Month by month.** Each month, interest (`balance × r`) is added and the payment subtracted until the
   balance hits zero. That final payment month is your debt-free date.
7. **Range.** The earliest to latest final payment across your scenarios.

My Plan shows this as a chart, milestones and these steps filled in with your numbers.
`tests/stress_plan.py` re-checks every step against an independent simulator.

## How it works

```
College Scorecard CSVs ─► src/prepare_data.py ─► degree_roi_clean.parquet ─┐
Institution CSV ────────► src/build_reference_data.py ─► school_directory.csv ├─► FastAPI (src/api.py + src/app_routes.py)
Official state pages ───► state_tax_reference.csv (hand-verified) ──────────┘        │  JSON
                                                                                     ▼
                     grafana/build_dashboards.py ─► grafana/dashboards/*.json ─► Grafana (JSON API datasource)
                     static/app/ (student app at :8000) ─► embeds Detail View charts; My Plan calculates via POST /plan/calculate
```

- **One source for all dashboards.** `grafana/build_dashboards.py` defines the nav bar, the shared
  variables and the page layouts once. Don't edit the generated JSON by hand.
- **Shared filters.** Every API endpoint takes the same optional query params, and `filters.py` applies
  them. "All" never filters anything, so the Classic dashboards return exactly what they did before.
- **School search.** The School variable lists `Name — City, ST` and stores the IPEDS institution ID,
  because 46 school names repeat across states. You can type a name or a state code (`TX`).
- **Smart filters.** Picking a school switches **State** to that school's state, and narrows **Major** and
  **CIP code** to its programs. Under the hood, State's only remaining option is the school's state; the
  dependency order is school → state → major → CIP.
- **Debt measure.** "Median debt" is the median **federal student-loan debt (Stafford + Grad PLUS) borrowed
  at the school** (`DEBT_ALL_STGP_EVAL_MDN`). Earlier versions used `DEBT_ALL_PP_ANY_MDN`, which the
  Scorecard data dictionary defines as **Parent PLUS** debt. That was corrected in Nov 2026; see
  `gradpath/docs/methodology.md`.
- **Repayment Timeline Agent.** `pipeline/agents/repayment_timeline_agent.py` builds each student's payoff
  timeline: a month-by-month balance per salary scenario, milestones (25/50/75% repaid, final payment) and a
  step-by-step explanation with the student's own numbers. It is deterministic (no AI) and is served at
  `/plan/timeline`, `/plan/milestones` and `/plan/explain`.
- **Look.** A bright theme: Grafana's light theme (`cfg:users.default_theme=light` in `start.sh`) with
  burnt-orange and red accents chosen for WCAG AA contrast.
- **My Plan inputs.** Grafana has no built-in form, so a small HTML form served by FastAPI collects the
  inputs. It validates them, saves them in the browser's `localStorage` and opens the My Plan dashboard
  with the values in the URL. No bank connections, no credentials and no server-side storage.
- **Deterministic calculations.** `src/plan_calc.py` holds plain formulas with unit tests. No AI is used
  in any calculation.
- **Performance.**
  - pandas writes JSON responses directly.
  - Responses over 2 KB are gzipped, which cuts the full 32,551-point scatter by about 90%.
  - Read-only GET responses are cached in memory (`src/response_cache.py`). `/plan/*` is never cached
    because its answers depend on today's date.
  - Cache statistics are at http://localhost:8000/meta/health.

## Datasets

| File | Built by | Contents |
|---|---|---|
| `data/processed/degree_roi_clean.parquet` | `prepare_data.py` | 32,551 programs (320 majors, 4,043 schools, 8 credential levels) with earnings, student debt and ratios |
| `data/processed/degree_roi_latest.csv` | `build_reference_data.py` | The same rows plus address, city, ZIP and source year |
| `data/processed/school_directory.csv` | `build_reference_data.py` | 6,272 institutions with address, city, state, ZIP, type, latitude/longitude and source year (plus published tuition, used to pre-fill My Plan) |
| `data/processed/state_tax_reference.csv` | **hand-verified** | 10 states, tax year 2025, with source URL and verified date |
| `data/processed/state_tax_brackets.csv` | **hand-verified** | CA and NY single-filer brackets for 2025 |
| `data/processed/data_source_registry.csv` | `build_reference_data.py` | Every source with its URL, year, dates and limitations |
| `data/samples/student_plan_demo.csv` | `build_reference_data.py` | 3 **fictional** students (`is_synthetic=true`) |

**Addresses are never guessed.** 473 institutions report no street address, and 74 schools in the
Field of Study file are missing from the Institution file. GradPath shows these as *Not reported*.

## State tax coverage

**Verified (tax year 2025):** CA, NY, TX, FL, WA, PA, IL, NC, MA, GA. CA and MA were read through a
search index of their official pages, because those sites block automated downloads, so open their
source links to confirm the figures. Every other state shows **"Not yet verified"** and no tax figures.
Student-loan-interest treatment could not be verified for any state, so that field shows *Not verified*.

## Data caveats

1. Historical earnings do not guarantee future salary.
2. Median debt is not the same as cost of attendance.
3. School and major do not cause a particular income.
4. Some records are suppressed for privacy (~85% of raw rows).
5. The data lags current market conditions.
6. State tax rules change over time.
7. Company, occupation, location and experience all affect earnings.
8. These are educational estimates, not personalized financial or tax advice.

## Project layout

```
IBM_BOB/
├── start.sh                         one-command launcher
├── dataset/College_Scorecard_…/     raw downloads (not in git)
└── gradpath/
    ├── src/
    │   ├── config.py                paths and constants
    │   ├── prepare_data.py          Scorecard cleaning pipeline (unchanged)
    │   ├── build_reference_data.py  directory, registry and demo datasets
    │   ├── api.py                   FastAPI app + Classic endpoints (now filter-aware)
    │   ├── app_routes.py            GradPath app endpoints
    │   ├── filters.py               shared filters + safe number parsing
    │   ├── plan_calc.py             deterministic plan formulas
    │   ├── response_cache.py        in-memory cache for read-only GET endpoints
    │   └── data_store.py            load-once data access
    ├── static/app/                  student app (index.html, app.css, app.js, pages.js, plan.js, embed.json)
    ├── tests/test_gradpath.py       unit tests
    ├── tests/stress_plan.py         API stress test (rerun after data refresh)
    ├── data/processed/ · data/samples/
    ├── docs/                        data mapping + methodology
    └── grafana/
        ├── build_dashboards.py      generates every dashboard
        ├── dashboards/main|detail|legacy/   generated, one directory per Grafana folder
        ├── backup/                  dashboard JSON before the UX recovery
        └── provisioning/            datasource + "GradPath" folder provider
```
