"""
Chat Routes — Production-Grade Upgrade.
New endpoints:
- POST /api/chat          — standard (sync) chat
- POST /api/chat/stream   — streaming SSE response
- POST /api/chat/async    — Celery background task
- GET  /api/chat/task/:id — poll background task result
- GET  /api/chat/history/:session_id
- GET  /api/chat/sessions/:repo_id
- POST /api/chat/build    — multi-step build agent
- POST /api/chat/semantic-search
"""
import uuid
import json
import asyncio
from typing import Optional, Dict, AsyncGenerator

from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, model_validator

from app.services.repo_service import get_orchestrator_by_id

chat_router = APIRouter(prefix="/api/chat", tags=["chat"])


# ── Request models ─────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    repo_id:    str
    message:    str
    session_id: Optional[str] = None
    model:      Optional[str] = None
    target:     Optional[str] = None
    intent:     Optional[str] = None   # override auto-routing

    @model_validator(mode='after')
    def map_target_to_intent(self) -> 'ChatRequest':
        if self.target in ["ask", "debug", "build", "qa", "impact"] and not self.intent:
            self.intent = self.target
            self.target = None
        return self


class BuildRequest(BaseModel):
    repo_id:        str
    session_id:     str
    action:         str            # clarify | spec | build | push_pr
    message:        Optional[str]  = None
    answers:        Optional[Dict] = None
    approved:       Optional[bool] = None
    model:          Optional[str]  = None
    github_token:   Optional[str]  = None
    repo_full_name: Optional[str]  = None


class SemanticSearchRequest(BaseModel):
    repo_id:   str
    query:     str
    top_k:     Optional[int] = 5
    node_type: Optional[str] = None


# ── Auth helper ────────────────────────────────────────────────────────────────

async def _get_user(authorization: Optional[str]):
    from app.core.auth import get_current_user
    user = await get_current_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user


def _get_orch(repo_id: str):
    orch = get_orchestrator_by_id(repo_id)
    if not orch:
        raise HTTPException(
            status_code=404,
            detail=f"Repo '{repo_id}' ready nahi hai. Pehle index karo."
        )
    return orch


# ── Standard Chat ──────────────────────────────────────────────────────────────

@chat_router.post("")
async def chat(
    req: ChatRequest,
    authorization: Optional[str] = Header(None),
):
    """
    Standard synchronous chat endpoint.
    AutoRouter se intent detect hota hai, DelegationManager agent run karta hai.
    """
    user = await _get_user(authorization)
    orch = _get_orch(req.repo_id)

    # ✅ Credit check — RBAC se PEHLE
    from app.core.user_admin import has_credits, deduct_credit
    if not has_credits(user.user_id):
        raise HTTPException(
            status_code=402,
            detail="Credits khatam ho gaye. Admin se contact karo ya plan upgrade karo."
        )

    # RBAC
    from app.core.auth import check_permission, get_intent_permission
    from app.agents.auto_router import get_router

    route_result  = await get_router().route(req.message, req.model)
    intent        = req.intent or route_result["intent"]
    required_perm = get_intent_permission(intent)
    if not check_permission(user, required_perm, req.repo_id):
        raise HTTPException(
            status_code=403,
            detail=f"Permission '{required_perm}' nahi hai is repo mein."
        )

    session_id = req.session_id or str(uuid.uuid4())[:12]

    # Observability
    from app.core.observability import get_obs
    obs = get_obs()

    with obs.measure(
        "chat_request",
        user_id=user.user_id, repo_id=req.repo_id,
        session_id=session_id, intent=intent, action="handle"
    ):
        from app.agents.delegation_manager import DelegationManager
        dm     = DelegationManager(store=orch.store, repo_id=req.repo_id)
        result = await dm.execute(
            message    = req.message,
            session_id = session_id,
            intent     = intent,
            target     = req.target,
            model      = req.model,
        )

    # ✅ SUCCESS ke baad credit deduct karo
    deduct_credit(user.user_id, reason="chat_message")

    result["session_id"] = session_id
    return {"status": "success", "data": result}


# ── Streaming Chat (SSE) ───────────────────────────────────────────────────────

@chat_router.post("/stream")
async def chat_stream(
    req: ChatRequest,
    authorization: Optional[str] = Header(None),
):
    """
    Streaming SSE endpoint.
    Response tokens stream karte hain real-time mein.
    """
    user = await _get_user(authorization)
    orch = _get_orch(req.repo_id)

    session_id = req.session_id or str(uuid.uuid4())[:12]

    async def event_generator() -> AsyncGenerator[str, None]:
        # ✅ Credit check — stream shuru karne se PEHLE
        from app.core.user_admin import has_credits, deduct_credit
        if not has_credits(user.user_id):
            yield f"data: {json.dumps({'content': 'Credits khatam ho gaye.', 'done': True, 'error': True, 'error_code': 'INSUFFICIENT_CREDITS'})}\n\n"
            return

        try:
            from app.agents.delegation_manager import DelegationManager
            dm = DelegationManager(store=orch.store, repo_id=req.repo_id)

            async for chunk in dm.execute_stream(
                message    = req.message,
                session_id = session_id,
                intent     = req.intent,
                target     = req.target,
                model      = req.model,
            ):
                payload = chunk.model_dump()
                yield f"data: {json.dumps(payload)}\n\n"

            # ✅ Stream complete hone ke baad credit deduct karo
            deduct_credit(user.user_id, reason="chat_stream")

            # Final done event
            yield f"data: {json.dumps({'content': '', 'done': True})}\n\n"

        except Exception as e:
            error_payload = {"content": f"Stream error: {e}", "done": True, "error": True}
            yield f"data: {json.dumps(error_payload)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":               "no-cache",
            "X-Accel-Buffering":           "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


