"""
Judge agent for the multi-agent sentiment pipeline.

Orchestrates the full run lifecycle:
  1. Tavily search to estimate topic breadth and polarization
  2. Determine worker roster (stance plan)
  3. Spawn worker K8s Jobs + ClusterIP Services
  4. Poll until workers are serving (research done, HTTP server up)
  5. Interrogation phase — send targeted questions to workers via HTTP
  6. Aggregation — combine all evidence into aggregate output
  7. Shutdown workers
  8. Spawn summarizer K8s Job
  9. Read and print final report

Env vars required:
  OPENAI_API_KEY, TAVILY_API_KEY, REDIS_HOST, SENTIMENT_IMAGE
Optional:
  TOPIC (default: "latest hot topics in AI")
  K8S_NAMESPACE (default: "default")
  MAX_INTERROGATION_ROUNDS (default: 3)
  WORKER_PORT (default: 8080)
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from kubernetes import client as k8s_client
from kubernetes import config as k8s_config

from sp26_gke.workflows.llm import create_client, invoke_json
from sp26_gke.workflows.prompts import (
    JUDGE_AGGREGATION_PROMPT,
    JUDGE_INTERROGATION_PROMPT,
    JUDGE_PLANNING_PROMPT,
    JUDGE_PLANNING_SEARCH_QUERIES_PROMPT,
    JUDGE_SHOULD_CONTINUE_PROMPT,
)
from sp26_gke.workflows.redis_state import RedisState
from sp26_gke.workflows.schemas import InterrogationExchange, JudgeAggregate, JudgePlan
from sp26_gke.workflows.search import create_client as create_tavily
from sp26_gke.workflows.search import execute_queries

WORKER_PORT = 8080
WORKER_POLL_INTERVAL = 5
WORKER_TIMEOUT = 600
DEFAULT_TOPIC = "latest hot topics in AI"
MAX_INTERROGATION_ROUNDS = 3
INTERROGATION_HTTP_TIMEOUT = 120


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _log(event: str, **fields: object) -> None:
    payload = {"ts": _now_iso(), "event": event, **fields}
    print(json.dumps(payload, default=str), flush=True)


def _worker_service_name(run_id: str, stance_id: str) -> str:
    """Internal DNS name for a worker's ClusterIP Service."""
    return f"worker-{run_id}-{stance_id}"


def _worker_url(run_id: str, stance_id: str, namespace: str, port: int) -> str:
    """Full cluster-internal URL for a worker."""
    svc = _worker_service_name(run_id, stance_id)
    return f"http://{svc}.{namespace}.svc.cluster.local:{port}"


def _make_worker_job(
    run_id: str,
    stance_id: str,
    stance_label: str,
    topic: str,
    image: str,
    namespace: str,
    redis_host: str,
    port: int,
) -> k8s_client.V1Job:
    """Build a K8s Job manifest for a worker agent."""
    job_name = f"worker-{run_id}-{stance_id}"
    env_vars = {
        "AGENT_ROLE": "worker",
        "RUN_ID": run_id,
        "STANCE_ID": stance_id,
        "STANCE_LABEL": stance_label,
        "TOPIC": topic,
        "REDIS_HOST": redis_host,
        "WORKER_PORT": str(port),
        "OPENAI_API_KEY": os.environ["OPENAI_API_KEY"],
        "TAVILY_API_KEY": os.environ["TAVILY_API_KEY"],
    }
    env_list = [k8s_client.V1EnvVar(name=k, value=v) for k, v in env_vars.items()]

    container = k8s_client.V1Container(
        name="worker",
        image=image,
        image_pull_policy="IfNotPresent",
        env=env_list,
        ports=[k8s_client.V1ContainerPort(container_port=port, name="http")],
    )
    template = k8s_client.V1PodTemplateSpec(
        metadata=k8s_client.V1ObjectMeta(
            labels={
                "app": "sentiment-agent",
                "role": "worker",
                "stance": stance_id,
                "run-id": run_id,
            },
        ),
        spec=k8s_client.V1PodSpec(
            restart_policy="Never",
            containers=[container],
        ),
    )
    return k8s_client.V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=k8s_client.V1ObjectMeta(
            name=job_name,
            namespace=namespace,
            labels={
                "app": "sentiment-agent",
                "role": "worker",
                "stance": stance_id,
                "run-id": run_id,
            },
        ),
        spec=k8s_client.V1JobSpec(
            backoff_limit=0,
            ttl_seconds_after_finished=7200,
            template=template,
        ),
    )


