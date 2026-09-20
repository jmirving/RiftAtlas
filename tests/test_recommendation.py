from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from rift_atlas.cli import main
from rift_atlas.contracts import REQUIRED_DRAFT_COLUMNS
from rift_atlas.model import DraftContext, DraftRecord
from rift_atlas.recommendation import MappingRolePolicy, RecommendationIndex


def record(
    game: int,
    blue: tuple[str, str, str, str, str],
    *,
    patch: str = "1.1",
    league: str = "L1",
) -> DraftRecord:
    red = tuple(f"Enemy{game}_{index}" for index in range(5))
    return DraftRecord(
        context=DraftContext(
            gameid=f"game-{game}",
            date="2026-01-01",
            year="2026",
            split="Spring",
            league=league,
            patch=patch,
            game=str(game),
        ),
        blue_teamid=f"blue-{game}",
        red_teamid=f"red-{game}",
        blue_picks=blue,
        red_picks=red,
        blue_bans=("b1", "b2", "b3", "b4", "b5"),
        red_bans=("r1", "r2", "r3", "r4", "r5"),
    )


def candidate(result: dict[str, object], champion: str) -> dict[str, object]:
    candidates = result["candidates"]
    assert isinstance(candidates, list)
    return next(item for item in candidates if item["champion"] == champion)


