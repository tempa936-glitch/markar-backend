"""
Markar Intelligence — All API Routes
Fixed: no duplicate router, git clone support, rich analysis.
DEBUG ENDPOINT — Sirf testing ke liye
Neo4j mein jo bhi store hai — sab Postman mein dikha do.
Delete Endpoints — Neo4j + SQLite dono ek saath clean karo
===========================================================
health.py ke end mein add karo yeh poora block.
 
3 endpoints hain:
  1. DELETE /api/code-intelligence/repo/{repo_id}  — ek repo delete
  2. DELETE /api/code-intelligence/repos/all        — saari repos delete
  3. GET    /api/code-intelligence/storage/stats    — kitna space use ho raha hai
"""

from fastapi import APIRouter, HTTPException, Query, Depends, Header, Request
from pydantic import BaseModel
from typing import List, Optional
import os, shutil, tempfile, hashlib

from app.code_intelligence import CodeIntelligenceOrchestrator, QueryType, WorkflowExecutor
from app.dependencies.code_intelligence import get_orchestrator, set_orchestrator
from fastapi.responses import StreamingResponse
from app.services.repo_service import get_orchestrator_by_id

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

@ci_router.get("/debug/{repo_id}/neo4j")
async def debug_neo4j_full(repo_id: str):
    """
    Testing endpoint — Neo4j mein sab kuch dikhao.
    
    GET /api/code-intelligence/debug/{repo_id}/neo4j
    GET /api/code-intelligence/debug/{repo_id}/neo4j?section=deep_ast
    GET /api/code-intelligence/debug/{repo_id}/neo4j?section=git
    GET /api/code-intelligence/debug/{repo_id}/neo4j?section=graph
    GET /api/code-intelligence/debug/{repo_id}/neo4j?section=branches
    GET /api/code-intelligence/debug/{repo_id}/neo4j?section=exceptions
    GET /api/code-intelligence/debug/{repo_id}/neo4j?section=functions
    GET /api/code-intelligence/debug/{repo_id}/neo4j?section=combined
    """
    from app.services.repo_service import get_orchestrator_by_id
    from fastapi import Query as FQuery
 
    orch = get_orchestrator_by_id(repo_id)
    if not orch:
        raise HTTPException(
            status_code=404,
            detail=f"Repo '{repo_id}' ready nahi hai. Pehle initialize karo."
        )
 
    store = orch.store
 
    from app.code_intelligence.graph.neo4j_store import Neo4jStore
    if not isinstance(store, Neo4jStore):
        raise HTTPException(
            status_code=400,
            detail="Yeh endpoint sirf Neo4j repos ke liye hai."
        )
 
    try:
        driver = store._connect()
 
        with driver.session() as s:
 
            # ── 1. Basic stats ────────────────────────────────────────────
            stats_row = s.run("""
                MATCH (n:CodeNode {repo_id:$r})
                RETURN
                    count(n) AS total_nodes,
                    sum(CASE WHEN n.node_type = 'file'     THEN 1 ELSE 0 END) AS files,
                    sum(CASE WHEN n.node_type = 'function' THEN 1 ELSE 0 END) AS functions,
                    sum(CASE WHEN n.node_type = 'class'    THEN 1 ELSE 0 END) AS classes
            """, r=repo_id).single()
            stats = dict(stats_row) if stats_row else {}
 
            # ── 2. Deep AST summary ───────────────────────────────────────
            deep_row = s.run("""
                MATCH (n:CodeNode {repo_id:$r, node_type:'function'})
                WHERE n.deep_complexity IS NOT NULL
                RETURN
                    count(n)                                                            AS analyzed,
                    avg(n.deep_complexity)                                              AS avg_complexity,
                    max(n.deep_complexity)                                              AS max_complexity,
                    sum(CASE WHEN n.deep_risk_level = 'CRITICAL' THEN 1 ELSE 0 END)   AS critical,
                    sum(CASE WHEN n.deep_risk_level = 'HIGH'     THEN 1 ELSE 0 END)   AS high,
                    sum(CASE WHEN n.deep_risk_level = 'MEDIUM'   THEN 1 ELSE 0 END)   AS medium,
                    sum(CASE WHEN n.deep_risk_level = 'LOW'      THEN 1 ELSE 0 END)   AS low,
                    sum(CASE WHEN n.deep_is_async = true THEN 1 ELSE 0 END)            AS async_count,
                    sum(CASE WHEN n.deep_has_try_except = true THEN 1 ELSE 0 END)      AS try_except_count
            """, r=repo_id).single()
            deep_summary = dict(deep_row) if deep_row else {}
            if "avg_complexity" in deep_summary and deep_summary["avg_complexity"]:
                deep_summary["avg_complexity"] = round(deep_summary["avg_complexity"], 2)
 
            # ── 3. Top 10 CRITICAL/HIGH functions ────────────────────────
            hotspot_rows = s.run("""
                MATCH (n:CodeNode {repo_id:$r, node_type:'function'})
                WHERE n.deep_risk_level IN ['CRITICAL','HIGH']
                RETURN n.name              AS name,
                       n.file_path         AS file,
                       n.line_no           AS line,
                       n.deep_risk_level   AS risk,
                       n.deep_complexity   AS complexity,
                       n.deep_max_depth    AS nesting,
                       n.deep_branch_count AS branches,
                       n.deep_raises       AS raises,
                       n.deep_risk_reasons AS reasons,
                       n.deep_logic_lines  AS logic_lines,
                       n.deep_is_async     AS is_async
                ORDER BY
                    CASE n.deep_risk_level WHEN 'CRITICAL' THEN 0 ELSE 1 END,
                    n.deep_complexity DESC
                LIMIT 10
            """, r=repo_id)
            hotspots = [dict(r) for r in hotspot_rows]
 
            # ── 4. BranchNodes stats ──────────────────────────────────────
            branch_stats_row = s.run("""
                MATCH (b:BranchNode {repo_id:$r})
                RETURN
                    count(b) AS total_branches,
                    sum(CASE WHEN b.leads_raise = true  THEN 1 ELSE 0 END) AS leads_to_raise,
                    sum(CASE WHEN b.leads_return = true THEN 1 ELSE 0 END) AS leads_to_return,
                    collect(DISTINCT b.branch_type)[..10] AS branch_types
            """, r=repo_id).single()
            branch_stats = dict(branch_stats_row) if branch_stats_row else {}
 
            # ── 5. Sample branches ────────────────────────────────────────
            branch_rows = s.run("""
                MATCH (fn:CodeNode {repo_id:$r, node_type:'function'})
                      -[:HAS_BRANCH]->(b:BranchNode {repo_id:$r})
                WHERE fn.deep_risk_level IN ['CRITICAL','HIGH']
                RETURN fn.name        AS function,
                       fn.file_path   AS file,
                       b.branch_type  AS branch_type,
                       b.condition    AS condition,
                       b.line_no      AS line,
                       b.leads_raise  AS leads_raise,
                       b.raises_type  AS raises_type,
                       b.leads_return AS leads_return
                ORDER BY b.line_no
                LIMIT 20
            """, r=repo_id)
            sample_branches = [dict(r) for r in branch_rows]
 
            # ── 6. Exception nodes ────────────────────────────────────────
            exc_rows = s.run("""
                MATCH (fn:CodeNode {repo_id:$r})-[rel:RAISES]->(ex:ExceptionNode {repo_id:$r})
                RETURN ex.exc_type   AS exception_type,
                       count(fn)     AS raised_by_count,
                       collect(fn.name)[..5] AS raised_by_functions,
                       sum(CASE WHEN rel.is_caught = false THEN 1 ELSE 0 END) AS uncaught_count
                ORDER BY raised_by_count DESC
                LIMIT 15
            """, r=repo_id)
            exceptions = [dict(r) for r in exc_rows]
 
            # ── 7. CAN_PROPAGATE relationships ────────────────────────────
            prop_rows = s.run("""
                MATCH (fn:CodeNode {repo_id:$r})-[rel:CAN_PROPAGATE]->(ex:ExceptionNode {repo_id:$r})
                RETURN fn.name     AS function,
                       ex.exc_type AS exception_type,
                       rel.callee  AS via_callee,
                       rel.line_no AS line
                LIMIT 15
            """, r=repo_id)
            propagations = [dict(r) for r in prop_rows]
 
            # ── 8. All relationships count ────────────────────────────────
            rel_rows = s.run("""
                MATCH ()-[r]->()
                WHERE type(r) IN ['DEPENDS_ON','HAS_BRANCH','RAISES','CAN_PROPAGATE']
                RETURN type(r) AS rel_type, count(r) AS count
                ORDER BY count DESC
            """)
            relationships = [dict(r) for r in rel_rows]
 
            # ── 9. Sample functions with ALL deep properties ──────────────
            sample_func_rows = s.run("""
                MATCH (n:CodeNode {repo_id:$r, node_type:'function'})
                WHERE n.deep_complexity IS NOT NULL
                RETURN n.name                AS name,
                       n.file_path           AS file,
                       n.line_no             AS line,
                       n.deep_risk_level     AS deep_risk,
                       n.deep_complexity     AS complexity,
                       n.deep_max_depth      AS nesting,
                       n.deep_branch_count   AS branches,
                       n.deep_loop_count     AS loops,
                       n.deep_exception_count AS exceptions,
                       n.deep_raises         AS raises,
                       n.deep_can_propagate  AS can_propagate,
                       n.deep_risk_reasons   AS risk_reasons,
                       n.deep_branch_paths   AS branch_paths,
                       n.deep_is_async       AS is_async,
                       n.deep_has_await      AS has_await,
                       n.deep_has_try_except AS has_try_except,
                       n.deep_always_returns AS always_returns,
                       n.deep_can_return_none AS can_return_none,
                       n.deep_return_type    AS return_type,
                       n.deep_logic_lines    AS logic_lines,
                       n.deep_total_lines    AS total_lines,
                       n.deep_data_inputs    AS inputs,
                       n.deep_data_returns   AS returns,
                       n.deep_language       AS language
                ORDER BY n.deep_complexity DESC
                LIMIT 10
            """, r=repo_id)
            sample_functions = [dict(r) for r in sample_func_rows]
 
            # ── 10. Git history (agar available hai) ──────────────────────
            git_row = s.run("""
                MATCH (n:CodeNode {repo_id:$r})
                WHERE n.git_churn_score IS NOT NULL
                RETURN
                    count(n) AS git_tracked,
                    sum(CASE WHEN n.git_churn_score = 'CRITICAL' THEN 1 ELSE 0 END) AS critical_churn,
                    sum(CASE WHEN n.git_churn_score = 'HIGH'     THEN 1 ELSE 0 END) AS high_churn,
                    sum(CASE WHEN n.git_churn_score = 'MEDIUM'   THEN 1 ELSE 0 END) AS medium_churn,
                    sum(CASE WHEN n.git_churn_score = 'LOW'      THEN 1 ELSE 0 END) AS low_churn
            """, r=repo_id).single()
            git_summary = dict(git_row) if git_row else {"git_tracked": 0}
 
            # ── 11. Combined risk (agar available hai) ────────────────────
            combined_row = s.run("""
                MATCH (n:CodeNode {repo_id:$r, node_type:'function'})
                WHERE n.combined_risk IS NOT NULL
                RETURN
                    count(n) AS total,
                    sum(CASE WHEN n.combined_risk = 'CRITICAL' THEN 1 ELSE 0 END) AS critical,
                    sum(CASE WHEN n.combined_risk = 'HIGH'     THEN 1 ELSE 0 END) AS high,
                    sum(CASE WHEN n.combined_risk = 'MEDIUM'   THEN 1 ELSE 0 END) AS medium,
                    sum(CASE WHEN n.combined_risk = 'LOW'      THEN 1 ELSE 0 END) AS low
            """, r=repo_id).single()
            combined_summary = dict(combined_row) if combined_row else {"total": 0}
 
        return {
            "repo_id": repo_id,
            "status":  "debug_data",
 
            # ── Basic ──────────────────────────────────────────────────────
            "graph_stats": stats,
            "relationships": relationships,
 
            # ── Deep AST ───────────────────────────────────────────────────
            "deep_ast": {
                "summary":          deep_summary,
                "hotspots_top10":   hotspots,
                "branch_stats":     branch_stats,
                "sample_branches":  sample_branches,
                "exceptions":       exceptions,
                "propagations":     propagations,
            },
 
            # ── Sample functions with all properties ────────────────────────
            "sample_functions_top10_by_complexity": sample_functions,
 
            # ── Git (agar run hua ho) ───────────────────────────────────────
            "git_history": git_summary,
 
            # ── Combined risk (Deep AST + Git) ──────────────────────────────
            "combined_risk": combined_summary,
        }
 
    except Exception as e:
        import traceback
        raise HTTPException(
            status_code=500,
            detail={"error": str(e), "traceback": traceback.format_exc()[-500:]}
        )
    

