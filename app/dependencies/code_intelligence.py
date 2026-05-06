"""FastAPI dependency — provides a scoped CodeIntelligenceOrchestrator per request."""

from fastapi import HTTPException
from app.code_intelligence.orchestrator import CodeIntelligenceOrchestrator



# Module-level singleton (can be replaced with Redis-backed registry later)
_orchestrator: CodeIntelligenceOrchestrator | None = None


def get_orchestrator() -> CodeIntelligenceOrchestrator:
    """Return the initialized orchestrator or raise 400."""
    if _orchestrator is None:
        raise HTTPException(
            status_code=400,
            detail="System not initialized. POST /api/code-intelligence/initialize first."
        )
    return _orchestrator


def set_orchestrator(instance: CodeIntelligenceOrchestrator) -> None:
    """Store a new orchestrator instance (called during /initialize)."""
    global _orchestrator
    _orchestrator = instance
