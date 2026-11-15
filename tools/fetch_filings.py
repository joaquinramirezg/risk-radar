#!/usr/bin/env python3
"""Download the latest two 10-Ks for each S&P 100 company from SEC EDGAR.

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

# Roughly the S&P 100 (102 tickers, one per company), as drawn up in November 2026.
# Index membership changes; this list is not kept in sync with it.
COMPANIES = {
    "AAPL": 320193, "ABBV": 1551152, "ABT": 1800, "ACN": 1467373, "ADBE": 796343, "AIG": 5272,
    "AMD": 2488, "AMGN": 318154, "AMT": 1053507, "AMZN": 1018724, "AVGO": 1730168, "AXP": 4962,
    "BA": 12927, "BAC": 70858, "BK": 1390777, "BKNG": 1075531, "BLK": 2012383, "BMY": 14272,
    "BRK-B": 1067983, "C": 831001, "CAT": 18230, "CHTR": 1091667, "CL": 21665, "CMCSA": 1166691,
    "COF": 927628, "COP": 1163165, "COST": 909832, "CRM": 1108524, "CSCO": 858877, "CVS": 64803,
    "CVX": 93410, "DE": 315189, "DHR": 313616, "DIS": 1744489, "DUK": 1326160, "EMR": 32604,
    "F": 37996, "FDX": 1048911, "GD": 40533, "GE": 40545, "GILD": 882095, "GM": 1467858,
    "GOOGL": 1652044, "GS": 886982, "HD": 354950, "HON": 773840, "IBM": 51143, "INTC": 50863,
    "INTU": 896878, "ISRG": 1035267, "JNJ": 200406, "JPM": 19617, "KO": 21344, "LIN": 1707925,
    "LLY": 59478, "LMT": 936468, "LOW": 60667, "MA": 1141391, "MCD": 63908, "MDLZ": 1103982,
    "MDT": 1613103, "MET": 1099219, "META": 1326801, "MMM": 66740, "MO": 764180, "MRK": 310158,
    "MS": 895421, "MSFT": 789019, "NEE": 753308, "NFLX": 1065280, "NKE": 320187, "NOW": 1373715,
    "NVDA": 1045810, "ORCL": 1341439, "PEP": 77476, "PFE": 78003, "PG": 80424, "PLTR": 1321655,
    "PM": 1413329, "PYPL": 1633917, "QCOM": 804328, "RTX": 101829, "SBUX": 829224,
    "SCHW": 316709, "SO": 92122, "SPG": 1063761, "T": 732717, "TGT": 27419, "TMO": 97745,
    "TMUS": 1283699, "TSLA": 1318605, "TXN": 97476, "UBER": 1543151, "UNH": 731766,
    "UNP": 100885, "UPS": 1090727, "USB": 36104, "V": 1403161, "VZ": 732712, "WFC": 72971,
    "WMT": 104169, "XOM": 34088,
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


def companion(cik: int, acc: str, primary: str, dest: Path, ua: str) -> None:
    """Some banks (BNY, U.S. Bancorp, Wells Fargo) file the annual report,
    which holds the risk factors, as a second main document of the 10-K.
    Save any such document next to the primary one as <name>.annual.html."""
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}"
    out = dest.with_suffix(".annual.html")
    if out.exists():
        return
    items = json.loads(get(f"{base}/index.json", ua))["directory"]["item"]
    docs = [i["name"] for i in items if i["name"].endswith(".htm") and i["name"] != primary
            and not i["name"].startswith("R") and "ex" not in i["name"].lower()]
    if docs:
        out.write_bytes(get(f"{base}/{docs[0]}", ua))


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
            companion(cik, acc, f["primaryDocument"], dest, ua)
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