# ── 1. Ek specific repo delete karo ────────────────────────────────────────
@ci_router.delete("/repo/{repo_id}")
async def delete_repo(repo_id: str):
    """
    Ek repo ko Neo4j + SQLite + memory — teeno se delete karo.
 
    DELETE /api/code-intelligence/repo/{repo_id}
 
    Safe hai — sirf us repo ka data delete hoga.
    """
    from app.services.repo_service import _jobs, JOBS_DB
    import sqlite3
 
    result = {
        "repo_id":        repo_id,
        "neo4j_deleted":  0,
        "sqlite_deleted": False,
        "memory_deleted": False,
        "errors":         [],
    }
 
    # ── Step 1: Neo4j se delete ───────────────────────────────────────────
    try:
        from app.code_intelligence.graph.neo4j_store import Neo4jStore
        store = Neo4jStore(repo_id=repo_id)
        driver = store._connect()
 
        with driver.session() as s:
            # Saare nodes count karo pehle
            count = s.run(
                "MATCH (n {repo_id:$r}) RETURN count(n) AS cnt",
                r=repo_id
            ).single()["cnt"]
 
            # Delete karo — relationships automatically delete honge (DETACH)
            s.run("MATCH (n:CodeNode     {repo_id:$r}) DETACH DELETE n", r=repo_id)
            s.run("MATCH (n:BranchNode   {repo_id:$r}) DETACH DELETE n", r=repo_id)
            s.run("MATCH (n:ExceptionNode{repo_id:$r}) DETACH DELETE n", r=repo_id)
 
            result["neo4j_deleted"] = count
 
    except Exception as e:
        result["errors"].append(f"Neo4j: {str(e)}")
 
    # ── Step 2: SQLite se delete ──────────────────────────────────────────
    try:
        with sqlite3.connect(JOBS_DB) as conn:
            rows = conn.execute(
                "DELETE FROM persisted_repos WHERE repo_id = ?", (repo_id,)
            ).rowcount
        result["sqlite_deleted"] = rows > 0
    except Exception as e:
        result["errors"].append(f"SQLite: {str(e)}")
 
    # ── Step 3: Memory (_jobs) se delete ─────────────────────────────────
    if repo_id in _jobs:
        del _jobs[repo_id]
        result["memory_deleted"] = True
 
    result["status"] = "deleted" if not result["errors"] else "partial"
    return result
 
 
