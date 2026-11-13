# Funding periods and school evidence

Bind this feature to `DESIGN.md`. It extends step 2 of My Plan within the existing four-step journey.

## Flow

1. Student selects a school and residency in step 1. The planner looks up the versioned College Scorecard directory and pre-fills tuition only if the student leaves the tuition input empty.
2. Step 2 shows tuition, living expenses, scholarships and savings contributions with amount and `Per year` / `Per month` controls. Current savings remains a balance today. Each entered figure shows its annual equivalent below the control. Monthly means 12 equal months per school year, regardless of the school's payment calendar.
3. The adjacent evidence panel shows published tuition for the selected residency, optional cost of attendance, equivalent monthly arithmetic, release date, and the institution's official website. The site link opens in a new tab for current fee verification. The user may enter a more current amount without changing the source data.
4. Review displays the entered period. Calculation receives the unit with the amount and converts monthly figures to annual before funding and repayment math.

## States and components

| Component | Empty/loading | Valid | Error/recovery | Small screen and accessibility |
| --- | --- | --- | --- | --- |
| Amount + period | Optional blank or tuition hint for auto-fill | Live annual equivalent and saved period | Numeric bounds and inline error on blur; focusable linked summary on submit | Input and native select stack under 540px; each has a distinct accessible name and 44px target |
| School evidence | Loading message; no school means no lookup | Source year, tuition, cost of attendance and safe official link | Missing tuition or website shown in words; API failure invites own estimate | One text column, link remains keyboard reachable, external tab has `noopener noreferrer` |
| Review and result | Missing required inputs surfaced | Period described in review; calculation uses annualized value | Invalid monthly annual total rejected, with recovery | Normal reading order; no color-only meaning |

Browser refresh and back navigation restore draft values and periods from local storage. An offline source lookup shows a fallback and still permits manual tuition. No site page is scraped for a fee number: the published Scorecard figure is labeled with its release, while current tuition is verified at the linked official school site. Estimates are never framed as a monthly billing quote.

## Acceptance and preflight

- Verify monthly and yearly inputs yield the same annual cost when numerically equivalent; switching period preserves the typed amount, recalculates the interpretation and saves it.
- Verify missing published tuition and absent official URL remain explicit, and no generated link uses a non-HTTP scheme.
- Verify keyboard, 375px viewport, focus/error summary, refresh, reduced motion, and source attribution.
- Visual identity, hierarchy, accessibility, edge states, copy, restraint and motion checked against `DESIGN.md`; avoid decorative cards and unsupported numeric claims.

Implementation handoff: the existing vanilla JavaScript/FastAPI application owns the feature. Keep native form elements and the existing tokens; implement the interactions and data contract as specified above.
