"""
Summarizer agent for the multi-agent sentiment pipeline.

Takes the judge's aggregate output and produces the final polished report
in both JSON and markdown formats.

Env vars required:
  OPENAI_API_KEY, RUN_ID, REDIS_HOST
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime

from sp26_gke.workflows.llm import create_client, invoke_text
from sp26_gke.workflows.prompts import SUMMARIZER_PROMPT
from sp26_gke.workflows.redis_state import RedisState


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _log(event: str, **fields: object) -> None:
    payload = {"ts": _now_iso(), "event": event, **fields}
    print(json.dumps(payload, default=str), flush=True)


def run() -> int:
    """Run the summarizer agent."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    run_id = os.environ.get("RUN_ID", "")
    redis_host = os.environ.get("REDIS_HOST", "localhost")
    topic = os.environ.get("TOPIC", "")

    if not run_id:
        _log("summarizer_error", error="Missing RUN_ID")
        return 1
    if not os.environ.get("OPENAI_API_KEY"):
        _log("summarizer_error", error="Missing OPENAI_API_KEY")
        return 1

    _log("summarizer_started", run_id=run_id)

    state = RedisState(host=redis_host)
    state.ping()
    state.set_summarizer_status(run_id, "running")

    if not topic:
        meta = state.get_run_meta(run_id)
        topic = meta.get("topic", "Unknown topic") if meta else "Unknown topic"

    aggregate = state.get_judge_aggregate(run_id)
    if not aggregate:
        _log("summarizer_error", error="No judge aggregate found in Redis")
        return 1

    _log("summarizer_generating_report")

    llm = create_client(temperature=0.4)
    prompt = SUMMARIZER_PROMPT.format(
        topic=topic,
        judge_aggregate=json.dumps(aggregate, indent=2, default=str),
    )
    raw_response = invoke_text(llm, prompt)

    # Split JSON and markdown sections
    if "===MARKDOWN===" in raw_response:
        json_part, md_part = raw_response.split("===MARKDOWN===", 1)
    else:
        json_part = ""
        md_part = raw_response

    # Parse the JSON portion
    report_json: dict[str, object] = {}
    json_part = json_part.strip()
    if json_part:
        if json_part.startswith("```"):
            json_part = json_part.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        try:
            report_json = json.loads(json_part)
        except json.JSONDecodeError:
            _log("summarizer_json_parse_warning", raw_length=len(json_part))

    report_md = md_part.strip()

    state.set_final_report(run_id, report_json)
    state.set_final_report_md(run_id, report_md)
    state.set_summarizer_status(run_id, "complete")

    print("\n" + "=" * 80, flush=True)
    print("FINAL SENTIMENT DEBATE REPORT", flush=True)
    print("=" * 80, flush=True)
    print(f"Topic: {topic}", flush=True)
    print(f"Run ID: {run_id}", flush=True)
    print("=" * 80 + "\n", flush=True)
    print(report_md, flush=True)
    print("\n" + "=" * 80, flush=True)

    _log("summarizer_completed", run_id=run_id)
    return 0


if __name__ == "__main__":
    sys.exit(run())
