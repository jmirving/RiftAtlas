from __future__ import annotations

from dataclasses import dataclass

from rift_atlas.contracts import DRAFT_SCHEMA_VERSION, RELATIONSHIP_SCHEMA_VERSION


@dataclass(frozen=True)
class DraftContext:
    gameid: str
    date: str
    year: str
    split: str
    league: str
    patch: str
    game: str


@dataclass(frozen=True)
class DraftRecord:
    context: DraftContext
    blue_teamid: str
    red_teamid: str
    blue_picks: tuple[str, ...]
    red_picks: tuple[str, ...]
    blue_bans: tuple[str, ...]
    red_bans: tuple[str, ...]

    @classmethod
    def from_row(cls, row: dict[str, str], line_number: int | None = None) -> "DraftRecord":
        location = f" on CSV line {line_number}" if line_number is not None else ""

        def required(name: str) -> str:
            value = (row.get(name) or "").strip()
            if not value:
                raise ValueError(f"Missing required value {name}{location}.")
            return value

        schema_version = required("schema_version")
        if schema_version != DRAFT_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported drafts schema_version={schema_version!r}{location}; "
                f"expected {DRAFT_SCHEMA_VERSION!r}."
            )

        blue_teamid = required("blue_teamid")
        red_teamid = required("red_teamid")
        if blue_teamid == red_teamid:
            raise ValueError(f"Blue and red team IDs are identical{location}.")

        blue_picks = tuple(required(f"blue_pick{i}") for i in range(1, 6))
        red_picks = tuple(required(f"red_pick{i}") for i in range(1, 6))
        blue_bans = tuple(required(f"blue_ban{i}") for i in range(1, 6))
        red_bans = tuple(required(f"red_ban{i}") for i in range(1, 6))

        all_picks = blue_picks + red_picks
        if len(set(all_picks)) != len(all_picks):
            raise ValueError(f"Duplicate champion pick detected{location}.")

        return cls(
            context=DraftContext(
                gameid=required("gameid"),
                date=required("date"),
                year=required("year"),
                split=required("split"),
                league=required("league"),
                patch=required("patch"),
                game=required("game"),
            ),
            blue_teamid=blue_teamid,
            red_teamid=red_teamid,
            blue_picks=blue_picks,
            red_picks=red_picks,
            blue_bans=blue_bans,
            red_bans=red_bans,
        )


@dataclass(frozen=True)
class PickEndpoint:
    champion: str
    side: str
    pick: int
    event: int


@dataclass(frozen=True)
class RelationshipObservation:
    relationship: str
    source: PickEndpoint
    target: PickEndpoint
    context: DraftContext

    def as_dict(self) -> dict[str, str | int]:
        return {
            "schema_version": RELATIONSHIP_SCHEMA_VERSION,
            "relationship": self.relationship,
            "source": self.source.champion,
            "target": self.target.champion,
            "source_side": self.source.side,
            "target_side": self.target.side,
            "source_pick": self.source.pick,
            "target_pick": self.target.pick,
            "source_event": self.source.event,
            "target_event": self.target.event,
            "gameid": self.context.gameid,
            "date": self.context.date,
            "year": self.context.year,
            "split": self.context.split,
            "league": self.context.league,
            "patch": self.context.patch,
            "game": self.context.game,
        }
