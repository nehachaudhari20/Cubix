"""
Multi-provider LLM factory.

Environment:
  LLM_PROVIDER=gemini|bedrock|openai  (default: gemini)
  RED_TEAM_USE_LLM=true|false
  RED_TEAM_LLM_MODEL=<model id>

Gemini:  GOOGLE_API_KEY or GEMINI_API_KEY
OpenAI:  OPENAI_API_KEY
Bedrock: AWS_REGION, BEDROCK_MODEL_ID (e.g. anthropic.claude-3-5-sonnet-20241022-v2:0)
         Requires langchain-aws and AWS credentials (IAM role on SageMaker/ECS later).
"""

from __future__ import annotations

import os
from enum import Enum
from typing import Any, Optional


class LLMProvider(str, Enum):
    GEMINI = "gemini"
    BEDROCK = "bedrock"
    OPENAI = "openai"


def _use_llm_enabled() -> bool:
    return os.environ.get("RED_TEAM_USE_LLM", "false").lower() in ("1", "true", "yes")


def _resolve_provider() -> LLMProvider:
    raw = (os.environ.get("LLM_PROVIDER") or "gemini").strip().lower()
    try:
        return LLMProvider(raw)
    except ValueError:
        return LLMProvider.GEMINI


def get_llm(model: Optional[str] = None, temperature: float = 0.4) -> Any | None:
    """Return a LangChain chat model for the configured provider, or None if disabled."""
    if not _use_llm_enabled():
        return None

    provider = _resolve_provider()
    model_id = model or os.environ.get(
        "RED_TEAM_LLM_MODEL",
        _default_model_for(provider),
    )

    try:
        if provider == LLMProvider.GEMINI:
            api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
            if not api_key:
                return None
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(model=model_id, temperature=temperature, google_api_key=api_key)

        if provider == LLMProvider.OPENAI:
            if not os.environ.get("OPENAI_API_KEY"):
                return None
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(model=model_id, temperature=temperature)

        if provider == LLMProvider.BEDROCK:
            region = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
            try:
                from langchain_aws import ChatBedrockConverse
                return ChatBedrockConverse(
                    model=model_id,
                    region_name=region,
                    temperature=temperature,
                )
            except ImportError:
                from langchain_community.chat_models import BedrockChat
                return BedrockChat(
                    model_id=model_id,
                    region_name=region,
                    model_kwargs={"temperature": temperature},
                )
    except Exception:
        return None

    return None


def _default_model_for(provider: LLMProvider) -> str:
    if provider == LLMProvider.BEDROCK:
        return os.environ.get(
            "BEDROCK_MODEL_ID",
            "anthropic.claude-3-5-sonnet-20241022-v2:0",
        )
    if provider == LLMProvider.OPENAI:
        return "gpt-4o-mini"
    return "gemini-2.0-flash"


def invoke_text(llm: Any, system: str, user: str) -> Optional[str]:
    """Invoke a LangChain chat model and return text content."""
    if llm is None:
        return None
    try:
        from langchain.schema import HumanMessage, SystemMessage
        response = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        return getattr(response, "content", str(response))
    except Exception:
        return None
