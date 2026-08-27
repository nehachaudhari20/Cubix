# Payment Defense Twin — Data Dictionary

Companion to `docs/FULL_DATA_ARCHITECTURE_AUDIT.md`.

**Status:** object dictionary. Implemented layout and live counts: `docs/DATA_MODEL.md`. Variants, vectors, templates, parameters, GenAI capabilities, and signal-feature mappings now exist as canonical JSON.

**Labels:** **SOURCE-DERIVED** · **EXISTING IMPLEMENTATION** · **PROPOSED** · **INFERRED**

**Domain flags used below**

| Flag | Meaning |
| --- | --- |
| Source knowledge | Stable taxonomy / reusable concepts. KB. |
| Runtime data | Mutable world, executions, scores, models. Not KB. |
| ML training? | Whether rows of this object may enter FraudShield training. A model *score* is never a label. |

---

## How to use this dictionary

Each object answers:

1. What is it?
2. Who creates it?
3. Who reads it?
4. Where does it live?
5. Is it knowledge or runtime?
6. Can Blue train on it?

If two objects share a name in code (e.g. “evidence”), both senses are listed.

---

## AttackFamily

| Field | Value |
| --- | --- |
| **Object name** | AttackFamily |
| **Purpose** | Concept-level attack category / mechanism. Answers: “what kind of attack is this?” |
| **Source** | **SOURCE-DERIVED** from 15 taxonomy PDFs (identity tables). **EXISTING IMPLEMENTATION:** 57 records in legacy + canonical JSON. |
| **Owner** | Knowledge Base (taxonomy). Not Red, not Sandbox. |
| **Consumers** | **EXISTING:** `KnowledgeLoader`, `OfflineKnowledge`, ThreatHunter, AttackPlanner, `kb_campaign_builder`, FailureAnalyzer, StrategyLayer, `/api/kb`, loop status. **Unused:** `CanonicalKnowledgeLoader`. |
| **Lifecycle** | Created by PDF extraction; normalized to canonical; rarely edited. Enrichment must not overwrite with concatenated PDF bleed. |
| **Storage** | **EXISTING:** `data/knowledge/attack_families.json` (legacy, runtime); `data/knowledge/canonical/attack_families.json`. **PROPOSED:** `knowledge/attacks/attack_families`. JSON. |
| **Primary key** | `attack_id` (e.g. `AG-001`, `AML-001`). |
| **Foreign keys / references** | **EXISTING canonical:** `lifecycle_stage_id`, `cross_stage_lifecycle_stage_ids[]`, `observable_signal_ids[]`, `targeted_control_ids[]`, `evidence[]` IDs. **PROPOSED:** `variant_ids[]`, `vector_ids[]` (or reverse FKs), `genai.capability_ids[]`. |
| **Mutable / immutable** | Treat as **immutable** after review. Corrections via versioned KB release, not per experiment. |
| **ML training?** | **No.** Descriptions are not training rows. Family ID on a transaction is **blocked** as a model feature (`train_model.py` `BLOCKED_EXACT`). |
| **Knowledge vs runtime** | **Source knowledge.** |

**EXISTING legacy fields:** `name`, `variants[]` (strings), `lifecycle_stage` (free text), `genai_classification` (`PASS`/`PARTIAL`), `simulation_type`, `prerequisites[]`, `attack_flow[]`, `detection_signals[]` (embedded objects), `controls_targeted[]` (strings), `evidence_confidence`.

**PROPOSED GenAI:** `traditional` \| `genai_amplified` \| `genai_load_bearing` \| `unknown` plus `load_bearing` and `transformation`. Never `is_genai` boolean only.

---

## AttackVariant

| Field | Value |
| --- | --- |
| **Object name** | AttackVariant |
| **Purpose** | Meaningful variation of a family (e.g. Payment Instruction Manipulation → beneficiary substitution vs QR manipulation). |
| **Source** | **SOURCE-DERIVED** PDF variant lists / family `variants` strings. **EXISTING IMPLEMENTATION:** not a registry; strings on the family. Dataset generator uses underscored slugs (`AitM_Phishing`) that may not equal KB strings. |
| **Owner** | Knowledge Base. |
| **Consumers** | **EXISTING:** planner copies `selected_variant` onto payloads. **PROPOSED:** vector.family/variant join; evaluation coverage. |
| **Lifecycle** | Created with family; only add variants that are source-backed or explicitly `implementation_derived`. |
| **Storage** | **PROPOSED:** `knowledge/attacks/attack_variants.json`. |
| **Primary key** | **PROPOSED:** `variant_id` (e.g. `VAR-AG-001-01`). |
| **Foreign keys / references** | `family_id` → AttackFamily; `evidence_ids[]`. |
| **Mutable / immutable** | Immutable after review. |
| **ML training?** | **No.** Optional metadata on instances; blocked as a feature today. |
| **Knowledge vs runtime** | **Source knowledge.** |

