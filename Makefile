.PHONY: test lint types check eval ladder fetch radar serve all
# Tests, lint, types and the site check need no install beyond the dev extra:
# pure stdlib, so a reviewer can run them from a fresh clone.
test:
	PYTHONPATH=src:tools python3 -m pytest -q
lint:
	ruff check src tools tests
types:
	mypy src
# Is the published data internally consistent? (deep links, counts, quotes)
check:
	python3 tools/check_site.py
eval:
	PYTHONPATH=src:tools python3 tools/run_retrieval_eval.py
ladder:
	PYTHONPATH=src:tools python3 tools/run_retrieval_eval.py --ladder

# Risk Radar, end to end. fetch needs SEC_USER_AGENT="name email" (EDGAR's
# rule for automated clients); radar needs the `ladder` extra for the matcher.
fetch:
	python3 tools/fetch_filings.py
radar:
	PYTHONPATH=src python3 tools/build_radar.py
	python3 tools/findings.py
	python3 tools/search_index.py
	python3 tools/check_site.py
serve:
	python3 -m http.server 8000 --directory site

all: lint types test check
