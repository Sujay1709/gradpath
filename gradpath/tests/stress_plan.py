"""
GradPath stress test — rerun after every data refresh.

Needs the API running (./start.sh, or uvicorn on port 8000). Run from anywhere:

    python3 gradpath/tests/stress_plan.py                 # full run (~1 minute)
    python3 gradpath/tests/stress_plan.py --quick         # 3 schools per category
    python3 gradpath/tests/stress_plan.py --per-category 40 --seed 11
    python3 gradpath/tests/stress_plan.py --skip-perf     # correctness only

Four checks, exit code 1 if any fails:

1. Dashboard queries — every query in every generated dashboard is replayed under
   several filter scenarios; each must return HTTP 200 and the fields its panel reads.
2. Repayment oracle — real schools are sampled from every school type × credential
   category and run through /plan/estimate and /plan/scenarios with five input
   profiles (blank, typical, heavy debt, specific major, random/invalid). Every debt,
   payment, month count, final-payment month, interest total and date range is
   checked against an independent month-by-month loan simulator written here
   (it does not import plan_calc.py). Auto-filled tuition and salary must match
   the source data, and no standard plan may exceed 120 payments. The Repayment Timeline
   Agent's chart and milestones must hit $0 in the same month as the scenario table.
   Smart filters: picking a school must leave only its state and its own majors.
3. Cache and gzip — a cached response must be identical to a fresh one, and large
   responses must be compressed.
4. Performance budgets — single-request latency per endpoint and throughput when
   many simulated users load every page at once.
"""
import argparse
import calendar
import collections
import glob
import gzip
import json
import math
import os
import random
import re
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))          # gradpath/
DASHBOARDS = os.path.join(ROOT, "grafana", "dashboards")
ROI = os.path.join(ROOT, "data", "processed", "degree_roi_clean.parquet")
DIRECTORY = os.path.join(ROOT, "data", "processed", "school_directory.csv")
SHARED = ["school", "state", "major", "cip", "credential", "school_type", "data_year"]

# Performance budgets (milliseconds / requests per second) on a developer laptop
BUDGET_COLD_MS = 500        # any single uncached request
BUDGET_WARM_P95_MS = 50     # repeated requests (cache)
BUDGET_LOAD_P95_MS = 400    # p95 while 10 users load every page at once
BUDGET_MIN_RPS = 200


class Report:
    def __init__(self):
        self.issues = collections.Counter()
        self.examples = {}

    def flag(self, kind, msg):
        self.issues[kind] += 1
        self.examples.setdefault(kind, msg)

    def ok(self):
        return not self.issues

    def print_issues(self, title):
        if self.ok():
            print(f"  ✅ {title}: no issues")
            return
        print(f"  ❌ {title}: {dict(self.issues)}")
        for kind, msg in self.examples.items():
            print(f"     e.g. {kind}: {msg[:220]}")


def get(api, path, params=None, gzip_ok=False):
    if isinstance(params, dict):
        params = [(k, v) for k, v in params.items() if v is not None]
    req = urllib.request.Request(f"{api}{path}?{urllib.parse.urlencode(params or [])}",
                                 headers={"Accept-Encoding": "gzip" if gzip_ok else "identity"})
    t = time.perf_counter()
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
        headers = {k.lower(): v for k, v in r.headers.items()}
    elapsed = time.perf_counter() - t
    body = gzip.decompress(raw) if headers.get("content-encoding") == "gzip" else raw
    return json.loads(body), elapsed, len(raw), headers


# ── 1. Dashboard query replay ────────────────────────────────────────────────

def dashboard_queries(values):
    """(path, params, json keys the panel reads) for every query in every dashboard."""
    def walk(panels):
        for p in panels:
            yield p
            yield from walk(p.get("panels", []))

    def sub(v):
        m = re.fullmatch(r"\$\{(\w+)(?::\w+)?\}", v)
        return values.get(m.group(1), "") if m else v

    seen, out = set(), []
    for f in sorted(glob.glob(os.path.join(DASHBOARDS, "gradpath-*.json"))):
        d = json.load(open(f))
        targets = [t for p in walk(d["panels"]) for t in p.get("targets", [])]
        targets += [v["query"] for v in d["templating"]["list"] if v["type"] == "query"]
        for t in targets:
            params = [(k, sub(v)) for k, v in t.get("params", [])]
            key = (t["urlPath"], tuple(params))
            if key in seen:
                continue
            seen.add(key)
            out.append((t["urlPath"], params, [fl["jsonPath"].split(".")[-1] for fl in t["fields"]]))
    return out


