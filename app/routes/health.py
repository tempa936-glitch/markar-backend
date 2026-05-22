"""
Markar Intelligence — All API Routes
Fixed: no duplicate router, git clone support, rich analysis.
"""

from fastapi import APIRouter, HTTPException, Query, Depends, Header, Request
from pydantic import BaseModel
from typing import List, Optional
import os, shutil, tempfile, hashlib

from app.code_intelligence import CodeIntelligenceOrchestrator, QueryType, WorkflowExecutor
from app.dependencies.code_intelligence import get_orchestrator, set_orchestrator
from fastapi.responses import StreamingResponse

from app.services.repo_service import (
    start_initialization,
    get_status as repo_get_status,
    get_orchestrator_by_id,
    list_all_repos,
    stream_status,
    get_files_page,
    get_file_detail,
)

# TWO separate routers — no duplicate
system_router = APIRouter(tags=["system"])
ci_router     = APIRouter(prefix="/api/code-intelligence", tags=["code-intelligence"])


# ── System ─────────────────────────────────────────────────────
@system_router.get("/")
async def root():
    return {"message": "Markar Intelligence is running", "version": "2.0.0"}

@system_router.get("/health")
async def health_check():
    return {"status": "healthy"}

@system_router.get("/version")
async def version():
    return {"version": "2.0.0"}


# ── Models ─────────────────────────────────────────────────────
class InitRequest(BaseModel):
    repo_path:  Optional[str] = None   # local path
    git_url:    Optional[str] = None   # https://github.com/...
    git_branch: Optional[str] = "main"

class ImpactAnalysisRequest(BaseModel):
    target: str

class DependencyAnalysisRequest(BaseModel):
    target: str

class RootCauseRequest(BaseModel):
    failing_node: str

class RefactoringRequest(BaseModel):
    target: str

class APIMigrationRequest(BaseModel):
    target: str
    description: str

class MultiChangeRequest(BaseModel):
    changes: List[str]

class CodeChangeWorkflowRequest(BaseModel):
    changed_files: List[str]

class CodeReviewWorkflowRequest(BaseModel):
    pr_description: str
    changed_files: List[str]


# ── Initialize — local path OR git URL ────────────────────────
@ci_router.post("/initialize")
async def initialize(
    request: InitRequest,
    authorization: Optional[str] = Header(None),  # ✅ Header se aayega ab
):
    """Initialize from local path OR GitHub URL — non-blocking."""

    # ── Step 1: user_id nikalo ──────────────────────────────
    user_id = None
    try:
        from app.core.auth import get_current_user
        user = await get_current_user(authorization)
        if user:
            user_id = user.user_id
    except Exception:
        pass

    # ── Step 2: Limits & Credit check (CLONE SE PEHLE) ───────────────
    if user_id:
        from app.core.user_admin import check_repo_limit
        repo_limit_check = check_repo_limit(user_id)
        if not repo_limit_check["allowed"]:
            raise HTTPException(
                status_code=403,
                detail=f"Repo limit reached. Aap apne plan me sirf {repo_limit_check['max']} repos add kar sakte hain. Purani repos delete karein ya admin se limit badhwayein."
            )

    if user_id and request.git_url:
        from app.core.user_admin import has_credits
        if not has_credits(user_id):
            raise HTTPException(
                status_code=402,
                detail="Credits khatam ho gaye. Repo index nahi ho sakta. Admin se contact karo."
            )
        # GitHub API se size + tier check — HUGE ya insufficient credits block
        from app.services.repo_service import _github_precheck
        precheck = _github_precheck(request.git_url, user_id)
        if precheck["blocked"]:
            raise HTTPException(
                status_code=402,
                detail=precheck["message"],
                headers={"X-Block-Reason": precheck.get("reason", "BLOCKED")}
            )

    # ── Step 3: Worker shuru karo ───────────────────────────
    result = start_initialization(
        git_url    = request.git_url,
        repo_path  = request.repo_path,
        git_branch = request.git_branch,
        user_id    = user_id,   # ✅ ab sahi user_id pass ho raha hai
    )
    return result


