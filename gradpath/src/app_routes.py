"""
GradPath app endpoints (Overview / Schools / States & Taxes / Graphs / My Plan / Help).

Every endpoint returns a JSON array of flat objects, the shape the
marcusolsson-json-datasource plugin maps to Grafana fields. Shared dashboard
filters arrive as query params and are applied by filters.apply_filters.
"""
import os
import sys
from datetime import date
from functools import lru_cache

import pandas as pd
from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import FileResponse, Response

from config import DATA_YEAR_LABEL, SCORECARD_URL, STATIC_DIR
from data_store import (
    STATE_NAMES, get_df, get_directory, get_source_registry, get_tax_brackets,
    get_tax_reference, to_records,
)
from filters import Filters, apply_filters, parse_multi, parse_number
from plan_calc import ASSUMPTIONS, PlanInputs, compute_plan

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # gradpath/ → pipeline pkg
from pipeline.agents.repayment_timeline_agent import RepaymentTimelineAgent  # noqa: E402

timeline_agent = RepaymentTimelineAgent()

router = APIRouter()

NOT_REPORTED = "Not reported in College Scorecard"
NOT_VERIFIED = "Not verified"
DEFAULT_LOAN_RATE = 6.52  # https://fsapartners.ed.gov (GENERAL-26-33), undergrad Direct Loans 2026–27
SOURCE_LABEL = "U.S. Dept. of Education — College Scorecard"


def _cip_label(code: str) -> str:
    code = str(code)
    return f"{code[:2]}.{code[2:]}" if len(code) == 4 and code.isdigit() else code


def _dir_lookup() -> pd.DataFrame:
    d = get_directory()
    return d.set_index("institution_id") if len(d) else d


# ── Variable option lists ────────────────────────────────────────────────────
# Dependency order (no cycles): state, school_type, credential → major → cip → school

ALL_OPTION = {"text": "All", "value": "__all"}


@router.get("/options/states")
def options_states(flt: Filters = Depends()):
    """
    With a school selected, the only option is that school's state, so Grafana switches the
    State box to it automatically. Otherwise "All" plus every state with matching programs.
    """
    iid = _selected_school(flt)
    if iid:
        states = get_df().loc[get_df()["institution_id"] == iid, "state"].dropna().unique()
        if len(states):
            return [{"text": f"{c} — {STATE_NAMES.get(c, c)}", "value": c} for c in sorted(states)]
        return [ALL_OPTION]
    df = apply_filters(get_df(), flt.without("state", "school", "major", "cip"))
    codes = sorted(df["state"].dropna().unique())
    return [ALL_OPTION] + [{"text": f"{c} — {STATE_NAMES.get(c, c)}", "value": c} for c in codes]


@router.get("/options/school_types")
def options_school_types():
    return [{"text": v, "value": v} for v in sorted(get_df()["school_type"].dropna().unique())]


@router.get("/options/credentials")
def options_credentials():
    return [{"text": v, "value": v} for v in sorted(get_df()["credential_level"].dropna().unique())]


@router.get("/options/majors")
def options_majors(flt: Filters = Depends()):
    df = apply_filters(get_df(), flt.without("major", "cip"))      # a selected school narrows its majors
    return [{"text": v.rstrip("."), "value": v} for v in sorted(df["cip_title"].dropna().unique())]


@router.get("/options/cips")
def options_cips(flt: Filters = Depends()):
    df = apply_filters(get_df(), flt.without("cip"))
    pairs = df[["cip_code", "cip_title"]].drop_duplicates().sort_values("cip_code")
    return [{"text": f"{_cip_label(c)} — {t.rstrip('.')}", "value": c} for c, t in pairs.itertuples(index=False)]


@router.get("/options/schools")
def options_schools(flt: Filters = Depends()):
    f = flt.without("school")
    return Response(content=_school_options_json(f.state, f.major, f.cip, f.credential, f.school_type,
                                                 f.data_year), media_type="application/json")