def check_dashboards(api, sample_school):
    rep = Report()
    scenarios = [
        {},
        {"school": sample_school},
        {"state": "TX", "credential": "Bachelor's Degree", "savings": "abc", "rate": "99", "work_state": "TX"},
        {"state": "ZZ"},                                       # matches nothing → empty states
    ]
    n = 0
    for extra in scenarios:
        values = {v: "__all" for v in SHARED} | {"example_income": "50000"} | extra
        for path, params, keys in dashboard_queries(values):
            n += 1
            try:
                data, *_ = get(api, path, params)
            except urllib.error.HTTPError as e:
                rep.flag("http_error", f"{e.code} {path} {params}")
                continue
            missing = [k for k in keys if data and isinstance(data, list) and k not in data[0]]
            if missing:
                rep.flag("missing_fields", f"{path} {missing} with {extra or 'all filters = All'}")
    print(f"  {n} dashboard queries replayed across {len(scenarios)} filter scenarios")
    return rep


# ── 2. Independent repayment oracle ──────────────────────────────────────────

def add_months(y, m, n):
    i = y * 12 + m - 1 + n
    return i // 12, i % 12 + 1


def label(y, m):
    return f"{calendar.month_abbr[m]} {y}"


def round_up_cents(x):
    return math.ceil(round(x * 100, 6)) / 100


def simulate(balance, rate_pct, payment):
    """Monthly interest, then the payment, until the balance is cleared: (payments, interest)."""
    r = rate_pct / 1200
    n, interest = 0, 0.0
    while balance > 0.005 and n < 1200:
        i = balance * r
        interest += i
        balance += i - min(payment, balance + i)
        n += 1
    return n, interest


def expected_debt(start, grad, per_year, existing, rate_pct, now_y, now_m):
    """Simple interest from each September disbursement (and from today for existing loans) to repayment."""
    rs_y, rs_m = add_months(grad, 5, 6)                     # November after a May graduation
    rs = rs_y * 12 + rs_m - 1
    years = max(1, grad - start)
    acc = sum(per_year * rate_pct / 100 * max(0, rs - ((start + i) * 12 + 8)) / 12 for i in range(years))
    acc += existing * rate_pct / 100 * max(0, rs - (now_y * 12 + now_m - 1)) / 12
    return existing + per_year * years + acc, (rs_y, rs_m)


def repay_pct_used(raw):
    """Mirror of the documented input rule: 1–50 %, otherwise the 10 % default."""
    try:
        v = float(str(raw).replace("$", "").replace(",", "").replace("%", "").strip())
        return v if 1 <= v <= 50 else 10.0
    except ValueError:
        return 10.0


PROFILES = {
    "blank": {},
    "typical": dict(savings="3000", contribution="1200", grants="4000", borrowing="5500", living="12000",
                    start_year="2027", grad_year="2031"),
    "heavy": dict(savings="0", borrowing="20000", existing_debt="10000", rate="8.0", living="18000",
                  salary_low="30000", salary_high="50000", start_year="2027", grad_year="2031", repay_pct="5"),
    "major": dict(borrowing="7000", salary_low="35000", salary_high="90000", work_state="NY",
                  start_year="2026", grad_year="2028"),
    "fuzz": None,
}


def fuzz_profile(rnd):
    p = {k: rnd.choice(["", "abc", "-5", "1e9", "$12,500", "7.5%", str(rnd.randint(0, 60000))])
         for k in ["savings", "borrowing", "rate", "tuition", "living", "salary_low", "salary_mid",
                   "salary_high", "repay_pct", "existing_debt"]}
    p.update(start_year=rnd.choice(["2027", "2031", "x"]), grad_year=rnd.choice(["2026", "2032", ""]))
    return p


