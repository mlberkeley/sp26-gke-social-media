"""
Worker agent for the multi-agent sentiment pipeline.

Each worker defends a single stance for a single run. Internally it performs
two phases: researcher (evidence gathering via Tavily) and advocate (building
a persuasive case from the evidence). After research completes, the worker
starts a FastAPI server so the judge can send interrogation questions over HTTP.

Env vars required:
  OPENAI_API_KEY, TAVILY_API_KEY, RUN_ID, STANCE_ID, STANCE_LABEL, TOPIC,
  REDIS_HOST
Optional:
  WORKER_PORT (default: 8080)
"""

from __future__ import annotations

import json
import os
import signal
import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import uvicorn
from fastapi import FastAPI

from sp26_gke.workflows.llm import create_client, invoke_json, invoke_text
from sp26_gke.workflows.prompts import (
    WORKER_ADVOCATE_PROMPT,
    WORKER_INTERROGATION_RESPONSE_PROMPT,
    WORKER_RESEARCH_ANALYSIS_PROMPT,
    WORKER_RESEARCH_QUERIES_PROMPT,
)
from sp26_gke.workflows.redis_state import RedisState
from sp26_gke.workflows.schemas import (
    InterrogationRequest,
    InterrogationResponse,
    WorkerOutput,
)
from sp26_gke.workflows.search import create_client as create_tavily
from sp26_gke.workflows.search import execute_queries

WORKER_PORT = 8080


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _log(event: str, **fields: object) -> None:
    payload = {"ts": _now_iso(), "event": event, **fields}
    print(json.dumps(payload, default=str), flush=True)


def _research_phase(
    topic: str,
    stance_label: str,
    stance_description: str,
) -> dict[str, Any]:
    """Gather evidence via Tavily search and analyze it."""
    llm = create_client(temperature=0.3)
    tavily = create_tavily()

    query_prompt = WORKER_RESEARCH_QUERIES_PROMPT.format(
        topic=topic,
        stance_label=stance_label,
        stance_description=stance_description,
    )
    queries = invoke_json(
        llm,
        query_prompt,
        fallback=[
            f"{topic} {stance_label} evidence support",
            f"{topic} {stance_label} counterarguments criticism",
            f"{topic} {stance_label} community opinions",
        ],
    )
    _log("worker_queries_generated", queries=queries)

    results = execute_queries(tavily, queries[:3])
    _log("worker_search_completed", result_count=len(results))

    analysis_prompt = WORKER_RESEARCH_ANALYSIS_PROMPT.format(
        topic=topic,
        stance_label=stance_label,
        stance_description=stance_description,
        search_results=json.dumps(results, indent=2, default=str),
    )
    research_findings = invoke_json(
        llm,
        analysis_prompt,
        fallback={
            "supporting_evidence": [],
            "counterarguments": [],
            "community_patterns": [],
            "key_sources": [],
            "evidence_strength": "weak",
            "raw_claims": [],
        },
    )
    _log("worker_research_completed")
    return research_findings


def _advocate_phase(
    topic: str,
    stance_label: str,
    stance_description: str,
    research_findings: dict[str, Any],
    run_id: str,
    stance_id: str,
) -> WorkerOutput:
    """Build a persuasive case from the research findings."""
    llm = create_client(temperature=0.4)

    advocate_prompt = WORKER_ADVOCATE_PROMPT.format(
        topic=topic,
        stance_label=stance_label,
        stance_description=stance_description,
        research_findings=json.dumps(research_findings, indent=2, default=str),
    )
    raw_output = invoke_json(
        llm,
        advocate_prompt,
        fallback={
            "summary": f"Advocate analysis for {stance_label} stance",
            "top_claims": [],
            "crossover_positions": [],
            "antagonistic_positions": [],
            "fringe_positions": [],
            "consensus_points": [],
            "axes_of_debate": [],
            "confidence": 0.0,
        },
    )

    raw_output["run_id"] = run_id
    raw_output["stance_id"] = stance_id
    raw_output["stance_label"] = stance_label
    raw_output["key_sources"] = research_findings.get("key_sources", [])

    return WorkerOutput.model_validate(raw_output)


