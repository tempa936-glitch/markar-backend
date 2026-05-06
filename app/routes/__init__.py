"""Routes package — all API routers are registered here."""

from .health import system_router, ci_router

__all__ = ["system_router", "ci_router"]
