from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class DatabaseConfig:
    backend: str
    database_url: str
    postgres_pool_min_size: int = 1
    postgres_pool_max_size: int = 5


def load_database_config() -> DatabaseConfig:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise ValueError("DATABASE_URL is required for PostgreSQL runtime.")

    pool_min = int(os.getenv("OGP_POSTGRES_POOL_MIN", "1") or "1")
    pool_max = int(os.getenv("OGP_POSTGRES_POOL_MAX", "5") or "5")
    return DatabaseConfig(
        backend="postgres",
        database_url=database_url,
        postgres_pool_min_size=max(1, pool_min),
        postgres_pool_max_size=max(1, pool_max),
    )
