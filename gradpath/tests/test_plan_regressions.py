"""Calculator edge-case regressions; intentionally independent of pandas/datasets.

Run from gradpath/: python3 -m unittest discover -s tests -p 'test_plan_regressions.py' -v
"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from plan_calc import PlanInputs, compute_plan  # noqa: E402


class RepaymentRegressionTests(unittest.TestCase):
    def plan(self, **overrides):
        args = dict(start_year=2027, grad_year=2031, current_year=2031, current_month=11,
                    existing_balance=30000, rate_pct=6.52, salary_conservative=None,
                    salary_expected=None, salary_aspirational=None)
        args.update(overrides)
        return compute_plan(PlanInputs(**args))

    def test_zero_income_is_distinct_from_missing_salary(self):
        result = self.plan(salary_expected=0)
        zero_income = result["scenarios"][1]
        missing = result["scenarios"][0]

        self.assertEqual(zero_income["starting_salary"], 0)
        self.assertEqual(zero_income["estimated_net_salary"], 0)
        self.assertEqual(zero_income["monthly_payment"], result["standard_monthly_payment"])
        self.assertIsNone(zero_income["payment_share_of_gross_pct"])
        self.assertIsNone(zero_income["payment_share_of_net_pct"])
        self.assertIn("No income is reported", zero_income["affordability_warning"])
        self.assertEqual(missing["debt_free_date"], "Missing salary")

    def test_high_payment_to_income_warns_but_lower_burden_does_not(self):
        scenarios = self.plan(existing_balance=100000, salary_conservative=30000,
                              salary_expected=200000)["scenarios"]
        self.assertGreater(scenarios[0]["payment_share_of_gross_pct"], 30)
        self.assertIsNotNone(scenarios[0]["affordability_warning"])
        self.assertLessEqual(scenarios[1]["payment_share_of_gross_pct"], 30)
        self.assertIsNone(scenarios[1]["affordability_warning"])

    def test_upper_bound_debt_and_rate_remain_finite_and_repay_on_standard_schedule(self):
        scenario = self.plan(existing_balance=2_000_000, rate_pct=25,
                             salary_expected=0)["scenarios"][1]
        self.assertTrue(math.isfinite(scenario["monthly_payment"]))
        self.assertEqual(scenario["months_to_debt_free"], 120)
        self.assertIsNotNone(scenario["affordability_warning"])

    def test_zero_rate_and_zero_income_have_no_interest_and_a_clear_warning(self):
        result = self.plan(existing_balance=12000, rate_pct=0, salary_expected=0)
        scenario = result["scenarios"][1]
        self.assertEqual(scenario["monthly_payment"], 100)
        self.assertEqual(scenario["total_interest"], 0)
        self.assertEqual(scenario["months_to_debt_free"], 120)
        self.assertIsNotNone(scenario["affordability_warning"])

    def test_calculator_matches_independent_monthly_amortization_oracle(self):
        # The oracle below intentionally does not use production schedule helpers.
        principal, rate, annual_salary, repay_pct = 30000.0, 6.52, 60000.0, 10.0
        monthly_rate = rate / 1200
        raw_standard = principal * monthly_rate / (1 - (1 + monthly_rate) ** -120)
        expected_standard = math.ceil(round(raw_standard * 100, 6)) / 100
        salary_payment = annual_salary / 12 * repay_pct / 100
        expected_payment = max(expected_standard, math.ceil(round(salary_payment * 100, 6)) / 100)

        balance, total_interest, payment_count = principal, 0.0, 0
        while balance > 0.005:
            monthly_interest = balance * monthly_rate
            total_interest += monthly_interest
            amount_due = balance + monthly_interest
            paid = min(expected_payment, amount_due)
            balance = max(0.0, amount_due - paid)
            payment_count += 1

        result = self.plan(salary_expected=annual_salary)
        actual = result["scenarios"][1]
        self.assertEqual(result["standard_monthly_payment"], expected_standard)
        self.assertEqual(actual["monthly_payment"], expected_payment)
        self.assertEqual(actual["months_to_debt_free"], payment_count)
        self.assertAlmostEqual(actual["total_interest"], round(total_interest, 2), places=2)


if __name__ == "__main__":
    unittest.main()
