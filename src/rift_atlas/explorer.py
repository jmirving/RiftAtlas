from __future__ import annotations

import json
import threading
import webbrowser
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from rift_atlas.model import DraftRecord


@dataclass(frozen=True)
class TeamObservation:
    champions: frozenset[str]
    patch: str
    league: str


class RelationshipIndex:
    """Immutable aggregate for neutral, evidence-first graph exploration."""

    ASSOCIATION_PRIOR = 2

    def __init__(
        self,
        records: Iterable[DraftRecord],
        *,
        input_identifier: str,
        role_context_loaded: bool = False,
    ) -> None:
        observations: list[TeamObservation] = []
        canonical: dict[str, str] = {}
        games = 0
        for record in records:
            games += 1
            for picks in (record.blue_picks, record.red_picks):
                for champion in picks:
                    canonical.setdefault(champion.casefold(), champion)
                observations.append(
                    TeamObservation(frozenset(picks), record.context.patch, record.context.league)
                )

        self._observations = tuple(observations)
        self._canonical = canonical
        self._support = Counter(
            champion for observation in observations for champion in observation.champions
        )
        observation_ids: dict[str, set[int]] = {
            champion: set() for champion in self._support
        }
        for index, observation in enumerate(observations):
            for champion in observation.champions:
                observation_ids[champion].add(index)
        self._observation_ids = {
            champion: frozenset(indexes)
            for champion, indexes in observation_ids.items()
        }
        self._context = {
            "games_loaded": games,
            "team_observations_loaded": len(observations),
            "patches": sorted({observation.patch for observation in observations}),
            "leagues": sorted({observation.league for observation in observations}),
            "input_identifier": input_identifier,
            "role_context_loaded": role_context_loaded,
        }

    @property
    def dataset_context(self) -> dict[str, object]:
        return dict(self._context)

    def search(self, query: str = "", *, limit: int = 20) -> list[str]:
        if limit < 0:
            raise ValueError("limit must be non-negative.")
        needle = query.strip().casefold()
        champions = sorted(self._support, key=lambda value: (value.casefold(), value))
        if needle:
            champions = [champion for champion in champions if needle in champion.casefold()]
            champions.sort(
                key=lambda champion: (
                    not champion.casefold().startswith(needle),
                    champion.casefold(),
                    champion,
                )
            )
        return champions[:limit]

    def graph(self, champion: str, *, limit: int = 12) -> dict[str, object]:
        if limit < 0:
            raise ValueError("limit must be non-negative.")
        canonical = self._canonical.get(champion.strip().casefold())
        if canonical is None:
            raise ValueError(f"Unknown champion: {champion}")

        focal_ids = self._observation_ids[canonical]
        neighbors: list[dict[str, object]] = []
        for neighbor in self._support:
            if neighbor == canonical:
                continue
            matching = focal_ids.intersection(self._observation_ids[neighbor])
            if not matching:
                continue
            support = len(matching)
            focal_support = self._support[canonical]
            neighbor_support = self._support[neighbor]
            lift = (
                support * len(self._observations) / (focal_support * neighbor_support)
            )
            adjusted = lift * support / (support + self.ASSOCIATION_PRIOR)
            contexts = [self._observations[index] for index in matching]
            neighbors.append(
                {
                    "champion": neighbor,
                    "baseline_support": neighbor_support,
                    "relationship": "co_pick",
                    "co_pick_support": support,
                    "focal_support": focal_support,
                    "neighbor_support": neighbor_support,
                    "lift": lift,
                    "confidence_adjusted_lift": adjusted,
                    "supporting_patches": sorted({item.patch for item in contexts}),
                    "supporting_leagues": sorted({item.league for item in contexts}),
                }
            )

        neighbors.sort(
            key=lambda item: (
                -float(item["confidence_adjusted_lift"]),
                -int(item["co_pick_support"]),
                str(item["champion"]).casefold(),
                str(item["champion"]),
            )
        )
        visible = neighbors[:limit]
        return {
            "relationship_types": ["co_pick"],
            "focal": {
                "champion": canonical,
                "baseline_support": self._support[canonical],
            },
            "neighbors": visible,
            "neighbor_count": len(neighbors),
            "visible_neighbor_limit": limit,
            "dataset": self.dataset_context,
            "encoding": {
                "edge_width": "confidence_adjusted_lift",
                "node_size": "baseline_support",
                "association_prior": self.ASSOCIATION_PRIOR,
            },
        }


def _static_asset(name: str) -> bytes:
    return files("rift_atlas.web").joinpath(name).read_bytes()


def make_handler(index: RelationshipIndex) -> type[BaseHTTPRequestHandler]:
    class ExplorerHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/api/champions":
                    query = parse_qs(parsed.query)
                    limit = _integer_parameter(query, "limit", 20, maximum=100)
                    self._json({"champions": index.search(query.get("q", [""])[0], limit=limit)})
                    return
                if parsed.path == "/api/graph":
                    query = parse_qs(parsed.query)
                    champion = query.get("champion", [""])[0]
                    if not champion:
                        self._json({"error": "champion is required"}, HTTPStatus.BAD_REQUEST)
                        return
                    limit = _integer_parameter(query, "limit", 12, maximum=50)
                    self._json(index.graph(champion, limit=limit))
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
    query: dict[str, list[str]], name: str, default: int, *, maximum: int
) -> int:
    raw = query.get(name, [str(default)])[0]
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if not 0 <= value <= maximum:
        raise ValueError(f"{name} must be between 0 and {maximum}")
    return value


def create_server(
    index: RelationshipIndex, host: str = "127.0.0.1", port: int = 8765
) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(index))


def serve_explorer(
    records: Iterable[DraftRecord],
    *,
    input_path: str | Path,
    role_context_loaded: bool = False,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
) -> None:
    index = RelationshipIndex(
        records,
        input_identifier=str(input_path),
        role_context_loaded=role_context_loaded,
    )
    server = create_server(index, host, port)
    actual_port = server.server_address[1]
    url = f"http://{host}:{actual_port}/"
    print(f"RiftAtlas relationship explorer: {url}")
    print("Press Ctrl+C to stop.")
    if open_browser:
        threading.Timer(0.2, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