---

## AttackVector

| Field | Value |
| --- | --- |
| **Object name** | AttackVector |
| **Purpose** | Executable **specification** for how to instantiate an attack. Not a transaction. Not an instance. Example: “gradually escalate amount after adding a new beneficiary.” |
| **Source** | **PROPOSED** from family flow + simulation section + (later) implementation-derived templates. **EXISTING:** schema `attack_vector.schema.json` only; **zero records.** Behavior lives in `kb_campaign_builder.py`. |
| **Owner** | Knowledge Base / simulation. |
| **Consumers** | **PROPOSED:** planner, generic simulation engine. **EXISTING:** none. |
| **Lifecycle** | Reviewed, versioned with KB. Diversity comes from parameter distributions × sandbox state, not millions of vector rows. |
| **Storage** | **PROPOSED:** JSON under `knowledge/attacks/attack_vectors`. |
| **Primary key** | `vector_id`. |
| **Foreign keys / references** | `family_id`, `variant_id`, `simulation_template_id`, `parameter_refs[]`, `expected_signal_ids[]`, `targeted_control_ids[]`, `legitimate_counterpart_ids[]`, `evidence_ids[]`, lifecycle stage IDs. |
| **Mutable / immutable** | Immutable spec. Do **not** store `amount: 49721` or timestamps. |
| **ML training?** | **No.** |
| **Knowledge vs runtime** | **Source knowledge** (executable knowledge, still not runtime state). |

---

## AttackInstance

| Field | Value |
| --- | --- |
| **Object name** | AttackInstance |
| **Purpose** | One concrete generation of a vector: customer C001, device D001, amount ₹47,912, timestamp T1. Same vector → many instances. |
| **Source** | **EXISTING IMPLEMENTATION (unnamed):** `ActionPayload` from `AttackGenerator` (`new_campaign_ids`, payload_template, `BaselineLoader` noise). |
| **Owner** | Red Team generator. **Not** the KB. |
| **Consumers** | Sandbox (execute), collector (payment subset), experiments. |
| **Lifecycle** | Created at campaign time; should be **immutable** once executed (append-only log). |
| **Storage** | **EXISTING:** ephemeral in graph state; fragments in buffer JSONL and `campaign_events`. **PROPOSED:** experiment store / JSONL with `attack_instance_id`. |
| **Primary key** | **PROPOSED:** `attack_instance_id`. **EXISTING:** none; `campaign_id` + `step` is an **INFERRED** composite. |
| **Foreign keys / references** | `vector_id` (missing today), `family_id`, `variant_id`, `campaign_id`, sandbox entity IDs, `experiment_id`. |
| **Mutable / immutable** | Immutable after execution. |
| **ML training?** | **Not directly.** Features derived from the instance **may** enter training if the observation is **selected** into the buffer/dataset. The instance record itself is experiment data. |
| **Knowledge vs runtime** | **Runtime data.** |

---

## Signal

| Field | Value |
| --- | --- |
| **Object name** | Signal (detection signal) |
| **Purpose** | Observable behavior (e.g. novel beneficiary / suspicious pattern). First-class KB entity. Referenced by ID from attacks. |
| **Source** | **SOURCE-DERIVED** PDF detection tables. **EXISTING:** 276 global records; additional names embedded on families (327 unmatched after normalize). |
| **Owner** | Knowledge Base (defense). |
| **Consumers** | **EXISTING:** campaign builder (regex → payload hints), FailureAnalyzer (name match to triggers), API `/signals`. **PROPOSED:** evaluation coverage; signal→feature map. |
| **Lifecycle** | Stable; alias map for names. Unmatched names stay in review, not guessed. |
| **Storage** | Legacy `attack_signals.json`; canonical `signals.json`. |
| **Primary key** | **EXISTING canonical:** `signal_id` (`SIG-####`). **Legacy:** none (`signal_name`). |
| **Foreign keys / references** | **PROPOSED:** `evidence_ids[]`; inverse from families/vectors; `feature_ids[]` via mapping table. |
| **Mutable / immutable** | Immutable definitions. |
| **ML training?** | **No** as text. Mapped **features** may be trained on. |
| **Knowledge vs runtime** | **Source knowledge.** Observed firing at runtime is `Observation.signals`, not a new Signal row. |

