# Payment Defense Twin — Canonical Data Model

This document is the data-architecture source of truth after the 2026-08-25 modeling pass.

It supersedes `docs/FULL_DATA_ARCHITECTURE_AUDIT.md` as the **implemented** model.
The audit remains useful as the pre-implementation inspection record.
Companion object dictionary: `docs/DATA_DICTIONARY.md`.
PostgreSQL DDL (later): `docs/sql/payment_defense_twin_schema.sql`.

Interactive summary: open the architecture canvas beside chat.

---

## Domain law (do not mix)

| Domain | Answers | Storage now | Later |
| --- | --- | --- | --- |
| Knowledge Base | What we know about attacks, signals, controls, lifecycle, simulation | JSON under `data/knowledge/canonical/` | `kb_*` tables |
| Sandbox state | What is true **right now** | In-memory `SandboxState` | `sandbox_*` tables |
| Experiment / observation | What happened when we executed | SQLite `campaign_events` (thin) + `SandboxObservation` | `experiments`, `observations` |
| Red memory | What Red learned in **this** environment | `MemoryAgent` RAM / optional Chroma | `red_memory` |
| Adversarial buffer | Which executions are worth training on | `data/adversarial_buffer/evidence.jsonl` | `adversarial_examples` |
| Training dataset | Exact mix used to train model X | reconstructed `data/models/training_dataset_manifest.json` | `training_datasets` |
| Model registry | Which model is running and how it was trained | `data/models/model_registry.json` + artifact files | `model_versions` |

A FraudShield **score is an output**, never a fraud label, never KB ground truth.

---

## What was kept

- 57 PDF-backed attack families (legacy + canonical). No new families invented.
- 276 signals, 49 lifecycle stages, 342 controls, existing evidence and `occurs_at` / `observes` / `targets` edges.
- Legacy runtime files frozen: canonical only at `data/knowledge/canonical/`. `KnowledgeLoader` hydrates runtime aliases in memory.
- `KnowledgeLoader` / Red Team / loop read canonical via `KnowledgeLoader` (runtime aliases hydrated in memory).
- Dirty `attack_families_enriched.json` was **not** promoted.
- `MCH-*` and `PI-F*` remain **dataset-only**, in `data/knowledge/review/dataset_only_families.json`, because those IDs were not extracted from merchant-6 / payment-inititation-5 PDFs.

---

## Canonical layout (JSON, PostgreSQL-shaped)

```text
data/knowledge/canonical/
├── catalog.json
├── attacks/
│   ├── attack_families.json
│   ├── attack_variants.json
│   ├── attack_vectors.json
│   └── attack_relationships.json
├── defense/
│   ├── signals.json
│   ├── controls.json
│   └── signal_feature_mappings.json
├── lifecycle/
│   └── lifecycle_stages.json
├── simulation/
│   ├── simulation_templates.json
│   ├── parameters.json
│   ├── state_requirements.json
│   └── legitimate_counterparts.json
├── genai/
│   └── capabilities.json
└── evidence/
    └── evidence.json
```

The nested tree is the only on-disk KB. Duplicate flat copies at `canonical/*.json` were removed. Duplicate runtime JSON files at `data/knowledge/` were removed; `KnowledgeLoader` projects compatibility aliases in memory for Red Team and the API.

---

## Implemented registry counts

From `catalog.json`:

| Object | Count | Origin |
| --- | ---: | --- |
| Attack families | 57 | source-backed |
| Attack variants | 363 | 282 source-backed family strings + 81 dataset-generator names for those same 57 families (`implementation_derived`) |
| Attack vectors | 363 | one specification per variant; **no** concrete ₹ / timestamps |
| Signals | 276 | source-backed |
| Controls | 342 | source-backed names; no invented production thresholds |
| Lifecycle stages | 49 | source-backed |
| Relationships | 2096 | original 526 plus variant_of / instantiates / uses_template / has_counterpart / maps_to_feature / implemented_by |
| Evidence | 388 | existing family + field evidence |
| Simulation templates | 9 | implementation-derived from campaign-builder patterns |
| Simulation parameters | 14 | implementation-derived reusable dimensions |
| Legitimate counterparts | 5 | implementation-derived hard-negative patterns |
| GenAI capabilities | 15 | catalog; attached to families by identity keywords, not `is_genai` |
| Signal → feature mappings | 151 | implementation-derived keyword bridge to FraudShield features |
| Dataset-only family IDs | 10 | review only |

