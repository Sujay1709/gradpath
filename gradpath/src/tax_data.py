"""
2024 U.S. State Income Tax Data
================================
Sources:
  - Tax Foundation: "State Individual Income Tax Rates and Brackets 2024"
    https://taxfoundation.org/data/all/state/state-income-tax-rates-2024/
  - IRS: 2024 Federal income tax brackets (Rev. Proc. 2023-34)

Contains:
  - STATE_TAX_BRACKETS: dict[state_abbr → list of (threshold, rate) tuples]
  - FEDERAL_BRACKETS_2024: federal single/married brackets
  - STANDARD_DEDUCTION_2024: single/married/hoh
  - FLAT_TAX_STATES: states with a single flat rate
  - NO_INCOME_TAX_STATES: states with no individual income tax

NOTE: These are the TOP marginal rates and bracket structures for 2024.
This is for educational illustration only. For accurate tax filing,
consult the IRS and your state's department of revenue.
"""

# ── No income tax states ──────────────────────────────────────────────────────
NO_INCOME_TAX_STATES = {
    "AK": "Alaska",
    "FL": "Florida",
    "NV": "Nevada",
    "NH": "New Hampshire",   # Only taxes interest/dividends, phasing out
    "SD": "South Dakota",
    "TN": "Tennessee",       # No wage tax
    "TX": "Texas",
    "WA": "Washington",      # No income tax (has capital gains tax)
    "WY": "Wyoming",
}

# ── Flat tax states (single rate on all income) ───────────────────────────────
FLAT_TAX_STATES = {
    "AZ": 2.5,
    "CO": 4.4,
    "GA": 5.49,
    "ID": 5.8,
    "IL": 4.95,
    "IN": 3.05,
    "KY": 4.0,
    "MA": 5.0,
    "MI": 4.25,
    "MS": 4.7,
    "NC": 4.5,
    "PA": 3.07,
    "UT": 4.65,
}