@lru_cache(maxsize=256)
def _school_options_json(state, major, cip, credential, school_type, data_year) -> str:
    """'Name — City, ST' labels keyed by institution ID; cached because every page load asks for them."""
    flt = Filters(state=state, major=major, cip=cip, credential=credential, school_type=school_type,
                  data_year=data_year)
    df = apply_filters(get_df(), flt)
    # 2 source rows have no UNITID and so cannot be selected; they still count in aggregates
    schools = (df[["institution_id", "institution_name", "state"]]
               .dropna(subset=["institution_id"]).drop_duplicates("institution_id"))
    d = get_directory()
    if len(d):
        schools = schools.merge(d[["institution_id", "city"]], on="institution_id", how="left")
    else:
        schools = schools.assign(city=None)
    where = (schools["city"].fillna("") + ", " + schools["state"].fillna("")).str.strip(", ")
    text = schools["institution_name"].where(where == "", schools["institution_name"] + " — " + where)
    out = pd.DataFrame({"text": text, "value": schools["institution_id"]})
    out = out.iloc[out["text"].str.lower().argsort(kind="stable")]
    return out.to_json(orient="records", force_ascii=False)


@router.get("/options/data_years")
def options_data_years():
    return [{"text": DATA_YEAR_LABEL, "value": v} for v in sorted(get_df()["earnings_cohort"].dropna().unique())]


# ── Graph data ───────────────────────────────────────────────────────────────

SCATTER_SERIES = {
    "Public": "earnings_public",
    "Private, nonprofit": "earnings_private_nonprofit",
    "Private, for-profit": "earnings_private_for_profit",
}


@router.get("/metrics/scatter")
def scatter(flt: Filters = Depends()):
    """One frame with a stable earnings column per school type, so series colours never shift."""
    df = apply_filters(get_df(), flt)
    out = pd.DataFrame({
        "median_debt": df["median_debt"].round(0),
        **{col: df["median_earnings"].where(df["school_type"] == st).round(0) for st, col in SCATTER_SERIES.items()},
        "cohort_size": df["cohort_size"],
        "median_earnings": df["median_earnings"].round(0),
        "debt_to_earnings": df["debt_to_earnings"].round(2),
        "school": df["institution_name"],
        "program": df["cip_title"].str.rstrip("."),
        "state": df["state"].fillna("Not reported"),
        "credential": df["credential_level"],
        "school_type": df["school_type"],
    })
    return to_records(out.sort_values("median_debt"))


@router.get("/metrics/scatter_reference")
def scatter_reference(flt: Filters = Depends()):
    df = apply_filters(get_df(), flt)
    top = float(max(df["median_debt"].max(), df["median_earnings"].max())) if len(df) else 100000.0
    return [{"ref_debt": 0.0, "earnings_equal_debt": 0.0}, {"ref_debt": top, "earnings_equal_debt": top}]


GROUP_COLUMNS = {
    "state": "state", "credential": "credential_level", "school_type": "school_type", "major": "cip_title",
}


@router.get("/metrics/group")
def grouped(by: str = Query("state", pattern="^(state|credential|school_type|major)$"),
            sort: str = Query("median_earnings", pattern="^(median_earnings|median_debt|debt_to_earnings|programs|name)$"),
            n: int = Query(60, ge=1, le=300),
            min_programs: int = Query(1, ge=1, le=100),
            flt: Filters = Depends()):
    """Median earnings, median debt and the median-of-ratios per group."""
    col = GROUP_COLUMNS[by]
    df = apply_filters(get_df(), flt).dropna(subset=[col])
    if df.empty:
        return []
    g = df.groupby(col).agg(
        median_earnings=("median_earnings", "median"),
        median_debt=("median_debt", "median"),
        debt_to_earnings=("debt_to_earnings", "median"),
        programs=("median_earnings", "size"),
        schools=("institution_id", "nunique"),
    ).reset_index().rename(columns={col: "name"})
    g = g[g["programs"] >= min_programs]
    if by == "state":
        g["label"] = g["name"].map(lambda c: f"{c} — {STATE_NAMES.get(c, c)}")
    else:
        g["label"] = g["name"].str.rstrip(".")
    ascending = sort in ("debt_to_earnings", "name", "median_debt")
    g = g.sort_values(sort, ascending=ascending).head(n)
    g[["median_earnings", "median_debt"]] = g[["median_earnings", "median_debt"]].round(0)
    g["debt_to_earnings"] = g["debt_to_earnings"].round(2)
    return to_records(g)