# ── Status — now returns RICH analysis ────────────────────────
@ci_router.get("/status/{repo_id}")
async def repo_status(repo_id: str):
    from app.services.repo_service import get_status as _get_status
    result = _get_status(repo_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Repo {repo_id} not found")
    return result


@ci_router.get("/status/{repo_id}/files")
async def repo_files(
    repo_id: str,
    page:      int = Query(default=1,  ge=1),
    page_size: int = Query(default=30, ge=1, le=200),
    risk:      Optional[str] = Query(default=None),
):
    """
    Paginated file list — Files tab ke liye.
    ?page=1&page_size=30&risk=HIGH
    """
    result = get_files_page(repo_id, page=page, page_size=page_size,
                            risk_filter=risk)
    if result is None:
        raise HTTPException(status_code=404,
                            detail="Repo not found or graph not ready yet")
    return result


@ci_router.get("/status/{repo_id}/file")
async def repo_file_detail(
    repo_id:   str,
    path:      str = Query(..., description="Relative file path, e.g. controllers/user.js"),
):
    """
    Ek file ka poora detail — graph node click pe.
    ?path=controllers/user.controller.js
    """
    result = get_file_detail(repo_id, file_path=path)
    if result is None:
        raise HTTPException(status_code=404,
                            detail="Repo not found or graph not ready")
    return result

@ci_router.get("/stream/{repo_id}")
async def stream_repo_status(repo_id: str):
    """
    SSE endpoint — status updates stream karo
    Frontend yahan connect kare aur wait kare
    """
    return StreamingResponse(
        stream_status(repo_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no", 
        }
    )        

@ci_router.get("/analyze")
async def analyze(
    orchestrator: CodeIntelligenceOrchestrator = Depends(get_orchestrator),
):
    """Standalone deep analysis."""
    try:
        return {"status": "success", "data": orchestrator.get_rich_analysis()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── All existing routes — unchanged ───────────────────────────
@ci_router.post("/analyze/impact")
async def analyze_impact(request: ImpactAnalysisRequest,
    orchestrator: CodeIntelligenceOrchestrator = Depends(get_orchestrator)):
    result = orchestrator.query(QueryType.IMPACT_ANALYSIS, target=request.target)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"status": "success", "data": result}

@ci_router.post("/analyze/dependencies")
async def analyze_dependencies(request: DependencyAnalysisRequest,
    orchestrator: CodeIntelligenceOrchestrator = Depends(get_orchestrator)):
    result = orchestrator.query(QueryType.DEPENDENCY_ANALYSIS, target=request.target)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"status": "success", "data": result}

@ci_router.post("/analyze/root-cause")
async def analyze_root_cause(request: RootCauseRequest,
    orchestrator: CodeIntelligenceOrchestrator = Depends(get_orchestrator)):
    result = orchestrator.query(QueryType.ROOT_CAUSE, failing_node=request.failing_node)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"status": "success", "data": result}

@ci_router.post("/suggest/refactoring")
async def suggest_refactoring(request: RefactoringRequest,
    orchestrator: CodeIntelligenceOrchestrator = Depends(get_orchestrator)):
    result = orchestrator.query(QueryType.REFACTORING, target=request.target)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"status": "success", "data": result}

@ci_router.post("/plan/api-migration")
async def plan_api_migration(request: APIMigrationRequest,
    orchestrator: CodeIntelligenceOrchestrator = Depends(get_orchestrator)):
    result = orchestrator.query(QueryType.API_MIGRATION,
        target=request.target, description=request.description)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"status": "success", "data": result}

@ci_router.post("/analyze/multi-change")
async def analyze_multi_change(request: MultiChangeRequest,
    orchestrator: CodeIntelligenceOrchestrator = Depends(get_orchestrator)):
    result = orchestrator.query(QueryType.MULTI_CHANGE, changes=request.changes)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"status": "success", "data": result}

