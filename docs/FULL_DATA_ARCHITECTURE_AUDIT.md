# Payment Defense Twin — Full Data Architecture Audit

**Status:** pre-implementation audit. Implemented model and counts live in `docs/DATA_MODEL.md`.

**Scope:** inspect the existing repository, then propose a coherent data architecture *on top of* current work. Do not restart the project.

**How to read labels (mandatory):**

| Label | Meaning |
| --- | --- |
| **SOURCE-DERIVED** | Present in a taxonomy PDF, or copied from PDF-backed JSON without reinterpretation. |
| **EXISTING IMPLEMENTATION** | Present in current files, schemas, or running code. Observed, not assumed. |
| **PROPOSED** | Recommended next-state data model / storage / migration. Not implemented. |
| **INFERRED** | Reasonable conclusion from code or data, not an explicit source claim. Treat as hypothesis until verified. |

Related prior docs (EXISTING IMPLEMENTATION): `docs/KB_AUDIT.md`, `docs/KB_NORMALIZATION_REPORT.md`, `docs/FAMILY_ENRICHMENT_REPORT.md`, `docs/GENAI_CLASSIFICATION_REPORT.md`, `docs/PDF_TAXONOMY_MAP.md`. This audit supersedes those as the **data-architecture** source of truth; it does not replace their field-level extraction notes.

---

## A. Current architecture

### A.1 Conceptual product (EXISTING IMPLEMENTATION + user concept)

PAYMENT DEFENSE TWIN is an isolated synthetic payment-fraud laboratory.

| Side | Role today |
| --- | --- |
| **Knowledge Base** | Relatively stable attack/defense taxonomy loaded as JSON. |
| **Red Team** | Discovers families, plans campaigns, generates concrete sandbox actions, executes them, analyzes outcomes, stores in-process memory. |
| **Sandbox** | Mutable in-memory payment world: entities, rules, engines, FraudShield score, authorization. |
| **Blue Team** | Collects selected payment observations into an adversarial buffer, retrains FraudShield, evaluates v1 vs v2. |
| **Platform** | Loop runner, SQLite run log, API, scheduler. |

The *intended* domain split (PROPOSED, from product concept) is:

```text
15 TAXONOMY PDFs
        │
        ▼
 SOURCE EVIDENCE          ← knowledge, stable
        │
        ▼
  KNOWLEDGE BASE          ← families / variants / vectors / signals / controls / templates
        │
        ▼
     RED TEAM             ← plans + generates instances (not KB records)
        │
        ▼
     SANDBOX              ← mutable world state
        │
        ▼
   OBSERVATION            ← canonical immutable handoff
        │
   ┌────┴────┐
   ▼         ▼
RED MEMORY   EXPERIMENT STORE
             │
             ▼
      ADVERSARIAL BUFFER  ← curated, not every observation
             │
             ▼
      TRAINING DATASET    ← versioned mix of baseline + known fraud + buffer + hard negatives
             │
             ▼
        MODEL VERSION     ← FraudShield artifact + registry lineage
```

### A.2 What actually runs today (EXISTING IMPLEMENTATION)

```text
data/raw_pdfs/*.pdf
        │  (historical LLM extract: src/scripts/extract_knowledge_base.py)
        ▼
data/knowledge/attack_families.json
data/knowledge/attack_signals.json
data/knowledge/lifecycle_stages.json     ← LEGACY KB (runtime)
        │
        ├── KnowledgeLoader / OfflineKnowledge
        ├── /api/kb  and  backend/api/knowledge_api.py
        └── Red agents (threat_hunter, planner, campaign_builder, failure_analyzer, strategy)
                │
                ▼
        AttackPlan + ActionPayload (concrete amounts, IDs, timestamps)
                │
                ▼
        PaymentSandbox (in-memory SandboxState)
                │  rules + engines + FraudShield
                ▼
        SandboxObservation → dict (legacy response)
                │
        ┌───────┼───────────────┐
        ▼       ▼               ▼
  FailureAnalyzer  EvidenceCollector   CampaignEvent (SQLite, thin)
  MemoryAgent      evidence.jsonl
  (in-process)           │
                         ▼
                  HardeningTrainer
                  (master_dataset.json sample + buffer)
                         │
                         ▼
                  data/models/fraudshield_v2.txt
```

A **parallel canonical KB** already exists under `data/knowledge/canonical/` and is loaded only by `CanonicalKnowledgeLoader`. **No Red Team, Blue Team, Sandbox, API, or loop consumer uses it at runtime.** That loader is documented as intentionally separate so legacy behavior stays unchanged.

### A.3 What must not be mixed (PROPOSED domain law)

These seven domains must remain separate:

| Domain | Answers | Must not contain |
| --- | --- | --- |
| Knowledge Base | What we know about attacks, signals, controls, lifecycle | Transactions, scores, sandbox customers |
| Sandbox state | What is true right now | Taxonomy, training labels |
| Experiment / observation | What happened when we executed | Reusable attack definitions |
| Red memory | What Red learned in *this* environment | Long-term taxonomy |
| Adversarial buffer | Which executions are worth training on | The full experiment log |
| Training dataset | Exact rows used to train model X | Live sandbox state |
| Model registry | Which model is running and how it was trained | Fraud labels derived from scores |

---

## B. Current data objects

### B.1 Knowledge (taxonomy)

