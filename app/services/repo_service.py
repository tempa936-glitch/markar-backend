import os
import uuid
import shutil
import subprocess
import threading
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Optional

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

def start_initialization(git_url=None, repo_path=None) -> dict:
    
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
            result = subprocess.run(
                ["git", "clone", "--depth", "1",
                 job["git_url"], job["clone_path"]],
                capture_output=True, text=True, timeout=120
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
        job["status"] = "PARSING"
        from app.code_intelligence import CodeIntelligenceOrchestrator
        instance = CodeIntelligenceOrchestrator(job["repo_path"])
        init_result = instance.initialize()
        job["orchestrator"] = instance
        job["parser"] = instance.store
        job["graph_stats"] = init_result
        job["graph_ready"] = True
        job["status"] = "READY"
        
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
    }

    # Graph ready hone ke baad hi deep data add karo
    if job["graph_ready"] and job.get("orchestrator"):
        orchestrator = job["orchestrator"]
        store = orchestrator.store
        base["graph_stats"] = store.get_stats()
        base["repo_overview"] = _build_repo_overview(store, job.get("parser"),repo_path=job.get("repo_path") )

    return base
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
                and store.nodes[p].type == ("function", "method")
            ]
            # Yeh function kisko call karta hai
            calls = [
                {
                    "name": store.nodes[c].name,
                    "file": store.nodes[c].file_path
                }
                for c in fn.children
                if c in store.nodes 
                and store.nodes[c].type == ("function", "method")
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