# ── Progressive bracket states: (income_threshold, marginal_rate_%) ──────────
# Format: sorted list of (threshold, rate) — income >= threshold taxed at rate
# Last entry threshold is the catch-all (use last for all above)
STATE_TAX_BRACKETS: dict[str, list[tuple[float, float]]] = {
    "AL": [(0, 2.0), (500, 4.0), (3000, 5.0)],
    "AR": [(0, 2.0), (4300, 4.0), (8500, 4.9)],
    "CA": [(0, 1.0), (10099, 2.0), (23942, 4.0), (37788, 6.0),
           (52455, 8.0), (66295, 9.3), (338639, 10.3), (406364, 11.3),
           (677275, 12.3), (1000000, 13.3)],
    "CT": [(0, 2.0), (10000, 4.5), (50000, 5.5), (100000, 6.0),
           (200000, 6.5), (250000, 6.9), (500000, 6.99)],
    "DE": [(0, 0.0), (2000, 2.2), (5000, 3.9), (10000, 4.8),
           (20000, 5.2), (25000, 5.55), (60000, 6.6)],
    "HI": [(0, 1.4), (2400, 3.2), (4800, 5.5), (9600, 6.4),
           (14400, 6.8), (19200, 7.2), (24000, 7.6), (36000, 7.9),
           (48000, 8.25), (150000, 9.0), (175000, 10.0), (200000, 11.0)],
    "IA": [(0, 4.4), (6000, 4.82), (30000, 5.7), (75000, 6.0)],
    "KS": [(0, 3.1), (15000, 5.25), (30000, 5.7)],
    "LA": [(0, 1.85), (12500, 3.5), (50000, 4.25)],
    "ME": [(0, 5.8), (23000, 6.75), (54450, 7.15)],
    "MD": [(0, 2.0), (1000, 3.0), (2000, 4.0), (3000, 4.75),
           (100000, 5.0), (125000, 5.25), (150000, 5.5), (250000, 5.75)],
    "MN": [(0, 5.35), (30070, 6.80), (98760, 7.85), (183340, 9.85)],
    "MO": [(0, 1.5), (1207, 2.0), (2414, 2.5), (3621, 3.0),
           (4828, 3.5), (6035, 4.0), (7242, 4.5), (8449, 5.0), (9656, 5.4)],
    "MT": [(0, 4.7), (20500, 5.9)],
    "NE": [(0, 2.46), (3700, 3.51), (22170, 5.01), (35730, 6.64)],
    "NJ": [(0, 1.4), (20000, 1.75), (35000, 3.5), (40000, 5.525),
           (75000, 6.37), (500000, 8.97), (1000000, 10.75)],
    "NM": [(0, 1.7), (5500, 3.2), (11000, 4.7), (16000, 4.9), (210000, 5.9)],
    "NY": [(0, 4.0), (8500, 4.5), (11700, 5.25), (13900, 5.85),
           (21400, 6.25), (80650, 6.85), (215400, 9.65), (1077550, 10.3),
           (5000000, 10.9)],
    "ND": [(0, 1.1), (44725, 2.04), (225975, 2.27)],
    "OH": [(0, 0.0), (26050, 2.765), (46100, 3.226), (92150, 3.688),
           (115300, 3.99)],
    "OK": [(0, 0.25), (1000, 0.75), (2500, 1.75), (3750, 2.75),
           (4900, 3.75), (7200, 4.75)],
    "OR": [(0, 4.75), (18400, 6.75), (250000, 8.75), (400000, 9.9)],
    "RI": [(0, 3.75), (77450, 4.75), (176050, 5.99)],
    "SC": [(0, 0.0), (3460, 3.0), (17330, 6.4)],
    "VT": [(0, 3.35), (45400, 6.60), (110050, 7.60), (229550, 8.75)],
    "VA": [(0, 2.0), (3000, 3.0), (5000, 5.0), (17000, 5.75)],
    "WI": [(0, 3.50), (14320, 4.40), (28640, 5.30), (315310, 7.65)],
    "WV": [(0, 3.0), (10000, 4.0), (25000, 4.5), (40000, 6.0), (60000, 6.5)],
}

# Add flat-tax states to brackets structure for uniform handling
for _st, _rate in FLAT_TAX_STATES.items():
    STATE_TAX_BRACKETS[_st] = [(0, _rate)]

# No-tax states get 0% brackets
for _st in NO_INCOME_TAX_STATES:
    STATE_TAX_BRACKETS[_st] = [(0, 0.0)]

# ── 2024 Federal brackets (single filer) ─────────────────────────────────────
FEDERAL_BRACKETS_2024_SINGLE = [
    (0,       10.0),
    (11600,   12.0),
    (47150,   22.0),
    (100525,  24.0),
    (191950,  32.0),
    (243725,  35.0),
    (609350,  37.0),
]

FEDERAL_BRACKETS_2024_MARRIED = [
    (0,       10.0),
    (23200,   12.0),
    (94300,   22.0),
    (201050,  24.0),
    (383900,  32.0),
    (487450,  35.0),
    (731200,  37.0),
]

# ── 2024 Standard deductions ──────────────────────────────────────────────────
STANDARD_DEDUCTION_2024 = {
    "single":  14600,
    "married": 29200,
    "hoh":     21900,
}

# FICA: Social Security (6.2% up to $168,600) + Medicare (1.45%)
FICA_SS_RATE      = 6.2
FICA_SS_WAGE_BASE = 168_600
FICA_MEDICARE     = 1.45
FICA_MEDICARE_ADDL = 0.9    # Additional 0.9% on wages > $200,000 (single)
FICA_MEDICARE_ADDL_THRESHOLD = 200_000


