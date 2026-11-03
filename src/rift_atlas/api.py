"""DPS HTTP boundary. Start with uvicorn rift_atlas.api:app --workers 1."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from importlib.resources import files
from time import perf_counter
from typing import Annotated, Callable

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from rift_atlas.dataset import Dataset, Settings, load_dataset

log = logging.getLogger("uvicorn.error")
Label = Annotated[str, Query(min_length=1, max_length=128)]
OptionalLabel = Annotated[str | None, Query(max_length=128)]


def create_app(settings: Settings | None = None, *, loader: Callable[[Settings], Dataset] = load_dataset) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        started = perf_counter()
        try:
            app.state.dataset = loader(settings or Settings.from_env())
        except Exception:
            log.exception("DPS startup failed: supply a validated canonical snapshot and manifest")
            raise
        dataset = app.state.dataset
        log.info("DPS ready revision=%s dataset=%s games=%s load_seconds=%.3f",
                 os.environ.get("RENDER_GIT_COMMIT", "local"), dataset.metadata["dataset_id"],
                 dataset.index.dataset_context["games_loaded"], perf_counter() - started)
        try:
            yield
        finally:
            app.state.dataset = None

    app = FastAPI(title="DPS — Draft Positioning System", version="1", lifespan=lifespan,
                  responses={400: {"description": "Invalid query; JSON error string"},
                             500: {"description": "Unexpected failure; generic JSON error"},
                             503: {"description": "Dataset not ready"}})
    app.state.dataset = None

    def openapi():
        if app.openapi_schema is None:
            schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
            for path in schema["paths"].values():
                for operation in path.values():
                    operation.get("responses", {}).pop("422", None)
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = openapi

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        return JSONResponse({"error": "Invalid query parameters; see /docs for bounds and types."}, status_code=400)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, error):
        return JSONResponse({"error": error.detail}, status_code=error.status_code)

    @app.exception_handler(Exception)
    async def unexpected_error(request, error):
        log.error("DPS request failed", exc_info=(type(error), error, error.__traceback__))
        return JSONResponse({"error": "Internal server error"}, status_code=500)

    @app.middleware("http")
    async def bounded_query(request: Request, call_next):
        if len(request.scope.get("query_string", b"")) > 8192:
            return JSONResponse({"error": "Query is too long"}, status_code=400)
        started = perf_counter()
        try:
            return await call_next(request)
        finally:
            # Do not log query strings or dataset contents.
            log.info("DPS request method=%s seconds=%.4f", request.method, perf_counter() - started)

    def current() -> Dataset:
        if app.state.dataset is None:
            raise HTTPException(503, "Dataset is not ready")
        return app.state.dataset

    def parameters(request: Request, allowed: set[str], repeated: set[str] = frozenset()):
        for key in request.query_params:
            if key not in allowed:
                raise HTTPException(400, f"Unsupported query parameter: {key}")
            if key not in repeated and len(request.query_params.getlist(key)) != 1:
                raise HTTPException(400, f"Query parameter must occur once: {key}")

    @app.get("/healthz")
    def health():
        return {"status": "ready", "dataset_id": current().metadata["dataset_id"]}

    @app.get("/api/v1/dataset")
    def dataset():
        return current().metadata

    @app.get("/api/v1/champions")
    def champions(request: Request, q: Annotated[str, Query(max_length=128)] = "",
                  limit: Annotated[int, Query(ge=0, le=100)] = 20):
        parameters(request, {"q", "limit"})
        snapshot = current()
        return {"api_version": "1", "dataset_id": snapshot.metadata["dataset_id"],
                "champions": snapshot.index.search(q, limit=limit)}

    @app.get("/api/v1/relationships")
    def relationships(
        request: Request, champion: Label,
        pinned: Annotated[list[str] | None, Query(max_length=4)] = None,
        mode: Annotated[str, Query(max_length=32)] = "established",
        limit: Annotated[int, Query(ge=0, le=50)] = 12,
        minimum_support: Annotated[int, Query(ge=1, le=100_000)] = 1,
        patch: OptionalLabel = None, patch_from: OptionalLabel = None, patch_to: OptionalLabel = None,
        league: Annotated[list[str] | None, Query(max_length=100)] = None,
        hide_role_infeasible: bool = False,
        relationship: Annotated[str, Query(max_length=32)] = "co_pick",
    ):
        parameters(request, {"champion", "pinned", "mode", "limit", "minimum_support", "patch", "patch_from", "patch_to", "league", "hide_role_infeasible", "relationship"}, {"pinned", "league"})
        if relationship != "co_pick":
            raise HTTPException(400, "Only co_pick relationships are queryable")
        if any(len(value) > 128 for value in (pinned or []) + (league or [])):
            raise HTTPException(400, "Champion and league labels must be at most 128 characters")
        snapshot = current()
        try:
            result = snapshot.index.graph(champion, pinned=pinned, mode=mode, limit=limit,
                minimum_support=minimum_support, patch=patch, patch_from=patch_from, patch_to=patch_to,
                leagues=[value for value in league if value] if league is not None else None,
                hide_role_infeasible=hide_role_infeasible)
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
        return {**result, "api_version": "1", "dataset_id": snapshot.metadata["dataset_id"]}

    @app.get("/", include_in_schema=False)
    def index():
        return asset("index.html", "text/html")

    @app.get("/app.js", include_in_schema=False)
    def javascript():
        return asset("app.js", "text/javascript")

    @app.get("/styles.css", include_in_schema=False)
    def stylesheet():
        return asset("styles.css", "text/css")

    def asset(name: str, media_type: str):
        return Response(files("rift_atlas.web").joinpath(name).read_bytes(), media_type=media_type)

    return app


app = create_app()