| Object | Status | Notes |
| --- | --- | --- |
| Attack family (legacy) | EXISTING IMPLEMENTATION | 57 records. Flat. Embeds signal objects and free-text controls. `genai_classification` is `PASS` / `PARTIAL`. |
| Attack family (canonical) | EXISTING IMPLEMENTATION | 57 records. IDs for stage/signals/controls. Four-way GenAI enum. Some identity fields filled; `maturity` null. |
| Attack family (enriched copy) | EXISTING IMPLEMENTATION | `attack_families_enriched.json`. PDF-field bleed into `objective` (null-byte / concatenated sections). **Do not treat as clean source.** |
| Attack variant | SOURCE-DERIVED as strings; missing as entity | Family `variants: string[]`. No `variant_id`. |
| Attack vector | Schema only | `attack_vector.schema.json` exists. **Zero vector records.** |
| Attack relationship | EXISTING IMPLEMENTATION (canonical only) | 526 edges: `occurs_at`, `observes`, `targets`. Other types unused. |
| Signal (legacy global) | EXISTING IMPLEMENTATION | 276 records, **no IDs**, no family FK. |
| Signal (canonical) | EXISTING IMPLEMENTATION | 276 records with `SIG-####`. Family links via `observable_signal_ids`. Empty `evidence`. |
| Control (canonical) | EXISTING IMPLEMENTATION | 342 records `CTL-####`. Deduped from stage+family strings. Empty `detects_signal_ids` and `evidence`. |
| Control (executable) | EXISTING IMPLEMENTATION | Sandbox rule classes + `EXECUTABLE_DEFAULTS` numeric thresholds. **Not the same object as KB controls.** |
| Lifecycle stage (legacy) | EXISTING IMPLEMENTATION | 58 records, `stage_name` + control name arrays. Duplicate names exist. |
| Lifecycle stage (canonical) | EXISTING IMPLEMENTATION | 49 stages after exact-name merge + one source-derived `Cross-stage / Network`. |
| Evidence / provenance | EXISTING IMPLEMENTATION (partial) | Family-level `EVD-<id>` plus field-level `EVD-SRC-*` on some canonical families. Page locators often null on the original 57. Source extractions have pages. |
| Simulation template | Schema only | No data file. |
| Simulation parameter | Missing | No schema file either. |
| Legitimate counterpart | Schema only | PDFs contain the concept (SOURCE-DERIVED in simulation tables). No registry. |
| GenAI capability registry | Missing | Classification lives *on the family*, not as a capability catalog. |
| Signal → feature mapping | Missing | Features exist in Blue code / `features.json`; signals exist in KB; they are not joined. |

### B.2 Runtime / experiment

| Object | Status | Notes |
| --- | --- | --- |
| Sandbox entity | EXISTING IMPLEMENTATION | Customer, device, account, merchant, beneficiary dataclasses. |
| Sandbox state | EXISTING IMPLEMENTATION | In-memory dicts + `transaction_log`. Not persisted. |
| Journey | EXISTING IMPLEMENTATION | `JourneyStep` list on `SandboxObservation`. |
| Action / payload | EXISTING IMPLEMENTATION | `ActionPayload` (concrete instance fields). |
| Attack instance | EXISTING IMPLEMENTATION (unnamed) | Generated payloads are instances. No `attack_instance_id`, no `vector_id`. |
| Observation | EXISTING IMPLEMENTATION (partial) | `SandboxObservation` + `to_legacy_response()`. Missing experiment/vector/model/environment IDs as first-class fields. |
| Experiment / campaign | EXISTING IMPLEMENTATION (fragmented) | `campaign_id` on payloads; `RedTeamState` in-process; SQLite `loop_runs` + `campaign_events`. |
| Control execution | EXISTING IMPLEMENTATION (unnamed) | `control_triggers: string[]` on observation / buffer. Not a typed execution record. |
| Red memory | EXISTING IMPLEMENTATION | `MemoryAgent` lists in RAM; optional ChromaDB. Lost on process exit. |

### B.3 Blue / ML

| Object | Status | Notes |
| --- | --- | --- |
| Feature vector | EXISTING IMPLEMENTATION | `FeatureBuilder.SANDBOX_FEATURES` + `features.json` `feature_order`. |
| Adversarial example | EXISTING IMPLEMENTATION | `EvidenceRecord` in `evidence.jsonl`. **Every payment is `label=1`.** No selection policy beyond “payment action”. |
| Baseline transactions | EXISTING IMPLEMENTATION | `data/baseline/baseline_transactions.csv` (~53,931 data rows). `is_fraud=0`. Also carries `attack_family` empty and `source_document` values. |
| Known fraud | EXISTING IMPLEMENTATION | `data/known_fraud/known_fraud.csv` (~53,166 data rows). `is_fraud=1`. Family IDs include values **not** in the 57-family KB (e.g. `PI-F003`). |
| Master dataset | EXISTING IMPLEMENTATION | `master_dataset.json` — what `train_model.py` and `HardeningTrainer` actually sample. |
| Training dataset version | Missing as object | Mix is implied by `features.json` `training_sources` (row counts, buffer families) not a dataset snapshot. |
| Model version / registry | EXISTING IMPLEMENTATION (partial) | Artifacts in `data/models/`. No first-class registry table. `features.json` is the closest spec. |
| Evaluation run | EXISTING IMPLEMENTATION (partial) | `model_metrics.json` (v1 leakage/metrics), `hardening_report.json` (v2 vs buffer). SQLite loop row stores some metrics. |

---

## C. Current files storing each object

### C.1 Source taxonomies (SOURCE-DERIVED)

