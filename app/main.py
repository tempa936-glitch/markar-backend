"""Markar Intelligence — FastAPI app entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.health import system_router, ci_router

app = FastAPI(
    title="Markar Intelligence",
    description="AI-powered codebase understanding platform",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(system_router)
app.include_router(ci_router)