---

## Feature

| Field | Value |
| --- | --- |
| **Object name** | Feature |
| **Purpose** | Numeric/categorical input to FraudShield (amount, device_age_days, is_new_beneficiary, …). Bridge from signal to model. |
| **Source** | **EXISTING IMPLEMENTATION:** `train_model.py` `CANDIDATE_FEATURES`; `FeatureBuilder.SANDBOX_FEATURES`; `data/models/features.json` `feature_order`. **INFERRED** from transaction columns in baseline/known_fraud CSVs. Not PDF-authored. |
| **Owner** | Blue Team (feature engineering). |
| **Consumers** | `train_model.py`, `HardeningTrainer`, `FraudShieldModel`, `FeatureBuilder`, evaluator. |
| **Lifecycle** | Versioned with `feature_version` (**PROPOSED**). Changing order/mappings requires a new model. |
| **Storage** | Spec JSON in `data/models/`; values on each training row / `EvidenceRecord.features`. |
| **Primary key** | Feature **name** string in `feature_order`. **PROPOSED:** `feature_id` if catalogued. |
| **Foreign keys / references** | **PROPOSED:** SignalFeatureMapping. `features.json` `model_file`. |
| **Mutable / immutable** | Spec immutable per model version; values computed per transaction. |
| **ML training?** | **Yes** — these are the training columns. IDs, family names, and `meta_*` must stay out. |
| **Knowledge vs runtime** | **Runtime / ML contract.** Mapping *from* KB signals is knowledge; the vector is runtime. |

---

## Control

| Field | Value |
| --- | --- |
| **Object name** | Control (semantic KB control) |
| **Purpose** | Named defensive concept (“velocity monitoring”, “beneficiary verification”). Describes *what* is defended, not a production threshold. |
| **Source** | **SOURCE-DERIVED** PDF control lists / stage tables / family `controls_targeted`. **EXISTING:** 342 canonical `CTL-####` from exact-text dedupe; legacy as strings on stages and families. |
| **Owner** | Knowledge Base (defense). |
| **Consumers** | Canonical loader (unused); validation; **PROPOSED** evaluation/coverage. Runtime rules do **not** look up `CTL-####`. |
| **Lifecycle** | Stable KB. |
| **Storage** | `canonical/controls.json`. Stages still embed **name strings**. |
| **Primary key** | `control_id`. |
| **Foreign keys / references** | `lifecycle_stage_ids[]`; **PROPOSED:** `detects_signal_ids[]`, `implemented_by` → sandbox rule, `evidence_ids[]`. |
| **Mutable / immutable** | Immutable definition. |
| **ML training?** | **No.** |
| **Knowledge vs runtime** | **Source knowledge.** |

Do **not** invent `threshold = ₹50,000` on this object unless the **Sandbox** config explicitly defines that synthetic limit.

---

## ControlExecution

| Field | Value |
| --- | --- |
| **Object name** | ControlExecution |
| **Purpose** | One firing of an **executable** sandbox rule during an action (e.g. `account_younger_than_30_days`). Outcome of a control, not the control definition. |
| **Source** | **EXISTING IMPLEMENTATION (unnamed):** `control_triggers: string[]` on `SandboxObservation`, buffer records, rule `triggered_rules`. |
| **Owner** | Sandbox / experiment store. |
| **Consumers** | FailureAnalyzer, EvidenceCollector, dashboard (indirect). |
| **Lifecycle** | Append-only with the observation. |
| **Storage** | **EXISTING:** arrays on observation/buffer. **PROPOSED:** typed rows: `execution_id`, `observation_id`, `rule_id`, optional `control_id`, contribution, timestamp. |
| **Primary key** | **PROPOSED:** `control_execution_id`. |
| **Foreign keys / references** | `observation_id`; optional `control_id` (KB); sandbox `rule_name`. |
| **Mutable / immutable** | Immutable. |
| **ML training?** | **Not as labels.** May appear as features only if an explicit engineered feature exists (today: trigger strings are **not** in `feature_order`). |
| **Knowledge vs runtime** | **Runtime data.** |

---

## LifecycleStage

