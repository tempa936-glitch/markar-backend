"""
Chat endpoint — frontend yahan se message bhejega.
POST /api/chat
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.services.repo_service import get_orchestrator_by_id

chat_router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    repo_id:  str
    message:  str
    model:    Optional[str] = None   # claude-3-5-haiku, gpt-4o-mini, etc
    target:   Optional[str] = None   # specific file ya function


@chat_router.post("")
async def chat(req: ChatRequest):
    """
    User ka message lo, Supervisor Agent se process karo,
    structured response wapas do.
    """
    orch = get_orchestrator_by_id(req.repo_id)
    if not orch:
        raise HTTPException(
            status_code=404,
            detail=f"Repo '{req.repo_id}' ready nahi hai."
        )

    from app.agents.supervisor import SupervisorAgent
    supervisor = SupervisorAgent(orch.store, req.repo_id)

    result = supervisor.handle(
        message=req.message,
        model=req.model,
        target=req.target,
    )

    return {"status": "success", "data": result}

class BuildRequest(BaseModel):
    repo_id:    str
    session_id: str
    action:     str   # "clarify" | "spec" | "build" | "push_pr"
    message:    Optional[str] = None
    answers:    Optional[Dict] = None
    approved:   Optional[bool] = None
    model:      Optional[str]  = None
    github_token:    Optional[str] = None
    repo_full_name:  Optional[str] = None


@chat_router.post("/build")
async def build_chat(req: BuildRequest):
    """
    Multi-step Build Agent endpoint.

    Step 1: action="clarify", message="add rate limiting"
    Step 2: action="spec",    answers={"Q1": "A1", "Q2": "A2"}
    Step 3: action="build",   approved=True
    Step 4: action="push_pr", github_token="...", repo_full_name="owner/repo"
    """
    orch = get_orchestrator_by_id(req.repo_id)
    if not orch:
        raise HTTPException(status_code=404,
                            detail=f"Repo '{req.repo_id}' ready nahi hai.")

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
            raise HTTPException(status_code=400,
                                detail="github_token aur repo_full_name chahiye.")
        result = agent.push_pr(
            req.session_id, req.github_token, req.repo_full_name
        )
    else:
        raise HTTPException(status_code=400,
                            detail=f"Unknown action: {req.action}")

    return {"status": "success", "data": result}