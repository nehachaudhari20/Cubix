# RedBlue — Payment Defense Twin

### Build the attack. Break the defense. Understand the gap. Harden the payment system.

**RedBlue** (Payment Defense Twin) is an isolated, **synthetic** adversarial payment laboratory built for the **Mastercard Innovation Challenge 2026 — AI Defense Lab for Payment Security**.

It runs a closed loop:

1. **Red Team** discovers / plans adversarial payment journeys  
2. Executes them in a **stateful synthetic sandbox**  
3. Captures evidence in an adversarial buffer  
4. **Blue Team** trains / hardens FraudShield from that evidence  
5. **Evaluation** scores the loop and surfaces control gaps  
6. Repeat

> This platform uses **synthetic data only**. It is not connected to live issuer/acquirer rails.

---

## Live deployment

| Surface | URL |
|--------|-----|
| **Mission Control (UI)** | [http://13.51.196.173:3000/mission-control](http://13.51.196.173:3000/mission-control) |
| **Frontend root** | [http://13.51.196.173:3000](http://13.51.196.173:3000) |
| **API docs** | [http://13.51.196.173:8000/docs](http://13.51.196.173:8000/docs) |
| **API health** | [http://13.51.196.173:8000/health](http://13.51.196.173:8000/health) |

EC2 host: `13.51.196.173` · SSH user: `ec2-user` · Stack: Docker Compose (`postgres` + `backend` + `frontend`)

---

## Features

### Research & knowledge base
RedBlue is built on a **canonical payment-fraud knowledge base** assembled from structured research — not scraped transaction dumps.

**Sources we synthesized**
- **15 Mastercard Innovation Challenge taxonomies** (`data/raw_pdfs/`) — KYC, device/session, authentication, payment initiation, authorization, merchant, acquirer, gateway, payment rails, open banking, cash-out, AML, agent commerce, network abuse
- **Industry threat research** — CrowdStrike-style payment-fraud reporting, published card-not-present / ATO / mule narratives, and open fraud case studies used to enrich family flows, signals, and controls
- **Internal normalization pipeline** — PDF → family records → vectors → controls → simulation templates → compiled sandbox rules (`scripts/build_canonical_knowledge.py`, `docs/PDF_TAXONOMY_MAP.md`)

**What the KB contains (canonical registry v2)**

| Asset | Scale |
|-------|------:|
| Attack families | **67** (all simulatable across 7 control surfaces) |
| Attack variants & executable vectors | **363** each |
| Cross-family relationships | **5,000** |
| Detection signals | **276** |
| Defense controls | **342** |
| Lifecycle stages | **49** |
| Compiled sandbox rules | **301** |
| Signal → feature mappings | **151** |
| Evidence / source references | **388** |
| Simulation templates | **9** surfaces × parameter sets |

The KB is **not** training data — it is the **spec** Red Team plans from and the Sandbox adjudicates against.

---

### Red Team — adversarial discovery & DeepTeam engine
- **Threat Hunter Agent + Attack Planner Agent** select families from the KB using strategy memory and surface coverage goals.
- **DeepTeam-inspired engine** (`backend/red_team/deepteam/`): **Transform → Vary → Validate** — mutates legitimate payment baselines into adversarial payloads, scores variations against compiled controls, and rejects invalid journeys before sandbox execution.
- **Linear mutator + surface mutator** for multi-surface campaigns (KYC, device, auth, open banking, agentic GenAI, payment rail, network).
- **LLM-assisted generation** (optional): Cohere / OpenRouter / Bedrock / Gemini agents for hypothesis expansion; ChromaDB RAG over the full KB for grounded retrieval.
- **Composite campaigns** chain multiple surfaces in one adversarial journey (not payment-only stubs).
- Outputs **Adversarial Payment Campaigns** — never self-labels success; the Sandbox decides.

---

### Synthetic sandbox — stateful payment environment
The sandbox is the **live bank world**, not Blue Team.

- **Persistent world state** — customers, devices, accounts, merchants, velocity, trust carry forward (`backend/sandbox/state.py`).
- **15 control-surface engines** — KYC, device/session, authentication, beneficiary, payment initiation, gateway, acquirer, AML, mule/cash-out, GenAI context, risk, authorization, settlement, and more.
- **KB-compiled rule engine** — 301 rules derived from canonical controls; returns **ALLOW / CHALLENGE / BLOCK** with `control_triggers` and reasons.
- **FraudShield scoring** on every adjudicated path — stacked ensemble + isolation-forest anomaly layer on active model version.
- **7 adjudicated surfaces · 35 techniques · 67/67 families executable** — agentic, social-engineering, and open-banking families no longer forced through a fake payment leg.
- Emits unified **`SandboxObservation`** records → adversarial evidence buffer (decision, risk, ML score, journey, missing controls).

---

### Blue Team — FraudShield ML stack
- **FraudShield v3 stacked ensemble**: Level-0 **XGBoost + LightGBM + Logistic Regression** → Level-1 **meta-learner** (out-of-fold stacking).
- **Isolation Forest** anomaly head for novel distribution / hard-negative detection.
- **Feature builder** — 31 engineered features with KB signal mappings (amount, velocity, device age, merchant risk, graph flags, surface-specific GenAI features, etc.).
- **Training mix** — baseline legitimate rows + adversarial buffer bypasses + hard negatives with **campaign-disjoint** temporal splits (no leakage across Red campaigns).
- **Hardening loop** — retrain on new buffer evidence, compare v1 → v2 → v3, optional model swap into the live sandbox.
- **Feature importance** surfaced in Mission Control / Blue Team for explainability after each harden.

---

### Closed learning loop — how the system learns
Each **platform loop** runs end-to-end:

```text
KB → Red Team (DeepTeam + campaigns) → Sandbox adjudication → Evidence buffer
      → Blue harden (stacked retrain) → Evaluation (11a–11e) → Control-gap labs → Verify → repeat
```

- **Mission Control** starts loops with **8 / 15 / 20 / 35 / 40 / All (67)** families; live stream rotates families in batches.
- **`fresh_buffer=false`** preserves accumulated adversarial evidence across runs (demo-safe).
- **Force Stop** (`POST /api/platform/loop/stop`) clears stuck scheduler state.
- After each loop, Evaluation scores detection lift; Control Gap Lab compares **expected KB controls vs what actually fired**; Blue swaps the harder model into the next Red round.

---

### Evaluation framework (Phases 11–14)
Full loop scorecard — not a single accuracy number:

| Pillar | What it measures |
|--------|------------------|
| **Detection** | Holdout / test / buffer PR-AUC, ROC-AUC, F1 vs prior model version |
| **Fidelity** | Synthetic vs baseline distribution checks (amount KS, timing, velocity correlation, score separation) |
| **Generalization** | Family recall, surface recall, **LOFO** gap, unseen variant recall, composite campaign recall |
| **Integrity** | Calibration, stability, and adversarial robustness battery |
| **ASR** | Attack Success Rate before vs after hardening |
| **Graph fidelity** | Journey / relationship graph realism |
| **Graph model** | Graph-aware fraud signal evaluation |

Rendered in **Evaluation** UI as radar + fidelity bars + per-run JSON under `data/evaluation/`.

---

### Control gap & Labs
- **Control Gap Lab** — for each sandbox outcome, compares KB `targeted_control_ids` vs `control_triggers` actually fired; surfaces missing controls (CTL-####) and families with gaps.
- **Labs** — experiment table across completed **and stopped** runs: buffer lift, ASR before→after, gap heatmaps, hardening signals (works on partial EC2 runs too).

---

### Platform scale (research + runtime)

| Metric | Scale |
|--------|------:|
| Closed-loop platform runs executed | **45+** |
| Synthetic ML corpus (`master_dataset.json`) | **~107,100** labeled transactions |
| Legitimate baseline rows | **53,930** |
| Known-fraud reference rows | **53,170** |
| Adversarial evidence adjudications (buffer) | **1,946+** |
| Campaign events logged | **2,000+** |
| Per-loop evaluation artifacts | **12** JSON reports |
| Money-at-risk simulated (demo KPI) | **₹42L+** fraud exposure analyzed |

*All figures are synthetic — used for adversarial testing and model hardening only.*

---

### Mission Control UI
| Page | Route | Highlights |
|------|-------|------------|
| **Overview** | `/mission-control` | KPIs, loop start/stop, live experiment stream, history |
| **Red Team** | `/red-team` | Family catalog + per-loop campaign outcomes |
| **Sandbox** | `/sandbox` | Full adjudication path, rails, ML + rule scores |
| **Blue Team** | `/blue-team` | Stacked model learning curve (Day 1–4), feature importance |
| **Labs** | `/labs` | Control gaps, ASR lift, experiment grid |
| **Evaluation** | `/evaluation` | Real radar from loop JSON — fidelity, generalization, detection |

---

### Tech stack

| Layer | Technologies |
|-------|----------------|
| **Frontend** | Next.js 16, React 19, TypeScript, Tailwind |
| **API** | FastAPI, Uvicorn, Pydantic v2, SQLAlchemy |
| **Agents** | LangGraph, LangChain |
| **LLM** | Cohere, OpenRouter, OpenAI, Google Gemini, **AWS Bedrock** |
| **Vector memory** | ChromaDB (KB RAG for Red Team) |
| **ML / Blue Team** | XGBoost, LightGBM, scikit-learn, Isolation Forest, pandas, NumPy |
| **Graph analysis** | NetworkX (journey / relationship evaluation) |
| **Database** | PostgreSQL (Docker/EC2), SQLite (local fallback) |
| **Cloud / deploy** | **AWS EC2**, Docker Compose, **AWS Bedrock**, boto3, optional **AWS SageMaker** for managed training endpoints |
| **Scheduling** | APScheduler (platform loop scheduler) |

---

## Architecture

![RedBlue / Payment Defense Twin architecture](docs/architecture.png)

---

## Repository layout

```text
RedBlue/
├── backend/                 # FastAPI + Red/Blue/Sandbox/platform
│   ├── api/                 # HTTP routes (platform, knowledge, …)
│   ├── red_team/
│   ├── blue_team/
│   ├── sandbox/
│   ├── platform/            # loop runner, scheduler, status
│   └── llm/                 # Cohere / OpenRouter / … providers
├── frontend/                # Next.js Mission Control UI
├── data/
│   ├── knowledge/           # Canonical attack KB
│   ├── models/              # FraudShield artifacts
│   ├── evaluation/          # Per-loop eval JSON
│   ├── adversarial_buffer/  # evidence.jsonl (demo snapshot included)
│   └── platform.db          # Demo SQLite snapshot (seeded into Postgres on Docker boot)
├── scripts/
│   ├── deploy-ec2.sh
│   ├── docker-entrypoint.sh
│   ├── seed_demo_to_pg.py
│   └── …
├── docker-compose.yml
├── Dockerfile.prod          # Backend image
├── requirements.txt         # Local / full deps
├── requirements-prod.txt    # Lean production image deps
└── .env.example
```

---

## Prerequisites

- **Python 3.12+** and a virtualenv  
- **Node.js 20+** and npm  
- **Docker + Docker Compose** (for container / EC2 style runs)  
- An LLM API key (e.g. `COHERE_API_KEY` or `OPENROUTER_API_KEY`) if you want live Red Team LLM calls  

---

## Quick start — local (recommended for development)

### 1. Clone & Python env

```bash
git clone https://github.com/nehachaudhari20/RedBlue.git
cd RedBlue
python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Environment

```bash
cp .env.example .env
```

For **local uvicorn** (no Docker Postgres), set:

```env
DB_URL=sqlite:///./data/platform.db
RED_TEAM_USE_LLM=true
LLM_PROVIDER=cohere
COHERE_API_KEY=your_key_here
```

> If `RDS_HOST` is set and RDS is unreachable, the backend falls back to SQLite automatically.

### 3. Start backend (port 8000)

```bash
# from repo root, venv active
python -m uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000
```

API docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### 4. Start frontend (port 3000)

```bash
cd frontend
cp .env.example .env.local   # optional
# .env.local:
# NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000

npm install --legacy-peer-deps
npm run dev
```

UI: [http://127.0.0.1:3000/mission-control](http://127.0.0.1:3000/mission-control)

### 5. Smoke checks

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/platform/status
curl http://127.0.0.1:8000/api/platform/runs
```

---

## Run with Docker Compose (local or EC2-like)

This starts **Postgres + backend + frontend**.

### 1. Configure `.env`

```bash
cp .env.example .env
```

**Important for Docker:** `DB_URL` must use hostname **`postgres`** (the Compose service name), not `localhost`:

```env
POSTGRES_DB=payment_defense_twin
POSTGRES_USER=postgres
POSTGRES_PASSWORD=change_me_in_production
DB_URL=postgresql+psycopg://postgres:change_me_in_production@postgres:5432/payment_defense_twin
COHERE_API_KEY=your_key_here
RED_TEAM_USE_LLM=true
LLM_PROVIDER=cohere

# Browser-facing API URL baked into the Next.js image
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

### 2. Build & start

```bash
docker compose down
docker compose build --no-cache frontend   # required when API URL / UI changes
docker compose up -d --build
docker compose ps
docker compose logs -f backend
```

### 3. Open

- UI: [http://127.0.0.1:3000/mission-control](http://127.0.0.1:3000/mission-control)  
- API: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### Demo data seed

On container start, `scripts/docker-entrypoint.sh` copies the baked demo snapshot and runs `scripts/seed_demo_to_pg.py` when `loop_runs` is empty (SQLite `data/platform.db` → Postgres). Buffer comes from baked `data/adversarial_buffer/evidence.jsonl`.

Force re-seed:

```bash
docker compose exec backend sh -lc 'FORCE_DEMO_SEED=1 PYTHONPATH=/app python /app/scripts/seed_demo_to_pg.py'
docker compose restart backend
```

---

## Deploy / update on EC2

**Current prod URL:** [http://13.51.196.173:3000/mission-control](http://13.51.196.173:3000/mission-control)

```bash
ssh -i redblue.pem ec2-user@13.51.196.173
cd ~/RedBlue
bash scripts/deploy-ec2.sh
```

Or manually:

```bash
cd ~/RedBlue
git fetch origin && git checkout master && git pull origin master

# Ensure .env has ONE DB_URL pointing at @postgres (not localhost / not duplicate RDS lines)
docker compose build --no-cache frontend
docker compose up -d --build
docker compose ps
```

Set the public API URL for the frontend image:

```bash
export NEXT_PUBLIC_API_BASE_URL=http://13.51.196.173:8000
docker compose build --no-cache frontend
docker compose up -d
```

**Security group:** allow inbound TCP **22**, **3000**, **8000** (keep **5432** closed from the public internet).

---

## Platform loop (API)

Start a loop (families limited up to 67/80):

```bash
curl -X POST http://127.0.0.1:8000/api/platform/loop/run \
  -H "Content-Type: application/json" \
  -d '{"families":8,"skip_train_v1":true,"swap_model":true,"fresh_buffer":false}'
```

Force-stop (clears stuck UI / scheduler state):

```bash
curl -X POST http://127.0.0.1:8000/api/platform/loop/stop
```

---

## Useful commands

```bash
# Backend only
python -m uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000

# Frontend only
cd frontend && npm run dev

# Docker
docker compose ps
docker compose logs -f backend
docker compose logs -f frontend
docker compose down

# Rebuild UI after code or API URL change
docker compose build --no-cache frontend && docker compose up -d frontend
```

---

## Environment reference

| Variable | Purpose |
|----------|---------|
| `DB_URL` | SQLAlchemy URL (`sqlite:///./data/platform.db` or Postgres) |
| `POSTGRES_*` | Compose Postgres bootstrap |
| `RED_TEAM_USE_LLM` | Enable LLM-backed Red Team |
| `LLM_PROVIDER` | `cohere` / `openrouter` / `openai` / `gemini` / … |
| `COHERE_API_KEY` | Cohere key |
| `OPENROUTER_API_KEY` | OpenRouter key |
| `NEXT_PUBLIC_API_BASE_URL` | Browser → API base (baked into Next production build) |
| `RDS_HOST` / `RDS_*` | Optional AWS RDS (local falls back to SQLite if unreachable) |
| `FORCE_DEMO_SEED` | `1` to re-import baked `platform.db` into Postgres |

Never commit real `.env` files.

---

## Notes / gotchas

1. **Frontend Docker cache** — after UI or `NEXT_PUBLIC_API_BASE_URL` changes, always `docker compose build --no-cache frontend`.  
2. **`DB_URL` inside containers** — must be `@postgres`, not `@localhost`. Multiple `DB_URL=` lines in `.env` → last one wins (avoid duplicate RDS lines on EC2).  
3. **Entrypoint line endings** — `scripts/docker-entrypoint.sh` must be LF (Unix). CRLF causes `exec ... no such file or directory`.  
4. **Local vs remote data** — local SQLite/`evidence.jsonl` are not automatically the same as EC2 Postgres unless you bake/seed (this repo includes a demo snapshot for Docker).  
5. **Synthetic only** — all payments, merchants, and identities are simulated.

---

## License / challenge context

Built for the **Mastercard Innovation Challenge 2026 — AI Defense Lab for Payment Security**.

See repository `LICENSE` (if present) and `docs/` for deeper architecture and data dictionary material.
