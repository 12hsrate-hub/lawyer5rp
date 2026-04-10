from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque

from ogp_web.db.factory import get_database_backend
from ogp_web.db.types import DatabaseBackend
from ogp_web.storage.user_repository import UserRepository


LOGGER = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    pass


class InMemoryRateLimiter:
    """In-memory sliding window limiter used as a last-resort fallback."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._windows: dict[str, deque[float]] = defaultdict(deque)

    def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> bool:
        now = time.monotonic()
        cutoff = now - window_seconds

        with self._lock:
            dq = self._windows[key]
            while dq and dq[0] < cutoff:
                dq.popleft()

            if len(dq) >= max_requests:
                return False

            dq.append(now)
            return True

    def check(self, key: str, max_requests: int, window_seconds: int) -> None:
        if not self.is_allowed(key, max_requests, window_seconds):
            raise RateLimitExceeded(
                f"РЎР»РёС€РєРѕРј РјРЅРѕРіРѕ Р·Р°РїСЂРѕСЃРѕРІ. РџРѕРїСЂРѕР±СѓР№С‚Рµ СЃРЅРѕРІР° С‡РµСЂРµР· {window_seconds} СЃРµРєСѓРЅРґ."
            )

    def reset(self) -> None:
        with self._lock:
            self._windows.clear()


class PersistentRateLimiter:
    """Database-backed limiter that works across processes sharing one DB."""

    def __init__(self, backend: DatabaseBackend):
        self.backend = backend
        self.repository = UserRepository(backend)
        self._fallback = InMemoryRateLimiter()
        self._ensure_schema()

    @property
    def is_postgres_backend(self) -> bool:
        return self.backend.__class__.__name__ == "PostgresBackend"

    def _ensure_schema(self) -> None:
        conn = self.repository.connect()
        try:
            if self.is_postgres_backend:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS auth_rate_limit_events (
                        action TEXT NOT NULL,
                        subject_key TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_auth_rate_limit_lookup
                    ON auth_rate_limit_events (action, subject_key, created_at)
                    """
                )
            else:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS auth_rate_limit_events (
                        action TEXT NOT NULL,
                        subject_key TEXT NOT NULL,
                        created_at REAL NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_auth_rate_limit_lookup
                    ON auth_rate_limit_events (action, subject_key, created_at)
                    """
                )
            conn.commit()
        except Exception as exc:
            try:
                conn.rollback()
            except Exception:
                pass
            LOGGER.warning("Rate limit storage init failed, using in-memory fallback: %s", exc)

    def healthcheck(self) -> dict[str, object]:
        details = self.backend.healthcheck()
        details = dict(details)
        details["component"] = "rate_limiter"
        if details.get("ok"):
            details["storage"] = "database"
            return details
        details["storage"] = "in-memory-fallback"
        return details

    def reset(self) -> None:
        self._fallback.reset()
        conn = self.repository.connect()
        try:
            conn.execute("DELETE FROM auth_rate_limit_events")
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass

    def check(self, key: str, max_requests: int, window_seconds: int, *, action: str) -> None:
        try:
            self._check_persistent(key, max_requests, window_seconds, action=action)
        except RateLimitExceeded:
            raise
        except Exception as exc:
            LOGGER.warning("Rate limit storage unavailable, using in-memory fallback: %s", exc)
            self._fallback.check(f"{action}:{key}", max_requests, window_seconds)

    def _check_persistent(self, key: str, max_requests: int, window_seconds: int, *, action: str) -> None:
        conn = self.repository.connect()
        try:
            if self.is_postgres_backend:
                conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"{action}:{key}",))
                conn.execute(
                    """
                    DELETE FROM auth_rate_limit_events
                    WHERE action = %s
                      AND subject_key = %s
                      AND created_at < NOW() - (%s * INTERVAL '1 second')
                    """,
                    (action, key, window_seconds),
                )
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS total
                    FROM auth_rate_limit_events
                    WHERE action = %s AND subject_key = %s
                    """,
                    (action, key),
                ).fetchone()
                total = int(row["total"] if row else 0)
                if total >= max_requests:
                    conn.rollback()
                    raise RateLimitExceeded(
                        f"РЎР»РёС€РєРѕРј РјРЅРѕРіРѕ Р·Р°РїСЂРѕСЃРѕРІ. РџРѕРїСЂРѕР±СѓР№С‚Рµ СЃРЅРѕРІР° С‡РµСЂРµР· {window_seconds} СЃРµРєСѓРЅРґ."
                    )
                conn.execute(
                    """
                    INSERT INTO auth_rate_limit_events (action, subject_key)
                    VALUES (%s, %s)
                    """,
                    (action, key),
                )
                conn.commit()
                return

            now = time.time()
            cutoff = now - window_seconds
            conn.execute(
                """
                DELETE FROM auth_rate_limit_events
                WHERE action = ? AND subject_key = ? AND created_at < ?
                """,
                (action, key, cutoff),
            )
            row = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM auth_rate_limit_events
                WHERE action = ? AND subject_key = ?
                """,
                (action, key),
            ).fetchone()
            total = int(row["total"] if row else 0)
            if total >= max_requests:
                conn.rollback()
                raise RateLimitExceeded(
                    f"РЎР»РёС€РєРѕРј РјРЅРѕРіРѕ Р·Р°РїСЂРѕСЃРѕРІ. РџРѕРїСЂРѕР±СѓР№С‚Рµ СЃРЅРѕРІР° С‡РµСЂРµР· {window_seconds} СЃРµРєСѓРЅРґ."
                )
            conn.execute(
                """
                INSERT INTO auth_rate_limit_events (action, subject_key, created_at)
                VALUES (?, ?, ?)
                """,
                (action, key, now),
            )
            conn.commit()
        except RateLimitExceeded:
            raise
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise


_default_limiter: PersistentRateLimiter | None = None


def _get_default_limiter() -> PersistentRateLimiter:
    global _default_limiter
    if _default_limiter is None:
        _default_limiter = PersistentRateLimiter(get_database_backend())
    return _default_limiter


def create_rate_limiter(
    backend: DatabaseBackend | None = None,
) -> PersistentRateLimiter:
    if backend is not None:
        return PersistentRateLimiter(backend)
    return PersistentRateLimiter(get_database_backend())


def reset_for_testing(limiter: PersistentRateLimiter | None = None) -> None:
    target = limiter or _get_default_limiter()
    target.reset()


def auth_rate_limit(ip: str, action: str, limiter: PersistentRateLimiter | None = None) -> None:
    """
    Limits:
      login          вЂ” 10 attempts per 5 minutes
      register       вЂ” 5 attempts per 10 minutes
      forgot-password вЂ” 5 attempts per 10 minutes
    """
    limits = {
        "login": (10, 300),
        "register": (5, 600),
        "forgot-password": (5, 600),
    }
    max_req, window = limits.get(action, (20, 60))
    target = limiter or _get_default_limiter()
    target.check(ip, max_req, window, action=action)
