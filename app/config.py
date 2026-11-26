"""Application configuration via environment variables.

Development defaults use a local SQLite database and the filesystem storage
backend. The podman-compose stack overrides DATABASE_URL to point at
PostgreSQL (see docker-compose.yml).
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LEGALGIT_", env_file=".env")

    database_url: str = f"sqlite:///{REPO_ROOT / 'var' / 'dev.db'}"

    # Object-storage abstraction root (local filesystem backend in dev).
    storage_dir: Path = REPO_ROOT / "var" / "storage"

    # Raw upstream artifacts are retained under storage_dir/raw.
    raw_prefix: str = "raw"

    api_title: str = "Legal Git API"
    api_version: str = "1.0.0"

    log_level: str = "INFO"




settings = Settings()
