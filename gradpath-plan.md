# GradPath — MVP Plan

## Overview

Build the first working version of GradPath: a public-facing Streamlit web dashboard that helps
students compare U.S. degree programs using median earnings and median debt data from the
U.S. Department of Education College Scorecard Field of Study dataset.

**Scope:** Phase 1 (data inspection + synthetic demo dataset), Phase 2 (data pipeline),
Phase 3 (metrics), Phase 4 (Streamlit MVP). No loan predictions, salary tiers, AI recommendations,
or chatbot in this version.

**Starting point:** Empty repository.

**Data strategy:** Start with a synthetic demo dataset that mirrors the real Scorecard schema.
The pipeline and app must work identically when a real CSV is dropped into `data/raw/`.

**Deployment target:** Streamlit Community Cloud. The app must be runnable with
`streamlit run app.py` after a one-time `python src/prepare_data.py`.

---

## Sub-Tasks

---

### Sub-Task 1 — Repository Scaffold

**Intent**
Create the base project structure: folders, configuration files, and the synthetic demo dataset.
This establishes the layout every subsequent sub-task builds on.

**Expected Outcomes**
- Directory tree matches the agreed structure.
- `requirements.txt` lists all direct dependencies pinned to stable versions.
- `data/samples/degree_roi_demo.csv` exists with ~200 synthetic rows, clearly labelled synthetic.
- `.gitignore` excludes large raw CSVs, Python caches, and Streamlit secrets.
- `README.md` stub exists (will be completed in Sub-Task 6).

**Todo List**
1. Create directories: `app/`, `src/`, `data/raw/`, `data/processed/`, `data/samples/`, `docs/`.
2. Create `requirements.txt` with: `streamlit`, `pandas`, `plotly`, `openpyxl` (for xlsx read if needed).
3. Create `.gitignore` (Python + Streamlit defaults, exclude `data/raw/*.csv`).
4. Create `src/config.py` with all file paths and column-name constants.
5. Generate `data/samples/degree_roi_demo.csv`:
   - ~200 rows
   - Columns mirroring real Scorecard schema (see data mapping below)
   - Varied schools, states, CIP codes, credential levels, school types
   - Realistic but clearly fictional earnings and debt values
   - Include a banner column `IS_SYNTHETIC = True` so the app can detect demo mode
6. Create `docs/data_mapping.md` populated with the synthetic column mapping.

**Relevant Context**
- All file paths defined once in `src/config.py` — no hard-coded strings elsewhere.
- Synthetic data must never imply real institutional data.

**Synthetic Schema (mirrors real Scorecard columns)**

| App Column           | Real Scorecard Column | Label                        | Notes                             |
|---------------------|-----------------------|------------------------------|-----------------------------------|
| `institution_id`     | `UNITID`              | Institution ID (IPEDS)       | Numeric identifier                |
| `institution_name`   | `INSTNM`              | School name                  |                                   |
| `state`              | `STABBR`              | State abbreviation           | 2-letter                          |
| `school_control`     | `CONTROL`             | Control type code            | 1=Public 2=Private nonprofit 3=Private for-profit |
| `cip_code`           | `CIPCODE`             | CIP code                     | 6-digit decimal                   |
| `cip_title`          | `CIPDESC`             | CIP program title            |                                   |
| `credential_level`   | `CREDLEV`             | Credential level code        | 1=Certificate <2yr 2=Certificate 2-4yr 3=Associate 4=Bachelor 5=Master 6=Doctoral 7=First professional 8=Graduate certificate |
| `median_earnings`    | `EARN_MDN_HI_2YR`     | Median earnings 2yr post-completion | Dollars; suppressed = PrivacySuppressed |
| `earnings_year`      | derived               | Cohort year for earnings     | From filename or metadata         |
| `median_debt`        | `DEBT_MDN`            | Median cumulative debt       | Dollars; suppressed = PrivacySuppressed |
| `debt_definition`    | literal               | "Completers — federal loans" | Fixed note                        |
| `cohort_size`        | `EARN_COUNT`          | Number of earnings observations | May be suppressed for small groups |
| `is_synthetic`       | —                     | Synthetic data flag          | True for demo; absent in real data |

**Code-to-Label Mappings**

CONTROL:
- 1 → Public
- 2 → Private nonprofit
- 3 → Private for-profit

