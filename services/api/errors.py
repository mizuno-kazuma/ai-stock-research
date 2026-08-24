"""RFC 7807 Problem Details（docs/09-api-spec.md §1.1）。"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from packages.schemas.common import ProblemDetails
from packages.schemas.enums import ProblemType

PROBLEM_BASE = "https://example.invalid/problems"


class ApiError(Exception):
    def __init__(
        self,
        *,
        problem_type: ProblemType,
        title: str,
        status: int,
        detail: str | None = None,
        instance: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.problem_type = problem_type
        self.title = title
        self.status = status
        self.detail = detail
        self.instance = instance
        self.extra = extra or {}
        super().__init__(detail or title)

    def to_problem(self, instance: str | None = None) -> ProblemDetails:
        return ProblemDetails(
            type=f"{PROBLEM_BASE}/{self.problem_type}",
            title=self.title,
            status=self.status,
            detail=self.detail,
            instance=instance or self.instance,
            **self.extra,
        )


def not_found(detail: str, *, instance: str | None = None) -> ApiError:
    return ApiError(
        problem_type=ProblemType.NOT_FOUND,
        title="見つかりません",
        status=404,
        detail=detail,
        instance=instance,
    )


def data_not_ready(
    detail: str,
    *,
    latest_available_as_of: dt.date | None = None,
    instance: str | None = None,
) -> ApiError:
    extra: dict[str, Any] = {}
    if latest_available_as_of is not None:
        extra["latest_available_as_of"] = latest_available_as_of
    return ApiError(
        problem_type=ProblemType.DATA_NOT_READY,
        title="データが未生成です",
        status=409,
        detail=detail,
        instance=instance,
        extra=extra,
    )


def cost_cap_exceeded(
    *,
    spent_today_usd: float,
    daily_cap_usd: float,
    resets_at: dt.datetime,
    instance: str | None = None,
) -> ApiError:
    return ApiError(
        problem_type=ProblemType.COST_CAP_EXCEEDED,
        title="LLM予算の上限に達しています",
        status=429,
        detail=(
            f"本日の使用額 ${spent_today_usd:.2f} が上限 ${daily_cap_usd:.2f} に達しました。"
            "設定から上限を変更できます。"
        ),
        instance=instance,
        extra={
            "spent_today_usd": spent_today_usd,
            "daily_cap_usd": daily_cap_usd,
            "resets_at": resets_at,
        },
    )


def upstream_unavailable(detail: str, *, instance: str | None = None) -> ApiError:
    return ApiError(
        problem_type=ProblemType.UPSTREAM_UNAVAILABLE,
        title="上流サービスが応答しません",
        status=503,
        detail=detail,
        instance=instance,
    )


def validation_error(detail: str, *, errors: list[dict[str, Any]] | None = None) -> ApiError:
    extra: dict[str, Any] = {}
    if errors:
        extra["errors"] = errors
    return ApiError(
        problem_type=ProblemType.VALIDATION_ERROR,
        title="パラメータが不正です",
        status=422,
        detail=detail,
        extra=extra,
    )


def _problem_response(problem: ProblemDetails) -> JSONResponse:
    payload = problem.model_dump(mode="json", exclude_none=True)
    return JSONResponse(
        status_code=problem.status,
        content=payload,
        media_type="application/problem+json",
    )


async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    return _problem_response(exc.to_problem(instance=str(_request.url.path)))


async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = []
    for err in exc.errors():
        errors.append(
            {
                "loc": list(err.get("loc", ())),
                "msg": err.get("msg"),
                "type": err.get("type"),
            }
        )
    problem = ProblemDetails(
        type=f"{PROBLEM_BASE}/{ProblemType.VALIDATION_ERROR}",
        title="パラメータが不正です",
        status=422,
        detail="リクエストの検証に失敗しました。",
        instance=str(request.url.path),
        errors=errors,
    )
    return _problem_response(problem)


async def pydantic_handler(request: Request, exc: ValidationError) -> JSONResponse:
    problem = ProblemDetails(
        type=f"{PROBLEM_BASE}/{ProblemType.VALIDATION_ERROR}",
        title="パラメータが不正です",
        status=422,
        detail=str(exc),
        instance=str(request.url.path),
    )
    return _problem_response(problem)


async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    problem = ProblemDetails(
        type=f"{PROBLEM_BASE}/{ProblemType.INTERNAL_ERROR}",
        title="内部エラー",
        status=500,
        detail=str(exc) or "予期しないエラーが発生しました。",
        instance=str(request.url.path),
    )
    return _problem_response(problem)
