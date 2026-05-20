"""
Admin Routes — Full Control Panel.

Existing routes (untouched):
  POST /api/admin/token               — dev token generate
  GET  /api/admin/stats/{repo_id}     — repo usage stats
  GET  /api/admin/errors/{repo_id}    — recent errors
  GET  /api/admin/audit/{session_id}  — session audit
  POST /api/admin/repos               — repo register
  GET  /api/admin/repos/me            — my repos
  POST /api/admin/repos/{repo_id}/members
  POST /api/admin/custom-agents
  GET  /api/admin/custom-agents/{repo_id}
  DELETE /api/admin/custom-agents/{agent_id}
  GET  /api/admin/graph-changes/{repo_id}
  GET  /api/admin/vector-stats/{repo_id}

NEW — User Management:
  GET  /api/admin/users                     — all users list
  GET  /api/admin/users/{user_id}           — user detail
  GET  /api/admin/users/{user_id}/limits    — user limits
  PUT  /api/admin/users/{user_id}/limits    — update limits / change plan
  GET  /api/admin/users/{user_id}/credits   — credit balance
  POST /api/admin/users/{user_id}/credits   — add/deduct credits
  POST /api/admin/users/{user_id}/unlimited — unlimited on/off
  GET  /api/admin/users/{user_id}/credit-log — credit history
  POST /api/admin/users/{user_id}/activate  — activate/deactivate user
  GET  /api/admin/users/{user_id}/repo-limit — repo limit check
"""
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional, List

admin_router = APIRouter(prefix="/api/admin", tags=["admin"])


# ═══════════════════════════════════════════════════════════════════════════
# Helper — admin auth check
# ═══════════════════════════════════════════════════════════════════════════

async def _require_admin(authorization: Optional[str]) -> "TokenPayload":  # noqa
    from app.core.auth import get_current_user, Role
    user = await get_current_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if user.role != Role.ADMIN:
        raise HTTPException(status_code=403, detail="Admin role chahiye.")
    return user


# ═══════════════════════════════════════════════════════════════════════════
# ── EXISTING ROUTES (unchanged) ──────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════

class TokenRequest(BaseModel):
    user_id: str = "admin"
    repo_id: str = "*"
    role:    str = "admin"
    secret:  str


@admin_router.post("/token", summary="Dev/Admin token generate karo")
async def create_token(req: TokenRequest):
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


@admin_router.get("/stats/{repo_id}", summary="Repo usage stats")
async def repo_stats(repo_id: str, hours: int = 24,
                     authorization: Optional[str] = Header(None)):
    from app.core.auth import get_current_user, check_permission
    user = await get_current_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not check_permission(user, "admin", repo_id):
        raise HTTPException(status_code=403, detail="Admin permission chahiye.")
    from app.core.observability import get_obs
    return {"status": "success", "data": get_obs().get_repo_stats(repo_id, hours=hours)}


@admin_router.get("/errors/{repo_id}", summary="Recent errors")
async def recent_errors(repo_id: str, limit: int = 10,
                        authorization: Optional[str] = Header(None)):
    from app.core.auth import get_current_user, check_permission
    user = await get_current_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not check_permission(user, "admin", repo_id):
        raise HTTPException(status_code=403, detail="Admin permission chahiye.")
    from app.core.observability import get_obs
    return {"status": "success", "data": get_obs().get_recent_errors(repo_id, limit=limit)}


@admin_router.get("/audit/{session_id}", summary="Session audit trail")
async def session_audit(session_id: str,
                        authorization: Optional[str] = Header(None)):
    from app.core.auth import get_current_user
    user = await get_current_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    from app.core.observability import get_obs
    return {"status": "success", "data": get_obs().get_session_audit(session_id)}


class RepoRegisterRequest(BaseModel):
    repo_id:     str
    name:        str
    description: Optional[str] = ""
    graph_path:  Optional[str] = ""


@admin_router.post("/repos", summary="Naya repo register karo")
async def register_repo(req: RepoRegisterRequest,
                        authorization: Optional[str] = Header(None)):
    from app.core.auth import get_current_user
    user = await get_current_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    from app.core.multi_repo import get_repo_manager
    repo = get_repo_manager().register_repo(
        repo_id=req.repo_id, name=req.name, owner_id=user.user_id,
        description=req.description or "", graph_path=req.graph_path or "",
    )
    return {"status": "success", "data": repo}


@admin_router.get("/repos/me", summary="Mujhe accessible repos")
async def my_repos(authorization: Optional[str] = Header(None)):
    from app.core.auth import get_current_user
    user = await get_current_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    from app.core.multi_repo import get_repo_manager
    return {"status": "success",
            "data": get_repo_manager().cross_repo_summary(user.user_id)}


class AddMemberRequest(BaseModel):
    user_id: str
    role:    str = "viewer"


