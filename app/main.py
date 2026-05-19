"""
Markar Intelligence — FastAPI app entry point.
Phase 1: Conversation store + Tool registry + Agent registry
Phase 2: Self-reflection + Multi-step reasoning
Phase 3: Auth + RBAC + Audit logs + Multi-repo
Phase 4: Incremental graph + Vector memory + Custom agents
Phase 5: Multi-agent delegation + AutoRouter + Streaming + Celery
"""
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.health import system_router, ci_router
from app.routes.chat   import chat_router
from app.routes.admin  import admin_router
from app.routes.auth   import auth_router

app = FastAPI(
    title="Markar Intelligence",
    description="AI-powered codebase understanding platform — Phase 1-5",
    version="5.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(system_router)
app.include_router(ci_router)
app.include_router(chat_router)
app.include_router(admin_router)
app.include_router(auth_router)


@app.on_event("startup")
async def startup():
    # Phase 1: Conversation store + Tool registry
    from app.core.conversation_store import init_db
    from app.core.tool_registry import get_registry
    init_db()
    print("[Markar] Phase 1 — Conversation DB initialized")

    # Phase 3: Observability + Multi-repo + Auth
    from app.core.observability import init_observability_db
    from app.core.multi_repo import init_repo_db
    from app.core.auth import init_auth_db
    init_observability_db()
    init_repo_db()
    init_auth_db()
    print("[Markar] Phase 3 — Observability + Multi-repo + Auth initialized")

    # Phase 4: Vector memory + Custom agents + Incremental graph
    from app.core.vector_memory import init_vector_db
    from app.core.custom_agents import init_custom_agents_db
    from app.core.incremental_graph import init_incremental_db
    init_vector_db()
    init_custom_agents_db()
    init_incremental_db()
    print("[Markar] Phase 4 — Vector memory + Custom agents initialized")

    # Phase 5: Multi-agent delegation + AutoRouter + Celery
    from app.core.agent_registry import setup_default_agents
    from app.celery_app import celery_app
    setup_default_agents()
    print("[Markar] Phase 5 — Multi-agent delegation + AutoRouter initialized")
    print("[Markar] All systems ready — v5.0.0")


@app.get("/")
async def root():
    return {
        "name":    "Markar Intelligence",
        "version": "5.0.0",
        "phases":  [
            "Phase 1: Memory+Routing",
            "Phase 2: Reflection+Reasoning",
            "Phase 3: Auth+RBAC+Observability",
            "Phase 4: Vector+Incremental+Custom",
            "Phase 5: MultiAgent+AutoRouter+Streaming+Celery",
        ],
        "docs": "/docs",
    }