# ── Schools ──────────────────────────────────────────────────────────────────

def _with_directory(df: pd.DataFrame) -> pd.DataFrame:
    d = get_directory()
    keep = ["institution_id", "address", "city", "zip", "latitude", "longitude", "source_year"]
    return df.merge(d[keep] if len(d) else pd.DataFrame(columns=keep), on="institution_id", how="left")


@router.get("/schools/table")
def schools_table(limit: int = Query(500, ge=1, le=5000),
                  sort: str = Query("debt_to_earnings", pattern="^(debt_to_earnings|median_earnings|median_debt)$"),
                  flt: Filters = Depends()):
    df = _with_directory(apply_filters(get_df(), flt))
    df = df.sort_values(sort, ascending=(sort != "median_earnings")).head(limit)
    out = pd.DataFrame({
        "rank": range(1, len(df) + 1),
        "school": df["institution_name"].values,
        "institution_id": df["institution_id"].values,
        "school_type": df["school_type"].values,
        "city_state": [", ".join(x for x in (c, s) if isinstance(x, str)) or NOT_REPORTED
                       for c, s in zip(df["city"], df["state"])],
        "address": df["address"].fillna(NOT_REPORTED).values,
        "program": df["cip_title"].str.rstrip(".").values,
        "credential": df["credential_level"].values,
        "median_earnings": df["median_earnings"].round(0).values,
        "median_debt": df["median_debt"].round(0).values,
        "debt_to_earnings": df["debt_to_earnings"].round(2).values,
        "cohort_size": df["cohort_size"].values,
        "source_year": DATA_YEAR_LABEL,
    })
    return to_records(out)


def _selected_school(flt: Filters) -> str | None:
    vals = parse_multi(flt.school)
    return vals[0] if vals and len(vals) == 1 else None


@router.get("/schools/detail")
def school_detail(flt: Filters = Depends()):
    iid = _selected_school(flt)
    if iid is None:
        hint = "No school selected — type a name in the School box, or click a school in the table below."
        return [{"card": "Value", "school_name": hint, "address": "—", "city_state_zip": "—", "school_type": "—",
                 "matching_programs": "—", "address_source": "—", "outcomes_source": "—"}]
    progs = apply_filters(get_df(), flt)
    base = get_df()[get_df()["institution_id"] == iid]
    d = _dir_lookup()
    row = d.loc[iid] if len(d) and iid in d.index else None

    def val(col):
        if row is None:
            return None
        v = row[col]
        return None if pd.isna(v) else v

    name = val("school_name") or (base["institution_name"].iloc[0] if len(base) else "Unknown school")
    city, st, zp = val("city"), val("state"), val("zip")
    return [{"card": "Value", 
        "school_name": name,
        "address": val("address") or NOT_REPORTED,
        "city_state_zip": " ".join(x for x in [", ".join(y for y in [city, st] if y), zp] if x) or NOT_REPORTED,
        "school_type": val("school_type") or (base["school_type"].iloc[0] if len(base) else None),
        "matching_programs": int(len(progs)),
        "all_reported_programs": int(len(base)),
        "median_earnings": float(progs["median_earnings"].median()) if len(progs) else None,
        "median_debt": float(progs["median_debt"].median()) if len(progs) else None,
        "debt_to_earnings": round(float(progs["debt_to_earnings"].median()), 2) if len(progs) else None,
        "total_cohort": float(progs["cohort_size"].sum()) if len(progs) else None,
        "latitude": val("latitude"),
        "longitude": val("longitude"),
        "address_source": val("source_year") or "No directory record",
        "outcomes_source": f"{SOURCE_LABEL}, {DATA_YEAR_LABEL}",
    }]


@router.get("/schools/programs")
def school_programs(flt: Filters = Depends()):
    iid = _selected_school(flt)
    if iid is None:
        return []
    df = apply_filters(get_df(), flt).sort_values("median_earnings", ascending=False)
    return to_records(pd.DataFrame({
        "program": df["cip_title"].str.rstrip("."),
        "major_value": df["cip_title"],
        "cip_code": df["cip_code"].map(_cip_label),
        "credential": df["credential_level"],
        "median_earnings": df["median_earnings"].round(0),
        "median_debt": df["median_debt"].round(0),
        "debt_to_earnings": df["debt_to_earnings"].round(2),
        "cohort_size": df["cohort_size"],
    }))


