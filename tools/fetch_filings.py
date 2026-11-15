#!/usr/bin/env python3
"""Download the latest two 10-Ks for each company in COMPANIES from SEC EDGAR.

  SEC_USER_AGENT="your-name your-email" python3 tools/fetch_filings.py

Writes data/raw/ (latest) and data/raw_prev/ (the one before), each with a
MANIFEST.tsv of accession numbers and URLs. EDGAR asks every automated client
to identify itself in the User-Agent and to stay under 10 requests a second.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

COMPANIES = {
    "AAPL": 320193, "MSFT": 789019, "NVDA": 1045810, "AMZN": 1018724, "GOOGL": 1652044,
    "META": 1326801, "JPM": 19617, "GS": 886982, "V": 1403161, "JNJ": 200406,
    "PFE": 78003, "UNH": 731766, "XOM": 34088, "CAT": 18230, "BA": 12927,
    "WMT": 104169, "KO": 21344, "NKE": 320187, "DIS": 1744489, "TSLA": 1318605,
}
FIELDS = ("form", "accessionNumber", "filingDate", "primaryDocument", "reportDate")
COLUMNS = "ticker company cik accession filing_date period_end file url".split()


def get(url: str, ua: str) -> bytes:
    time.sleep(0.15)
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    with urllib.request.urlopen(req, timeout=60) as r:
        data: bytes = r.read()
        return data


def last_two_10k(cik: int, ua: str) -> tuple[str, list[dict[str, str]]]:
    d = json.loads(get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", ua))
    r = {k: list(d["filings"]["recent"][k]) for k in FIELDS}
    # Prolific filers (JPMorgan) push older 10-Ks out of "recent" into paged files.
    for page in d["filings"].get("files", []):
        if r["form"].count("10-K") >= 2:
            break
        extra = json.loads(get(f"https://data.sec.gov/submissions/{page['name']}", ua))
        for k in FIELDS:
            r[k] += extra[k]
    idx = [i for i, f in enumerate(r["form"]) if f == "10-K"][:2]
    return d["name"], [{k: r[k][i] for k in FIELDS} for i in idx]


def main() -> int:
    ua = os.environ.get("SEC_USER_AGENT", "")
    if "@" not in ua:
        print("Set SEC_USER_AGENT to 'name email', as EDGAR's fair-access policy asks.")
        return 2
    rows: dict[str, list[list[str]]] = {"data/raw": [], "data/raw_prev": []}
    for ticker, cik in COMPANIES.items():
        name, filings = last_two_10k(cik, ua)
        for folder, f in zip(rows, filings, strict=False):
            acc = f["accessionNumber"]
            url = (f"https://www.sec.gov/Archives/edgar/data/{cik}/"
                   f"{acc.replace('-', '')}/{f['primaryDocument']}")
            fn = f"{ticker}_10-K_{f['reportDate']}.htm"
            dest = Path(folder) / fn
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                dest.write_bytes(get(url, ua))
            rows[folder].append([ticker, name, str(cik), acc, f["filingDate"],
                                 f["reportDate"], fn, url])
        print(f"ok   {ticker}")
    for folder, rs in rows.items():
        with open(Path(folder) / "MANIFEST.tsv", "w") as out:
            out.write("\t".join(COLUMNS) + "\n")
            out.writelines("\t".join(r) + "\n" for r in rs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