| File | Object |
| --- | --- |
| `data/raw_pdfs/agent-commerce-11.pdf` | AG-001 … AG-005, GP-001, SIF-001 (IDs also appear in other PDFs) |
| `data/raw_pdfs/aml-14.pdf` | AML-001 … AML-006 |
| `data/raw_pdfs/aquirer-7.pdf` | ACQ-001 … ACQ-004 |
| `data/raw_pdfs/authentication-4.pdf` | AUTH-001 … AUTH-004, BBE-001 |
| `data/raw_pdfs/authorization-10.pdf` | AUT-001 … AUT-003 and overlapping IDs |
| `data/raw_pdfs/cash-out-13.pdf` | CM-001 … CM-004 |
| `data/raw_pdfs/device-session-3.pdf` | BBE-001, BOT-001, DFS-001, EFF-001, RAT-001 |
| `data/raw_pdfs/gateway-processor-8.pdf` | GP-001 … GP-007 |
| `data/raw_pdfs/KYC-1.pdf` | ATO-001, DII-001, GDF-001, SEP-001, SIF-001 |
| `data/raw_pdfs/merchant-6.pdf` | **PDF_TAXONOMY_MAP: no family IDs detected** |
| `data/raw_pdfs/network-15.pdf` | BOT-001, CM-003, EFF-001, N-001 … N-004 |
| `data/raw_pdfs/onboarding-2.pdf` | ATO-002, MDF-001, SIA-001 |
| `data/raw_pdfs/open-banking-12.pdf` | OB-001 … OB-006 and overlapping IDs |
| `data/raw_pdfs/payment-inititation-5.pdf` | **PDF_TAXONOMY_MAP: no family IDs detected** |
| `data/raw_pdfs/payment-rail-9.pdf` | AUTH-001 … AUTH-003, GP-005, R-001 |

Page-preserving extract: `data/knowledge/source_extractions/pages.json`.

**INFERRED:** `generate_dataset.py` still encodes `MCH-001…006` and `PI-F001…004` mapped to merchant and payment-initiation PDFs. Those IDs are **absent** from the 57-family runtime KB. Do not invent them into the KB; resolve from PDFs or mark dataset-only.

### C.2 Legacy KB (runtime)

| File | Records |
| --- | --- |
| `data/knowledge/attack_families.json` | 57 families (`generated_at` 2026-08-21) |
| `data/knowledge/attack_signals.json` | 276 signals |
| `data/knowledge/lifecycle_stages.json` | 58 stages |

### C.3 Canonical KB (not runtime)

| File | Contents |
| --- | --- |
| `canonical/attack_families.json` | 57 families, ID references |
| `canonical/attack_families_enriched.json` | Dirty enrichment copy |
| `canonical/signals.json` | 276 signals |
| `canonical/controls.json` | 342 controls |
| `canonical/lifecycle_stages.json` | 49 stages |
| `canonical/lifecycle_aliases.json` | legacy stage name → `STG-####` |
| `canonical/signal_aliases.json` | normalized signal name → `SIG-####` |
| `canonical/relationships.json` | 526 edges |
| `canonical/evidence.json` | evidence records |
| `canonical/normalization_metadata.json` | counts + 327 unresolved embedded-signal names |

### C.4 Extraction / review (not runtime)

| File | Role |
| --- | --- |
| `source_extractions/family_evidence.json` | Family → PDF pages |
| `source_extractions/evidence_candidates.json` | Field candidates (often concatenated) |
| `source_extractions/genai_classifications.json` | Per-family classification + locators |
| `source_extractions/families.json` | Intermediate extract |
| `review/family_review_queue.json` | 346 conflict items |

### C.5 Schemas (contracts, mostly empty of data)

`data/knowledge/schemas/`: `attack_family`, `attack_vector`, `signal`, `control`, `lifecycle_stage`, `relationship`, `evidence`, `simulation_template`, `legitimate_counterpart`.

**Missing schema files (PROPOSED):** attack variant, simulation parameter, signal-feature mapping, genai capability, observation, experiment, attack instance, red memory, training dataset, model version, evaluation run, control execution, sandbox entity.

### C.6 Sandbox / experiment / ML files

| File | Object |
| --- | --- |
| In-memory `SandboxState` | Current world |
| `orchestrator.execution_log` | Action log (process lifetime) |
| `data/platform.db` or `sqlite:///./data/platform.db` | `loop_runs`, `campaign_events`, `scheduler_config` |
| `data/adversarial_buffer/evidence.jsonl` | 17 `EvidenceRecord`s (current snapshot) |
| `data/baseline/baseline_transactions.csv` | Legitimate-labeled rows (~18.9 MB) |
| `data/known_fraud/known_fraud.csv` | Fraud-labeled rows (~20.7 MB) |
| `master_dataset.json` | Combined training source for v1/v2 trainer |
| `data/models/features.json` | Active model spec (currently points at v2 artifact in the inspected file) |
| `data/models/features_v1_backup.json`, `features_v2.json` | Versioned specs |
| `data/models/fraudshield_v1.txt`, `fraudshield_v2.txt` | LightGBM artifacts |
| `data/models/model_metrics.json` | v1 evaluation suite |
| `data/models/hardening_report.json` | v2 hardening summary |
| `data/test_platform.db` | Test SQLite |

---

## D. Current consumers

### D.1 Knowledge consumers

| Consumer | Loader | Files used | What it reads |
| --- | --- | --- | --- |
| `KnowledgeLoader` | legacy | three JSON files | families, signals, stages |
| Duplicate `src/knowledge/loader.py` | legacy | same | same (path may differ by cwd) |
| `OfflineKnowledge` | wraps `KnowledgeLoader` | same | Red Team facade |
| `ThreatHunter` | OfflineKnowledge | families | simulatable families → `Hypothesis` |
| `AttackPlanner` | OfflineKnowledge | family + stages + signals | `build_plan_from_family` |
| `kb_campaign_builder` | passed dicts | all three | pattern classification, payload hints, steps |
| `FailureAnalyzer` | OfflineKnowledge | family + global signals | map triggers → KB signal names |
| `StrategyLayer` | OfflineKnowledge | families | untested family queue |
| `LoopRunner` / `status_service` | OfflineKnowledge | stats | dashboard KB counts |
| `/api/kb` (`routes/knowledge.py`) | KnowledgeLoader | three files | REST, **legacy field names** |
| `knowledge_api.py` | KnowledgeLoader | three files | older FastAPI app |
| `CanonicalKnowledgeLoader` | canonical | families, signals, stages, controls | **unused at runtime** |
| `validate_canonical_knowledge.py` | canonical | six registries | referential integrity CLI |
| `validate_knowledge.py` | legacy | three files | shape validation |

