"""
Composite attack intelligence — KB-wide context for Threat Hunter & Planner.

Builds CVSS-ranked, GenAI-aware, multi-family hypotheses from relationships,
variants, and lifecycle complementarity (the KB has no explicit family↔family
edges, so composites are derived from stage/pattern/prefix recipes).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from .kb_campaign_builder import build_hypothesis_from_family, classify_family, is_simulatable
from .deepteam.family_scorer import prioritize_families
from .schemas import Hypothesis


# Archetypes: ordered prefix groups → pick one family from each group
COMPOSITE_ARCHETYPES: List[Dict[str, Any]] = [
    {
        "name": "identity_merchant_payment",
        "description": "Synthetic identity + merchant facade + authorization evasion",
        "groups": [["SIF", "DII", "GDF", "SIA"], ["ACQ", "MDF", "BBE"], ["AUT", "AUTH", "GP"]],
    },
    {
        "name": "genai_agent_ecosystem",
        "description": "Agentic GenAI fraud + payment rail + acquirer monitoring gap",
        "groups": [["AG", "GP"], ["AUT", "AUTH"], ["ACQ"]],
    },
    {
        "name": "aml_layering_cashout",
        "description": "AML structuring + outbound/cash-out + merchant settlement",
        "groups": [["AML"], ["OB", "N", "CM"], ["ACQ", "AUT"]],
    },
    {
        "name": "ato_social_payment",
        "description": "Account takeover / social engineering + auth bypass + payment",
        "groups": [["ATO", "SEP", "AUTH"], ["AUT", "GP"], ["ACQ", "OB"]],
    },
    {
        "name": "bot_velocity_burst",
        "description": "Bot / automation + velocity structuring + beneficiary cash-out",
        "groups": [["BOT", "RAT", "DFS"], ["AUT", "AML"], ["OB", "N"]],
    },
]


def _prefix(attack_id: str) -> str:
    return (attack_id or "").split("-")[0].upper()


def is_genai_load_bearing(family: Dict[str, Any]) -> bool:
    genai = family.get("genai") or {}
    return bool(
        family.get("genai_load_bearing")
        or genai.get("load_bearing")
        or genai.get("classification") == "genai_load_bearing"
        or family.get("genai_classification") == "genai_load_bearing"
    )


def is_genai_family(family: Dict[str, Any]) -> bool:
    genai = family.get("genai") or {}
    classification = str(genai.get("classification") or family.get("genai_classification") or "")
    return classification.startswith("genai") or bool(genai.get("capability_ids"))


def family_variants_summary(canonical, family: Dict[str, Any], limit: int = 3) -> List[str]:
    attack_id = family.get("attack_id") or ""
    variants = canonical.get_family_variants(attack_id) if canonical else []
    names: List[str] = []
    for v in variants[:limit]:
        names.append(v.get("variant_id") or v.get("name") or "")
    if not names:
        names = list((family.get("variants") or [])[:limit])
    return [n for n in names if n]


def family_vector_summary(canonical, family: Dict[str, Any], limit: int = 2) -> List[str]:
    attack_id = family.get("attack_id") or ""
    vectors = canonical.get_family_vectors(attack_id) if canonical else []
    return [
        v.get("vector_id") or v.get("name") or ""
        for v in vectors[:limit]
        if v.get("vector_id") or v.get("name")
    ]


def capability_ids(family: Dict[str, Any]) -> List[str]:
    genai = family.get("genai") or {}
    return list(genai.get("capability_ids") or [])


def occurs_at_stage_map(relationships: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """attack_id → list of STG-* stage ids from occurs_at relationships."""
    mapping: Dict[str, List[str]] = {}
    for rel in relationships or []:
        if rel.get("relationship_type") != "occurs_at":
            continue
        src = rel.get("from_ref") or ""
        dst = rel.get("to_ref") or ""
        if src.startswith("STG-") or not dst.startswith("STG-"):
            continue
        mapping.setdefault(src, [])
        if dst not in mapping[src]:
            mapping[src].append(dst)
    return mapping


def build_kb_intel_context(
    *,
    families: List[Dict[str, Any]],
    signals: List[Dict[str, Any]],
    stages: List[Dict[str, Any]],
    relationships: List[Dict[str, Any]],
    canonical: Any,
    tested: Set[str],
    limit_families: int = 40,
) -> Dict[str, Any]:
    """Rich context block for Threat Hunter LLM + rule-based composites."""
    simulatable = [f for f in families if is_simulatable(f)]
    genai_lb = [f for f in simulatable if is_genai_load_bearing(f)]
    ranked = prioritize_families(
        simulatable, signals, tested_ids=tested, limit=min(15, len(simulatable))
    )
    stage_map = occurs_at_stage_map(relationships)

    family_lines: List[str] = []
    for family in simulatable[:limit_families]:
        fid = family.get("attack_id") or ""
        variants = family_variants_summary(canonical, family)
        vectors = family_vector_summary(canonical, family)
        caps = capability_ids(family)
        cvss_item = next((c for c in ranked if c.family_id == fid), None)
        cvss_s = f"{cvss_item.cvss.composite:.2f}" if cvss_item else "?"
        genai_tag = "LOAD_BEARING" if is_genai_load_bearing(family) else (
            "AMPLIFIED" if is_genai_family(family) else "none"
        )
        family_lines.append(
            f"{fid}: {family.get('name')} | stage={family.get('lifecycle_stage')} | "
            f"pattern={classify_family(family)} | genai={genai_tag} | cvss={cvss_s} | "
            f"variants={','.join(variants[:2]) or 'n/a'} | "
            f"vectors={','.join(vectors[:2]) or 'n/a'} | "
            f"caps={','.join(caps[:3]) or 'n/a'} | "
            f"stages_rel={','.join(stage_map.get(fid, [])[:3]) or family.get('lifecycle_stage_id') or 'n/a'}"
        )

    cvss_lines = [
        f"{c.family_id} composite={c.cvss.composite} impact={c.cvss.impact} "
        f"exploit={c.cvss.exploitability} exposure={c.cvss.exposure}"
        for c in ranked[:10]
    ]
    genai_lines = [
        f"{f.get('attack_id')}: {f.get('name')} caps={capability_ids(f)[:4]}"
        for f in genai_lb[:12]
    ]
    stage_lines = [
        f"- {(s.get('stage_name') or s.get('name'))}: {', '.join((s.get('controls') or [])[:3])}"
        for s in stages[:20]
    ]

    return {
        "family_lines": family_lines,
        "cvss_lines": cvss_lines,
        "genai_lines": genai_lines,
        "stage_lines": stage_lines,
        "ranked": ranked,
        "genai_load_bearing": genai_lb,
        "simulatable": simulatable,
        "stage_map": stage_map,
        "catalog": {
            "families": len(families),
            "simulatable": len(simulatable),
            "genai_load_bearing": len(genai_lb),
            "signals": len(signals),
            "stages": len(stages),
            "relationships": len(relationships or []),
            "variants": len(getattr(canonical, "variants", []) or []),
            "vectors": len(getattr(canonical, "vectors", []) or []),
            "capabilities": len(getattr(canonical, "capabilities", []) or []),
        },
    }


def _pick_from_group(
    group_prefixes: List[str],
    pool: List[Dict[str, Any]],
    used: Set[str],
    prefer_genai: bool = False,
) -> Optional[Dict[str, Any]]:
    candidates = [
        f for f in pool
        if _prefix(f.get("attack_id") or "") in group_prefixes
        and (f.get("attack_id") or "") not in used
    ]
    if not candidates:
        return None
    if prefer_genai:
        lb = [f for f in candidates if is_genai_load_bearing(f)]
        if lb:
            candidates = lb
    return candidates[0]


def suggest_composite_hypotheses(
    *,
    simulatable: List[Dict[str, Any]],
    ranked_ids: List[str],
    tested: Set[str],
    limit: int = 3,
) -> List[Hypothesis]:
    """Rule-based composite hypotheses from archetypes + CVSS ordering."""
    # Prefer untested, ordered by CVSS rank when available
    id_rank = {fid: i for i, fid in enumerate(ranked_ids)}
    pool = sorted(
        [f for f in simulatable if f.get("attack_id") not in tested],
        key=lambda f: id_rank.get(f.get("attack_id") or "", 999),
    )
    if len(pool) < 2:
        pool = list(simulatable)

    hypotheses: List[Hypothesis] = []
    used_combos: Set[Tuple[str, ...]] = set()

    for archetype in COMPOSITE_ARCHETYPES:
        if len(hypotheses) >= limit:
            break
        picked: List[Dict[str, Any]] = []
        used: Set[str] = set()
        for gi, group in enumerate(archetype["groups"]):
            fam = _pick_from_group(group, pool, used, prefer_genai=(gi == 0 and "genai" in archetype["name"]))
            if fam is None:
                fam = _pick_from_group(group, simulatable, used, prefer_genai=False)
            if fam is None:
                break
            picked.append(fam)
            used.add(fam.get("attack_id") or "")

        if len(picked) < 2:
            continue

        ids = tuple(f.get("attack_id") for f in picked)
        if ids in used_combos:
            continue
        used_combos.add(ids)

        primary = picked[0]
        composites = [f.get("attack_id") for f in picked[1:] if f.get("attack_id")]
        stages = list(dict.fromkeys(
            (f.get("lifecycle_stage") or "Payment Initiation") for f in picked
        ))
        flow_bits = []
        for f in picked:
            flow = f.get("attack_flow") or []
            flow_bits.append(f"{f.get('attack_id')}: {' → '.join(flow[:3]) if flow else f.get('name')}")

        h = Hypothesis(
            name=f"{archetype['name']}: {' + '.join(ids)}",
            primary_family=primary.get("attack_id"),
            composite_families=composites,
            target_stages=stages,
            novelty_score=0.85,
            success_probability=0.55,
            prerequisites=list(dict.fromkeys(
                p for f in picked for p in (f.get("prerequisites") or [])[:2]
            ))[:6],
            attack_flow_summary=" || ".join(flow_bits),
            reasoning=(
                f"Composite archetype '{archetype['name']}': {archetype['description']}. "
                f"Families {list(ids)} span stages {stages}."
            ),
            suggested_variant=(primary.get("variants") or ["default"])[0],
            jailbreak_strategy="sequential",
        )
        hypotheses.append(h)

    return hypotheses[:limit]


def validate_hypothesis_families(
    hypothesis: Hypothesis,
    known_ids: Set[str],
) -> Optional[Hypothesis]:
    """Drop unknown attack_ids; require primary to exist."""
    if hypothesis.primary_family not in known_ids:
        return None
    composites = [fid for fid in (hypothesis.composite_families or []) if fid in known_ids and fid != hypothesis.primary_family]
    return hypothesis.model_copy(update={"composite_families": composites})


def covered_family_ids(hypothesis: Hypothesis) -> Set[str]:
    ids = {hypothesis.primary_family}
    ids.update(hypothesis.composite_families or [])
    return {i for i in ids if i}
