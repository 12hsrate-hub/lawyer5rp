from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[3]
DEFAULT_SQLITE_PATH = ROOT_DIR / "web" / "data" / "app.db"


@dataclass(frozen=True)
class DatabaseConfig:
    backend: str
    database_url: str
    sqlite_path: Path | None
    postgres_pool_min_size: int = 1
    postgres_pool_max_size: int = 5


def load_database_config() -> DatabaseConfig:
    backend = os.getenv("OGP_DB_BACKEND", "postgres").strip().lower() or "postgres"
    database_url = os.getenv("DATABASE_URL", "").strip()
    pool_min = int(os.getenv("OGP_POSTGRES_POOL_MIN", "1") or "1")
    pool_max = int(os.getenv("OGP_POSTGRES_POOL_MAX", "5") or "5")

    if backend == "postgres":
        if not database_url:
            raise ValueError("DATABASE_URL is required when OGP_DB_BACKEND=postgres.")
        return DatabaseConfig(
            backend="postgres",
            database_url=database_url,
            sqlite_path=None,
            postgres_pool_min_size=max(1, pool_min),
            postgres_pool_max_size=max(1, pool_max),
        )

    sqlite_path = Path(os.getenv("OGP_SQLITE_PATH", str(DEFAULT_SQLITE_PATH))).expanduser()
    return DatabaseConfig(
        backend="sqlite",
        database_url=f"sqlite:///{sqlite_path}",
        sqlite_path=sqlite_path,
        postgres_pool_min_size=max(1, pool_min),
        postgres_pool_max_size=max(1, pool_max),
    )