@ci_router.get("/search")
async def search_nodes(query: str = Query(..., min_length=1),
    node_type: Optional[str] = None,
    orchestrator: CodeIntelligenceOrchestrator = Depends(get_orchestrator)):
    return {"status": "success", "data": orchestrator.search(query, node_type)}

@ci_router.get("/file-structure")
async def get_file_structure(file_path: str = Query(...),
    orchestrator: CodeIntelligenceOrchestrator = Depends(get_orchestrator)):
    structure = orchestrator.get_file_structure(file_path)
    if not structure:
        raise HTTPException(status_code=404, detail="File not found")
    return {"status": "success", "data": structure}

@ci_router.get("/stats")
async def get_stats(
    orchestrator: CodeIntelligenceOrchestrator = Depends(get_orchestrator)):
    return {"status": "success", "data": orchestrator.get_stats()}

@ci_router.get("/visualization/{repo_id}")
async def get_visualization(repo_id: str):
    orch = get_orchestrator_by_id(repo_id)
    if not orch:
        raise HTTPException(
            status_code=404,
            detail=f"Repo '{repo_id}' not ready. Initialize first."
        )
    return {"status": "success", "data": orch.export_visualization()}

@ci_router.post("/workflow/on-code-change")
async def workflow_on_code_change(request: CodeChangeWorkflowRequest,
    orchestrator: CodeIntelligenceOrchestrator = Depends(get_orchestrator)):
    executor = WorkflowExecutor(orchestrator)
    return {"status": "success", "data": executor.on_code_change(request.changed_files)}

@ci_router.post("/workflow/pre-deployment-check")
async def workflow_pre_deployment_check(ver: str = Query(..., alias="version"),
    orchestrator: CodeIntelligenceOrchestrator = Depends(get_orchestrator)):
    executor = WorkflowExecutor(orchestrator)
    return {"status": "success", "data": executor.on_deployment(ver)}

@ci_router.post("/workflow/code-review")
async def workflow_code_review(request: CodeReviewWorkflowRequest,
    orchestrator: CodeIntelligenceOrchestrator = Depends(get_orchestrator)):
    executor = WorkflowExecutor(orchestrator)
    return {"status": "success",
            "data": executor.on_code_review(request.pr_description, request.changed_files)}

# ── User Repos API ────────────────────────────────────────────────────────

@ci_router.get("/my-repos")
async def get_my_repos(request: Request):
    """
    Current user ke saare repos return karo.
    Frontend dashboard mein repo list ke liye.
    """
    from app.core.auth import get_user_repos, TokenPayload
    import os

    auth_enabled = os.getenv("MARKAR_AUTH_ENABLED", "false").lower() == "true"

    if not auth_enabled:
        # Dev mode — saare repos return karo
        from app.services.repo_service import list_all_repos
        return {"status": "success", "data": list_all_repos()}

    # Auth mode — sirf us user ke repos
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token required")

    from app.core.auth import verify_token
    payload = verify_token(auth_header[7:])
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    repos = get_user_repos(payload.user_id)
    return {"status": "success", "data": repos, "user_id": payload.user_id}


@ci_router.delete("/my-repos/{repo_id}")
async def delete_my_repo(repo_id: str, request: Request):
    """User ki repo list se ek repo hata do."""
    from app.core.auth import verify_token, delete_user_repo
    import os

    auth_enabled = os.getenv("MARKAR_AUTH_ENABLED", "false").lower() == "true"
    if not auth_enabled:
        return {"status": "success", "message": "Dev mode — skipped"}

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token required")

    payload = verify_token(auth_header[7:])
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    delete_user_repo(payload.user_id, repo_id)
    return {"status": "success", "message": f"Repo {repo_id} removed"}

@ci_router.post("/reconnect/{repo_id}")
async def reconnect_repo(repo_id: str):
    """
    Server restart ke baad Neo4j se graph reconnect karo.
    Re-parse nahi hoga — sirf existing graph connect hoga.
    """
    from app.services.repo_service import reconnect_repo
    result = reconnect_repo(repo_id)
    return {"status": "success", "data": result}