def _make_worker_service(
    run_id: str,
    stance_id: str,
    namespace: str,
    port: int,
) -> k8s_client.V1Service:
    """Build a ClusterIP Service that routes to a worker pod."""
    svc_name = _worker_service_name(run_id, stance_id)
    return k8s_client.V1Service(
        api_version="v1",
        kind="Service",
        metadata=k8s_client.V1ObjectMeta(
            name=svc_name,
            namespace=namespace,
            labels={
                "app": "sentiment-agent",
                "role": "worker",
                "stance": stance_id,
                "run-id": run_id,
            },
        ),
        spec=k8s_client.V1ServiceSpec(
            type="ClusterIP",
            selector={
                "app": "sentiment-agent",
                "role": "worker",
                "stance": stance_id,
                "run-id": run_id,
            },
            ports=[
                k8s_client.V1ServicePort(
                    port=port, target_port=port, protocol="TCP", name="http"
                )
            ],
        ),
    )


def _make_summarizer_job(
    run_id: str,
    topic: str,
    image: str,
    namespace: str,
    redis_host: str,
) -> k8s_client.V1Job:
    """Build a K8s Job manifest for the summarizer agent."""
    job_name = f"summarizer-{run_id}"
    env_vars = {
        "AGENT_ROLE": "summarizer",
        "RUN_ID": run_id,
        "TOPIC": topic,
        "REDIS_HOST": redis_host,
        "OPENAI_API_KEY": os.environ["OPENAI_API_KEY"],
    }
    env_list = [k8s_client.V1EnvVar(name=k, value=v) for k, v in env_vars.items()]

    container = k8s_client.V1Container(
        name="summarizer",
        image=image,
        image_pull_policy="IfNotPresent",
        env=env_list,
    )
    template = k8s_client.V1PodTemplateSpec(
        metadata=k8s_client.V1ObjectMeta(
            labels={"app": "sentiment-agent", "role": "summarizer"},
        ),
        spec=k8s_client.V1PodSpec(
            restart_policy="Never",
            containers=[container],
        ),
    )
    return k8s_client.V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=k8s_client.V1ObjectMeta(
            name=job_name,
            namespace=namespace,
            labels={"app": "sentiment-agent", "role": "summarizer"},
        ),
        spec=k8s_client.V1JobSpec(
            backoff_limit=0,
            ttl_seconds_after_finished=7200,
            template=template,
        ),
    )


def _wait_for_workers_serving(
    state: RedisState,
    run_id: str,
    worker_ids: list[str],
    timeout: int = WORKER_TIMEOUT,
) -> bool:
    """Poll Redis until all workers report status 'serving'."""
    start = time.time()
    while time.time() - start < timeout:
        all_serving = True
        for wid in worker_ids:
            status = state.get_worker_status(run_id, wid)
            if status == "serving":
                continue
            if status == "failed":
                _log("worker_failed", worker_id=wid)
                return False
            all_serving = False
        if all_serving:
            return True
        time.sleep(WORKER_POLL_INTERVAL)
    _log("workers_timed_out", worker_ids=worker_ids)
    return False


def _wait_for_jobs(
    batch_api: k8s_client.BatchV1Api,
    namespace: str,
    job_names: list[str],
    timeout: int = WORKER_TIMEOUT,
) -> bool:
    """Poll until all named Jobs succeed or any fails."""
    start = time.time()
    while time.time() - start < timeout:
        all_done = True
        for name in job_names:
            try:
                job = batch_api.read_namespaced_job(name=name, namespace=namespace)
                status = job.status
                if status.succeeded and status.succeeded >= 1:
                    continue
                if status.failed and status.failed >= 1:
                    _log("job_failed", job_name=name)
                    return False
                all_done = False
            except k8s_client.ApiException as exc:
                _log("job_poll_error", job_name=name, error=str(exc))
                all_done = False
        if all_done:
            return True
        time.sleep(WORKER_POLL_INTERVAL)
    _log("jobs_timed_out", job_names=job_names)
    return False


