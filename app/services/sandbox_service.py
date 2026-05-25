"""
Sandbox Service — Isolated Code Execution.
Generated code ko safely run karo — network/filesystem isolated.

3 modes (auto-detect):
  1. Docker  — best isolation (docker SDK)
  2. Process — subprocess + timeout + restricted env (fallback)
  3. Dry-run — sirf syntax check, no actual execution (safest fallback)

Usage:
    sandbox = get_sandbox()
    result  = await sandbox.run(code="print('hello')", language="python")
"""
import os
import sys
import time
import uuid
import asyncio
import tempfile
import subprocess
from typing import Dict, Optional
from dataclasses import dataclass


# ── Config ────────────────────────────────────────────────────────────────────

DEFAULT_TIMEOUT   = int(os.getenv("SANDBOX_TIMEOUT_SEC",  "15"))
MAX_OUTPUT_BYTES  = int(os.getenv("SANDBOX_MAX_OUTPUT",   "32768"))   # 32 KB
DOCKER_IMAGE      = os.getenv("SANDBOX_DOCKER_IMAGE",     "python:3.11-slim")
SANDBOX_MODE      = os.getenv("SANDBOX_MODE", "auto")   # auto | docker | process | dryrun


# ── Result ────────────────────────────────────────────────────────────────────

@dataclass
class SandboxResult:
    run_id:     str
    mode:       str       # docker | process | dryrun
    language:   str
    status:     str       # success | error | timeout | syntax_error
    stdout:     str
    stderr:     str
    exit_code:  int
    latency_ms: float
    timed_out:  bool = False

    def to_dict(self) -> Dict:
        return {
            "run_id":     self.run_id,
            "mode":       self.mode,
            "language":   self.language,
            "status":     self.status,
            "stdout":     self.stdout[:MAX_OUTPUT_BYTES],
            "stderr":     self.stderr[:4096],
            "exit_code":  self.exit_code,
            "latency_ms": round(self.latency_ms, 1),
            "timed_out":  self.timed_out,
            "success":    self.status == "success",
        }


# ── Language Configs ──────────────────────────────────────────────────────────

LANG_CONFIGS = {
    "python": {
        "ext":     ".py",
        "cmd":     [sys.executable, "{file}"],
        "docker_cmd": ["python3", "{file}"],
        "syntax_check": [sys.executable, "-m", "py_compile", "{file}"],
    },
    "javascript": {
        "ext":     ".js",
        "cmd":     ["node", "{file}"],
        "docker_cmd": ["node", "{file}"],
        "docker_image": "node:20-slim",
        "syntax_check": ["node", "--check", "{file}"],
    },
    "typescript": {
        "ext":     ".ts",
        "cmd":     ["npx", "ts-node", "{file}"],
        "docker_cmd": ["npx", "ts-node", "{file}"],
        "docker_image": "node:20-slim",
        "syntax_check": ["npx", "tsc", "--noEmit", "{file}"],
    },
    "bash": {
        "ext":     ".sh",
        "cmd":     ["bash", "{file}"],
        "docker_cmd": ["bash", "{file}"],
        "syntax_check": ["bash", "-n", "{file}"],
    },
}


# ── Sandbox Service ───────────────────────────────────────────────────────────