def compute_tax(income: float, brackets: list[tuple[float, float]]) -> float:
    """
    Compute tax owed given income and a list of (threshold, rate%) brackets.
    Uses marginal (progressive) calculation.
    """
    if not brackets:
        return 0.0
    tax = 0.0
    sorted_brackets = sorted(brackets, key=lambda x: x[0])
    for i, (threshold, rate) in enumerate(sorted_brackets):
        if income <= threshold:
            break
        next_threshold = sorted_brackets[i + 1][0] if i + 1 < len(sorted_brackets) else float("inf")
        taxable_in_bracket = min(income, next_threshold) - threshold
        tax += taxable_in_bracket * (rate / 100)
    return round(tax, 2)


def compute_federal_tax(income: float, filing_status: str = "single") -> float:
    """Compute 2024 federal income tax after standard deduction."""
    deduction = STANDARD_DEDUCTION_2024.get(filing_status, STANDARD_DEDUCTION_2024["single"])
    taxable = max(0.0, income - deduction)
    brackets = FEDERAL_BRACKETS_2024_MARRIED if filing_status == "married" else FEDERAL_BRACKETS_2024_SINGLE
    return compute_tax(taxable, brackets)


def compute_state_tax(income: float, state: str) -> float:
    """Compute estimated state income tax. Returns 0 for no-tax states."""
    brackets = STATE_TAX_BRACKETS.get(state.upper(), [(0, 0.0)])
    return compute_tax(income, brackets)


def compute_fica(income: float) -> dict:
    """Compute FICA (Social Security + Medicare) for a single filer."""
    ss = min(income, FICA_SS_WAGE_BASE) * (FICA_SS_RATE / 100)
    medicare = income * (FICA_MEDICARE / 100)
    medicare_addl = max(0, income - FICA_MEDICARE_ADDL_THRESHOLD) * (FICA_MEDICARE_ADDL / 100)
    return {
        "social_security": round(ss, 2),
        "medicare": round(medicare + medicare_addl, 2),
        "total_fica": round(ss + medicare + medicare_addl, 2),
    }


def get_marginal_federal_rate(income: float, filing_status: str = "single") -> float:
    """Return the marginal federal tax rate for a given income."""
    deduction = STANDARD_DEDUCTION_2024.get(filing_status, STANDARD_DEDUCTION_2024["single"])
    taxable = max(0.0, income - deduction)
    brackets = FEDERAL_BRACKETS_2024_MARRIED if filing_status == "married" else FEDERAL_BRACKETS_2024_SINGLE
    for threshold, rate in reversed(brackets):
        if taxable >= threshold:
            return rate
    return 0.0


def get_marginal_state_rate(income: float, state: str) -> float:
    """Return the top marginal state rate that applies to this income."""
    brackets = STATE_TAX_BRACKETS.get(state.upper(), [(0, 0.0)])
    for threshold, rate in reversed(sorted(brackets)):
        if income >= threshold:
            return rate
    return 0.0


# ── Tax bracket classification labels ────────────────────────────────────────
def classify_federal_bracket(income: float, filing_status: str = "single") -> str:
    """Return the federal tax bracket label for a given income."""
    rate = get_marginal_federal_rate(income, filing_status)
    return f"{int(rate)}%"


def effective_tax_rate(income: float, state: str, filing_status: str = "single") -> dict:
    """
    Compute total effective tax burden: federal + state + FICA.
    Returns a breakdown dict.
    """
    federal = compute_federal_tax(income, filing_status)
    state_tax = compute_state_tax(income, state)
    fica = compute_fica(income)

    total = federal + state_tax + fica["total_fica"]
    return {
        "gross_income": income,
        "state": state.upper(),
        "filing_status": filing_status,
        "federal_income_tax": federal,
        "state_income_tax": state_tax,
        "fica_social_security": fica["social_security"],
        "fica_medicare": fica["medicare"],
        "total_tax": round(total, 2),
        "net_income": round(income - total, 2),
        "effective_rate_pct": round(total / income * 100, 2) if income > 0 else 0.0,
        "marginal_federal_rate_pct": get_marginal_federal_rate(income, filing_status),
        "marginal_state_rate_pct": get_marginal_state_rate(income, state),
        "federal_bracket": classify_federal_bracket(income, filing_status),
    }
