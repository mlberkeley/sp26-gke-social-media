"""
Researcher sub-agent for the multi-agent sentiment pipeline.

Reads its assigned config (focus area, platform hint, custom prompt) from Redis,
generates search queries, executes them via Tavily, analyzes results, and writes
findings back to Redis.

Env vars required:
  OPENAI_API_KEY, TAVILY_API_KEY, RUN_ID, AGENT_INDEX, REDIS_HOST
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from typing import Any

import redis
from langchain_openai import ChatOpenAI
from tavily import TavilyClient

from sp26_gke.workflows.prompts import (
    RESEARCHER_SEARCH_QUERIES_PROMPT,
    SENTIMENT_ANALYSIS_PROMPT,
)

OPENAI_MODEL = "gpt-4o-mini"
TAVILY_MAX_RESULTS_PER_QUERY = 5
REDIS_KEY_TTL = 14400  # 4 hours


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _log(event: str, **fields: object) -> None:
    payload = {"ts": _now_iso(), "event": event, **fields}
    print(json.dumps(payload, default=str), flush=True)


def run() -> int:
    """Run the researcher sub-agent."""
    # Load .env for local testing
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    run_id = os.environ.get("RUN_ID", "")
    agent_index = os.environ.get("AGENT_INDEX", "")
    redis_host = os.environ.get("REDIS_HOST", "localhost")

    if not run_id or not agent_index:
        _log("researcher_error", error="Missing RUN_ID or AGENT_INDEX")
        return 1

    missing = [
        v for v in ("OPENAI_API_KEY", "TAVILY_API_KEY") if not os.environ.get(v)
    ]
    if missing:
        _log("researcher_error", error=f"Missing env vars: {', '.join(missing)}")
        return 1

    _log("researcher_started", run_id=run_id, agent_index=agent_index)

    try:
        r = redis.Redis(host=redis_host, port=6379, decode_responses=True)

        # Read config from Redis
        config_key = f"run:{run_id}:config:{agent_index}"
        config_raw = r.get(config_key)
        if not config_raw:
            _log("researcher_error", error=f"No config found at {config_key}")
            return 1

        config = json.loads(config_raw)
        focus = config.get("focus", "general")
        platform_hint = config.get("platform_hint", "general")
        custom_prompt = config.get("prompt", "")
        topic = config.get("topic", "")

        _log(
            "researcher_config_loaded",
            focus=focus,
            platform_hint=platform_hint,
        )

        llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0.3)

        # Step 1: Generate search queries tailored to this agent's focus
        query_prompt = RESEARCHER_SEARCH_QUERIES_PROMPT.format(
            topic=topic,
            focus=focus,
            platform_hint=platform_hint,
        )
        query_response = llm.invoke(query_prompt)

        try:
            raw = str(query_response.content).strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            queries: list[str] = json.loads(raw)
        except (json.JSONDecodeError, IndexError):
            queries = [
                f"{topic} {focus} site:{platform_hint}",
                f"{topic} {focus} social media discussion",
                f"{topic} {focus} opinions reactions this week",
            ]

        _log("researcher_queries_generated", queries=queries)

        # Step 2: Execute searches via Tavily
        tavily = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
        all_results: list[dict[str, Any]] = []

        for query in queries[:3]:
            try:
                response = tavily.search(
                    query=query,
                    max_results=TAVILY_MAX_RESULTS_PER_QUERY,
                    search_depth="advanced",
                    include_raw_content=False,
                )
                for result in response.get("results", []):
                    all_results.append(
                        {
                            "title": result.get("title", ""),
                            "url": result.get("url", ""),
                            "content": result.get("content", ""),
                            "score": result.get("score", 0),
                        }
                    )
            except Exception as exc:
                _log("researcher_search_error", query=query, error=str(exc))

        _log("researcher_search_completed", result_count=len(all_results))

        # Step 3: Analyze sentiment
        search_results_str = json.dumps(all_results, indent=2, default=str)
        analysis_prompt = SENTIMENT_ANALYSIS_PROMPT.format(
            topic=f"{topic} — focus: {focus}",
            search_results=search_results_str,
        )
        analysis_response = llm.invoke(analysis_prompt)
        analysis = str(analysis_response.content).strip()

        _log("researcher_analysis_completed", analysis_length=len(analysis))

        # Step 4: Write results to Redis
        result_data = {
            "focus": focus,
            "platform_hint": platform_hint,
            "custom_prompt": custom_prompt,
            "search_queries": queries[:3],
            "search_result_count": len(all_results),
            "analysis": analysis,
        }
        result_key = f"run:{run_id}:result:{agent_index}"
        r.set(result_key, json.dumps(result_data, default=str), ex=REDIS_KEY_TTL)

        _log("researcher_completed", run_id=run_id, agent_index=agent_index)
        return 0

    except Exception as exc:
        _log("researcher_error", error=str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(run())
