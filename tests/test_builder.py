from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from rift_atlas.builder import build_relationship_file, iter_relationships
from rift_atlas.contracts import REQUIRED_DRAFT_COLUMNS
from rift_atlas.model import DraftRecord


def sample_row() -> dict[str, str]:
    row = {column: "unused" for column in REQUIRED_DRAFT_COLUMNS}
    row.update(
        {
            "schema_version": "1",
            "gameid": "game-1",
            "date": "2026-09-01",
            "year": "2026",
            "split": "Summer",
            "league": "TEST",
            "patch": "26.17",
            "game": "1",
            "blue_teamid": "blue-team",
            "red_teamid": "red-team",
            "blue_pick1": "Aatrox",
            "blue_pick2": "Sejuani",
            "blue_pick3": "Ahri",
            "blue_pick4": "Jinx",
            "blue_pick5": "Nautilus",
            "red_pick1": "Renekton",
            "red_pick2": "Maokai",
            "red_pick3": "Syndra",
            "red_pick4": "KaiSa",
            "red_pick5": "Rakan",
            "blue_ban1": "Gnar",
            "blue_ban2": "Vi",
            "blue_ban3": "Orianna",
            "blue_ban4": "Ezreal",
            "blue_ban5": "Leona",
            "red_ban1": "Camille",
            "red_ban2": "Nocturne",
            "red_ban3": "Azir",
            "red_ban4": "Caitlyn",
            "red_ban5": "Braum",
        }
    )
    return row


class RelationshipBuilderTests(unittest.TestCase):
    def test_single_game_yields_expected_relationship_counts(self) -> None:
        record = DraftRecord.from_row(sample_row())
        relationships = list(iter_relationships(record))

        counts: dict[str, int] = {}
        for relationship in relationships:
            counts[relationship.relationship] = counts.get(relationship.relationship, 0) + 1

        self.assertEqual(70, len(relationships))
        self.assertEqual(
            {
                "co_pick": 20,
                "opposition": 25,
                "draft_response": 25,
            },
            counts,
        )

    def test_draft_response_points_from_visible_pick_to_later_pick(self) -> None:
        record = DraftRecord.from_row(sample_row())
        responses = [
            relationship
            for relationship in iter_relationships(record)
            if relationship.relationship == "draft_response"
        ]

        b1_to_r1 = next(
            relationship
            for relationship in responses
            if {relationship.source.champion, relationship.target.champion}
            == {"Aatrox", "Renekton"}
        )

        self.assertEqual("Aatrox", b1_to_r1.source.champion)
        self.assertEqual("Renekton", b1_to_r1.target.champion)
        self.assertEqual(1, b1_to_r1.source.event)
        self.assertEqual(2, b1_to_r1.target.event)

    def test_wrong_input_schema_is_rejected(self) -> None:
        row = sample_row()
        row["schema_version"] = "2"

        with self.assertRaisesRegex(ValueError, "Unsupported drafts schema_version"):
            DraftRecord.from_row(row)

    def test_build_writes_deterministic_jsonl_and_stats(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "drafts.csv"
            output_path = root / "relationships.jsonl"

            with input_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(REQUIRED_DRAFT_COLUMNS))
                writer.writeheader()
                writer.writerow(sample_row())

            stats = build_relationship_file(input_path, output_path)
            lines = output_path.read_text(encoding="utf-8").splitlines()
            first = json.loads(lines[0])

            self.assertEqual(1, stats.games)
            self.assertEqual(70, stats.relationships)
            self.assertEqual(70, len(lines))
            self.assertEqual("1", first["schema_version"])
            self.assertEqual("co_pick", first["relationship"])
            self.assertEqual("game-1", first["gameid"])


if __name__ == "__main__":
    unittest.main()
