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

_jobs = {}  # { repo_id: { ...job data... } }

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

def start_initialization(git_url=None, repo_path=None, git_branch="main") -> dict:
    
    # Deterministic repo_id — same URL = same ID
    clone_path = None
    if git_url:
        import hashlib
        repo_id = hashlib.sha256(git_url.encode()).hexdigest()[:12]
        # ✅ FIX: clone_path set karo — warna git clone ko destination nahi milti
        clone_path = os.path.join(tempfile.gettempdir(), f"markar_{repo_id}")
    else:
        repo_id = str(uuid.uuid4())[:8]
    
    # Job entry banao
    _jobs[repo_id] = {
        "repo_id": repo_id,
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
    
    # Background thread shuru karo
    thread = threading.Thread(
        target=_worker,
        args=(repo_id,),
        daemon=True
    )
    thread.start()
    
    # TURANT return karo — wait mat karo
    return {
        "repo_id": repo_id,
        "status": _jobs[repo_id]["status"],
        "message": f"Poll /api/code-intelligence/status/{repo_id}",
        "overview": None,
        "graph_ready": False,
        "error": None
    }

def _force_rmtree(path: str):
    """
    Windows pe git clone folder delete karne ka sahi tarika.
    Git ke .git/objects files read-only hote hain Windows mein —
    normal rmtree fail karta hai. onerror se force chmod karke delete karo.
    """
    import stat

    def _on_error(func, fpath, exc_info):
        # Read-only file → permission do → phir delete
        try:
            os.chmod(fpath, stat.S_IWRITE)
            func(fpath)
        except Exception:
            pass  # Agar phir bhi fail ho toh ignore

    shutil.rmtree(path, onerror=_on_error)


def _worker(repo_id: str):
    job = _jobs[repo_id]
    
    try:
        # ── Stage 1: Clone (agar git_url hai) ──────────────
        if job["git_url"]:
            job["status"] = "CLONING"
            # Windows fix: read-only files (git objects) ko force delete karo
            if job["clone_path"] and os.path.exists(job["clone_path"]):
                _force_rmtree(job["clone_path"])
            clone_args = ["git", "clone", "--depth", "1"]
            if job.get("git_branch"):
                clone_args += ["--branch", job["git_branch"]]
            clone_args += [job["git_url"], job["clone_path"]]
            result = subprocess.run(
                clone_args,
                capture_output=True, text=True, timeout=800
            )
            if result.returncode != 0:
                raise Exception(f"Clone failed: {result.stderr.strip()}")
            job["repo_path"] = job["clone_path"]
        
        # ── Stage 2: Quick overview ─────────────────────────
        # Yeh 1 second mein run hoga — sirf files scan karo
        overview = _quick_overview(job["repo_path"])
        job["overview"] = overview
        job["status"] = "OVERVIEW_READY"
        # ← AB FRONTEND KO DETAILS MIL JAATI HAIN
        
        # ── Stage 3: Full graph build ───────────────────────
        job["status"]  = "CHECKING_LANGUAGES"

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

        # ── Stage 4: Full graph build ───────────────────────
        job["status"] = "PARSING"
        print(f"[STAGE4] Starting for {job['repo_path']}")
        try:
            from app.code_intelligence import CodeIntelligenceOrchestrator
            instance = CodeIntelligenceOrchestrator(job["repo_path"],repo_id=job["repo_id"])
            print(f"[STAGE4] Orchestrator created")
            init_result = instance.initialize()
            print(f"[STAGE4] Initialize done: {type(init_result)}")
            job["orchestrator"] = instance
            job["parser"] = instance.store
            job["graph_stats"] = init_result
            job["graph_ready"] = True
            job["status"] = "READY"
            print(f"[STAGE4] ✅ READY!") 
        except Exception as stage4_error:
            import traceback
            print(f"[STAGE4] ❌ ERROR: {stage4_error}")      # ← ADD
            print(traceback.format_exc())                    # ← ADD
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
        # Cleanup cloned folder — Windows safe
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
        # Ignore karo
        if any(p in IGNORE_DIRS for p in fp.parts):
            continue
        
        total_files += 1
        total_bytes += fp.stat().st_size
        
        ext = fp.suffix.lower()
        if ext in LANG_MAP:
            lang = LANG_MAP[ext]
            languages[lang] = languages.get(lang, 0) + 1
            try:
                lines = fp.read_text(
                    errors="ignore"
                ).count("\n")
                total_lines += lines
            except:
                pass
    
    # Top-level structure
    top_level = []
    try:
        for item in sorted(path.iterdir()):
            if item.name in IGNORE_DIRS:
                continue
            if item.name.startswith("."):
                continue
            top_level.append({
                "name": item.name,
                "type": "directory" if item.is_dir() else "file"
            })
    except:
        pass
    
    primary = max(languages, key=languages.get) if languages else "Unknown"
    
    return {
        "total_files": total_files,
        "total_lines": total_lines,
        "size_mb": round(total_bytes / (1024 * 1024), 2),
        "primary_language": primary,
        "languages": dict(
            sorted(languages.items(), key=lambda x: -x[1])
        ),
        "language_count": len(languages),
        "top_level_structure": top_level[:20],
        "has_docker": (
            (path / "Dockerfile").exists() or
            (path / "docker-compose.yml").exists()
        ),
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
    # DEBUG — yeh print karo
    print(f"DEBUG status: {job['status']}")
    print(f"DEBUG graph_ready: {job['graph_ready']}")
    print(f"DEBUG orchestrator exists: {job.get('orchestrator') is not None}")
    print(f"DEBUG job keys: {list(job.keys())}")
    # ← YEH 3 LINES ADD KARO
    print(f"=== DEBUG ===")
    print(f"graph_ready: {job['graph_ready']}")
    print(f"orchestrator: {job.get('orchestrator') is not None}")
    print(f"status: {job['status']}")
    print(f"=============")
    base = {
        "repo_id": job["repo_id"],
        "status": job["status"],
        "overview": job["overview"],
        "graph_ready": job["graph_ready"],
        "error": job.get("error"),
        "traceback": job.get("traceback"),   # ← debug ke liye
        "created_at": job["created_at"],
        "graph_stats": None,
        "repo_overview": None,
         # Language support — available after CHECKING_LANGUAGES stage completes
        "languages": {
            "installed": job.get("languages_installed"),
            "missing":   job.get("languages_missing"),
            "supported_extensions": job.get("supported_extensions"),
            "tip": "pip install tree-sitter-<lang> to add missing grammars"
                   if job.get("languages_missing") else None,
        } if job.get("languages_installed") is not None else None,             
    }

    # Graph ready hone ke baad sirf SUMMARY add karo — files alag endpoint se aayengi
    if job["graph_ready"] and job.get("orchestrator"):
        store = job["orchestrator"].store
        base["graph_stats"] = store.get_stats()

        from app.code_intelligence.graph.neo4j_store import Neo4jStore
        if isinstance(store, Neo4jStore):
            # Sirf summary — files nahi (files /files endpoint se aayengi)
            base["repo_overview"] = _build_summary_neo4j(store)
        else:
            base["repo_overview"] = _build_summary_in_memory(store)

    return base


def _build_summary_neo4j(store) -> dict:
    """Neo4j se sirf summary counts — fast, koi LIMIT nahi."""
    try:
        from app.code_intelligence.graph.neo4j_store import Neo4jStore
        driver = store._connect()
        with driver.session() as s:
            stats = store.get_stats()

            top = s.run("""
                MATCH (f:CodeNode {repo_id:$r, node_type:'function'})
                OPTIONAL MATCH ()-[:DEPENDS_ON]->(f)
                WITH f, count(*) AS dep
                ORDER BY dep DESC LIMIT 10
                RETURN f.name AS name, f.file_path AS file,
                       f.line_no AS line, dep AS dependents
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

        return {
            "total_files":        stats.get("files", 0),
            "total_functions":    stats.get("functions", 0),
            "total_classes":      stats.get("classes", 0),
            "dead_code_count":    dead,
            "entry_points_count": entry,
            "top_10_most_called": top_10,
            "files": [],   # ← empty — /files endpoint se lo
            "issues_summary": {
                "critical":     risk_counts["critical"] if risk_counts else 0,
                "high":         risk_counts["high"]     if risk_counts else 0,
                "total_issues": (risk_counts["critical"] + risk_counts["high"]) if risk_counts else 0,
            }
        }
    except Exception as e:
        return {"error": str(e)}


def _build_summary_in_memory(store) -> dict:
    """In-memory store se sirf summary — files nahi."""
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
        "files": [],  # ← empty — /files endpoint se lo
        "issues_summary": {
            "critical":     file_risks.count("CRITICAL"),
            "high":         file_risks.count("HIGH"),
            "total_issues": file_risks.count("CRITICAL") + file_risks.count("HIGH"),
        }
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

def _build_repo_overview(store, parser=None, repo_path=None) -> dict:
    """
    Graph ke nodes se poori repo ka X-ray banao.
    Ek baar mein sab kuch — files, classes, functions, risks.
    Saare nodes ke file_path ko normalize karo
    Graph mein relative paths hain — unhe consistent banao
    """
    def _norm(path: str) -> str:
        """Backslash → forward slash, lowercase"""
        return path.replace("\\", "/").lower().strip().lstrip("/")

    # ── Step 1: Saare file nodes nikalo ──────────────────────
    file_nodes = {
        nid: n for nid, n in store.nodes.items()
        if n.type == "file"
    }
    func_nodes = {
        nid: n for nid, n in store.nodes.items()
        if n.type == "function"
    }
    class_nodes = {
        nid: n for nid, n in store.nodes.items()
        if n.type == "class"
    }

    # ── Step 2: Har file ka breakdown banao ──────────────────
    files_breakdown = []

    for fid, fnode in file_nodes.items():
        fnode_norm = _norm(fnode.file_path)

        # Is file ke functions
        file_funcs = [
            n for n in func_nodes.values()
            if _norm(n.file_path) == _norm(fnode.file_path)
        ]
        # Is file ke classes
        file_classes = [
            n for n in class_nodes.values()
            if _norm(n.file_path) == _norm(fnode.file_path)
        ]

        # Har function ki detail
        functions_detail = []
        for fn in file_funcs:
            dependents_count = len(fn.parents)
            # Parent functions jo is function ko call karte hain
            called_by = [
                {
                    "name": store.nodes[p].name,
                    "file": store.nodes[p].file_path
                }
                for p in fn.parents
                if p in store.nodes 
                and store.nodes[p].type in ("function", "method")
            ]
            # Yeh function kisko call karta hai
            calls = [
                {
                    "name": store.nodes[c].name,
                    "file": store.nodes[c].file_path
                }
                for c in fn.children
                if c in store.nodes 
                and store.nodes[c].type in ("function", "method")
            ]

            functions_detail.append({
                "name": fn.name,
                "full_name": fn.name,
                "line": fn.line_no,
                "dependents_count": dependents_count,
                "called_by": called_by[:10],
                "calls": calls[:10],
                "risk": _func_risk(dependents_count),
                "is_entry_point": dependents_count == 0, 
                "is_dead_code": dependents_count == 0 and len(fn.children) == 0
            })

        # Sort by most depended upon
        functions_detail.sort(key=lambda x: -x["dependents_count"])

        # Har class ki detail
        classes_detail = []
        for cn in file_classes:
            methods = [
                {
                    "name": store.nodes[m].name.split(".")[-1],
                    "line": store.nodes[m].line_no,
                    "dependents": len(store.nodes[m].parents)
                }
                for m in cn.children
                if m in store.nodes
            ]
            classes_detail.append({
                "name": cn.name,
                "line": cn.line_no,
                "method_count": len(methods),
                "methods": sorted(methods, key=lambda x: -x["dependents"])
            })

        # File risk — based on function + class count
        total_funcs = len(file_funcs)
        max_dependents = max(
            (len(n.parents) for n in file_funcs), default=0
        )
        file_risk = _file_risk(total_funcs, max_dependents)

        try:
            if repo_path:
                abs_path = os.path.join(repo_path, fnode.file_path.replace("\\", "/"))
            else:
                abs_path = fnode.file_path
            actual_lines = len(Path(abs_path).read_text(errors="ignore").splitlines())    
        except:
            actual_lines = 0

        files_breakdown.append({
            "file": fnode.file_path,
            "total_lines": actual_lines,
            "function_count": total_funcs,
            "class_count": len(file_classes),
            "imported_by_count": len(fnode.parents),  # kitni files import karti hain
            "risk": file_risk,
            "functions": functions_detail,
            "classes": classes_detail,
            "top_3_risky_functions": functions_detail[:3],
             "summary": { 
                 "most_called_function": functions_detail[0]["name"] if functions_detail else None,
                 "entry_points_count": sum(1 for f in functions_detail if f["is_entry_point"]),
                 "dead_code_count": sum(1 for f in functions_detail if f["is_dead_code"])
             }
        })

    # Sort files by risk
    risk_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "ISOLATED": 4}
    files_breakdown.sort(key=lambda x: risk_order.get(x["risk"], 5))

    # ── Step 3: Repo-level insights ──────────────────────────

    # Top 10 most called functions across entire repo
    all_funcs_sorted = sorted(
        func_nodes.values(),
        key=lambda n: -len(n.parents)
    )
    top_functions = [
        {
            "name": n.name,
            "file": n.file_path,
            "line": n.line_no,
            "dependents": len(n.parents),
            "risk": _func_risk(len(n.parents))
        }
        for n in all_funcs_sorted[:10]
    ]

    # Entry points — functions jo koi call nahi karta
    entry_points = [
        {"name": n.name, "file": n.file_path, "line": n.line_no}
        for n in func_nodes.values()
        if len(n.parents) == 0
    ][:20]  # max 20

    # Dead code candidates — functions jo kuch call nahi karte
    dead_code = [
        {"name": n.name, "file": n.file_path, "line": n.line_no}
        for n in func_nodes.values()
        if len(n.parents) == 0 and len(n.children) == 0
    ][:20]

    # Critical files — bahut zyada functions ya dependents
    critical_files = [f for f in files_breakdown if f["risk"] == "CRITICAL"]
    high_files = [f for f in files_breakdown if f["risk"] == "HIGH"]

    return {
        "total_files": len(file_nodes),
        "total_functions": len(func_nodes),
        "total_classes": len(class_nodes),
        "critical_files_count": len(critical_files),
        "high_risk_files_count": len(high_files),
        "files": files_breakdown,
        "top_10_most_called_functions": top_functions,
        "entry_points": entry_points,
        "dead_code_candidates": dead_code,
        "issues_summary": {
            "critical": len(critical_files),
            "high": len(high_files),
            "total_issues": len(critical_files) + len(high_files)
        }
    }


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
    """
    SSE generator — status updates stream karo
    jab tak READY ya ERROR na ho
    """
    import json, asyncio

    while True:
        job = _jobs.get(repo_id)

        if not job:
            yield f"data: {json.dumps({'error': 'Repo not found'})}\n\n"
            break

        status = job["status"]
        
        payload = {
            "status": status,
            "overview": job.get("overview"),
            "graph_ready": job.get("graph_ready", False),
            "graph_stats": job.get("graph_stats"),
            "error": job.get("error"),
        }

        yield f"data: {json.dumps(payload)}\n\n"

        if status in ("READY", "ERROR"):
            break

        await asyncio.sleep(1)


def get_files_page(repo_id: str, page: int = 1, page_size: int = 30,
                   risk_filter: str = None) -> Optional[dict]:
    """
    Paginated files list — dashboard Files tab ke liye.
    Har page mein page_size files aayengi.
    """
    job = _jobs.get(repo_id)
    if not job or not job["graph_ready"]:
        return None

    store = job["orchestrator"].store

    from app.code_intelligence.graph.neo4j_store import Neo4jStore
    if isinstance(store, Neo4jStore):
        return store.get_files_page(page=page, page_size=page_size,
                                    risk_filter=risk_filter)
    else:
        # In-memory store ke liye
        return _files_page_in_memory(store, job.get("repo_path"),
                                     page, page_size, risk_filter)


def get_file_detail(repo_id: str, file_path: str) -> Optional[dict]:
    """
    Ek file ka poora detail — graph pe click karne par.
    Functions, classes, called_by, calls sab aata hai.
    """
    job = _jobs.get(repo_id)
    if not job or not job["graph_ready"]:
        return None

    store = job["orchestrator"].store

    from app.code_intelligence.graph.neo4j_store import Neo4jStore
    if isinstance(store, Neo4jStore):
        return store.get_file_detail(file_path)
    else:
        return _file_detail_in_memory(store, job.get("repo_path"), file_path)


def _files_page_in_memory(store, repo_path, page, page_size, risk_filter) -> dict:
    """In-memory store ke liye paginated files."""
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
    """In-memory store se ek file ka poora detail."""
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
