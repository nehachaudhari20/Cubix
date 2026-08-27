# Knowledge Base audit and schema foundation

Audit date: 2026-08-25. Scope is deliberately read-only with respect to the
existing KB and application behavior. The 15 PDFs in `data/raw_pdfs/` were
inspected alongside their generated JSON outputs and consumers.

## A. Current KB structure

`attack_families.json` is a wrapper (`generated_at`, `total_families`,
`attack_families`) containing 57 flat family records. Each family embeds its
own signal objects and free-text control names. `attack_signals.json` is a
wrapper containing 276 global signal records, but has no IDs or family links.
`lifecycle_stages.json` is a wrapper containing 58 stage records with a name
and an array of control strings. There are no standalone controls, evidence,
relationships, vectors, templates, counterparts, sandbox state, experiments,
or generated instances.

## B. Current schemas inferred from actual data

Every family currently has: `attack_id`, `name`, `variants` (string array),
`lifecycle_stage` (free-text string), `genai_classification` (`PASS` or
`PARTIAL`), `simulation_type`, `prerequisites` (string array), `attack_flow`
(string array), `detection_signals` (objects with `name` and
`detection_method`), `controls_targeted` (string array), and
`evidence_confidence`.

Every global signal has: `signal_name`, `category`, `description`,
`detection_method` (often several semicolon-delimited methods),
`false_positive_risk`, and `cross_account_needed` (boolean). Every stage has
`stage_name` and `controls` (string array). The wrapper totals are 57, 276,
and 58 respectively.

The nine schemas in `data/knowledge/schemas/` define the canonical target
records. Fields marked in their descriptions as an “implementation extension”
are needed for stable IDs/references or executable use and are not claimed to
be direct taxonomy fields. They do not change the three existing files.

## C. Current consumers of each KB object

`KnowledgeLoader` loads all three files and exposes family lookup, exact stage
filtering, family-embedded signals, and controls. `OfflineKnowledge` wraps it
for Red Team agents. `attack_planner`, `strategy_layer`, `threat_hunter`, and
`failure_analyzer` use that wrapper; `kb_campaign_builder` reads family
strings, embedded signals, global signals, and stage controls to synthesize
plans. `backend/api/routes/knowledge.py` exposes all three through `/api/kb`.
The legacy `backend/api/knowledge_api.py` also loads the KB directly. Platform
status/loop services and the Red Team scripts consume `OfflineKnowledge`.

The global signal file is not joined by an explicit key: `OfflineKnowledge`
and `kb_campaign_builder` use normalized/substring signal-name matching.
Stage matching is likewise exact or substring matching. `KnowledgeLoader`
currently uses `stage` rather than the actual `stage_name` field in
`get_all_controls`; this collapses its keys to `Unknown`. The route response
model also calls the field `stage`. These are existing compatibility risks,
not changed in this phase.

## D. Missing data-model objects

1. Stable lifecycle-stage registry and aliases.
2. Standalone control registry.
3. Stable signal registry with IDs.
4. Explicit relationships/graph edges.
5. Evidence/source references with PDF/page/section locators.
6. Canonical family record with the source identity fields preserved.
7. Executable attack-vector specifications.
8. Simulation templates separate from vectors and generated instances.
9. Legitimate counterparts for false-positive/evaluation cases.
10. Parameter-distribution references.
11. Sandbox-state contract.
12. Experiment/execution result object.
13. Curated training-dataset manifest.
14. Model/version provenance object.
15. Generated attack-instance object.

## E. Missing fields

The PDFs regularly contain attacker, target, objective, primary lifecycle
stage, cross-stage stages, traditional mechanism, GenAI transformation,
GenAI classification/role, detailed observable signals, controls, and source
evidence. The family JSON has only a flattened subset. Specifically absent or
not structurally represented are objective, attacker, target, cross-stage
stages, traditional mechanism, GenAI transformation, whether GenAI is
load-bearing, normalized signal/control references, evidence locations, and
maturity. Families also have no canonical stage ID.