| Field | Value |
| --- | --- |
| **Object name** | LifecycleStage |
| **Purpose** | Where in the payment lifecycle an attack or control sits (KYC, device/session, authentication, payment initiation, settlement, AML, …). |
| **Source** | **SOURCE-DERIVED** PDF stage labels. **EXISTING:** 58 legacy `stage_name`s; 49 canonical after duplicate merge + `STG-####`; aliases JSON. |
| **Owner** | Knowledge Base. |
| **Consumers** | Family filter, campaign builder stage hints, `control_registry.STAGE_ALIASES`, API `/stages`. |
| **Lifecycle** | Stable IDs; aliases preserve legacy strings. |
| **Storage** | `lifecycle_stages.json` (legacy + canonical). |
| **Primary key** | **Canonical:** `stage_id`. **Legacy:** `stage_name` (not unique historically). |
| **Foreign keys / references** | Families/controls/vectors reference stage IDs. Canonical stage still embeds control **names**, not IDs. |
| **Mutable / immutable** | Immutable IDs. |
| **ML training?** | **No** as taxonomy. CSV `lifecycle_stage` column is blocked as a feature. |
| **Knowledge vs runtime** | **Source knowledge.** Journey step names in sandbox are a **runtime** parallel (KYC, Device, …) — **INFERRED** overlap, not the same PK. |

---

## SimulationTemplate

| Field | Value |
| --- | --- |
| **Object name** | SimulationTemplate |
| **Purpose** | Reusable recipe: required entities/state, action types, parameter refs, constraints, expected transitions. “How can this vector be instantiated in *our* Sandbox?” |
| **Source** | **SOURCE-DERIVED** PDF “Simulation Intelligence” / “GENERATE” tables. **EXISTING:** schema only; Python `PATTERN_KEYWORDS` is the de facto template set (**implementation_derived**). |
| **Owner** | Knowledge / simulation. |
| **Consumers** | **PROPOSED:** generator. **EXISTING:** none as data. |
| **Lifecycle** | Version with sandbox action_type enum. |
| **Storage** | **PROPOSED:** `knowledge/simulation/simulation_templates.json`. |
| **Primary key** | `template_id`. |
| **Foreign keys / references** | `parameter_refs[]`, `supported_action_types[]` (sandbox `ActionType`). |
| **Mutable / immutable** | Spec immutable per KB version; distinct from instance. |
| **ML training?** | **No.** |
| **Knowledge vs runtime** | **Source knowledge** (simulation support). |

---

## SimulationParameter

| Field | Value |
| --- | --- |
| **Object name** | SimulationParameter |
| **Purpose** | Reusable parameter definition: amount, time, device age, beneficiary novelty, velocity, geo, session duration, etc. Legitimate distribution **reference** + mutation strategies + attacker-controllable flag. |
| **Source** | **SOURCE-DERIVED** PDF mutation/variant parameter tables. **EXISTING:** hardcoded numbers in campaign builder and `EXECUTABLE_DEFAULTS`. No schema file. |
| **Owner** | Knowledge / simulation. Executable limits stay in Sandbox. |
| **Consumers** | **PROPOSED:** vectors, templates, generator, FeatureBuilder alignment. |
| **Lifecycle** | Stable definitions; distributions may point at baseline columns. |
| **Storage** | **PROPOSED:** `knowledge/simulation/parameters.json`. |
| **Primary key** | `parameter_id` (e.g. `PRM-AMOUNT`). |
| **Foreign keys / references** | related `signal_ids[]`, `feature_names[]`. |
| **Mutable / immutable** | Definition immutable; sampled values belong on instances. |
| **ML training?** | **No** (the definition). Sampled values become features on rows. |
| **Knowledge vs runtime** | **Source knowledge.** |

---

## LegitimateCounterpart

| Field | Value |
| --- | --- |
| **Object name** | LegitimateCounterpart |
| **Purpose** | Legitimate behavior that looks like an attack (new phone + family beneficiary + rent at night vs new device + new beneficiary + high-value night). Hard negatives so the model does not learn `new_device = fraud`. |
| **Source** | **SOURCE-DERIVED** PDF simulation tables (“Legitimate counterpart”). **EXISTING:** schema only; CSV column `meta_hard_negative`; generator realism. No KB registry. |
| **Owner** | Simulation / Blue training support. **Not** an attack family. |
| **Consumers** | **PROPOSED:** vector evaluation, training mix. **EXISTING:** dataset `meta_hard_negative` if used (blocked from features as `meta_*`). |
| **Lifecycle** | Reviewed with vectors. |
| **Storage** | **PROPOSED:** `knowledge/simulation/legitimate_counterparts.json`; training rows in CSV/Parquet. |
| **Primary key** | `counterpart_id`. |
| **Foreign keys / references** | `distinguishing_signal_ids[]`; vectors `legitimate_counterpart_ids[]`. |
| **Mutable / immutable** | Spec immutable; generated legit rows are dataset runtime. |
| **ML training?** | **Yes, as label=0 rows** when materialized into a training dataset. The KB record is not a training row. |
| **Knowledge vs runtime** | KB record = **source knowledge**. Generated transactions = **runtime / training data**. |

