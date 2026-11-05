"""
Deterministic education-finance formulas for the GradPath "My Plan" page.

No AI, no randomness: same inputs always give the same outputs. Every
simplifying assumption is listed in ASSUMPTIONS and shown on the dashboard.
"""
import math
from dataclasses import dataclass

STANDARD_TERM_MONTHS = 120          # federal standard repayment plan: 10 years
GRACE_MONTHS = 6                    # repayment starts 6 months after graduation
GRADUATION_MONTH = 5                # assume a May graduation
SCHOOL_START_MONTH = 9              # loans disbursed each September

ASSUMPTIONS = [
    "Each school year costs the same (tuition + living expenses); no tuition increases.",
    "Savings earn no interest or investment growth.",
    "Scholarships and grants are entered per year and repeat every year in school.",
    "Annual borrowing is taken each September, at the start of each school year.",
    "All loans accrue simple interest from disbursement (unsubsidized), including a 6-month grace "
    "period; accrued interest is added to the balance when repayment starts.",
    "Existing loans are deferred and accrue interest until repayment starts.",
    "One fixed interest rate applies to all loans.",
    "You pay at least the 10-year standard payment; if the chosen share of salary is higher, "
    "the extra goes to principal. Income-driven plans and forgiveness are not modelled.",
    "Salaries are gross and flat (no raises); taxes are not subtracted.",
    "Graduation in May of the graduation year; repayment starts in November.",
]


@dataclass
class PlanInputs:
    start_year: int
    grad_year: int
    current_year: int
    current_month: int = 1
    current_savings: float = 0.0
    annual_contribution: float = 0.0
    annual_grants: float = 0.0
    existing_balance: float = 0.0
    annual_borrowing: float = 0.0
    rate_pct: float = 0.0
    annual_tuition: float = 0.0
    annual_living: float = 0.0
    salary_conservative: float | None = None
    salary_expected: float | None = None
    salary_aspirational: float | None = None
    repay_pct: float = 10.0


def years_in_school(start_year: int, grad_year: int) -> int:
    return max(1, grad_year - start_year)


def amortized_payment(principal: float, annual_rate_pct: float, months: int) -> float:
    if principal <= 0:
        return 0.0
    r = annual_rate_pct / 100 / 12
    if r == 0:
        return principal / months
    return principal * r / (1 - (1 + r) ** -months)


def months_to_payoff(principal: float, annual_rate_pct: float, payment: float) -> int | None:
    """Whole months until the balance reaches zero; None if the payment never covers interest."""
    if principal <= 0:
        return 0
    if payment <= 0:
        return None
    r = annual_rate_pct / 100 / 12
    if r == 0:
        return math.ceil(principal / payment)
    if payment <= principal * r:
        return None
    return math.ceil(-math.log(1 - r * principal / payment) / math.log(1 + r))


def total_interest(principal: float, annual_rate_pct: float, payment: float, months: int | None) -> float | None:
    """Exact interest over the schedule, with a smaller final payment."""
    if months is None:
        return None
    if principal <= 0 or months == 0:
        return 0.0
    r = annual_rate_pct / 100 / 12
    bal, paid = principal, 0.0
    for _ in range(months):
        bal += bal * r
        pay = min(payment, bal)
        bal -= pay
        paid += pay
    return round(paid - principal, 2)


def add_months(year: int, month: int, n: int) -> tuple[int, int]:
    idx = year * 12 + (month - 1) + n
    return idx // 12, idx % 12 + 1


def repayment_start(grad_year: int) -> tuple[int, int]:
    return add_months(grad_year, GRADUATION_MONTH, GRACE_MONTHS)


def _month_index(year: int, month: int) -> int:
    return year * 12 + (month - 1)