# ── 2. Saari repos delete karo ─────────────────────────────────────────────
@ci_router.delete("/repos/all")
async def delete_all_repos(confirm: str = "no"):
    """
    Saari repos Neo4j + SQLite + memory se delete karo.
 
    DELETE /api/code-intelligence/repos/all?confirm=yes
 
    IMPORTANT: confirm=yes pass karna zaroori hai — warna kaam nahi karega.
    """
    if confirm.lower() != "yes":
        return {
            "status":  "not_confirmed",
            "message": "confirm=yes query param pass karo",
            "example": "DELETE /api/code-intelligence/repos/all?confirm=yes",
        }
 
    from app.services.repo_service import _jobs, JOBS_DB
    import sqlite3
 
    result = {
        "neo4j_deleted":   0,
        "sqlite_deleted":  0,
        "memory_cleared":  0,
        "errors":          [],
    }
 
    # ── Neo4j — poora wipe ────────────────────────────────────────────────
    try:
        from app.code_intelligence.graph.neo4j_store import Neo4jStore
        # Kisi bhi connected repo ka store use karo
        if _jobs:
            first_id = next(iter(_jobs))
            store  = Neo4jStore(repo_id=first_id)
            driver = store._connect()
        else:
            # Direct connection try karo
            import os
            from neo4j import GraphDatabase
            driver = GraphDatabase.driver(
                os.getenv("NEO4J_URI"),
                auth=(os.getenv("NEO4J_USERNAME","neo4j"),
                      os.getenv("NEO4J_PASSWORD",""))
            )
 
        with driver.session() as s:
            count = s.run("MATCH (n) RETURN count(n) AS cnt").single()["cnt"]
            # Batch mein delete karo — large DB ke liye safe
            s.run("MATCH (n:CodeNode)      DETACH DELETE n")
            s.run("MATCH (n:BranchNode)    DETACH DELETE n")
            s.run("MATCH (n:ExceptionNode) DETACH DELETE n")
            result["neo4j_deleted"] = count
 
    except Exception as e:
        result["errors"].append(f"Neo4j: {str(e)}")
 
    # ── SQLite — saari rows delete ────────────────────────────────────────
    try:
        with sqlite3.connect(JOBS_DB) as conn:
            rows = conn.execute("DELETE FROM persisted_repos").rowcount
        result["sqlite_deleted"] = rows
    except Exception as e:
        result["errors"].append(f"SQLite: {str(e)}")
 
    # ── Memory clear ──────────────────────────────────────────────────────
    count = len(_jobs)
    _jobs.clear()
    result["memory_cleared"] = count
 
    result["status"] = "all_deleted" if not result["errors"] else "partial"
    return result
 
 
