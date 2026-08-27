"""Quick connectivity check for Red Team LLM (Cohere by default)."""

import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.llm import get_llm, invoke_text, llm_status


def main() -> None:
    status = llm_status()
    print(json.dumps(status, indent=2))
    if not status["enabled"]:
        print("\nSet RED_TEAM_USE_LLM=true in .env")
        sys.exit(1)
    if not status["client_ready"]:
        print("\nLLM client not ready — check COHERE_API_KEY and LLM_PROVIDER")
        sys.exit(1)

    llm = get_llm()
    reply = invoke_text(llm, "You are a fraud analyst.", "Reply with exactly: LLM_OK")
    print(f"\nSample reply: {reply!r}")
    sys.exit(0 if reply and "LLM_OK" in reply.upper() else 2)


if __name__ == "__main__":
    main()
