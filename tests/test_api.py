"""Synthetic boundary tests only. These do not validate the real processor artifact."""
from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from rift_atlas.api import create_app
from rift_atlas.contracts import REQUIRED_DRAFT_COLUMNS
from rift_atlas.dataset import Settings, load_dataset
from test_explorer import record


def write_fixture(directory: Path) -> Settings:
    """Explicit temporary test-only data; never installed as a deployment default."""
    records = [record(1, ("A", "B", "C", "D", "E")),
               record(2, ("A", "B", "C", "X", "Y"), patch="1.2", league="L2")]
    csv_path = directory / "test-only.csv"
    with csv_path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=REQUIRED_DRAFT_COLUMNS)
        writer.writeheader()
        for item in records:
            row = {"schema_version": "1", **asdict(item.context),
                   "blue_teamid": item.blue_teamid, "red_teamid": item.red_teamid}
            for side in ("blue", "red"):
                for kind in ("pick", "ban"):
                    for number, champion in enumerate(getattr(item, f"{side}_{kind}s"), 1):
                        row[f"{side}_{kind}{number}"] = champion
            writer.writerow(row)
    manifest = {
        "test_only": True, "dataset_id": "synthetic-test-only", "draft_schema_version": "1",
        "csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        "source": {"name": "Synthetic test fixture, not Oracle's Elixir", "url": "https://example.invalid/test-only"},
        "processor": {"repository": "https://github.com/jmirving/lol-pro-data-processor", "revision": "0" * 40, "artifact_id": "test-only-not-produced"},
        "generated_at": "2026-01-01T00:00:00Z", "source_retrieved_at": None,
        "attribution": "Synthetic test data only", "source_notices": "Not a production artifact",
        "coverage": {"game_count": 2, "patches": ["1.1", "1.2"], "leagues": ["L1", "L2"], "match_date_from": "2026-01-01", "match_date_to": "2026-01-01"},
        "roles": None,
    }
    manifest_path = directory / "test-only-manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    return Settings(csv_path, manifest_path)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.settings = write_fixture(Path(self.directory.name))

    def load(self):
        return load_dataset(self.settings, allow_test_data=True)

    def manifest(self, change):
        data = json.loads(self.settings.manifest_path.read_text())
        change(data)
        self.settings.manifest_path.write_text(json.dumps(data))

    def test_valid_test_fixture_metadata_and_no_paths(self):
        result = self.load()
        self.assertEqual(2, result.metadata["coverage"]["game_count"])
        self.assertEqual("not_evaluated", result.metadata["role_status"])
        self.assertNotIn(self.directory.name, json.dumps(result.metadata))
        self.assertEqual("synthetic-test-only", result.index.dataset_context["input_identifier"])
        self.manifest(lambda m: m.update(private_path="/private/secret"))
        self.assertNotIn("private_path", self.load().metadata)

    def test_default_loader_rejects_test_data(self):
        with self.assertRaisesRegex(ValueError, "Test-only"):
            load_dataset(self.settings)

    def test_missing_files_fail(self):
        self.settings.drafts_path.unlink()
        with self.assertRaisesRegex(ValueError, "DPS snapshot validation failed"):
            self.load()

    def test_invalid_manifest_fields_fail(self):
        original = self.settings.manifest_path.read_text()
        for key, value in [("coverage", {}), ("csv_sha256", "0" * 64), ("draft_schema_version", "2"),
                           ("source", {}), ("processor", {}), ("dataset_id", "/tmp/private"),
                           ("generated_at", "2026-01-01"), ("attribution", ""), ("roles", {})]:
            with self.subTest(key=key):
                self.settings.manifest_path.write_text(original)
                self.manifest(lambda m: m.update({key: value}))
                with self.assertRaises(ValueError):
                    self.load()

    def test_empty_corrupt_schema_and_duplicate_games_fail(self):
        original = self.settings.drafts_path.read_text()
        lines = original.splitlines(keepends=True)
        for content in [lines[0], "not,csv\n", original.replace("\n1,", "\n2,"), original + lines[1]]:
            with self.subTest(content=content[:40]):
                self.settings.drafts_path.write_text(content)
                self.manifest(lambda m: m.update(csv_sha256=hashlib.sha256(self.settings.drafts_path.read_bytes()).hexdigest()))
                with self.assertRaises(ValueError):
                    self.load()

    def configure_roles(self, mapping):
        path = Path(self.directory.name) / "roles.json"
        path.write_text(json.dumps(mapping))
        self.settings = Settings(self.settings.drafts_path, self.settings.manifest_path, path)
        self.manifest(lambda m: m.update(roles={"source": {"name": "Test roles", "url": "https://example.invalid/roles"}, "version": "test", "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}))

    def test_role_validation_and_incomplete_roles(self):
        for mapping in [{}, {"A": "top"}, {"A": ["invented"]}, {"A": [None]}, {"A": ["top"], "a": ["mid"]}]:
            with self.subTest(mapping=mapping):
                self.configure_roles(mapping)
                with self.assertRaises(ValueError):
                    self.load()
        self.configure_roles({"A": ["top"]})
        data = self.load().index.graph("A", pinned=["A", "B"])
        self.assertEqual("unknown", data["pinned_role_feasibility"]["status"])

    def test_readiness_and_lifespan_fail_closed(self):
        app = create_app(self.settings)
        with self.assertRaisesRegex(ValueError, "Test-only"):
            with TestClient(app):
                pass
        self.assertIsNone(app.state.dataset)
        client = TestClient(app)
        self.assertEqual(503, client.get("/healthz").status_code)
        self.assertEqual(503, client.get("/api/v1/dataset").status_code)


class ApiTests(unittest.TestCase):
    configure_roles = SnapshotTests.configure_roles
    manifest = SnapshotTests.manifest
    load = SnapshotTests.load

    def setUp(self):
        SnapshotTests.setUp(self)
        self.snapshot = self.load()
        self.app = create_app(self.settings, loader=lambda settings: self.snapshot)
        self.client = TestClient(self.app, raise_server_exceptions=False)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def test_metadata_search_assets_and_health(self):
        self.assertEqual(200, self.client.get("/healthz").status_code)
        self.assertEqual(self.snapshot.metadata, self.client.get("/api/v1/dataset").json())
        self.assertEqual(["A"], self.client.get("/api/v1/champions?q=a&limit=1").json()["champions"])
        for path in ["/", "/app.js", "/styles.css", "/openapi.json"]:
            self.assertEqual(200, self.client.get(path).status_code)
        self.assertIn("Draft Positioning System", self.client.get("/").text)
        self.assertIn("/api/v1/relationships", self.client.get("/app.js").text)
        self.assertEqual(404, self.client.get("/../pyproject.toml").status_code)

    def test_engine_equivalence_for_all_modes_and_filters(self):
        cases = [({}, {}), ({"pinned": ["A", "B"]}, {"pinned": ["A", "B"]}),
                 ({"league": ""}, {"leagues": []}), ({"league": ["L1", "L2"]}, {"leagues": ["L1", "L2"]}),
                 ({"patch": "1.2"}, {"patch": "1.2"}),
                 ({"patch_from": "1.1", "patch_to": "1.2", "minimum_support": 2}, {"patch_from": "1.1", "patch_to": "1.2", "minimum_support": 2})]
        for mode in ["established", "frequent", "surprising"]:
            for query, kwargs in cases:
                with self.subTest(mode=mode, query=query):
                    response = self.client.get("/api/v1/relationships", params={"champion": "a", "mode": mode, **query})
                    self.assertEqual(200, response.status_code, response.text)
                    result = response.json()
                    self.assertEqual("1", result.pop("api_version"))
                    self.assertEqual("synthetic-test-only", result.pop("dataset_id"))
                    self.assertEqual(self.snapshot.index.graph("a", mode=mode, **kwargs), result)
                    self.assertEqual(response.json(), self.client.get("/api/v1/relationships", params={"champion": "a", "mode": mode, **query}).json())
        empty = self.client.get("/api/v1/relationships?champion=A&league=").json()
        self.assertEqual(0, empty["dataset"]["team_observations_in_scope"])
        self.assertEqual([], empty["neighbors"])
        self.assertNotIn(self.directory.name, json.dumps(empty))

    def test_navigation_keeps_whole_pinned_composition(self):
        result = self.client.get("/api/v1/relationships?champion=C&pinned=A&pinned=B").json()
        self.assertEqual(["A", "B"], result["pinned_champions"])
        self.assertEqual("C", result["focal"]["champion"])

    def test_invalid_queries_are_consistent_400(self):
        for suffix in ["", "champion=Unknown", "champion=A&limit=51", "champion=A&limit=-1",
                       "champion=A&pinned=A&pinned=a", "champion=A&pinned=", "champion=A&pinned=A&pinned=B&pinned=C&pinned=D&pinned=E",
                       "champion=A&minimum_support=0", "champion=A&mode=bogus", "champion=A&relationship=opposition",
                       "champion=A&hide_role_infeasible=maybe", "champion=A&limit=1&limit=2", "champion=A&surprise=yes",
                       "champion=A&league=" + "x" * 129, "champion=" + "x" * 8300]:
            with self.subTest(suffix=suffix[:80]):
                response = self.client.get("/api/v1/relationships?" + suffix)
                self.assertEqual(400, response.status_code, response.text)
                self.assertEqual(["error"], list(response.json()))
        self.assertEqual(400, self.client.get("/api/v1/champions?limit=101").status_code)

    def test_unexpected_failure_is_generic(self):
        with patch.object(self.snapshot.index, "search", side_effect=RuntimeError("private/path")):
            result = self.client.get("/api/v1/champions")
        self.assertEqual(500, result.status_code)
        self.assertEqual({"error": "Internal server error"}, result.json())

    def test_role_api_matches_engine_for_present_and_infeasible_cases(self):
        self.configure_roles({"A": ["top"], "B": ["top"], "C": ["mid"]})
        self.app.state.dataset = self.load()
        for pins in [["A"], ["A", "B"], ["A", "X"]]:
            for hidden in [False, True]:
                response = self.client.get("/api/v1/relationships", params={"champion": "A", "pinned": pins, "hide_role_infeasible": str(hidden).lower()})
                actual = response.json()
                actual.pop("api_version"); actual.pop("dataset_id")
                self.assertEqual(self.app.state.dataset.index.graph("A", pinned=pins, hide_role_infeasible=hidden), actual)
