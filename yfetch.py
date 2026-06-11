#!/usr/bin/env python3
"""
yfetch.py — ticker -> quarterly payload via Yahoo Finance fundamentals.

Yahoo's free window is ~5 quarters of as-reported data: the judge's minimum,
so trajectory verdicts lean on a shorter runway than the 8-quarter ideal.
No login, works for NSE (.NS), BSE (.BO) and global tickers.

EPS surprise isn't available here -> 0 (neutral). The judge never sees street
expectations in this path.
"""

import json
import re
import subprocess
import time
import urllib.parse
import urllib.request

# NB: a full Chrome UA gets 429'd (TLS fingerprint mismatch); generic passes
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
TYPES = ("quarterlyTotalRevenue", "quarterlyEBITDA", "quarterlyTotalDebt",
         "quarterlyCashAndCashEquivalents", "quarterlyOperatingCashFlow",
         "annualOperatingCashFlow", "annualEBITDA")

_cache = {}  # symbol -> (ts, payload)
CACHE_TTL = 3600


def _get(url, retries=2):
    # Yahoo 429s python-urllib's TLS/header fingerprint but accepts curl's;
    # use curl when available, urllib as fallback
    for attempt in range(retries + 1):
        try:
            out = subprocess.run(
                ["curl", "-sS", "--fail-with-body", "--compressed", "-m", "20",
                 "-A", UA, "-H", "Accept: application/json", url],
                capture_output=True, timeout=25)
            if out.returncode == 0:
                return json.loads(out.stdout.decode())
            if b"429" not in out.stderr or attempt == retries:
                raise RuntimeError(out.stderr.decode().strip()[:200] or "curl failed")
        except FileNotFoundError:
            req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                       "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode())
        time.sleep(2 * (attempt + 1))  # Yahoo burst limit; back off


def _series(result, typ):
    """[(asOfDate, raw_value), ...] sorted oldest first."""
    for r in result:
        if r["meta"]["type"][0] == typ:
            vals = r.get(typ) or []
            return sorted((v["asOfDate"], v["reportedValue"]["raw"])
                          for v in vals if v and v.get("reportedValue"))
    return []


def _quarter_label(as_of):
    y, m = int(as_of[:4]), int(as_of[5:7])
    # Indian FY: Apr-Mar. Jun=Q1, Sep=Q2, Dec=Q3, Mar=Q4
    q = {3: "Q4", 6: "Q1", 9: "Q2", 12: "Q3"}.get(m)
    fy = y if m == 3 else y + 1
    return f"{q} FY{fy % 100:02d}" if q else as_of


def _company_name(symbol):
    try:
        j = _get("https://query1.finance.yahoo.com/v1/finance/search?q="
                 + urllib.parse.quote(symbol) + "&quotesCount=1&newsCount=0")
        q = j.get("quotes") or []
        return q[0].get("shortname") or q[0].get("longname") or symbol
    except Exception:
        return symbol


def fetch(symbol):
    """Returns (payload, notes). Raises ValueError with a friendly message."""
    symbol = symbol.strip().upper()
    if not re.fullmatch(r"[A-Z0-9.&^-]{1,20}", symbol):
        raise ValueError("that doesn't look like a ticker")

    cached = _cache.get(symbol)
    if cached and time.time() - cached[0] < CACHE_TTL:
        return cached[1]

    # bare Indian names get .NS first, then .BO
    candidates = [symbol] if "." in symbol or symbol.isalpha() is False else [symbol]
    if "." not in symbol:
        candidates = [symbol + ".NS", symbol + ".BO", symbol]

    p2 = int(time.time())
    p1 = p2 - 3 * 365 * 86400
    last_err = None
    for sym in candidates:
        try:
            url = ("https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/"
                   f"finance/timeseries/{urllib.parse.quote(sym)}?type={','.join(TYPES)}"
                   f"&period1={p1}&period2={p2}")
            result = _get(url)["timeseries"]["result"]
            rev = _series(result, "quarterlyTotalRevenue")
            ebd = _series(result, "quarterlyEBITDA")
            if len(rev) >= 5 and len(ebd) >= 3:
                payload = _build(sym, result, rev, ebd)
                _cache[symbol] = (time.time(), payload)
                return payload
            last_err = f"only {len(rev)} quarters of revenue for {sym}"
        except Exception as e:
            last_err = str(e)
    raise ValueError(
        f"couldn't fetch quarterly fundamentals for '{symbol}' "
        f"({last_err}). Banks/financials often lack EBITDA data — "
        "and so do the very obscure. You can still paste numbers manually.")


