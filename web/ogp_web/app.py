from __future__ import annotations

import atexit
import logging
import os
import socket
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from urllib.parse import urlparse

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from ogp_web.env import load_web_env

load_web_env()

from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from ogp_web.rate_limit import create_rate_limiter
from ogp_web.routes.admin import router as admin_router
from ogp_web.routes.auth import router as auth_router
from ogp_web.routes.complaint import router as complaint_router
from ogp_web.routes.exam_import import router as exam_import_router
from ogp_web.routes.pages import router as pages_router
from ogp_web.routes.profile import router as profile_router
from ogp_web.server_config import get_server_config
from ogp_web.services.auth_service import _get_secret_key, get_current_user, is_admin_user
from ogp_web.services.exam_import_tasks import ExamImportTaskRegistry
from ogp_web.storage.admin_metrics_store import AdminMetricsStore, get_default_admin_metrics_store
from ogp_web.storage.exam_answers_store import ExamAnswersStore, get_default_exam_answers_store
from ogp_web.storage.user_store import UserStore, get_default_user_store
from ogp_web.web import STATIC_DIR, _normalized_url


LOGS_DIR = ROOT_DIR / "web" / "data" / "logs"
LOG_PATH = LOGS_DIR / "ogp_web.log"
EXAM_IMPORT_TASKS_DB_PATH = ROOT_DIR / "web" / "data" / "exam_import_tasks.db"


def _allowed_csrf_origins() -> frozenset[str]:
    configured_origins = [
        os.getenv("OGP_WEB_BASE_URL", "https://www.lawyer5rp.online"),
        os.getenv("OGP_WEB_ALTERNATE_BASE_URL", "https://www.lawyer5rp.su"),
    ]
    configured_origins.extend(os.getenv("OGP_WEB_ALLOWED_ORIGINS", "").split(","))
    return frozenset(
        normalized
        for normalized in (_normalized_url(origin) for origin in configured_origins)
        if normalized
    )


def _request_origin_candidates(request) -> frozenset[str]:
    forwarded_proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip()
    forwarded_host = (request.headers.get("x-forwarded-host") or "").split(",")[0].strip()
    host = (request.headers.get("host") or "").split(",")[0].strip()
    candidates = {_normalized_url(str(request.base_url).rstrip("/"))}
    if forwarded_proto and forwarded_host:
        candidates.add(_normalized_url(f"{forwarded_proto}://{forwarded_host}"))
    elif forwarded_proto and host:
        candidates.add(_normalized_url(f"{forwarded_proto}://{host}"))
    return frozenset(filter(None, candidates))


def _configure_web_logging() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    root_logger = logging.getLogger()
    formatter = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")

    if not any(getattr(handler, "name", "") == "ogp_web_file" for handler in root_logger.handlers):
        file_handler = TimedRotatingFileHandler(
            LOG_PATH,
            when="midnight",
            interval=1,
            backupCount=int(os.getenv("OGP_WEB_LOG_BACKUP_DAYS", "30") or "30"),
            encoding="utf-8",
            utc=True,
        )
        file_handler.set_name("ogp_web_file")
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    if not any(getattr(handler, "name", "") == "ogp_web_stderr" for handler in root_logger.handlers):
        stream_handler = logging.StreamHandler()
        stream_handler.set_name("ogp_web_stderr")
        stream_handler.setFormatter(formatter)
        root_logger.addHandler(stream_handler)

    if root_logger.level == logging.NOTSET or root_logger.level > logging.INFO:
        root_logger.setLevel(logging.INFO)


def _check_tcp_dependency(name: str, host: str, port: int, *, timeout: float = 3.0) -> dict[str, object]:
    details: dict[str, object] = {
        "dependency": name,
        "host": host,
        "port": port,
        "ok": False,
    }
    if not host or port <= 0:
        details["error"] = "missing_config"
        return details
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
    except OSError as exc:
        details["error"] = str(exc)
        return details
    details["ok"] = True
    return details


def _check_smtp_health() -> dict[str, object]:
    host = os.getenv("SMTP_HOST", "").strip()
    port = int(os.getenv("SMTP_PORT", "587") or "587")
    username = os.getenv("SMTP_USERNAME", "").strip()
    sender = os.getenv("SMTP_FROM_EMAIL", "").strip()
    if not host and not username and not sender:
        return {
            "dependency": "smtp",
            "host": "",
            "port": port,
            "configured": False,
            "ok": True,
            "skipped": True,
        }
    details = _check_tcp_dependency("smtp", host, port)
    details["configured"] = bool(host and (sender or username))
    if not details["configured"] and details.get("ok"):
        details["ok"] = False
        details["error"] = "missing_sender_or_credentials"
    return details


