import os
import uuid
import shutil
import subprocess
import threading
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Optional
import asyncio
from typing import AsyncGenerator
import sqlite3

_jobs = {}  # { repo_id: { ...job data... } }

JOBS_DB = os.getenv("MARKAR_DB_PATH", "markar.db")

LANG_MAP = {
    ".py": "Python", ".js": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript",
    ".jsx": "JavaScript", ".java": "Java",
    ".go": "Go", ".rs": "Rust", ".c": "C",
    ".cpp": "C++", ".cs": "C#", ".rb": "Ruby",
    ".php": "PHP", ".swift": "Swift", ".kt": "Kotlin",
}

IGNORE_DIRS = {
    ".git", "node_modules", "__pycache__",
    ".venv", "venv", "dist", "build",
    ".next", "target", "vendor"
}

def _init_jobs_db():
    with sqlite3.connect(JOBS_DB) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS persisted_repos (
                repo_id     TEXT PRIMARY KEY,
                git_url     TEXT,
                git_branch  TEXT DEFAULT 'main',
                status      TEXT DEFAULT 'READY',
                created_at  TEXT,
                overview    TEXT
            )
        """)

def _save_repo_to_db(job: dict):
    import json
    with sqlite3.connect(JOBS_DB) as conn:
        conn.execute("""
            INSERT OR REPLACE INTO persisted_repos
                (repo_id, git_url, git_branch, status, created_at, overview)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            job["repo_id"],
            job.get("git_url"),
            job.get("git_branch", "main"),
            job.get("status", "READY"),
            job.get("created_at"),
            json.dumps(job.get("overview") or {}),
        ))


def load_persisted_repos():
    import json
    try:
        _init_jobs_db()
        loaded = 0

        with sqlite3.connect(JOBS_DB) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM persisted_repos").fetchall()

        for row in rows:
            repo_id = row["repo_id"]
            if repo_id not in _jobs:
                overview = {}
                try:
                    overview = json.loads(row["overview"] or "{}")
                except Exception:
                    pass
                _jobs[repo_id] = {
                    "repo_id":    repo_id,
                    "git_url":    row["git_url"],
                    "git_branch": row["git_branch"],
                    "repo_path":  None,
                    "clone_path": None,
                    "status":     "NEEDS_RECONNECT",
                    "overview":   overview,
                    "graph_ready": False,
                    "orchestrator": None,
                    "error":      None,
                    "created_at": row["created_at"],
                }
                loaded += 1

        try:
            from app.core.auth import load_all_user_repos
            user_repos = load_all_user_repos()
            for repo in user_repos:
                repo_id = repo["repo_id"]
                if repo_id not in _jobs:
                    _jobs[repo_id] = {
                        "repo_id":    repo_id,
                        "git_url":    repo.get("git_url"),
                        "git_branch": repo.get("git_branch", "main"),
                        "repo_path":  None,
                        "clone_path": None,
                        "status":     "NEEDS_RECONNECT",
                        "overview":   repo.get("overview", {}),
                        "graph_ready": False,
                        "orchestrator": None,
                        "error":      None,
                        "created_at": repo.get("created_at"),
                    }
                    loaded += 1
        except Exception as e:
            print(f"[RepoService] user_repos load failed: {e}")

        print(f"[RepoService] Loaded {loaded} repos from DB")
    except Exception as e:
        print(f"[RepoService] DB load failed: {e}")


def start_initialization(git_url=None, repo_path=None, git_branch="main", user_id: str = None) -> dict:
    clone_path = None
    if git_url:
        import hashlib
        repo_id = hashlib.sha256(git_url.encode()).hexdigest()[:12]
        _base = os.getenv("MARKAR_REPO_PATH", tempfile.gettempdir())
        os.makedirs(_base, exist_ok=True)
        clone_path = os.path.join(_base, f"markar_{repo_id}")
    else:
        repo_id = str(uuid.uuid4())[:8]

    _jobs[repo_id] = {
        "repo_id": repo_id,
        "user_id":  user_id,
        "git_url": git_url,
        "git_branch": git_branch,
        "repo_path": repo_path or clone_path,
        "clone_path": clone_path,
        "status": "CLONING" if git_url else "PARSING",
        "overview": None,
        "graph_ready": False,
        "orchestrator": None,
        "error": None,
        "created_at": datetime.now().isoformat()
    }

    thread = threading.Thread(target=_worker, args=(repo_id,), daemon=True)
    thread.start()

    return {
        "repo_id": repo_id,
        "status": _jobs[repo_id]["status"],
        "message": f"Poll /api/code-intelligence/status/{repo_id}",
        "overview": None,
        "graph_ready": False,
        "error": None
    }

