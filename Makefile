PYTHON ?= python3

.PHONY: verify verify-strict test test-unittest lint typecheck ci

verify:
	$(PYTHON) tools/verify.py --report-json logs/verify-report.json

verify-strict:
	$(PYTHON) tools/verify.py --strict-tools --report-json logs/verify-report.json

ci: verify-strict

test:
	$(PYTHON) -m pytest -q

test-unittest:
	$(PYTHON) -m unittest discover -s tests -p 'test_*.py'

lint:
	$(PYTHON) -m ruff check inkscape_wps tests

typecheck:
	$(PYTHON) -m mypy