# ── States & taxes ───────────────────────────────────────────────────────────

TAX_FIELDS = ["state_code", "state_name", "tax_year", "income_tax_type", "minimum_rate", "maximum_rate",
              "standard_deduction_single", "student_loan_interest_treatment", "education_credit_summary",
              "official_source_url", "last_verified", "verification_method", "notes"]
DISPLAY_IF_BLANK = ("standard_deduction_single", "student_loan_interest_treatment", "education_credit_summary")


def _single_state(flt: Filters) -> str | None:
    vals = parse_multi(flt.state)
    return vals[0] if vals and len(vals) == 1 else None


@router.get("/states/tax")
def state_tax(flt: Filters = Depends()):
    code = _single_state(flt)
    if code is None:
        return [{"card": "Value", **{f: "" for f in TAX_FIELDS}, "supported": "Select one state",
                 "rate_summary": "Choose a single state in the State box to see its tax facts."}]
    ref = get_tax_reference()
    hit = ref[ref["state_code"] == code] if len(ref) else ref
    if hit.empty:
        return [{"card": "Value", **{f: "" for f in TAX_FIELDS}, "state_code": code, "state_name": STATE_NAMES.get(code, code),
                 "supported": "Not yet verified",
                 "rate_summary": (f"{STATE_NAMES.get(code, code)} is not in GradPath's verified demonstration set yet. "
                                  "Check the state's department of revenue for current rules."),
                 "notes": "No tax figures are shown for unverified states."}]
    r = hit.iloc[0].to_dict()
    shown = {k: (v if v != "" or k not in DISPLAY_IF_BLANK else NOT_VERIFIED) for k, v in r.items()}
    if r["income_tax_type"] == "none":
        shown["standard_deduction_single"] = "Not applicable (no wage income tax)"
    elif r["standard_deduction_single"]:
        shown["standard_deduction_single"] = f"${float(r['standard_deduction_single']):,.0f}"
    status = "Verified" if r.get("verification_method", "").startswith("official page read") else "Verified — confirm manually"
    return [{"card": "Value", **shown, "supported": status, "rate_summary": _rate_summary(r)}]


def _rate_summary(r: dict) -> str:
    kind = r.get("income_tax_type", "")
    lo, hi = r.get("minimum_rate", ""), r.get("maximum_rate", "")
    if kind == "none":
        return f"No individual income tax on wages (tax year {r['tax_year']})."
    if kind == "flat":
        return f"Flat rate of {hi}% on taxable income (tax year {r['tax_year']})."
    if kind == "graduated":
        return f"Graduated rates from {lo}% to {hi}% depending on taxable income (tax year {r['tax_year']})."
    return r.get("notes", "")


@router.get("/states/tax_table")
def state_tax_table():
    ref = get_tax_reference()
    if ref.empty:
        return []
    out = ref.copy()
    out["rate_summary"] = [_rate_summary(r) for r in ref.to_dict(orient="records")]
    return out[["state_code", "state_name", "tax_year", "income_tax_type", "rate_summary",
                "last_verified", "official_source_url"]].to_dict(orient="records")


def estimate_state_tax(code: str, wages: float) -> dict | None:
    """Educational estimate for a single filer with only wage income. None if unsupported."""
    ref = get_tax_reference()
    hit = ref[ref["state_code"] == code] if len(ref) else ref
    if hit.empty:
        return None
    r = hit.iloc[0]
    std = float(r["standard_deduction_single"]) if r["standard_deduction_single"] else 0.0
    taxable = max(0.0, wages - std)
    kind = r["income_tax_type"]
    if kind == "none":
        tax = 0.0
    elif kind == "flat":
        tax = taxable * float(r["maximum_rate"]) / 100
    else:
        b = get_tax_brackets()
        b = b[(b["state_code"] == code) & (b["filing_status"] == "single")].sort_values("lower_bound")
        if b.empty:
            return None
        tax, bounds = 0.0, list(b["lower_bound"].astype(float)) + [float("inf")]
        for i, rate in enumerate(b["rate_pct"].astype(float)):
            lo, hi = bounds[i], bounds[i + 1]
            if taxable > lo:
                tax += (min(taxable, hi) - lo) * rate / 100
    return {"tax": round(tax, 0), "tax_year": r["tax_year"], "taxable": round(taxable, 0),
            "standard_deduction_used": std, "kind": kind}