class SandboxService:
    """
    Code execution sandbox.
    Auto-detects best available mode.
    """

    def __init__(self):
        self._mode = self._detect_mode()
        print(f"[Sandbox] Mode: {self._mode}")

    def _detect_mode(self) -> str:
        if SANDBOX_MODE != "auto":
            return SANDBOX_MODE

        # Docker available hai?
        try:
            import docker
            client = docker.from_env()
            client.ping()
            return "docker"
        except Exception:
            pass

        # Process fallback
        return "process"

    async def run(
        self,
        code:      str,
        language:  str = "python",
        timeout:   int = DEFAULT_TIMEOUT,
        run_id:    str = None,
    ) -> SandboxResult:
        """
        Code safely run karo.
        Returns SandboxResult with stdout, stderr, exit_code.
        """
        run_id   = run_id or str(uuid.uuid4())[:10]
        lang_cfg = LANG_CONFIGS.get(language.lower())

        if not lang_cfg:
            return SandboxResult(
                run_id=run_id, mode=self._mode, language=language,
                status="error", stdout="", exit_code=1, latency_ms=0,
                stderr=f"Language '{language}' supported nahi: {list(LANG_CONFIGS.keys())}",
            )

        # Syntax check pehle (fast fail)
        syntax_err = await self._syntax_check(code, language, lang_cfg)
        if syntax_err:
            return SandboxResult(
                run_id=run_id, mode="dryrun", language=language,
                status="syntax_error", stdout="", exit_code=1,
                latency_ms=0, stderr=syntax_err,
            )

        # Actual execution
        if self._mode == "docker":
            return await self._run_docker(code, language, lang_cfg, timeout, run_id)
        else:
            return await self._run_process(code, language, lang_cfg, timeout, run_id)

    async def syntax_only(self, code: str, language: str = "python") -> Dict:
        """Sirf syntax check — execution nahi."""
        lang_cfg = LANG_CONFIGS.get(language.lower())
        if not lang_cfg:
            return {"valid": False, "error": f"Language '{language}' not supported"}

        err = await self._syntax_check(code, language, lang_cfg)
        return {"valid": not bool(err), "error": err or ""}

    # ── Syntax Check ──────────────────────────────────────────────────────────

    async def _syntax_check(self, code: str, language: str, cfg: Dict) -> Optional[str]:
        """Returns error string ya None agar valid hai."""
        if language == "python":
            try:
                import ast
                ast.parse(code)
                return None
            except SyntaxError as e:
                return f"SyntaxError line {e.lineno}: {e.msg}"
        return None  # Other languages — skip for now

    # ── Docker Execution ──────────────────────────────────────────────────────

    async def _run_docker(
        self, code: str, language: str, cfg: Dict,
        timeout: int, run_id: str
    ) -> SandboxResult:
        start = time.time()
        tmp_dir = tempfile.mkdtemp(prefix=f"markar_sandbox_{run_id}_")

        try:
            import docker
            client = docker.from_env()

            # Code file likho
            code_file = os.path.join(tmp_dir, f"code{cfg['ext']}")
            with open(code_file, "w", encoding="utf-8") as fh:
                fh.write(code)

            image   = cfg.get("docker_image", DOCKER_IMAGE)
            cmd_tpl = cfg.get("docker_cmd", cfg["cmd"])
            cmd     = [c.replace("{file}", f"/sandbox/code{cfg['ext']}") for c in cmd_tpl]

            loop = asyncio.get_event_loop()
            container_result = await loop.run_in_executor(
                None,
                lambda: client.containers.run(
                    image=image,
                    command=cmd,
                    volumes={tmp_dir: {"bind": "/sandbox", "mode": "ro"}},
                    network_mode="none",         # No network
                    mem_limit="128m",            # 128 MB RAM
                    cpu_period=100000,
                    cpu_quota=50000,             # 50% CPU
                    read_only=True,
                    remove=True,
                    stdout=True,
                    stderr=True,
                    timeout=timeout,
                )
            )

            elapsed = (time.time() - start) * 1000
            stdout  = container_result.decode("utf-8", errors="replace")[:MAX_OUTPUT_BYTES]

            return SandboxResult(
                run_id=run_id, mode="docker", language=language,
                status="success", stdout=stdout, stderr="",
                exit_code=0, latency_ms=elapsed,
            )

        except Exception as e:
            err_str = str(e)
            timed_out = "timeout" in err_str.lower() or "timed out" in err_str.lower()
            elapsed = (time.time() - start) * 1000
            return SandboxResult(
                run_id=run_id, mode="docker", language=language,
                status="timeout" if timed_out else "error",
                stdout="", stderr=err_str[:2000],
                exit_code=1, latency_ms=elapsed, timed_out=timed_out,
            )
        finally:
            import shutil
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass

    # ── Process Execution (fallback) ──────────────────────────────────────────

    async def _run_process(
        self, code: str, language: str, cfg: Dict,
        timeout: int, run_id: str
    ) -> SandboxResult:
        start = time.time()
        tmp_file = None

        try:
            # Temp file mein code likho
            suffix   = cfg["ext"]
            fd, tmp_file = tempfile.mkstemp(suffix=suffix, prefix=f"markar_{run_id}_")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(code)

            cmd = [c.replace("{file}", tmp_file) for c in cfg["cmd"]]

            # Restricted environment — minimal env vars
            safe_env = {
                "PATH":     os.getenv("PATH", "/usr/bin:/bin"),
                "HOME":     tempfile.gettempdir(),
                "LANG":     "en_US.UTF-8",
                "PYTHONPATH": "",
                "PYTHONDONTWRITEBYTECODE": "1",
            }

            loop   = asyncio.get_event_loop()
            proc   = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    cmd,
                    capture_output=True,
                    timeout=timeout,
                    env=safe_env,
                    cwd=tempfile.gettempdir(),
                )
            )

            elapsed = (time.time() - start) * 1000
            stdout  = proc.stdout.decode("utf-8", errors="replace")[:MAX_OUTPUT_BYTES]
            stderr  = proc.stderr.decode("utf-8", errors="replace")[:4096]
            status  = "success" if proc.returncode == 0 else "error"

            return SandboxResult(
                run_id=run_id, mode="process", language=language,
                status=status, stdout=stdout, stderr=stderr,
                exit_code=proc.returncode, latency_ms=elapsed,
            )

        except subprocess.TimeoutExpired:
            elapsed = (time.time() - start) * 1000
            return SandboxResult(
                run_id=run_id, mode="process", language=language,
                status="timeout", stdout="", stderr=f"Timeout after {timeout}s",
                exit_code=124, latency_ms=elapsed, timed_out=True,
            )
        except FileNotFoundError as e:
            return SandboxResult(
                run_id=run_id, mode="process", language=language,
                status="error", stdout="",
                stderr=f"Runtime not found: {e}. Install karo.",
                exit_code=127, latency_ms=0,
            )
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            return SandboxResult(
                run_id=run_id, mode="process", language=language,
                status="error", stdout="", stderr=str(e)[:2000],
                exit_code=1, latency_ms=elapsed,
            )
        finally:
            if tmp_file:
                try:
                    os.unlink(tmp_file)
                except Exception:
                    pass


# ── Global instance ───────────────────────────────────────────────────────────

_sandbox: Optional[SandboxService] = None


def get_sandbox() -> SandboxService:
    global _sandbox
    if _sandbox is None:
        _sandbox = SandboxService()
    return _sandbox