@admin_router.post("/repos/{repo_id}/members", summary="Repo mein member add")
async def add_member(repo_id: str, req: AddMemberRequest,
                     authorization: Optional[str] = Header(None)):
    from app.core.auth import get_current_user, check_permission
    user = await get_current_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not check_permission(user, "admin", repo_id):
        raise HTTPException(status_code=403, detail="Admin permission chahiye.")
    from app.core.multi_repo import get_repo_manager
    return {"status": "success",
            "data": get_repo_manager().add_member(repo_id, req.user_id, req.role)}


class CustomAgentRequest(BaseModel):
    repo_id:       str
    name:          str
    description:   Optional[str] = ""
    system_prompt: str
    triggers:      List[str]
    capabilities:  Optional[List[str]] = []


@admin_router.post("/custom-agents", summary="Custom agent banao")
async def create_custom_agent(req: CustomAgentRequest,
                              authorization: Optional[str] = Header(None)):
    from app.core.auth import get_current_user, check_permission
    user = await get_current_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not check_permission(user, "admin", req.repo_id):
        raise HTTPException(status_code=403, detail="Admin permission chahiye.")
    from app.core.custom_agents import get_custom_agent_manager
    agent = get_custom_agent_manager().create_agent({
        "repo_id": req.repo_id, "name": req.name,
        "description": req.description, "system_prompt": req.system_prompt,
        "triggers": req.triggers, "capabilities": req.capabilities,
        "created_by": user.user_id,
    })
    return {"status": "success", "data": agent}


@admin_router.get("/custom-agents/{repo_id}", summary="Repo ke custom agents")
async def list_custom_agents(repo_id: str,
                             authorization: Optional[str] = Header(None)):
    from app.core.auth import get_current_user
    user = await get_current_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    from app.core.custom_agents import get_custom_agent_manager
    return {"status": "success",
            "data": get_custom_agent_manager().list_repo_agents(repo_id)}


@admin_router.delete("/custom-agents/{agent_id}", summary="Custom agent delete")
async def delete_custom_agent(agent_id: str,
                              authorization: Optional[str] = Header(None)):
    from app.core.auth import get_current_user
    user = await get_current_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    from app.core.custom_agents import get_custom_agent_manager
    get_custom_agent_manager().delete_agent(agent_id)
    return {"status": "success", "data": {"deleted": agent_id}}


@admin_router.get("/graph-changes/{repo_id}", summary="Graph changelog")
async def graph_changes(repo_id: str,
                        authorization: Optional[str] = Header(None)):
    from app.core.auth import get_current_user
    user = await get_current_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    from app.core.incremental_graph import IncrementalGraphUpdater
    updater = IncrementalGraphUpdater(repo_id, None)
    return {"status": "success", "data": updater.get_changelog(limit=20)}


@admin_router.get("/vector-stats/{repo_id}", summary="Vector memory stats")
async def vector_stats(repo_id: str,
                       authorization: Optional[str] = Header(None)):
    from app.core.auth import get_current_user
    user = await get_current_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    from app.core.vector_memory import get_vector_memory
    return {"status": "success",
            "data": get_vector_memory(repo_id).get_stats()}


# ═══════════════════════════════════════════════════════════════════════════
# ── NEW ROUTES — User Management ─────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════

# ── List all users ────────────────────────────────────────────────────────

@admin_router.get(
    "/users",
    summary="Saare users ki list (admin only)",
    description="Pagination: ?limit=50&offset=0",
)
async def list_users(
    limit: int = 50,
    offset: int = 0,
    authorization: Optional[str] = Header(None),
):
    await _require_admin(authorization)
    from app.core.user_admin import list_all_users
    users = list_all_users(limit=limit, offset=offset)
    return {
        "status": "success",
        "data": {
            "users": users,
            "count": len(users),
            "limit": limit,
            "offset": offset,
        },
    }


# ── Single user detail ────────────────────────────────────────────────────

@admin_router.get(
    "/users/{user_id}",
    summary="User ki poori detail — limits, credits, repos",
)
async def get_user(user_id: str,
                   authorization: Optional[str] = Header(None)):
    await _require_admin(authorization)
    from app.core.user_admin import get_user_detail
    detail = get_user_detail(user_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"User '{user_id}' nahi mila.")
    return {"status": "success", "data": detail}


# ── User limits GET ───────────────────────────────────────────────────────

@admin_router.get(
    "/users/{user_id}/limits",
    summary="User ke current limits dekho",
)
async def get_limits(user_id: str,
                     authorization: Optional[str] = Header(None)):
    await _require_admin(authorization)
    from app.core.user_admin import get_user_limits
    return {"status": "success", "data": get_user_limits(user_id)}


# ── User limits PUT ───────────────────────────────────────────────────────

class UpdateLimitsRequest(BaseModel):
    plan:             Optional[str]  = None   # "free" | "pro" | "enterprise"
    max_repos:        Optional[int]  = None
    max_repo_size_mb: Optional[int]  = None
    max_messages_day: Optional[int]  = None
    is_active:        Optional[int]  = None   # 1 = active, 0 = deactivated
    notes:            Optional[str]  = None