@router.get("/states/tax_estimate")
def state_tax_estimate(income: str | None = None, flt: Filters = Depends()):
    """Educational example for one state: wages-only single filer, standard deduction if verified."""
    code = _single_state(flt)
    msgs: list[str] = []
    wages = parse_number(income, "Example salary", 0, 2_000_000, 50000.0, msgs)
    est = estimate_state_tax(code, wages) if code else None
    if est is None:
        return [{"card": "Value", "example_salary": wages, "estimated_state_tax": None, "effective_rate_pct": None,
                 "taxable_income": None, "tax_year": "",
                 "assumptions": ("Select one verified state to see an example." if code is None else
                                 f"No estimate: {STATE_NAMES.get(code, code)} is not in the verified set "
                                 "(or its brackets are not loaded)."),
                 "input_check": " ".join(msgs) or "OK"}]
    std_note = (f"minus the ${est['standard_deduction_used']:,.0f} standard deduction" if est["standard_deduction_used"]
                else "with no standard deduction applied")
    return [{"card": "Value", 
        "example_salary": wages,
        "estimated_state_tax": est["tax"],
        "effective_rate_pct": round(est["tax"] / wages * 100, 2) if wages else 0.0,
        "taxable_income": est["taxable"],
        "tax_year": est["tax_year"],
        "assumptions": (f"Tax year {est['tax_year']}. Single filer, wage income only, {std_note}. "
                        "Ignores credits, local taxes, other deductions and exemptions. Educational estimate — not tax advice."),
        "input_check": " ".join(msgs) or "OK",
    }]


# ── My Plan ──────────────────────────────────────────────────────────────────

PLAN_PARAMS = dict(
    start_year=("Start year", 2000, 2045), grad_year=("Graduation year", 2000, 2055),
    savings=("Current savings", 0, 2_000_000), contribution=("Annual savings contribution", 0, 500_000),
    grants=("Scholarships & grants per year", 0, 500_000), existing_debt=("Existing student-loan balance", 0, 2_000_000),
    borrowing=("Expected annual borrowing", 0, 500_000), rate=("Loan interest rate %", 0, 25),
    tuition=("Annual tuition", 0, 500_000), living=("Annual living expenses", 0, 500_000),
    salary_low=("Conservative salary", 0, 2_000_000), salary_mid=("Expected salary", 0, 2_000_000),
    salary_high=("Aspirational salary", 0, 2_000_000), repay_pct=("Share of salary for loans %", 1, 50),
)


class PlanParams:
    def __init__(self, start_year: str | None = None, grad_year: str | None = None, savings: str | None = None,
                 contribution: str | None = None, grants: str | None = None, existing_debt: str | None = None,
                 borrowing: str | None = None, rate: str | None = None, tuition: str | None = None,
                 living: str | None = None, salary_low: str | None = None, salary_mid: str | None = None,
                 salary_high: str | None = None, repay_pct: str | None = None, in_state: str | None = None,
                 work_state: str | None = None, occupation: str | None = None):
        self.raw = {k: v for k, v in locals().items() if k != "self"}