def reconnect_repo(repo_id: str) -> dict:
    job = _jobs.get(repo_id)
    if not job:
        return {"error": f"Repo {repo_id} not found"}
    if job.get("graph_ready"):
        return {"status": "already_ready", "repo_id": repo_id}
    try:
        from app.code_intelligence import CodeIntelligenceOrchestrator
        from app.code_intelligence.graph.neo4j_store import Neo4jStore

        store = Neo4jStore(repo_id=repo_id)
        stats = store.get_stats()

        if stats.get("total_nodes", 0) == 0:
            return {
                "status":  "not_found_in_neo4j",
                "repo_id": repo_id,
                "message": "Graph Neo4j mein nahi hai — dobara initialize karo",
            }

        orch = CodeIntelligenceOrchestrator.__new__(CodeIntelligenceOrchestrator)
        orch.repo_path = job.get("repo_path") or ""
        orch.store     = store

        job["orchestrator"] = orch
        job["graph_ready"]  = True
        job["status"]       = "READY"
        job["graph_stats"]  = stats

        print(f"[Reconnect] ✅ {repo_id} — {stats.get('total_nodes')} nodes")
        return {
            "status":      "reconnected",
            "repo_id":     repo_id,
            "total_nodes": stats.get("total_nodes", 0),
        }

    except Exception as e:
        print(f"[Reconnect] ❌ {repo_id}: {e}")
        job["status"] = "ERROR"
        job["error"]  = str(e)
        return {"error": str(e)}

def _force_rmtree(path: str):
    import stat
    def _on_error(func, fpath, exc_info):
        try:
            os.chmod(fpath, stat.S_IWRITE)
            func(fpath)
        except Exception:
            pass
    shutil.rmtree(path, onerror=_on_error)


