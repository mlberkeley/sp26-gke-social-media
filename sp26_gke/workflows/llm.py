"""
LLM client wrapper.

Wraps OpenAI via langchain-openai. Kept thin and generalizable so the backend can be
swapped later (per REFACTOR.md section 16).
"""

from __future__ import annotations

import json
from typing import Any

from langchain_openai import ChatOpenAI

DEFAULT_MODEL = "gpt-5.4-mini"


def create_client(model: str = DEFAULT_MODEL, temperature: float = 0.3) -> ChatOpenAI:
    """
    Create a ChatOpenAI client.

    Reads OPENAI_API_KEY from env.
    """
    return ChatOpenAI(model=model, temperature=temperature)


def invoke_json(client: ChatOpenAI, prompt: str, fallback: Any = None) -> Any:
    """
    Invoke the LLM and parse the response as JSON.

    Strips markdown code fences if present. Returns *fallback* when parsing fails and a
    fallback was provided, otherwise raises.
    """
    response = client.invoke(prompt)
    raw = str(response.content).strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, IndexError):
        if fallback is not None:
            return fallback
        raise


def invoke_text(client: ChatOpenAI, prompt: str) -> str:
    """Invoke the LLM and return the raw text response."""
    response = client.invoke(prompt)
    return str(response.content).strip()
