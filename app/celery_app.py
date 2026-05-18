"""
Celery App — Async Task Queue for Markar.
Heavy operations (agent runs, graph builds) ko background mein bhejo.

Setup:
- Broker: Redis (default localhost:6379)
- Result backend: Redis
- SQLite fallback (dev mode without Redis)
"""
import os
from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Dev mode: agar Redis nahi hai to eager mode (synchronous) use karo
DEV_MODE = os.getenv("MARKAR_DEV_MODE", "true").lower() == "true"

celery_app = Celery(
    "markar",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

celery_app.conf.update(
    # Serialization
    task_serializer         = "json",
    result_serializer       = "json",
    accept_content          = ["json"],

    # Timezone
    timezone                = "UTC",
    enable_utc              = True,

    # Task behavior
    task_track_started      = True,
    task_acks_late          = True,
    task_reject_on_worker_lost = True,

    # Result expiry (24 hours)
    result_expires          = 86400,

    # Retry defaults
    task_max_retries        = 3,
    task_default_retry_delay = 5,

    # Dev mode: tasks run synchronously (no Redis needed)
    task_always_eager       = DEV_MODE,
    task_eager_propagates   = DEV_MODE,

    # Worker concurrency
    worker_concurrency      = int(os.getenv("CELERY_WORKERS", "4")),
    worker_prefetch_multiplier = 1,

    # Routing
    task_routes = {
        "markar.tasks.agent.*":     {"queue": "agent"},
        "markar.tasks.graph.*":     {"queue": "graph"},
        "markar.tasks.fast.*":      {"queue": "fast"},
    },
)

# Auto-discover tasks
celery_app.autodiscover_tasks(["app.tasks"])

if DEV_MODE:
    print("[Celery] DEV MODE — tasks run synchronously (no Redis needed)")
    print("[Celery] Set MARKAR_DEV_MODE=false and start Redis for async mode")
