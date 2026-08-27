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

```text
payment-defense-twin/
├── .env.example
├── .gitignore
├── README.md
├── LICENSE
├── requirements.txt
├── docker-compose.yml
├── Makefile
│
├── docs/
│   ├── architecture.md
│   ├── data-dictionary.md
│   └── taxonomies/
│       ├── identity-kyc.pdf
│       ├── authentication.pdf
│       └── ...
│
├── data/
│   ├── baseline/
│   │   └── baseline_transactions.csv
│   ├── known_fraud/
│   │   └── known_fraud.csv
│   ├── knowledge/
│   │   └── canonical/
│   └── models/
│
├── backend/
│   ├── api/
│   ├── knowledge/
│   ├── sandbox/
│   ├── red_team/
│   └── blue_team/
├── frontend/
│   ├── app/
│   ├── components/
│   └── public/
├── scripts/
│   ├── run_full_loop.py
│   ├── test_red_team_llm_agents.py
│   └── ...
│
└── .github/
    └── workflows/
```

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
```
