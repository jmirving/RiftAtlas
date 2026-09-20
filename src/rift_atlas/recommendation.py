from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations
from typing import Protocol

from rift_atlas.contracts import RECOMMENDATION_SCHEMA_VERSION
from rift_atlas.model import DraftRecord


DEFAULT_ROLES = ("top", "jungle", "mid", "bottom", "support")


@dataclass(frozen=True)
class RoleFeasibility:
    status: str
    feasible: bool | None
    possible_roles: dict[str, tuple[str, ...]]
    reason: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "feasible": self.feasible,
            "possible_roles": {
                champion: list(roles)
                for champion, roles in sorted(self.possible_roles.items())
            },
            "reason": self.reason,
        }


class RolePolicy(Protocol):
    """Explicit source of role feasibility; draft pick order is never consulted."""

    def evaluate(self, champions: Sequence[str]) -> RoleFeasibility: ...


class MappingRolePolicy:
    """Role policy backed by caller-supplied champion-to-roles data."""

    def __init__(
        self,
        roles_by_champion: Mapping[str, Iterable[str]],
        required_roles: Sequence[str] = DEFAULT_ROLES,
    ) -> None:
        self.required_roles = tuple(required_roles)
        if len(set(self.required_roles)) != len(self.required_roles):
            raise ValueError("Required roles must be distinct.")
        allowed = set(self.required_roles)
        self._roles: dict[str, tuple[str, ...]] = {}
        for champion, roles in roles_by_champion.items():
            if isinstance(roles, str):
                raise ValueError(f"Roles for {champion!r} must be an array, not a string.")
            self._roles[champion.casefold()] = tuple(
                sorted(set(roles).intersection(allowed), key=self.required_roles.index)
            )

    def evaluate(self, champions: Sequence[str]) -> RoleFeasibility:
        possibilities: dict[str, tuple[str, ...]] = {}
        missing: list[str] = []
        for champion in champions:
            roles = self._roles.get(champion.casefold(), ())
            possibilities[champion] = roles
            if not roles:
                missing.append(champion)

        if missing:
            return RoleFeasibility(
                status="unknown",
                feasible=None,
                possible_roles=possibilities,
                reason="No supplied role data for: " + ", ".join(sorted(missing)),
            )

        # Bipartite matching preserves flex options until the full set constrains them.
        ordered = sorted(champions, key=lambda champion: (len(possibilities[champion]), champion))

        def can_assign(index: int, used: frozenset[str]) -> bool:
            if index == len(ordered):
                return True
            return any(
                role not in used and can_assign(index + 1, used | {role})
                for role in possibilities[ordered[index]]
            )

        feasible = len(champions) <= len(self.required_roles) and can_assign(0, frozenset())
        return RoleFeasibility(
            status="feasible" if feasible else "infeasible",
            feasible=feasible,
            possible_roles=possibilities,
            reason=None if feasible else "No distinct required-role assignment exists.",
        )


@dataclass(frozen=True)
class TeamObservation:
    champions: frozenset[str]
    patch: str
    league: str


