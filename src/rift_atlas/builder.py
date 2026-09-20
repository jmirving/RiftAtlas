from __future__ import annotations

import csv
import json
import os
import tempfile
from collections import Counter
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Iterable, Iterator

from rift_atlas.contracts import validate_header
from rift_atlas.model import DraftRecord, PickEndpoint, RelationshipObservation


# Standard professional Summoner's Rift draft pick order.
# B1, R1/R2, B2/B3, R3, second ban phase, R4, B4/B5, R5.
PICK_SEQUENCE = (
    ("blue", 1),
    ("red", 1),
    ("red", 2),
    ("blue", 2),
    ("blue", 3),
    ("red", 3),
    ("red", 4),
    ("blue", 4),
    ("blue", 5),
    ("red", 5),
)


@dataclass(frozen=True)
class BuildStats:
    games: int
    relationships: int
    by_type: dict[str, int]

    def as_dict(self) -> dict[str, object]:
        return {
            "games": self.games,
            "relationships": self.relationships,
            "by_type": dict(sorted(self.by_type.items())),
        }


def read_drafts(path: str | Path) -> Iterator[DraftRecord]:
    input_path = Path(path)
    with input_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        validate_header(reader.fieldnames)
        for line_number, row in enumerate(reader, start=2):
            yield DraftRecord.from_row(row, line_number=line_number)


def _pick_endpoints(record: DraftRecord) -> tuple[list[PickEndpoint], list[PickEndpoint]]:
    event_for = {
        (side, pick): event
        for event, (side, pick) in enumerate(PICK_SEQUENCE, start=1)
    }

    blue = [
        PickEndpoint(
            champion=champion,
            side="blue",
            pick=pick,
            event=event_for[("blue", pick)],
        )
        for pick, champion in enumerate(record.blue_picks, start=1)
    ]
    red = [
        PickEndpoint(
            champion=champion,
            side="red",
            pick=pick,
            event=event_for[("red", pick)],
        )
        for pick, champion in enumerate(record.red_picks, start=1)
    ]
    return blue, red


def _undirected(
    relationship: str,
    first: PickEndpoint,
    second: PickEndpoint,
    record: DraftRecord,
) -> RelationshipObservation:
    endpoints = sorted(
        (first, second),
        key=lambda endpoint: (
            endpoint.champion.casefold(),
            endpoint.champion,
            endpoint.side,
            endpoint.pick,
        ),
    )
    return RelationshipObservation(
        relationship=relationship,
        source=endpoints[0],
        target=endpoints[1],
        context=record.context,
    )


def iter_relationships(record: DraftRecord) -> Iterator[RelationshipObservation]:
    blue, red = _pick_endpoints(record)

    for side_picks in (blue, red):
        for first, second in combinations(side_picks, 2):
            yield _undirected("co_pick", first, second, record)

    for blue_pick in blue:
        for red_pick in red:
            yield _undirected("opposition", blue_pick, red_pick, record)

    for blue_pick in blue:
        for red_pick in red:
            if blue_pick.event < red_pick.event:
                source, target = blue_pick, red_pick
            else:
                source, target = red_pick, blue_pick
            yield RelationshipObservation(
                relationship="draft_response",
                source=source,
                target=target,
                context=record.context,
            )


def iter_all_relationships(records: Iterable[DraftRecord]) -> Iterator[RelationshipObservation]:
    for record in records:
        yield from iter_relationships(record)


def build_relationship_file(input_path: str | Path, output_path: str | Path) -> BuildStats:
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    games = 0
    relationship_count = 0
    by_type: Counter[str] = Counter()

    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
        text=True,
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output:
            for record in read_drafts(input_path):
                games += 1
                for observation in iter_relationships(record):
                    output.write(
                        json.dumps(
                            observation.as_dict(),
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                    )
                    output.write("\n")
                    relationship_count += 1
                    by_type[observation.relationship] += 1

        os.replace(temporary_name, destination)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise

    return BuildStats(
        games=games,
        relationships=relationship_count,
        by_type=dict(by_type),
    )
