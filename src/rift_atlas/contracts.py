from __future__ import annotations

DRAFT_SCHEMA_VERSION = "1"
RELATIONSHIP_SCHEMA_VERSION = "1"

CONTEXT_COLUMNS = (
    "gameid",
    "date",
    "year",
    "split",
    "league",
    "patch",
    "game",
)

TEAM_COLUMNS = ("blue_teamid", "red_teamid")

BLUE_PICK_COLUMNS = tuple(f"blue_pick{i}" for i in range(1, 6))
RED_PICK_COLUMNS = tuple(f"red_pick{i}" for i in range(1, 6))
BLUE_BAN_COLUMNS = tuple(f"blue_ban{i}" for i in range(1, 6))
RED_BAN_COLUMNS = tuple(f"red_ban{i}" for i in range(1, 6))

REQUIRED_DRAFT_COLUMNS = (
    "schema_version",
    *CONTEXT_COLUMNS,
    *TEAM_COLUMNS,
    *BLUE_PICK_COLUMNS,
    *RED_PICK_COLUMNS,
    *BLUE_BAN_COLUMNS,
    *RED_BAN_COLUMNS,
)


def validate_header(fieldnames: list[str] | None) -> None:
    if not fieldnames:
        raise ValueError("Draft artifact has no CSV header.")

    missing = [column for column in REQUIRED_DRAFT_COLUMNS if column not in fieldnames]
    if missing:
        raise ValueError(
            "Draft artifact is missing required columns: " + ", ".join(missing)
        )
