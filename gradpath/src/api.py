"""
GradPath FastAPI backend — marcusolsson-json-datasource v1.4.4 compatible.

The marcusolsson-json-datasource plugin (v1.4.x) calls each panel's configured
urlPath directly. Each endpoint returns a JSON array of objects. The plugin
then maps the JSON keys to Grafana fields using the field definitions in the
panel query editor.

Endpoints:
  GET  /                                → health (datasource test)
  GET  /metrics/summary_stats           → [{total_programs, total_institutions, ...}]
  GET  /metrics/earnings_by_school_type → [{school_type, median_earnings_usd}]
  GET  /metrics/earnings_by_credential  → [{credential_level, median_earnings_usd}]
  GET  /metrics/debt_by_credential      → [{credential_level, median_debt_usd}]
  GET  /metrics/dte_by_school_type      → [{school_type, median_debt_to_earnings}]
  GET  /metrics/top_programs_earnings   → [{cip_title, credential_level, ...}]
  GET  /metrics/top_programs_dte        → [{cip_title, credential_level, ...}]
  GET  /metrics/state_earnings          → [{state, median_earnings_usd}]
  GET  /metrics/school_type_dist        → [{school_type, count}]
  GET  /metrics/credential_dist         → [{credential_level, count}]
  GET  /metrics/programs_table          → [{institution_name, state, ...}]

Run:
    uvicorn src.api:app --host 0.0.0.0 --port 8000 --workers 4
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd
from fastapi import Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse


app = FastAPI(title="GradPath API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Data access + shared filters (see data_store.py / filters.py) ─────────────

from data_store import get_df, to_records  # noqa: E402
from filters import Filters, apply_filters  # noqa: E402
from app_routes import router as app_router  # noqa: E402

app.include_router(app_router)

# Performance: repeated identical GETs come from memory; large JSON is gzipped.
# Starlette makes the last-added middleware the outermost, so the cache stores
# uncompressed bodies and gzip negotiates per client.
from fastapi.middleware.gzip import GZipMiddleware  # noqa: E402
from response_cache import ResponseCache  # noqa: E402

app.add_middleware(ResponseCache)
app.add_middleware(GZipMiddleware, minimum_size=2048, compresslevel=5)


def _find_cache():
    """Walk the built middleware stack to report cache statistics."""
    layer = app.middleware_stack
    while layer is not None:
        if isinstance(layer, ResponseCache):
            return layer
        layer = getattr(layer, "app", None)
    return None


@app.get("/meta/health")
def meta_health():
    """Record count and cache statistics (tests/stress_plan.py reads this)."""
    from app_routes import timeline_agent
    cache = _find_cache()
    return {"records": len(get_df()), "cache": cache.stats() if cache else None,
            "agents": {timeline_agent.name: timeline_agent.stats}}


# ── Health / datasource test ──────────────────────────────────────────────────

@app.get("/")
def health():
    """Grafana calls GET / to test the datasource connection."""
    return {"status": "ok", "service": "GradPath API", "records": len(get_df())}


# ── Metric endpoints (one per panel) ─────────────────────────────────────────

@app.get("/metrics/summary_stats")
def summary_stats(flt: Filters = Depends()):
    df = apply_filters(get_df(), flt)
    empty = df.empty
    return [{
        "total_programs": int(len(df)),
        "total_institutions": int(df["institution_name"].nunique()),
        "total_states": int(df["state"].nunique()),
        "median_earnings_overall": None if empty else int(df["median_earnings"].median()),
        "median_debt_overall": None if empty else int(df["median_debt"].median()),
        "median_debt_to_earnings": None if empty else round(float(df["debt_to_earnings"].median()), 3),
        # GradPath app fields: schools counted by institution ID (names can repeat across states)
        "matching_schools": int(df["institution_id"].nunique()),
        "matching_programs": int(len(df)),
    }]


@app.get("/metrics/earnings_by_school_type")
def earnings_by_school_type(flt: Filters = Depends()):
    df = apply_filters(get_df(), flt)
    result = (
        df.groupby("school_type")["median_earnings"]
        .median()
        .reset_index()
        .rename(columns={"median_earnings": "median_earnings_usd"})
        .sort_values("median_earnings_usd", ascending=False)
    )
    return to_records(result)


@app.get("/metrics/earnings_by_credential")
def earnings_by_credential(flt: Filters = Depends()):
    df = apply_filters(get_df(), flt)
    result = (
        df.groupby("credential_level")["median_earnings"]
        .median()
        .reset_index()
        .rename(columns={"median_earnings": "median_earnings_usd"})
        .sort_values("median_earnings_usd", ascending=False)
    )
    return to_records(result)


@app.get("/metrics/debt_by_credential")
def debt_by_credential(flt: Filters = Depends()):
    df = apply_filters(get_df(), flt)
    result = (
        df.groupby("credential_level")["median_debt"]
        .median()
        .reset_index()
        .rename(columns={"median_debt": "median_debt_usd"})
        .sort_values("median_debt_usd", ascending=False)
    )
    return to_records(result)


@app.get("/metrics/dte_by_school_type")
def dte_by_school_type(flt: Filters = Depends()):
    df = apply_filters(get_df(), flt)
    result = (
        df.groupby("school_type")["debt_to_earnings"]
        .median()
        .reset_index()
        .rename(columns={"debt_to_earnings": "median_debt_to_earnings"})
        .sort_values("median_debt_to_earnings")
    )
    return to_records(result)


@app.get("/metrics/top_programs_earnings")
def top_programs_earnings(n: int = Query(default=20, ge=1, le=100), flt: Filters = Depends()):
    df = apply_filters(get_df(), flt)
    result = (
        df.groupby(["cip_title", "credential_level", "school_type"])[
            ["median_earnings", "median_debt"]
        ]
        .median()
        .reset_index()
    )
    result["debt_to_earnings"] = (result["median_debt"] / result["median_earnings"]).round(3)
    result["median_earnings"] = result["median_earnings"].round(0)
    result["median_debt"] = result["median_debt"].round(0)
    result = result.sort_values("median_earnings", ascending=False).head(n)
    return to_records(result)


@app.get("/metrics/top_programs_dte")
def top_programs_dte(n: int = Query(default=20, ge=1, le=100), flt: Filters = Depends()):
    df = apply_filters(get_df(), flt)
    result = (
        df.groupby(["cip_title", "credential_level", "school_type"])[
            ["median_earnings", "median_debt"]
        ]
        .median()
        .reset_index()
    )
    result["debt_to_earnings"] = (result["median_debt"] / result["median_earnings"]).round(3)
    result["median_earnings"] = result["median_earnings"].round(0)
    result["median_debt"] = result["median_debt"].round(0)
    result = result[result["median_debt"] > 0].sort_values("debt_to_earnings").head(n)
    return to_records(result)


@app.get("/metrics/state_earnings")
def state_earnings(flt: Filters = Depends()):
    df = apply_filters(get_df(), flt)
    result = (
        df.groupby("state")["median_earnings"]
        .median()
        .reset_index()
        .rename(columns={"median_earnings": "median_earnings_usd"})
        .sort_values("median_earnings_usd", ascending=False)
    )
    return to_records(result)


@app.get("/metrics/school_type_dist")
def school_type_dist(flt: Filters = Depends()):
    df = apply_filters(get_df(), flt)
    result = (
        df.groupby("school_type")
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
    )
    return to_records(result)


@app.get("/metrics/credential_dist")
def credential_dist(flt: Filters = Depends()):
    df = apply_filters(get_df(), flt)
    result = (
        df.groupby("credential_level")
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
    )
    return to_records(result)


@app.get("/metrics/programs_table")
def programs_table(limit: int = Query(default=500, ge=1, le=5000), flt: Filters = Depends()):
    df = apply_filters(get_df(), flt)
    cols = [
        "institution_name", "state", "school_type", "cip_title",
        "credential_level", "median_earnings", "median_debt",
        "debt_to_earnings", "earnings_to_debt", "earnings_debt_difference",
        "cohort_size", "earnings_cohort",
    ]
    result = df[cols].sort_values("debt_to_earnings").head(limit).copy()
    result["median_earnings"] = result["median_earnings"].round(0)
    result["median_debt"] = result["median_debt"].round(0)
    result["earnings_debt_difference"] = result["earnings_debt_difference"].round(0)
    return to_records(result)


# ── Tax bracket AI endpoints ──────────────────────────────────────────────────

_tax_clf = None

def get_tax_clf():
    global _tax_clf
    if _tax_clf is None:
        from tax_classifier import TaxClassifier
        _tax_clf = TaxClassifier.load()
    return _tax_clf


@app.get("/tax/predict")
def tax_predict(
    income: float = Query(..., description="Gross annual income"),
    state: str = Query(default="CA", description="2-letter state abbreviation"),
    filing_status: str = Query(default="single", description="single | married | hoh"),
    age: int = Query(default=30),
    years_exp: int = Query(default=5),
    student_debt: float = Query(default=0),
    credential: str = Query(default="Bachelor's Degree"),
    school_type: str = Query(default="Public"),
    dependents: int = Query(default=0),
    homeowner: bool = Query(default=False),
    retirement_rate: float = Query(default=0.05),
):
    """Predict federal tax bracket and compute full tax breakdown for a profile."""
    profile = {
        "income": income, "state": state, "filing_status": filing_status,
        "age": age, "years_exp": years_exp, "student_debt": student_debt,
        "monthly_payment": student_debt / 120 if student_debt > 0 else 0,
        "school_type": school_type, "credential": credential,
        "dependents": dependents, "homeowner": homeowner,
        "retirement_rate": retirement_rate,
    }
    result = get_tax_clf().predict(profile)
    # Flatten for Grafana: return as single-row array
    tax = result["tax_breakdown"]
    return [{
        "income": income,
        "state": state.upper(),
        "filing_status": filing_status,
        "predicted_bracket": result["predicted_bracket"],
        "confidence_pct": round(result["confidence"] * 100, 1),
        "federal_income_tax": tax["federal_income_tax"],
        "state_income_tax": tax["state_income_tax"],
        "fica_social_security": tax["fica_social_security"],
        "fica_medicare": tax["fica_medicare"],
        "total_tax": tax["total_tax"],
        "net_income": tax["net_income"],
        "effective_rate_pct": tax["effective_rate_pct"],
        "marginal_federal_rate_pct": tax["marginal_federal_rate_pct"],
        "marginal_state_rate_pct": tax["marginal_state_rate_pct"],
    }]


@app.get("/tax/state_rates")
def tax_state_rates():
    """All 51 states with their top marginal rate and tax category."""
    from tax_data import STATE_TAX_BRACKETS, NO_INCOME_TAX_STATES, FLAT_TAX_STATES
    rows = []
    for state, brackets in sorted(STATE_TAX_BRACKETS.items()):
        top_rate = max(r for _, r in brackets)
        if state in NO_INCOME_TAX_STATES:
            category = "No Income Tax"
        elif state in FLAT_TAX_STATES:
            category = "Flat Tax"
        else:
            category = "Progressive"
        rows.append({
            "state": state,
            "top_marginal_rate_pct": top_rate,
            "tax_category": category,
        })
    return rows


@app.get("/tax/bracket_distribution")
def tax_bracket_distribution():
    """Distribution of the 10,000 synthetic training profiles across federal brackets."""
    from tax_classifier import TaxClassifier, generate_synthetic_profiles, BRACKET_LABELS
    import json as _json
    stats_path = os.path.join(
        os.path.dirname(__file__), "..", "data", "processed", "tax_classifier_stats.json"
    )
    if os.path.exists(stats_path):
        with open(stats_path) as f:
            stats = _json.load(f)
        per = stats.get("per_bracket", {})
        return [
            {
                "bracket": label,
                "support": int(per.get(label, {}).get("support", 0)),
                "precision": round(per.get(label, {}).get("precision", 0), 3),
                "recall": round(per.get(label, {}).get("recall", 0), 3),
                "f1": round(per.get(label, {}).get("f1-score", 0), 3),
            }
            for label in BRACKET_LABELS
        ]
    return []


@app.get("/tax/model_stats")
def tax_model_stats():
    """Training statistics for the tax bracket AI model."""
    import json as _json
    stats_path = os.path.join(
        os.path.dirname(__file__), "..", "data", "processed", "tax_classifier_stats.json"
    )
    if os.path.exists(stats_path):
        with open(stats_path) as f:
            stats = _json.load(f)
        return [{
            "n_train": stats.get("n_train", 0),
            "n_test": stats.get("n_test", 0),
            "accuracy_pct": round(stats.get("accuracy", 0) * 100, 1),
            "n_parameters": stats.get("n_parameters", 0),
            "n_features": stats.get("n_features", 0),
            "n_iterations": stats.get("n_iter", 0),
        }]
    return []


@app.get("/tax/earnings_after_tax_by_state")
def earnings_after_tax_by_state():
    """
    For each state, compute net income after all taxes for a median earner
    ($34,348 gross — the dataset median) as a single filer.
    Useful for visualizing state tax burden impact on degree ROI.
    """
    from tax_data import effective_tax_rate, STATE_TAX_BRACKETS
    median_income = 34_348.0
    rows = []
    for state in sorted(STATE_TAX_BRACKETS.keys()):
        tax = effective_tax_rate(median_income, state, "single")
        rows.append({
            "state": state,
            "gross_income": median_income,
            "net_income": tax["net_income"],
            "total_tax": tax["total_tax"],
            "effective_rate_pct": tax["effective_rate_pct"],
            "federal_bracket": tax["federal_bracket"],
            "state_rate_pct": tax["marginal_state_rate_pct"],
        })
    return sorted(rows, key=lambda r: r["net_income"], reverse=True)
