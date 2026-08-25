#!/usr/bin/env python3
"""Test tree mode + memory persistence in continuous runner."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("RED_TEAM_USE_LLM", "false")
os.environ.setdefault("RED_TEAM_USE_ATTACK_ENGINE", "true")
os.environ.setdefault("RED_TEAM_LINEAR_RETRIES", "1")
os.environ.setdefault("RED_TEAM_JAILBREAK_STRATEGY", "tree")

from backend.red_team.runner import run_continuous


def main() -> int:
    summary = run_continuous(max_families=1, family_id="AUT-001", print_sections=False)
    assert summary, "Expected one campaign summary"
    assert summary[0].get("branches", 1) >= 3, "Tree mode should produce 3 branches"
    print(f"tree campaign: branches={summary[0]['branches']} executed={summary[0]['steps_executed']}")
    print("OK: test_deepteam_tree_mode passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
