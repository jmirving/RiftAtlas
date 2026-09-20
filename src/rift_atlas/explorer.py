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
from math import log1p
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from rift_atlas.model import DraftRecord


@dataclass(frozen=True)
class TeamObservation:
    champions: frozenset[str]
    patch: str
    league: str


@dataclass(frozen=True)
class RelationshipEvidence:
    """One reusable evidence model for every relationship view."""

    champion: str
    baseline_support: int
    co_pick_support: int
    focal_support: int
    lift: float
    confidence_adjusted_lift: float
    supporting_patches: tuple[str, ...]
    supporting_leagues: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "champion": self.champion,
            "baseline_support": self.baseline_support,
            "relationship": "co_pick",
            "co_pick_support": self.co_pick_support,
            "focal_support": self.focal_support,
            "neighbor_support": self.baseline_support,
            "lift": self.lift,
            "confidence_adjusted_lift": self.confidence_adjusted_lift,
            "supporting_patches": list(self.supporting_patches),
            "supporting_leagues": list(self.supporting_leagues),
        }


class RelationshipIndex:
    """Immutable aggregate for neutral, evidence-first graph exploration."""

    ASSOCIATION_PRIOR = 2
    MIN_NODE_RADIUS = 24.0
    MAX_NODE_RADIUS = 58.0
    DEFAULT_MODE = "established"
    MODE_DESCRIPTIONS = {
        "established": {
            "label": "Established",
            "description": "Balances normalized association with the amount of supporting evidence.",
            "ordering": "confidence-adjusted lift descending, then co-pick support descending, then champion name",
        },
        "frequent": {
            "label": "Frequent",
            "description": "Shows the relationships observed together most often.",
            "ordering": "co-pick support descending, then confidence-adjusted lift descending, then champion name",
        },
        "surprising": {
            "label": "Surprising",
            "description": "Surfaces unusually strong normalized association, including rare pairs.",
            "ordering": "lift descending, then co-pick support descending, then champion name",
        },
    }

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

    def graph(
        self,
        champion: str,
        *,
        limit: int = 12,
        mode: str = DEFAULT_MODE,
        minimum_support: int = 1,
    ) -> dict[str, object]:
        if limit < 0:
            raise ValueError("limit must be non-negative.")
        if mode not in self.MODE_DESCRIPTIONS:
            choices = ", ".join(self.MODE_DESCRIPTIONS)
            raise ValueError(f"mode must be one of: {choices}")
        if minimum_support < 1:
            raise ValueError("minimum_support must be at least 1.")
        canonical = self._canonical.get(champion.strip().casefold())
        if canonical is None:
            raise ValueError(f"Unknown champion: {champion}")

        focal_ids = self._observation_ids[canonical]
        evidence: list[RelationshipEvidence] = []
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
            evidence.append(
                RelationshipEvidence(
                    champion=neighbor,
                    baseline_support=neighbor_support,
                    co_pick_support=support,
                    focal_support=focal_support,
                    lift=lift,
                    confidence_adjusted_lift=adjusted,
                    supporting_patches=tuple(sorted({item.patch for item in contexts})),
                    supporting_leagues=tuple(sorted({item.league for item in contexts})),
                )
            )

        eligible = [item for item in evidence if item.co_pick_support >= minimum_support]
        eligible.sort(key=lambda item: self._ranking_key(item, mode))
        visible = [item.as_dict() for item in eligible[:limit]]
        visible_supports = [self._support[canonical]] + [
            int(item["baseline_support"]) for item in visible
        ]
        minimum_visible_support = min(visible_supports)
        maximum_visible_support = max(visible_supports)
        for item in visible:
            item["visual_radius"] = self._node_radius(
                int(item["baseline_support"]),
                minimum_visible_support,
                maximum_visible_support,
            )
        return {
            "relationship_types": ["co_pick"],
            "focal": {
                "champion": canonical,
                "baseline_support": self._support[canonical],
                "visual_radius": self._node_radius(
                    self._support[canonical],
                    minimum_visible_support,
                    maximum_visible_support,
                ),
            },
            "neighbors": visible,
            "neighbor_count": len(eligible),
            "relationship_count": len(evidence),
            "visible_neighbor_limit": limit,
            "minimum_support": minimum_support,
            "mode": mode,
            "mode_definition": dict(self.MODE_DESCRIPTIONS[mode]),
            "available_modes": {
                name: dict(description)
                for name, description in self.MODE_DESCRIPTIONS.items()
            },
            "dataset": self.dataset_context,
            "encoding": {
                "edge_width": "confidence_adjusted_lift",
                "edge_opacity": "co_pick_support",
                "node_size": "baseline_support",
                "node_radius_scale": {
                    "transform": "log1p",
                    "minimum": self.MIN_NODE_RADIUS,
                    "maximum": self.MAX_NODE_RADIUS,
                },
                "association_prior": self.ASSOCIATION_PRIOR,
            },
        }

    @staticmethod
    def _ranking_key(
        evidence: RelationshipEvidence, mode: str
    ) -> tuple[float | int | str, ...]:
        name = evidence.champion
        alphabetical = (name.casefold(), name)
        if mode == "frequent":
            return (
                -evidence.co_pick_support,
                -evidence.confidence_adjusted_lift,
                *alphabetical,
            )
        if mode == "surprising":
            return (-evidence.lift, -evidence.co_pick_support, *alphabetical)
        return (
            -evidence.confidence_adjusted_lift,
            -evidence.co_pick_support,
            *alphabetical,
        )

    @classmethod
    def _node_radius(cls, support: int, minimum: int, maximum: int) -> float:
        """Map support to a bounded perceptual radius within the visible graph."""
        if maximum == minimum:
            return (cls.MIN_NODE_RADIUS + cls.MAX_NODE_RADIUS) / 2
        scaled = (log1p(support) - log1p(minimum)) / (
            log1p(maximum) - log1p(minimum)
        )
        radius = cls.MIN_NODE_RADIUS + scaled * (
            cls.MAX_NODE_RADIUS - cls.MIN_NODE_RADIUS
        )
        return round(radius, 2)


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
                    minimum_support = _integer_parameter(
                        query, "minimum_support", 1, minimum=1, maximum=100_000
                    )
                    mode = query.get("mode", [RelationshipIndex.DEFAULT_MODE])[0]
                    self._json(
                        index.graph(
                            champion,
                            limit=limit,
                            mode=mode,
                            minimum_support=minimum_support,
                        )
                    )
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
