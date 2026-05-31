from __future__ import annotations

import datetime
import json
import logging
import os
from dataclasses import asdict, dataclass
from typing import Optional

import statsapi

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Team name / ID tables
# ---------------------------------------------------------------------------

# Full team name → abbrev (for UI dropdown)
TEAM_NAMES: dict[str, str] = {
    "Arizona Diamondbacks":   "AZ",
    "Atlanta Braves":         "ATL",
    "Baltimore Orioles":      "BAL",
    "Boston Red Sox":         "BOS",
    "Chicago Cubs":           "CHC",
    "Chicago White Sox":      "CWS",
    "Cincinnati Reds":        "CIN",
    "Cleveland Guardians":    "CLE",
    "Colorado Rockies":       "COL",
    "Detroit Tigers":         "DET",
    "Houston Astros":         "HOU",
    "Kansas City Royals":     "KC",
    "Los Angeles Angels":     "LAA",
    "Los Angeles Dodgers":    "LAD",
    "Miami Marlins":          "MIA",
    "Milwaukee Brewers":      "MIL",
    "Minnesota Twins":        "MIN",
    "New York Mets":          "NYM",
    "New York Yankees":       "NYY",
    "Athletics":              "ATH",
    "Philadelphia Phillies":  "PHI",
    "Pittsburgh Pirates":     "PIT",
    "San Diego Padres":       "SD",
    "Seattle Mariners":       "SEA",
    "San Francisco Giants":   "SF",
    "St. Louis Cardinals":    "STL",
    "Tampa Bay Rays":         "TB",
    "Texas Rangers":          "TEX",
    "Toronto Blue Jays":      "TOR",
    "Washington Nationals":   "WSH",
}

# abbrev → full name (reverse lookup)
ABBREV_TO_NAME: dict[str, str] = {v: k for k, v in TEAM_NAMES.items()}

# Sorted list of full names for UI
TEAM_NAME_OPTIONS: list[str] = sorted(TEAM_NAMES.keys())

# abbrev → MLB stats API team ID (same as logo_cache.TEAM_ID_MAP)
_TEAM_ID_MAP: dict[str, int] = {
    "AZ":  109, "ATL": 144, "BAL": 110, "BOS": 111, "CHC": 112,
    "CWS": 145, "CIN": 113, "CLE": 114, "COL": 115, "DET": 116,
    "HOU": 117, "KC":  118, "LAA": 108, "LAD": 119, "MIA": 146,
    "MIL": 158, "MIN": 142, "NYM": 121, "NYY": 147, "ATH": 133,
    "PHI": 143, "PIT": 134, "SD":  135, "SEA": 136, "SF":  137,
    "STL": 138, "TB":  139, "TEX": 140, "TOR": 141, "WSH": 120,
}

# ---------------------------------------------------------------------------
# Position grouping
# ---------------------------------------------------------------------------

POSITION_GROUPS: list[str] = [
    "Catchers",
    "Infielders",
    "Outfielders",
    "DH",
    "Starting Pitchers",
    "Relievers / Closers",
    "Two-Way",
    "Other",
]

ROSTER_TYPE_OPTIONS: list[str] = ["Active 26-Man", "40-Man", "Main Starters"]

_ROSTER_TYPE_API: dict[str, str] = {
    "Active 26-Man": "active",
    "40-Man":        "40Man",
}

# Canonical field positions for "Main Starters" mode (C → 1B → 2B → 3B → SS → LF → CF → RF)
_STARTER_POSITIONS: list[str] = ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF"]

_STARTER_POS_GROUP: dict[str, str] = {
    "C":  "Catchers",
    "1B": "Infielders", "2B": "Infielders", "3B": "Infielders", "SS": "Infielders",
    "LF": "Outfielders", "CF": "Outfielders", "RF": "Outfielders",
}

_STARTER_POS_NAME: dict[str, str] = {
    "C":  "Catcher",
    "1B": "First Base",  "2B": "Second Base", "3B": "Third Base", "SS": "Shortstop",
    "LF": "Left Field",  "CF": "Center Field", "RF": "Right Field",
}

