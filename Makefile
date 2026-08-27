PYTHON ?= python

.PHONY: install train run dashboard test test-platform loop query-rds

install:
	$(PYTHON) -m pip install -r requirements.txt

train:
	$(PYTHON) scripts/train_model.py

run:
	$(PYTHON) -m uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000

dashboard: run

loop:
	$(PYTHON) scripts/run_full_loop.py --skip-train-v1 --families 5

test:
	pytest -q

test-platform:
	$(PYTHON) scripts/test_platform.py

query-rds:
	$(PYTHON) scripts/query_rds.py
