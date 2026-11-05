# GradPath — Degree ROI & Student Planning

GradPath is a small local app, built on Grafana, that helps students compare U.S. college programs by
**median earnings** and **median debt** (U.S. Department of Education College Scorecard). It also shows
verified **state income-tax facts** and lets students build a **personal plan** for savings, borrowing
and loan payoff.

> ⚠️ Historical outcomes for past completers who received federal aid — **not salary guarantees** and not
> financial or tax advice.

---

## The six pages

Every page has the same navigation bar at the top, with the current page highlighted. The shared filters
(School, State, Major, CIP code, Credential, School type, Data year) carry over when you move between pages.

| Page | URL | What it shows |
|---|---|---|
| 🏠 Overview | `/d/gradpath-overview` | Matching schools and programs, median earnings, debt and ratio, plus cards linking to every page |
| 🧭 My Plan | `/d/gradpath-my-plan` (inputs at `http://localhost:8000/plan`) | Cost, funding gap, debt at graduation, monthly payment, debt-free range, salary scenarios |
| 🏫 Schools | `/d/gradpath-schools` | Searchable ranked table; click a school for its address, programs and outcomes |
| 🗺️ States & Taxes | `/d/gradpath-states` | Verified tax facts (tax year 2025) for 10 states, with sources and an example estimate |
| 📊 Graphs | `/d/gradpath-graphs` | Cards linking to five graph pages (below) |
| ❓ Help | `/d/gradpath-help` | How-to, formulas, data years, tax method, privacy, FAQ, limitations |

The five graph pages are:

- `gradpath-graph-debt-earnings`
- `gradpath-graph-rankings`
- `gradpath-graph-programs`
- `gradpath-graph-states`
- `gradpath-graph-credentials`

All of these dashboards live in the Grafana folder **GradPath**. The original dashboards still work as
**Classic** versions: `/d/gradpath-main` and `/d/gradpath-tax`.

---

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
```

To use a newer College Scorecard download, put the files in `dataset/…` and update the paths and the
`SCORECARD_*` constants in `gradpath/src/config.py`.

## Start and open

```bash
./start.sh
open http://localhost:3000/d/gradpath-overview
```

`start.sh` builds any missing data, starts the FastAPI backend on port 8000 and starts Grafana on port 3000.
If Grafana is already running, it keeps the running instance.

If you change the API code, restart it:

```bash
pkill -f "uvicorn api:app"
cd gradpath && python3 -m uvicorn api:app --app-dir src --port 8000
```

---

## How it works

```
College Scorecard CSVs ─► src/prepare_data.py ─► degree_roi_clean.parquet ─┐
Institution CSV ────────► src/build_reference_data.py ─► school_directory.csv ├─► FastAPI (src/api.py + src/app_routes.py)
Official state pages ───► state_tax_reference.csv (hand-verified) ──────────┘        │  JSON
                                                                                     ▼
                     grafana/build_dashboards.py ─► grafana/dashboards/*.json ─► Grafana (JSON API datasource)
                     static/plan.html (My Plan form, served at :8000/plan) ─► opens the My Plan dashboard
```

- **One source for all dashboards.** `grafana/build_dashboards.py` defines the nav bar, the shared
  variables and the page layouts once. Don't edit the generated JSON by hand.
- **Shared filters.** Every API endpoint takes the same optional query params, and `filters.py` applies
  them. "All" never filters anything, so the Classic dashboards return exactly what they did before.
- **School search.** The School variable lists `Name — City, ST` and stores the IPEDS institution ID,
  because 18 school names repeat across states.
- **My Plan inputs.** Grafana has no built-in form, so a small HTML form served by FastAPI collects the
  inputs. It validates them, saves them in the browser's `localStorage` and opens the My Plan dashboard
  with the values in the URL. No bank connections, no credentials and no server-side storage.
- **Deterministic calculations.** `src/plan_calc.py` holds plain formulas with unit tests. No AI is used
  in any calculation.

## Datasets

| File | Built by | Contents |
|---|---|---|
| `data/processed/degree_roi_clean.parquet` | `prepare_data.py` (unchanged) | 8,266 programs with earnings, debt and ratios |
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
4. Some records are suppressed for privacy (~96% of raw rows).
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
    │   └── data_store.py            load-once data access
    ├── static/plan.html             My Plan input form
    ├── tests/test_gradpath.py       unit tests
    ├── data/processed/ · data/samples/
    ├── docs/                        data mapping + methodology
    └── grafana/
        ├── build_dashboards.py      generates every dashboard
        ├── dashboards/*.json        generated, committed
        └── provisioning/            datasource + "GradPath" folder provider
```
