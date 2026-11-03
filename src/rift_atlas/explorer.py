from __future__ import annotations

import json
import threading
import webbrowser
from collections.abc import Iterable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from rift_atlas.model import DraftRecord
from rift_atlas.recommendation import RolePolicy


from rift_atlas.relationships import RelationshipIndex, TOP_REGION_LEAGUES


def _static_asset(name: str) -> bytes:
    return files("rift_atlas.web").joinpath(name).read_bytes()


def make_handler(index: RelationshipIndex) -> type[BaseHTTPRequestHandler]:
    class ExplorerHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            parsed = urlparse(self.path)
            try:
                if parsed.path in {"/api/champions", "/api/v1/champions"}:
                    query = parse_qs(parsed.query, keep_blank_values=True)
                    limit = _integer_parameter(query, "limit", 20, maximum=100)
                    self._json({"champions": index.search(query.get("q", [""])[0], limit=limit)})
                    return
                if parsed.path in {"/api/graph", "/api/v1/relationships"}:
                    query = parse_qs(parsed.query, keep_blank_values=True)
                    champion = query.get("champion", [""])[0]
                    if not champion:
                        self._json({"error": "champion is required"}, HTTPStatus.BAD_REQUEST)
                        return
                    limit = _integer_parameter(query, "limit", 12, maximum=50)
                    minimum_support = _integer_parameter(
                        query, "minimum_support", 1, minimum=1, maximum=100_000
                    )
                    mode = query.get("mode", [RelationshipIndex.DEFAULT_MODE])[0]
                    patch = query.get("patch", [None])[0]
                    patch_from = query.get("patch_from", [None])[0]
                    patch_to = query.get("patch_to", [None])[0]
                    leagues = query.get("league")
                    pinned = query.get("pinned")
                    hide_role_infeasible = _boolean_parameter(
                        query, "hide_role_infeasible", False
                    )
                    self._json(
                        index.graph(
                            champion,
                            pinned=pinned,
                            limit=limit,
                            mode=mode,
                            minimum_support=minimum_support,
                            patch=patch,
                            patch_from=patch_from,
                            patch_to=patch_to,
                            leagues=(
                                [value for value in leagues if value]
                                if leagues is not None
                                else None
                            ),
                            hide_role_infeasible=hide_role_infeasible,
                        )
                    )
                    return
                if parsed.path == "/api/v1/dataset":
                    self._json({
                        "api_version": "1", "dataset_id": "local-unverified",
                        "source": {"name": "Caller-supplied local data (unverified)"},
                        "generated_at": None, "attribution": "Provenance not verified by the local explorer.",
                        "coverage": index.dataset_context,
                        "role_status": "configured" if index.dataset_context["role_context_loaded"] else "not_evaluated",
                    })
                    return
                assets = {
                    "/": ("index.html", "text/html; charset=utf-8"),
                    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
                }
                asset = assets.get(parsed.path)
                if asset is None:
                    self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                    return
                body = _static_asset(asset[0])
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", asset[1])
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except ValueError as error:
                self._json({"error": str(error)}, HTTPStatus.BAD_REQUEST)

        def _json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    return ExplorerHandler


def _integer_parameter(
    query: dict[str, list[str]],
    name: str,
    default: int,
    *,
    maximum: int,
    minimum: int = 0,
) -> int:
    raw = query.get(name, [str(default)])[0]
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _boolean_parameter(
    query: dict[str, list[str]], name: str, default: bool
) -> bool:
    raw = query.get(name, [str(default)])[0].casefold()
    if raw in {"true", "1", "yes"}:
        return True
    if raw in {"false", "0", "no"}:
        return False
    raise ValueError(f"{name} must be true or false")


def create_server(
    index: RelationshipIndex, host: str = "127.0.0.1", port: int = 8765
) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(index))


def serve_explorer(
    records: Iterable[DraftRecord],
    *,
    input_path: str | Path,
    role_context_loaded: bool = False,
    role_policy: RolePolicy | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
) -> None:
    index = RelationshipIndex(
        records,
        input_identifier=str(input_path),
        role_context_loaded=role_context_loaded,
        role_policy=role_policy,
    )
    server = create_server(index, host, port)
    actual_port = server.server_address[1]
    url = f"http://{host}:{actual_port}/"
    print(f"DPS relationship explorer: {url}")
    print("Press Ctrl+C to stop.")
    if open_browser:
        threading.Timer(0.2, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
