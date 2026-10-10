"""RFC 7807 problem+json error envelopes."""

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger(__name__)

PROBLEM_JSON = "application/problem+json"
TYPE_BASE = "https://invoicelens.dev/problems/"


class AppError(Exception):
    """Domain error rendered as problem+json."""

    def __init__(
        self,
        status: int,
        detail: str,
        *,
        code: str | None = None,
        title: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.code = code or HTTPStatus(status).phrase.lower().replace(" ", "-")
        self.title = title or HTTPStatus(status).phrase
        self.extra = extra or {}


class NotFoundError(AppError):
    def __init__(self, what: str, ident: object) -> None:
        super().__init__(404, f"{what} {ident} was not found", code="not-found")


def problem(
    request: Request,
    status: int,
    title: str,
    detail: str,
    code: str,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": TYPE_BASE + code,
        "title": title,
        "status": status,
        "detail": detail,
        "instance": request.url.path,
        **(extra or {}),
    }
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return problem(request, exc.status, exc.title, exc.detail, exc.code, exc.extra)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        phrase = HTTPStatus(exc.status_code).phrase
        return problem(
            request,
            exc.status_code,
            phrase,
            str(exc.detail),
            phrase.lower().replace(" ", "-"),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"loc": [str(p) for p in err["loc"]], "msg": err["msg"], "type": err["type"]}
            for err in exc.errors()
        ]
        return problem(
            request,
            422,
            "Unprocessable Content",
            "Request validation failed",
            "validation-error",
            {"errors": errors},
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error", extra={"path": request.url.path})
        return problem(
            request, 500, "Internal Server Error", "An unexpected error occurred", "internal"
        )
