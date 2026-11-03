"""Validated immutable snapshots; no network access or fixture fallback."""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from rift_atlas.builder import read_drafts
from rift_atlas.contracts import DRAFT_SCHEMA_VERSION
from rift_atlas.recommendation import DEFAULT_ROLES, MappingRolePolicy
from rift_atlas.relationships import RelationshipIndex


@dataclass(frozen=True)
class Settings:
    drafts_path: Path
    manifest_path: Path
    roles_path: Path | None = None

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            Path(os.environ.get("DPS_DRAFTS_PATH", "data/drafts.csv")),
            Path(os.environ.get("DPS_MANIFEST_PATH", "data/manifest.json")),
            Path(os.environ["DPS_ROLES_PATH"]) if os.environ.get("DPS_ROLES_PATH") else None,
        )


@dataclass(frozen=True)
class Dataset:
    index: RelationshipIndex
    metadata: dict


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Manifest {name} must be a nonempty string")
    return value


def _timestamp(value: object, name: str) -> str:
    text = _text(value, name)
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"Manifest {name} must include a timezone")
    return text


def _source(value: object, name: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"Manifest {name} must be an object")
    label = _text(value.get("name"), f"{name}.name")
    url = _text(value.get("url"), f"{name}.url")
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError(f"Manifest {name}.url must be a public HTTPS URL")
    return {"name": label, "url": url}


def _checksum(path: Path, expected: object) -> None:
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("Manifest must contain a lowercase SHA-256 checksum")
    with path.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != expected:
        raise ValueError("Snapshot checksum does not match manifest")


def load_dataset(settings: Settings, *, allow_test_data: bool = False) -> Dataset:
    """Only explicit test code may opt into a manifest marked test_only."""
    try:
        manifest = json.loads(settings.manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("Manifest must be a JSON object")
        if type(manifest.get("test_only", False)) is not bool:
            raise ValueError("Manifest test_only must be a boolean")
        if manifest.get("test_only", False) and not allow_test_data:
            raise ValueError("Test-only snapshots cannot be served by the production loader")
        dataset_id = _text(manifest.get("dataset_id"), "dataset_id")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", dataset_id):
            raise ValueError("Manifest dataset_id must be a stable identifier, not a path")
        if manifest.get("draft_schema_version") != DRAFT_SCHEMA_VERSION:
            raise ValueError("Manifest draft_schema_version must be 1")
        _checksum(settings.drafts_path, manifest.get("csv_sha256"))
        source = _source(manifest.get("source"), "source")
        processor = manifest.get("processor")
        if not isinstance(processor, dict) or processor.get("repository") != "https://github.com/jmirving/lol-pro-data-processor":
            raise ValueError("Manifest must identify the canonical processor repository")
        revision = processor.get("revision")
        if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise ValueError("Manifest processor.revision must be a full commit SHA")
        artifact_id = processor.get("artifact_id")
        if artifact_id is not None:
            _text(artifact_id, "processor.artifact_id")
        generated_at = _timestamp(manifest.get("generated_at"), "generated_at")
        retrieved_at = manifest.get("source_retrieved_at")
        if retrieved_at is not None:
            _timestamp(retrieved_at, "source_retrieved_at")
        attribution = _text(manifest.get("attribution"), "attribution")
        notices = _text(manifest.get("source_notices"), "source_notices")
        records = list(read_drafts(settings.drafts_path))
        if not records:
            raise ValueError("Snapshot contains no usable games")
        if len({record.context.gameid for record in records}) != len(records):
            raise ValueError("Snapshot contains duplicate game IDs")
        dates = [datetime.fromisoformat(record.context.date.replace("Z", "+00:00")).date().isoformat() for record in records]
        coverage = {
            "game_count": len(records),
            "patches": sorted({record.context.patch for record in records}),
            "leagues": sorted({record.context.league for record in records}),
            "match_date_from": min(dates), "match_date_to": max(dates),
        }
        if not isinstance(manifest.get("coverage"), dict) or type(manifest["coverage"].get("game_count")) is not int or manifest["coverage"] != coverage:
            raise ValueError("Manifest coverage does not match snapshot counts, patches, leagues, or dates")
        role_policy = None
        roles_metadata = None
        if settings.roles_path is not None:
            role_info = manifest.get("roles")
            if not isinstance(role_info, dict):
                raise ValueError("Configured roles require manifest provenance")
            _checksum(settings.roles_path, role_info.get("sha256"))
            roles_metadata = {"source": _source(role_info.get("source"), "roles.source"),
                              "version": _text(role_info.get("version"), "roles.version"),
                              "sha256": role_info["sha256"]}
            mapping = json.loads(settings.roles_path.read_text(encoding="utf-8"))
            if not isinstance(mapping, dict) or not mapping:
                raise ValueError("Configured role mapping must be a nonempty object")
            folded = set()
            for champion, roles in mapping.items():
                if not champion.strip() or champion.casefold() in folded:
                    raise ValueError("Role champion names must be nonempty and distinct")
                folded.add(champion.casefold())
                if not isinstance(roles, list) or not roles or any(not isinstance(role, str) or role not in DEFAULT_ROLES for role in roles):
                    raise ValueError("Every configured role entry must list recognized roles")
            role_policy = MappingRolePolicy(mapping)
        elif manifest.get("roles") is not None:
            raise ValueError("Manifest declares roles but DPS_ROLES_PATH is not configured")
        index = RelationshipIndex(records, input_identifier=dataset_id, role_policy=role_policy)
        return Dataset(index, {
            "api_version": "1", "dataset_id": dataset_id,
            "draft_schema_version": DRAFT_SCHEMA_VERSION, "csv_sha256": manifest["csv_sha256"],
            "source": source, "processor": {"repository": processor["repository"], "revision": revision, "artifact_id": artifact_id},
            "generated_at": generated_at, "source_retrieved_at": retrieved_at,
            "coverage": coverage, "attribution": attribution, "source_notices": notices,
            "roles": roles_metadata, "role_status": "configured" if role_policy else "not_evaluated",
            "test_only": manifest.get("test_only", False),
            "capabilities": {"queryable_relationships": ["co_pick"], "export_only_relationships": ["opposition", "draft_response"],
                             "modes": list(RelationshipIndex.MODE_DESCRIPTIONS), "maximum_pins": 4},
        })
    except (OSError, ValueError, TypeError) as error:
        raise ValueError(f"DPS snapshot validation failed: {error}. Check DPS_DRAFTS_PATH, DPS_MANIFEST_PATH, and DPS_ROLES_PATH.") from error


if __name__ == "__main__":
    dataset = load_dataset(Settings.from_env())
    print(json.dumps({"dataset_id": dataset.metadata["dataset_id"], "coverage": dataset.metadata["coverage"]}))