`get_all_controls()` on `KnowledgeLoader` looks up `stage.get("stage")` but legacy records use `stage_name`. **EXISTING IMPLEMENTATION bug:** control map keys collapse to `"Unknown"`. API `LifecycleStageResponse` also names the field `stage`.

### D.2 Sandbox consumers

| Consumer | Data |
| --- | --- |
| `PaymentSandbox.execute` | action_type + payload → `SandboxObservation` |
| Engines (kyc, device, auth, account_merchant, payment_initiation, risk, authorization, settlement) | mutate/read `SandboxState` |
| Rule packs | executable thresholds from `control_registry.EXECUTABLE_DEFAULTS` |
| `RiskEngine` | rules + optional FraudShield |
| `SandboxClient` | converts observation → Red dict |

### D.3 Observation consumers (not one canonical object)

| Consumer | Shape it actually uses |
| --- | --- |
| FailureAnalyzer | legacy dict: `decision`, `journey`, `state`, `control_triggers` |
| EvidenceCollector | same dict + payload + plan; **payments only** |
| LoopRunner | writes thin `CampaignEvent` (family, decision, ml_score, amount) |
| MemoryAgent | `AnalysisResult` + hypothesis, not raw observation |
| Dashboard | loop_runs + campaign_events + buffer stats |

### D.4 Blue / training consumers

| Consumer | Inputs |
| --- | --- |
| `FeatureBuilder` | payment payload + `SandboxState` |
| `EvidenceBuffer` | JSONL append/read |
| `HardeningTrainer` | `master_dataset.json` sample + buffer export |
| `train_model.py` | `master_dataset.json` only (not the CSV pair directly) |
| `HardeningEvaluator` | v1/v2 artifacts + buffer features |
| `FraudShieldModel` | `features.json` + booster file |
| `AttackGenerator` | `BaselineLoader` on `baseline_transactions.csv` for amount/rail/MCC sampling |

### D.5 What Blue does **not** consume

Blue does **not** train on attack-family prose, PDF text, or KB descriptions. It trains on numeric/categorical **features** plus `is_fraud`. KB is used indirectly (Red chooses families; buffer stores `attack_family` as metadata, blocked from being a model feature).

---

## E. Missing data objects

Relative to the target architecture. “Missing” means no first-class, populated, referenced registry or store.

| Object | Schema exists? | Data exists? | Gap |
| --- | --- | --- | --- |
| AttackVariant | no | strings only | No IDs, provenance, or `variant_of` edges |
| AttackVector | yes | no | Executable spec not extracted; campaign builder invents sequences in Python |
| AttackInstance | no | yes, unnamed | Payloads are instances mixed with plans |
| SimulationTemplate | yes | no | Campaign shapes live in `PATTERN_KEYWORDS` |
| SimulationParameter | no | no | Amount/velocity/device mutations hardcoded |
| LegitimateCounterpart | yes | no | PDFs list counterparts; unused |
| StateRequirement | no | no | Prerequisites are free text |
| GenAICapability | no | partial on family | Need traditional / amplified / load-bearing *capabilities*, not a boolean |
| SignalFeatureMapping | no | no | Bridge ATTACK → SIGNAL → FEATURE → FraudShield |
| ControlExecution | no | trigger strings | Cannot audit “which KB control fired” |
| Canonical Observation | partial (`SandboxObservation`) | yes, incomplete | Not the single handoff object |
| Experiment store | partial (SQLite) | thin events | No vector_id, instance_id, state_before/after, full scores |
| RedMemory store | no (RAM) | process-local | Not environment-durable |
| TrainingDataset manifest | no | implied | Cannot reproduce “exactly what trained v2” |
| ModelRegistry | no | files | Lineage scattered across JSON artifacts |
| EvaluationRun | no | reports | Not linked as an entity to model + dataset |
| Hard-negative set | no | `meta_hard_negative` column on CSVs | Not a KB/simulation object |

Canonical family fields still often null (EXISTING IMPLEMENTATION, from normalization report / enrichment): `traditional_mechanism`, `genai_transformation`, `maturity`; some `attacker`/`target`; controls lack `detects_signal_ids`; signals/stages/controls lack per-record evidence.

---

## F. Missing relationships

Canonical relationships **present:** `occurs_at` (family→stage), `observes` (family→signal), `targets` (family→control).

Schema allows but **unused:** `mitigates`, `crosses`, `has_counterpart`, `implemented_by`.

**PROPOSED relationship types** (only when source or implementation evidence exists; do not fabricate):

