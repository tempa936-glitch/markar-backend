"""
Phase 3 — Admin Routes.
Auth, RBAC, Audit logs, Observability endpoints.
"""
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional, List

admin_router = APIRouter(prefix="/api/admin", tags=["admin"])


# ── Auth endpoints ────────────────────────────────────────────────────────
class TokenRequest(BaseModel):
    user_id:  str
    repo_id:  str
    role:     str = "viewer"
    secret:   str  # Admin secret for token generation


@admin_router.post("/token")
async def create_token(req: TokenRequest):
    """Dev/admin ke liye token generate karo."""
    admin_secret = __import__("os").getenv("MARKAR_ADMIN_SECRET", "markar-admin-dev")
    if req.secret != admin_secret:
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.core.auth import create_token, Role
    try:
        role = Role(req.role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid role: {req.role}")

    token = create_token(req.user_id, req.repo_id, role)
    return {"status": "success", "data": {"token": token, "role": role.value}}


# ── Observability endpoints ───────────────────────────────────────────────
@admin_router.get("/stats/{repo_id}")
async def repo_stats(repo_id: str, hours: int = 24,
                     authorization: Optional[str] = Header(None)):
    """Repo ke last N hours ki usage stats."""
    from app.core.auth import get_current_user, check_permission
    user = await get_current_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not check_permission(user, "admin", repo_id):
        raise HTTPException(status_code=403, detail="Admin permission chahiye.")

    from app.core.observability import get_obs
    stats = get_obs().get_repo_stats(repo_id, hours=hours)
    return {"status": "success", "data": stats}


@admin_router.get("/errors/{repo_id}")
async def recent_errors(repo_id: str, limit: int = 10,
                         authorization: Optional[str] = Header(None)):
    """Recent errors — debugging ke liye."""
    from app.core.auth import get_current_user, check_permission
    user = await get_current_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not check_permission(user, "admin", repo_id):
        raise HTTPException(status_code=403, detail="Admin permission chahiye.")

    from app.core.observability import get_obs
    errors = get_obs().get_recent_errors(repo_id, limit=limit)
    return {"status": "success", "data": errors}


@admin_router.get("/audit/{session_id}")
async def session_audit(session_id: str,
                         authorization: Optional[str] = Header(None)):
    """Session ka complete audit trail."""
    from app.core.auth import get_current_user
    user = await get_current_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    from app.core.observability import get_obs
    events = get_obs().get_session_audit(session_id)
    return {"status": "success", "data": events}


# ── Multi-repo endpoints ──────────────────────────────────────────────────
class RepoRegisterRequest(BaseModel):
    repo_id:     str
    name:        str
    description: Optional[str] = ""
    graph_path:  Optional[str] = ""


@admin_router.post("/repos")
async def register_repo(req: RepoRegisterRequest,
                         authorization: Optional[str] = Header(None)):
    """Naya repo register karo."""
    from app.core.auth import get_current_user
    user = await get_current_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    from app.core.multi_repo import get_repo_manager
    repo = get_repo_manager().register_repo(
        repo_id=req.repo_id,
        name=req.name,
        owner_id=user.user_id,
        description=req.description or "",
        graph_path=req.graph_path or "",
    )
    return {"status": "success", "data": repo}


@admin_router.get("/repos/me")
async def my_repos(authorization: Optional[str] = Header(None)):
    """Mujhe accessible saare repos."""
    from app.core.auth import get_current_user
    user = await get_current_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    from app.core.multi_repo import get_repo_manager
    summary = get_repo_manager().cross_repo_summary(user.user_id)
    return {"status": "success", "data": summary}


class AddMemberRequest(BaseModel):
    user_id: str
    role:    str = "viewer"


@admin_router.post("/repos/{repo_id}/members")
async def add_member(repo_id: str, req: AddMemberRequest,
                      authorization: Optional[str] = Header(None)):
    """Repo mein member add karo."""
    from app.core.auth import get_current_user, check_permission
    user = await get_current_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not check_permission(user, "admin", repo_id):
        raise HTTPException(status_code=403, detail="Admin permission chahiye.")

    from app.core.multi_repo import get_repo_manager
    result = get_repo_manager().add_member(repo_id, req.user_id, req.role)
    return {"status": "success", "data": result}


# ── Phase 4: Custom agent CRUD ────────────────────────────────────────────
class CustomAgentRequest(BaseModel):
    repo_id:       str
    name:          str
    description:   Optional[str] = ""
    system_prompt: str
    triggers:      List[str]
    capabilities:  Optional[List[str]] = []


@admin_router.post("/custom-agents")
async def create_custom_agent(req: CustomAgentRequest,
                               authorization: Optional[str] = Header(None)):
    """Custom agent banao."""
    from app.core.auth import get_current_user, check_permission
    user = await get_current_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not check_permission(user, "admin", req.repo_id):
        raise HTTPException(status_code=403, detail="Admin permission chahiye.")

    from app.core.custom_agents import get_custom_agent_manager
    agent = get_custom_agent_manager().create_agent({
        "repo_id":       req.repo_id,
        "name":          req.name,
        "description":   req.description,
        "system_prompt": req.system_prompt,
        "triggers":      req.triggers,
        "capabilities":  req.capabilities,
        "created_by":    user.user_id,
    })
    return {"status": "success", "data": agent}


@admin_router.get("/custom-agents/{repo_id}")
async def list_custom_agents(repo_id: str,
                              authorization: Optional[str] = Header(None)):
    """Repo ke custom agents list karo."""
    from app.core.auth import get_current_user
    user = await get_current_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    from app.core.custom_agents import get_custom_agent_manager
    agents = get_custom_agent_manager().list_repo_agents(repo_id)
    return {"status": "success", "data": agents}


@admin_router.delete("/custom-agents/{agent_id}")
async def delete_custom_agent(agent_id: str,
                               authorization: Optional[str] = Header(None)):
    """Custom agent delete karo."""
    from app.core.auth import get_current_user
    user = await get_current_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    from app.core.custom_agents import get_custom_agent_manager
    get_custom_agent_manager().delete_agent(agent_id)
    return {"status": "success", "data": {"deleted": agent_id}}


# ── Phase 4: Incremental graph endpoint ──────────────────────────────────
@admin_router.get("/graph-changes/{repo_id}")
async def graph_changes(repo_id: str,
                         authorization: Optional[str] = Header(None)):
    """Recent graph changes — incremental indexing log."""
    from app.core.auth import get_current_user
    user = await get_current_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    from app.core.incremental_graph import IncrementalGraphUpdater
    updater = IncrementalGraphUpdater(repo_id, None)
    changes = updater.get_changelog(limit=20)
    return {"status": "success", "data": changes}


# ── Phase 4: Vector memory stats ─────────────────────────────────────────
@admin_router.get("/vector-stats/{repo_id}")
async def vector_stats(repo_id: str,
                        authorization: Optional[str] = Header(None)):
    """Vector memory stats — kitne embeddings hain."""
    from app.core.auth import get_current_user
    user = await get_current_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    from app.core.vector_memory import get_vector_memory
    stats = get_vector_memory(repo_id).get_stats()
    return {"status": "success", "data": stats}
