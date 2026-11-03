"""Release-data acceptance: use the committed real artifact and production loader."""
import json
from pathlib import Path
import unittest

from fastapi.testclient import TestClient
from rift_atlas.api import create_app
from rift_atlas.dataset import Settings


class RealSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.app = create_app(Settings(root / "data/drafts.csv", root / "data/manifest.json"))
        cls.client = TestClient(cls.app)
        cls.client.__enter__()
        cls.addClassCleanup(cls.client.__exit__, None, None, None)

    def test_real_provenance_and_readiness(self):
        self.assertEqual(200, self.client.get("/healthz").status_code)
        metadata = self.client.get("/api/v1/dataset").json()
        self.assertFalse(metadata["test_only"])
        self.assertEqual(9243, metadata["coverage"]["game_count"])
        self.assertEqual("2026-11-01", metadata["coverage"]["match_date_to"])
        self.assertEqual("not_evaluated", metadata["role_status"])
        self.assertEqual("16493bdcfa4d6b4a362b8cc37e4bbb78c7bbac41", metadata["processor"]["revision"])
        for private in ("/home/", "/mnt/", "C:\\\\", "source_path"):
            self.assertNotIn(private, json.dumps(metadata))
        self.assertIn("Maokai", self.client.get("/api/v1/champions?q=mao").json()["champions"])
        for asset in ("/", "/app.js", "/styles.css"):
            self.assertEqual(200, self.client.get(asset).status_code)

    def test_real_api_matches_engine_for_all_modes_and_populations(self):
        cases = [({}, {}),
                 ({"pinned": ["Maokai", "Jinx"]}, {"pinned": ["Maokai", "Jinx"]}),
                 ({"pinned": ["Maokai", "Jinx", "Ahri", "Nautilus"]}, {"pinned": ["Maokai", "Jinx", "Ahri", "Nautilus"]}),
                 ({"league": ["LCK", "LPL"]}, {"leagues": ["LCK", "LPL"]}),
                 ({"patch_from": "16.17", "patch_to": "16.20"}, {"patch_from": "16.17", "patch_to": "16.20"}),
                 ({"league": ""}, {"leagues": []})]
        for mode in ("established", "frequent", "surprising"):
            for query, kwargs in cases:
                with self.subTest(mode=mode, query=query):
                    params = {"champion": "Maokai", "mode": mode, **query}
                    response = self.client.get("/api/v1/relationships", params=params)
                    self.assertEqual(200, response.status_code, response.text)
                    actual = response.json()
                    self.assertEqual(self.app.state.dataset.metadata["dataset_id"], actual.pop("dataset_id"))
                    self.assertEqual("1", actual.pop("api_version"))
                    self.assertEqual(self.app.state.dataset.index.graph("Maokai", mode=mode, **kwargs), actual)
                    self.assertEqual(response.json(), self.client.get("/api/v1/relationships", params=params).json())

    def test_empty_scope_and_follow_preserve_real_composition(self):
        empty = self.client.get("/api/v1/relationships?champion=Maokai&league=").json()
        self.assertEqual(0, empty["dataset"]["team_observations_in_scope"])
        self.assertEqual([], empty["neighbors"])
        followed = self.client.get("/api/v1/relationships?champion=Ahri&pinned=Maokai&pinned=Jinx").json()
        self.assertEqual(["Maokai", "Jinx"], followed["pinned_champions"])
        self.assertEqual("Ahri", followed["focal"]["champion"])
