"""
Sentiment analysis agent — role-based entry point.

Uses the AGENT_ROLE env var to dispatch to the appropriate module:
  - "judge"       → plans stances, spawns workers, interrogates, aggregates
  - "worker"      → researches + advocates for assigned stance
  - "summarizer"  → produces final report from judge aggregate

Usage:
  # Multi-agent on K8s (set via env vars in Job manifests):
  AGENT_ROLE=judge ...
  AGENT_ROLE=worker ...
  AGENT_ROLE=summarizer ...

  # Default (no AGENT_ROLE): runs judge
  pixi run sentiment-agent
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _log(event: str, **fields: object) -> None:
    payload = {"ts": _now_iso(), "event": event, **fields}
    print(json.dumps(payload, default=str), flush=True)


def run() -> int:
    """Dispatch to the appropriate agent based on AGENT_ROLE."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    role = os.environ.get("AGENT_ROLE", "judge")

    match role:
        case "judge":
            from sp26_gke.workflows.judge import run as judge_run

            return judge_run()
        case "worker":
            from sp26_gke.workflows.worker import run as worker_run

            return worker_run()
        case "summarizer":
            from sp26_gke.workflows.summarizer import run as summarizer_run

            return summarizer_run()
        case _:
            _log("unknown_role", role=role)
            return 1


if __name__ == "__main__":
    sys.exit(run())