def debt_at_graduation(p: PlanInputs) -> dict:
    """Balance when repayment starts (graduation + grace), with simple interest accrued so far."""
    years = years_in_school(p.start_year, p.grad_year)
    rate = p.rate_pct / 100
    repay_idx = _month_index(*repayment_start(p.grad_year))
    new_principal = p.annual_borrowing * years
    accrued_new = sum(
        p.annual_borrowing * rate * max(0, repay_idx - _month_index(p.start_year + i, SCHOOL_START_MONTH)) / 12
        for i in range(years)
    )
    existing_months = max(0, repay_idx - _month_index(p.current_year, p.current_month))
    accrued_existing = p.existing_balance * rate * existing_months / 12
    principal = p.existing_balance + new_principal
    accrued = accrued_new + accrued_existing
    return {
        "new_borrowing_total": round(new_principal, 2),
        "existing_balance": round(p.existing_balance, 2),
        "accrued_interest_before_repayment": round(accrued, 2),
        "debt_at_repayment_start": round(principal + accrued, 2),
    }


def compute_plan(p: PlanInputs) -> dict:
    years = years_in_school(p.start_year, p.grad_year)
    total_cost = (p.annual_tuition + p.annual_living) * years
    pre_enrollment_years = max(0, p.start_year - p.current_year)
    savings_at_enrollment = p.current_savings + p.annual_contribution * pre_enrollment_years
    in_school_contributions = p.annual_contribution * years
    grants_total = p.annual_grants * years
    own_funds = savings_at_enrollment + in_school_contributions
    funding_gap = max(0.0, total_cost - grants_total - own_funds)
    coverage = (min(1.0, own_funds / total_cost) * 100) if total_cost > 0 else None

    debt = debt_at_graduation(p)
    principal = debt["debt_at_repayment_start"]
    std_payment = amortized_payment(principal, p.rate_pct, STANDARD_TERM_MONTHS)
    std_interest = total_interest(principal, p.rate_pct, std_payment, months_to_payoff(principal, p.rate_pct, std_payment))
    start_y, start_m = repayment_start(p.grad_year)

    scenarios = []
    for label, salary in (("Conservative", p.salary_conservative),
                          ("Expected", p.salary_expected),
                          ("Aspirational", p.salary_aspirational)):
        if salary is None or salary <= 0:
            scenarios.append({"scenario": label, "starting_salary": None, "monthly_payment": None,
                              "months_to_debt_free": None, "debt_free_date": "Missing salary",
                              "total_interest": None, "payment_share_of_gross_pct": None})
            continue
        budget = max(std_payment, salary / 12 * p.repay_pct / 100)
        months = months_to_payoff(principal, p.rate_pct, budget)
        if months is None:
            date = "Not paid off at this payment"
        elif months == 0:
            date = "No loan balance"
        else:
            y, m = add_months(start_y, start_m, months)
            date = f"{y}-{m:02d}"
        scenarios.append({
            "scenario": label,
            "starting_salary": round(salary, 0),
            "monthly_payment": round(budget, 2) if principal > 0 else 0.0,
            "months_to_debt_free": months,
            "debt_free_date": date,
            "total_interest": total_interest(principal, p.rate_pct, budget, months),
            "payment_share_of_gross_pct": round(budget * 12 / salary * 100, 1) if principal > 0 else 0.0,
        })

    dated = [s for s in scenarios if s["months_to_debt_free"] not in (None, 0)]
    if principal <= 0:
        debt_free_range = "No loan balance"
    elif dated:
        dates = sorted(s["debt_free_date"] for s in dated)
        debt_free_range = dates[0] if dates[0] == dates[-1] else f"{dates[0]} to {dates[-1]}"
    else:
        debt_free_range = "Enter salary scenarios"

    return {
        "years_in_school": years,
        "total_education_cost": round(total_cost, 2),
        "savings_at_enrollment": round(savings_at_enrollment, 2),
        "in_school_contributions": round(in_school_contributions, 2),
        "grants_total": round(grants_total, 2),
        "funding_gap": round(funding_gap, 2),
        "gap_after_planned_borrowing": round(max(0.0, funding_gap - debt["new_borrowing_total"]), 2),
        "savings_coverage_pct": round(coverage, 1) if coverage is not None else None,
        **debt,
        "standard_monthly_payment": round(std_payment, 2),
        "standard_total_interest": std_interest,
        "repayment_start": f"{start_y}-{start_m:02d}",
        "debt_free_range": debt_free_range,
        "scenarios": scenarios,
    }
