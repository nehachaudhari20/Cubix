#!/usr/bin/env python3
"""Launch continuous Red Team run (no Bedrock required)."""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("RED_TEAM_USE_LLM", "false")
os.environ.setdefault("USE_KB_API", "false")
os.environ.setdefault("RED_TEAM_USE_ATTACK_ENGINE", "true")
os.environ.setdefault("RED_TEAM_LINEAR_RETRIES", "2")
os.environ.setdefault("RED_TEAM_JAILBREAK_STRATEGY", "kb")


def main() -> int:
    parser = argparse.ArgumentParser(description="Continuous Red Team payload generation")
    parser.add_argument("--families", type=int, default=3)
    parser.add_argument("--family", type=str, default=None)
    parser.add_argument("--strategy", choices=["kb", "crescendo", "tree", "sequential"], default=None)
    parser.add_argument("--linear-retries", type=int, default=None)
    parser.add_argument("--no-engine", action="store_true")
    args = parser.parse_args()

    if args.strategy:
        os.environ["RED_TEAM_JAILBREAK_STRATEGY"] = args.strategy
    if args.linear_retries is not None:
        os.environ["RED_TEAM_LINEAR_RETRIES"] = str(args.linear_retries)
    if args.no_engine:
        os.environ["RED_TEAM_USE_ATTACK_ENGINE"] = "false"

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