| Type | From | To | Why |
| --- | --- | --- | --- |
| `variant_of` | variant | family | First-class variants |
| `instantiates` | vector | family/variant | Vector is not an instance |
| `uses_template` | vector | simulation template | Reuse |
| `parameterizes` | vector/template | parameter def | Shared mutation dims |
| `maps_to_feature` | signal | feature | Blue bridge |
| `implemented_by` | KB control | sandbox rule/engine | Semantic vs executable |
| `mitigates` | control | signal | Only if PDF/KB supports |
| `precedes` / `enables` / `composes_with` | family/vector | family/vector | Composite campaigns; PDF attack flows, not guessed |
| `has_counterpart` | vector | legitimate counterpart | Hard negatives |
| `derived_from` | instance | vector | Lineage |
| `produced` | observation | experiment | Audit |
| `selected_into` | observation | adversarial example | Curation |
| `trained_on` | model | dataset | Registry |
| `evaluated_by` | model | evaluation run | Registry |

**EXISTING IMPLEMENTATION gap:** 327 unique **embedded family signal names** did not match the 276 global signals (normalization metadata). Family `observable_signal_ids` therefore omit those names rather than inventing aliases.

---

## G. Current duplicated data

| Duplication | Where | Risk |
| --- | --- | --- |
| Two KBs | `data/knowledge/*.json` vs `canonical/` | Runtime ignores canonical; drift |
| Two family copies | canonical vs `attack_families_enriched.json` | Enriched file is contaminated |
| Two loaders | `KnowledgeLoader` vs `CanonicalKnowledgeLoader` | Plus duplicate `src/knowledge/loader.py` and two APIs |
| Signals twice | Embedded on legacy family + global `attack_signals.json` | Fuzzy name matching |
| Controls twice | Stage arrays, family `controls_targeted`, canonical registry, sandbox rule names | No ID join to executions |
| GenAI labels twice | Legacy `PASS`/`PARTIAL` vs canonical four-way enum | API still serves PASS/PARTIAL |
| Features twice | `train_model.py` CANDIDATE_FEATURES vs `FeatureBuilder.SANDBOX_FEATURES` vs `features.json` | Inference subset ≠ training set (`location_*` filled with defaults in trainer) |
| Training sources twice | CSV baseline/known_fraud vs `master_dataset.json` | Trainer samples JSON, generator samples CSV |
| Observation twice | `SandboxObservation` vs `to_legacy_response()` vs `EvidenceRecord` vs `CampaignEvent` | Four incompatible event shapes |
| Campaign IDs twice | `new_campaign_ids()` vs `RedTeamState.create_campaign` | Different ID schemes |
| Stage names many times | Free text, aliases, `STAGE_ALIASES` in control_registry, canonical IDs | String matching |

---

## H. Hardcoded data / logic

**Do not migrate this into the KB until the data model is stable** (product constraint). Documented here as EXISTING IMPLEMENTATION.

### H.1 `kb_campaign_builder.py`

- `PURE_AGENTIC` / `is_simulatable()` — drops `simulation_type == "agentic"` from sandbox campaigns.
- `PATTERN_KEYWORDS` — mule, merchant, identity, aml, velocity, account, auth.
- `STAGE_ACTION_HINTS` — action_type ↔ stage keywords.
- `SIGNAL_PAYLOAD_RULES` — regex → **concrete amounts** (9999, 35000, 8000, 2500), MCC `7995`/`5411`, PAN `SYN0009999`, trust `0.32`.
- Pattern **defaults** (35000 mule, 45000 merchant, structuring 9500, balances 75000, etc.).
- These are **synthetic sandbox heuristics**, not Mastercard production thresholds. Still: they are instance-level numbers living in Python, which the target architecture forbids inside **vectors**.

### H.2 Other Red code

- `AttackGenerator`: default PAN, trust 0.65, address, fingerprints, balances.
- `sandbox_client.py`: default `trust_score` 0.5.
- `failure_analyzer.py`: mutation suggestions (e.g. raise trust_score).
- `new_campaign_ids()`: synthesizes C_/D_/M_/BEN_/ACC_ IDs independent of sandbox population.

### H.3 Sandbox executable controls

`control_registry.EXECUTABLE_DEFAULTS`: amount tiers 25k/50k/100k, velocity 5/10, AML structuring 20k–24999, new-beneficiary 24h + 25k, device age 30 days, authz allow/challenge 0.30/0.60, etc.

**PROPOSED:** keep these in Sandbox config, not in KB control records.

### H.4 Dataset generator

`src/scripts/generate_dataset.py` hardcodes **67** family IDs including `MCH-*` and `PI-F*` and variant slug lists. This is a **second taxonomy** beside the 57-family JSON. Known-fraud CSV rows can cite families the KB does not contain.

### H.5 Blue labels

`EvidenceCollector._infer_label` always returns `1` for Red payment steps. FraudShield scores are **not** used as labels (correct). Selection is **not** “successful / diverse / near-boundary”; it is “all initiate_payment observations.”

---

## I. Proposed canonical data model

Logical KB (JSON first). **PROPOSED.** Physical folder layout can stay under `data/knowledge/canonical/` with additional files; a later `attacks/`, `defense/`, `lifecycle/`, `simulation/`, `genai/`, `evidence/` split is optional and must not break loaders.

```text
knowledge/
├── attacks/
│   ├── attack_families
│   ├── attack_variants
│   ├── attack_vectors
│   └── attack_relationships
├── defense/
│   ├── signals
│   ├── controls
│   └── signal_feature_mappings
├── lifecycle/
│   └── lifecycle_stages
├── simulation/
│   ├── simulation_templates
│   ├── parameters
│   ├── state_requirements
│   └── legitimate_counterparts
├── genai/
│   └── capabilities
└── evidence/
    └── evidence
```

### I.1 AttackFamily (concept)

Answers: *What category/mechanism is this?*

Keep current canonical identity (`attack_id`, `name`, variants as **references** not only strings, `objective`, `attacker`, `target`, `prerequisites`, `traditional_mechanism`, `attack_flow`, `simulation_type`, `observable_signal_ids`, `targeted_control_ids`, `evidence_ids`, `confidence`, `maturity`).