@admin_router.put(
    "/users/{user_id}/limits",
    summary="User ke limits update karo — plan change, size limit, repo count",
)
async def update_limits(
    user_id: str,
    req: UpdateLimitsRequest,
    authorization: Optional[str] = Header(None),
):
    admin = await _require_admin(authorization)

    if req.plan and req.plan not in ("free", "pro", "enterprise"):
        raise HTTPException(
            status_code=400,
            detail="Plan sirf 'free', 'pro', ya 'enterprise' ho sakta hai.",
        )

    from app.core.user_admin import set_user_limits, get_user_detail
    updated = set_user_limits(
        user_id=user_id,
        plan=req.plan,
        max_repos=req.max_repos,
        max_repo_size_mb=req.max_repo_size_mb,
        max_messages_day=req.max_messages_day,
        is_active=req.is_active,
        notes=req.notes,
        updated_by=admin.user_id,
    )
    return {
        "status": "success",
        "message": f"User '{user_id}' ke limits update ho gaye.",
        "data": updated,
    }


# ── Credits GET ───────────────────────────────────────────────────────────

@admin_router.get(
    "/users/{user_id}/credits",
    summary="User ka credit balance",
)
async def get_credits(user_id: str,
                      authorization: Optional[str] = Header(None)):
    await _require_admin(authorization)
    from app.core.user_admin import get_user_credits
    return {"status": "success", "data": get_user_credits(user_id)}


# ── Credits ADD/DEDUCT ────────────────────────────────────────────────────

class AddCreditsRequest(BaseModel):
    amount: int        # positive = add, negative = deduct
    reason: str = "admin_grant"


@admin_router.post(
    "/users/{user_id}/credits",
    summary="Credits add ya deduct karo",
    description="amount > 0 = add credits, amount < 0 = deduct credits",
)
async def add_credits_route(
    user_id: str,
    req: AddCreditsRequest,
    authorization: Optional[str] = Header(None),
):
    admin = await _require_admin(authorization)

    if req.amount == 0:
        raise HTTPException(status_code=400, detail="Amount 0 nahi ho sakta.")

    from app.core.user_admin import add_credits
    updated = add_credits(
        user_id=user_id,
        amount=req.amount,
        reason=req.reason,
        admin_id=admin.user_id,
    )
    action = "add" if req.amount > 0 else "deduct"
    return {
        "status":  "success",
        "message": f"{abs(req.amount)} credits {action} ho gaye user '{user_id}' ke liye.",
        "data":    updated,
    }


# ── Unlimited access toggle ───────────────────────────────────────────────

class UnlimitedRequest(BaseModel):
    unlimited: bool   # True = unlimited on, False = off


@admin_router.post(
    "/users/{user_id}/unlimited",
    summary="User ko unlimited access do ya hato",
)
async def set_unlimited_route(
    user_id: str,
    req: UnlimitedRequest,
    authorization: Optional[str] = Header(None),
):
    admin = await _require_admin(authorization)
    from app.core.user_admin import set_unlimited, get_user_detail
    updated = set_unlimited(
        user_id=user_id,
        unlimited=req.unlimited,
        admin_id=admin.user_id,
    )
    status_msg = "diya gaya" if req.unlimited else "hata diya gaya"
    return {
        "status":  "success",
        "message": f"User '{user_id}' ko unlimited access {status_msg}.",
        "data":    updated,
    }


# ── Credit log ────────────────────────────────────────────────────────────

@admin_router.get(
    "/users/{user_id}/credit-log",
    summary="User ke credit transactions ka history",
)
async def credit_log(
    user_id: str,
    limit: int = 20,
    authorization: Optional[str] = Header(None),
):
    await _require_admin(authorization)
    from app.core.user_admin import get_credit_log
    return {
        "status": "success",
        "data": get_credit_log(user_id, limit=limit),
    }


# ── Activate / Deactivate user ────────────────────────────────────────────

class ActivateRequest(BaseModel):
    is_active: bool


@admin_router.post(
    "/users/{user_id}/activate",
    summary="User account activate ya deactivate karo",
)
async def activate_user(
    user_id: str,
    req: ActivateRequest,
    authorization: Optional[str] = Header(None),
):
    admin = await _require_admin(authorization)
    from app.core.user_admin import set_user_limits
    updated = set_user_limits(
        user_id=user_id,
        is_active=1 if req.is_active else 0,
        updated_by=admin.user_id,
    )
    action = "activate" if req.is_active else "deactivate"
    return {
        "status":  "success",
        "message": f"User '{user_id}' {action} ho gaya.",
        "data":    {"is_active": updated["is_active"]},
    }


# ── Repo limit check ──────────────────────────────────────────────────────

@admin_router.get(
    "/users/{user_id}/repo-limit",
    summary="User aur repo add kar sakta hai?",
)
async def repo_limit_check(
    user_id: str,
    authorization: Optional[str] = Header(None),
):
    await _require_admin(authorization)
    from app.core.user_admin import check_repo_limit
    return {"status": "success", "data": check_repo_limit(user_id)}