---

## SandboxEntity

| Field | Value |
| --- | --- |
| **Object name** | SandboxEntity |
| **Purpose** | A thing in the synthetic world: customer, account, device, merchant, beneficiary (later: session, instrument, …). |
| **Source** | **EXISTING IMPLEMENTATION:** dataclasses in `backend/sandbox/state.py`. Created by Red payloads / orchestrator handlers. |
| **Owner** | Sandbox. |
| **Consumers** | Engines, rules, FeatureBuilder, RiskEngine. |
| **Lifecycle** | Created/updated during campaigns; **mutable**. Lost on process restart (**EXISTING**). |
| **Storage** | In-memory dicts. **PROPOSED:** PostgreSQL/SQLite entity tables. |
| **Primary key** | `customer_id`, `device_id`, `account_id`, `merchant_id`, `beneficiary_id` (per type). |
| **Foreign keys / references** | device.customer_id, account.customer_id, beneficiary.customer_id, merchant.owner_customer_id. |
| **Mutable / immutable** | **Mutable** (balances, last_seen, transaction lists). |
| **ML training?** | **No** as entities. Aggregates computed from them become features. |
| **Knowledge vs runtime** | **Runtime data.** Must **not** live in the KB. |

---

## SandboxState

| Field | Value |
| --- | --- |
| **Object name** | SandboxState |
| **Purpose** | The full “what is true right now” snapshot: all entities, relationships, transaction_log, trust/risk/lifecycle fields. |
| **Source** | **EXISTING IMPLEMENTATION:** class `SandboxState`. |
| **Owner** | Sandbox. |
| **Consumers** | Orchestrator, FeatureBuilder (`build(..., state)`), rules. |
| **Lifecycle** | Mutated on every successful action; payment `add_transaction` even after decision. |
| **Storage** | RAM. `state_snapshot` on observation is a **tiny** subset (customer_id, trust_score, tx_count_24h). |
| **Primary key** | None (singleton per sandbox process). **PROPOSED:** `environment_id` + `as_of`. |
| **Foreign keys / references** | Contains all entity PKs. |
| **Mutable / immutable** | **Mutable.** Snapshots on observations should be **immutable copies**. |
| **ML training?** | **No** as a blob. |
| **Knowledge vs runtime** | **Runtime data.** |

Example that belongs here, not in KB: customer C001 has device D001, account A001, 4 beneficiaries, 20 legit txs, just registered D002.

---

## Journey

| Field | Value |
| --- | --- |
| **Object name** | Journey |
| **Purpose** | Ordered lifecycle engine results for one action (KYC → Device → Auth → Payment Initiation → Risk → Authorization → Settlement). |
| **Source** | **EXISTING IMPLEMENTATION:** `List[JourneyStep]` on `SandboxObservation`. |
| **Owner** | Sandbox orchestrator. |
| **Consumers** | FailureAnalyzer (`journey_trace`), observation consumers. |
| **Lifecycle** | Immutable once observation emitted. |
| **Storage** | Embedded in observation / legacy dict. |
| **Primary key** | None; belongs to `action_id` / observation. |
| **Foreign keys / references** | Parent observation. Step names are strings, not `stage_id`. |
| **Mutable / immutable** | Immutable. |
| **ML training?** | **No** as nested journey. |
| **Knowledge vs runtime** | **Runtime data.** |

---

## Experiment