**PROPOSED GenAI object** (replace opaque PASS/PARTIAL; already partly on canonical family):

```text
genai.classification: traditional | genai_amplified | genai_load_bearing | unknown
genai.load_bearing: true | false | null
genai.transformation: string | null
genai.capability_ids: [CAP-...]
```

Do **not** reduce to `is_genai: boolean`.

Null if PDF does not support the field. Conflicts go to the review queue. **Do not promote `attack_families_enriched.json` until field extraction is cleaned.**

### I.2 AttackVariant

Meaningful variation of a family (SOURCE-DERIVED from family `variants` and PDF variant lists).  
`variant_id`, `family_id`, `name`, `origin` (`source_backed` | `implementation_derived`), `evidence_ids`.  
Do not mint variants to inflate counts.

### I.3 AttackVector vs AttackInstance (critical)

| | Vector (KB) | Instance (runtime) |
| --- | --- | --- |
| Meaning | Executable *specification* | One generated execution |
| Amount | Parameter ref / mutation strategy | ₹47,912 at T1 |
| Customer | Required-state role | C001 |
| Storage | JSON KB | Experiment / generator output |
| Cardinality | Hundreds, source- or implementation-backed | Tens/hundreds of thousands |

Vector **PROPOSED** fields: `vector_id`, `family_id`, `variant_id`, `objective`, lifecycle IDs, rails/channels, prerequisites, `required_state`, ordered `actions` (types + parameter refs, **not** concrete amounts), attacker-controlled parameters, mutation dimensions, `simulation_template_id`, expected signals, targeted controls, success/failure conditions, counterpart IDs, evidence.

**Do not randomly generate vectors.** Path: PDFs → families → variants → mechanisms → state requirements → templates → vectors. Implementation-derived vectors (from campaign builder) must be flagged as such.

### I.4 Signal, Control, Stage

Keep canonical IDs. Reference by ID. Do not copy full signal objects onto every family.

**Control (KB)** = semantic defense (“velocity monitoring”).  
**Control (Sandbox)** = executable rule + synthetic threshold.  
Join later via `implemented_by`, not by stuffing thresholds into the KB.

### I.5 SimulationTemplate / Parameter / Counterpart

Templates: required entities, required state, action types, parameter refs, constraints, edge cases. Reusable.

Parameters: type, legitimate source (baseline distribution **reference**, not a copied million rows), mutation strategies, attacker-controllable flag, related feature/signal IDs. No invented production Mastercard limits.

Counterparts: suspicious pattern vs lookalike legitimate behavior for hard negatives.

### I.6 Non-KB proposed objects

See `docs/DATA_DICTIONARY.md`. Summary:

- **SandboxEntity / SandboxState** — mutable; PostgreSQL later; in-memory OK now.
- **Observation** — one immutable handoff (experiment_id, campaign_id, vector_id, instance_id, state_before/after, features, signals, controls, rule/ML/graph/behavior, unified risk, decision, outcome, model_version, environment_version).
- **Experiment** — campaign grouping; auditable.
- **RedMemory** — environment-specific; not taxonomy.
- **AdversarialExample** — curated subset of observations.
- **TrainingDataset** — versioned snapshot/manifest.
- **ModelVersion / EvaluationRun** — lineage.

---

## J. Proposed storage model

**PROPOSED.** Do not move everything into one database.

| Store | Holds | Today |
| --- | --- | --- |
| **JSON** | KB, schemas, source-derived static knowledge | Yes (legacy + canonical) |
| **SQLite now / PostgreSQL later** | Sandbox persistence (optional), experiments, observations, red memory, model registry metadata, loop runs | Only loop_runs / campaign_events / scheduler |
| **CSV / Parquet** | Baseline, known fraud, adversarial exports, training/eval feature tables | CSV + giant JSON |
| **JSONL** | Append-only observations / buffer (acceptable MVP) | Buffer only |
| **Model files** | Boosters | `.txt` LightGBM |
| **Vector index (optional)** | Evidence / red-memory retrieval | Chroma optional, unused in default loop |
| **Redis** | Campaign hot state | Unused |

**PROPOSED MVP:** keep KB as JSON; expand SQLite tables for Observation/Experiment/RedMemory/ModelRegistry **without** rewriting the loop in the first coding phase; keep CSV/JSONL for ML.

---

## K. Data flow: PDF → KB → Red → Sandbox → Observation → Blue

### K.1 As implemented (EXISTING IMPLEMENTATION)

```text
15 PDFs
  │  extract_knowledge_base.py (LLM, historical)
  ▼
Legacy three JSON files  ─────────────────────────────┐
  │                                                     │
  │  build_canonical_knowledge.py                       │
  ▼                                                     │
Canonical registries (unused at runtime)                │
  │                                                     │
  │  extract_family_evidence.py → messy candidates      │
  │  enrich_canonical_families.py → enriched JSON       │
  ▼                                                     │
Review queue (346 conflicts)                            │
                                                        │
OfflineKnowledge ◄──────────────────────────────────────┘
  │
ThreatHunter → Hypothesis (family_id)
  │
AttackPlanner + kb_campaign_builder
  │  hardcoded patterns + concrete payload numbers
  ▼
AttackPlan (steps, payload_template)
  │
AttackGenerator + BaselineLoader (CSV amount/rail noise)
  ▼
ActionPayload  == de facto AttackInstance
  │  new synthetic customer/device IDs each campaign
  ▼
SandboxOrchestrator.execute
  │  KYC → Device → Auth → Payment Initiation → Risk(rules+ML) → Authz → Settlement
  │  mutates SandboxState; appends transaction_log
  ▼
SandboxObservation → legacy dict
  │
  ├─ FailureAnalyzer → AnalysisResult → MemoryAgent (RAM)
  ├─ EvidenceCollector (if initiate_payment) → evidence.jsonl  label=1
  └─ LoopRunner → campaign_events row
  │
HardeningTrainer: sample master_dataset.json + buffer features
  ▼
fraudshield_v2 + features_v2.json
  │  optional swap into features.json
  ▼
Sandbox RiskEngine uses active FraudShield
```