def check_plan(api, per_category, seed):
    rep = Report()
    rnd = random.Random(seed)
    roi = pd.read_parquet(ROI).dropna(subset=["institution_id"])
    directory = pd.read_csv(DIRECTORY, dtype={"institution_id": str}).set_index("institution_id")
    today = pd.Timestamp.today()
    runs, categories = 0, collections.Counter()
    payoff_years = collections.defaultdict(list)

    for (stype, cred), g in roi.groupby(["school_type", "credential_level"]):
        ids = sorted(g["institution_id"].unique())
        rnd.shuffle(ids)
        for iid in ids[:per_category]:
            categories[(stype, cred)] += 1
            for pname, prof in PROFILES.items():
                q = dict(fuzz_profile(rnd) if prof is None else prof, school=iid, credential=cred,
                         in_state=rnd.choice(["yes", "no"]))
                if pname == "major":
                    q["major"] = g[g.institution_id == iid]["cip_title"].iloc[0]
                try:
                    (est,), *_ = get(api, "/plan/estimate", q)
                    scen, *_ = get(api, "/plan/scenarios", q)
                except Exception as e:
                    rep.flag("http_error", f"{pname} {iid}: {e}")
                    continue
                runs += 1
                where = f"{iid} ({stype}, {cred}) {pname}"

                per_year = est["new_borrowing_total"] / est["years_in_school"]
                want_debt, (rs_y, rs_m) = expected_debt(est["start_year_used"], est["grad_year_used"], per_year,
                                                        est["existing_balance"], est["rate_used_pct"],
                                                        today.year, today.month)
                if abs(want_debt - est["debt_at_repayment_start"]) > 1:
                    rep.flag("debt", f"{where}: api {est['debt_at_repayment_start']} vs oracle {want_debt:.2f}")
                if est["repayment_start"] != label(rs_y, rs_m):
                    rep.flag("first_payment", f"{where}: {est['repayment_start']} vs {label(rs_y, rs_m)}")

                P, rate = est["debt_at_repayment_start"], est["rate_used_pct"]
                std = est["standard_monthly_payment"]
                if P > 0:
                    n_std, _ = simulate(P, rate, std)
                    if n_std > 120:
                        rep.flag("standard_over_120", f"{where}: {n_std} payments")

                dated = []
                for s in scen:
                    if s["starting_salary"] is None:
                        if s["debt_free_date"] != "Missing salary":
                            rep.flag("missing_salary_label", f"{where}: {s['debt_free_date']}")
                        continue
                    if P <= 0:
                        if s["debt_free_date"] != "No loan balance":
                            rep.flag("zero_debt_label", f"{where}: {s['debt_free_date']}")
                        continue
                    pct = repay_pct_used(q.get("repay_pct", ""))
                    want_pay = max(std, round_up_cents(s["starting_salary"] / 12 * pct / 100))
                    if abs(s["monthly_payment"] - want_pay) > 0.011:
                        rep.flag("payment", f"{where} {s['scenario']}: api {s['monthly_payment']} vs {want_pay}")
                    n, interest = simulate(P, rate, s["monthly_payment"])
                    if s["months_to_debt_free"] != n:
                        rep.flag("months", f"{where} {s['scenario']}: api {s['months_to_debt_free']} vs oracle {n}")
                    want_date = label(*add_months(rs_y, rs_m, n - 1))
                    if s["debt_free_date"] != want_date:
                        rep.flag("final_payment_month",
                                 f"{where} {s['scenario']}: api {s['debt_free_date']} vs {want_date}")
                    if s["total_interest"] is not None and abs(s["total_interest"] - interest) > 2:
                        rep.flag("interest", f"{where}: api {s['total_interest']} vs {interest:.2f}")
                    dated.append((n, s["debt_free_date"]))
                    if pname == "typical":
                        payoff_years[(stype, cred)].append(n / 12)

                if P > 0:
                    if dated:
                        lo, hi = min(dated), max(dated)
                        want_range = lo[1] if lo[0] == hi[0] else f"{lo[1]} – {hi[1]}"
                    else:
                        want_range = f"{est['standard_debt_free_date']} (standard 10-year plan)"
                    if est["debt_free_range"] != want_range:
                        rep.flag("range", f"{where}: {est['debt_free_range']} vs {want_range}")
                elif est["debt_free_range"] != "No loan balance":
                    rep.flag("zero_range", f"{where}: {est['debt_free_range']}")

                if pname in ("typical", "heavy") and P > 0:
                    check_agent(api, q, scen, rep, where)

                if pname == "blank":
                    d = directory.loc[iid] if iid in directory.index else None
                    col = "tuition_fees_in_state" if q["in_state"] == "yes" else "tuition_fees_out_of_state"
                    if d is not None and pd.notna(d[col]):
                        if abs(est["annual_tuition_used"] - d[col]) > 0.5:
                            rep.flag("tuition_autofill", f"{where}: {est['annual_tuition_used']} vs {d[col]}")
                    elif est["tuition_source"].startswith("Scorecard"):
                        rep.flag("tuition_invented", where)
                    hist = g[g.institution_id == iid]["median_earnings"].median()
                    if abs(est["expected_salary_used"] - hist) > 0.5:
                        rep.flag("salary_autofill", f"{where}: {est['expected_salary_used']} vs {hist}")

    print(f"  {runs} plans: {sum(categories.values())} schools × {len(PROFILES)} profiles, "
          f"{len(categories)} categories")
    print("  typical profile ($5,500/yr borrowed) — years of payments, median by category:")
    for (stype, cred), yrs in sorted(payoff_years.items()):
        print(f"     {stype:20s} {cred:38s} {statistics.median(yrs):4.1f} yr")
    return rep


