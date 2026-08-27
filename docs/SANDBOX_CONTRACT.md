# Sandbox Contract — what the sandbox is, and is not

## Three roles, not two

| Role | Job | Analogy | Code |
|------|-----|---------|------|
| **Red** | Invents and executes attacks from the KB | Attacker | `backend/red_team/` |
| **Sandbox** | The bank's **live environment**: holds state, runs control surfaces, adjudicates every action | Production defense *as it is right now* | `backend/sandbox/` |
| **Blue** | Learns **offline** from what happened, retrains, swaps the active model | Risk / model-ops team | `backend/blue_team/` |

**Sandbox ≠ Blue.** Blue does not sit in the loop deciding individual payments. The sandbox does.

## The five jobs the sandbox actually does

1. **Holds world state** — customers, devices, accounts, beneficiaries, merchants, prior
   attempts (`backend/sandbox/state.py`). The same customer tomorrow is not a blank slate;
   trust score, device age, and 24h velocity carry forward.
2. **Runs control surfaces** — KYC, device, auth, beneficiary, payment-init, gateway,
   acquirer, AML, mule/cash-out, GenAI context, risk, authorization, settlement
   (`backend/sandbox/engines/`, 15 engines) plus the KB-compiled rule set
   (`backend/sandbox/rules/`). Returns **ALLOW / CHALLENGE / BLOCK** (or PASS/FAIL for
   setup actions) **plus why**.
3. **Makes attacks falsifiable** — Red's claim "this vishing works" is *tested* against
   state + rules + ML + engines. Red never labels its own success.
4. **Produces evidence** — decision, reason, risk/ML/rule scores, `control_triggers`,
   and the full `journey` are emitted as one `SandboxObservation`
   (`backend/sandbox/schemas.py`) and written to the adversarial buffer. Without this,
   Blue has nothing real to learn from.
5. **Hosts the *active* model** — the sandbox's `RiskEngine` loads whatever FraudShield
   version is currently active (`backend/sandbox/sandbox.py::_try_load_fraudshield`).
   After Blue hardens and swaps, the next Red round hits a **harder world**.

## The loop

```text
Red attacks  →  Sandbox (live decide + state mutation)  →  evidence buffer
                      ↑                                        ↓
                      └────── Blue retrain / swap active model ─┘
```

Scores + decision + state change **are** the defense *in the moment*.
Blue is defense *improvement over time*.

If the sandbox merely echoed Red's own label, it would be an output box. It does not:
**Red proposes, the sandbox adjudicates, Blue adapts.**

## Non-goals

- Not a bank OS simulator. No real voice/SMS/call stack, no card network emulation.
- Not one ML model per attack scenario.
- Not a 100-capability GenAI ontology. The ontology stays at **15 capabilities**
  (`data/knowledge/canonical/genai/capabilities.json`); the work is making the **57 KB
  attack families executable**, not documenting more of them.

## Multi-surface execution (implemented)

Before Phase 2 the sandbox exposed 9 action types, of which only `initiate_payment` ran a
full multi-engine journey. 21 of 57 KB families were marked `sandbox_executable: false`
and pointed at `TPL-AGENTIC-NONEXEC`, a template with an **empty**
`supported_action_types` list — so agentic, social-engineering, KYC-deepfake and
open-banking-consent families could only be "executed" by forcing them through a payment
leg and scoring an agentic attack as a transaction.

Now: **7 adjudicated surfaces, 35 techniques, 57/57 families and 363/363 vectors
executable.** Each surface returns the same `SandboxObservation` shape, so Blue sees one
evidence stream.

### Two levels, not one: surface vs technique

A single coarse action per surface (`simulate_genai_context` for all agentic fraud) is
**not** operationally useful: it tells Blue nothing about *how* the attack worked, and it
cannot honestly adjudicate, because the KB assigns each family a **different control set**.
All 21 non-executable families have *distinct* `targeted_control_ids` — prompt injection is
CTL-0236/0237, memory poisoning is CTL-0240, agent-to-agent is CTL-0241. One handler
scoring all of them against one rule would be an output box again.

Equally, 30+ hand-written action handlers is the over-engineering this project is trying to
avoid. So the contract separates two levels:

| Level | Count | Purpose | Where it lives |
|-------|-------|---------|----------------|
| **`surface`** | 7 | Which control chain adjudicates. One handler each. | [surface_adjudicator.py](../backend/sandbox/surface_adjudicator.py) |
| **`action_type`** (technique) | 35 | What the attacker actually did. Red's routing key, Blue's label and report dimension. | [taxonomy/techniques.py](../backend/taxonomy/techniques.py) |
| **controls** | per family | Which specific controls must fire. | `targeted_control_ids` + 58 surface rules in `rules.json` |

Granular adjudication comes from **data, not code**: one handler per surface evaluates the
*family's own* `targeted_control_ids` through the compiled control set
(`rules/control_compiler.py`, `rules/rule_engine.py`) plus 58 surface rules targeting 53
distinct CTL ids. **7 handlers, 35 techniques, 21 distinct control verdicts.**

Adding a technique needs no new handler, enum member, or dispatch entry — only a row in
`techniques.py`. The orchestrator resolves a technique to its surface entry action and
merges its KB axes (family, rail, channel, payload defaults) into the payload.

Technique names are **derived from the KB, not invented** — the axes already exist:
`family_id` (57) × `rails` (upi, card, bank_transfer, crypto, wallet) × `channels`
(mobile_app, web, api, agent, voice) × `mutation_dimensions` (15). So
`initiate_crypto_conversion` is `initiate_payment` + `rail=crypto`; `execute_vishing_call`
is the auth_se surface + `channel=voice`; `poison_agent_memory` is family AG-003.