def _plan_context(pp: PlanParams, flt: Filters) -> dict:
    """Validate inputs, auto-fill from Scorecard where blank, run the deterministic plan."""
    msgs: list[str] = []
    today = date.today()
    raw = pp.raw
    num = {k: parse_number(raw.get(k), label, lo, hi, None, msgs) for k, (label, lo, hi) in PLAN_PARAMS.items()}
    provenance: dict[str, str] = {}
    entered = {k for k, v in num.items() if v is not None}
    for k in entered:
        provenance[k] = "You entered"

    iid = _selected_school(flt)
    progs = apply_filters(get_df(), flt)
    d = _dir_lookup()
    drow = d.loc[iid] if iid and len(d) and iid in d.index else None
    in_state = (raw.get("in_state") or "yes").strip().lower() not in ("no", "false", "0", "out", "out-of-state")

    # Auto-fill tuition from Scorecard published tuition & fees when blank
    if num["tuition"] is None and drow is not None:
        col = "tuition_fees_in_state" if in_state else "tuition_fees_out_of_state"
        if col in drow.index and not pd.isna(drow[col]):
            num["tuition"] = float(drow[col])
            provenance["tuition"] = f"Scorecard published tuition & fees ({'in' if in_state else 'out-of'}-state) — editable"

    hist_earn = float(progs["median_earnings"].median()) if len(progs) else None
    hist_debt = float(progs["median_debt"].median()) if len(progs) else None
    cohort = float(progs["cohort_size"].sum()) if len(progs) else 0.0
    if num["salary_mid"] is None and hist_earn is not None:
        num["salary_mid"] = hist_earn
        provenance["salary_mid"] = "Scorecard historical median earnings — editable"

    lo, mid, hi = num["salary_low"], num["salary_mid"], num["salary_high"]
    if (lo is not None and mid is not None and lo > mid) or (mid is not None and hi is not None and mid > hi):
        msgs.append("Salary scenarios are out of order (conservative ≤ expected ≤ aspirational). "
                    "Check them — the expected salary may have been auto-filled from Scorecard.")

    start = int(num["start_year"]) if num["start_year"] is not None else today.year + (1 if today.month > 8 else 0)
    if num["start_year"] is None:
        provenance["start_year"] = "Assumed next fall"
    grad = int(num["grad_year"]) if num["grad_year"] is not None else start + 4
    if num["grad_year"] is None:
        provenance["grad_year"] = "Assumed 4 years after start"
    if grad <= start:
        msgs.append("Graduation year must be after the start year — using start year + 1.")
        grad = start + 1
    rate = num["rate"] if num["rate"] is not None else DEFAULT_LOAN_RATE
    if num["rate"] is None:
        provenance["rate"] = (f"Assumed {DEFAULT_LOAN_RATE}% — federal undergraduate Direct Loan rate for loans "
                              "first disbursed July 1, 2026–June 30, 2027 (FSA GENERAL-26-33)")
    repay = num["repay_pct"] if num["repay_pct"] is not None else 10.0
    if num["repay_pct"] is None:
        provenance["repay_pct"] = "Assumed 10% of gross salary"

    inputs = PlanInputs(
        start_year=start, grad_year=grad, current_year=today.year, current_month=today.month,
        current_savings=num["savings"] or 0.0, annual_contribution=num["contribution"] or 0.0,
        annual_grants=num["grants"] or 0.0, existing_balance=num["existing_debt"] or 0.0,
        annual_borrowing=num["borrowing"] or 0.0, rate_pct=rate,
        annual_tuition=num["tuition"] or 0.0, annual_living=num["living"] or 0.0,
        salary_conservative=num["salary_low"], salary_expected=num["salary_mid"],
        salary_aspirational=num["salary_high"], repay_pct=repay,
    )
    result = compute_plan(inputs)

    missing = [PLAN_PARAMS[k][0] for k in ("tuition", "living", "savings", "borrowing", "salary_low", "salary_high")
               if num[k] is None]
    if iid is None:
        missing.insert(0, "School (pick one in the School box)")

    # Rule-based confidence in the historical comparison
    if iid and parse_multi(flt.major) and len(progs) == 1 and cohort >= 30:
        confidence = "High — exact school + program match with 30+ graduates measured"
    elif iid and parse_multi(flt.major) and len(progs) >= 1:
        confidence = "Medium — school + program match, but fewer than 30 graduates measured"
    elif len(progs) >= 1:
        confidence = "Medium — based on a broader group (pick both a school and a major for a closer match)"
    else:
        confidence = "Low — no Scorecard record matches these filters"

    work_state = (raw.get("work_state") or "").strip().upper()[:2] or None
    tax_rows = []
    if work_state:
        for s in result["scenarios"]:
            est = estimate_state_tax(work_state, s["starting_salary"]) if s["starting_salary"] else None
            tax_rows.append((s["scenario"], est))

    return dict(inputs=inputs, result=result, msgs=msgs, provenance=provenance, missing=missing, iid=iid,
                drow=drow, progs=progs, hist_earn=hist_earn, hist_debt=hist_debt, cohort=cohort,
                confidence=confidence, in_state=in_state, work_state=work_state, tax_rows=tax_rows,
                occupation=(raw.get("occupation") or "").strip()[:80])