### K.2 Target flow (PROPOSED)

```text
PDFs → Evidence (page/section, field, confidence)
     → Families / Variants / Signals / Controls / Stages / Relationships
     → Simulation templates + parameters (source or implementation_derived)
     → Attack vectors (no concrete ₹ / timestamps)
            │
Red planner selects vector (+ optional Red memory)
            │
Generator: vector + sandbox state + baseline distributions + mutations
            │
Attack instance (concrete)
            │
Sandbox engines + KB-mapped controls + features + FraudShield
            │
Canonical Observation (immutable)
            │
     ┌──────┼──────────────┐
     ▼      ▼              ▼
Red memory  Experiment     Curation policy
                           ▼
                    Adversarial buffer
                           ▼
              Training dataset vN (baseline + known fraud
                 + selected adv + hard negatives)
                           ▼
                    ModelVersion vN
                           ▼
                    EvaluationRun → deploy or reject
```

---

## L. Training data lineage

### L.1 Current (EXISTING IMPLEMENTATION)

**FraudShield v1 (`train_model.py`):**

1. Load `master_dataset.json` → `transactions`.
2. Leakage audit on candidate features (block `attack_family`, ids, `meta_*`).
3. Time-based split; train LightGBM/XGBoost.
4. Write `data/models/fraudshield_v1.txt` + `features.json` + `model_metrics.json`.

**FraudShield v2 (`HardeningTrainer`):**

1. Sample 4000 legit + 4000 fraud from **the same** `master_dataset.json` (not directly from the two CSVs).
2. Convert **all** buffer payment rows (`label=1`) to feature rows.
3. Concatenate, shuffle, 15% val.
4. Encode with v1 categorical mappings extended.
5. Write `fraudshield_v2.txt` + `features_v2.json`.
6. `hardening_report.json`: inspected run used **17 buffer rows**, all **blocked**, families AML-001/002/003/004/006, `val_pr_auc` ≈ 0.851.
7. Inspected `features.json` currently names `fraudshield_v2.txt` as `model_file` with `training_sources.buffer_rows: 17`.

**CSV pair:** `baseline_transactions.csv` (`is_fraud=0`) and `known_fraud.csv` (`is_fraud=1`) share the same column schema (including `attack_family`, `meta_hard_negative`, `meta_evasion_level`). Red `BaselineLoader` uses the legit CSV for **sampling distributions**, not for v2 training.

**Gap:** no dataset_version ID, no frozen snapshot of the 8017 v2 rows, no hard-negative KB objects, no “select bypasses only” filter (buffer was 0 bypassed / 17 blocked in the inspected hardening report).

### L.2 Target (PROPOSED)

```text
source PDF
  → evidence → family → variant → vector
  → instance → experiment → observation
  → (optional) adversarial example
  → training dataset version
  → model version
  → evaluation run
```

Initial train: legitimate baseline + known fraud → features → v1.  
Later: same + **selected** adversarial + hard negatives → v2.  
Do not put FraudShield scores back into the KB as ground truth.  
Do not retrain after every single attack.

---

## M. Model lineage

### M.1 Current artifacts (EXISTING IMPLEMENTATION)

| Artifact | Role |
| --- | --- |
| `fraudshield_v1.txt` | v1 booster |
| `fraudshield_v2.txt` | v2 booster |
| `features.json` | **Active** spec (model_file, feature_order, mappings, training_sources, threshold) |
| `features_v1_backup.json` | Prior v1 spec |
| `features_v2.json` | v2 spec |
| `model_metrics.json` | Multi-model comparison from `train_model.py` (majority, stump, tree, logreg, XGBoost, LightGBM) |
| `hardening_report.json` | Buffer mean-score lift / val AUCs |
| SQLite `loop_runs` | v1/v2 buffer means, score_lift, recommend_swap, val metrics per loop |

Missing: `parent_model_version` as a registry row (v2 spec has `parent_version` field in features.json), feature_version ID, dataset_version ID, evaluation_run_id FK, deployment status enum distinct from “whichever file features.json points at”.

### M.2 Proposed registry fields (PROPOSED)

`model_version`, `dataset_version`, `feature_version`, `training_config`, `algorithm`, `metrics`, `evaluation_run_id`, `deployment_status`, `created_at`, `parent_model_version`, `artifact_path`.

The **model file is the artifact**. The registry is metadata/lineage only.

---

## N. Migration plan

**Constraint:** freeze legacy files; do not delete; do not rewrite Red/Blue loop in one step; do not migrate campaign builder to vectors until the model is reviewed.

