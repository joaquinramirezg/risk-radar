#!/usr/bin/env python3
"""Pull the forecast's signals from EDGAR: 10-Qs, 8-K item lists, and one older 10-K.

  SEC_USER_AGENT="name email" python3 tools/fetch_10q.py

For each of the 102 companies, using the two 10-Ks the site already shows
(site/data/index.json):

  next window  every 10-Q and 8-K filed after the latest 10-K (the forecast's inputs)
  back window  every 10-Q and 8-K filed between the previous 10-K and the latest
               one (the backtest's inputs; the latest 10-K is the known outcome)

and the 10-K before the previous one (data/raw_prev2/), so the backtest can
ask "did this company add the theme the year before?" just as the forecast
does. A 10-K filed after the latest one is recorded too: that company's next
filing is already out, so it cannot be forecast.

Writes data/raw_10q/<window>/<TICKER>/<accession>.htm, data/raw_10q/MANIFEST.tsv,
data/raw_prev2/ (raw, gitignored) and data/events.json (committed: form, date
and 8-K items only). Same fair-access rules as tools/fetch_filings.py.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date

from fetch_filings import companion, get
from forecast_common import EVENTS, RAW_10Q, RAW_PREV2, SUBMISSIONS, index, sector

FIELDS = ("form", "accessionNumber", "filingDate", "primaryDocument", "reportDate", "items")


def submissions(cik: int, ua: str, since: str) -> tuple[dict, list[dict[str, str]]]:
    """Every filing back to `since` (paged files pulled until they reach it)."""
    d = json.loads(get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", ua))
    r = {
        k: list(d["filings"]["recent"].get(k, [""] * len(d["filings"]["recent"]["form"])))
        for k in FIELDS
    }
    for page in d["filings"].get("files", []):
        if min(r["filingDate"]) <= since and [f for f in r["form"] if f == "10-K"][2:]:
            break
        extra = json.loads(get(f"https://data.sec.gov/submissions/{page['name']}", ua))
        for k in FIELDS:
            r[k] += extra.get(k, [""] * len(extra["form"]))
    rows = [{k: r[k][i] for k in FIELDS} for i in range(len(r["form"]))]
    meta = {
        "name": d["name"],
        "sic": d.get("sic", ""),
        "sicDescription": d.get("sicDescription", ""),
    }
    return meta, rows


def acc_of(url: str) -> str:
    """0000320193-26-000026 from .../000032019326000026/aapl-20260926.htm"""
    a = url.rstrip("/").split("/")[-2]
    return f"{a[:10]}-{a[10:12]}-{a[12:]}"


def main() -> int:
    ua = os.environ.get("SEC_USER_AGENT", "")
    if "@" not in ua:
        print("Set SEC_USER_AGENT to 'name email', as EDGAR's fair-access policy asks.")
        return 2
    from fetch_filings import COMPANIES

    SUBMISSIONS.mkdir(parents=True, exist_ok=True)
    RAW_PREV2.mkdir(parents=True, exist_ok=True)
    events: dict[str, dict] = {}
    manifest = ["ticker\twindow\taccession\tfiling_date\tperiod_end\tfile\turl"]
    for c in index()["companies"]:
        t, cik = c["ticker"], COMPANIES[c["ticker"]]
        cur_filed, prev_filed = c["current"]["filed"], c["previous"]["filed"]
        meta, rows = submissions(cik, ua, prev_filed)
        (SUBMISSIONS / f"{t}.json").write_text(json.dumps({**meta, "filings": rows}))
        tenk = sorted((r for r in rows if r["form"] == "10-K"), key=lambda r: r["filingDate"])
        later = [r for r in tenk if r["filingDate"] > cur_filed]
        older = [r for r in tenk if r["filingDate"] < prev_filed]
        ev: dict = {
            "company": c["company"],
            "sic": meta["sic"],
            "sector": sector(meta["sic"]),
            "latest_10k": {"filed": cur_filed, "accession": acc_of(c["current"]["url"])},
            "next_10k": (
                {"filed": later[0]["filingDate"], "accession": later[0]["accessionNumber"]}
                if later
                else None
            ),
            "back": [],
            "next": [],
        }
        for r in sorted(rows, key=lambda r: r["filingDate"]):
            d = r["filingDate"]
            window = "next" if d > cur_filed else "back" if prev_filed < d < cur_filed else None
            if window is None or r["form"] not in ("10-Q", "8-K"):
                continue
            ev[window].append(
                {
                    "form": r["form"],
                    "date": d,
                    "accession": r["accessionNumber"],
                    "items": [i for i in r["items"].split(",") if i] if r["form"] == "8-K" else [],
                }
            )
            if r["form"] == "10-Q":
                acc = r["accessionNumber"]
                url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{r['primaryDocument']}"
                dest = RAW_10Q / window / t / f"{acc}.htm"
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not dest.exists():
                    dest.write_bytes(get(url, ua))
                manifest.append(
                    f"{t}\t{window}\t{acc}\t{d}\t{r['reportDate']}\t{dest.relative_to(RAW_10Q)}\t{url}"
                )
        if older:
            p2 = older[-1]
            dest = RAW_PREV2 / f"{t}_10-K_{p2['reportDate']}.htm"
            if not dest.exists():
                url = (
                    f"https://www.sec.gov/Archives/edgar/data/{cik}/"
                    f"{p2['accessionNumber'].replace('-', '')}/{p2['primaryDocument']}"
                )
                dest.write_bytes(get(url, ua))
            companion(cik, p2["accessionNumber"], p2["primaryDocument"], dest, ua)
            ev["prev2_10k"] = {
                "filed": p2["filingDate"],
                "accession": p2["accessionNumber"],
                "file": dest.name,
            }
        events[t] = ev
        nq = {w: sum(1 for x in ev[w] if x["form"] == "10-Q") for w in ("back", "next")}
        n8 = {w: sum(1 for x in ev[w] if x["form"] == "8-K") for w in ("back", "next")}
        flag = "  NEXT 10-K ALREADY FILED" if later else ""
        print(
            f"ok   {t:6} 10-Q back {nq['back']} next {nq['next']}  8-K back {n8['back']} next {n8['next']}{flag}"
        )
    (RAW_10Q / "MANIFEST.tsv").write_text("\n".join(manifest) + "\n")
    EVENTS.write_text(json.dumps({"made": date.today().isoformat(), "companies": events}, indent=1))
    none = [t for t, e in events.items() if not any(x["form"] == "10-Q" for x in e["next"])]
    print(f"\n{len(events)} companies; no 10-Q since the latest 10-K: {len(none)} {' '.join(none)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