# Position code → group name
def _group_for_position(pos_code: str, pos_type: str) -> str:
    code = pos_code.upper()
    ptype = pos_type.lower()
    if code == "C":
        return "Catchers"
    if code in ("1B", "2B", "3B", "SS"):
        return "Infielders"
    if code in ("LF", "CF", "RF", "OF"):
        return "Outfielders"
    if code == "DH":
        return "DH"
    if ptype in ("starter", "sp"):
        return "Starting Pitchers"
    if ptype in ("reliever", "closer", "rp", "cp"):
        return "Relievers / Closers"
    if code == "TWP":
        return "Two-Way"
    # Fallback for pitchers with generic type
    if ptype == "pitcher" or code == "P":
        return "Relievers / Closers"
    return "Other"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class RosterEntry:
    player_id: int
    jersey_number: str    # "" if unknown
    player_name: str
    position_code: str    # e.g. "SS", "SP", "C"
    position_name: str    # e.g. "Shortstop"
    position_group: str   # one of POSITION_GROUPS
    bats: str             # "L", "R", "S" (switch)
    throws: str           # "L", "R"
    age: int              # 0 if unknown


@dataclass
class RosterBlock:
    as_of: datetime.datetime
    team_abbrev: str
    team_name: str
    roster_type: str      # "Active 26-Man" or "40-Man"
    entries: list[RosterEntry]


# ---------------------------------------------------------------------------
# Fetch & cache
# ---------------------------------------------------------------------------

def _cache_path(working_dir: str, team_abbrev: str, roster_type: str) -> str:
    cache_dir = os.path.join(working_dir, "cache")
    os.makedirs(cache_dir, exist_ok=True)
    safe_type = roster_type.replace(" ", "_").replace("-", "")
    return os.path.join(cache_dir, f"roster_{team_abbrev}_{safe_type}.json")


