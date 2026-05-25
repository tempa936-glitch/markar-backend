"""
Trace Routes  — GET /api/chat/trace/:session_id
Recipe Routes — POST /api/recipes/run, GET /api/recipes/list, etc.
Agents Routes — GET /api/agents/list, POST /api/agents/create, specialists
"""
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional, List, Dict

# ═══════════════════════════════════════════════════════════════════════════
# TRACE ROUTES
# ═══════════════════════════════════════════════════════════════════════════

trace_router = APIRouter(prefix="/api/chat", tags=["trace"])


@trace_router.get("/trace/{session_id}", summary="Session ka execution trace")
async def get_trace(
    session_id: str,
    authorization: Optional[str] = Header(None),
):
    """
    Ek session ka poora agent execution trace.
    Frontend timeline UI ke liye.
    Returns: events list, timeline, latency stats, tokens used.
    """
    from app.core.auth import get_current_user
    user = await get_current_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    from app.core.trace_manager import get_tracer
    trace = get_tracer().get_trace(session_id)
    return {"status": "success", "data": trace}


@trace_router.get("/traces/recent", summary="Recent sessions ka trace summary")
async def recent_traces(
    limit: int = 20,
    authorization: Optional[str] = Header(None),
):
    from app.core.auth import get_current_user
    user = await get_current_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    from app.core.trace_manager import get_tracer
    traces = get_tracer().get_recent_traces(limit=limit)
    return {"status": "success", "data": traces}


# ═══════════════════════════════════════════════════════════════════════════
# RECIPE ROUTES
# ═══════════════════════════════════════════════════════════════════════════

recipe_router = APIRouter(prefix="/api/recipes", tags=["recipes"])


class RecipeRunRequest(BaseModel):
    recipe_id:  str
    repo_id:    str
    message:    str           # user ka input / feature request / bug description
    target:     Optional[str] = ""
    model:      Optional[str] = None
    session_id: Optional[str] = None


class CreateRecipeRequest(BaseModel):
    name:        str
    description: Optional[str] = ""
    repo_id:     Optional[str] = "*"
    steps: List[Dict]  # list of RecipeStep dicts


@recipe_router.get("/list", summary="Available recipes list")
async def list_recipes(
    repo_id: Optional[str] = "*",
    authorization: Optional[str] = Header(None),
):
    """Built-in + repo-specific recipes."""
    from app.core.auth import get_current_user
    user = await get_current_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    from app.core.recipe_engine import get_recipe_engine
    recipes = get_recipe_engine().list_recipes(repo_id or "*")
    return {"status": "success", "data": recipes}


@recipe_router.post("/run", summary="Recipe execute karo")
async def run_recipe(
    req: RecipeRunRequest,
    authorization: Optional[str] = Header(None),
):
    """
    Multi-step recipe run karo.
    Har step automatically execute hogi, prev output next step mein jaayegi.
    """
    from app.core.auth import get_current_user
    user = await get_current_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Credit check — recipe = multiple steps = multiple credits
    from app.core.user_admin import has_credits
    if not has_credits(user.user_id):
        raise HTTPException(
            status_code=402,
            detail="Credits khatam ho gaye. Recipe run ke liye credits chahiye."
        )

    from app.services.repo_service import get_orchestrator_by_id
    orch = get_orchestrator_by_id(req.repo_id)
    if not orch:
        raise HTTPException(
            status_code=404,
            detail=f"Repo '{req.repo_id}' ready nahi. Pehle index karo."
        )

    import uuid
    session_id = req.session_id or str(uuid.uuid4())[:12]

    from app.core.recipe_engine import get_recipe_engine
    result = await get_recipe_engine().run(
        recipe_id  = req.recipe_id,
        session_id = session_id,
        repo_id    = req.repo_id,
        user_input = req.message,
        target     = req.target or "",
        model      = req.model,
        user_id    = user.user_id,
        store      = orch.store,
    )

    if result.get("status") == "failed":
        raise HTTPException(status_code=500, detail=result)

    return {"status": "success", "data": result}


@recipe_router.get("/run/{run_id}", summary="Recipe run ka status/result")
async def get_run(
    run_id: str,
    authorization: Optional[str] = Header(None),
):
    from app.core.auth import get_current_user
    user = await get_current_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    from app.core.recipe_engine import get_recipe_engine
    run = get_recipe_engine().get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' nahi mili.")
    return {"status": "success", "data": run}


@recipe_router.post("/create", summary="Custom recipe banao")
async def create_recipe(
    req: CreateRecipeRequest,
    authorization: Optional[str] = Header(None),
):
    from app.core.auth import get_current_user
    user = await get_current_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    from app.core.recipe_engine import get_recipe_engine
    result = get_recipe_engine().create_recipe({
        "name":        req.name,
        "description": req.description,
        "repo_id":     req.repo_id or "*",
        "steps":       req.steps,
        "created_by":  user.user_id,
    })
    return {"status": "success", "data": result}


# ═══════════════════════════════════════════════════════════════════════════
# AGENTS (Specialists + Custom) ROUTES
# ═══════════════════════════════════════════════════════════════════════════