| Field | Value |
| --- | --- |
| **Object name** | Experiment (campaign / loop run) |
| **Purpose** | Auditable grouping: “we ran these instances against this environment/model.” Contains campaign metadata, not taxonomy. |
| **Source** | **EXISTING IMPLEMENTATION (split):** `campaign_id` on payloads; `RedTeamState.campaigns`; SQLite `loop_runs` + `campaign_events`; graph `iteration`. |
| **Owner** | Platform / Red execution. |
| **Consumers** | Dashboard, LoopRunner, evaluator (indirect via buffer). |
| **Lifecycle** | Created at run start; **immutable** after finish (status updates allowed). |
| **Storage** | **EXISTING:** SQLite `loop_runs`. **PROPOSED:** experiment header + observation FKs. |
| **Primary key** | **EXISTING:** `loop_runs.id` (UUID); payload `campaign_id` is a **different** namespace. |
| **Foreign keys / references** | **PROPOSED:** `environment_version`, `model_version`, `attack_vector_id`s, observation IDs. |
| **Mutable / immutable** | Header mostly immutable; status/metrics filled at end. |
| **ML training?** | **No.** |
| **Knowledge vs runtime** | **Runtime / experiment data.** |

---

## Observation

| Field | Value |
| --- | --- |
| **Object name** | Observation |
| **Purpose** | **Canonical immutable handoff** of what happened for one sandbox action. Feeds Red memory, experiment store, Blue buffer, labs, UI. One shape — not four. |
| **Source** | **EXISTING IMPLEMENTATION (partial):** `SandboxObservation` in `sandbox/schemas.py` + `to_legacy_response()`. |
| **Owner** | Sandbox emit; experiment store persist. |
| **Consumers** | **EXISTING:** Red sandbox_client, FailureAnalyzer, EvidenceCollector, LoopRunner (projected). **PROPOSED:** all subsystems. |
| **Lifecycle** | Append-only. |
| **Storage** | **EXISTING:** return value + orchestrator `execution_log` (RAM). **PROPOSED:** JSONL/SQLite observations table. |
| **Primary key** | **EXISTING:** `action_id`. **PROPOSED:** `observation_id` (may equal action_id). |
| **Foreign keys / references** | **PROPOSED:** `experiment_id`, `campaign_id`, `attack_vector_id`, `attack_instance_id`, `transaction_id`, `model_version`, `environment_version`. |
| **Mutable / immutable** | **Immutable.** |
| **ML training?** | **Not automatically.** Only if curated into AdversarialExample / TrainingDataset. Scores on the observation are **outputs**, not labels. |
| **Knowledge vs runtime** | **Runtime / experiment data.** |

**EXISTING fields:** `action_id`, `action_type`, `decision`, `reason`, `message`, `risk_score`, `control_triggers`, `journey`, `state_snapshot`, `timestamp`, payment: `transaction_id`, `ml_score`, `rule_risk`, `settled`, `settlement_detail`.

**PROPOSED additions:** vector/instance/experiment IDs, `state_before` / `state_after`, full feature map, behavioral/graph outputs, unified risk breakdown, outcome/reason codes, model/environment versions.

---

## RedMemory

| Field | Value |
| --- | --- |
| **Object name** | RedMemory |
| **Purpose** | Environment-specific lessons: “new device + immediate high-value is caught by device control”; “gradual escalation bypassed current velocity rule.” Dynamic. Must **not** overwrite taxonomy. |
| **Source** | **EXISTING IMPLEMENTATION:** `MemoryAgent` (`MemoryEntry`, `StrategyMemory`); optional ChromaDB. |
| **Owner** | Red Team. |
| **Consumers** | StrategyLayer, ThreatHunter (`memory_context`), planner (indirect). |
| **Lifecycle** | Created from `AnalysisResult`; **mutable** confidence/counts; **EXISTING** lost on process exit. |
| **Storage** | RAM. **PROPOSED:** SQLite/JSONL + optional vector index keyed by `environment_id`. |
| **Primary key** | `memory_id` / `strategy_id`. |
| **Foreign keys / references** | **PROPOSED:** `observation_id`, `family_id`, `control` names/IDs, `model_version`. |
| **Mutable / immutable** | Mutable summaries; cite immutable observations. |
| **ML training?** | **No.** Blue must not train on Red’s prose memories. |
| **Knowledge vs runtime** | **Runtime / Red-specific knowledge** — not the KB. |

---

## AdversarialExample

