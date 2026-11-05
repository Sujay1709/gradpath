# Methodology — GradPath

## Data Selection

The primary data file is `Most-Recent-Cohorts-Field-of-Study.csv` from the
College Scorecard Nov 2026 release. This file contains one row per
(institution, CIP code, credential level) combination and reports earnings
and debt outcomes for completers.

State was not available in the Field of Study file and was joined from
`Most-Recent-Cohorts-Institution.csv` via the `UNITID` key.

---

## Cleaning Decisions

### 1. Suppression handling
The dataset uses `"PS"` (PrivacySuppressed), `"NULL"`, `"NA"`, and blank strings
to indicate that a value was withheld for privacy reasons (cohort too small).
All of these are converted to `NaN` before any numeric coercion.

This is the expected behaviour from the data dictionary (`data.yaml`):
```
null_value:
  - 'NULL'
  - PrivacySuppressed
  - NA
  - PS
```

### 2. Required fields
A row is kept only if all of the following are non-null:
- `institution_name`
- `cip_code`
- `credential_level`
- `median_earnings` (EARN_MDN_HI_2YR)
- `median_debt` (DEBT_ALL_PP_ANY_MDN)

This removes ~96% of rows, which is expected. The Scorecard suppresses
earnings and debt for any program where the student count is below the
privacy threshold (~30 students for most fields).

### 3. Impossible values
- Earnings ≤ 0 are dropped (not a valid reported earnings figure).
- Debt < 0 is dropped (not possible for cumulative debt).
- Debt = 0 is kept: it is a valid value for programs where all completers
  had no federal loans. However, `earnings_to_debt` returns `NaN` for
  zero-debt rows to avoid producing infinity.

### 4. Deduplication
Exact duplicate rows (all columns identical) are removed.

---

## Metric Formulas

### Debt-to-Earnings
```
debt_to_earnings = median_debt / median_earnings
```
- Measures how many years of (median) annual income it would take to repay the
  median debt load, ignoring interest, taxes, and living costs.
- Lower is better.
- Threshold interpretation: < 0.5 green, 0.5–1.0 yellow, ≥ 1.0 red.

### Earnings-to-Debt
```
earnings_to_debt = median_earnings / median_debt   (NaN when median_debt = 0)
```
- Inverse of debt-to-earnings. Higher = more earning power relative to debt.
- Returns NaN (not displayed) when debt is zero to avoid infinity.

### Earnings Minus Debt
```
earnings_debt_difference = median_earnings - median_debt
```
- A simple absolute comparison: positive means annual earnings exceed total
  cumulative debt; negative means the reverse.
- Useful for quick magnitude comparison but ignores repayment schedules.

---

## What These Metrics Do NOT Measure

- They do not account for interest on loans.
- They do not account for taxes or living expenses.
- They do not predict an individual's earnings.
- They do not reflect the full cost of attendance (only federal loan debt).
- They do not control for field of work, location, experience, or demographics.
- They are medians: half of completers were above, half below.

---

## Earnings Field Selection

`EARN_MDN_HI_2YR` was selected as the primary earnings measure because:
- It has the best non-suppression rate in this dataset (more rows with valid values
  than the 3-year or 4-year fields in the Field of Study file).
- It is the measure used by the official College Scorecard website for program comparisons.
- It measures outcomes 2 years post-completion, when most graduates have entered the workforce.

The 1-year earnings (`EARN_MDN_HI_1YR`) is loaded as a supplemental column but not
used as a primary metric, as it often reflects partial-year employment.

---

## Debt Field Selection

`DEBT_ALL_PP_ANY_MDN` was selected because:
- "PP" = post-program (completers only, not dropouts).
- "ALL" = all loan types combined.
- "ANY" = any loan, not limited to a specific evaluation period.
- Median (MDN) rather than mean reduces sensitivity to outliers.

This is the same definition used by the College Scorecard's public-facing tool.

---

## My Plan Calculations (deterministic — `src/plan_calc.py`)

| Output | Formula |
|---|---|
| Years in school | `graduation year − start year` (minimum 1) |
| Total education cost | `(annual tuition + annual living expenses) × years` |
| Savings at enrollment | `current savings + annual contribution × years until the start year` (no growth) |
| Scholarships & grants total | `annual grants × years` |
| Funding gap | `max(0, cost − grants − savings at enrollment − annual contribution × years)` |
| Savings coverage | `min(100%, own savings ÷ cost)` |
| Debt when repayment starts | `existing balance + annual borrowing × years + simple interest` — each September disbursement accrues interest until repayment starts in November after a May graduation (6-month grace) |
| Standard monthly payment | `P·r / (1 − (1+r)^−120)`, with `r` = annual rate ÷ 12 |
| Scenario payment | `max(standard payment, repay% × salary ÷ 12)` |
| Payments | rounded **up** to the cent, as lenders bill, so the standard plan always finishes within 120 payments |
| Months to debt-free | simulated month by month with the exact payment shown (the final payment is smaller); "not paid off" if `A ≤ rP` |
| Final payment month | first payment month (November after a May graduation) + payments − 1 |
| Total interest | sum of all payments − starting balance, from the same simulation |
| Confidence | High = exact school + major match with 30+ graduates measured; Medium = smaller or broader match; Low = no match |

If left blank:
- **Tuition** uses the Scorecard published tuition & fees (`TUITIONFEE_IN` or `_OUT`).
- **Expected salary** uses the Scorecard historical median for the matching programs.
- **Interest rate** uses 6.52% (federal undergraduate Direct Loans, 2026–27; FSA announcement GENERAL-26-33).

Every auto-filled value is labelled on the page.

## State Tax Reference Methodology

- Source: each state's official revenue site or booklet for **tax year 2025**, checked on 2026-11-04.
  The URL, verification date and method are stored in every row of `data/processed/state_tax_reference.csv`.
- A field is filled only if the official page states it. Otherwise it shows "Not verified".
- One state's rules are never applied to another.
- Estimates assume a single filer with wage income only, apply the verified standard deduction and use the
  verified flat rate or bracket schedule (`state_tax_brackets.csv`). They ignore credits, local taxes and exemptions.