class RecommendationTests(unittest.TestCase):
    def test_one_locked_champion_reports_pair_support_and_context(self) -> None:
        index = RecommendationIndex(
            [
                record(1, ("A", "C", "X1", "X2", "X3"), patch="1.1", league="L1"),
                record(2, ("A", "C", "Y1", "Y2", "Y3"), patch="1.2", league="L2"),
            ]
        )
        result = index.recommend(["A"])
        evidence = candidate(result, "C")

        self.assertEqual(2, evidence["candidate_support"])
        self.assertEqual(2, evidence["pairwise_evidence"][0]["co_pick_support"])
        self.assertEqual(["1.1", "1.2"], evidence["supporting_patches"])
        self.assertEqual(["L1", "L2"], evidence["supporting_leagues"])
        self.assertEqual(2, evidence["ranking_components"]["supporting_patch_count"])
        self.assertEqual(2, evidence["ranking_components"]["supporting_league_count"])
        self.assertEqual("not_evaluated", evidence["role_feasibility"]["status"])

    def test_two_locked_champions_use_both_and_report_exact_trio(self) -> None:
        index = RecommendationIndex(
            [
                record(1, ("A", "B", "Broad", "X1", "X2")),
                record(2, ("A", "Edge", "Y1", "Y2", "Y3")),
                record(3, ("A", "Edge", "Z1", "Z2", "Z3")),
            ]
        )
        result = index.recommend(["A", "B"])
        broad = candidate(result, "Broad")
        edge = candidate(result, "Edge")

        self.assertEqual([1, 1], [p["co_pick_support"] for p in broad["pairwise_evidence"]])
        self.assertEqual(1, broad["exact_joint_support"])
        self.assertEqual(1, broad["subset_support"]["A + B + Broad"])
        self.assertEqual(2, broad["coverage_count"])
        self.assertEqual(1.0, broad["coverage_ratio"])
        self.assertEqual(1, edge["coverage_count"])
        self.assertLess(
            [item["champion"] for item in result["candidates"]].index("Broad"),
            [item["champion"] for item in result["candidates"]].index("Edge"),
        )

    def test_popularity_normalization_can_outweigh_raw_pair_count(self) -> None:
        records = [
            record(1, ("A", "Popular", "Rare", "X1", "X2")),
            record(2, ("A", "Popular", "Rare", "Y1", "Y2")),
            record(3, ("A", "Popular", "Z1", "Z2", "Z3")),
        ]
        # Popular appears in three more teams without A; Rare does not.
        records.extend(
            record(number, ("Popular", f"P{number}a", f"P{number}b", f"P{number}c", f"P{number}d"))
            for number in range(4, 7)
        )
        result = RecommendationIndex(records).recommend(["A"])
        popular = candidate(result, "Popular")
        rare = candidate(result, "Rare")

        self.assertGreater(
            popular["pairwise_evidence"][0]["co_pick_support"],
            rare["pairwise_evidence"][0]["co_pick_support"],
        )
        self.assertGreater(
            rare["pairwise_evidence"][0]["confidence_adjusted_lift"],
            popular["pairwise_evidence"][0]["confidence_adjusted_lift"],
        )
        self.assertLess(
            [item["champion"] for item in result["candidates"]].index("Rare"),
            [item["champion"] for item in result["candidates"]].index("Popular"),
        )

    def test_input_errors_and_deterministic_tie_break(self) -> None:
        index = RecommendationIndex([record(1, ("A", "Beta", "Alpha", "X", "Y"))])
        with self.assertRaisesRegex(ValueError, "distinct"):
            index.recommend(["A", "a"])
        with self.assertRaisesRegex(ValueError, "Unknown"):
            index.recommend(["Missing"])
        with self.assertRaisesRegex(ValueError, "fewer than five"):
            index.recommend(["A", "Beta", "Alpha", "X", "Y"])

        names = [item["champion"] for item in index.recommend(["A"])["candidates"]]
        self.assertLess(names.index("Alpha"), names.index("Beta"))
        repeated_names = [
            item["champion"] for item in index.recommend(["A"])["candidates"]
        ]
        self.assertEqual(names, repeated_names)

    def test_role_policy_preserves_flex_and_rejects_impossible_candidates(self) -> None:
        index = RecommendationIndex(
            [
                record(1, ("Top", "Jungle", "Bottom", "Flex", "Support")),
                record(2, ("Top", "Jungle", "Bottom", "Flex", "MidOnly")),
            ]
        )
        policy = MappingRolePolicy(
            {
                "Top": ["top"],
                "Jungle": ["jungle"],
                "Bottom": ["bottom"],
                "Flex": ["mid", "bottom"],
                "MidOnly": ["mid"],
                "Support": ["support"],
            }
        )
        locked = ["Top", "Jungle", "Bottom", "Flex"]
        result = index.recommend(locked, role_policy=policy)
        names = [item["champion"] for item in result["candidates"]]

        self.assertIn("Support", names)
        self.assertNotIn("MidOnly", names)
        flex = candidate(result, "Support")["role_feasibility"]
        self.assertEqual("feasible", flex["status"])
        self.assertEqual(["mid", "bottom"], flex["possible_roles"]["Flex"])

        flagged = index.recommend(
            locked, role_policy=policy, include_infeasible=True
        )
        self.assertEqual("infeasible", candidate(flagged, "MidOnly")["role_feasibility"]["status"])

    def test_cli_emits_machine_readable_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "drafts.csv"
            row = {column: "unused" for column in REQUIRED_DRAFT_COLUMNS}
            row.update(
                {
                    "schema_version": "1",
                    "gameid": "game-1",
                    "date": "2026-01-01",
                    "year": "2026",
                    "split": "Spring",
                    "league": "L1",
                    "patch": "1.1",
                    "game": "1",
                    "blue_teamid": "blue",
                    "red_teamid": "red",
                }
            )
            for index, champion in enumerate(("A", "B", "C", "D", "E"), start=1):
                row[f"blue_pick{index}"] = champion
                row[f"blue_ban{index}"] = f"BlueBan{index}"
            for index, champion in enumerate(("F", "G", "H", "I", "J"), start=1):
                row[f"red_pick{index}"] = champion
                row[f"red_ban{index}"] = f"RedBan{index}"
            with input_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(REQUIRED_DRAFT_COLUMNS))
                writer.writeheader()
                writer.writerow(row)

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(
                    ["recommend", "--input", str(input_path), "--pick", "A", "--limit", "1"]
                )

            payload = json.loads(output.getvalue())
            self.assertEqual(0, exit_code)
            self.assertEqual("1", payload["schema_version"])
            self.assertEqual(["A"], payload["locked_champions"])
            self.assertEqual(1, len(payload["candidates"]))


if __name__ == "__main__":
    unittest.main()