def _planning_phase(topic: str, run_id: str, state: RedisState) -> JudgePlan:
    """Use Tavily to research topic breadth, then plan stances."""
    llm = create_client(temperature=0.4)
    tavily = create_tavily()

    query_prompt = JUDGE_PLANNING_SEARCH_QUERIES_PROMPT.format(topic=topic)
    queries = invoke_json(
        llm,
        query_prompt,
        fallback=[
            f"{topic} debate controversy opinions",
            f"{topic} public reaction social media",
        ],
    )
    _log("judge_planning_queries", queries=queries)

    results = execute_queries(tavily, queries[:2], max_results=3, search_depth="basic")
    _log("judge_planning_search_done", result_count=len(results))

    planning_prompt = JUDGE_PLANNING_PROMPT.format(
        topic=topic,
        search_results=json.dumps(results, indent=2, default=str),
    )
    plan_data = invoke_json(
        llm,
        planning_prompt,
        fallback={
            "conversation_breadth": "moderate",
            "is_polarized": True,
            "major_axes": ["support vs opposition"],
            "stances": [
                {
                    "stance_id": "positive",
                    "stance_label": "positive",
                    "description": f"Defend the positive view on {topic}",
                },
                {
                    "stance_id": "negative",
                    "stance_label": "negative",
                    "description": f"Defend the negative view on {topic}",
                },
            ],
        },
    )
    plan_data["run_id"] = run_id
    plan_data["topic"] = topic

    stances = plan_data.get("stances", [])
    if len(stances) < 2:
        stances.append(
            {
                "stance_id": "mixed",
                "stance_label": "mixed",
                "description": f"Defend a nuanced/mixed view on {topic}",
            }
        )
        plan_data["stances"] = stances
    plan_data["stances"] = stances[:6]

    plan = JudgePlan.model_validate(plan_data)
    state.set_judge_plan(run_id, plan.model_dump())
    _log("judge_plan_created", stance_count=len(plan.stances))
    return plan