def check_agent(api, q, scen, rep, where):
    """Repayment Timeline Agent output must agree with the scenario table."""
    timeline, *_ = get(api, "/plan/timeline", q)
    milestones, *_ = get(api, "/plan/milestones", q)
    explain, *_ = get(api, "/plan/explain", q)
    cols = {"Conservative": "balance_conservative", "Expected": "balance_expected",
            "Aspirational": "balance_aspirational"}
    for s in scen:
        if not s.get("months_to_debt_free"):
            continue
        col = cols[s["scenario"]]
        zero = next((r["month"] for r in timeline if r[col] == 0), None)
        if zero != s["debt_free_date"]:
            rep.flag("agent_timeline", f"{where} {s['scenario']}: chart hits $0 in {zero}, table says {s['debt_free_date']}")
        final = [m for m in milestones if m["scenario"] == s["scenario"] and m["milestone"].startswith("Debt-free")]
        if not final or final[0]["date"] != s["debt_free_date"]:
            rep.flag("agent_milestone", f"{where} {s['scenario']}: {final[0]['date'] if final else None}")
    if len(explain) < 5:
        rep.flag("agent_explain", f"{where}: only {len(explain)} steps")


def check_smart_filters(api, seed, n=40):
    """Picking a school must leave exactly its own state, and only its own majors."""
    rep = Report()
    roi = pd.read_parquet(ROI).dropna(subset=["institution_id"])
    rnd = random.Random(seed)
    ids = sorted(roi["institution_id"].unique())
    for iid in rnd.sample(ids, min(n, len(ids))):
        rows = roi[roi.institution_id == iid]
        states, *_ = get(api, "/options/states", {"school": iid})
        want = sorted(rows["state"].dropna().unique()) or ["__all"]
        if [o["value"] for o in states] != want:
            rep.flag("state_not_auto", f"{iid}: {[o['value'] for o in states]} vs {want}")
        majors, *_ = get(api, "/options/majors", {"school": iid})
        if {o["value"] for o in majors} != set(rows["cip_title"]):
            rep.flag("majors_not_narrowed", f"{iid}: {len(majors)} vs {rows['cip_title'].nunique()}")
    states, *_ = get(api, "/options/states")
    if states[0] != {"text": "All", "value": "__all"}:
        rep.flag("state_all_missing", str(states[:1]))
    print(f"  {n} random schools: State auto-fills and Major narrows to the school's programs")
    return rep


# ── 3 + 4. Cache, gzip and performance ───────────────────────────────────────

