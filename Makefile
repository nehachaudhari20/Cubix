PYTHON ?= python

.PHONY: install seed train run test

install:
	$(PYTHON) -m pip install -r requirements.txt

seed:
	$(PYTHON) src/scripts/seed_knowledge.py

train:
	$(PYTHON) src/ml/train_baseline.py

run:
	uvicorn src.backend.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest -q
