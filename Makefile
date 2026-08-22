PYTHON ?= python

.PHONY: install seed train run dashboard test test-platform loop

install:
	$(PYTHON) -m pip install -r requirements.txt

seed:
	$(PYTHON) src/scripts/seed_knowledge.py

train:
	$(PYTHON) src/ml/train_baseline.py

run:
	$(PYTHON) -m uvicorn backend.api.main:app --app-dir src --reload --host 0.0.0.0 --port 8000

dashboard: run

loop:
	$(PYTHON) src/scripts/run_full_loop.py --skip-train-v1 --families 5

test:
	pytest -q

test-platform:
	$(PYTHON) src/scripts/test_platform.py
