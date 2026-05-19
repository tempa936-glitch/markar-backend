"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings
from pathlib import Path
from typing import Optional


class Settings(BaseSettings):
    app_name: str = "MarkarServer"
    app_version: str = "1.0.0"
    debug: bool = False

    # Code Intelligence
    default_graph_storage_path: str = ".code_graph"
    default_repo_path: str = str(Path.cwd())

    # CORS
    allowed_origins: list[str] = ["*"]

    # GitHub OAuth (set these in your .env or environment)
    github_client_id: Optional[str] = None
    github_client_secret: Optional[str] = None

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