| Phase | Work | Out of scope |
| --- | --- | --- |
| **0 — this audit** | Documents only | Code |
| **1 — stabilize KB contracts** | Align schemas to family/variant/vector/parameter/mapping/observation; keep JSON | Runtime switch |
| **2 — clean source fields** | Fix PDF field segmentation; promote only clean values; keep review queue; **do not** use enriched JSON as-is | Inventing nulls |
| **3 — first-class variants + evidence** | Promote source-backed variant strings to records; attach evidence IDs already known | New families |
| **4 — simulation layer** | Parameter defs + templates **copied from code heuristics**, marked `implementation_derived` | Changing generated attack behavior |
| **5 — vectors** | One reviewed vector per simulatable family/variant where flow+template exist; still unused by generator | Random vector mill |
| **6 — compatibility adapter** | `CanonicalKnowledgeLoader` projects **legacy shape** for OfflineKnowledge; feature-flag | Big-bang API break |
| **7 — observation contract** | Add fields to `SandboxObservation` / persist JSONL; keep `to_legacy_response()` | Dropping dict consumers |
| **8 — experiment + red memory stores** | SQLite tables; MemoryAgent flush | PostgreSQL mandate |
| **9 — buffer curation + dataset manifests** | Selection criteria; versioned parquet/jsonl; trainer reads manifest | Retrain every attack |
| **10 — model registry** | Write registry JSON/SQLite on train/swap | New algorithm |
| **11 — optional** | Point planner at vectors; retire hardcoded amounts from Python into parameter refs | Rewriting sandbox rules |

**Compatibility rule:** legacy `attack_families.json` remains the runtime default until phase 6 is proven by existing tests (`test_red_team_dynamic_kb`, `test_sandbox_with_kb`, `test_evidence_buffer`, `test_platform`).

---

## O. Risks

| Risk | Label | Mitigation |
| --- | --- | --- |
| Switching field names (`lifecycle_stage` vs `lifecycle_stage_id`) breaks Red/API | EXISTING IMPLEMENTATION | Adapter; tests first |
| `get_all_controls` / API `stage` key mismatch | EXISTING IMPLEMENTATION | Fix only with regression tests |
| Enriched families contain concatenated PDF text and `\u0000` | EXISTING IMPLEMENTATION | Do not merge into canonical without cleaning |
| 346 “conflicts” are mostly greedy extract vs already-good legacy strings | INFERRED | Prefer legacy values; review queue is not a todo to overwrite |
| 327 unmatched embedded signals | EXISTING IMPLEMENTATION | Leave unlinked; human alias workflow |
| merchant/payment-initiation PDFs vs MCH/PI-F dataset IDs | EXISTING IMPLEMENTATION | Do not add families without PDF IDs |
| Hardcoded amounts become “KB vectors” that look like instances | PROPOSED risk | Parameters + distributions, not ₹49721 on the vector |
| Training on all blocked attacks (current buffer) | EXISTING IMPLEMENTATION | Curation policy in phase 9 |
| `master_dataset.json` vs CSV drift | INFERRED | Manifest must name the actual file used |
| Canonical loader unused → canonical rot | EXISTING IMPLEMENTATION | Phase 6 or stop writing unused files |
| Putting sandbox customers into KB | Product risk | Domain law in section A.3 |
| Using ML score as fraud label | Product risk | Already avoided in collector; keep it that way |
| One-shot rewrite of loop + KB | Product risk | Phases 0–11 |

---

## P. Recommended implementation phases

After you review this audit (no code until then):

1. **Approve domain boundaries** in A.3 and vector vs instance in I.3.
2. **Phase 1–2:** schemas + clean extraction (data only).
3. **Phase 3–5:** populate variants, parameters, templates, a **small** vector set, marked origin.
4. **Phase 6:** compatibility loader; loop still unchanged in behavior.
5. **Phase 7–10:** observation/experiment/registry **storage** around the existing loop.
6. **Phase 11:** only then stop hardcoding campaign knowledge in Python.

**Immediate non-goals:** random family generators; millions of KB rows; PostgreSQL-for-everything; deleting legacy JSON; retraining FraudShield as part of the data-model change; rewriting `loop_runner.py`.

---

## Appendix 1 — PDF family page pattern (SOURCE-DERIVED)

Inspected via `source_extractions/pages.json` (agent-commerce-11.pdf). Each family typically has:

- **A. Identity:** Attack ID, name, variants, primary lifecycle stage, cross-stage stages, attacker, target, objective, agentic mechanism.
- **B. Fraud understanding:** narrative, traditional equivalent, GenAI/agentic transformation table, load-bearing rationale, HARD test, prerequisites, conceptual flow, trust boundary, payment consequence.
- **C. Agentic characteristics**
- **D. Detection intelligence:** signal table (category, observable, why, method, FP risk)
- **E. Simulation intelligence:** components, variant/mutation parameters, **legitimate counterpart**, edge cases, simulation type
- **F. Evidence:** claim, publisher, date, type, confidence, maturity

The flattened legacy JSON keeps a subset (id, name, variants, one stage string, PASS/PARTIAL, simulation_type, prerequisites, flow, some signals, control strings, confidence). **That is why enrichment is incomplete, not because the PDFs lack structure.**

## Appendix 2 — Canonical 57 family IDs (EXISTING IMPLEMENTATION)

AG-001…005, AML-001…006, ACQ-001…004, AUTH-001…004, AUT-001…003, CM-001…004, DFS-001, EFF-001, RAT-001, BOT-001, BBE-001, GP-001…007, SIF-001, GDF-001, DII-001, SEP-001, ATO-001, N-001…004, SIA-001, MDF-001, ATO-002, OB-001…006, R-001.

## Appendix 3 — Open questions (do not assume)

1. Should `MCH-*` / `PI-F*` exist in the KB after a **manual PDF read** of merchant-6 and payment-inititation-5, or only in historical datasets?
2. Is `master_dataset.json` a frozen export of the two CSVs, or a third generator output? (Trainer and `train_model.py` depend on it.)
3. Should agentic-only families stay non-simulatable until sandbox actions exist, or get non-payment vectors?
4. Who owns review-queue resolution (human vs later extraction fix)?

---

*End of audit. Companion: `docs/DATA_DICTIONARY.md`.*