# ── 3. Storage stats ────────────────────────────────────────────────────────
@ci_router.get("/storage/stats")
async def storage_stats():
    """
    Kitna data store hai — Neo4j + SQLite dono ka breakdown.
 
    GET /api/code-intelligence/storage/stats
    """
    from app.services.repo_service import _jobs, JOBS_DB
    import sqlite3, os
 
    result = {
        "neo4j":  {},
        "sqlite": {},
        "memory": {},
        "repos":  [],
    }
 
    # ── Neo4j stats ───────────────────────────────────────────────────────
    try:
        if _jobs:
            first_id = next(iter(_jobs))
            job = _jobs[first_id]
            if job.get("orchestrator"):
                store  = job["orchestrator"].store
                from app.code_intelligence.graph.neo4j_store import Neo4jStore
                if isinstance(store, Neo4jStore):
                    driver = store._connect()
                    with driver.session() as s:
                        # Per-repo breakdown
                        repo_rows = s.run("""
                            MATCH (n:CodeNode)
                            RETURN n.repo_id                      AS repo_id,
                                   count(n)                       AS nodes,
                                   sum(CASE WHEN n.node_type='function' THEN 1 ELSE 0 END) AS functions,
                                   sum(CASE WHEN n.node_type='file'     THEN 1 ELSE 0 END) AS files
                            ORDER BY nodes DESC
                        """)
                        repos_data = [dict(r) for r in repo_rows]
 
                        # Total nodes
                        total = s.run("MATCH (n) RETURN count(n) AS cnt").single()["cnt"]
                        branches = s.run("MATCH (n:BranchNode) RETURN count(n) AS cnt").single()["cnt"]
                        exceptions = s.run("MATCH (n:ExceptionNode) RETURN count(n) AS cnt").single()["cnt"]
 
                    result["neo4j"] = {
                        "total_nodes":      total,
                        "code_nodes":       sum(r["nodes"] for r in repos_data),
                        "branch_nodes":     branches,
                        "exception_nodes":  exceptions,
                        "repos_breakdown":  repos_data,
                    }
    except Exception as e:
        result["neo4j"]["error"] = str(e)
 
    # ── SQLite stats ──────────────────────────────────────────────────────
    try:
        db_size = os.path.getsize(JOBS_DB) if os.path.exists(JOBS_DB) else 0
        with sqlite3.connect(JOBS_DB) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT repo_id, git_url, status, created_at FROM persisted_repos"
            ).fetchall()
        result["sqlite"] = {
            "db_size_kb": round(db_size / 1024, 2),
            "total_repos": len(rows),
            "repos": [dict(r) for r in rows],
        }
    except Exception as e:
        result["sqlite"]["error"] = str(e)
 
    # ── Memory stats ──────────────────────────────────────────────────────
    result["memory"] = {
        "repos_loaded": len(_jobs),
        "repo_ids":     list(_jobs.keys()),
        "statuses":     {rid: j.get("status") for rid, j in _jobs.items()},
    }
 
    return result    