PLAN_MONEY = ["total_education_cost", "savings_at_enrollment", "grants_total", "funding_gap",
              "gap_after_planned_borrowing", "new_borrowing_total", "debt_at_repayment_start",
              "standard_monthly_payment", "standard_total_interest", "historical_median_earnings",
              "historical_median_debt"]


def _dollars(value, cents=False) -> str:
    if value is None or (isinstance(value, float) and value != value):
        return "—"
    return f"${value:,.2f}" if cents else f"${round(value):,}"


@router.get("/plan/estimate")
def plan_estimate(pp: PlanParams = Depends(), flt: Filters = Depends()):
    c = _plan_context(pp, flt)
    r, drow = c["result"], c["drow"]
    if drow is not None:
        name = drow["school_name"]
    elif c["iid"] is None:
        name = "No school selected"
    else:
        # schools missing from the Institution file still have a name in the Field of Study data
        hit = get_df().loc[get_df()["institution_id"] == c["iid"], "institution_name"]
        name = f"{hit.iloc[0]} (address not reported)" if len(hit) else "School not found"
    addr = (drow["address"] if drow is not None and not pd.isna(drow["address"]) else NOT_REPORTED)
    city = ", ".join(str(x) for x in ([drow["city"], drow["state"]] if drow is not None else []) if not pd.isna(x))
    zp = drow["zip"] if drow is not None and not pd.isna(drow["zip"]) else ""
    flat = {k: v for k, v in r.items() if k != "scenarios"}
    flat.update({"historical_median_earnings": c["hist_earn"], "historical_median_debt": c["hist_debt"]})
    # Grafana shortens $6,456 to "$6K"; ready-made strings keep the tiles exact
    display = {f"{k}_display": _dollars(flat.get(k), cents=k == "standard_monthly_payment") for k in PLAN_MONEY}
    return [{"card": "Value", 
        **display,
        **flat,
        "school_name": name,
        "school_address": addr if c["iid"] else "Select a school",
        "school_city_state_zip": f"{city} {zp}".strip() or NOT_REPORTED,
        "historical_median_earnings": c["hist_earn"],
        "historical_median_debt": c["hist_debt"],
        "historical_cohort": c["cohort"],
        "matching_programs": int(len(c["progs"])),
        "confidence": c["confidence"],
        "residency": "In-state" if c["in_state"] else "Out-of-state",
        "occupation": c["occupation"] or "Not entered",
        "rate_used_pct": c["inputs"].rate_pct,
        "rate_source": c["provenance"].get("rate", "You entered"),
        "annual_tuition_used": c["inputs"].annual_tuition,
        "tuition_source": c["provenance"].get("tuition", "Missing — enter estimated tuition"),
        "expected_salary_used": c["inputs"].salary_expected,
        "expected_salary_source": c["provenance"].get("salary_mid", "Missing"),
        "start_year_used": c["inputs"].start_year,
        "grad_year_used": c["inputs"].grad_year,
        "input_check": "All inputs OK" if not c["msgs"] else f"{len(c['msgs'])} input(s) need attention — see notes",
    }]


@router.get("/plan/scenarios")
def plan_scenarios(pp: PlanParams = Depends(), flt: Filters = Depends()):
    c = _plan_context(pp, flt)
    taxes = dict(c["tax_rows"])
    rows = []
    for s in c["result"]["scenarios"]:
        est = taxes.get(s["scenario"])
        rows.append({
            **s,
            "salary_source": c["provenance"].get({"Conservative": "salary_low", "Expected": "salary_mid",
                                                  "Aspirational": "salary_high"}[s["scenario"]], "Missing"),
            "est_state_income_tax": est["tax"] if est else None,
            "state_tax_note": (f"{c['work_state']} tax year {est['tax_year']}, single filer, wages only — educational estimate"
                               if est else ("Work state not entered" if not c["work_state"]
                                            else f"{c['work_state']} not in verified tax set")),
        })
    return rows


