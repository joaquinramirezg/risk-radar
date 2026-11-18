#!/usr/bin/env python3
"""Check that the published site data is internally consistent.

  python3 tools/check_site.py          # exit 1 and list every problem found

Stdlib only, so CI runs it on every push. It catches what a rebuild can break
without any test failing: a company in the index with no data file, a deep
link on the front page that points at a risk that no longer exists, counts
that disagree with the risks listed, a diff whose two sides do not add up to
the text shown, or a filing link that is not on sec.gov.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "site" / "data"
STATUSES = {"new", "split", "removed", "merged", "rewritten", "edited", "unchanged"}
LABELS = {"new_exposure", "escalated", "de_escalated", "clarified", "boilerplate"}
LINKED = {"split", "merged"}
PAIRED = {"rewritten", "edited"}


def check_company(ticker: str, d: dict) -> list[str]:
    bad: list[str] = []
    say = bad.append
    if d.get("ticker") != ticker:
        say(f"{ticker}: file holds ticker {d.get('ticker')!r}")
    for side in ("current", "previous"):
        f = d.get(side) or {}
        if not str(f.get("url", "")).startswith("https://www.sec.gov/Archives/edgar/data/"):
            say(f"{ticker}: {side} filing link is not an EDGAR archive URL")
        if not f.get("period_end") or not f.get("filed"):
            say(f"{ticker}: {side} filing has no period or filing date")
    if d["current"]["period_end"] <= d["previous"]["period_end"]:
        say(f"{ticker}: current period does not follow the previous one")

    risks = d.get("risks", [])
    ids = Counter(r.get("id") for r in risks)
    for rid, n in ids.items():
        if n > 1:
            say(f"{ticker}: risk id {rid} used {n} times")
    statuses = Counter(r["status"] for r in risks)
    if dict(statuses) != {k: v for k, v in d["counts"].items() if v}:
        say(f"{ticker}: counts {d['counts']} disagree with the risks listed {dict(statuses)}")
    now = sum(v for k, v in statuses.items() if k not in ("removed", "merged"))
    before = sum(v for k, v in statuses.items() if k not in ("new", "split"))
    if now != d["current"]["risks"] or before != d["previous"]["risks"]:
        say(f"{ticker}: {now}/{before} risks listed, header says "
            f"{d['current']['risks']}/{d['previous']['risks']}")

    titles_now = {r["title"] for r in risks if r["status"] not in ("removed", "merged")}
    titles_before = {r.get("old_title", r["title"]) for r in risks
                     if r["status"] not in ("new", "split")}
    for r in risks:
        where = f"{ticker} {r.get('id')}"
        if r["status"] not in STATUSES:
            say(f"{where}: unknown status {r['status']!r}")
        if not r.get("title", "").strip():
            say(f"{where}: empty title")
        if r["status"] in PAIRED:
            ops = r.get("diff")
            if not ops:
                say(f"{where}: {r['status']} risk has no diff")
                continue
            if any(op not in ("=", "+", "-") for op, _ in ops):
                say(f"{where}: diff has an unknown op")
            if all(op == "=" for op, _ in ops):
                if r.get("old_title", r["title"]) == r["title"]:
                    say(f"{where}: {r['status']} risk has no change in title or text")
        elif not r.get("body", "").strip():
            say(f"{where}: {r['status']} risk has no text")
        if r["status"] in LINKED:
            pool = titles_before if r["status"] == "split" else titles_now
            if r.get("link_title") not in pool:
                say(f"{where}: {r['status']} partner {r.get('link_title')!r} is not in the list")
        ch = r.get("change")
        if ch is not None:
            if r["status"] not in ("edited", "rewritten"):
                say(f"{where}: change type on a {r['status']} risk")
            if ch.get("label") not in LABELS:
                say(f"{where}: unknown change type {ch.get('label')!r}")
    return bad


def main() -> int:
    bad: list[str] = []
    index = json.loads((DATA / "index.json").read_text())
    listed = [c["ticker"] for c in index["companies"]]
    shared = {"index", "findings", "search", "eval", "faded", "example", "examples",
              "forecast", "forecast_score"}
    files = {p.stem for p in DATA.glob("*.json")} - shared
    if len(set(listed)) != len(listed):
        bad.append("index lists a company twice")
    for t in sorted(set(listed) - files):
        bad.append(f"index lists {t} but site/data/{t}.json is missing")
    for t in sorted(files - set(listed)):
        bad.append(f"site/data/{t}.json is not in the index")
    skipped = {s["ticker"] if isinstance(s, dict) else s for s in index.get("skipped", [])}
    for t in sorted(skipped & set(listed)):
        bad.append(f"{t} is both listed and skipped")

    docs = {}
    for t in sorted(set(listed) & files):
        d = json.loads((DATA / f"{t}.json").read_text())
        docs[t] = d
        bad += check_company(t, d)
        entry = next(c for c in index["companies"] if c["ticker"] == t)
        if entry["counts"] != d["counts"] or entry["current"] != d["current"]:
            bad.append(f"{t}: index entry disagrees with its data file")

    f = json.loads((DATA / "findings.json").read_text())
    if f["companies"] != len(docs):
        bad.append(f"findings counts {f['companies']} companies, index has {len(docs)}")
    ids = {(t, r["id"]): r for t, d in docs.items() for r in d["risks"]}
    for th in f["themes"]:
        name = th["theme"]
        for ex, side in [(e, "+") for e in th["examples"]] + \
                [(e, "-") for e in th.get("down_examples", [])]:
            r = ids.get((ex["ticker"], ex["id"]))
            if r is None:
                bad.append(f"finding '{name}' links to missing risk {ex['ticker']}/{ex['id']}")
                continue
            # Up examples quote this year's text, down examples last year's.
            other = "-" if side == "+" else "+"
            text = r.get("body") or "".join(t for op, t in r["diff"] if op != other)
            probe = ex["sentence"].rstrip("…").strip()[:80]
            if probe not in text:
                bad.append(f"finding '{name}' quotes a sentence not in {ex['ticker']}/{ex['id']}")

    for line in bad:
        print(line)
    n = sum(len(d["risks"]) for d in docs.values())
    print(f"{len(docs)} companies, {n} risks, {len(bad)} problems")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
