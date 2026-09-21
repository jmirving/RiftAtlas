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
from itertools import combinations
from math import log1p
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from rift_atlas.model import DraftRecord


TOP_REGION_LEAGUES = ("LCK", "LPL", "LEC", "LCS", "LCP")


def _patch_sort_key(value: str) -> tuple[tuple[int, int | str], ...]:
    """Sort dotted patch labels naturally while retaining arbitrary labels."""
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part.casefold())
        for part in value.split(".")
    )


@dataclass(frozen=True)
class TeamObservation:
    champions: frozenset[str]
    patch: str
    league: str
    game_id: str


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
    patch_distribution: tuple[tuple[str, int], ...]
    league_distribution: tuple[tuple[str, int], ...]

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
            "patch_distribution": [
                {"patch": patch, "count": count}
                for patch, count in self.patch_distribution
            ],
            "league_distribution": [
                {"league": league, "count": count}
                for league, count in self.league_distribution
            ],
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
            "description": "Prioritizes coverage across the pinned set, then balances normalized association with supporting evidence.",
            "ordering": "coverage descending, then minimum confidence-adjusted lift, exact joint support, mean adjusted lift, minimum pair support, and champion name",
        },
        "frequent": {
            "label": "Frequent",
            "description": "Prioritizes coverage, then relationships observed together most often across the pinned set.",
            "ordering": "coverage descending, then total pair support, exact joint support, mean adjusted lift, and champion name",
        },
        "surprising": {
            "label": "Surprising",
            "description": "Prioritizes coverage, then unusually strong normalized association across every pinned relationship.",
            "ordering": "coverage descending, then minimum lift, exact joint support, total pair support, and champion name",
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
                    TeamObservation(
                        frozenset(picks),
                        record.context.patch,
                        record.context.league,
                        record.context.gameid,
                    )
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
            "patches": sorted(
                {observation.patch for observation in observations}, key=_patch_sort_key
            ),
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
        pinned: Iterable[str] | None = None,
        limit: int = 12,
        mode: str = DEFAULT_MODE,
        minimum_support: int = 1,
        patch: str | None = None,
        patch_from: str | None = None,
        patch_to: str | None = None,
        league: str | None = None,
        leagues: Iterable[str] | None = None,
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
        requested_pins = tuple(pinned) if pinned is not None else (canonical,)
        if not requested_pins:
            raise ValueError("At least one pinned champion is required.")
        folded_pins = [item.strip().casefold() for item in requested_pins]
        if len(set(folded_pins)) != len(folded_pins):
            raise ValueError("Pinned champions must be distinct.")
        unknown_pins = [
            item for item, key in zip(requested_pins, folded_pins)
            if key not in self._canonical
        ]
        if unknown_pins:
            raise ValueError("Unknown pinned champion(s): " + ", ".join(unknown_pins))
        if len(requested_pins) >= 5:
            raise ValueError("Exploration requires fewer than five pinned champions.")
        normalized_pins = tuple(self._canonical[key] for key in folded_pins)
        observations, active_filters = self._filtered_observations(
            patch=patch,
            patch_from=patch_from,
            patch_to=patch_to,
            league=league,
            leagues=leagues,
        )
        scoped_support = Counter(
            item for observation in observations for item in observation.champions
        )
        observation_ids: dict[str, set[int]] = {
            item: set() for item in scoped_support
        }
        for index, observation in enumerate(observations):
            for item in observation.champions:
                observation_ids[item].add(index)

        pinned_set = frozenset(normalized_pins)
        evidence: list[dict[str, object]] = []
        relationship_count = 0
        for neighbor in scoped_support:
            if neighbor in pinned_set:
                continue
            item = self._candidate_evidence(
                normalized_pins,
                neighbor,
                observations,
                observation_ids,
                scoped_support,
                minimum_support,
            )
            if any(int(pair["co_pick_support"]) > 0 for pair in item["pairwise_evidence"]):
                relationship_count += 1
            if not any(
                int(pair["co_pick_support"]) >= minimum_support
                for pair in item["pairwise_evidence"]
            ):
                continue
            evidence.append(item)

        evidence.sort(key=lambda item: self._candidate_ranking_key(item, mode))
        visible = evidence[:limit]
        focal_support = len(observation_ids.get(canonical, set()))
        visible_supports = [
            len(observation_ids.get(item, set())) for item in normalized_pins
        ] + [
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
        pinned_nodes = []
        for item in normalized_pins:
            support = len(observation_ids.get(item, set()))
            pinned_nodes.append(
                {
                    "champion": item,
                    "baseline_support": support,
                    "visual_radius": self._node_radius(
                        support, minimum_visible_support, maximum_visible_support
                    ),
                }
            )
        pinned_edges = []
        for left, right in combinations(normalized_pins, 2):
            pair = self._pair_evidence(
                left, right, observations, observation_ids, scoped_support
            )
            pair.pop("_matching_indexes")
            pinned_edges.append(pair)
        return {
            "relationship_types": ["co_pick"],
            "pinned_champions": list(normalized_pins),
            "pinned": pinned_nodes,
            "pinned_edges": pinned_edges,
            "focal": {
                "champion": canonical,
                "baseline_support": focal_support,
                "visual_radius": self._node_radius(
                    focal_support,
                    minimum_visible_support,
                    maximum_visible_support,
                ),
            },
            "neighbors": visible,
            "neighbor_count": len(evidence),
            "relationship_count": relationship_count,
            "visible_neighbor_limit": limit,
            "minimum_support": minimum_support,
            "mode": mode,
            "mode_definition": dict(self.MODE_DESCRIPTIONS[mode]),
            "available_modes": {
                name: dict(description)
                for name, description in self.MODE_DESCRIPTIONS.items()
            },
            "dataset": self._dataset_context_for(observations, active_filters),
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

    def _candidate_evidence(
        self,
        pinned: tuple[str, ...],
        candidate: str,
        observations: tuple[TeamObservation, ...],
        observation_ids: dict[str, set[int]],
        scoped_support: Counter[str],
        minimum_support: int,
    ) -> dict[str, object]:
        pairwise = [
            self._pair_evidence(
                locked, candidate, observations, observation_ids, scoped_support
            )
            for locked in pinned
        ]
        pair_counts = [int(pair["co_pick_support"]) for pair in pairwise]
        adjusted = [float(pair["confidence_adjusted_lift"]) for pair in pairwise]
        lifts = [float(pair["lift"]) for pair in pairwise]
        exact_indexes = self._matching_scoped_observations(
            (*pinned, candidate), observation_ids
        )
        exact_contexts = [observations[index] for index in exact_indexes]
        union_indexes: set[int] = set()
        for pair in pairwise:
            union_indexes.update(pair.pop("_matching_indexes"))
        union_contexts = [observations[index] for index in union_indexes]
        patch_counts = Counter(item.patch for item in union_contexts)
        league_counts = Counter(item.league for item in union_contexts)
        exact_patch_counts = Counter(item.patch for item in exact_contexts)
        exact_league_counts = Counter(item.league for item in exact_contexts)
        subset_support: dict[str, int] = {}
        for size in range(2, len(pinned) + 1):
            for subset in combinations(pinned, size):
                label = " + ".join((*subset, candidate))
                subset_support[label] = len(
                    self._matching_scoped_observations(
                        (*subset, candidate), observation_ids
                    )
                )
        coverage_count = sum(value >= minimum_support for value in pair_counts)
        candidate_support = scoped_support[candidate]
        return {
            "champion": candidate,
            "baseline_support": candidate_support,
            "candidate_support": candidate_support,
            "pairwise_evidence": pairwise,
            "coverage_count": coverage_count,
            "coverage_ratio": coverage_count / len(pinned),
            "exact_joint_support": len(exact_indexes),
            "subset_support": subset_support,
            "any_pair_supporting_patches": sorted(patch_counts, key=_patch_sort_key),
            "any_pair_supporting_leagues": sorted(league_counts),
            "exact_joint_patches": sorted(exact_patch_counts, key=_patch_sort_key),
            "exact_joint_leagues": sorted(exact_league_counts),
            "patch_distribution": [
                {"patch": value, "count": patch_counts[value]}
                for value in sorted(patch_counts, key=_patch_sort_key)
            ],
            "league_distribution": [
                {"league": value, "count": league_counts[value]}
                for value in sorted(league_counts)
            ],
            "exact_joint_patch_distribution": [
                {"patch": value, "count": exact_patch_counts[value]}
                for value in sorted(exact_patch_counts, key=_patch_sort_key)
            ],
            "exact_joint_league_distribution": [
                {"league": value, "count": exact_league_counts[value]}
                for value in sorted(exact_league_counts)
            ],
            # Compatibility aggregate for existing single-focus clients.
            "co_pick_support": sum(pair_counts),
            "focal_support": int(pairwise[0]["locked_support"]),
            "neighbor_support": candidate_support,
            "lift": sum(lifts) / len(lifts),
            "confidence_adjusted_lift": sum(adjusted) / len(adjusted),
            "supporting_patches": sorted(patch_counts, key=_patch_sort_key),
            "supporting_leagues": sorted(league_counts),
            "ranking_components": {
                "minimum_pair_support": min(pair_counts),
                "total_pair_support": sum(pair_counts),
                "minimum_lift": min(lifts),
                "minimum_confidence_adjusted_lift": min(adjusted),
                "mean_confidence_adjusted_lift": sum(adjusted) / len(adjusted),
            },
        }

    def _pair_evidence(
        self,
        locked: str,
        candidate: str,
        observations: tuple[TeamObservation, ...],
        observation_ids: dict[str, set[int]],
        scoped_support: Counter[str],
    ) -> dict[str, object]:
        matching = observation_ids.get(locked, set()).intersection(
            observation_ids.get(candidate, set())
        )
        support = len(matching)
        locked_support = scoped_support[locked]
        candidate_support = scoped_support[candidate]
        lift = (
            support * len(observations) / (locked_support * candidate_support)
            if support and locked_support and candidate_support
            else 0.0
        )
        adjusted = lift * support / (support + self.ASSOCIATION_PRIOR)
        contexts = [observations[index] for index in matching]
        patch_counts = Counter(item.patch for item in contexts)
        league_counts = Counter(item.league for item in contexts)
        return {
            "locked_champion": locked,
            "candidate_champion": candidate,
            "co_pick_support": support,
            "locked_support": locked_support,
            "candidate_support": candidate_support,
            "lift": lift,
            "confidence_adjusted_lift": adjusted,
            "supporting_patches": sorted(patch_counts, key=_patch_sort_key),
            "supporting_leagues": sorted(league_counts),
            "patch_distribution": [
                {"patch": value, "count": patch_counts[value]}
                for value in sorted(patch_counts, key=_patch_sort_key)
            ],
            "league_distribution": [
                {"league": value, "count": league_counts[value]}
                for value in sorted(league_counts)
            ],
            "_matching_indexes": sorted(matching),
        }

    @staticmethod
    def _matching_scoped_observations(
        champions: Iterable[str], observation_ids: dict[str, set[int]]
    ) -> set[int]:
        indexes = [observation_ids.get(champion, set()) for champion in champions]
        return set.intersection(*indexes) if indexes else set()

    @staticmethod
    def _candidate_ranking_key(
        evidence: dict[str, object], mode: str
    ) -> tuple[object, ...]:
        components = evidence["ranking_components"]
        assert isinstance(components, dict)
        name = str(evidence["champion"])
        alphabetical = (name.casefold(), name)
        if mode == "frequent":
            return (
                -int(evidence["coverage_count"]),
                -int(components["total_pair_support"]),
                -int(evidence["exact_joint_support"]),
                -float(components["mean_confidence_adjusted_lift"]),
                *alphabetical,
            )
        if mode == "surprising":
            return (
                -int(evidence["coverage_count"]),
                -float(components["minimum_lift"]),
                -int(evidence["exact_joint_support"]),
                -int(components["total_pair_support"]),
                *alphabetical,
            )
        return (
            -int(evidence["coverage_count"]),
            -float(components["minimum_confidence_adjusted_lift"]),
            -int(evidence["exact_joint_support"]),
            -float(components["mean_confidence_adjusted_lift"]),
            -int(components["minimum_pair_support"]),
            *alphabetical,
        )

    def _filtered_observations(
        self,
        *,
        patch: str | None,
        patch_from: str | None,
        patch_to: str | None,
        league: str | None,
        leagues: Iterable[str] | None,
    ) -> tuple[tuple[TeamObservation, ...], dict[str, object]]:
        if patch and (patch_from or patch_to):
            raise ValueError("patch cannot be combined with patch_from or patch_to")
        if league is not None and leagues is not None:
            raise ValueError("league cannot be combined with leagues")
        known_patches = set(self._context["patches"])
        known_leagues = set(self._context["leagues"])
        for name, value in (
            ("patch", patch),
            ("patch_from", patch_from),
            ("patch_to", patch_to),
        ):
            if value and value not in known_patches:
                raise ValueError(f"Unknown {name}: {value}")
        selected_leagues = (
            tuple(sorted(set(leagues))) if leagues is not None else None
        )
        if league is not None:
            selected_leagues = (league,)
        unknown_leagues = (
            set(selected_leagues).difference(known_leagues)
            if selected_leagues is not None
            else set()
        )
        if unknown_leagues:
            raise ValueError(f"Unknown league: {', '.join(sorted(unknown_leagues))}")
        if (
            patch_from
            and patch_to
            and _patch_sort_key(patch_from) > _patch_sort_key(patch_to)
        ):
            raise ValueError("patch_from must not be after patch_to")

        active_filters: dict[str, object] = {
            name: value
            for name, value in (
                ("patch", patch),
                ("patch_from", patch_from),
                ("patch_to", patch_to),
            )
            if value
        }
        if selected_leagues is not None:
            active_filters["leagues"] = list(selected_leagues)
        selected_league_set = (
            set(selected_leagues) if selected_leagues is not None else None
        )
        filtered = tuple(
            observation
            for observation in self._observations
            if (not patch or observation.patch == patch)
            and (
                not patch_from
                or _patch_sort_key(observation.patch) >= _patch_sort_key(patch_from)
            )
            and (
                not patch_to
                or _patch_sort_key(observation.patch) <= _patch_sort_key(patch_to)
            )
            and (
                selected_league_set is None
                or observation.league in selected_league_set
            )
        )
        return filtered, active_filters

    def _dataset_context_for(
        self,
        observations: tuple[TeamObservation, ...],
        active_filters: dict[str, object],
    ) -> dict[str, object]:
        context = self.dataset_context
        context.update(
            {
                "games_in_scope": len({item.game_id for item in observations}),
                "team_observations_in_scope": len(observations),
                "patches_in_scope": sorted(
                    {item.patch for item in observations}, key=_patch_sort_key
                ),
                "leagues_in_scope": sorted({item.league for item in observations}),
                "top_region_leagues": [
                    league
                    for league in TOP_REGION_LEAGUES
                    if league in self._context["leagues"]
                ],
                "active_filters": active_filters,
            }
        )
        return context

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
                    query = parse_qs(parsed.query, keep_blank_values=True)
                    limit = _integer_parameter(query, "limit", 20, maximum=100)
                    self._json({"champions": index.search(query.get("q", [""])[0], limit=limit)})
                    return
                if parsed.path == "/api/graph":
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
