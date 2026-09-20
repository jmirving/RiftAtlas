from __future__ import annotations

import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

from rift_atlas.explorer import RelationshipIndex, create_server
from rift_atlas.model import DraftContext, DraftRecord


def record(
    game: int,
    blue: tuple[str, str, str, str, str],
    *,
    patch: str = "1.1",
    league: str = "L1",
) -> DraftRecord:
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
        red_picks=tuple(f"Enemy{game}_{index}" for index in range(5)),
        blue_bans=("b1", "b2", "b3", "b4", "b5"),
        red_bans=("r1", "r2", "r3", "r4", "r5"),
    )


def sample_index() -> RelationshipIndex:
    return RelationshipIndex(
        [
            record(1, ("A", "B", "C", "D", "E")),
            record(2, ("A", "B", "C", "X", "Y"), patch="1.2", league="L2"),
            record(3, ("A", "Q", "R", "S", "T")),
        ],
        input_identifier="fixtures/drafts.csv",
    )


class RelationshipIndexTests(unittest.TestCase):
    def test_champion_search_and_case_insensitive_focus(self) -> None:
        index = sample_index()

        self.assertEqual(["Enemy1_0", "Enemy1_1"], index.search("enemy1", limit=2))
        self.assertEqual("A", index.graph("a")["focal"]["champion"])

    def test_neighbors_are_deterministic_and_limited(self) -> None:
        index = sample_index()

        first = index.graph("A", limit=2)
        second = index.graph("A", limit=2)

        self.assertEqual(first, second)
        self.assertEqual(["B", "C"], [item["champion"] for item in first["neighbors"]])
        self.assertEqual(2, len(first["neighbors"]))
        self.assertGreater(first["neighbor_count"], 2)

    def test_co_pick_edge_evidence_matches_observations(self) -> None:
        graph = sample_index().graph("A")
        edge = next(item for item in graph["neighbors"] if item["champion"] == "B")

        self.assertEqual(2, edge["co_pick_support"])
        self.assertEqual(3, edge["focal_support"])
        self.assertEqual(2, edge["neighbor_support"])
        self.assertEqual(2.0, edge["lift"])
        self.assertEqual(1.0, edge["confidence_adjusted_lift"])
        self.assertEqual(["1.1", "1.2"], edge["supporting_patches"])
        self.assertEqual(["L1", "L2"], edge["supporting_leagues"])

    def test_unknown_champion_and_no_self_neighbor(self) -> None:
        index = sample_index()

        with self.assertRaisesRegex(ValueError, "Unknown champion"):
            index.graph("Missing")
        self.assertNotIn("A", [item["champion"] for item in index.graph("A")["neighbors"]])

    def test_dataset_context_is_descriptive(self) -> None:
        context = sample_index().dataset_context

        self.assertEqual(6, context["team_observations_loaded"])
        self.assertEqual(["1.1", "1.2"], context["patches"])
        self.assertEqual(["L1", "L2"], context["leagues"])
        self.assertEqual("fixtures/drafts.csv", context["input_identifier"])
        self.assertFalse(context["role_context_loaded"])


class ExplorerServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = create_server(sample_index(), port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_initial_page_and_graph_endpoint_are_served(self) -> None:
        with urlopen(self.base_url + "/", timeout=2) as response:
            page = response.read().decode()
        with urlopen(self.base_url + "/app.js", timeout=2) as response:
            script = response.read().decode()
        with urlopen(self.base_url + "/styles.css", timeout=2) as response:
            styles = response.read().decode()
        with urlopen(self.base_url + "/api/graph?champion=A&limit=1", timeout=2) as response:
            payload = json.load(response)

        self.assertIn("Relationship explorer", page)
        self.assertIn("do not claim synergy", page)
        self.assertIn("renderGraph", script)
        self.assertIn(".workspace", styles)
        self.assertEqual("A", payload["focal"]["champion"])
        self.assertEqual(1, len(payload["neighbors"]))

    def test_unknown_champion_returns_bad_request(self) -> None:
        with self.assertRaises(HTTPError) as caught:
            urlopen(self.base_url + "/api/graph?champion=Missing", timeout=2)

        self.assertEqual(400, caught.exception.code)
        payload = json.load(caught.exception)
        self.assertIn("Unknown champion", payload["error"])


if __name__ == "__main__":
    unittest.main()
