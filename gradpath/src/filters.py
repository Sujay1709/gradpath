"""
Shared filter handling for every GradPath API endpoint.

Grafana sends dashboard variables as query params. "All" is sent as the custom
all-value "__all" (or left empty); multi-values are joined with "|" using the
${var:pipe} format. A filter that is absent or "All" never narrows the data,
so the Classic dashboards (which send no params) get unchanged results.
"""
from dataclasses import dataclass, fields

import pandas as pd

ALL_TOKENS = {"", "__all", "$__all", "all", "All", "*"}

# filter name -> dataframe column
FILTER_COLUMNS = {
    "school": "institution_id",
    "state": "state",
    "major": "cip_title",
    "cip": "cip_code",
    "credential": "credential_level",
    "school_type": "school_type",
    "data_year": "earnings_cohort",
}


def parse_multi(value: str | None) -> list[str] | None:
    """Return the selected values, or None when the filter means "All"."""
    if value is None:
        return None
    value = value.strip()
    if value in ALL_TOKENS:
        return None
    # Grafana's pipe format wraps multi-values in "{a|b}" for some panel types
    if value.startswith("{") and value.endswith("}"):
        value = value[1:-1]
    parts = [p.strip() for p in value.split("|")]
    parts = [p for p in parts if p and p not in ALL_TOKENS]
    return parts or None


@dataclass
class Filters:
    school: str | None = None
    state: str | None = None
    major: str | None = None
    cip: str | None = None
    credential: str | None = None
    school_type: str | None = None
    data_year: str | None = None

    def without(self, *names: str) -> "Filters":
        """Copy with some filters cleared — used for cascading option lists."""
        return Filters(**{f.name: (None if f.name in names else getattr(self, f.name)) for f in fields(self)})

    def active(self) -> dict[str, list[str]]:
        out = {}
        for f in fields(self):
            vals = parse_multi(getattr(self, f.name))
            if vals:
                out[f.name] = vals
        return out


def apply_filters(df: pd.DataFrame, flt: Filters | None) -> pd.DataFrame:
    if flt is None:
        return df
    mask = pd.Series(True, index=df.index)
    for name, values in flt.active().items():
        col = FILTER_COLUMNS[name]
        if col in df.columns:
            mask &= df[col].astype(str).isin(values)
    return df[mask]


def parse_number(raw: str | None, name: str, lo: float, hi: float, default: float | None,
                 messages: list[str]) -> float | None:
    """
    Parse a user-entered number safely. Accepts "12,000", "$12000", " 6.5 ".
    Out-of-range or unparseable input falls back to the default and records
    a plain-language message instead of raising.
    """
    if raw is None or str(raw).strip() in ALL_TOKENS:
        return default
    text = str(raw).strip().replace(",", "").replace("$", "").replace("%", "")
    try:
        val = float(text)
    except ValueError:
        messages.append(f"{name}: '{str(raw)[:30]}' is not a number — using {_fmt_default(default)}.")
        return default
    if val != val or val in (float("inf"), float("-inf")):
        messages.append(f"{name}: not a finite number — using {_fmt_default(default)}.")
        return default
    if not lo <= val <= hi:
        messages.append(f"{name}: {val:g} is outside {lo:g}–{hi:g} — using {_fmt_default(default)}.")
        return default
    return val


def _fmt_default(default: float | None) -> str:
    return "nothing (left blank)" if default is None else f"{default:g}"