agents_router = APIRouter(prefix="/api/agents", tags=["agents"])


class CreateAgentRequest(BaseModel):
    repo_id:       str
    name:          str
    description:   Optional[str] = ""
    system_prompt: str
    triggers:      List[str]
    capabilities:  Optional[List[str]] = []


@agents_router.get("/list/{repo_id}", summary="Repo ke custom agents + specialists")
async def list_agents(
    repo_id: str,
    authorization: Optional[str] = Header(None),
):
    """Custom agents (repo-specific) + built-in specialists dono."""
    from app.core.auth import get_current_user
    user = await get_current_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    from app.core.custom_agents import get_custom_agent_manager
    from app.core.specialist_agents import get_all_specialists

    custom      = get_custom_agent_manager().list_repo_agents(repo_id)
    specialists = get_all_specialists()

    return {
        "status": "success",
        "data": {
            "custom_agents": custom,
            "specialists":   specialists,
            "total":         len(custom) + len(specialists),
        },
    }


@agents_router.post("/create", summary="Custom agent create karo")
async def create_agent(
    req: CreateAgentRequest,
    authorization: Optional[str] = Header(None),
):
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


@agents_router.delete("/{agent_id}", summary="Custom agent delete")
async def delete_agent(
    agent_id: str,
    authorization: Optional[str] = Header(None),
):
    from app.core.auth import get_current_user
    user = await get_current_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    from app.core.custom_agents import get_custom_agent_manager
    get_custom_agent_manager().delete_agent(agent_id)
    return {"status": "success", "data": {"deleted": agent_id}}


@agents_router.get("/specialists", summary="Built-in specialists list (public)")
async def list_specialists():
    """No auth — frontend pe specialist list dikhane ke liye."""
    from app.core.specialist_agents import get_all_specialists
    return {"status": "success", "data": get_all_specialists()}



# ═══════════════════════════════════════════════════════════════════════════
# FORGE ROUTES — Build agent diff view
# ═══════════════════════════════════════════════════════════════════════════

forge_router = APIRouter(prefix="/api/forge", tags=["forge"])


@forge_router.get("/diff/{session_id}", summary="Generated code ka diff view")
async def get_diff(
    session_id: str,
    authorization: Optional[str] = Header(None),
):
    """
    Build agent ke generated code ka unified diff.
    Frontend mein GitHub-style diff view dikhao.
    """
    from app.core.auth import get_current_user
    user = await get_current_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    from app.agents.delegation_manager import DelegationManager
    dm    = DelegationManager()
    agent = dm._get_agent("build", session_id)
    diff  = agent.get_diff(session_id)

    if diff.get("error"):
        raise HTTPException(status_code=404, detail=diff["error"])

    return {"status": "success", "data": diff}


# ═══════════════════════════════════════════════════════════════════════════
# SANDBOX ROUTES — Isolated code execution
# ═══════════════════════════════════════════════════════════════════════════

sandbox_router = APIRouter(prefix="/api/sandbox", tags=["sandbox"])


class SandboxRunRequest(BaseModel):
    code:     str
    language: str = "python"    # python | javascript | typescript | bash
    timeout:  int = 15


class SyntaxCheckRequest(BaseModel):
    code:     str
    language: str = "python"


@sandbox_router.post("/run", summary="Code safely execute karo (isolated)")
async def sandbox_run(
    req: SandboxRunRequest,
    authorization: Optional[str] = Header(None),
):
    """
    Code ko isolated sandbox mein run karo.
    Docker available → Docker container (network=none, mem=128m)
    Docker nahi → subprocess + timeout
    """
    from app.core.auth import get_current_user
    user = await get_current_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Credit check
    from app.core.user_admin import has_credits
    if not has_credits(user.user_id):
        raise HTTPException(status_code=402, detail="Credits khatam ho gaye.")

    if len(req.code) > 50_000:
        raise HTTPException(status_code=400, detail="Code too large (max 50KB).")

    from app.services.sandbox_service import get_sandbox
    result = await get_sandbox().run(
        code=req.code,
        language=req.language,
        timeout=min(req.timeout, 30),
    )
    return {"status": "success", "data": result.to_dict()}


@sandbox_router.post("/syntax", summary="Syntax check only (no execution)")
async def syntax_check(
    req: SyntaxCheckRequest,
    authorization: Optional[str] = Header(None),
):
    """Fast syntax validation — no execution, no credits needed."""
    from app.core.auth import get_current_user
    user = await get_current_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    from app.services.sandbox_service import get_sandbox
    result = await get_sandbox().syntax_only(req.code, req.language)
    return {"status": "success", "data": result}


@sandbox_router.get("/status", summary="Sandbox mode aur capabilities")
async def sandbox_status():
    """No auth — frontend ko batao kaunsa mode active hai."""
    from app.services.sandbox_service import get_sandbox, LANG_CONFIGS
    sb = get_sandbox()
    return {
        "status": "success",
        "data": {
            "mode":               sb._mode,
            "supported_languages": list(LANG_CONFIGS.keys()),
            "max_timeout_sec":    30,
            "max_output_kb":      32,
            "docker_available":   sb._mode == "docker",
        },
    }
