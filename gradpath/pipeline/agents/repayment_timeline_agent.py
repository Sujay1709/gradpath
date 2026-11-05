"""
Repayment Timeline Agent — builds a student's loan payoff timeline.

Deterministic: it uses the same formulas as src/plan_calc.py (no AI, no randomness).
Given the student's plan inputs and computed plan, it produces:

    schedule     month-by-month balance for each salary scenario and the standard plan
    milestones   first payment, 25 / 50 / 75 % of the starting balance repaid, final payment
    explanation  numbered steps showing how the timeline was calculated, using the
                 student's own numbers

It follows the BaseAgent contract, so it can run as a threaded pipeline stage
(reading "repayment_requests", writing "repayment_timelines"). The API calls
`handle()` directly for each request, which runs `process()` synchronously.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))           # gradpath/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))    # plan_calc

from pipeline.agents.base_agent import BaseAgent
from pipeline.bus.message_bus import Bus, Message
from plan_calc import (
    STANDARD_TERM_MONTHS, PlanInputs, accrual_breakdown, add_months, amortization_rows,
    month_label, repayment_start,
)

MILESTONES = ((0.25, "25% of starting balance repaid"), (0.50, "Half repaid"), (0.75, "75% repaid"))


def _money(x: float, cents: bool = False) -> str:
    return f"${x:,.2f}" if cents else f"${x:,.0f}"


class RepaymentTimelineAgent(BaseAgent):
    def __init__(self, bus: Bus | None = None, in_channel: str = "repayment_requests",
                 out_channel: str = "repayment_timelines"):
        super().__init__("repayment_timeline", bus or Bus(), in_channel, out_channel)

    def handle(self, inputs: PlanInputs, plan: dict) -> dict:
        """Synchronous entry point used by the API."""
        result = self.process(Message(source_agent="api", payload={"inputs": inputs, "plan": plan}))
        self.stats["processed"] += 1
        return result.payload

    def process(self, message: Message) -> Message:
        inputs: PlanInputs = message.payload["inputs"]
        plan: dict = message.payload["plan"]
        principal = plan["debt_at_repayment_start"]
        start_y, start_m = repayment_start(inputs.grad_year)

        tracks = {}
        for s in plan["scenarios"]:
            if s.get("monthly_payment") and s.get("months_to_debt_free"):
                tracks[s["scenario"]] = s["monthly_payment"]
        if principal > 0:
            tracks["Standard 10-year plan"] = plan["standard_monthly_payment"]

        schedules = {name: list(amortization_rows(principal, inputs.rate_pct, pay)) for name, pay in tracks.items()}
        payload = {
            "schedule": self._schedule(principal, start_y, start_m, schedules),
            "milestones": self._milestones(principal, start_y, start_m, schedules),
            "explanation": self._explain(inputs, plan, start_y, start_m, schedules),
        }
        return Message(source_agent=self.name, payload=payload, metadata=message.metadata)

    # ── outputs ──────────────────────────────────────────────────────────────

    @staticmethod
    def _schedule(principal, start_y, start_m, schedules):
        """One row per month from the month before the first payment until every track is at zero."""
        if not schedules:
            return []
        longest = max(len(rows) for rows in schedules.values())
        out = []
        for k in range(longest + 1):
            y, m = add_months(start_y, start_m, k - 1)
            row = {"month": month_label(y, m), "year": round(y + (m - 1) / 12, 4)}
            for name, rows in schedules.items():
                row[name] = round(principal if k == 0 else (rows[k - 1][3] if k <= len(rows) else 0.0), 2)
            out.append(row)
        return out

    @staticmethod
    def _milestones(principal, start_y, start_m, schedules):
        out = []
        for name, rows in schedules.items():
            interest_so_far = 0.0
            pending = list(MILESTONES)
            out.append({"scenario": name, "milestone": "First payment", "date": month_label(start_y, start_m),
                        "balance_left": round(principal, 2), "interest_paid_so_far": 0.0, "payment_number": 1})
            for n, interest, _, bal in rows:
                interest_so_far += interest
                while pending and bal <= principal * (1 - pending[0][0]):
                    out.append({"scenario": name, "milestone": pending[0][1],
                                "date": month_label(*add_months(start_y, start_m, n - 1)),
                                "balance_left": round(bal, 2), "interest_paid_so_far": round(interest_so_far, 2),
                                "payment_number": n})
                    pending.pop(0)
            n = rows[-1][0] if rows else 0
            out.append({"scenario": name, "milestone": "Debt-free (final payment)",
                        "date": month_label(*add_months(start_y, start_m, n - 1)), "balance_left": 0.0,
                        "interest_paid_so_far": round(interest_so_far, 2), "payment_number": n})
        return out

    @staticmethod
    def _explain(inputs: PlanInputs, plan: dict, start_y, start_m, schedules):
        steps = []

        def step(title, detail):
            steps.append({"step": len(steps) + 1, "title": title, "detail": detail})

        rate = inputs.rate_pct
        borrowed = plan["new_borrowing_total"] + plan["existing_balance"]
        if borrowed <= 0:
            step("No loans", "You entered no borrowing and no existing balance, so there is nothing to repay.")
            return steps

        years = plan["years_in_school"]
        step("What you borrow",
             f"{_money(inputs.annual_borrowing)} each September for {years} year(s) "
             f"({inputs.start_year}–{inputs.start_year + years - 1}) = {_money(plan['new_borrowing_total'])}"
             + (f", plus an existing balance of {_money(plan['existing_balance'])}." if plan["existing_balance"] else "."))
        parts = "; ".join(f"{a['loan']}: {_money(a['amount'])} × {rate:g}% × {a['months']}/12 = "
                          f"{_money(a['interest'], cents=True)}" for a in accrual_breakdown(inputs))
        step("Interest before payments start",
             f"Unsubsidized loans build simple interest from the day they are paid out until repayment starts in "
             f"{month_label(start_y, start_m)} (6 months after a May {inputs.grad_year} graduation). {parts}. "
             f"Total: {_money(plan['accrued_interest_before_repayment'], cents=True)}.")
        step("Balance when repayment starts",
             f"{_money(borrowed, cents=True)} borrowed + {_money(plan['accrued_interest_before_repayment'], cents=True)} "
             f"interest = {_money(plan['debt_at_repayment_start'], cents=True)} in {month_label(start_y, start_m)}.")
        r = rate / 100 / 12
        step("Standard 10-year payment",
             f"Payment = P × r ÷ (1 − (1 + r)^−{STANDARD_TERM_MONTHS}), with P = "
             f"{_money(plan['debt_at_repayment_start'], cents=True)} and r = {rate:g}% ÷ 12 = {r * 100:.4f}% per month "
             f"→ {_money(plan['standard_monthly_payment'], cents=True)} per month (rounded up to the cent), "
             f"finishing in {plan['standard_debt_free_date']}.")
        for s in plan["scenarios"]:
            if not s.get("starting_salary"):
                step(f"{s['scenario']} salary", "No salary entered, so this scenario is skipped.")
                continue
            share = s["starting_salary"] / 12 * inputs.repay_pct / 100
            chosen = ("your share of salary is higher, so the extra goes to principal"
                      if s["monthly_payment"] > plan["standard_monthly_payment"] + 0.005
                      else "the standard payment is higher, so you pay that")
            step(f"{s['scenario']} salary ({_money(s['starting_salary'])}/yr)",
                 f"{inputs.repay_pct:g}% of {_money(s['starting_salary'])} ÷ 12 = {_money(share, cents=True)}; "
                 f"{chosen}: {_money(s['monthly_payment'], cents=True)}/month. Each month, interest "
                 f"(balance × {r * 100:.4f}%) is added and the payment subtracted: {s['months_to_debt_free']} "
                 f"payments ({s['time_to_repay']}), last payment {s['debt_free_date']}, total interest "
                 f"{_money(s['total_interest'] or 0, cents=True)}.")
        step("Your debt-free range",
             f"Earliest to latest final payment across your salary scenarios: {plan['debt_free_range']} "
             f"({plan['repayment_time_range']}).")
        step("What this leaves out",
             "Income-driven plans, forgiveness, missed or extra payments, rate changes and daily (rather than "
             "monthly) interest. These are educational estimates, not financial advice.")
        return steps
