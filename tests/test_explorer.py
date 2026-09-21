from __future__ import annotations

import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

from rift_atlas.explorer import TOP_REGION_LEAGUES, RelationshipIndex, create_server
from rift_atlas.model import DraftContext, DraftRecord
from rift_atlas.recommendation import MappingRolePolicy


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

    def test_relationship_modes_have_documented_deterministic_ordering(self) -> None:
        index = RelationshipIndex(
            [
                record(1, ("A", "Frequent", "Surprising", "X1", "X2")),
                record(2, ("A", "Frequent", "X3", "X4", "X5")),
                record(3, ("A", "Frequent", "X6", "X7", "X8")),
                record(4, ("Frequent", "P1", "P2", "P3", "P4")),
                record(5, ("Frequent", "P5", "P6", "P7", "P8")),
            ],
            input_identifier="fixtures/modes.csv",
        )

        established = index.graph("A")
        frequent = index.graph("A", mode="frequent")
        surprising = index.graph("A", mode="surprising")

        self.assertEqual("Frequent", established["neighbors"][0]["champion"])
        self.assertEqual("Frequent", frequent["neighbors"][0]["champion"])
        self.assertEqual("Surprising", surprising["neighbors"][0]["champion"])
        self.assertEqual("established", index.graph("A")["mode"])
        self.assertIn("ordering", surprising["mode_definition"])
        self.assertEqual(frequent, index.graph("A", mode="frequent"))

    def test_minimum_support_filters_without_changing_evidence_model(self) -> None:
        graph = sample_index().graph("A", minimum_support=2)

        self.assertEqual(["B", "C"], [item["champion"] for item in graph["neighbors"]])
        self.assertEqual(2, graph["neighbor_count"])
        self.assertGreater(graph["relationship_count"], graph["neighbor_count"])
        self.assertEqual(2, graph["minimum_support"])

    def test_invalid_mode_and_minimum_support_are_rejected(self) -> None:
        index = sample_index()

        with self.assertRaisesRegex(ValueError, "mode must be one of"):
            index.graph("A", mode="quality")
        with self.assertRaisesRegex(ValueError, "at least 1"):
            index.graph("A", minimum_support=0)

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
        self.assertEqual(
            [{"patch": "1.1", "count": 1}, {"patch": "1.2", "count": 1}],
            edge["patch_distribution"],
        )
        self.assertEqual(
            [{"league": "L1", "count": 1}, {"league": "L2", "count": 1}],
            edge["league_distribution"],
        )

    def test_pinned_set_reports_full_and_partial_coverage_and_exact_joint_support(self) -> None:
        index = RelationshipIndex(
            [
                record(1, ("A", "B", "Both", "C", "D")),
                record(2, ("A", "Both", "E", "F", "G"), patch="1.2"),
                record(3, ("B", "Both", "H", "I", "J"), league="L2"),
                record(4, ("A", "OnlyA", "K", "L", "M")),
                record(5, ("B", "OnlyB", "N", "O", "P")),
            ],
            input_identifier="fixtures/pinned.csv",
        )

        graph = index.graph("OnlyA", pinned=["a", "B"], limit=50)
        candidates = {item["champion"]: item for item in graph["neighbors"]}
        both = candidates["Both"]
        only_a = candidates["OnlyA"]

        self.assertEqual("OnlyA", graph["focal"]["champion"])
        self.assertEqual(["A", "B"], graph["pinned_champions"])
        self.assertEqual(2, both["coverage_count"])
        self.assertEqual(1.0, both["coverage_ratio"])
        self.assertEqual(1, both["exact_joint_support"])
        self.assertEqual(1, both["subset_support"]["A + B + Both"])
        self.assertEqual([2, 2], [
            pair["co_pick_support"] for pair in both["pairwise_evidence"]
        ])
        self.assertEqual(1, only_a["coverage_count"])
        self.assertEqual(0, only_a["exact_joint_support"])
        self.assertEqual(1, len(graph["pinned_edges"]))

    def test_minimum_support_changes_pinned_coverage_without_hiding_partial_candidates(self) -> None:
        index = RelationshipIndex(
            [
                record(1, ("A", "B", "Candidate", "C", "D")),
                record(2, ("A", "Candidate", "E", "F", "G")),
            ],
            input_identifier="fixtures/pinned-support.csv",
        )

        candidate = index.graph(
            "A", pinned=["A", "B"], minimum_support=2
        )["neighbors"][0]

        self.assertEqual("Candidate", candidate["champion"])
        self.assertEqual(1, candidate["coverage_count"])
        self.assertEqual([2, 1], [
            pair["co_pick_support"] for pair in candidate["pairwise_evidence"]
        ])

    def test_pinned_set_validation_rejects_duplicates_unknowns_and_five_pins(self) -> None:
        index = sample_index()

        with self.assertRaisesRegex(ValueError, "must be distinct"):
            index.graph("A", pinned=["A", "a"])
        with self.assertRaisesRegex(ValueError, "Unknown pinned"):
            index.graph("A", pinned=["Missing"])
        with self.assertRaisesRegex(ValueError, "fewer than five"):
            index.graph("A", pinned=["A", "B", "C", "D", "E"])

    def test_role_feasibility_overlays_pinned_and_candidate_compositions(self) -> None:
        index = RelationshipIndex(
            [
                record(1, ("Top", "Jungle", "Bottom", "Flex", "Support")),
                record(2, ("Top", "Jungle", "Bottom", "Flex", "MidOnly")),
            ],
            input_identifier="fixtures/roles.csv",
            role_policy=MappingRolePolicy(
                {
                    "Top": ["top"],
                    "Jungle": ["jungle"],
                    "Bottom": ["bottom"],
                    "Flex": ["mid", "bottom"],
                    "Support": ["support"],
                    "MidOnly": ["mid"],
                }
            ),
        )

        graph = index.graph(
            "Top", pinned=["Top", "Jungle", "Bottom", "Flex"], limit=50
        )
        candidates = {item["champion"]: item for item in graph["neighbors"]}

        self.assertEqual("configured", graph["role_policy"])
        self.assertEqual("feasible", graph["pinned_role_feasibility"]["status"])
        self.assertEqual(
            ["mid"], graph["pinned_role_feasibility"]["possible_roles"]["Flex"]
        )
        self.assertEqual("feasible", candidates["Support"]["role_feasibility"]["status"])
        self.assertEqual(
            ["mid"], candidates["Support"]["role_feasibility"]["possible_roles"]["Flex"]
        )
        self.assertEqual("infeasible", candidates["MidOnly"]["role_feasibility"]["status"])
        self.assertEqual(1, graph["role_infeasible_candidate_count"])

        hidden = index.graph(
            "Top",
            pinned=["Top", "Jungle", "Bottom", "Flex"],
            limit=50,
            hide_role_infeasible=True,
        )
        self.assertNotIn("MidOnly", [item["champion"] for item in hidden["neighbors"]])
        self.assertTrue(hidden["hide_role_infeasible"])

    def test_role_feasibility_is_explicit_when_unconfigured_or_incomplete(self) -> None:
        unconfigured = sample_index().graph("A", limit=1)
        incomplete = RelationshipIndex(
            [record(1, ("A", "B", "C", "D", "E"))],
            input_identifier="fixtures/incomplete-roles.csv",
            role_policy=MappingRolePolicy({"A": ["top"]}),
        ).graph("A", limit=1)

        self.assertEqual("not_configured", unconfigured["role_policy"])
        self.assertEqual(
            "not_evaluated", unconfigured["neighbors"][0]["role_feasibility"]["status"]
        )
        self.assertEqual("unknown", incomplete["neighbors"][0]["role_feasibility"]["status"])
        self.assertIn("No supplied role data", incomplete["neighbors"][0]["role_feasibility"]["reason"])

    def test_patch_and_league_filters_recompute_graph_from_scoped_population(self) -> None:
        index = RelationshipIndex(
            [
                record(1, ("A", "B", "C", "D", "E")),
                record(2, ("A", "X", "F", "G", "H"), patch="1.2", league="L2"),
                record(3, ("B", "X", "I", "J", "K"), patch="1.2", league="L2"),
            ],
            input_identifier="fixtures/filters.csv",
        )
        unfiltered = index.graph("A")
        filtered = index.graph("A", patch="1.1", leagues=["L1"])
        edge = next(item for item in filtered["neighbors"] if item["champion"] == "B")

        self.assertEqual(
            1.5,
            next(
                item for item in unfiltered["neighbors"] if item["champion"] == "B"
            )["lift"],
        )
        self.assertEqual(1, edge["co_pick_support"])
        self.assertEqual(1, edge["focal_support"])
        self.assertEqual(1, edge["neighbor_support"])
        self.assertEqual(2.0, edge["lift"])
        self.assertEqual([{"patch": "1.1", "count": 1}], edge["patch_distribution"])
        self.assertEqual(
            {"patch": "1.1", "leagues": ["L1"]},
            filtered["dataset"]["active_filters"],
        )
        self.assertEqual(1, filtered["dataset"]["games_in_scope"])
        self.assertEqual(2, filtered["dataset"]["team_observations_in_scope"])

    def test_patch_range_is_inclusive_and_uses_natural_patch_order(self) -> None:
        index = RelationshipIndex(
            [
                record(1, ("A", "B", "C", "D", "E"), patch="16.9"),
                record(2, ("A", "B", "F", "G", "H"), patch="16.10"),
                record(3, ("A", "B", "I", "J", "K"), patch="16.11"),
            ],
            input_identifier="fixtures/range.csv",
        )

        graph = index.graph("A", patch_from="16.10", patch_to="16.11")
        edge = next(item for item in graph["neighbors"] if item["champion"] == "B")

        self.assertEqual(["16.9", "16.10", "16.11"], graph["dataset"]["patches"])
        self.assertEqual(2, edge["co_pick_support"])
        self.assertEqual(
            [{"patch": "16.10", "count": 1}, {"patch": "16.11", "count": 1}],
            edge["patch_distribution"],
        )

    def test_invalid_context_filters_are_rejected(self) -> None:
        index = sample_index()

        with self.assertRaisesRegex(ValueError, "cannot be combined"):
            index.graph("A", patch="1.1", patch_from="1.1")
        with self.assertRaisesRegex(ValueError, "Unknown league"):
            index.graph("A", league="Missing")
        with self.assertRaisesRegex(ValueError, "must not be after"):
            index.graph("A", patch_from="1.2", patch_to="1.1")

    def test_multiple_and_empty_league_selections_are_explicit(self) -> None:
        index = sample_index()

        selected = index.graph("A", leagues=["L2", "L1", "L2"])
        empty = index.graph("A", leagues=[])

        self.assertEqual(["L1", "L2"], selected["dataset"]["active_filters"]["leagues"])
        self.assertEqual(6, selected["dataset"]["team_observations_in_scope"])
        self.assertEqual([], empty["dataset"]["active_filters"]["leagues"])
        self.assertEqual(0, empty["dataset"]["team_observations_in_scope"])
        self.assertEqual([], empty["neighbors"])
        self.assertEqual(0, empty["focal"]["baseline_support"])

    def test_patch_range_composes_with_multiple_leagues(self) -> None:
        index = RelationshipIndex(
            [
                record(1, ("A", "B", "C", "D", "E"), patch="1.1", league="L1"),
                record(2, ("A", "B", "F", "G", "H"), patch="1.2", league="L2"),
                record(3, ("A", "B", "I", "J", "K"), patch="1.2", league="L3"),
                record(4, ("A", "B", "M", "N", "O"), patch="1.3", league="L2"),
            ],
            input_identifier="fixtures/composed-filters.csv",
        )

        graph = index.graph(
            "A", patch_from="1.2", patch_to="1.2", leagues=["L1", "L2"]
        )
        edge = next(item for item in graph["neighbors"] if item["champion"] == "B")

        self.assertEqual(2, graph["dataset"]["team_observations_in_scope"])
        self.assertEqual(1, edge["co_pick_support"])
        self.assertEqual(
            {"patch_from": "1.2", "patch_to": "1.2", "leagues": ["L1", "L2"]},
            graph["dataset"]["active_filters"],
        )

    def test_top_region_configuration_is_explicit_and_limited_to_loaded_data(self) -> None:
        index = RelationshipIndex(
            [
                record(1, ("A", "B", "C", "D", "E"), league="LCK"),
                record(2, ("A", "F", "G", "H", "I"), league="LPL"),
                record(3, ("A", "J", "K", "L", "M"), league="NACL"),
            ],
            input_identifier="fixtures/top-regions.csv",
        )

        dataset = index.graph("A")["dataset"]

        self.assertEqual(("LCK", "LPL", "LEC", "LCS", "LCP"), TOP_REGION_LEAGUES)
        self.assertEqual(["LCK", "LPL"], dataset["top_region_leagues"])

    def test_graph_documents_separate_association_and_evidence_encodings(self) -> None:
        encoding = sample_index().graph("A")["encoding"]

        self.assertEqual("confidence_adjusted_lift", encoding["edge_width"])
        self.assertEqual("co_pick_support", encoding["edge_opacity"])
        self.assertEqual("baseline_support", encoding["node_size"])
        self.assertEqual(
            {"transform": "log1p", "minimum": 24.0, "maximum": 58.0},
            encoding["node_radius_scale"],
        )

    def test_node_radius_scale_is_bounded_monotonic_and_compressed(self) -> None:
        supports = [5, 50, 742]
        radii = [
            RelationshipIndex._node_radius(support, supports[0], supports[-1])
            for support in supports
        ]

        self.assertEqual(RelationshipIndex.MIN_NODE_RADIUS, radii[0])
        self.assertEqual(RelationshipIndex.MAX_NODE_RADIUS, radii[-1])
        self.assertLess(radii[0], radii[1])
        self.assertLess(radii[1], radii[2])
        linear_middle = radii[0] + (radii[-1] - radii[0]) * (50 - 5) / (742 - 5)
        self.assertGreater(radii[1], linear_middle)

    def test_equal_node_supports_use_midpoint_radius(self) -> None:
        self.assertEqual(41.0, RelationshipIndex._node_radius(10, 10, 10))

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
        self.assertIn("Thicker edge = stronger confidence-adjusted association", page)
        self.assertIn("Darker edge = more observed co-picks", page)
        self.assertIn("Larger node = champion appeared in more team drafts", page)
        self.assertIn("Relationship view", page)
        self.assertIn("Clockwise from top", page)
        self.assertIn("Minimum co-picks", page)
        self.assertIn("Pinned set", page)
        self.assertNotIn('id="pin-focus"', page)
        self.assertIn('id="pin-limit-status"', page)
        self.assertIn('id="clear-pins"', page)
        self.assertIn("renderGraph", script)
        self.assertIn("played: ${node.baseline_support}", script)
        self.assertIn("edgeOpacity(edge.co_pick_support)", script)
        self.assertIn("minimum_support", script)
        self.assertIn("patch_from", script)
        self.assertIn("Observations by patch", script)
        self.assertIn("Patch from", page)
        self.assertIn("League selections", page)
        self.assertIn("Select all", page)
        self.assertIn("Clear all", page)
        self.assertIn("Top regions", page)
        self.assertIn('id="filter-toggle"', page)
        self.assertIn('aria-controls="context-filters"', page)
        self.assertIn('id="context-filters"', page)
        self.assertIn('id="reset-view"', page)
        self.assertIn('id="hide-role-infeasible"', page)
        self.assertIn('id="role-summary"', page)
        self.assertIn('<g id="graph-viewport">', page)
        self.assertIn('query.append("league", league)', script)
        self.assertIn('graph.addEventListener("pointerdown"', script)
        self.assertIn("graph.setPointerCapture(event.pointerId)", script)
        self.assertIn('graphViewport.setAttribute("transform"', script)
        self.assertIn("updateViewportTransform();", script)
        self.assertIn('graph.addEventListener("wheel"', script)
        self.assertIn("pointer.x - (pointer.x - viewportPan.x) * ratio", script)
        self.assertIn("resetViewForNewFocus", script)
        self.assertIn("relationshipMode", script)
        self.assertIn('query.append("pinned", item)', script)
        self.assertIn("function pinToggle(champion, radius, pinned)", script)
        self.assertIn('event.stopPropagation()', script)
        self.assertIn('`Pin ${champion}`', script)
        self.assertIn('`Unpin ${champion}`', script)
        self.assertIn('group.append(nodeAction, pinToggle(node.champion, node.visual_radius, false))', script)
        self.assertIn('group.append(nodeAction, pinToggle(node.champion, radius, explicitlyPinned))', script)
        self.assertNotIn("pinFocusButton", script)
        self.assertNotIn("? [focusChampion]", script)
        self.assertIn("coverage_count", script)
        self.assertIn("exact_joint_support", script)
        self.assertIn("candidate.role_feasibility", script)
        self.assertIn('query.set("hide_role_infeasible", "true")', script)
        self.assertIn("role-infeasible", styles)
        self.assertIn("co-pick${edge.co_pick_support === 1", script)
        self.assertIn('r: node.visual_radius', script)
        self.assertIn("paint-order: stroke fill", styles)
        self.assertIn(".workspace", styles)
        self.assertIn("grid-template-rows: auto auto minmax(0, 1fr)", styles)
        self.assertIn("touch-action: none", styles)
        self.assertIn("cursor: grabbing", styles)
        self.assertEqual("A", payload["focal"]["champion"])
        self.assertEqual(["A"], payload["pinned_champions"])
        self.assertEqual(1, len(payload["neighbors"]))

    def test_graph_endpoint_accepts_repeated_pinned_champions(self) -> None:
        with urlopen(
            self.base_url + "/api/graph?champion=X&pinned=A&pinned=B&limit=50",
            timeout=2,
        ) as response:
            payload = json.load(response)

        self.assertEqual("X", payload["focal"]["champion"])
        self.assertEqual(["A", "B"], payload["pinned_champions"])
        candidate = next(
            item for item in payload["neighbors"] if item["champion"] == "C"
        )
        self.assertEqual(2, candidate["coverage_count"])
        self.assertEqual(2, len(candidate["pairwise_evidence"]))

    def test_graph_endpoint_accepts_mode_and_sample_control(self) -> None:
        with urlopen(
            self.base_url
            + "/api/graph?champion=A&mode=frequent&minimum_support=2",
            timeout=2,
        ) as response:
            payload = json.load(response)

        self.assertEqual("frequent", payload["mode"])
        self.assertEqual(2, payload["minimum_support"])
        self.assertTrue(
            all(item["co_pick_support"] >= 2 for item in payload["neighbors"])
        )

    def test_graph_endpoint_accepts_patch_range_and_league_filters(self) -> None:
        with urlopen(
            self.base_url
            + "/api/graph?champion=A&patch_from=1.2&patch_to=1.2&league=L2",
            timeout=2,
        ) as response:
            payload = json.load(response)

        self.assertEqual(
            {"patch_from": "1.2", "patch_to": "1.2", "leagues": ["L2"]},
            payload["dataset"]["active_filters"],
        )
        self.assertEqual(2, payload["dataset"]["team_observations_in_scope"])

    def test_graph_endpoint_accepts_multiple_or_no_leagues(self) -> None:
        with urlopen(
            self.base_url + "/api/graph?champion=A&league=L2&league=L1",
            timeout=2,
        ) as response:
            selected = json.load(response)
        with urlopen(
            self.base_url + "/api/graph?champion=A&league=",
            timeout=2,
        ) as response:
            empty = json.load(response)

        self.assertEqual(
            ["L1", "L2"], selected["dataset"]["active_filters"]["leagues"]
        )
        self.assertEqual(6, selected["dataset"]["team_observations_in_scope"])
        self.assertEqual([], empty["dataset"]["active_filters"]["leagues"])
        self.assertEqual(0, empty["dataset"]["team_observations_in_scope"])

    def test_unknown_champion_returns_bad_request(self) -> None:
        with self.assertRaises(HTTPError) as caught:
            urlopen(self.base_url + "/api/graph?champion=Missing", timeout=2)

        self.assertEqual(400, caught.exception.code)
        payload = json.load(caught.exception)
        self.assertIn("Unknown champion", payload["error"])


if __name__ == "__main__":
    unittest.main()