@router.get("/plan/notes")
def plan_notes(pp: PlanParams = Depends(), flt: Filters = Depends()):
    c = _plan_context(pp, flt)
    rows = [{"type": "⚠️ Input check", "detail": m} for m in c["msgs"]]
    rows += [{"type": "❔ Missing", "detail": m} for m in c["missing"]]
    labels = {k: v[0] for k, v in PLAN_PARAMS.items()}
    rows += [{"type": "✏️ You entered" if src == "You entered" else "⚙️ Assumption / auto-filled",
              "detail": f"{labels[k]}: {src}"} for k, src in sorted(c["provenance"].items())]
    rows += [{"type": "⚙️ Assumption", "detail": a} for a in ASSUMPTIONS]
    rows.append({"type": "📘 Historical data", "detail": f"Program outcomes: {SOURCE_LABEL}, {DATA_YEAR_LABEL}. "
                                                        "Historical earnings do not guarantee future salary."})
    return rows


def _timeline(pp: PlanParams, flt: Filters) -> dict:
    c = _plan_context(pp, flt)
    return timeline_agent.handle(c["inputs"], c["result"])


@router.get("/plan/timeline")
def plan_timeline(pp: PlanParams = Depends(), flt: Filters = Depends()):
    """Month-by-month remaining balance per scenario (Repayment Timeline Agent)."""
    rows = _timeline(pp, flt)["schedule"]
    keys = {"Conservative": "balance_conservative", "Expected": "balance_expected",
            "Aspirational": "balance_aspirational", "Standard 10-year plan": "balance_standard"}
    return [{"month": r["month"], "year": r["year"], **{v: r.get(k) for k, v in keys.items()}} for r in rows]


@router.get("/plan/milestones")
def plan_milestones(pp: PlanParams = Depends(), flt: Filters = Depends()):
    return _timeline(pp, flt)["milestones"]


@router.get("/plan/explain")
def plan_explain(pp: PlanParams = Depends(), flt: Filters = Depends()):
    """Step-by-step explanation of how the repayment timeline was calculated."""
    return _timeline(pp, flt)["explanation"]


PLAN_KEYS = ["start_year", "grad_year", "savings", "contribution", "grants", "existing_debt", "borrowing", "rate",
             "tuition", "living", "salary_low", "salary_mid", "salary_high", "repay_pct", "in_state", "work_state",
             "occupation"]


@router.post("/plan/calculate")
def plan_calculate(body: dict = Body(...)):
    """
    Everything the My Plan results page needs, in one call. Personal values arrive in the request
    body (never in a URL), are used once, and are not stored or cached.
    """
    val = lambda k: None if body.get(k) in (None, "") else str(body[k])[:80]
    pp = PlanParams(**{k: val(k) for k in PLAN_KEYS})
    flt = Filters(school=val("school"), major=val("major"), credential=val("credential"))
    est = plan_estimate(pp, flt)[0]
    est.pop("card", None)
    return {"estimate": est, "scenarios": plan_scenarios(pp, flt), "notes": plan_notes(pp, flt),
            "timeline": plan_timeline(pp, flt), "milestones": plan_milestones(pp, flt),
            "explanation": plan_explain(pp, flt)}


# ── Student product pages: one app shell, routed in the browser ─────────────
APP_INDEX = os.path.join(STATIC_DIR, "app", "index.html")


def app_page():
    return FileResponse(APP_INDEX, media_type="text/html", headers={"Cache-Control": "no-cache"})


def app_graph_page(slug: str):
    return app_page()


for _path in ["/plan", "/plan/review", "/plan/results", "/plan/edit", "/schools", "/graphs", "/states", "/help"]:
    router.add_api_route(_path, app_page, methods=["GET"], include_in_schema=False)
router.add_api_route("/graphs/{slug}", app_graph_page, methods=["GET"], include_in_schema=False)


# ── Help / sources ───────────────────────────────────────────────────────────

@router.get("/meta/sources")
def sources():
    reg = get_source_registry()
    if reg.empty:
        return [{"dataset_name": "College Scorecard", "source_organization": "U.S. Department of Education",
                 "source_url": SCORECARD_URL, "source_year": DATA_YEAR_LABEL}]
    return reg.to_dict(orient="records")