def _check_openai_health() -> dict[str, object]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    proxy_url = os.getenv("OPENAI_PROXY_URL", "").strip()
    if not api_key and not proxy_url:
        return {
            "dependency": "openai",
            "configured": False,
            "ok": True,
            "skipped": True,
            "target": proxy_url or "https://api.openai.com",
        }
    target_url = proxy_url or "https://api.openai.com"
    parsed = urlparse(target_url)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    details = _check_tcp_dependency("openai", host, port)
    details["configured"] = bool(api_key)
    details["target"] = f"{parsed.scheme or 'https'}://{host}:{port}" if host else target_url
    if not api_key:
        details["ok"] = False
        details["error"] = "missing_api_key"
    return details


def _ensure_utf8_charset(content_type: str) -> str:
    normalized = (content_type or "").strip()
    if not normalized:
        return normalized
    base = normalized.split(";", 1)[0].strip().lower()
    if "charset=" in normalized.lower():
        return normalized
    if base.startswith("text/") or base in {"application/json", "application/javascript", "application/xml"}:
        return f"{normalized}; charset=utf-8"
    return normalized


def _close_app_resources(app: FastAPI) -> None:
    if getattr(app.state, "_resources_closed", False):
        return
    user_store = getattr(app.state, "user_store", None)
    user_repository = getattr(user_store, "repository", None)
    if user_repository is not None:
        user_repository.close()
    rate_limiter = getattr(app.state, "rate_limiter", None)
    rate_limiter_repository = getattr(rate_limiter, "repository", None)
    if rate_limiter_repository is not None:
        rate_limiter_repository.close()
    app.state._resources_closed = True