def check_cache_and_perf(api):
    rep = Report()
    for path in ["/metrics/scatter", "/options/schools", "/schools/table"]:
        fresh, *_ = get(api, path, {"cache_probe": str(time.time())})      # unique URL → never cached
        warm, _, wire, headers = get(api, path, gzip_ok=True)
        again, _, _, headers2 = get(api, path, gzip_ok=True)
        if fresh != warm or warm != again:
            rep.flag("cache_mismatch", f"{path}: cached body differs from fresh body")
        if headers2.get("x-cache") != "HIT":
            rep.flag("cache_not_used", path)
        if len(json.dumps(fresh)) > 50_000 and headers.get("content-encoding") != "gzip":
            rep.flag("not_compressed", f"{path} sent {wire:,} bytes uncompressed")

    queries = dashboard_queries({v: "__all" for v in SHARED} | {"example_income": "50000"})
    stamp = str(time.time())
    cold, warm = [], []
    for path, params, _ in queries:
        _, t, _, _ = get(api, path, params + [("cold", stamp)], gzip_ok=True)
        cold.append((t * 1000, path))
        warm.append(statistics.median(get(api, path, params, gzip_ok=True)[1] for _ in range(3)) * 1000)
    slowest = max(cold)
    if slowest[0] > BUDGET_COLD_MS:
        rep.flag("slow_cold", f"{slowest[1]} took {slowest[0]:.0f} ms (budget {BUDGET_COLD_MS})")
    warm_p95 = sorted(warm)[int(len(warm) * 0.95)]
    if warm_p95 > BUDGET_WARM_P95_MS:
        rep.flag("slow_warm", f"p95 {warm_p95:.0f} ms (budget {BUDGET_WARM_P95_MS})")

    urls = [(p, prm) for p, prm, _ in queries] * 10                         # 10 users, every page
    t0 = time.perf_counter()
    with ThreadPoolExecutor(32) as pool:
        lat = sorted(pool.map(lambda a: get(api, a[0], a[1], gzip_ok=True)[1] * 1000, urls))
    elapsed = time.perf_counter() - t0
    rps, p95 = len(urls) / elapsed, lat[int(len(lat) * 0.95)]
    if p95 > BUDGET_LOAD_P95_MS:
        rep.flag("slow_under_load", f"p95 {p95:.0f} ms (budget {BUDGET_LOAD_P95_MS})")
    if rps < BUDGET_MIN_RPS:
        rep.flag("low_throughput", f"{rps:.0f} req/s (budget {BUDGET_MIN_RPS})")

    print(f"  cold: slowest {slowest[1]} {slowest[0]:.0f} ms · warm p95 {warm_p95:.1f} ms · "
          f"load: {len(urls)} requests, {rps:.0f} req/s, p95 {p95:.0f} ms")
    try:
        print(f"  server cache: {get(api, '/meta/health')[0]['cache']}")
    except Exception:
        pass
    return rep


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--per-category", type=int, default=15, help="schools sampled per school type × credential")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--quick", action="store_true", help="3 schools per category")
    ap.add_argument("--skip-perf", action="store_true")
    args = ap.parse_args()

    try:
        get(args.api, "/")
    except Exception as e:
        sys.exit(f"GradPath API not reachable at {args.api} ({e}). Start it with ./start.sh first.")

    roi = pd.read_parquet(ROI).dropna(subset=["institution_id"])
    sample_school = roi.sort_values("cohort_size", ascending=False)["institution_id"].iloc[0]
    reports = []
    print("1. Dashboard queries")
    reports.append(("dashboard queries", check_dashboards(args.api, sample_school)))
    reports[-1][1].print_issues("dashboard queries")
    print("1b. Smart filters")
    reports.append(("smart filters", check_smart_filters(args.api, args.seed)))
    reports[-1][1].print_issues("smart filters")
    print("2. Repayment oracle + Repayment Timeline Agent")
    reports.append(("repayment oracle", check_plan(args.api, 3 if args.quick else args.per_category, args.seed)))
    reports[-1][1].print_issues("repayment oracle")
    if not args.skip_perf:
        print("3–4. Cache, gzip and performance")
        reports.append(("performance", check_cache_and_perf(args.api)))
        reports[-1][1].print_issues("cache, gzip and performance")

    failed = [name for name, rep in reports if not rep.ok()]
    print("\nRESULT:", "PASS" if not failed else f"FAIL ({', '.join(failed)})")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