| Field | Value |
| --- | --- |
| **Object name** | AdversarialExample |
| **Purpose** | An executed observation **selected** as useful for Blue (success, high-information, diverse, near-boundary, novel, bypass, hard case). Not every attack instance. |
| **Source** | **EXISTING IMPLEMENTATION (over-inclusive):** `EvidenceRecord` in `data/adversarial_buffer/evidence.jsonl`. Collector stores **every** `initiate_payment` with `label=1`. Inspected file: 17 rows, all blocked, AML families. |
| **Owner** | Blue Team buffer (curation **PROPOSED**). |
| **Consumers** | `HardeningTrainer.export_training_rows`, evaluator, `harden_fraudshield.py`. |
| **Lifecycle** | Append-only JSONL; loop can `clear()` on `--fresh-buffer`. |
| **Storage** | JSONL. **PROPOSED:** curated table + pointer to `observation_id`. |
| **Primary key** | `evidence_id` (buffer). **Note:** this is **not** KB `EVD-*` evidence. |
| **Foreign keys / references** | `campaign_id`, `attack_family`; **PROPOSED:** `observation_id`, `vector_id`, `dataset_version` when exported. |
| **Mutable / immutable** | Treat records as immutable; buffer file may be cleared. |
| **ML training?** | **Yes, if selected** — features + fraud label. **Not** the ML score as label. |
| **Knowledge vs runtime** | **Runtime / training candidate.** |

Name collision: KB **Evidence** (PDF provenance) ≠ Blue **EvidenceRecord** (adversarial buffer).

---

## TrainingDataset

| Field | Value |
| --- | --- |
| **Object name** | TrainingDataset |
| **Purpose** | Exact mix used to train FraudShield version X. Reproducible. |
| **Source** | **EXISTING IMPLEMENTATION (implied):** v1 = `master_dataset.json`; v2 = JSON sample (4000+4000) + buffer rows. CSVs exist but trainer does not read them directly. |
| **Owner** | Blue Team / ML. |
| **Consumers** | `train_model.py`, `HardeningTrainer`. |
| **Lifecycle** | Frozen when a model is trained. New mix → new `dataset_version`. |
| **Storage** | **EXISTING:** `master_dataset.json`, two CSVs, buffer JSONL. **PROPOSED:** manifest JSON + Parquet snapshot. |
| **Primary key** | **PROPOSED:** `dataset_version`. |
| **Foreign keys / references** | sources: baseline path/hash, known_fraud path/hash, buffer evidence_ids, hard-negative set id, feature_version. |
| **Mutable / immutable** | **Immutable** once published. |
| **ML training?** | **Yes** — this *is* the training set. |
| **Knowledge vs runtime** | **Runtime / ML data.** Not KB. |

Target mix: legitimate baseline + known fraud [+ selected adversarial + hard negatives].

---

## ModelVersion

| Field | Value |
| --- | --- |
| **Object name** | ModelVersion |
| **Purpose** | Which FraudShield artifact is running and how it was trained. Lineage/metadata; the booster file is the artifact. |
| **Source** | **EXISTING IMPLEMENTATION (partial):** `features.json` (`version`, `model_file`, `parent_version`, `training_sources`, `feature_order`, `decision_threshold`, `trained_at`). Files `fraudshield_v1.txt` / `v2.txt`. |
| **Owner** | Blue Team / platform deploy (swap writes active spec). |
| **Consumers** | `FraudShieldModel.load`, sandbox `RiskEngine`, evaluator, dashboard status. |
| **Lifecycle** | Created at train time; activation = point `features.json` at artifact (**EXISTING**). |
| **Storage** | `data/models/*`. **PROPOSED:** `model_registry.json` or SQLite `model_versions`. |
| **Primary key** | `version` string (`v1`, `v2`) **EXISTING**; **PROPOSED:** monotonic `model_version` ID. |
| **Foreign keys / references** | `dataset_version`, `feature_version`, `parent_model_version`, `evaluation_run_id`, `artifact_path`. |
| **Mutable / immutable** | Artifact immutable; `deployment_status` mutable. |
| **ML training?** | N/A (it *is* the model). Predictions are not KB and not labels. |
| **Knowledge vs runtime** | **Runtime / ML artifact metadata.** |

---

## EvaluationRun

| Field | Value |
| --- | --- |
| **Object name** | EvaluationRun |
| **Purpose** | Held-out or buffer comparison for a model version (PR-AUC, ROC-AUC, buffer mean lift, recommend_swap). |
| **Source** | **EXISTING IMPLEMENTATION:** `model_metrics.json` (v1 suite); `hardening_report.json`; SQLite `loop_runs` metric columns. |
| **Owner** | Blue Team / platform. |
| **Consumers** | LoopRunner swap decision, dashboard. |
| **Lifecycle** | Created after train; immutable report. |
| **Storage** | JSON reports + loop row. **PROPOSED:** `evaluation_runs` table. |
| **Primary key** | **PROPOSED:** `evaluation_run_id`. **EXISTING:** none (file + loop id). |
| **Foreign keys / references** | `model_version`, `dataset_version` (holdout), buffer path/hash. |
| **Mutable / immutable** | Immutable. |
| **ML training?** | **No** (metrics only). |
| **Knowledge vs runtime** | **Runtime / experiment data.** |