| Surface | Techniques (examples) | Engines | KB template |
|---------|----------------------|---------|-------------|
| `payment` | `initiate_card_payment`, `initiate_crypto_conversion`, `initiate_threshold_optimized_payment`, `initiate_mule_pass_through` | 15-engine chain | `TPL-MULE`, `TPL-AML`, … |
| `agent` | `inject_prompt_agent` (AG-001), `impersonate_agent` (AG-002), `poison_agent_memory` (AG-003), `inject_a2a_communication` (AG-004), `adapt_autonomous_fraud` (AG-005) | `genai_engine` + KB controls | `TPL-AGENT` |
| `auth_se` | `send_phishing_email` (AUTH-001), `execute_otp_social_engineering` (AUTH-002), `exploit_auth_recovery` (AUTH-003), `execute_vishing_call` (channel=voice) | `auth` + `genai_engine` | `TPL-AUTH-SE` |
| `kyc` | `submit_deepfake_biometric` (SEP-001), `submit_recovery_document_fraud` (ATO-001), `submit_synthetic_identity_onboarding` (ATO-002) | `kyc` + `genai_engine` | `TPL-KYC-GENAI` |
| `open_banking` | `request_broad_consent` (OB-001), `abuse_consent_scope_creep`, `replay_stolen_consent_token`, `register_malicious_tpp` (OB-002) | `consent` + `genai_engine` | `TPL-OB-CONSENT` |
| `device` | `deploy_remote_access_trojan` (RAT-001), `execute_automated_bot_interaction` (BOT-001), `evade_behavioral_biometrics` (BBE-001) | `session_integrity` + `genai_engine` | `TPL-SESSION` |
| `network` | `orchestrate_fraud_ring` (N-002), `coordinate_multi_stage_campaign` (N-003), `socially_engineer_aml_investigator` (AML-005) | `network` + graph signals | `TPL-NETWORK` |

A family flips to `sandbox_executable: true` only once its template has non-empty
`supported_action_types` **and** its own `targeted_control_ids` produce a real
ALLOW/CHALLENGE/BLOCK.

### Durable cross-surface state

Surfaces mutate state that later surfaces read — that is what a payment-only sandbox
cannot represent:

- accepted KYC evidence sets `verified` and raises `trust_score`, so a deepfake that
  passes makes every subsequent payment look legitimate
- memory poisoning permanently lowers an agent's `memory_integrity`, so a second attempt
  against the same agent starts from a weaker position
- a disclosed OTP lowers the victim's resistance to the next social-engineering attempt
- a granted consent persists, which is the only reason scope creep and token replay mean
  anything

### Attacker-controlled attack strength

The KB describes what a family is *capable* of; the payload describes how hard the
attacker is pushing on *this* attempt, and attacker values take precedence. Without that
precedence the capability profile pins every attempt to the same score, Red can never
trade strength for stealth, and Blue only ever sees blocked attacks. Measured boundary:

| Attack strength | agent | auth_se | kyc |
|---|---|---|---|
| 0.10 – 0.40 | ALLOW | ALLOW | ALLOW |
| 0.50 | CHALLENGE | ALLOW | ALLOW |
| ≥ 0.60 | BLOCK | BLOCK | BLOCK |

## Breadth asymmetry: dataset ⊃ KB ⊃ sandbox

The three layers do not cover the same ground, and the sandbox is the narrowest:

| Layer | Coverage | Artifact |
|-------|----------|----------|
| Baseline dataset | 67 attack families, 28 event types, 17 lifecycle stages, 15 taxonomies, 107,100 rows | `master_dataset.json` |
| Canonical KB | 57 families (all 57 also in the dataset), 363 vectors, 49 stages | `data/knowledge/canonical/` |
| Sandbox (before Phase 2) | **1 adjudicated event type** (payment), 9 actions, 36/57 families executable | `backend/sandbox/` |
| Sandbox (after Phase 2) | **7 adjudicated surfaces**, 35 techniques, 57/57 families and 363/363 vectors executable | `backend/sandbox/` |

Blue is trained on 28 event types (`consent_grant`, `video_kyc`, `auth_attempt`,
`protocol_message`, `tpp_onboarding`, `scope_access`, …). Before Phase 2, Red and the
sandbox generated only one of them, so the closed loop exercised a thin slice of the
model's own input space. The surfaces now emit `protocol_message`, `auth_attempt`,
`identity_verification` and `consent_grant` events, mapped onto the vocabulary the
baseline already uses.

Two consequences that constrain Phase 2:

1. **Reuse the dataset's vocabulary; never invent categories.** `master_dataset.json`
   already carries non-payment rails (`authentication`, `account_opening`, `data_access`,
   `protocol`, `token`, `device_session`) and matching event types. A new surface must emit
   values already present in `features_v3.json:categorical_mappings`. Inventing one (e.g.
   `transaction_type="control_surface"`) creates a category appearing only in adversarial
   rows — a perfect fraud tell that inflates metrics while detecting nothing. Non-feature
   diagnostics use the `meta_` prefix, per the dataset's own stated convention.
2. **10 dataset families are absent from the KB** (`MCH-001`–`006`, `PI-F001`–`004`), so
   "identify" has a documented gap that the generated data already covers.

## One line for judges

> The sandbox is the **live fintech defense environment** — multi-surface (agent, auth/SE,
> KYC, consent, payment), stateful, and hosting the currently-active FraudShield.
> Blue retrains from whatever bypassed it. Red re-attacks the hardened world.
> GenAI capabilities stay a small ontology; the KB families become **executable**,
> not just documented.