class RecommendationIndex:
    """Immutable aggregate of allied-team observations for repeated recommendations."""

    ASSOCIATION_PRIOR = 2

    def __init__(self, records: Iterable[DraftRecord]) -> None:
        observations: list[TeamObservation] = []
        canonical: dict[str, str] = {}
        for record in records:
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

    @property
    def team_observation_count(self) -> int:
        return len(self._observations)

    def recommend(
        self,
        locked: Sequence[str],
        *,
        limit: int = 20,
        role_policy: RolePolicy | None = None,
        include_infeasible: bool = False,
    ) -> dict[str, object]:
        if not locked:
            raise ValueError("At least one locked champion is required.")
        if limit < 0:
            raise ValueError("limit must be non-negative.")
        folded = [champion.casefold() for champion in locked]
        if len(set(folded)) != len(folded):
            raise ValueError("Locked champions must be distinct.")
        if len(locked) >= 5:
            raise ValueError("Recommendations require fewer than five locked champions.")
        unknown = [champion for champion, key in zip(locked, folded) if key not in self._canonical]
        if unknown:
            raise ValueError("Unknown locked champion(s): " + ", ".join(unknown))

        normalized = tuple(self._canonical[key] for key in folded)
        locked_set = frozenset(normalized)
        results: list[dict[str, object]] = []
        for candidate in sorted(self._support, key=lambda value: (value.casefold(), value)):
            if candidate in locked_set:
                continue
            evidence = self._candidate_evidence(normalized, candidate, role_policy)
            if not any(pair["co_pick_support"] for pair in evidence["pairwise_evidence"]):
                continue
            role = evidence["role_feasibility"]
            if role["feasible"] is False and not include_infeasible:
                continue
            results.append(evidence)

        results.sort(key=self._ranking_key)
        return {
            "schema_version": RECOMMENDATION_SCHEMA_VERSION,
            "locked_champions": list(normalized),
            "team_observation_count": self.team_observation_count,
            "role_policy": "not_configured" if role_policy is None else "configured",
            "ranking": {
                "order": [
                    "coverage_count descending",
                    "minimum confidence-adjusted lift descending",
                    "exact_joint_support descending",
                    "mean confidence-adjusted lift descending",
                    "minimum pair support descending",
                    "any-pair supporting patch count descending",
                    "any-pair supporting league count descending",
                    "candidate support descending",
                    "champion name ascending",
                ],
                "association": (
                    "lift = pair_support * team_observation_count / "
                    "(locked_support * candidate_support); confidence_adjusted_lift = "
                    "lift * pair_support / (pair_support + 2)"
                ),
            },
            "candidates": results[:limit],
        }

    def _candidate_evidence(
        self,
        locked: tuple[str, ...],
        candidate: str,
        role_policy: RolePolicy | None,
    ) -> dict[str, object]:
        candidate_support = self._support[candidate]
        pairwise: list[dict[str, object]] = []
        context_observations: set[int] = set()
        adjusted_values: list[float] = []
        pair_counts: list[int] = []
        for champion in locked:
            matching = self._matching_observations((champion, candidate))
            support = len(matching)
            context_observations.update(matching)
            pair_contexts = [self._observations[index] for index in matching]
            locked_support = self._support[champion]
            lift = (
                support * self.team_observation_count / (locked_support * candidate_support)
                if support
                else 0.0
            )
            adjusted = lift * support / (support + self.ASSOCIATION_PRIOR)
            adjusted_values.append(adjusted)
            pair_counts.append(support)
            pairwise.append(
                {
                    "locked_champion": champion,
                    "co_pick_support": support,
                    "locked_support": locked_support,
                    "candidate_support": candidate_support,
                    "lift": lift,
                    "confidence_adjusted_lift": adjusted,
                    "supporting_patches": sorted(
                        {item.patch for item in pair_contexts}
                    ),
                    "supporting_leagues": sorted(
                        {item.league for item in pair_contexts}
                    ),
                }
            )

        exact_indexes = self._matching_observations((*locked, candidate))
        subset_support: dict[str, int] = {}
        for size in range(2, len(locked) + 1):
            for subset in combinations(locked, size):
                champions = frozenset((*subset, candidate))
                subset_support[" + ".join((*subset, candidate))] = len(
                    self._matching_observations(champions)
                )

        coverage_count = sum(value > 0 for value in pair_counts)
        role = (
            RoleFeasibility("not_evaluated", None, {}, "No role policy was configured.")
            if role_policy is None
            else role_policy.evaluate((*locked, candidate))
        )
        contexts = [self._observations[index] for index in context_observations]
        exact_contexts = [self._observations[index] for index in exact_indexes]
        return {
            "champion": candidate,
            "candidate_support": candidate_support,
            "pairwise_evidence": pairwise,
            "coverage_count": coverage_count,
            "coverage_ratio": coverage_count / len(locked),
            "exact_joint_support": len(exact_indexes),
            "subset_support": subset_support,
            "any_pair_supporting_patches": sorted({item.patch for item in contexts}),
            "any_pair_supporting_leagues": sorted({item.league for item in contexts}),
            "exact_joint_patches": sorted({item.patch for item in exact_contexts}),
            "exact_joint_leagues": sorted({item.league for item in exact_contexts}),
            "ranking_components": {
                "minimum_pair_support": min(pair_counts),
                "minimum_confidence_adjusted_lift": min(adjusted_values),
                "mean_confidence_adjusted_lift": sum(adjusted_values) / len(adjusted_values),
                "any_pair_supporting_patch_count": len(
                    {item.patch for item in contexts}
                ),
                "any_pair_supporting_league_count": len(
                    {item.league for item in contexts}
                ),
            },
            "role_feasibility": role.as_dict(),
        }

    def _matching_observations(self, champions: Iterable[str]) -> frozenset[int]:
        indexes = [self._observation_ids[champion] for champion in champions]
        if not indexes:
            return frozenset()
        return frozenset.intersection(*indexes)

    @staticmethod
    def _ranking_key(evidence: dict[str, object]) -> tuple[object, ...]:
        components = evidence["ranking_components"]
        assert isinstance(components, dict)
        return (
            -int(evidence["coverage_count"]),
            -float(components["minimum_confidence_adjusted_lift"]),
            -int(evidence["exact_joint_support"]),
            -float(components["mean_confidence_adjusted_lift"]),
            -int(components["minimum_pair_support"]),
            -int(components["any_pair_supporting_patch_count"]),
            -int(components["any_pair_supporting_league_count"]),
            -int(evidence["candidate_support"]),
            str(evidence["champion"]).casefold(),
            str(evidence["champion"]),
        )