CREDLEV:
- 1 → Certificate (<2 yr)
- 2 → Certificate (2–4 yr)
- 3 → Associate's
- 4 → Bachelor's
- 5 → Master's
- 6 → Doctoral
- 7 → First professional
- 8 → Graduate certificate

**Status:** `[ ] pending`

---

### Sub-Task 2 — Data Pipeline (`src/prepare_data.py`)

**Intent**
Build the standalone data preparation script. It reads the raw CSV (or the synthetic demo),
cleans it, computes comparison metrics, and writes all processed outputs to `data/processed/`.

**Expected Outcomes**
- Running `python src/prepare_data.py` produces:
  - `data/processed/degree_roi_clean.csv` — all valid rows
  - `data/processed/degree_roi_latest.csv` — same as clean for this version
  - `data/processed/data_quality_summary.csv` — cleaning statistics
  - `data/processed/filter_options.json` — unique values for sidebar filters
- Script prints a brief summary to stdout on success.
- Script raises clear `FileNotFoundError` / `ValueError` messages on bad input.
- `docs/data_mapping.md` is updated or confirmed accurate.
- `docs/methodology.md` is created.

**Todo List**
1. Create `src/data_cleaning.py`:
   - `load_raw(path)` — reads CSV with all columns as strings initially.
   - `normalize_suppression(df)` — replaces `"PrivacySuppressed"`, `""`, `"NULL"`, whitespace with `NaN`.
   - `to_numeric_safe(series)` — coerces to float, errors become NaN.
   - `apply_schema(df)` — renames columns to app names using mapping from `src/config.py`.
   - `filter_required(df)` — drops rows missing institution name, CIP code, credential, earnings, or debt.
   - `filter_impossible(df)` — drops earnings ≤ 0, debt < 0, missing CIP or credential.
   - `map_labels(df)` — applies CONTROL and CREDLEV code-to-label mappings.
   - `deduplicate(df)` — removes exact duplicate rows.
2. Create `src/metrics.py`:
   - `add_metrics(df)` — adds `debt_to_earnings`, `earnings_to_debt` (handles zero debt), `earnings_debt_difference`.
3. Create `src/prepare_data.py` (orchestrator):
   - Calls each function in order.
   - Detects whether input is real data or synthetic demo (checks for `IS_SYNTHETIC` column or falls back to demo file).
   - Writes all four outputs.
   - Prints data-quality summary to stdout.
4. Create `docs/methodology.md` — formulas, suppression handling, cleaning decisions.

**Relevant Context**
- All paths from `src/config.py`.
- Zero debt is valid (full scholarship). Preserve it; `earnings_to_debt` returns `None`/`NaN` for zero-debt rows rather than infinity.
- Do not modify the raw file.

**Status:** `[ ] pending`

---

### Sub-Task 3 — Data Loader (`src/data_loader.py` + `src/filters.py`)

**Intent**
Build the modules the Streamlit app imports. The data loader reads the processed CSV once and
caches it. The filters module applies sidebar selections to return a filtered dataframe.

**Expected Outcomes**
- `src/data_loader.py` exposes `load_data()` — returns processed dataframe, cached with `@st.cache_data`.
- `src/data_loader.py` exposes `load_filter_options()` — returns the JSON filter options.
- `src/filters.py` exposes `apply_filters(df, params)` — pure function, no Streamlit imports.
- Both modules handle missing processed files with a clear error message pointing the user to run `prepare_data.py`.

**Todo List**
1. Create `src/data_loader.py`:
   - `load_data()` with `@st.cache_data` — reads `degree_roi_clean.csv`.
   - `load_filter_options()` with `@st.cache_data` — reads `filter_options.json`.
   - Clear `FileNotFoundError` handling with helpful message.
2. Create `src/filters.py`:
   - `apply_filters(df, params: dict) -> pd.DataFrame`
   - Handles multi-select (programs, credentials, states, school types, institutions).
   - Handles range filters (min earnings, max debt, min cohort size).
   - Returns empty dataframe (not an error) when no rows match.
   - No Streamlit imports — pure pandas logic.

**Relevant Context**
- `apply_filters` must handle the case where cohort_size column is absent (real Scorecard data may suppress it entirely).
- Filter params dict keys match the column names in `src/config.py`.

**Status:** `[ ] pending`

---

### Sub-Task 4 — Streamlit App (`app.py`)

