"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    app_name: str = "MarkarServer"
    app_version: str = "1.0.0"
    debug: bool = False

    # Code Intelligence
    default_graph_storage_path: str = ".code_graph"
    default_repo_path: str = str(Path.cwd())

    # CORS
    allowed_origins: list[str] = ["*"]

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