def fetch_roster(
    team_abbrev: str,
    roster_type: str = "Active 26-Man",
    ttl_minutes: int = 15,
    working_dir: str = "",
    force_refresh: bool = False,
) -> RosterBlock:
    """
    Fetch the roster for *team_abbrev* from the MLB Stats API.
    Results are cached per-team/type in cache/roster_{abbrev}_{type}.json.
    """
    cache = _cache_path(working_dir, team_abbrev, roster_type) if working_dir else ""
    if cache and not force_refresh and os.path.isfile(cache):
        age_min = (
            datetime.datetime.now().timestamp()
            - os.path.getmtime(cache)
        ) / 60.0
        if age_min < ttl_minutes:
            try:
                with open(cache, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                return _block_from_dict(data)
            except Exception as exc:
                logger.warning("Cache read failed for %s roster: %s", team_abbrev, exc)

    block = (
        _do_fetch_main_starters(team_abbrev)
        if roster_type == "Main Starters"
        else _do_fetch(team_abbrev, roster_type)
    )

    if cache:
        try:
            with open(cache, "w", encoding="utf-8") as fh:
                json.dump(_block_to_dict(block), fh, indent=2, default=str)
        except Exception as exc:
            logger.warning("Cache write failed for %s roster: %s", team_abbrev, exc)

    return block


def _do_fetch(team_abbrev: str, roster_type: str) -> RosterBlock:
    team_id = _TEAM_ID_MAP.get(team_abbrev)
    if team_id is None:
        raise ValueError(f"Unknown team abbreviation: {team_abbrev!r}")

    api_type = _ROSTER_TYPE_API.get(roster_type, "active")
    raw = statsapi.get(
        "team_roster",
        {
            "teamId": team_id,
            "rosterType": api_type,
            "hydrate": "person(birthDate,currentAge,batSide,pitchHand)",
        },
    )

    splits = raw.get("roster", [])
    team_name = ABBREV_TO_NAME.get(team_abbrev, team_abbrev)

    entries: list[RosterEntry] = []
    for p in splits:
        person    = p.get("person", {})
        pos       = p.get("position", {})
        pos_code  = pos.get("abbreviation", "?")
        pos_name  = pos.get("name", "")
        pos_type  = pos.get("type", "")

        bats_side = person.get("batSide", {})
        pitch_hand = person.get("pitchHand", {})
        bats   = bats_side.get("code", "?") if isinstance(bats_side, dict) else "?"
        throws = pitch_hand.get("code", "?") if isinstance(pitch_hand, dict) else "?"

        try:
            age = int(person.get("currentAge", 0) or 0)
        except (ValueError, TypeError):
            age = 0

        entries.append(RosterEntry(
            player_id=int(person.get("id", 0)),
            jersey_number=p.get("jerseyNumber", "") or "",
            player_name=person.get("fullName", "Unknown"),
            position_code=pos_code,
            position_name=pos_name,
            position_group=_group_for_position(pos_code, pos_type),
            bats=bats,
            throws=throws,
            age=age,
        ))

    # Sort: by group order, then alphabetically within group
    group_order = {g: i for i, g in enumerate(POSITION_GROUPS)}
    entries.sort(key=lambda e: (
        group_order.get(e.position_group, 99),
        e.player_name,
    ))

    return RosterBlock(
        as_of=datetime.datetime.now(),
        team_abbrev=team_abbrev,
        team_name=team_name,
        roster_type=roster_type,
        entries=entries,
    )


def _do_fetch_main_starters(team_abbrev: str) -> RosterBlock:
    """Fetch the active roster and pick the player with the most gamesStarted
    at each of the 8 standard field positions (C, 1B, 2B, 3B, SS, LF, CF, RF).
    Uses a single API call with hydrated per-player fielding stats.
    """
    team_id = _TEAM_ID_MAP.get(team_abbrev)
    if team_id is None:
        raise ValueError(f"Unknown team abbreviation: {team_abbrev!r}")

    season    = datetime.date.today().year
    team_name = ABBREV_TO_NAME.get(team_abbrev, team_abbrev)

    raw = statsapi.get(
        "team_roster",
        {
            "teamId": team_id,
            "rosterType": "active",
            "hydrate": (
                f"person(currentAge,batSide,pitchHand,"
                f"stats(type=season,group=fielding,season={season},gameType=R))"
            ),
        },
    )

    roster = raw.get("roster", [])

    # best_at_pos: pos_code -> (gamesStarted, RosterEntry)
    best_at_pos: dict[str, tuple[int, RosterEntry]] = {}

    for p in roster:
        person     = p.get("person", {})
        jersey     = p.get("jerseyNumber", "") or ""
        bats_side  = person.get("batSide", {})
        pitch_hand = person.get("pitchHand", {})
        bats   = bats_side.get("code", "?")  if isinstance(bats_side,  dict) else "?"
        throws = pitch_hand.get("code", "?") if isinstance(pitch_hand, dict) else "?"
        try:
            age = int(person.get("currentAge", 0) or 0)
        except (ValueError, TypeError):
            age = 0

        for sg in person.get("stats", []):
            for split in sg.get("splits", []):
                pos_code = split.get("position", {}).get("abbreviation", "")
                if pos_code not in _STARTER_POSITIONS:
                    continue
                try:
                    gs = int(split.get("stat", {}).get("gamesStarted", 0) or 0)
                except (ValueError, TypeError):
                    gs = 0
                current_gs = best_at_pos.get(pos_code, (0, None))[0]
                if gs > current_gs:
                    best_at_pos[pos_code] = (gs, RosterEntry(
                        player_id=int(person.get("id", 0)),
                        jersey_number=jersey,
                        player_name=person.get("fullName", "Unknown"),
                        position_code=pos_code,
                        position_name=_STARTER_POS_NAME.get(pos_code, pos_code),
                        position_group=_STARTER_POS_GROUP[pos_code],
                        bats=bats,
                        throws=throws,
                        age=age,
                    ))

    # Assemble in canonical C → 1B → 2B → 3B → SS → LF → CF → RF order
    entries = [best_at_pos[pos][1] for pos in _STARTER_POSITIONS if pos in best_at_pos]

    return RosterBlock(
        as_of=datetime.datetime.now(),
        team_abbrev=team_abbrev,
        team_name=team_name,
        roster_type="Main Starters",
        entries=entries,
    )


# ---------------------------------------------------------------------------
# JSON serialization helpers
# ---------------------------------------------------------------------------

def _block_to_dict(block: RosterBlock) -> dict:
    return {
        "as_of": block.as_of.isoformat(),
        "team_abbrev": block.team_abbrev,
        "team_name": block.team_name,
        "roster_type": block.roster_type,
        "entries": [asdict(e) for e in block.entries],
    }


def _block_from_dict(data: dict) -> RosterBlock:
    return RosterBlock(
        as_of=datetime.datetime.fromisoformat(data["as_of"]),
        team_abbrev=data["team_abbrev"],
        team_name=data["team_name"],
        roster_type=data["roster_type"],
        entries=[RosterEntry(**e) for e in data["entries"]],
    )
