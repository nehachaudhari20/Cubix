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

## Multi-surface requirement (current gap)

The sandbox currently exposes 9 action types, of which only `initiate_payment` runs a
full multi-engine journey. 21 of 57 KB families are marked
`sandbox_executable: false` and point at `TPL-AGENTIC-NONEXEC`, a template with an
**empty** `supported_action_types` list — so agentic, social-engineering, KYC-deepfake and
open-banking-consent families can only be executed by forcing them through a payment leg.

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
| **`surface`** | 6 | Which control chain adjudicates. One handler each. | orchestrator dispatch |
| **`action_type`** (technique) | ~30 | What the attacker actually did. Red's routing key, Blue's label and report dimension. | KB-derived |
| **controls** | per family | Which specific controls must fire. | `targeted_control_ids`, already KB-compiled |

Granular adjudication comes from **data, not code**: one handler per surface evaluates the
*family's own* `targeted_control_ids` through the existing compiled control set
(`rules/control_compiler.py`, `rules/rule_engine.py`). 6 handlers, ~30 techniques,
21 distinct control verdicts.

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
| `open_banking` | `request_broad_consent` (OB-001), `register_malicious_tpp` (OB-002) | `authorization` + `genai_engine` | `TPL-OB-CONSENT` |
| `network` | `orchestrate_fraud_ring` (N-002), `coordinate_multi_stage_campaign` (N-003) | `aml` + graph signals | `TPL-NETWORK` |

A family flips to `sandbox_executable: true` only once its template has non-empty
`supported_action_types` **and** its own `targeted_control_ids` produce a real
ALLOW/CHALLENGE/BLOCK.

## Breadth asymmetry: dataset ⊃ KB ⊃ sandbox

The three layers do not cover the same ground, and the sandbox is the narrowest:

| Layer | Coverage | Artifact |
|-------|----------|----------|
| Baseline dataset | 67 attack families, 28 event types, 17 lifecycle stages, 15 taxonomies, 107,100 rows | `master_dataset.json` |
| Canonical KB | 57 families (all 57 also in the dataset), 363 vectors, 49 stages | `data/knowledge/canonical/` |
| Sandbox | **1 adjudicated event type** (payment), 9 actions, 36/57 families executable | `backend/sandbox/` |

Blue is trained on 28 event types (`consent_grant`, `video_kyc`, `auth_attempt`,
`protocol_message`, `tpp_onboarding`, `scope_access`, …) while Red and the sandbox generate
only one of them. The closed loop exercises a thin slice of the model's own input space.

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
