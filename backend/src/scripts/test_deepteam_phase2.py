#!/usr/bin/env python3
"""Phase 2: AttackPlanner + AttackGenerator wired to DeepTeam adapters."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("RED_TEAM_USE_LLM", "false")
os.environ.setdefault("RED_TEAM_USE_ATTACK_ENGINE", "true")

from backend.knowledge.loader import KnowledgeLoader
from backend.red_team.agents.attack_planner import AttackPlanner
from backend.red_team.agents.attack_generator import AttackGenerator
from backend.red_team.schemas import Hypothesis
from backend.red_team.deepteam.schemas import JailbreakStrategy


def _hypothesis(family_id: str, strategy: str | None) -> Hypothesis:
    loader = KnowledgeLoader()
    family = loader.get_family(family_id) or loader.families[0]
    return Hypothesis(
        name=family.get("name", family_id),
        primary_family=family.get("attack_id", family_id),
        target_stages=[family.get("lifecycle_stage") or "Authorization"],
        novelty_score=0.6,
        success_probability=0.45,
        prerequisites=(family.get("prerequisites") or ["Registered customer"])[:3],
        attack_flow_summary="test",
        reasoning="phase2 test",
        jailbreak_strategy=strategy,
    )


def main() -> int:
    planner = AttackPlanner()
    generator = AttackGenerator()
    family_id = "AUT-001"

    kb_plan = planner.plan(_hypothesis(family_id, "kb"))
    assert kb_plan.jailbreak_strategy == "kb"
    kb_seq = generator.generate_sequence(kb_plan)
    assert kb_seq.total_payloads >= 2
    print(f"KB plan: {len(kb_plan.steps)} steps, {kb_seq.total_payloads} payloads")

    crescendo = planner.plan(_hypothesis(family_id, "crescendo"))
    assert crescendo.jailbreak_strategy == "crescendo"
    assert len(crescendo.steps) >= 5
    c_seq = generator.generate_sequence(crescendo)
    payment_payloads = [p for p in c_seq.payloads if p.action_type == "initiate_payment"]
    assert payment_payloads
    assert any(p.engine_validated for p in payment_payloads)
    print(f"Crescendo: {len(crescendo.steps)} steps, engine validated={payment_payloads[-1].variation_label}")

    branches = planner.plan_branches(_hypothesis(family_id, "tree"))
    assert len(branches) == 3
    assert all(branch.jailbreak_strategy == "tree" for branch in branches)
    for branch in branches:
        seq = generator.generate_sequence(branch)
        assert seq.total_payloads >= 3
    print(f"Tree branches: {[b.branch_label or b.campaign_name for b in branches]}")

    sequential = planner.plan(_hypothesis(family_id, "sequential"))
    assert sequential.jailbreak_strategy == "sequential"
    print(f"Sequential: {len(sequential.steps)} steps")

    print("OK: Phase 2 integration passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
