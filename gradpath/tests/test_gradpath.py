"""
GradPath unit tests (stdlib unittest — no extra dependencies).

Run from gradpath/:  python3 -m unittest discover -s tests -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pandas as pd  # noqa: E402

from filters import Filters, apply_filters, parse_multi, parse_number  # noqa: E402
from plan_calc import (  # noqa: E402
    PlanInputs, amortized_payment, compute_plan, months_to_payoff, round_up_cents, total_interest,
)


class AmortizationTests(unittest.TestCase):
    def test_standard_payment_known_value(self):
        # $30,000 at 6% over 120 months → $333.06 (standard amortization table value)
        self.assertAlmostEqual(amortized_payment(30000, 6.0, 120), 333.06, places=2)

    def test_zero_rate(self):
        self.assertAlmostEqual(amortized_payment(12000, 0.0, 120), 100.0)
        self.assertEqual(months_to_payoff(12000, 0.0, 100.0), 120)
        self.assertEqual(total_interest(12000, 0.0, 100.0, 120), 0.0)

    def test_payment_never_covers_interest(self):
        # interest is $150/month; paying $100 never reaches zero
        self.assertIsNone(months_to_payoff(30000, 6.0, 100.0))

    def test_payoff_matches_term(self):
        p = amortized_payment(30000, 6.0, 120)
        self.assertEqual(months_to_payoff(30000, 6.0, p), 120)
        self.assertAlmostEqual(total_interest(30000, 6.0, p, 120), p * 120 - 30000, delta=1.0)

    def test_standard_plan_never_exceeds_term(self):
        # rounded-up cent payments must clear any balance in at most 120 payments
        import random
        rnd = random.Random(3)
        for _ in range(2000):
            bal, rate = rnd.uniform(1, 250000), rnd.choice([0, 2.75, 5.5, 6.52, 8.08, 12.0])
            pay = round_up_cents(amortized_payment(bal, rate, 120))
            self.assertLessEqual(months_to_payoff(bal, rate, pay), 120, (bal, rate, pay))

    def test_no_debt(self):
        self.assertEqual(amortized_payment(0, 6.0, 120), 0.0)
        self.assertEqual(months_to_payoff(0, 6.0, 0), 0)


class PlanTests(unittest.TestCase):
    def base(self, **kw):
        args = dict(start_year=2027, grad_year=2031, current_year=2026, current_month=11,
                    current_savings=4000, annual_contribution=1000, annual_grants=5000,
                    annual_borrowing=5000, rate_pct=0.0, annual_tuition=10000, annual_living=12000,
                    salary_conservative=40000, salary_expected=50000, salary_aspirational=70000)
        args.update(kw)
        return PlanInputs(**args)

    def test_cost_savings_gap(self):
        r = compute_plan(self.base())
        self.assertEqual(r["years_in_school"], 4)
        self.assertEqual(r["total_education_cost"], 88000)
        self.assertEqual(r["savings_at_enrollment"], 5000)        # 4000 + 1 year × 1000
        self.assertEqual(r["grants_total"], 20000)
        self.assertEqual(r["funding_gap"], 88000 - 20000 - 5000 - 4000)
        self.assertEqual(r["new_borrowing_total"], 20000)

    def test_zero_rate_no_accrual(self):
        r = compute_plan(self.base())
        self.assertEqual(r["accrued_interest_before_repayment"], 0)
        self.assertEqual(r["debt_at_repayment_start"], 20000)

    def test_interest_accrues_by_month(self):
        # one $1,000 loan, Sept 2027 → repayment Nov 2028 = 14 months at 12% → $140
        r = compute_plan(self.base(start_year=2027, grad_year=2028, annual_borrowing=1000, rate_pct=12.0))
        self.assertAlmostEqual(r["accrued_interest_before_repayment"], 140.0, places=2)

    def test_higher_salary_pays_off_sooner(self):
        r = compute_plan(self.base(rate_pct=6.0))
        months = [s["months_to_debt_free"] for s in r["scenarios"]]
        self.assertTrue(months[0] >= months[1] >= months[2])
        self.assertLessEqual(months[0], 120)

    def test_debt_free_date_is_last_payment_month(self):
        # $1,200 at 0%, standard payment $10/month → 120 payments from Nov 2028 → last one Oct 2038
        r = compute_plan(self.base(start_year=2027, grad_year=2028, annual_borrowing=1200,
                                   salary_conservative=None, salary_expected=None, salary_aspirational=None))
        self.assertEqual(r["repayment_start"], "Nov 2028")
        self.assertEqual(r["standard_debt_free_date"], "Oct 2038")
        self.assertEqual(r["debt_free_range"], "Oct 2038 (standard 10-year plan)")
        self.assertEqual(r["repayment_time_range"], "10 yr of payments (standard plan)")
        # 10% of $36,000 = $300/month → 4 payments: Nov, Dec, Jan, Feb
        r = compute_plan(self.base(start_year=2027, grad_year=2028, annual_borrowing=1200,
                                   salary_conservative=36000))
        self.assertEqual(r["scenarios"][0]["months_to_debt_free"], 4)
        self.assertEqual(r["scenarios"][0]["debt_free_date"], "Feb 2029")
        self.assertEqual(r["scenarios"][0]["time_to_repay"], "4 mo")

    def test_missing_salary_flagged(self):
        r = compute_plan(self.base(salary_aspirational=None))
        self.assertEqual(r["scenarios"][2]["debt_free_date"], "Missing salary")

    def test_coverage_capped(self):
        r = compute_plan(self.base(current_savings=10**6))
        self.assertEqual(r["savings_coverage_pct"], 100.0)


class RepaymentAgentTests(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from pipeline.agents.repayment_timeline_agent import RepaymentTimelineAgent
        self.agent = RepaymentTimelineAgent()
        self.inputs = PlanInputs(start_year=2027, grad_year=2031, current_year=2026, current_month=11,
                                 annual_borrowing=5500, rate_pct=6.52, salary_conservative=32000,
                                 salary_expected=45000, salary_aspirational=60000)
        self.plan = compute_plan(self.inputs)
        self.out = self.agent.handle(self.inputs, self.plan)

    def test_timeline_reaches_zero_at_final_payment(self):
        rows = self.out["schedule"]
        self.assertEqual(rows[0]["month"], "Oct 2031")                       # month before the first payment
        for s in self.plan["scenarios"]:
            first_zero = next(r["month"] for r in rows if r[s["scenario"]] == 0)
            self.assertEqual(first_zero, s["debt_free_date"], s["scenario"])
        self.assertEqual(self.out["schedule"][-1]["Standard 10-year plan"], 0)

    def test_milestones_in_order_and_consistent(self):
        for s in self.plan["scenarios"]:
            ms = [m for m in self.out["milestones"] if m["scenario"] == s["scenario"]]
            self.assertEqual([m["milestone"] for m in ms],
                             ["First payment", "25% of starting balance repaid", "Half repaid", "75% repaid",
                              "Debt-free (final payment)"])
            self.assertEqual(ms[-1]["date"], s["debt_free_date"])
            nums = [m["payment_number"] for m in ms]
            self.assertEqual(nums, sorted(nums))
            self.assertAlmostEqual(ms[-1]["interest_paid_so_far"], s["total_interest"], delta=0.05)

    def test_explanation_uses_the_students_numbers(self):
        text = " ".join(st["detail"] for st in self.out["explanation"])
        self.assertIn(f"${self.plan['debt_at_repayment_start']:,.2f}", text)
        self.assertIn(f"${self.plan['standard_monthly_payment']:,.2f}", text)
        self.assertIn(self.plan["debt_free_range"], text)
        self.assertIn("Nov 2031", text)

    def test_no_loans(self):
        inputs = PlanInputs(start_year=2027, grad_year=2031, current_year=2026)
        out = self.agent.handle(inputs, compute_plan(inputs))
        self.assertEqual(out["schedule"], [])
        self.assertEqual(out["explanation"][0]["title"], "No loans")


class SmartFilterTests(unittest.TestCase):
    def test_selected_school_sets_the_only_state(self):
        from app_routes import options_states
        from data_store import get_df
        row = get_df().dropna(subset=["institution_id", "state"]).iloc[0]
        opts = options_states(Filters(school=row["institution_id"]))
        self.assertEqual([o["value"] for o in opts], [row["state"]])

    def test_no_school_offers_all_first(self):
        from app_routes import options_states
        opts = options_states(Filters())
        self.assertEqual(opts[0], {"text": "All", "value": "__all"})
        self.assertGreater(len(opts), 50)

    def test_majors_follow_the_school(self):
        from app_routes import options_majors
        from data_store import get_df
        df = get_df().dropna(subset=["institution_id"])
        iid = df["institution_id"].value_counts().index[0]
        school_majors = {o["value"] for o in options_majors(Filters(school=iid))}
        self.assertEqual(school_majors, set(df[df.institution_id == iid]["cip_title"]))
        self.assertGreater(len(options_majors(Filters())), 300)              # 320 majors overall


class FilterTests(unittest.TestCase):
    df = pd.DataFrame({
        "institution_id": ["1", "2", "3"], "state": ["CA", "NY", "CA"],
        "cip_title": ["Nursing.", "Nursing.", "Biology."], "cip_code": ["5138", "5138", "2601"],
        "credential_level": ["Bachelor's Degree"] * 3, "school_type": ["Public", "Public", "Private, nonprofit"],
        "earnings_cohort": ["c"] * 3,
    })

    def test_all_means_no_filter(self):
        for token in (None, "", "__all", "$__all", "All"):
            self.assertEqual(len(apply_filters(self.df, Filters(state=token))), 3)

    def test_single_and_multi(self):
        self.assertEqual(len(apply_filters(self.df, Filters(state="CA"))), 2)
        self.assertEqual(len(apply_filters(self.df, Filters(state="CA|NY", major="Nursing."))), 2)
        self.assertEqual(parse_multi("{CA|NY}"), ["CA", "NY"])

    def test_without(self):
        f = Filters(state="CA", school="1").without("school")
        self.assertIsNone(f.school)
        self.assertEqual(f.state, "CA")

    def test_parse_number(self):
        msgs = []
        self.assertEqual(parse_number("$12,000", "x", 0, 10**6, None, msgs), 12000)
        self.assertIsNone(parse_number("abc", "x", 0, 10**6, None, msgs))
        self.assertEqual(parse_number("999999999", "x", 0, 100, 5.0, msgs), 5.0)
        self.assertEqual(parse_number("nan", "x", 0, 100, 1.0, msgs), 1.0)
        self.assertEqual(len(msgs), 3)
        self.assertEqual(parse_number("'; DROP TABLE x;--", "x", 0, 1, None, []), None)


class DataTests(unittest.TestCase):
    """Run against the built datasets; skipped if build_reference_data.py has not been run."""

    @classmethod
    def setUpClass(cls):
        from config import SCHOOL_DIRECTORY_CSV, RAW_INST_CSV, STATE_TAX_CSV
        if not (os.path.exists(SCHOOL_DIRECTORY_CSV) and os.path.exists(RAW_INST_CSV)):
            raise unittest.SkipTest("datasets not built")
        cls.directory = pd.read_csv(SCHOOL_DIRECTORY_CSV, dtype=str)
        cls.raw = pd.read_csv(RAW_INST_CSV, usecols=["UNITID", "ADDR"], dtype=str)
        cls.tax = pd.read_csv(STATE_TAX_CSV, dtype=str)

    def test_no_fabricated_addresses(self):
        raw_missing = self.raw["ADDR"].isna() | self.raw["ADDR"].isin(["NULL", "PrivacySuppressed", "PS", "NA"])
        self.assertEqual(int(self.directory["address"].isna().sum()), int(raw_missing.sum()))

    def test_addresses_match_source(self):
        m = self.directory.merge(self.raw, left_on="institution_id", right_on="UNITID")
        both = m.dropna(subset=["address", "ADDR"])
        self.assertTrue((both["address"] == both["ADDR"].str.strip()).all())

    def test_tax_rows_have_year_source_date(self):
        for col in ("tax_year", "official_source_url", "last_verified"):
            self.assertFalse(self.tax[col].isna().any(), col)
        self.assertTrue(self.tax["official_source_url"].str.startswith("https://").all())


class RouteTests(unittest.TestCase):
    def test_state_tax_unsupported(self):
        from app_routes import state_tax
        row = state_tax(Filters(state="OH"))[0]
        self.assertEqual(row["supported"], "Not yet verified")
        self.assertEqual(row["maximum_rate"], "")

    def test_state_tax_none(self):
        from app_routes import state_tax
        row = state_tax(Filters(state="TX"))[0]
        self.assertEqual(row["income_tax_type"], "none")
        self.assertEqual(row["tax_year"], "2025")

    def test_flat_estimate(self):
        from app_routes import estimate_state_tax
        est = estimate_state_tax("PA", 50000)
        self.assertEqual(est["tax"], round(50000 * 0.0307))
        self.assertIsNone(estimate_state_tax("OH", 50000))

    def test_graduated_estimate_ny(self):
        from app_routes import estimate_state_tax
        # $58,000 wages − $8,000 std = $50,000 taxable → $600 + 5.5% × (50,000 − 13,900) = $2,585.50
        # (NY rounds its published $599.50 base up to $600, so marginal math is within $1)
        self.assertAlmostEqual(estimate_state_tax("NY", 58000)["tax"], 2585.5, delta=1.0)

    def test_plan_bad_input_does_not_raise(self):
        from app_routes import PlanParams, plan_estimate, plan_notes
        pp = PlanParams(savings="abc", rate="99", tuition="-5")
        row = plan_estimate(pp, Filters())[0]
        self.assertIn("need attention", row["input_check"])
        notes = plan_notes(pp, Filters())
        self.assertEqual(sum(n["type"].startswith("⚠️") for n in notes), 3)


if __name__ == "__main__":
    unittest.main()