def _answer_interrogation(
    topic: str,
    stance_label: str,
    worker_output: dict[str, Any],
    question: str,
) -> str:
    """Answer a judge's interrogation question."""
    llm = create_client(temperature=0.3)
    prompt = WORKER_INTERROGATION_RESPONSE_PROMPT.format(
        topic=topic,
        stance_label=stance_label,
        worker_output=json.dumps(worker_output, indent=2, default=str),
        question=question,
    )
    return invoke_text(llm, prompt)


def _create_app(
    topic: str,
    stance_id: str,
    stance_label: str,
    worker_output_dict: dict[str, Any],
    server_handle: dict[str, Any],
) -> FastAPI:
    """Build the FastAPI app for serving interrogation requests."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield

    app = FastAPI(title=f"Worker {stance_id}", lifespan=lifespan)

    @app.get("/.well-known/agent-card.json")
    def agent_card() -> dict[str, object]:
        return {
            "name": f"worker-{stance_id}",
            "description": f"Sentiment worker defending the {stance_label} stance",
            "capabilities": ["interrogation"],
            "stance_id": stance_id,
            "stance_label": stance_label,
        }

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "serving"}

    @app.post("/interrogate")
    def interrogate(req: InterrogationRequest) -> InterrogationResponse:
        answer = _answer_interrogation(
            topic=topic,
            stance_label=stance_label,
            worker_output=worker_output_dict,
            question=req.question,
        )
        return InterrogationResponse(answer=answer)

    @app.post("/shutdown")
    def shutdown() -> dict[str, str]:
        _log("worker_shutdown_requested", stance_id=stance_id)
        os.kill(os.getpid(), signal.SIGTERM)
        return {"status": "shutting_down"}

    return app


def run() -> int:
    """Run the worker agent: research, advocate, then serve interrogation."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    run_id = os.environ.get("RUN_ID", "")
    stance_id = os.environ.get("STANCE_ID", "")
    stance_label = os.environ.get("STANCE_LABEL", "")
    topic = os.environ.get("TOPIC", "")
    redis_host = os.environ.get("REDIS_HOST", "localhost")
    port = int(os.environ.get("WORKER_PORT", str(WORKER_PORT)))

    missing_vars = []
    for var in ("OPENAI_API_KEY", "TAVILY_API_KEY"):
        if not os.environ.get(var):
            missing_vars.append(var)
    for var, val in [
        ("RUN_ID", run_id),
        ("STANCE_ID", stance_id),
        ("STANCE_LABEL", stance_label),
        ("TOPIC", topic),
    ]:
        if not val:
            missing_vars.append(var)
    if missing_vars:
        _log("worker_error", error=f"Missing env vars: {', '.join(missing_vars)}")
        return 1

    _log(
        "worker_started", run_id=run_id, stance_id=stance_id, stance_label=stance_label
    )

    state = RedisState(host=redis_host)
    state.ping()
    state.set_worker_status(run_id, stance_id, "running")

    # Read stance description from judge plan
    plan = state.get_judge_plan(run_id)
    stance_description = ""
    if plan:
        for stance in plan.get("stances", []):
            if stance.get("stance_id") == stance_id:
                stance_description = stance.get("description", "")
                break
    if not stance_description:
        stance_description = f"Defend the {stance_label} position on: {topic}"

    _log("worker_research_phase", stance_description=stance_description)
    research_findings = _research_phase(topic, stance_label, stance_description)

    _log("worker_advocate_phase")
    output = _advocate_phase(
        topic, stance_label, stance_description, research_findings, run_id, stance_id
    )

    worker_output_dict = output.model_dump()
    state.set_worker_result(run_id, stance_id, worker_output_dict)
    state.set_worker_status(run_id, stance_id, "serving")

    _log(
        "worker_research_complete_starting_server",
        run_id=run_id,
        stance_id=stance_id,
        port=port,
    )

    # Start FastAPI server for interrogation
    server_handle: dict[str, Any] = {}
    app = _create_app(topic, stance_id, stance_label, worker_output_dict, server_handle)

    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")

    _log("worker_completed", run_id=run_id, stance_id=stance_id)
    return 0


if __name__ == "__main__":
    sys.exit(run())
