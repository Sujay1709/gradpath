"""
Metric calculations for GradPath.

All formulas are explicit and documented — no mystery scoring.
"""
import pandas as pd
import numpy as np


def add_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add comparison metrics to the cleaned dataframe.

    Metrics:
    - debt_to_earnings  = median_debt / median_earnings
      Lower = less debt relative to annual income.

    - earnings_to_debt  = median_earnings / median_debt
      Higher = more annual income relative to debt.
      Returns NaN when debt is zero (avoid infinity).

    - earnings_debt_difference = median_earnings - median_debt
      Positive = annual earnings exceed total cumulative debt.
    """
    df = df.copy()

    df["debt_to_earnings"] = (df["median_debt"] / df["median_earnings"]).round(3)

    # Earnings-to-debt: handle zero debt without producing inf
    df["earnings_to_debt"] = np.where(
        df["median_debt"] > 0,
        (df["median_earnings"] / df["median_debt"]).round(3),
        np.nan,
    )

    df["earnings_debt_difference"] = (df["median_earnings"] - df["median_debt"]).round(0)

    return df
