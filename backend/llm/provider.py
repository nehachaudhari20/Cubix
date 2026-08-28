"""
Multi-provider LLM factory.

Environment:
  LLM_PROVIDER=cohere|gemini|bedrock|openai|nvidia|openrouter  (auto-detects based on available API keys)
  RED_TEAM_USE_LLM=true|false
  RED_TEAM_LLM_MODEL=<model id>

Cohere:     COHERE_API_KEY
Gemini:     GOOGLE_API_KEY or GEMINI_API_KEY
OpenAI:     OPENAI_API_KEY
Bedrock:    AWS_REGION, BEDROCK_MODEL_ID
Nvidia:     NVIDIA_API_KEY
OpenRouter: OPENROUTER_API_KEY
"""

from __future__ import annotations

import logging
import os
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


class LLMProvider(str, Enum):
    COHERE = "cohere"
    GEMINI = "gemini"
    BEDROCK = "bedrock"
    OPENAI = "openai"
    NVIDIA = "nvidia"
    OPENROUTER = "openrouter"


def use_llm_enabled() -> bool:
    return os.environ.get("RED_TEAM_USE_LLM", "false").lower() in ("1", "true", "yes")


def _resolve_provider() -> LLMProvider:
    raw = (os.environ.get("LLM_PROVIDER") or "").strip().lower()
    if raw:
        try:
            return LLMProvider(raw)
        except ValueError:
            logger.warning("Unknown LLM_PROVIDER=%r — falling back to auto-detect.", raw)

    if os.environ.get("COHERE_API_KEY"):
        return LLMProvider.COHERE
    if os.environ.get("OPENAI_API_KEY"):
        return LLMProvider.OPENAI
    if os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"):
        return LLMProvider.GEMINI
    if os.environ.get("AWS_REGION") or os.environ.get("BEDROCK_MODEL_ID"):
        return LLMProvider.BEDROCK
    if os.environ.get("NVIDIA_API_KEY"):
        return LLMProvider.NVIDIA
    if os.environ.get("OPENROUTER_API_KEY"):
        return LLMProvider.OPENROUTER
    return LLMProvider.COHERE


def _cohere_api_key() -> Optional[str]:
    return os.environ.get("COHERE_API_KEY") or os.environ.get("COHERE_API_TOKEN")


def get_llm(model: Optional[str] = None, temperature: float = 0.4) -> Any | None:
    """Return a LangChain chat model for the configured provider, or None if disabled."""
    if not use_llm_enabled():
        return None

    provider = _resolve_provider()
    model_id = model or os.environ.get(
        "RED_TEAM_LLM_MODEL",
        _default_model_for(provider),
    )

    try:
        if provider == LLMProvider.COHERE:
            api_key = _cohere_api_key()
            if not api_key:
                logger.warning("RED_TEAM_USE_LLM=true but COHERE_API_KEY is missing.")
                return None
            from langchain_cohere import ChatCohere

            return ChatCohere(
                model=model_id,
                temperature=temperature,
                cohere_api_key=api_key,
            )

        if provider == LLMProvider.GEMINI:
            api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
            if not api_key:
                logger.warning("RED_TEAM_USE_LLM=true but GOOGLE/GEMINI API key is missing.")
                return None
            from langchain_google_genai import ChatGoogleGenerativeAI

            return ChatGoogleGenerativeAI(
                model=model_id,
                temperature=temperature,
                google_api_key=api_key,
            )

        if provider == LLMProvider.OPENAI:
            if not os.environ.get("OPENAI_API_KEY"):
                logger.warning("RED_TEAM_USE_LLM=true but OPENAI_API_KEY is missing.")
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

        if provider == LLMProvider.NVIDIA:
            api_key = os.environ.get("NVIDIA_API_KEY")
            if not api_key:
                logger.warning("RED_TEAM_USE_LLM=true but NVIDIA_API_KEY is missing.")
                return None
            from langchain_nvidia_ai_endpoints import ChatNVIDIA

            return ChatNVIDIA(
                model=model_id,
                api_key=api_key,
                temperature=temperature,
                top_p=0.95,
                max_tokens=16384,
            )

        if provider == LLMProvider.OPENROUTER:
            api_key = os.environ.get("OPENROUTER_API_KEY")
            if not api_key:
                logger.warning("RED_TEAM_USE_LLM=true but OPENROUTER_API_KEY is missing.")
                return None
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model=model_id,
                temperature=temperature,
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1",
                max_tokens=2048,
            )
    except Exception as exc:
        logger.warning("Failed to initialize LLM provider %s: %s", provider.value, exc)
        return None

    return None


def _default_model_for(provider: LLMProvider) -> str:
    if provider == LLMProvider.COHERE:
        return os.environ.get("COHERE_MODEL", "command-r-08-2024")
    if provider == LLMProvider.BEDROCK:
        return os.environ.get(
            "BEDROCK_MODEL_ID",
            "anthropic.claude-3-5-sonnet-20241022-v2:0",
        )
    if provider == LLMProvider.OPENAI:
        return "gpt-4o-mini"
    if provider == LLMProvider.NVIDIA:
        return os.environ.get("NVIDIA_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b")
    if provider == LLMProvider.OPENROUTER:
        return os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o")
    return "gemini-2.0-flash"


def _extract_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text") or block.get("content")
                if text:
                    parts.append(str(text))
            elif hasattr(block, "text"):
                parts.append(str(block.text))
        return "\n".join(parts)
    return str(content)


def invoke_text(llm: Any, system: str, user: str) -> Optional[str]:
    """Invoke a LangChain chat model and return text content."""
    if llm is None:
        return None
    try:
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
        except ImportError:
            from langchain.schema import HumanMessage, SystemMessage  # type: ignore

        response = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        return _extract_text(getattr(response, "content", response))
    except Exception as exc:
        logger.warning("LLM invoke failed: %s", exc)
        return None


def llm_status() -> dict[str, Any]:
    """Diagnostic snapshot for Red Team LLM wiring."""
    provider = _resolve_provider()
    return {
        "enabled": use_llm_enabled(),
        "provider": provider.value,
        "model": os.environ.get("RED_TEAM_LLM_MODEL") or _default_model_for(provider),
        "cohere_key_set": bool(_cohere_api_key()),
        "openai_key_set": bool(os.environ.get("OPENAI_API_KEY")),
        "gemini_key_set": bool(os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")),
        "nvidia_key_set": bool(os.environ.get("NVIDIA_API_KEY")),
        "openrouter_key_set": bool(os.environ.get("OPENROUTER_API_KEY")),
        "client_ready": get_llm() is not None if use_llm_enabled() else False,
    }
