# Data Mapping — GradPath

**Source file:** `Most-Recent-Cohorts-Field-of-Study.csv`
**Institution file:** `Most-Recent-Cohorts-Institution.csv`
**Release:** College Scorecard Nov 2026 (version 2026-10-05)

---

## Selected Columns

| App Column | Raw Column | Source File | Plain-English Meaning | Cohort / Source Year | Limitation |
|---|---|---|---|---|---|
| `institution_id` | `UNITID` | Field of Study | IPEDS institution identifier | — | Join key only |
| `institution_name` | `INSTNM` | Field of Study | School name | — | May include branch campuses |
| `state` | `STABBR` | **Institution** | State abbreviation (2-letter) | — | Joined via UNITID; main campus state |
| `school_type` | `CONTROL` | Field of Study | School control type | — | Already string in this file: "Public", "Private, nonprofit", "Private, for-profit" |
| `cip_code` | `CIPCODE` | Field of Study | 6-digit CIP classification code | — | Same code can mean different programs at different schools |
| `cip_title` | `CIPDESC` | Field of Study | CIP program title | — | Generic; institution-specific names may differ |
| `credential_level_code` | `CREDLEV` | Field of Study | Numeric credential level | — | See mapping below |
| `credential_level` | `CREDDESC` | Field of Study | Human-readable credential label | — | Used for display |
| `ipeds_count` | `IPEDSCOUNT1` | Field of Study | IPEDS completers count (cohort 1) | — | May be suppressed |
| `cohort_size` | `EARN_COUNT_WNE_HI_2YR` | Field of Study | Number of working, not enrolled completers measured at 2yr | 2yr post-completion | May be suppressed for small programs |
| `median_earnings` | `EARN_MDN_HI_2YR` | Field of Study | **PRIMARY:** Median earnings 2 years after completion | 2021–22 completers measured 2023–24 | Federal suppression ("PS") → excluded. Covers only working-not-enrolled students. |
| `median_earnings_1yr` | `EARN_MDN_HI_1YR` | Field of Study | Median earnings 1 year after completion | 2022–23 completers | Supplemental; more suppressed than 2yr |
| `median_debt` | `DEBT_ALL_STGP_EVAL_MDN` | Field of Study | **PRIMARY:** Median Stafford + Grad PLUS (federal student) loan debt borrowed at this institution | Program completion cohort | Borrowers only; excludes private loans and Parent PLUS |
| `median_debt_all_schools` | `DEBT_ALL_STGP_ANY_MDN` | Field of Study | Same loans, including debt carried in from other institutions | — | Supplemental |
| `median_parent_plus_debt` | `DEBT_ALL_PP_ANY_MDN` | Field of Study | Median **Parent PLUS** loan debt (borrowed by parents) | — | Supplemental; a different borrower group — never used as student debt |

---

## Suppression

Values stored as `"PS"` (PrivacySuppressed) or `"NULL"` in the CSV are converted to `NaN`
and excluded. Rows missing either `median_earnings` or `median_debt` are dropped.

This removes approximately **85% of raw rows**, leaving ~32,551 records with reportable
earnings and debt. This is expected behaviour: College Scorecard suppresses small cohorts
to protect student privacy.

---

## Code-to-Label Mappings

### CREDLEV (credential level)

| Code | Label |
|------|-------|
| 1 | Certificate (<2 yr) |
| 2 | Certificate (2–4 yr) |
| 3 | Associate's |
| 4 | Bachelor's |
| 5 | Master's |
| 6 | Doctoral |
| 7 | First professional |
| 8 | Graduate certificate |

### CONTROL (school type)

Already stored as readable string in this file:

| Value | Meaning |
|-------|---------|
| Public | Public institution |
| Private, nonprofit | Private not-for-profit |
| Private, for-profit | Private for-profit |

---

## Important Limitations

1. **Debt ≠ cost.** `DEBT_ALL_STGP_EVAL_MDN` is the median federal student-loan debt borrowed at
   this institution by completers who borrowed — not the total cost of the program.
2. **Earnings reflect working-not-enrolled completers only.** Students still in school or
   not working are excluded.
3. **Federal aid recipients only.** Students who paid entirely out-of-pocket are not
   counted.
4. **State from institution file.** Branch campuses may be assigned the main campus state.
5. **CIP codes are generic.** A CIP 11.0201 "Computer Programming" at MIT and at a
   community college are counted as the same program type.


---

## Correction (Nov 2026)

Earlier versions mapped `DEBT_ALL_PP_ANY_MDN` to `median_debt` and described it as
"post-program, any loan". The College Scorecard data dictionary (`data.yaml`, entry
`P_DEBT_ALL_PP_ANY_MDN`) defines it as **median Parent PLUS loan debt** — loans parents take out.
`median_debt` now uses `DEBT_ALL_STGP_EVAL_MDN` (Stafford + Grad PLUS borrowed at this institution),
which is the student's own federal debt and covers 32,551 programs and 320 majors (was 8,266 and 205).