def _interrogate_worker_http(
    run_id: str,
    stance_id: str,
    namespace: str,
    port: int,
    question: str,
) -> str:
    """Send an interrogation question to a worker via HTTP."""
    url = _worker_url(run_id, stance_id, namespace, port)
    response = httpx.post(
        f"{url}/interrogate",
        json={"question": question},
        timeout=INTERROGATION_HTTP_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()["answer"]


def _interrogation_phase(
    topic: str,
    run_id: str,
    state: RedisState,
    worker_ids: list[str],
    max_rounds: int,
    namespace: str,
    port: int,
) -> list[InterrogationExchange]:
    """Interrogate workers with targeted questions via HTTP."""
    llm = create_client(temperature=0.3)
    all_exchanges: list[InterrogationExchange] = []

    worker_outputs: dict[str, dict[str, Any]] = {}
    for wid in worker_ids:
        result = state.get_worker_result(run_id, wid)
        if result:
            worker_outputs[wid] = result

    worker_outputs_str = json.dumps(worker_outputs, indent=2, default=str)

    for round_num in range(1, max_rounds + 1):
        _log("judge_interrogation_round", round=round_num)

        previous_str = json.dumps(
            [e.model_dump() for e in all_exchanges], indent=2, default=str
        )

        q_prompt = JUDGE_INTERROGATION_PROMPT.format(
            topic=topic,
            worker_outputs=worker_outputs_str,
            previous_exchanges=previous_str,
        )
        questions = invoke_json(llm, q_prompt, fallback=[])

        for q in questions:
            target = q.get("target_worker_id", "")
            question_text = q.get("question", "")
            if not target or not question_text or target not in worker_outputs:
                continue

            _log(
                "judge_interrogation_sending",
                worker=target,
                question=question_text[:80],
            )
            answer = _interrogate_worker_http(
                run_id=run_id,
                stance_id=target,
                namespace=namespace,
                port=port,
                question=question_text,
            )
            exchange = InterrogationExchange(
                worker_id=target,
                question=question_text,
                answer=answer,
            )
            all_exchanges.append(exchange)
            _log(
                "judge_interrogation_exchange",
                worker=target,
                answer_length=len(answer),
            )

        continue_prompt = JUDGE_SHOULD_CONTINUE_PROMPT.format(
            topic=topic,
            round_number=round_num,
            max_rounds=max_rounds,
            all_exchanges=json.dumps(
                [e.model_dump() for e in all_exchanges], indent=2, default=str
            ),
            worker_outputs=worker_outputs_str,
        )
        decision = invoke_json(
            llm,
            continue_prompt,
            fallback={"should_continue": False, "reason": "Max rounds fallback"},
        )
        should_continue = decision.get("should_continue", False)
        _log(
            "judge_interrogation_decision",
            should_continue=should_continue,
            reason=decision.get("reason", ""),
        )
        if not should_continue:
            break

    state.set_judge_interrogation(run_id, [e.model_dump() for e in all_exchanges])
    return all_exchanges


def _shutdown_workers(
    run_id: str,
    worker_ids: list[str],
    namespace: str,
    port: int,
) -> None:
    """Send shutdown signal to all workers via HTTP."""
    for wid in worker_ids:
        url = _worker_url(run_id, wid, namespace, port)
        try:
            httpx.post(f"{url}/shutdown", timeout=10)
            _log("worker_shutdown_sent", worker_id=wid)
        except httpx.HTTPError:
            _log("worker_shutdown_failed", worker_id=wid)


def _cleanup_worker_services(
    core_api: k8s_client.CoreV1Api,
    run_id: str,
    worker_ids: list[str],
    namespace: str,
) -> None:
    """Delete ClusterIP Services created for workers."""
    for wid in worker_ids:
        svc_name = _worker_service_name(run_id, wid)
        try:
            core_api.delete_namespaced_service(name=svc_name, namespace=namespace)
            _log("worker_service_deleted", service=svc_name)
        except k8s_client.ApiException:
            _log("worker_service_delete_skipped", service=svc_name)


def _aggregation_phase(
    topic: str,
    run_id: str,
    state: RedisState,
    worker_ids: list[str],
    exchanges: list[InterrogationExchange],
) -> JudgeAggregate:
    """Combine all worker results and interrogation into aggregate."""
    llm = create_client(temperature=0.3)

    worker_outputs: dict[str, Any] = {}
    for wid in worker_ids:
        result = state.get_worker_result(run_id, wid)
        if result:
            worker_outputs[wid] = result

    agg_prompt = JUDGE_AGGREGATION_PROMPT.format(
        topic=topic,
        worker_outputs=json.dumps(worker_outputs, indent=2, default=str),
        interrogation_log=json.dumps(
            [e.model_dump() for e in exchanges], indent=2, default=str
        ),
    )
    agg_data = invoke_json(
        llm,
        agg_prompt,
        fallback={
            "stances": list(worker_outputs.keys()),
            "controversy_level": "medium",
            "agreement_matrix": [],
            "rebuttal_graph": [],
            "shared_ground": [],
            "fringe_positions": [],
            "conversation_locus_shift": "",
            "judge_notes": "Aggregation fallback — LLM response could not be parsed.",
        },
    )
    agg_data["run_id"] = run_id
    agg_data["topic"] = topic
    agg_data["interrogation_log"] = [e.model_dump() for e in exchanges]

    aggregate = JudgeAggregate.model_validate(agg_data)
    state.set_judge_aggregate(run_id, aggregate.model_dump())
    _log("judge_aggregate_created")
    return aggregate


def run() -> int:
    """Run the judge agent."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    missing = [
        v
        for v in ("OPENAI_API_KEY", "TAVILY_API_KEY", "REDIS_HOST", "SENTIMENT_IMAGE")
        if not os.environ.get(v)
    ]
    if missing:
        _log("judge_error", error=f"Missing env vars: {', '.join(missing)}")
        return 1

    topic = os.environ.get("TOPIC", DEFAULT_TOPIC)
    redis_host = os.environ["REDIS_HOST"]
    image = os.environ["SENTIMENT_IMAGE"]
    namespace = os.environ.get("K8S_NAMESPACE", "default")
    max_rounds = int(
        os.environ.get("MAX_INTERROGATION_ROUNDS", str(MAX_INTERROGATION_ROUNDS))
    )
    worker_port = int(os.environ.get("WORKER_PORT", str(WORKER_PORT)))
    run_id = str(uuid.uuid4())[:8]

    _log("judge_started", run_id=run_id, topic=topic)

    state = RedisState(host=redis_host)
    state.ping()
    state.set_run_meta(
        run_id,
        {
            "run_id": run_id,
            "topic": topic,
            "status": "planning",
            "started_at": _now_iso(),
        },
    )
    _log("redis_connected", host=redis_host)

    # Planning phase
    plan = _planning_phase(topic, run_id, state)
    _log("judge_plan_ready", stances=[s.stance_label for s in plan.stances])

    # K8s setup
    try:
        k8s_config.load_incluster_config()
    except k8s_config.ConfigException:
        k8s_config.load_kube_config()

    batch_api = k8s_client.BatchV1Api()
    core_api = k8s_client.CoreV1Api()
    worker_ids: list[str] = []

    # Spawn worker Jobs + ClusterIP Services
    for stance in plan.stances:
        job = _make_worker_job(
            run_id=run_id,
            stance_id=stance.stance_id,
            stance_label=stance.stance_label,
            topic=topic,
            image=image,
            namespace=namespace,
            redis_host=redis_host,
            port=worker_port,
        )
        batch_api.create_namespaced_job(namespace=namespace, body=job)

        svc = _make_worker_service(
            run_id=run_id,
            stance_id=stance.stance_id,
            namespace=namespace,
            port=worker_port,
        )
        core_api.create_namespaced_service(namespace=namespace, body=svc)

        worker_ids.append(stance.stance_id)
        _log(
            "worker_created",
            job=f"worker-{run_id}-{stance.stance_id}",
            service=_worker_service_name(run_id, stance.stance_id),
            stance=stance.stance_label,
        )

    # Wait for workers to finish research and start serving
    _log("waiting_for_workers_serving", count=len(worker_ids))
    if not _wait_for_workers_serving(state, run_id, worker_ids):
        _log("judge_error", error="One or more workers failed to reach serving state")
        _cleanup_worker_services(core_api, run_id, worker_ids, namespace)
        return 1
    _log("all_workers_serving")

    # Interrogation phase — queries workers over HTTP
    _log("judge_interrogation_starting", max_rounds=max_rounds)
    exchanges = _interrogation_phase(
        topic, run_id, state, worker_ids, max_rounds, namespace, worker_port
    )
    _log("judge_interrogation_completed", exchange_count=len(exchanges))

    # Shutdown workers and clean up services
    _shutdown_workers(run_id, worker_ids, namespace, worker_port)
    _cleanup_worker_services(core_api, run_id, worker_ids, namespace)

    # Aggregation
    _aggregation_phase(topic, run_id, state, worker_ids, exchanges)

    # Spawn summarizer
    summ_job = _make_summarizer_job(
        run_id=run_id,
        topic=topic,
        image=image,
        namespace=namespace,
        redis_host=redis_host,
    )
    batch_api.create_namespaced_job(namespace=namespace, body=summ_job)
    summ_job_name = f"summarizer-{run_id}"
    _log("summarizer_job_created", job_name=summ_job_name)

    if not _wait_for_jobs(batch_api, namespace, [summ_job_name]):
        _log("judge_error", error="Summarizer job failed or timed out")
        return 1
    _log("summarizer_completed")

    # Final report
    report_md = state.get_final_report_md(run_id)
    if report_md:
        print("\n" + "=" * 80, flush=True)
        print("FINAL SENTIMENT DEBATE REPORT", flush=True)
        print("=" * 80, flush=True)
        print(f"Topic: {topic}", flush=True)
        print(f"Run ID: {run_id}", flush=True)
        print(f"Workers: {len(plan.stances)}", flush=True)
        print(f"Interrogation rounds: {len(exchanges)} exchanges", flush=True)
        print("=" * 80 + "\n", flush=True)
        print(report_md, flush=True)
        print("\n" + "=" * 80, flush=True)
    else:
        _log("judge_warning", warning="No final report found in Redis")

    state.set_run_meta(
        run_id,
        {
            "run_id": run_id,
            "topic": topic,
            "status": "completed",
            "started_at": _now_iso(),
            "stances": [s.stance_id for s in plan.stances],
        },
    )

    _log("judge_completed", run_id=run_id, topic=topic, worker_count=len(plan.stances))
    return 0


if __name__ == "__main__":
    sys.exit(run())
