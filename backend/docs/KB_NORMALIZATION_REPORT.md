# Canonical knowledge normalization report

## Registry counts

| Measure | Count |
| --- | ---: |
| Legacy families / canonical families | 57 / 57 |
| Legacy signals / canonical signals | 276 / 276 |
| Legacy stages / canonical stages | 58 / 49 |
| Canonical controls | 342 |
| Evidence records | 57 |
| Relationships | 526 |

The canonical stage count is lower because exact normalized duplicate names
were retained as aliases and their control lists were combined. One additional
source-derived `Cross-stage / Network` stage was added because the network PDF
uses it as a primary stage but the legacy lifecycle registry omitted it.

## Source-derived

Family identity, names, variants, prerequisites, flows, simulation types, and
legacy confidence were copied without reinterpretation. Every family has an
evidence record pointing to its source taxonomy PDF. PDF page/section locators
are `null`: the legacy extraction did not preserve them, so none were invented.
The source filename mapping and GenAI classification rationale are retained in
`canonical/normalization_metadata.json`.

The PDF source section was inspected per family. 39 families use
`genai_load_bearing` when their own source section explicitly says GenAI or
agentic AI is load-bearing; 18 use `genai_amplified` when a section supplies a
GenAI transformation but lacks section-local load-bearing wording. No legacy
`PASS`/`PARTIAL` value was used as the classifier.

## Implementation normalization

`SIG-####`, `STG-####`, `CTL-####`, `EVD-<attack-id>`, and `REL-#####` are
stable registry IDs. Detection methods were split only at the existing
semicolon delimiter. Controls were deduplicated only by exact normalized text.
Family stage, signal, and control strings are represented as IDs; relationship
edges are generated only from those legacy links (`occurs_at`, `observes`, and
`targets`). The read-only `CanonicalKnowledgeLoader` is separate from the
legacy loader.

## Inferred / unresolved

No fuzzy signal equivalence was promoted to a canonical alias. The alias map
contains normalized names for the 276 global signal records only. There are
327 unique unresolved embedded-signal names, recorded in
`normalization_metadata.json`; they remain absent from family signal links
rather than being guessed. There are no unresolved lifecycle aliases after
adding the source-derived network stage.

The following source fields remain intentionally unsupported/null in canonical
families pending reviewed, field-level PDF extraction: `objective`, `attacker`,
`target`, `cross_stage_lifecycle_stage_ids`, `traditional_mechanism`,
`genai_transformation`, and `maturity`. Signals, stages, and controls lack
per-record evidence because legacy inputs provide no source links for them.
Controls have no invented thresholds, risk effects, detection mappings, or
engine implementations.

## Remaining gaps

1. Reviewed PDF page/section locators and field-level excerpts.
2. Explicit resolution workflow for the 327 embedded-signal aliases.
3. Cross-stage lifecycle extraction from source tables.
4. Objective, actor, target, traditional mechanism, and GenAI-transformation
   field extraction with human review.
5. Per-signal, stage, and control evidence links.
6. Evidence-backed control-to-signal `mitigates` relationships.
7. Canonical data migration adapter for legacy API/Red Team consumers.
8. A future vector/template layer—explicitly not created in this phase.