GenAI on families is **four-way**: 37 `genai_load_bearing`, 20 `genai_amplified`, 0 traditional, 0 unknown (canonical source-section classifier). Nested as:

```text
genai.classification
genai.load_bearing
genai.transformation
genai.capability_ids
```

Flat `genai_classification` / `genai_load_bearing` are retained for compatibility.

---

## Vector vs instance (critical)

| | Vector (KB) | Instance (runtime) |
| --- | --- | --- |
| Meaning | How to instantiate this variant | One generated execution |
| Amount | `PAR-AMOUNT` + mutation strategy | ₹47,912 at T1 |
| Customer | required-state role | C001 |
| Storage | `attack_vectors.json` | experiment / generator output |
| Cardinality | 363 specifications | tens/hundreds of thousands via parameters × sandbox state |

Diversity is **not** millions of KB rows. It is:

```text
57 families
× 363 variants/vectors
× rails / channels listed on the vector
× parameter mutation strategies
× current sandbox state
```

---

## GenAI model

Do not reduce to `is_genai: true/false`.

| Class | Meaning |
| --- | --- |
| `traditional` | Mechanism works without GenAI |
| `genai_amplified` | Traditional mechanism remains; GenAI increases scale, realism, personalization, adaptability |
| `genai_load_bearing` | GenAI/agent mechanism is fundamental |
| `unknown` | Evidence insufficient |

Capabilities (`CAP-0001` … `CAP-0015`) are reusable: synthetic content, personalization, scale, adaptive evasion, deepfake, voice cloning, document forgery, agentic planning, tool use, prompt injection, memory poisoning, social-engineering generation, model evasion, network orchestration, biometric synthesis.

---

## What Blue uses from the KB

Blue does **not** train on family prose.

Bridge:

```text
ATTACK → observable_signal_ids → SIGNAL → signal_feature_mappings → FraudShield features
```

Training mix remains:

1. v1: legitimate baseline + known fraud
2. v2: same + **selected** adversarial examples + hard negatives

Current trainer still uses all buffer payment rows; the **target** selection policy is documented, not yet enforced. Manifest: `data/models/training_dataset_manifest.json`.

---

## Compatibility / migration

| Phase | Status |
| --- | --- |
| Stabilize contracts + populate canonical KB | **done** |
| Keep legacy loader as runtime default | **done** |
| `CanonicalKnowledgeLoader` + `to_legacy_family()` adapter | **done** |
| Do not rewrite `kb_campaign_builder` onto vectors yet | **held** (hardcoded amounts stay in Python until planner is switched) |
| Observation / experiment / Red memory SQLite expansion | **schema ready**, not wired into the loop |
| PostgreSQL load of `kb_*` | **DDL ready**, not executed |
| Point generator at vectors + baseline distributions | **next**, after this model is accepted |

Rebuild command:

```text
python scripts/build_complete_knowledge_model.py
python scripts/validate_canonical_knowledge.py
```

---

## What we will not do

- Randomly invent attack families
- Store generated transactions in the KB
- Train ML on attack descriptions
- Put FraudShield scores into the KB as labels
- Put sandbox customers into the KB
- Treat controls and control executions as the same object
- Treat vectors as instances
- Fabricate PDF page numbers
- Invent production Mastercard thresholds
- Delete legacy JSON
- Rewrite Red/Blue/Sandbox in one step