def _github_precheck(git_url: str, user_id: str) -> dict:
    import re, urllib.request, json as _json

    if not git_url or "github.com" not in git_url:
        return {"blocked": False}

    match = re.search(r"github\.com[/:]([^/]+)/([^/\.]+)", git_url)
    if not match:
        return {"blocked": False}

    owner, repo = match.group(1), match.group(2)

    try:
        api_url = f"https://api.github.com/repos/{owner}/{repo}"
        req = urllib.request.Request(
            api_url,
            headers={"User-Agent": "Markar-App", "Accept": "application/vnd.github.v3+json"}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = _json.loads(resp.read())

        size_kb = data.get("size", 0)
        default_branch = data.get("default_branch", "main")

        exact_files = None
        try:
            tree_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1"
            req_tree = urllib.request.Request(
                tree_url,
                headers={"User-Agent": "Markar-App", "Accept": "application/vnd.github.v3+json"}
            )
            with urllib.request.urlopen(req_tree, timeout=8) as resp_tree:
                tree_data = _json.loads(resp_tree.read())
                exact_files = sum(1 for item in tree_data.get("tree", []) if item.get("type") == "blob")
        except Exception as e:
            print(f"[PRECHECK] Tree API failed ({e}), using estimate fallback")

        estimated_files = exact_files if exact_files is not None else (size_kb // 2)
        print(f"[PRECHECK] {owner}/{repo} → size={size_kb}KB, files={estimated_files}")

        if size_kb > 300_000 or estimated_files >= 1500:
            return {
                "blocked": True,
                "reason": "HUGE_REPO_BLOCKED",
                "message": (
                    f"Repo '{owner}/{repo}' bohot badi hai "
                    f"(~{size_kb//1024}MB, ~{estimated_files:,} files). "
                    f"1500+ files wali repos free plan mein index nahi ho sakti."
                ),
                "estimated_files": estimated_files,
                "size_kb": size_kb,
            }

        if user_id:
            from app.core.user_admin import check_repo_credit
            credit_result = check_repo_credit(user_id, estimated_files)
            if not credit_result["allowed"]:
                return {
                    "blocked":     True,
                    "reason":      credit_result.get("reason"),
                    "message":     credit_result.get("message"),
                    "estimated_files": estimated_files,
                    "size_kb":     size_kb,
                    "required":    credit_result.get("required"),
                    "available":   credit_result.get("available"),
                }

        return {"blocked": False, "estimated_files": estimated_files, "size_kb": size_kb}

    except Exception as e:
        print(f"[PRECHECK] GitHub API failed ({e}) — proceeding without pre-check")
        return {"blocked": False}


def _worker(repo_id: str):
    job = _jobs[repo_id]

    try:
        if job["git_url"]:
            job["status"] = "PRECHECKING"
            precheck = _github_precheck(job["git_url"], job.get("user_id"))
            if precheck["blocked"]:
                job["status"]         = "BLOCKED"
                job["error"]          = precheck["message"]
                job["blocked_reason"] = precheck["reason"]
                job["overview"]       = {
                    "estimated_files": precheck.get("estimated_files"),
                    "size_kb":         precheck.get("size_kb"),
                }
                print(f"[PRECHECK] ❌ BLOCKED before clone — {precheck['reason']}")
                return
            print(f"[PRECHECK] ✅ Passed — proceeding to clone")

        if job["git_url"]:
            job["status"] = "CLONING"
            if job["clone_path"] and os.path.exists(job["clone_path"]):
                _force_rmtree(job["clone_path"])
            clone_args = ["git", "clone", "--depth", "1"]
            if job.get("git_branch"):
                clone_args += ["--branch", job["git_branch"]]
            clone_args += [job["git_url"], job["clone_path"]]
            result = subprocess.run(clone_args, capture_output=True, text=True, timeout=800)
            if result.returncode != 0:
                raise Exception(f"Clone failed: {result.stderr.strip()}")
            job["repo_path"] = job["clone_path"]

        overview = _quick_overview(job["repo_path"])
        job["overview"] = overview
        job["status"] = "OVERVIEW_READY"

        if job.get("user_id"):
            from app.core.user_admin import check_repo_credit
            total_files = overview.get("total_files", 0)
            credit_result = check_repo_credit(job["user_id"], total_files)
            if not credit_result["allowed"]:
                job["status"] = "ERROR"
                job["error"] = credit_result["message"]
                job["blocked_reason"] = credit_result.get("reason", "INSUFFICIENT_CREDITS")
                print(f"[CREDIT CHECK] ❌ BLOCKED after clone — {credit_result['reason']}")
                if job.get("clone_path") and os.path.exists(job["clone_path"]):
                    _force_rmtree(job["clone_path"])
                return

        job["status"] = "CHECKING_LANGUAGES"

        try:
            from app.code_intelligence.parser.universal_parser import UniversalParser
            _uni = UniversalParser()
            _avail = _uni.languages_available()
            job["languages_installed"] = sorted([l for l, ok in _avail.items() if ok])
            job["languages_missing"]   = sorted([l for l, ok in _avail.items() if not ok])
            job["supported_extensions"] = _uni.get_supported_extensions()
        except Exception as _le:
            job["languages_installed"] = []
            job["languages_missing"]   = []
            job["supported_extensions"] = {}
            job["language_check_error"] = str(_le)

        job["status"] = "PARSING"
        print(f"[STAGE4] Starting for {job['repo_path']}")
        try:
            from app.code_intelligence import CodeIntelligenceOrchestrator
            instance = CodeIntelligenceOrchestrator(job["repo_path"], repo_id=job["repo_id"])
            print(f"[STAGE4] Orchestrator created")
            init_result = instance.initialize()
            print(f"[STAGE4] Initialize done: {type(init_result)}")
            job["orchestrator"] = instance
            job["parser"] = instance.store
            job["graph_stats"] = init_result
            job["graph_ready"] = True
            job["status"] = "READY"
            print(f"[STAGE4] ✅ READY!")
            _save_repo_to_db(job)

            if job.get("user_id"):
                from app.core.auth import save_user_repo
                save_user_repo(
                    user_id=job["user_id"],
                    repo_id=repo_id,
                    git_url=job.get("git_url"),
                    git_branch=job.get("git_branch", "main"),
                    status="READY",
                    overview=job.get("overview"),
                )
                print(f"[STAGE4] Repo saved for user: {job['user_id']}")

                from app.core.user_admin import deduct_repo_credit
                total_files = job.get("overview", {}).get("total_files", 0)
                deduct_result = deduct_repo_credit(job["user_id"], total_files, repo_id)
                job["credits_deducted"] = deduct_result.get("deducted", 0)
                print(f"[CREDIT] ✅ Deducted {deduct_result.get('deducted')} credits")

        except Exception as stage4_error:
            import traceback
            print(f"[STAGE4] ❌ ERROR: {stage4_error}")
            print(traceback.format_exc())
            job["status"] = "ERROR"
            job["error"] = str(stage4_error)

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        job["status"] = "ERROR"
        job["error"] = str(e)
        job["traceback"] = tb
        print(f"\n[WORKER ERROR] repo_id={repo_id}")
        print(f"[WORKER ERROR] {tb}")
        if job.get("clone_path") and os.path.exists(job["clone_path"]):
            _force_rmtree(job["clone_path"])

def _quick_overview(repo_path: str) -> dict:
    path = Path(repo_path)
    total_files = 0
    total_lines = 0
    total_bytes = 0
    languages = {}

    for fp in path.rglob("*"):
        if not fp.is_file():
            continue
        if any(p in IGNORE_DIRS for p in fp.parts):
            continue
        total_files += 1
        total_bytes += fp.stat().st_size
        ext = fp.suffix.lower()
        if ext in LANG_MAP:
            lang = LANG_MAP[ext]
            languages[lang] = languages.get(lang, 0) + 1
            try:
                lines = fp.read_text(errors="ignore").count("\n")
                total_lines += lines
            except:
                pass

    top_level = []
    try:
        for item in sorted(path.iterdir()):
            if item.name in IGNORE_DIRS or item.name.startswith("."):
                continue
            top_level.append({"name": item.name, "type": "directory" if item.is_dir() else "file"})
    except:
        pass

    primary = max(languages, key=languages.get) if languages else "Unknown"

    return {
        "total_files": total_files,
        "total_lines": total_lines,
        "size_mb": round(total_bytes / (1024 * 1024), 2),
        "primary_language": primary,
        "languages": dict(sorted(languages.items(), key=lambda x: -x[1])),
        "language_count": len(languages),
        "top_level_structure": top_level[:20],
        "has_docker": (path / "Dockerfile").exists() or (path / "docker-compose.yml").exists(),
        "has_tests": any(
            "test" in fp.name.lower() or "spec" in fp.name.lower()
            for fp in path.rglob("*") if fp.is_file()
        ),
        "has_ci": (path / ".github" / "workflows").exists(),
        "has_readme": bool(list(path.glob("README*")))
    }

def get_status(repo_id: str) -> Optional[dict]:
    job = _jobs.get(repo_id)
    if not job:
        return None

    base = {
        "repo_id":    job["repo_id"],
        "status":     job["status"],
        "overview":   job["overview"],
        "graph_ready": job["graph_ready"],
        "error":      job.get("error"),
        "traceback":  job.get("traceback"),
        "created_at": job["created_at"],
        "graph_stats": None,
        "repo_overview": None,
        "languages": {
            "installed": job.get("languages_installed"),
            "missing":   job.get("languages_missing"),
            "supported_extensions": job.get("supported_extensions"),
            "tip": "pip install tree-sitter-<lang> to add missing grammars"
                   if job.get("languages_missing") else None,
        } if job.get("languages_installed") is not None else None,
    }

    if job["graph_ready"] and job.get("orchestrator"):
        store = job["orchestrator"].store
        base["graph_stats"] = store.get_stats()

        from app.code_intelligence.graph.neo4j_store import Neo4jStore
        if isinstance(store, Neo4jStore):
            base["repo_overview"] = _build_summary_neo4j(store)
        else:
            base["repo_overview"] = _build_summary_in_memory(store)

    return base


def _build_summary_neo4j(store) -> dict:
    """Neo4j se summary + DEEP AST data."""
    try:
        driver = store._connect()
        with driver.session() as s:
            stats = store.get_stats()

            # Top 10 most called
            top = s.run("""
                MATCH (f:CodeNode {repo_id:$r, node_type:'function'})
                OPTIONAL MATCH ()-[:DEPENDS_ON]->(f)
                WITH f, count(*) AS dep
                ORDER BY dep DESC LIMIT 10
                RETURN f.name AS name, f.file_path AS file,
                       f.line_no AS line, dep AS dependents,
                       f.deep_risk_level AS deep_risk,
                       f.deep_complexity AS complexity
            """, r=store.repo_id)
            top_10 = [dict(row) for row in top]

            dead = s.run("""
                MATCH (f:CodeNode {repo_id:$r, node_type:'function'})
                WHERE NOT ()-[:DEPENDS_ON]->(f) AND NOT (f)-[:DEPENDS_ON]->()
                RETURN count(f) AS cnt
            """, r=store.repo_id).single()["cnt"]

            entry = s.run("""
                MATCH (f:CodeNode {repo_id:$r, node_type:'function'})
                WHERE NOT ()-[:DEPENDS_ON]->(f)
                RETURN count(f) AS cnt
            """, r=store.repo_id).single()["cnt"]

            risk_counts = s.run("""
                MATCH (file:CodeNode {repo_id:$r, node_type:'file'})
                OPTIONAL MATCH (file)-[:DEPENDS_ON]->(fn:CodeNode {node_type:'function'})
                WITH file, count(DISTINCT fn) AS fc
                RETURN
                  sum(CASE WHEN fc > 30 THEN 1 ELSE 0 END) AS critical,
                  sum(CASE WHEN fc > 15 AND fc <= 30 THEN 1 ELSE 0 END) AS high
            """, r=store.repo_id).single()

            # ── DEEP AST DATA ─────────────────────────────────────────
            deep_risk = s.run("""
                MATCH (n:CodeNode {repo_id:$r, node_type:'function'})
                WHERE n.deep_risk_level IS NOT NULL
                RETURN
                    sum(CASE WHEN n.deep_risk_level = 'CRITICAL' THEN 1 ELSE 0 END) AS critical,
                    sum(CASE WHEN n.deep_risk_level = 'HIGH'     THEN 1 ELSE 0 END) AS high,
                    sum(CASE WHEN n.deep_risk_level = 'MEDIUM'   THEN 1 ELSE 0 END) AS medium,
                    sum(CASE WHEN n.deep_risk_level = 'LOW'      THEN 1 ELSE 0 END) AS low,
                    avg(n.deep_complexity) AS avg_complexity,
                    max(n.deep_complexity) AS max_complexity,
                    count(n) AS total_analyzed
            """, r=store.repo_id).single()

            hotspots = s.run("""
                MATCH (n:CodeNode {repo_id:$r, node_type:'function'})
                WHERE n.deep_risk_level IN ['HIGH','CRITICAL']
                RETURN n.name AS name, n.file_path AS file,
                       n.line_no AS line,
                       n.deep_risk_level AS risk,
                       n.deep_complexity AS complexity,
                       n.deep_risk_reasons AS reasons,
                       n.deep_raises AS raises
                ORDER BY
                    CASE n.deep_risk_level WHEN 'CRITICAL' THEN 0 ELSE 1 END,
                    n.deep_complexity DESC
                LIMIT 10
            """, r=store.repo_id)
            hotspots_list = [dict(row) for row in hotspots]

            exception_summary = s.run("""
                MATCH (n:CodeNode {repo_id:$r})-[:RAISES]->(ex:ExceptionNode)
                RETURN ex.exc_type AS exc_type, count(*) AS raised_by
                ORDER BY raised_by DESC LIMIT 10
            """, r=store.repo_id)
            exc_list = [dict(row) for row in exception_summary]

        deep_data = {}
        if deep_risk and deep_risk["total_analyzed"]:
            deep_data = {
                "total_analyzed":   deep_risk["total_analyzed"],
                "risk_distribution": {
                    "CRITICAL": deep_risk["critical"],
                    "HIGH":     deep_risk["high"],
                    "MEDIUM":   deep_risk["medium"],
                    "LOW":      deep_risk["low"],
                },
                "avg_complexity":  round(deep_risk["avg_complexity"] or 0, 2),
                "max_complexity":  deep_risk["max_complexity"],
                "hotspots":        hotspots_list,
                "exception_summary": exc_list,
            }

        return {
            "total_files":        stats.get("files", 0),
            "total_functions":    stats.get("functions", 0),
            "total_classes":      stats.get("classes", 0),
            "dead_code_count":    dead,
            "entry_points_count": entry,
            "top_10_most_called": top_10,
            "files": [],
            "issues_summary": {
                "critical":     risk_counts["critical"] if risk_counts else 0,
                "high":         risk_counts["high"]     if risk_counts else 0,
                "total_issues": (risk_counts["critical"] + risk_counts["high"]) if risk_counts else 0,
            },
            # ── NEW: Deep AST ──────────────────────────────────────────
            "deep_ast": deep_data,
        }
    except Exception as e:
        return {"error": str(e)}


def _build_summary_in_memory(store) -> dict:
    func_nodes  = {nid: n for nid, n in store.nodes.items() if n.type == "function"}
    file_nodes  = {nid: n for nid, n in store.nodes.items() if n.type == "file"}
    class_nodes = {nid: n for nid, n in store.nodes.items() if n.type == "class"}

    all_funcs_sorted = sorted(func_nodes.values(), key=lambda n: -len(n.parents))
    top_10 = [
        {"name": n.name, "file": n.file_path, "line": n.line_no,
         "dependents": len(n.parents), "risk": _func_risk(len(n.parents))}
        for n in all_funcs_sorted[:10]
    ]
    dead  = sum(1 for n in func_nodes.values() if len(n.parents) == 0 and len(n.children) == 0)
    entry = sum(1 for n in func_nodes.values() if len(n.parents) == 0)

    file_risks = []
    for fn in file_nodes.values():
        ff = [n for n in func_nodes.values() if n.file_path == fn.file_path]
        max_dep = max((len(n.parents) for n in ff), default=0)
        file_risks.append(_file_risk(len(ff), max_dep))

    return {
        "total_files":        len(file_nodes),
        "total_functions":    len(func_nodes),
        "total_classes":      len(class_nodes),
        "dead_code_count":    dead,
        "entry_points_count": entry,
        "top_10_most_called": top_10,
        "files": [],
        "issues_summary": {
            "critical":     file_risks.count("CRITICAL"),
            "high":         file_risks.count("HIGH"),
            "total_issues": file_risks.count("CRITICAL") + file_risks.count("HIGH"),
        },
        "deep_ast": {},
    }


def get_orchestrator_by_id(repo_id: str):
    job = _jobs.get(repo_id)
    if not job or not job["graph_ready"]:
        return None
    return job.get("orchestrator")

def list_all_repos() -> list:
    return [
        {
            "repo_id": j["repo_id"],
            "git_url": j["git_url"],
            "status": j["status"],
            "primary_language": j["overview"]["primary_language"] if j["overview"] else None,
            "created_at": j["created_at"]
        }
        for j in _jobs.values()
    ]


def _func_risk(dependents: int) -> str:
    if dependents == 0:  return "ISOLATED"
    if dependents <= 3:  return "LOW"
    if dependents <= 10: return "MEDIUM"
    if dependents <= 30: return "HIGH"
    return "CRITICAL"


def _file_risk(func_count: int, max_dependents: int) -> str:
    if max_dependents > 30: return "CRITICAL"
    if max_dependents > 10: return "HIGH"
    if func_count > 30:     return "HIGH"
    if func_count > 15:     return "MEDIUM"
    if func_count > 5:      return "LOW"
    return "ISOLATED"


async def stream_status(repo_id: str) -> AsyncGenerator[str, None]:
    import json, asyncio
    while True:
        job = _jobs.get(repo_id)
        if not job:
            yield f"data: {json.dumps({'error': 'Repo not found'})}\n\n"
            break
        status = job["status"]
        payload = {
            "status":      status,
            "overview":    job.get("overview"),
            "graph_ready": job.get("graph_ready", False),
            "graph_stats": job.get("graph_stats"),
            "error":       job.get("error"),
        }
        yield f"data: {json.dumps(payload)}\n\n"
        if status in ("READY", "ERROR"):
            break
        await asyncio.sleep(1)


def get_files_page(repo_id: str, page: int = 1, page_size: int = 30,
                   risk_filter: str = None) -> Optional[dict]:
    job = _jobs.get(repo_id)
    if not job or not job["graph_ready"]:
        return None

    store = job["orchestrator"].store

    from app.code_intelligence.graph.neo4j_store import Neo4jStore
    if isinstance(store, Neo4jStore):
        return _files_page_neo4j(store, page, page_size, risk_filter)
    else:
        return _files_page_in_memory(store, job.get("repo_path"), page, page_size, risk_filter)


def _files_page_neo4j(store, page: int, page_size: int, risk_filter: str) -> dict:
    """Neo4j se paginated files — deep AST data included."""
    try:
        driver = store._connect()
        with driver.session() as s:

            # Filter clause
            filter_clause = ""
            if risk_filter:
                filter_clause = f"AND n.deep_risk_level = '{risk_filter.upper()}'"

            total_row = s.run(f"""
                MATCH (n:CodeNode {{repo_id:$r, node_type:'file'}})
                RETURN count(n) AS cnt
            """, r=store.repo_id).single()
            total = total_row["cnt"] if total_row else 0

            skip = (page - 1) * page_size

            rows = s.run(f"""
                MATCH (f:CodeNode {{repo_id:$r, node_type:'file'}})
                OPTIONAL MATCH (f)-[:DEPENDS_ON]->(fn:CodeNode {{repo_id:$r, node_type:'function'}})
                WITH f,
                     count(fn) AS func_count,
                     max(fn.deep_complexity) AS max_complexity,
                     sum(CASE WHEN fn.deep_risk_level IN ['HIGH','CRITICAL'] THEN 1 ELSE 0 END) AS risky_funcs,
                     collect(CASE WHEN fn.deep_risk_level IN ['HIGH','CRITICAL']
                             THEN fn.name END)[..3] AS top_risky_names
                RETURN f.file_path          AS file,
                       f.line_no            AS lines,
                       func_count,
                       max_complexity,
                       risky_funcs,
                       top_risky_names
                ORDER BY risky_funcs DESC, max_complexity DESC
                SKIP $skip LIMIT $limit
            """, r=store.repo_id, skip=skip, limit=page_size)

            files = []
            for row in rows:
                r = dict(row)
                mc = r.get("max_complexity") or 0
                rf = r.get("risky_funcs") or 0
                # Risk derive karo
                if rf >= 3 or mc >= 15:    risk = "CRITICAL"
                elif rf >= 1 or mc >= 8:   risk = "HIGH"
                elif mc >= 4:              risk = "MEDIUM"
                elif r.get("func_count"):  risk = "LOW"
                else:                      risk = "ISOLATED"

                if risk_filter and risk != risk_filter.upper():
                    continue

                files.append({
                    "file":           r.get("file"),
                    "function_count": r.get("func_count", 0),
                    "max_complexity": mc,
                    "risky_functions": rf,
                    "top_risky_functions": [n for n in (r.get("top_risky_names") or []) if n],
                    "risk":           risk,
                })

        return {
            "page":        page,
            "page_size":   page_size,
            "total_files": total,
            "total_pages": max(1, (total + page_size - 1) // page_size),
            "files":       files,
        }
    except Exception as e:
        return {"error": str(e)}


def get_file_detail(repo_id: str, file_path: str) -> Optional[dict]:
    job = _jobs.get(repo_id)
    if not job or not job["graph_ready"]:
        return None

    store = job["orchestrator"].store

    from app.code_intelligence.graph.neo4j_store import Neo4jStore
    if isinstance(store, Neo4jStore):
        return _file_detail_neo4j(store, file_path)
    else:
        return _file_detail_in_memory(store, job.get("repo_path"), file_path)


def _file_detail_neo4j(store, file_path: str) -> dict:
    """Neo4j se ek file ka poora detail — deep AST included."""
    try:
        driver = store._connect()
        with driver.session() as s:

            # Functions with deep data
            fn_rows = s.run("""
                MATCH (fn:CodeNode {repo_id:$r, node_type:'function', file_path:$fp})
                OPTIONAL MATCH ()-[:DEPENDS_ON]->(fn)
                WITH fn, count(*) AS dependents
                RETURN fn.name              AS name,
                       fn.line_no           AS line,
                       dependents,
                       fn.deep_risk_level   AS deep_risk,
                       fn.deep_complexity   AS complexity,
                       fn.deep_branch_count AS branches,
                       fn.deep_raises       AS raises,
                       fn.deep_risk_reasons AS risk_reasons,
                       fn.deep_is_async     AS is_async,
                       fn.deep_logic_lines  AS logic_lines,
                       fn.deep_max_depth    AS max_depth,
                       fn.deep_return_type  AS return_type,
                       fn.deep_data_inputs  AS inputs
                ORDER BY dependents DESC
            """, r=store.repo_id, fp=file_path)
            functions = [dict(row) for row in fn_rows]

            # Branches for each function
            branch_rows = s.run("""
                MATCH (fn:CodeNode {repo_id:$r, node_type:'function', file_path:$fp})
                      -[:HAS_BRANCH]->(b:BranchNode {repo_id:$r})
                RETURN fn.name AS func_name,
                       b.branch_type AS type,
                       b.condition   AS condition,
                       b.line_no     AS line,
                       b.leads_raise AS raises,
                       b.raises_type AS raises_type,
                       b.leads_return AS returns
                ORDER BY b.line_no
            """, r=store.repo_id, fp=file_path)
            branches_by_func = {}
            for row in branch_rows:
                fn = row["func_name"]
                if fn not in branches_by_func:
                    branches_by_func[fn] = []
                branches_by_func[fn].append({
                    "type":      row["type"],
                    "condition": row["condition"],
                    "line":      row["line"],
                    "raises":    row["raises"],
                    "raises_type": row["raises_type"],
                    "returns":   row["returns"],
                })

            # Attach branches to functions
            for fn in functions:
                fn["branch_detail"] = branches_by_func.get(fn["name"], [])

            # Classes
            cls_rows = s.run("""
                MATCH (c:CodeNode {repo_id:$r, node_type:'class', file_path:$fp})
                RETURN c.name AS name, c.line_no AS line
            """, r=store.repo_id, fp=file_path)
            classes = [dict(row) for row in cls_rows]

            # Exception summary for this file
            exc_rows = s.run("""
                MATCH (fn:CodeNode {repo_id:$r, node_type:'function', file_path:$fp})
                      -[:RAISES]->(ex:ExceptionNode {repo_id:$r})
                RETURN fn.name AS func_name, ex.exc_type AS exc_type
            """, r=store.repo_id, fp=file_path)
            exceptions = [dict(row) for row in exc_rows]

        return {
            "file":       file_path,
            "functions":  functions,
            "classes":    classes,
            "exceptions": exceptions,
        }
    except Exception as e:
        return {"error": str(e)}


def _files_page_in_memory(store, repo_path, page, page_size, risk_filter) -> dict:
    def _norm(p): return p.replace("\\", "/").lower().strip().lstrip("/")

    file_nodes  = {nid: n for nid, n in store.nodes.items() if n.type == "file"}
    func_nodes  = {nid: n for nid, n in store.nodes.items() if n.type == "function"}
    class_nodes = {nid: n for nid, n in store.nodes.items() if n.type == "class"}

    all_files = []
    for fid, fnode in file_nodes.items():
        ff = [n for n in func_nodes.values()  if _norm(n.file_path) == _norm(fnode.file_path)]
        fc = [n for n in class_nodes.values() if _norm(n.file_path) == _norm(fnode.file_path)]
        max_dep = max((len(n.parents) for n in ff), default=0)
        risk = _file_risk(len(ff), max_dep)

        if risk_filter and risk != risk_filter.upper():
            continue

        try:
            abs_path = os.path.join(repo_path, fnode.file_path.replace("\\", "/")) if repo_path else fnode.file_path
            total_lines = len(Path(abs_path).read_text(errors="ignore").splitlines())
        except:
            total_lines = 0

        all_files.append({
            "file":           fnode.file_path,
            "total_lines":    total_lines,
            "function_count": len(ff),
            "class_count":    len(fc),
            "max_dependents": max_dep,
            "risk":           risk,
        })

    risk_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "ISOLATED": 4}
    all_files.sort(key=lambda x: risk_order.get(x["risk"], 5))

    total = len(all_files)
    start = (page - 1) * page_size
    end   = start + page_size

    return {
        "page":        page,
        "page_size":   page_size,
        "total_files": total,
        "total_pages": max(1, (total + page_size - 1) // page_size),
        "files":       all_files[start:end],
    }


def _file_detail_in_memory(store, repo_path, file_path) -> dict:
    def _norm(p): return p.replace("\\", "/").lower().strip().lstrip("/")

    func_nodes  = {nid: n for nid, n in store.nodes.items() if n.type == "function"}
    class_nodes = {nid: n for nid, n in store.nodes.items() if n.type == "class"}

    file_funcs   = [n for n in func_nodes.values()  if _norm(n.file_path) == _norm(file_path)]
    file_classes = [n for n in class_nodes.values() if _norm(n.file_path) == _norm(file_path)]

    functions = []
    for fn in file_funcs:
        dep = len(fn.parents)
        called_by = [{"name": store.nodes[p].name, "file": store.nodes[p].file_path}
                     for p in fn.parents if p in store.nodes][:10]
        calls     = [{"name": store.nodes[c].name, "file": store.nodes[c].file_path}
                     for c in fn.children if c in store.nodes][:10]
        functions.append({
            "name":        fn.name,
            "line":        fn.line_no,
            "dependents":  dep,
            "risk":        _func_risk(dep),
            "called_by":   called_by,
            "calls":       calls,
            "is_dead_code": dep == 0 and len(fn.children) == 0,
        })
    functions.sort(key=lambda x: -x["dependents"])

    classes = []
    for cn in file_classes:
        methods = [{"name": store.nodes[m].name.split(".")[-1], "line": store.nodes[m].line_no}
                   for m in cn.children if m in store.nodes]
        classes.append({"name": cn.name, "line": cn.line_no, "methods": methods})

    try:
        abs_path = os.path.join(repo_path, file_path.replace("\\", "/")) if repo_path else file_path
        total_lines = len(Path(abs_path).read_text(errors="ignore").splitlines())
    except:
        total_lines = 0

    return {
        "file":        file_path,
        "total_lines": total_lines,
        "functions":   functions,
        "classes":     classes,
    }