---

## Evidence

| Field | Value |
| --- | --- |
| **Object name** | Evidence (KB provenance) |
| **Purpose** | Trace a KB claim to a taxonomy PDF: source file, page/section if known, field supported, short note, confidence, maturity. Do not fabricate page numbers. |
| **Source** | **SOURCE-DERIVED** PDF “F. Evidence” tables and identity sections. **EXISTING:** `canonical/evidence.json`; family `evidence` ID lists; `source_extractions/*`; review queue. Original 57 `EVD-<attack-id>` often have `locator: null`. |
| **Owner** | Knowledge Base. |
| **Consumers** | Validation, review, **PROPOSED** UI/audit. Not FraudShield. |
| **Lifecycle** | Append when extraction is verified. |
| **Storage** | `canonical/evidence.json`; extraction JSON. |
| **Primary key** | `evidence_id` (`EVD-AG-001`, `EVD-SRC-AG-001-ATTACKER`, `EVC-*` candidates). |
| **Foreign keys / references** | `source` filename; optional page; `attack_id` / field on candidates. |
| **Mutable / immutable** | Immutable once verified; candidates may be rejected. |
| **ML training?** | **No.** |
| **Knowledge vs runtime** | **Source knowledge.** |

**Do not confuse with** `EvidenceRecord` / `evidence_id` `ev_*` in the adversarial buffer.

---

## Additional objects (present in the repo, not in the minimum list)

### ActionPayload / AttackPlan / Hypothesis

**EXISTING IMPLEMENTATION** Red Pydantic contracts (`red_team/schemas.py`). Plan is an intermediate between family and instance. **PROPOSED:** plan should cite `vector_id`. Knowledge vs runtime: runtime. ML: no.

### LoopRun / CampaignEvent / SchedulerConfig

**EXISTING IMPLEMENTATION** SQLAlchemy models. Platform operations, not taxonomy. ML: no.

### FraudShieldPrediction

**EXISTING IMPLEMENTATION** score + threshold + `is_fraud_predicted`. **Output**, never KB ground truth, never training label.

### Executable control defaults

`EXECUTABLE_DEFAULTS` in `control_registry.py`. **Sandbox configuration**, not KB Control. Synthetic thresholds only.

---

## Quick answers (the questions this dictionary must close)

| Question | Answer |
| --- | --- |
| What data do we have? | 15 PDFs; 57 families; 276 signals; 49/58 stages; 342 canonical controls; 526 KB edges; sandbox entities in RAM; observations; 17 buffer payments; baseline + known-fraud CSVs; `master_dataset.json`; FraudShield v1/v2 files. |
| Where does it live? | See audit section C. Dual KB (legacy runtime vs canonical unused). |
| Who creates it? | PDFs/extractors → KB; Red generator → instances; Sandbox → observations/state; Collector → buffer; Trainer → models. |
| Who consumes it? | Red agents + API consume **legacy** KB; Sandbox consumes payloads + rules + model; Blue consumes features + labels; dashboard consumes SQLite + buffer stats. |
| What goes into the KB? | Reusable attack/defense/simulation **concepts** and vectors. Not rows, not scores, not customers. |
| What stays in Sandbox? | Entities, balances, graphs, executable thresholds, current risk. |
| What becomes an experiment? | A campaign/loop of instances + observations. |
| What becomes ML training data? | Feature rows with `is_fraud` from baseline/known fraud and **selected** buffer examples — not family prose, not ML scores. |
| What does Red learn? | `RedMemory` from observations/analysis (environment-specific). |
| What does Blue learn? | Model weights from a versioned training dataset. |
| Where do generated attacks live? | As **instances** (payloads / logs / buffer), **never** as new KB families. |
| Vector vs instance? | Vector = spec without ₹/timestamp; instance = bound to entities and values. |
| PDF → FraudShield v2? | PDF → (legacy) family → Red plan/instance → Sandbox observation → buffer JSONL → `HardeningTrainer` + `master_dataset.json` sample → `fraudshield_v2.txt`. Canonical KB is **not** on that path today. |

---

*End of data dictionary. No code migration starts until these two documents are reviewed.*
