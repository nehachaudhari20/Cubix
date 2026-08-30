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

## What you get in the UI

| Page | Route | Purpose |
|------|-------|---------|
| **Overview** | `/mission-control` | KPIs, start/stop platform loop, live experiment stream, history |
| **Red Team** | `/red-team` | Attack families + selected loop campaign view |
| **Sandbox** | `/sandbox` | Payment-environment evidence for a loop |
| **Blue Team** | `/blue-team` | Model learning / feature importance |
| **Labs** | `/labs` | Per-run lab table (completed + stopped) |
| **Evaluation** | `/evaluation` | Scorecards / radar from `data/evaluation` |

---

## Architecture (high level)

```text
┌─────────────┐     campaigns      ┌──────────────────┐
│  Red Team   │ ─────────────────► │ Synthetic Sandbox│
│  (LLM+KB)   │                    │ + Risk / Authz   │
└──────┬──────┘                    └────────┬─────────┘
       │                                    │ evidence.jsonl
       │                           ┌────────▼─────────┐
       │                           │ Adversarial Buffer│
       │                           └────────┬─────────┘
       │                                    │ train / harden
       │                           ┌────────▼─────────┐
       └────────────────────────── │ Blue Team        │
                                   │ FraudShield v3   │
                                   └────────┬─────────┘
                                            │ reports
                                   ┌────────▼─────────┐
                                   │ Evaluation JSON  │
                                   └──────────────────┘
```

**Data stores**

| Environment | Runs / history | Buffer / files |
|-------------|----------------|----------------|
| Local `uvicorn` (typical) | SQLite `data/platform.db` (or RDS if reachable) | `data/adversarial_buffer/evidence.jsonl` |
| Docker / EC2 | Postgres service `pdt-postgres` | Baked into backend image (+ seed on boot) |

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
