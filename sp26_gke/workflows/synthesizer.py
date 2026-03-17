"""
Synthesizer agent for the multi-agent sentiment pipeline.

Reads all researcher results from Redis, calls LLM to produce a unified
sentiment report, and writes the report back to Redis (also prints to stdout).

Env vars required:
  OPENAI_API_KEY, RUN_ID, REDIS_HOST
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime

import redis
from langchain_openai import ChatOpenAI

from sp26_gke.workflows.prompts import SYNTHESIZER_PROMPT

OPENAI_MODEL = "gpt-4o-mini"
REDIS_KEY_TTL = 14400  # 4 hours


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _log(event: str, **fields: object) -> None:
    payload = {"ts": _now_iso(), "event": event, **fields}
    print(json.dumps(payload, default=str), flush=True)


def run() -> int:
    """Run the synthesizer agent."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    run_id = os.environ.get("RUN_ID", "")
    redis_host = os.environ.get("REDIS_HOST", "localhost")
    topic = os.environ.get("SENTIMENT_TOPIC", "")

    if not run_id:
        _log("synthesizer_error", error="Missing RUN_ID")
        return 1

    if not os.environ.get("OPENAI_API_KEY"):
        _log("synthesizer_error", error="Missing OPENAI_API_KEY")
        return 1

    _log("synthesizer_started", run_id=run_id)

    try:
        r = redis.Redis(host=redis_host, port=6379, decode_responses=True)

        # Read agent count
        agent_count_raw = r.get(f"run:{run_id}:agent_count")
        if not agent_count_raw:
            _log("synthesizer_error", error="No agent_count found in Redis")
            return 1

        agent_count = int(agent_count_raw)
        _log("synthesizer_reading_results", agent_count=agent_count)

        # Collect all researcher results
        all_results_parts: list[str] = []
        for idx in range(agent_count):
            result_key = f"run:{run_id}:result:{idx}"
            result_raw = r.get(result_key)
            if result_raw:
                result_data = json.loads(result_raw)
                focus = result_data.get("focus", f"Agent {idx}")
                analysis = result_data.get("analysis", "No analysis available")
                all_results_parts.append(
                    f"### Agent {idx}: {focus}\n"
                    f"**Search queries:** {result_data.get('search_queries', [])}\n"
                    f"**Results found:** {result_data.get('search_result_count', 0)}\n"
                    f"**Analysis:**\n{analysis}\n"
                )
            else:
                all_results_parts.append(
                    f"### Agent {idx}\n**Status:** No results (may have failed)\n"
                )

        all_results_text = "\n---\n".join(all_results_parts)
        _log("synthesizer_results_collected", total_agents=agent_count)

        # Generate the unified report
        llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0.4)

        if not topic:
            topic_raw = r.get(f"run:{run_id}:topic")
            topic = topic_raw if topic_raw else "Unknown topic"

        timestamp = _now_iso()
        prompt = SYNTHESIZER_PROMPT.format(
            topic=topic,
            timestamp=timestamp,
            agent_count=agent_count,
            all_results=all_results_text,
        )
        response = llm.invoke(prompt)
        report = str(response.content).strip()

        _log("synthesizer_report_generated", report_length=len(report))

        # Write report to Redis
        r.set(f"run:{run_id}:report", report, ex=REDIS_KEY_TTL)

        # Also print the report to stdout
        print("\n" + "=" * 80, flush=True)
        print("SENTIMENT REPORT (MULTI-AGENT)", flush=True)
        print("=" * 80, flush=True)
        print(f"Topic: {topic}", flush=True)
        print(f"Generated: {timestamp}", flush=True)
        print(f"Agents: {agent_count}", flush=True)
        print("=" * 80 + "\n", flush=True)
        print(report, flush=True)
        print("\n" + "=" * 80, flush=True)

        _log("synthesizer_completed", run_id=run_id)
        return 0

    except Exception as exc:
        _log("synthesizer_error", error=str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(run())
