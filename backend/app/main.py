"""FastAPI application factory. Run with ``uvicorn --factory app.main:create_app``."""

import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from app.api.routes import documents, exports, meta, webhooks
from app.api.schemas import HealthOut
from app.core.config import Settings, get_settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.core.security import require_api_key
from app.services.container import Services, build_services

VERSION = "0.1.0"
log = logging.getLogger("app.http")


def _operation_id(route: APIRoute) -> str:
    return route.name


def create_app(settings: Settings | None = None, services: Services | None = None) -> FastAPI:
    settings = settings or (services.settings if services else get_settings())
    configure_logging(settings.log_level, settings.log_json)
    services = services or build_services(settings)

    app = FastAPI(
        title=f"{settings.app_name} API",
        version=VERSION,
        description="AI invoice extraction: upload, review, approve, export.",
        generate_unique_id_function=_operation_id,
    )
    app.state.services = services
    install_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],
    )

    @app.middleware("http")
    async def access_log(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        log.info(
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return response

    def health() -> HealthOut:
        return HealthOut(status="ok", provider=services.provider.name, version=VERSION)

    app.add_api_route("/health", health, methods=["GET"], tags=["meta"], name="health")

    api = APIRouter(prefix="/api/v1", dependencies=[Depends(require_api_key)])
    api.add_api_route("/health", health, methods=["GET"], tags=["meta"], name="api_health")
    api.include_router(documents.router)
    api.include_router(meta.router)
    api.include_router(exports.router)
    api.include_router(webhooks.router)
    app.include_router(api)
    return app
