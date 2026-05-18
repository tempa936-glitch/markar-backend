"""
Celery Tasks — Markar Agent Operations.
Heavy agent runs ko background queue mein execute karo.

Tasks:
- run_agent_task: Kisi bhi agent ko async run karo
- stream_agent_task: Streaming response queue mein daalo
- build_graph_task: Repository graph background mein banaao
"""
import os
import asyncio
import json
import time
from typing import Dict, Optional, Any

from app.celery_app import celery_app


# ── Agent Run Task ────────────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="markar.tasks.agent.run",
    max_retries=2,
    default_retry_delay=3,
    track_started=True,
)
def run_agent_task(
    self,
    repo_id:    str,
    message:    str,
    session_id: str,
    intent:     str,
    target:     Optional[str] = None,
    model:      Optional[str] = None,
    user_id:    Optional[str] = None,
) -> Dict:
    """
    Background agent execution task.
    Returns full result dict when complete.
    """
    task_id = self.request.id
    print(f"[AgentTask] Starting — task={task_id} intent={intent} session={session_id[:8]}")

    try:
        self.update_state(
            state="PROGRESS",
            meta={"status": "Initializing agent...", "intent": intent}
        )

        # Import here to avoid circular imports at module load
        from app.services.repo_service import get_orchestrator_by_id

        orch = get_orchestrator_by_id(repo_id)
        if not orch:
            return {
                "status":  "error",
                "error":   f"Repo '{repo_id}' ready nahi hai",
                "task_id": task_id,
            }

        self.update_state(
            state="PROGRESS",
            meta={"status": f"Running {intent} agent...", "intent": intent}
        )

        # Run the delegation pipeline
        from app.agents.delegation_manager import DelegationManager
        dm = DelegationManager(store=orch.store, repo_id=repo_id)

        result = asyncio.run(
            dm.execute(
                message=message,
                session_id=session_id,
                intent=intent,
                target=target,
                model=model,
            )
        )

        result["task_id"]   = task_id
        result["status"]    = "success"
        result["session_id"] = session_id

        print(f"[AgentTask] Done — task={task_id} intent={intent}")
        return result

    except Exception as exc:
        print(f"[AgentTask] Failed — task={task_id}: {exc}")
        try:
            raise self.retry(exc=exc, countdown=2 ** self.request.retries)
        except self.MaxRetriesExceededError:
            return {
                "status":  "error",
                "error":   str(exc),
                "task_id": task_id,
                "intent":  intent,
            }


# ── Graph Build Task ──────────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="markar.tasks.graph.build",
    max_retries=1,
    time_limit=300,   # 5 minutes max
    soft_time_limit=240,
)
def build_graph_task(
    self,
    repo_id:   str,
    repo_path: str,
    user_id:   Optional[str] = None,
) -> Dict:
    """
    Background graph construction task.
    Parse repository and build Neo4j knowledge graph.
    """
    task_id = self.request.id
    print(f"[GraphTask] Starting — task={task_id} repo={repo_id}")

    try:
        self.update_state(
            state="PROGRESS",
            meta={"status": "Parsing files...", "repo_id": repo_id}
        )

        from app.services.repo_service import build_repo_graph
        result = build_repo_graph(repo_id=repo_id, repo_path=repo_path)

        self.update_state(
            state="PROGRESS",
            meta={"status": "Graph complete", "repo_id": repo_id}
        )

        return {
            "status":  "success",
            "repo_id": repo_id,
            "task_id": task_id,
            **result,
        }

    except Exception as exc:
        print(f"[GraphTask] Failed — task={task_id}: {exc}")
        return {
            "status":  "error",
            "error":   str(exc),
            "repo_id": repo_id,
            "task_id": task_id,
        }


# ── Health check task ─────────────────────────────────────────────────────────

@celery_app.task(name="markar.tasks.fast.ping")
def ping_task() -> Dict:
    """Quick health check for Celery worker."""
    return {
        "status":    "ok",
        "timestamp": time.time(),
        "worker":    os.getenv("HOSTNAME", "unknown"),
    }
