.PHONY: test lint types eval all
# The deterministic half of this harness needs no install: pure stdlib, so a
# reviewer can reproduce the retrieval numbers from a fresh clone.
test:
	PYTHONPATH=src:tools python3 -m pytest -q
lint:
	ruff check src tools tests
types:
	mypy src
eval:
	PYTHONPATH=src:tools python3 tools/run_retrieval_eval.py
all: lint types test eval
