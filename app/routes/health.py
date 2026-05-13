"""
Markar Intelligence — All API Routes
Fixed: no duplicate router, git clone support, rich analysis.
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from typing import List, Optional
import os, shutil, tempfile, hashlib

from app.code_intelligence import CodeIntelligenceOrchestrator, QueryType, WorkflowExecutor
from app.dependencies.code_intelligence import get_orchestrator, set_orchestrator
from fastapi.responses import StreamingResponse

from app.services.repo_service import (
    start_initialization,
    get_status as repo_get_status,    # ← alias do conflict avoid karne ke liye
    get_orchestrator_by_id,
    list_all_repos,
    stream_status
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
async def initialize(request: InitRequest):
    """Initialize from local path OR GitHub URL — non-blocking."""
    result = start_initialization(
        git_url=request.git_url,
        repo_path=request.repo_path
    )
    return result


# ── Status — now returns RICH analysis ────────────────────────
@ci_router.get("/status/{repo_id}")
async def repo_status(                    # ← naam badla — conflict nahi hoga
    repo_id: str,
):
    from app.services.repo_service import get_status as _get_status
    result = _get_status(repo_id)         # ← repo_service wala call hoga
    if not result:
        raise HTTPException(status_code=404, detail=f"Repo {repo_id} not found")
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

@ci_router.get("/visualization")
async def get_visualization(
    orchestrator: CodeIntelligenceOrchestrator = Depends(get_orchestrator)):
    return {"status": "success", "data": orchestrator.export_visualization()}

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