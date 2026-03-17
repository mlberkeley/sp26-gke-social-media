"""
Sentiment analysis agent — role-based entry point.

Uses the AGENT_ROLE env var to dispatch to the appropriate module:
  - "orchestrator" → plans sub-agents, spawns K8s Jobs, reads final report
  - "researcher"   → searches + analyzes for a specific focus area
  - "synthesizer"  → merges all researcher results into one report
  - "standalone"   → runs the original single-agent pipeline (no Redis/K8s)

Usage:
  # Local standalone (no Redis needed):
  pixi run sentiment-agent

  # Multi-agent on K8s (set via env vars in Job manifests):
  AGENT_ROLE=orchestrator ...
  AGENT_ROLE=researcher ...
  AGENT_ROLE=synthesizer ...
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from typing import Any, cast

from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from tavily import TavilyClient
from typing_extensions import TypedDict

from sp26_gke.workflows.prompts import (
    REPORT_GENERATION_PROMPT,
    SEARCH_QUERIES_PROMPT,
    SENTIMENT_ANALYSIS_PROMPT,
)

# ── Default configuration ────────────────────────────────────────────────
DEFAULT_TOPIC = "latest hot topics in AI"
OPENAI_MODEL = "gpt-4o-mini"
TAVILY_MAX_RESULTS_PER_QUERY = 5


# ── Structured log helper ────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _log(event: str, **fields: object) -> None:
    payload = {"ts": _now_iso(), "event": event, **fields}
    print(json.dumps(payload, default=str), flush=True)


# ── LangGraph state ──────────────────────────────────────────────────────


class AgentState(TypedDict, total=False):
    topic: str
    search_queries: list[str]
    search_results: str
    sentiment_analysis: str
    final_report: str
    timestamp: str
    error: str


# ── Node functions (standalone mode) ─────────────────────────────────────


def research_topic(state: AgentState) -> dict[str, Any]:
    """Search X/social media for recent posts on the topic via Tavily."""
    topic = state["topic"]
    _log("research_started", topic=topic)

    tavily_key = os.environ["TAVILY_API_KEY"]

    # Step 1 — ask the LLM to generate targeted search queries
    llm = ChatOpenAI(
        model=OPENAI_MODEL,
        temperature=0.3,
    )
    query_prompt = SEARCH_QUERIES_PROMPT.format(topic=topic)
    query_response = llm.invoke(query_prompt)

    # Parse the JSON array of queries from the response
    try:
        raw = str(query_response.content).strip()
        # Handle markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        queries: list[str] = json.loads(raw)
    except (json.JSONDecodeError, IndexError):
        # Fallback: use simple default queries
        queries = [
            f"{topic} site:x.com",
            f"{topic} social media discussion",
            f"{topic} opinions reactions this week",
        ]

    _log("search_queries_generated", queries=queries)

    # Step 2 — execute each query with Tavily
    tavily = TavilyClient(api_key=tavily_key)
    all_results: list[dict[str, Any]] = []

    for query in queries[:3]:  # strictly limit to 3
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
            _log("search_query_error", query=query, error=str(exc))

    _log("research_completed", result_count=len(all_results))

    return {
        "search_queries": queries[:3],
        "search_results": json.dumps(all_results, indent=2, default=str),
    }


def analyze_sentiment(state: AgentState) -> dict[str, Any]:
    """Deeply analyse sentiment from the search results."""
    _log("analysis_started")

    llm = ChatOpenAI(
        model=OPENAI_MODEL,
        temperature=0.2,
    )

    prompt = SENTIMENT_ANALYSIS_PROMPT.format(
        topic=state["topic"],
        search_results=state["search_results"],
    )
    response = llm.invoke(prompt)
    analysis = str(response.content).strip()

    _log("analysis_completed", analysis_length=len(analysis))
    return {"sentiment_analysis": analysis}


def generate_report(state: AgentState) -> dict[str, Any]:
    """Produce the final polished sentiment report."""
    _log("report_generation_started")

    llm = ChatOpenAI(
        model=OPENAI_MODEL,
        temperature=0.4,
    )

    prompt = REPORT_GENERATION_PROMPT.format(
        topic=state["topic"],
        timestamp=state["timestamp"],
        sentiment_analysis=state["sentiment_analysis"],
    )
    response = llm.invoke(prompt)
    report = str(response.content).strip()

    _log("report_generation_completed", report_length=len(report))
    return {"final_report": report}


# ── Graph assembly ───────────────────────────────────────────────────────


def build_graph() -> StateGraph:
    """Build the 3-node LangGraph pipeline."""
    graph = StateGraph(AgentState)

    graph.add_node("research_topic", research_topic)
    graph.add_node("analyze_sentiment", analyze_sentiment)
    graph.add_node("generate_report", generate_report)

    graph.set_entry_point("research_topic")
    graph.add_edge("research_topic", "analyze_sentiment")
    graph.add_edge("analyze_sentiment", "generate_report")
    graph.add_edge("generate_report", END)

    return graph


# ── Standalone mode ──────────────────────────────────────────────────────


def _run_standalone() -> int:
    """Run the original single-agent pipeline (no Redis, no K8s)."""
    missing = [
        var for var in ("OPENAI_API_KEY", "TAVILY_API_KEY") if not os.environ.get(var)
    ]
    if missing:
        _log("agent_error", error=f"Missing env vars: {', '.join(missing)}")
        return 1

    topic = os.environ.get("SENTIMENT_TOPIC", DEFAULT_TOPIC)
    timestamp = _now_iso()

    _log("agent_started", topic=topic, model=OPENAI_MODEL, mode="standalone")

    try:
        graph = build_graph()
        app = graph.compile()

        initial_state: AgentState = {
            "topic": topic,
            "timestamp": timestamp,
        }
        result = app.invoke(cast(Any, initial_state))

        # Print the final report prominently
        print("\n" + "=" * 80, flush=True)
        print("SENTIMENT REPORT", flush=True)
        print("=" * 80, flush=True)
        print(f"Topic: {topic}", flush=True)
        print(f"Generated: {timestamp}", flush=True)
        print("=" * 80 + "\n", flush=True)
        print(result["final_report"], flush=True)
        print("\n" + "=" * 80, flush=True)

        _log("agent_completed", topic=topic)
        return 0

    except Exception as exc:
        _log("agent_error", error=str(exc))
        return 1


# ── Entry point (role dispatcher) ────────────────────────────────────────


def run() -> int:
    """
    Dispatch to the appropriate agent based on AGENT_ROLE.

    Returns 0 on success, 1 on error.
    """
    # Load .env file if present (for local runs outside Makefile)
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    role = os.environ.get("AGENT_ROLE", "standalone")

    if role == "orchestrator":
        from sp26_gke.workflows.orchestrator import run as orchestrator_run

        return orchestrator_run()
    elif role == "researcher":
        from sp26_gke.workflows.researcher import run as researcher_run

        return researcher_run()
    elif role == "synthesizer":
        from sp26_gke.workflows.synthesizer import run as synthesizer_run

        return synthesizer_run()
    else:
        # Default: run the standalone single-agent pipeline
        return _run_standalone()


if __name__ == "__main__":
    sys.exit(run())
