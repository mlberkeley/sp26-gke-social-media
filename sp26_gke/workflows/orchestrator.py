"""
Orchestrator agent for the multi-agent sentiment pipeline.

Runs as a K8s CronJob. On each invocation:
  1. Uses LLM to plan 2-4 sub-agents for the given topic
  2. Writes each sub-agent's config to Redis
  3. Spawns K8s Jobs for each researcher sub-agent
  4. Polls until all researcher Jobs complete
  5. Spawns a synthesizer K8s Job
  6. Polls until the synthesizer completes
  7. Reads the final report from Redis and prints it

Env vars required:
  OPENAI_API_KEY, TAVILY_API_KEY, REDIS_HOST, SENTIMENT_IMAGE
Optional:
  SENTIMENT_TOPIC (default: "latest hot topics in AI")
  K8S_NAMESPACE (default: "default")
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import UTC, datetime

import redis
from kubernetes import client as k8s_client
from kubernetes import config as k8s_config
from langchain_openai import ChatOpenAI

from sp26_gke.workflows.prompts import ORCHESTRATOR_PLANNING_PROMPT

OPENAI_MODEL = "gpt-4o-mini"
REDIS_KEY_TTL = 14400  # 4 hours
JOB_POLL_INTERVAL = 5  # seconds
JOB_TIMEOUT = 600  # 10 minutes max per phase
DEFAULT_TOPIC = "latest hot topics in AI"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _log(event: str, **fields: object) -> None:
    payload = {"ts": _now_iso(), "event": event, **fields}
    print(json.dumps(payload, default=str), flush=True)


def _make_job_manifest(
    job_name: str,
    image: str,
    namespace: str,
    agent_role: str,
    env_vars: dict[str, str],
) -> k8s_client.V1Job:
    """Build a K8s Job manifest for a sub-agent."""
    env_list = [
        k8s_client.V1EnvVar(name=k, value=v) for k, v in env_vars.items()
    ]

    container = k8s_client.V1Container(
        name=agent_role,
        image=image,
        image_pull_policy="IfNotPresent",
        env=env_list,
    )

    template = k8s_client.V1PodTemplateSpec(
        metadata=k8s_client.V1ObjectMeta(
            labels={"app": "sentiment-agent", "role": agent_role},
        ),
        spec=k8s_client.V1PodSpec(
            restart_policy="Never",
            containers=[container],
        ),
    )

    job = k8s_client.V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=k8s_client.V1ObjectMeta(
            name=job_name,
            namespace=namespace,
            labels={"app": "sentiment-agent", "role": agent_role},
        ),
        spec=k8s_client.V1JobSpec(
            backoff_limit=0,
            ttl_seconds_after_finished=7200,
            template=template,
        ),
    )
    return job


def _wait_for_jobs(
    batch_api: k8s_client.BatchV1Api,
    namespace: str,
    job_names: list[str],
    timeout: int = JOB_TIMEOUT,
) -> bool:
    """Poll until all named Jobs succeed or any fails. Returns True if all succeeded."""
    start = time.time()
    while time.time() - start < timeout:
        all_done = True
        for name in job_names:
            try:
                job = batch_api.read_namespaced_job(name=name, namespace=namespace)
                status = job.status
                if status.succeeded and status.succeeded >= 1:
                    continue  # this one is done
                if status.failed and status.failed >= 1:
                    _log("job_failed", job_name=name)
                    return False
                all_done = False  # still running
            except k8s_client.ApiException as exc:
                _log("job_poll_error", job_name=name, error=str(exc))
                all_done = False

        if all_done:
            return True

        time.sleep(JOB_POLL_INTERVAL)

    _log("jobs_timed_out", job_names=job_names)
    return False


def run() -> int:
    """Run the orchestrator."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    # Validate
    missing = [
        v
        for v in ("OPENAI_API_KEY", "TAVILY_API_KEY", "REDIS_HOST", "SENTIMENT_IMAGE")
        if not os.environ.get(v)
    ]
    if missing:
        _log("orchestrator_error", error=f"Missing env vars: {', '.join(missing)}")
        return 1

    topic = os.environ.get("SENTIMENT_TOPIC", DEFAULT_TOPIC)
    redis_host = os.environ["REDIS_HOST"]
    image = os.environ["SENTIMENT_IMAGE"]
    namespace = os.environ.get("K8S_NAMESPACE", "default")
    run_id = str(uuid.uuid4())[:8]  # short ID for readability

    _log("orchestrator_started", run_id=run_id, topic=topic)

    try:
        # Connect to Redis
        r = redis.Redis(host=redis_host, port=6379, decode_responses=True)
        r.ping()
        _log("redis_connected", host=redis_host)

        # Step 1: LLM plans sub-agents
        llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0.4)
        planning_prompt = ORCHESTRATOR_PLANNING_PROMPT.format(topic=topic)
        planning_response = llm.invoke(planning_prompt)

        try:
            raw = str(planning_response.content).strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            agent_configs: list[dict[str, str]] = json.loads(raw)
        except (json.JSONDecodeError, IndexError):
            # Fallback to 2 default agents
            _log("planning_fallback", reason="Failed to parse LLM response")
            agent_configs = [
                {
                    "focus": "X/Twitter sentiment",
                    "platform_hint": "x.com",
                    "prompt": f"Search X/Twitter for opinions about {topic}",
                },
                {
                    "focus": "Reddit & news discussion",
                    "platform_hint": "reddit.com",
                    "prompt": f"Search Reddit and news for discussions about {topic}",
                },
            ]

        # Clamp to 2-4 agents
        agent_configs = agent_configs[:4]
        if len(agent_configs) < 2:
            agent_configs.append(
                {
                    "focus": "General social media",
                    "platform_hint": "general",
                    "prompt": f"Search social media for any discussion about {topic}",
                }
            )

        agent_count = len(agent_configs)
        _log("agents_planned", count=agent_count, agents=[a["focus"] for a in agent_configs])

        # Step 2: Write configs to Redis
        r.set(f"run:{run_id}:agent_count", str(agent_count), ex=REDIS_KEY_TTL)
        r.set(f"run:{run_id}:topic", topic, ex=REDIS_KEY_TTL)

        for idx, config in enumerate(agent_configs):
            config["topic"] = topic  # inject topic into each config
            r.set(
                f"run:{run_id}:config:{idx}",
                json.dumps(config, default=str),
                ex=REDIS_KEY_TTL,
            )

        # Step 3: Init K8s client
        try:
            k8s_config.load_incluster_config()
        except k8s_config.ConfigException:
            k8s_config.load_kube_config()

        batch_api = k8s_client.BatchV1Api()

        # Step 4: Spawn researcher Jobs
        researcher_job_names: list[str] = []
        for idx in range(agent_count):
            job_name = f"researcher-{run_id}-{idx}"
            env_vars = {
                "AGENT_ROLE": "researcher",
                "RUN_ID": run_id,
                "AGENT_INDEX": str(idx),
                "REDIS_HOST": redis_host,
                "OPENAI_API_KEY": os.environ["OPENAI_API_KEY"],
                "TAVILY_API_KEY": os.environ["TAVILY_API_KEY"],
                "SENTIMENT_TOPIC": topic,
            }
            job_manifest = _make_job_manifest(
                job_name=job_name,
                image=image,
                namespace=namespace,
                agent_role="researcher",
                env_vars=env_vars,
            )
            batch_api.create_namespaced_job(namespace=namespace, body=job_manifest)
            researcher_job_names.append(job_name)
            _log("researcher_job_created", job_name=job_name, focus=agent_configs[idx]["focus"])

        # Step 5: Wait for all researchers
        _log("waiting_for_researchers", count=agent_count)
        if not _wait_for_jobs(batch_api, namespace, researcher_job_names):
            _log("orchestrator_error", error="One or more researcher jobs failed or timed out")
            return 1

        _log("all_researchers_completed")

        # Step 6: Spawn synthesizer Job
        synth_job_name = f"synthesizer-{run_id}"
        synth_env = {
            "AGENT_ROLE": "synthesizer",
            "RUN_ID": run_id,
            "REDIS_HOST": redis_host,
            "OPENAI_API_KEY": os.environ["OPENAI_API_KEY"],
            "SENTIMENT_TOPIC": topic,
        }
        synth_manifest = _make_job_manifest(
            job_name=synth_job_name,
            image=image,
            namespace=namespace,
            agent_role="synthesizer",
            env_vars=synth_env,
        )
        batch_api.create_namespaced_job(namespace=namespace, body=synth_manifest)
        _log("synthesizer_job_created", job_name=synth_job_name)

        # Step 7: Wait for synthesizer
        if not _wait_for_jobs(batch_api, namespace, [synth_job_name]):
            _log("orchestrator_error", error="Synthesizer job failed or timed out")
            return 1

        _log("synthesizer_completed")

        # Step 8: Read and print the final report
        report = r.get(f"run:{run_id}:report")
        if report:
            print("\n" + "=" * 80, flush=True)
            print("SENTIMENT REPORT (MULTI-AGENT)", flush=True)
            print("=" * 80, flush=True)
            print(f"Topic: {topic}", flush=True)
            print(f"Run ID: {run_id}", flush=True)
            print(f"Agents: {agent_count}", flush=True)
            print("=" * 80 + "\n", flush=True)
            print(report, flush=True)
            print("\n" + "=" * 80, flush=True)
        else:
            _log("orchestrator_warning", warning="No report found in Redis")

        _log("orchestrator_completed", run_id=run_id, topic=topic, agent_count=agent_count)
        return 0

    except Exception as exc:
        _log("orchestrator_error", error=str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(run())
