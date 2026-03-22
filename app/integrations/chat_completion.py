"""
Unified chat completion: Google Gemini (GCP / AI Studio) first, then OpenAI.
No Azure OpenAI — use GEMINI_API_KEY from https://aistudio.google.com/apikey
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional

from openai import OpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)


def _messages_to_prompt(messages: List[Dict[str, str]]) -> str:
    parts: List[str] = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            parts.append(f"### System instructions\n{content}")
        elif role == "user":
            parts.append(f"### User\n{content}")
        else:
            parts.append(f"### {role.capitalize()}\n{content}")
    return "\n\n".join(parts)


def _gemini_complete_sync(
    api_key: str,
    model_name: str,
    prompt: str,
    json_mode: bool,
    max_output_tokens: Optional[int],
) -> str:
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    gen_cfg = None
    if json_mode:
        gen_cfg = genai.GenerationConfig(
            response_mime_type="application/json",
            max_output_tokens=max_output_tokens or 2048,
        )
    elif max_output_tokens:
        gen_cfg = genai.GenerationConfig(max_output_tokens=max_output_tokens)

    model = genai.GenerativeModel(model_name)
    response = model.generate_content(prompt, generation_config=gen_cfg)
    try:
        text = (response.text or "").strip()
    except Exception:
        text = ""
    if not text and getattr(response, "candidates", None):
        # Blocked or empty finish reason
        logger.warning("Gemini returned no text (safety or empty candidate).")
    return text


def _openai_complete_sync(
    api_key: str,
    model_name: str,
    messages: List[Dict[str, str]],
    json_mode: bool,
    max_output_tokens: Optional[int],
) -> str:
    client = OpenAI(api_key=api_key)
    kwargs: dict = {"model": model_name, "messages": messages}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    if max_output_tokens:
        kwargs["max_tokens"] = max_output_tokens
    resp = client.chat.completions.create(**kwargs)
    return (resp.choices[0].message.content or "").strip()


async def chat_complete(
    messages: List[Dict[str, str]],
    *,
    json_mode: bool = False,
    max_output_tokens: Optional[int] = None,
) -> Optional[str]:
    """
    Returns assistant text, or None if no LLM is configured.
    Prefers Gemini when GEMINI_API_KEY (or GOOGLE_AI_API_KEY) is set.
    """
    s = get_settings()
    gemini_key = (s.gemini_api_key or "").strip()
    openai_key = (s.openai_api_key or "").strip()

    if gemini_key:
        prompt = _messages_to_prompt(messages)
        try:
            return await asyncio.to_thread(
                _gemini_complete_sync,
                gemini_key,
                s.gemini_model,
                prompt,
                json_mode,
                max_output_tokens,
            )
        except Exception:
            logger.exception("Gemini completion failed")
            return None

    if openai_key:
        try:
            return await asyncio.to_thread(
                _openai_complete_sync,
                openai_key,
                s.openai_model,
                messages,
                json_mode,
                max_output_tokens,
            )
        except Exception:
            logger.exception("OpenAI completion failed")
            return None

    return None