def _build(sym, result, rev, ebd):
    notes = []
    ebd_by_date = dict(ebd)
    dates = [d for d, _ in rev if d in ebd_by_date]
    if len(dates) < 5:
        # margins for missing quarters: carry the median
        dates = [d for d, _ in rev]
    rev_by_date = dict(rev)
    dates = sorted(dates)[-8:]

    revenue, margins = [], []
    med_margin = None
    known = [ebd_by_date[d] / rev_by_date[d] for d in dates
             if d in ebd_by_date and rev_by_date[d]]
    med_margin = sorted(known)[len(known) // 2] if known else 0.15
    scale = 1e7 if sym.endswith((".NS", ".BO")) else 1e6  # Rs cr, else millions
    for d in dates:
        revenue.append(round(rev_by_date[d] / scale, 1))
        m = ebd_by_date.get(d)
        margins.append(round(m / rev_by_date[d] if m is not None and rev_by_date[d]
                             else med_margin, 4))

    ttm_ebitda = sum(ebd_by_date[d] for d in dates[-4:] if d in ebd_by_date) or None

    debt = _series(result, "quarterlyTotalDebt")
    cash = _series(result, "quarterlyCashAndCashEquivalents")
    ndte = 0.0
    if debt and ttm_ebitda:
        net_debt = debt[-1][1] - (cash[-1][1] if cash else 0)
        ndte = round(max(-5.0, min(50.0, net_debt / ttm_ebitda)), 2)
    else:
        notes.append("net debt unavailable -> 0")

    ocf_q = _series(result, "quarterlyOperatingCashFlow")
    ocf_ratio = None
    if len(ocf_q) >= 4 and ttm_ebitda:
        ocf_ratio = sum(v for _, v in ocf_q[-4:]) / ttm_ebitda
    else:
        ocf_a, ebd_a = _series(result, "annualOperatingCashFlow"), _series(result, "annualEBITDA")
        if ocf_a and ebd_a and ebd_a[-1][1]:
            ocf_ratio = ocf_a[-1][1] / ebd_a[-1][1]
            notes.append("cash conversion from last ANNUAL filing")
    if ocf_ratio is None:
        ocf_ratio = 1.0
        notes.append("OCF unavailable -> cash conversion assumed perfect; judge will be kind")
    ocf_ratio = round(max(-2.0, min(3.0, ocf_ratio)), 2)

    unit = "Rs cr" if scale == 1e7 else "millions"
    notes.append("EPS surprise not available via Yahoo -> 0 (neutral)")
    notes.append(f"only {len(dates)} quarters available (Yahoo free window); "
                 "8 is the ideal runway")

    return {
        "company": _company_name(sym),
        "quarter": _quarter_label(dates[-1]),
        "revenue": revenue,
        "ebitda_margin": margins,
        "net_debt_to_ebitda": ndte,
        "ocf_to_ebitda": ocf_ratio,
        "eps_surprise_pct": 0.0,
        "one_off_items": False,
        "_source": f"Yahoo Finance, as-reported, {unit}, fetched as {sym}",
        "_notes": notes,
    }


if __name__ == "__main__":
    import sys
    print(json.dumps(fetch(sys.argv[1] if len(sys.argv) > 1 else "GIPCL"), indent=2))