**Intent**
Build the Streamlit MVP. Wire together the data loader, filters, metrics, charts, and
comparison feature into a clean, accessible dashboard.

**Expected Outcomes**
- `streamlit run app.py` launches without errors against the processed demo data.
- Sidebar filters work and update all panels reactively.
- Ranked table is sortable by the five allowed sort keys.
- Plotly scatterplot renders with correct axes, hover info, and diagonal reference line.
- Side-by-side program comparison works for up to 3 programs.
- Download buttons for filtered results and comparison export work.
- "No results" message appears when filters return zero rows.
- Caveats section is visible without scrolling past the chart.
- Synthetic data banner is shown when demo dataset is in use.
- "How this is calculated" section is visible and accurate.

**Todo List**
1. Create `app.py` — main entry point:
   - Page config: title, layout="wide", favicon.
   - Synthetic data banner (yellow info box) if `is_synthetic` column is present.
   - Title and one-sentence explanation.
   - Sidebar: all filters from spec (major, CIP, credential, state, school type, institution, min earnings, max debt, min cohort size).
   - Call `apply_filters` on sidebar state changes.
   - Summary metrics row (matching programs, schools, median earnings, median debt, median debt-to-earnings).
   - Ranked table with sort selector.
   - Plotly scatterplot (debt on X, earnings on Y, colored by school type, shaped by credential, sized by cohort if available, diagonal line, hover info).
   - Institution comparison widget (multiselect up to 3, side-by-side card layout).
   - Download buttons.
   - "How to interpret these results" caveats section.
   - "How this is calculated" section with visible formulas.
2. Keep each section in a clearly named function or block — do not write one monolithic function.
3. Use `st.columns` and `st.expander` to keep layout clean.
4. Format all currency values with `${:,.0f}` pattern.
5. Use high-contrast Plotly color palette.

**Relevant Context**
- `app.py` imports only from `src/` modules — no data logic inline.
- Streamlit Community Cloud requires `requirements.txt` at the repo root and `app.py` as the entry point.

**Status:** `[ ] pending`

---

### Sub-Task 5 — Documentation and README

**Intent**
Complete all documentation so the project is self-explaining to a new user and ready for
Streamlit Community Cloud deployment.

**Expected Outcomes**
- `README.md` is complete with all 10 required sections.
- `docs/data_mapping.md` is accurate and matches `src/config.py` constants.
- `docs/methodology.md` explains every metric formula and every cleaning decision.
- `data/samples/degree_roi_demo.csv` contains a comment or header note marking it synthetic.

**Todo List**
1. Complete `README.md`:
   - Project purpose and demo link placeholder.
   - Data source section (College Scorecard citation and URL).
   - Project structure tree.
   - Setup instructions (Python version, `pip install -r requirements.txt`).
   - Data prep command: `python src/prepare_data.py`.
   - App run command: `streamlit run app.py`.
   - Metric formulas (debt_to_earnings, earnings_to_debt, earnings_debt_difference).
   - Data caveats (all 10 from spec).
   - Screenshots section placeholder.
   - Future development section.
2. Confirm `docs/data_mapping.md` is accurate.
3. Confirm `docs/methodology.md` covers suppression handling, zero-debt edge case, impossible-value thresholds.

**Status:** `[ ] pending`

---

## Dependency Order

```
Sub-Task 1 (scaffold + synthetic data)
    → Sub-Task 2 (pipeline — reads data/samples/, writes data/processed/)
        → Sub-Task 3 (loader + filters — reads data/processed/)
            → Sub-Task 4 (app — imports src/ modules)
                → Sub-Task 5 (documentation)
```

Each sub-task must be fully complete before the next begins.

---

## Assumptions

- Python 3.11+ is available locally and on Streamlit Community Cloud.
- The synthetic demo dataset is the only data source for the first working version.
- When a real Scorecard CSV is provided, only `src/config.py` path constants need updating.
- Streamlit Community Cloud reads `requirements.txt` from the repo root and starts `app.py`.
- No authentication, database, or external API is needed in this version.
- The `EARN_MDN_HI_2YR` column (median earnings 2 years after completion) is the selected earnings field; this should be re-verified against the real data dictionary when real data is added.

---

## Out of Scope (This Version)

- Loan payment calculators
- Company salary tier comparisons
- AI-generated ROI scores or recommendations
- AI chatbot
- User accounts or saved searches
- Real-time data refresh
- Docker or Kubernetes deployment