## F. Duplications and inconsistencies

* Two `stage_name` values are duplicated: `Account Creation (Stage 2)` and
  `Payment Initiation (Stage 5)`.
* Family lifecycle labels use inconsistent spelling, separators, parenthetical
  detail, and cross-stage notation (for example `Cross-stage / Network`,
  `Cross-stage/Network`, and `AI-Agent Commerce / Cross-stage`).
* The same concepts occur as inline family signals and as global signals, but
  names differ enough to require fuzzy matching.
* Controls repeat across stage arrays and family `controls_targeted`, with no
  IDs, aliases, ownership, or relationship type.
* Multiple concepts are packed into strings: semicolon-delimited detection
  methods, compound lifecycle labels, slash-separated simulation types, and
  controls such as `All controls — agent learns to evade all controls`.
* `PASS` and `PARTIAL` are opaque GenAI labels; they do not encode the required
  traditional vs amplified vs load-bearing distinction.

## G. PDF → JSON coverage gaps

All 15 source files follow a richer taxonomy pattern. Examples include
`agent-commerce-11.pdf` (cross-stage stages, attacker, target, objective),
`authorization-10.pdf` (traditional/GenAI mechanism and control detail), and
`network-15.pdf` (network objects and attacker roles). The JSON preserves IDs,
names, variants, a primary stage label, prerequisites, flow, some signals,
controls, and confidence, but it does not retain source filename/page/section
for any record. Consequently individual JSON claims cannot be mechanically
traced to a PDF.

The global signal data has additional detection and false-positive prose but
does not identify its family/source. Conversely current metadata
(`generated_at`, `total_*`) is extraction-process information rather than
taxonomy evidence. `simulation_type`, `evidence_confidence`, global signal
categories, and detection-method wording may be useful curation, but without
per-field evidence they cannot be verified against a specific source taxonomy.

## H. Hardcoded attack knowledge found in code

`backend/red_team/kb_campaign_builder.py` contains the knowledge that should
eventually become controlled vector/template data: `PATTERN_KEYWORDS`,
`STAGE_ACTION_HINTS`, `SIGNAL_PAYLOAD_RULES`, pure-agentic classification,
pattern defaults, concrete MCC/PAN/trust/amount values, structuring and
velocity payment sequences, action-to-stage defaults, and fallback controls.
`failure_analyzer.py`, `attack_generator.py`, and `sandbox_client.py` also
embed remediation or default payload assumptions. None are moved in this
phase, because doing so would alter attack generation.

## I. Recommended migration plan

1. Freeze the three current files as legacy input and keep `KnowledgeLoader`
   behavior intact.
2. Introduce canonical registries for stages, signals, and controls with stable
   IDs and aliases; retain legacy strings during a transition.
3. Backfill family source references from PDFs, then add missing identity,
   cross-stage, mechanism, and GenAI-role fields only where evidenced.
4. Replace inline signal/control copies with explicit relationships while
   retaining compatibility projections for existing consumers.
5. Normalize `PASS`/`PARTIAL` to the three-part GenAI classification with an
   evidence-backed `genai_load_bearing` value.
6. Extract code-only campaign heuristics into simulation templates and then
   create reviewed vector specifications—never concrete transactions.
7. Add a loader adapter/API version for canonical records and migrate Red Team
   consumers incrementally.
8. Only after vector review, connect vectors to sandbox state and separately
   record executions, generated instances, training manifests, and models.

## J. Risks to existing code

Changing field names, normalizing stages in place, or replacing embedded
signals would break direct dict access, exact filters, response models, and
fuzzy matching. Changing campaign-builder heuristics would alter generated
behavior, which is out of scope. The existing stage key mismatch means any
loader/API repair needs regression tests. The validation tool therefore treats
absent future enrichment as warnings, while still reporting malformed current
records and duplicate IDs/names as current-data errors.
