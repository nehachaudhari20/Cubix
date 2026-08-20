# Payment Defense Twin

### Build the attack. Break the defense. Understand the gap. Harden the payment system.

Payment Defense Twin is an isolated, synthetic adversarial payment laboratory designed for the Mastercard Innovation Challenge 2026 — AI Defense Lab for Payment Security.

The system creates an adaptive Red Team that discovers and generates adversarial payment journeys, executes them inside a stateful synthetic payment environment, analyzes how the defense responds, discovers control gaps, and feeds useful adversarial evidence into a Blue Team fraud detector for batch hardening.

The goal is not simply to train a fraud classifier.

The goal is to:

1. Discover attacks
2. Build realistic attack journeys
3. Execute them inside a payment environment
4. Understand why they succeeded or failed
5. Discover control gaps
6. Test possible interventions
7. Harden the defense
8. Evaluate against unseen attacks
9. Re-attack the hardened environment

---
## Repository Structure
payment-defense-twin/
│
├── .env.example
├── .gitignore
├── README.md
├── LICENSE
├── requirements.txt
├── docker-compose.yml          # Local infrastructure — expanded as services are implemented
├── Makefile                    # Common development commands
│
├── docs/
│   ├── architecture.md
│   ├── data-dictionary.md
│   └── taxonomies/
│       ├── identity-kyc.pdf
│       ├── authentication.pdf
│       └── ...                 # Payment lifecycle stage taxonomies
│
├── data/
│   ├── baseline/
│   │   └── baseline_transactions.csv
│   │
│   ├── known_fraud/
│   │   └── known_fraud.csv
│   │
│   ├── synthetic_generated/
│   │                           # Red Team generated attacks
│   │
│   ├── knowledge/
│   │   ├── attack_families.json
│   │   ├── attack_signals.json
│   │   ├── lifecycle_stages.json
│   │   └── control_gaps.json
│   │
│   └── models/
│       └── fraudshield_v1.pkl
│
├── src/
│   ├── backend/
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── routes.py
│   │   │   └── schemas.py
│   │   │
│   │   ├── sandbox/
│   │   │   ├── engines/
│   │   │   ├── rules/
│   │   │   └── state.py
│   │   │
│   │   ├── red_team/
│   │   │   ├── agents/
│   │   │   ├── memory/
│   │   │   └── strategies/
│   │   │
│   │   ├── blue_team/
│   │   │   ├── features.py
│   │   │   ├── model.py
│   │   │   ├── trainer.py
│   │   │   └── evaluator.py
│   │   │
│   │   ├── knowledge/
│   │   │   ├── loader.py
│   │   │   └── vector_store.py
│   │   │
│   │   ├── utils/
│   │   └── main.py
│   │
│   ├── frontend/
│   │   ├── public/
│   │   ├── src/
│   │   │   ├── components/
│   │   │   ├── pages/
│   │   │   ├── hooks/
│   │   │   └── services/
│   │   └── package.json
│   │
│   ├── ml/
│   │   ├── train_baseline.py
│   │   └── evaluate_unseen.py
│   │
│   └── scripts/
│       ├── seed_knowledge.py
│       ├── generate_baseline.py
│       ├── load_taxonomies.py
│       └── init_db.py
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── conftest.py
│
└── .github/
    └── workflows/

---

## Product Architecture

The system consists of three primary pillars.

### 1. Red Team

The autonomous adversarial layer.

Responsibilities:

- Threat discovery
- Attack hypothesis generation
- Multi-step campaign planning
- Synthetic attack generation
- Sandbox experimentation
- Failure analysis
- Environment-specific memory
- Adaptive strategy selection

Primary output:

```text
Adversarial Payment Campaign