# ── Async Chat (Celery background task) ────────────────────────────────────────

@chat_router.post("/async")
async def chat_async(
    req: ChatRequest,
    authorization: Optional[str] = Header(None),
):
    """
    Background task — heavy queries ke liye.
    Returns task_id immediately, poll /async/:task_id for result.
    """
    user       = await _get_user(authorization)
    orch       = _get_orch(req.repo_id)
    session_id = req.session_id or str(uuid.uuid4())[:12]

    # ✅ Credit check
    from app.core.user_admin import has_credits, deduct_credit
    if not has_credits(user.user_id):
        raise HTTPException(
            status_code=402,
            detail="Credits khatam ho gaye. Admin se contact karo ya plan upgrade karo."
        )

    from app.agents.auto_router import get_router
    route_result = await get_router().route(req.message, req.model)
    intent       = req.intent or route_result["intent"]

    # ✅ Task queue mein dalne se PEHLE credit deduct karo
    deduct_credit(user.user_id, reason="chat_async")

    from app.tasks import run_agent_task
    task = run_agent_task.delay(
        repo_id    = req.repo_id,
        message    = req.message,
        session_id = session_id,
        intent     = intent,
        target     = req.target,
        model      = req.model,
        user_id    = user.user_id,
    )

    return {
        "status":     "queued",
        "task_id":    task.id,
        "session_id": session_id,
        "intent":     intent,
        "poll_url":   f"/api/chat/async/{task.id}",
    }


@chat_router.get("/async/{task_id}")
async def get_async_result(
    task_id: str,
    authorization: Optional[str] = Header(None),
):
    """Poll background task result."""
    await _get_user(authorization)

    from app.celery_app import celery_app
    task = celery_app.AsyncResult(task_id)

    if task.state == "PENDING":
        return {"status": "pending", "task_id": task_id}
    elif task.state == "PROGRESS":
        return {"status": "running", "task_id": task_id, "meta": task.info}
    elif task.state == "SUCCESS":
        return {"status": "success", "task_id": task_id, "data": task.result}
    elif task.state == "FAILURE":
        return {"status": "failed", "task_id": task_id, "error": str(task.result)}
    else:
        return {"status": task.state.lower(), "task_id": task_id}


# ── History ───────────────────────────────────────────────────────────────────

@chat_router.get("/history/{session_id}")
async def get_history(
    session_id: str,
    authorization: Optional[str] = Header(None),
):
    """Conversation history fetch karo."""
    await _get_user(authorization)

    from app.core.conversation_store import ConversationStore
    store   = ConversationStore()
    history = store.get_history(session_id, last_n=50)
    info    = store.get_session_info(session_id)
    return {"status": "success", "data": {"history": history, "session": info}}


@chat_router.get("/sessions/{repo_id}")
async def list_sessions(
    repo_id: str,
    authorization: Optional[str] = Header(None),
):
    """Repo ke saare sessions list karo."""
    await _get_user(authorization)

    from app.core.conversation_store import ConversationStore
    store    = ConversationStore()
    sessions = store.list_sessions(repo_id)
    return {"status": "success", "data": sessions}


# ── Build ─────────────────────────────────────────────────────────────────────

@chat_router.post("/build")
async def build_chat(
    req: BuildRequest,
    authorization: Optional[str] = Header(None),
):
    """Multi-step Build Agent endpoint."""
    user = await _get_user(authorization)

    from app.core.auth import check_permission
    if not check_permission(user, "build", req.repo_id):
        raise HTTPException(status_code=403, detail="Build permission nahi hai.")

    orch = _get_orch(req.repo_id)

    from app.agents.build_agent import BuildAgent
    agent = BuildAgent(orch.store, req.repo_id)

    if req.action == "clarify":
        result = agent.clarify(req.session_id, req.message, req.model)
    elif req.action == "spec":
        result = agent.make_spec(req.session_id, req.answers or {}, req.model)
    elif req.action == "build":
        result = agent.build(req.session_id, req.approved, req.model)
    elif req.action == "push_pr":
        if not req.github_token or not req.repo_full_name:
            raise HTTPException(
                status_code=400,
                detail="github_token aur repo_full_name chahiye push_pr ke liye."
            )
        result = agent.push_pr(req.session_id, req.github_token, req.repo_full_name)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {req.action}")

    return {"status": "success", "data": result}


# ── Semantic Search ────────────────────────────────────────────────────────────

@chat_router.post("/semantic-search")
async def semantic_search(
    req: SemanticSearchRequest,
    authorization: Optional[str] = Header(None),
):
    """Phase 4: Vector-based semantic search."""
    await _get_user(authorization)

    from app.core.vector_memory import get_vector_memory
    vm      = get_vector_memory(req.repo_id)
    results = vm.search(req.query, top_k=req.top_k, node_type=req.node_type)

    return {"status": "success", "data": {
        "results": results,
        "query":   req.query,
        "count":   len(results),
    }}