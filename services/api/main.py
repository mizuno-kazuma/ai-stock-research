"""FastAPI エントリポイント（docs/09-api-spec.md）。

    uv run uvicorn services.api.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.middleware.base import BaseHTTPMiddleware

from packages.core.config import Settings, get_settings
from packages.core.storage import DuckDBRepo, SQLiteRepo, should_load_seed_payload
from packages.schemas.common import Envelope
from packages.schemas.system import LivenessResponse
from services.api.deps import AppState, User, get_app_state, require_user
from services.api.envelope import wrap
from services.api.errors import (
    ApiError,
    api_error_handler,
    pydantic_handler,
    validation_handler,
)
from services.api.events import EventBus
from services.api.routers import agent, dashboard, documents, fx, models, portfolio, recommendations, screener, stocks, system
from services.api.util import utc_now

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response


def _open_duck(settings: Settings) -> DuckDBRepo:
    repo = DuckDBRepo.open(settings, read_only=False)
    repo.init_db()
    return repo


def _load_payload(sqlite: SQLiteRepo) -> dict:
    if not should_load_seed_payload(sqlite):
        return {}
    try:
        from services.api.seed import load_sample

        return load_sample()
    except Exception:
        logger.exception("シード JSON の読み込みに失敗しました")
        return {}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    injected: AppState | None = getattr(app.state, "api", None)
    if injected is not None:
        yield
        return
    settings = get_settings()
    settings.ensure_directories()
    duck = _open_duck(settings)
    sqlite = SQLiteRepo.open(settings)
    sqlite.init_db()
    sqlite.mark_interrupted_jobs(hours=0)
    payload = _load_payload(sqlite)
    bus = EventBus()
    from services.agent.progress import set_shared_bus

    set_shared_bus(bus)
    app.state.api = AppState(
        settings=settings,
        duck=duck,
        sqlite=sqlite,
        bus=bus,
        started_at=utc_now(),
        payload=payload,
        duck_owned=True,
        sqlite_owned=True,
    )
    scheduler = _start_agent_scheduler(settings, duck, sqlite)
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)
    if duck:
        duck.close()
    sqlite.close()


def _start_agent_scheduler(settings: Settings, duck: DuckDBRepo, sqlite: SQLiteRepo) -> Any:
    """DuckDB は単一ライタのため、収集ジョブは API と同じプロセスで動かす。"""
    from services.agent.main import create_scheduler, set_shared_storage

    set_shared_storage(duck, sqlite)
    url = settings.database_url or f"sqlite:///{settings.state_db_path}"
    url = url.replace("sqlite+aiosqlite://", "sqlite://")
    scheduler = create_scheduler(db_url=url, timezone=settings.tz, blocking=False)
    scheduler.start()
    logger.info("embedded agent scheduler started (tz=%s)", settings.tz)
    return scheduler


def create_app(
    *,
    settings: Settings | None = None,
    duck: DuckDBRepo | None = None,
    sqlite: SQLiteRepo | None = None,
    payload: dict | None = None,
) -> FastAPI:
    app = FastAPI(
        title="AI Stock Research API",
        version="0.1.0",
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        redoc_url="/api/v1/redoc",
        lifespan=lifespan,
    )
    cfg = settings or get_settings()
    origins = list(cfg.cors_origin_list)
    if "http://localhost:3000" not in origins:
        origins.append("http://localhost:3000")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_origin_regex=r"https?://.*\.ts\.net(:\d+)?",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_handler)
    app.add_exception_handler(ValidationError, pydantic_handler)

    prefix = "/api/v1"
    for mod in (
        dashboard,
        recommendations,
        screener,
        stocks,
        documents,
        fx,
        models,
        agent,
        portfolio,
        system,
    ):
        app.include_router(mod.router, prefix=prefix)

    @app.get("/health", response_model=LivenessResponse, tags=["system"])
    def health() -> LivenessResponse:
        return LivenessResponse(
            status="ok",
            app_version=cfg.app_version,
            checked_at=utc_now(),
        )

    @app.get("/api/v1/health", response_model=Envelope[LivenessResponse], tags=["system"])
    def health_v1(
        _user: User = Depends(require_user),
        state: AppState = Depends(get_app_state),
    ) -> Envelope[LivenessResponse]:
        return wrap(
            state,
            LivenessResponse(status="ok", app_version=cfg.app_version, checked_at=utc_now()),
        )

    if duck is not None and sqlite is not None:
        bus = EventBus()
        from services.agent.progress import set_shared_bus

        set_shared_bus(bus)
        app.state.api = AppState(
            settings=cfg,
            duck=duck,
            sqlite=sqlite,
            bus=bus,
            started_at=utc_now(),
            payload=payload if payload is not None else _load_payload(sqlite),
            duck_owned=False,
            sqlite_owned=False,
        )
    return app


app = create_app()