def create_app(
    user_store: UserStore | None = None,
    exam_answers_store: ExamAnswersStore | None = None,
    admin_metrics_store: AdminMetricsStore | None = None,
) -> FastAPI:
    _configure_web_logging()
    _get_secret_key()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        _close_app_resources(app)

    app = FastAPI(title="OGP Builder Web", version="1.3.0", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.state.user_store = user_store or get_default_user_store()
    app.state.exam_answers_store = exam_answers_store or get_default_exam_answers_store()
    app.state.admin_metrics_store = admin_metrics_store or get_default_admin_metrics_store()
    app.state.rate_limiter = create_rate_limiter(app.state.user_store.backend)
    exam_import_tasks_db_path = (
        admin_metrics_store.db_path.parent / "exam_import_tasks.db"
        if admin_metrics_store is not None
        else EXAM_IMPORT_TASKS_DB_PATH
    )
    exam_import_tasks_backend = None
    if getattr(app.state.admin_metrics_store, "is_postgres_backend", False):
        exam_import_tasks_backend = app.state.admin_metrics_store.backend
    app.state.exam_import_task_registry = ExamImportTaskRegistry(
        exam_import_tasks_db_path,
        backend=exam_import_tasks_backend,
    )
    app.state.server_config = get_server_config(os.getenv("OGP_DEFAULT_SERVER_CODE", "blackberry"))

    @app.middleware("http")
    async def attach_request_id(request, call_next):
        request_id = (request.headers.get("x-request-id") or "").strip() or uuid.uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    _allowed_origins = _allowed_csrf_origins()
    _unsafe_methods = frozenset({"POST", "PUT", "DELETE", "PATCH"})

    @app.middleware("http")
    async def csrf_origin_check(request, call_next):
        if request.method in _unsafe_methods:
            origin = request.headers.get("origin", "").strip().rstrip("/")
            request_origins = _request_origin_candidates(request)
            if origin and origin not in _allowed_origins and origin not in request_origins:
                logging.getLogger(__name__).warning(
                    "Rejected request by Origin check: origin=%s request_origins=%s host=%s path=%s",
                    origin,
                    sorted(request_origins),
                    request.headers.get("host", ""),
                    request.url.path,
                )
                return Response(
                    content='{"detail":"Запрос отклонён: недопустимый Origin."}',
                    status_code=403,
                    media_type="application/json",
                )
        return await call_next(request)

    @app.middleware("http")
    async def add_security_headers(request, call_next):
        response = await call_next(request)
        normalized_content_type = _ensure_utf8_charset(response.headers.get("content-type", ""))
        if normalized_content_type:
            response.headers["Content-Type"] = normalized_content_type
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self' https:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        forwarded_proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
        if request.url.scheme == "https" or forwarded_proto == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        request_id = getattr(request.state, "request_id", "")
        if request_id:
            response.headers["X-Request-ID"] = request_id
        return response

    @app.middleware("http")
    async def capture_admin_metrics(request, call_next):
        started = time.perf_counter()
        request_id = getattr(request.state, "request_id", "")
        user = get_current_user(request) if request.url.path.startswith("/api/") else None
        if request.url.path.startswith("/api/") and user and not request.url.path.startswith("/api/auth/"):
            policy_name = "user_quota_daily"
            if request.url.path.startswith("/api/admin/") and is_admin_user(user.username):
                policy_name = "admin_quota_daily"
                try:
                    quota_daily = int(os.getenv("OGP_WEB_ADMIN_API_QUOTA_DAILY", "0") or "0")
                except Exception:
                    quota_daily = 0
            else:
                try:
                    quota_daily = app.state.user_store.get_api_quota_daily(user.username)
                except Exception:
                    quota_daily = 0
            if quota_daily > 0:
                used_last_24h = app.state.admin_metrics_store.count_user_api_requests_last_24h(user.username)
                if used_last_24h >= quota_daily:
                    response = JSONResponse(
                        status_code=429,
                        content={
                            "detail": [
                                "Дневная квота API исчерпана. Обратитесь к администратору.",
                            ]
                        },
                    )
                    app.state.admin_metrics_store.log_event(
                        event_type="api_request",
                        username=user.username,
                        server_code=user.server_code,
                        path=request.url.path,
                        method=request.method,
                        status_code=429,
                        duration_ms=0,
                        request_bytes=int(request.headers.get("content-length") or 0),
                        response_bytes=len(response.body or b""),
                        meta={
                            "quota_daily": quota_daily,
                            "used_last_24h": used_last_24h,
                            "request_id": request_id,
                            "username": user.username,
                            "policy_name": policy_name,
                        },
                    )
                    return response
        try:
            response = await call_next(request)
        except Exception as exc:
            logging.getLogger(__name__).exception("Unhandled request error: %s %s", request.method, request.url.path)
            if request.url.path.startswith("/api/"):
                user = user or get_current_user(request)
                request_bytes = int(request.headers.get("content-length") or 0)
                duration_ms = int((time.perf_counter() - started) * 1000)
                app.state.admin_metrics_store.log_event(
                    event_type="api_exception",
                    username=user.username if user else "",
                    server_code=user.server_code if user else "",
                    path=request.url.path,
                    method=request.method,
                    status_code=500,
                    duration_ms=duration_ms,
                    request_bytes=request_bytes,
                    response_bytes=0,
                    meta={
                        "request_id": request_id,
                        "error_type": exc.__class__.__name__,
                        "error_message": str(exc),
                    },
                )
            raise
        if request.url.path.startswith("/api/"):
            user = user or get_current_user(request)
            request_bytes = int(request.headers.get("content-length") or 0)
            response_bytes = int(response.headers.get("content-length") or 0)
            duration_ms = int((time.perf_counter() - started) * 1000)
            app.state.admin_metrics_store.log_event(
                event_type="api_request",
                username=user.username if user else "",
                server_code=user.server_code if user else "",
                path=request.url.path,
                method=request.method,
                status_code=response.status_code,
                duration_ms=duration_ms,
                request_bytes=request_bytes,
                response_bytes=response_bytes,
                meta={"request_id": request_id},
            )
        return response

    @app.get("/health")
    async def health() -> JSONResponse:
        checks = {
            "user_store": app.state.user_store.healthcheck(),
            "exam_answers_store": app.state.exam_answers_store.healthcheck(),
            "admin_metrics_store": app.state.admin_metrics_store.healthcheck(),
            "exam_import_tasks_store": app.state.exam_import_task_registry.healthcheck(),
            "rate_limiter": app.state.rate_limiter.healthcheck(),
            "smtp": _check_smtp_health(),
            "openai": _check_openai_health(),
        }
        required_checks = (
            "user_store",
            "exam_answers_store",
            "admin_metrics_store",
            "exam_import_tasks_store",
            "rate_limiter",
        )
        overall_ok = all(bool(checks[name].get("ok")) for name in required_checks)
        active_backend = str(checks["user_store"].get("backend") or "unknown")
        return JSONResponse(
            status_code=200 if overall_ok else 503,
            content={
                "status": "ok" if overall_ok else "degraded",
                "version": app.version,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "database_backend": active_backend,
                "checks": checks,
            },
        )

    app.include_router(pages_router)
    app.include_router(auth_router)
    app.include_router(profile_router)
    app.include_router(complaint_router)
    app.include_router(exam_import_router)
    app.include_router(admin_router)
    return app


app = create_app()
atexit.register(_close_app_resources, app)
