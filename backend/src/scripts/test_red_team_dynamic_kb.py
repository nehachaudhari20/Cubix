"""
Dynamic KB -> Red Team -> Sandbox continuous test.

Prefer: PYTHONPATH=src python src/scripts/run_red_team_continuous.py
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("RED_TEAM_USE_LLM", "false")
os.environ.setdefault("USE_KB_API", "false")

from backend.red_team.runner import run_continuous


def main():
    parser = argparse.ArgumentParser(description="Dynamic KB Red Team Sandbox test")
    parser.add_argument("--families", type=int, default=5)
    parser.add_argument("--family", type=str, default=None)
    parser.add_argument("--strategy", choices=["kb", "crescendo", "tree", "sequential"], default=None)
    args = parser.parse_args()
    if args.strategy:
        os.environ["RED_TEAM_JAILBREAK_STRATEGY"] = args.strategy
    run_continuous(max_families=args.families, family_id=args.family)


if __name__ == "__main__":
    main()
