"""
Redis state manager for the multi-agent sentiment pipeline.

Implements the key schema from REFACTOR.md section 10.
"""

from __future__ import annotations

import json
from typing import Any, cast

import redis as redis_lib

KEY_TTL = 14400  # 4 hours


class RedisState:
    """Thin wrapper around Redis for run-scoped state management."""

    def __init__(self, host: str, port: int = 6379) -> None:
        self._r = redis_lib.Redis(host=host, port=port, decode_responses=True)

    def ping(self) -> bool:
        return cast(bool, self._r.ping())

    def _set_json(self, key: str, data: Any) -> None:
        self._r.set(key, json.dumps(data, default=str), ex=KEY_TTL)

    def _get_json(self, key: str) -> Any | None:
        raw = cast(str | None, self._r.get(key))
        if raw is None:
            return None
        return json.loads(raw)

    def set_run_meta(self, run_id: str, meta: dict[str, Any]) -> None:
        self._set_json(f"run:{run_id}:meta", meta)

    def get_run_meta(self, run_id: str) -> dict[str, Any] | None:
        return self._get_json(f"run:{run_id}:meta")

    def set_judge_plan(self, run_id: str, plan: dict[str, Any]) -> None:
        self._set_json(f"run:{run_id}:judge:plan", plan)

    def get_judge_plan(self, run_id: str) -> dict[str, Any] | None:
        return self._get_json(f"run:{run_id}:judge:plan")

    def set_judge_interrogation(self, run_id: str, data: list[dict[str, Any]]) -> None:
        self._set_json(f"run:{run_id}:judge:interrogation", data)

    def get_judge_interrogation(self, run_id: str) -> list[dict[str, Any]] | None:
        return self._get_json(f"run:{run_id}:judge:interrogation")

    def set_judge_aggregate(self, run_id: str, data: dict[str, Any]) -> None:
        self._set_json(f"run:{run_id}:judge:aggregate", data)

    def get_judge_aggregate(self, run_id: str) -> dict[str, Any] | None:
        return self._get_json(f"run:{run_id}:judge:aggregate")

    def set_worker_status(self, run_id: str, worker_id: str, status: str) -> None:
        self._r.set(f"run:{run_id}:worker:{worker_id}:status", status, ex=KEY_TTL)

    def get_worker_status(self, run_id: str, worker_id: str) -> str | None:
        return cast(str | None, self._r.get(f"run:{run_id}:worker:{worker_id}:status"))

    def set_worker_result(
        self, run_id: str, worker_id: str, result: dict[str, Any]
    ) -> None:
        self._set_json(f"run:{run_id}:worker:{worker_id}:result", result)

    def get_worker_result(self, run_id: str, worker_id: str) -> dict[str, Any] | None:
        return self._get_json(f"run:{run_id}:worker:{worker_id}:result")

    def set_summarizer_status(self, run_id: str, status: str) -> None:
        self._r.set(f"run:{run_id}:summarizer:status", status, ex=KEY_TTL)

    def set_final_report(self, run_id: str, report_json: dict[str, Any]) -> None:
        self._set_json(f"run:{run_id}:final_report", report_json)

    def get_final_report(self, run_id: str) -> dict[str, Any] | None:
        return self._get_json(f"run:{run_id}:final_report")

    def set_final_report_md(self, run_id: str, report_md: str) -> None:
        self._r.set(f"run:{run_id}:final_report_md", report_md, ex=KEY_TTL)

    def get_final_report_md(self, run_id: str) -> str | None:
        return cast(str | None, self._r.get(f"run:{run_id}:final_report_md"))
