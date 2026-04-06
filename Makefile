PYTHON ?= python3

.PHONY: install install-dev verify verify-strict test test-unittest lint typecheck bundle ci

install:
	$(PYTHON) -m pip install -e .

install-dev:
	$(PYTHON) -m pip install -r requirements-dev.txt

verify:
	$(PYTHON) tools/verify.py --report-json logs/verify-report.json

verify-strict:
	$(PYTHON) tools/verify.py --strict-tools --report-json logs/verify-report.json

test:
	$(PYTHON) -m pytest -q

test-unittest:
	$(PYTHON) -m unittest discover -s tests -p 'test_*.py'

lint:
	$(PYTHON) -m ruff check inkscape_wps tests

typecheck:
	$(PYTHON) -m mypy

bundle:
	$(PYTHON) -m PyInstaller packaging/inkscape_wps.spec --noconfirm

ci: verify-strict
