PY := $(CURDIR)/.venv/bin/python
export PYTHONPATH := $(CURDIR)/src
export MPLBACKEND := Agg
export MPLCONFIGDIR := /tmp/portfolio-matplotlib
.PHONY: setup lint test bench demo
setup:
	python3 -m venv .venv
	$(PY) -m pip install -r requirements.txt
lint:
	$(PY) -m ruff check src tests
	$(PY) -m ruff format --check src tests
test:
	$(PY) -m pytest -q
bench:
	@mkdir -p evidence
	$(PY) src/main.py > evidence/bench.json
	@cat evidence/bench.json
demo: bench
