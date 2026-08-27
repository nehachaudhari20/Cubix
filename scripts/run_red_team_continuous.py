#!/usr/bin/env python3
"""Launch continuous Red Team run (no Bedrock required)."""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("RED_TEAM_USE_LLM", "false")
os.environ.setdefault("USE_KB_API", "false")
os.environ.setdefault("RED_TEAM_USE_ATTACK_ENGINE", "true")
os.environ.setdefault("RED_TEAM_ENGINE_EXECUTE_ALL", "true")
os.environ.setdefault("RED_TEAM_ENGINE_MAX_VARIATIONS", "20")
os.environ.setdefault("RED_TEAM_MUTATE_BEFORE_JUMP", "2")
os.environ.setdefault("RED_TEAM_LINEAR_RETRIES", "3")
os.environ.setdefault("RED_TEAM_JAILBREAK_STRATEGY", "kb")


def main() -> int:
    parser = argparse.ArgumentParser(description="Continuous Red Team payload generation")
    parser.add_argument("--families", type=int, default=5, help="Number of Threat Hunter hypotheses/campaigns")
    parser.add_argument("--family", type=str, default=None)
    parser.add_argument("--strategy", choices=["kb", "crescendo", "tree", "sequential"], default=None)
    parser.add_argument("--linear-retries", type=int, default=None)
    parser.add_argument("--no-engine", action="store_true")
    parser.add_argument("--hard-negatives", action="store_true")
    parser.add_argument("--hard-negative-count", type=int, default=None)
    args = parser.parse_args()

    if args.strategy:
        os.environ["RED_TEAM_JAILBREAK_STRATEGY"] = args.strategy
    if args.linear_retries is not None:
        os.environ["RED_TEAM_LINEAR_RETRIES"] = str(args.linear_retries)
    if args.no_engine:
        os.environ["RED_TEAM_USE_ATTACK_ENGINE"] = "false"
    if args.hard_negatives:
        os.environ["RED_TEAM_HARD_NEGATIVES"] = "true"
    if args.hard_negative_count is not None:
        os.environ["RED_TEAM_HARD_NEGATIVE_COUNT"] = str(args.hard_negative_count)

    from backend.red_team.runner import run_continuous

    print("Red Team continuous runner")
    print(f"  RED_TEAM_USE_LLM={os.environ.get('RED_TEAM_USE_LLM')}")
    print(f"  strategy={os.environ.get('RED_TEAM_JAILBREAK_STRATEGY')}")
    print(f"  attack_engine={os.environ.get('RED_TEAM_USE_ATTACK_ENGINE')}")
    print(f"  linear_retries={os.environ.get('RED_TEAM_LINEAR_RETRIES')}\n")

    summary = run_continuous(max_families=args.families, family_id=args.family)
    return 0 if summary else 1


if __name__ == "__main__":
    raise SystemExit(main())
