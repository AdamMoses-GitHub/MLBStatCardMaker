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
# Data models
# ---------------------------------------------------------------------------

@dataclass
class BatterEntry:
    player_id: int
    player_name: str
    jersey_number: str    # e.g. "99", or "" if unknown
    position: str         # e.g. "CF", "1B", "DH", or "" if unknown
    team_abbrev: str
    team_name: str
    league_name: str      # "AL" or "NL"
    division_name: str    # e.g. "AL East"
    # Counting / rate stats
    games: int
    at_bats: int
    plate_appearances: int
    hits: int
    home_runs: int
    rbi: int
    walks: int
    strikeouts: int
    stolen_bases: int
    avg: str              # e.g. ".312"
    obp: str              # e.g. ".390"
    slg: str              # e.g. ".541"
    ops: str              # e.g. ".931"


@dataclass
class BattersBlock:
    """All batting stats for a season, as fetched from the API."""
    as_of: datetime.datetime
    season: int
    entries: list[BatterEntry]


# ---------------------------------------------------------------------------
# Sort stat options
# ---------------------------------------------------------------------------

# (label shown in UI, BatterEntry field name)
SORT_STAT_OPTIONS: list[tuple[str, str]] = [
    ("OPS",  "ops"),
    ("AVG",  "avg"),
    ("HR",   "home_runs"),
    ("RBI",  "rbi"),
    ("OBP",  "obp"),
    ("SLG",  "slg"),
    ("H",    "hits"),
    ("BB",   "walks"),
    ("SB",   "stolen_bases"),
]

SORT_STAT_LABELS = [label for label, _ in SORT_STAT_OPTIONS]
SORT_STAT_FIELD_MAP = {label: field for label, field in SORT_STAT_OPTIONS}

# ---------------------------------------------------------------------------
# Scope options
# ---------------------------------------------------------------------------

# All valid scope values — group scopes + individual team abbreviations
GROUP_SCOPES = [
    "All MLB",
    "AL", "NL",
    "AL East", "AL Central", "AL West",
    "NL East", "NL Central", "NL West",
]

# All 30 MLB team abbreviations (must match what the API returns)
ALL_TEAM_ABBREVS = [
    "AZ",  "ATL", "BAL", "BOS", "CHC",
    "CWS", "CIN", "CLE", "COL", "DET",
    "HOU", "KC",  "LAA", "LAD", "MIA",
    "MIL", "MIN", "NYM", "NYY", "ATH",
    "PHI", "PIT", "SD",  "SEA", "SF",
    "STL", "TB",  "TEX", "TOR", "WSH",
]

BATTER_SCOPE_OPTIONS = GROUP_SCOPES + ALL_TEAM_ABBREVS


def is_team_scope(scope: str) -> bool:
    """True if scope is a single team abbreviation rather than a group."""
    return scope in ALL_TEAM_ABBREVS


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def fetch_batters(season: Optional[int] = None) -> BattersBlock:
    """
    Fetch individual batting stats for the given season from the MLB Stats API.
    Returns a BattersBlock with all qualifying players.
    """
    if season is None:
        season = datetime.date.today().year

    raw = statsapi.get(
        "stats",
        {
            "stats": "season",
            "season": season,
            "group": "hitting",
            "gameType": "R",
            "limit": 1000,
            "offset": 0,
            "hydrate": "person,team(league,division)",
            "playerPool": "ALL",
        },
    )

    people = raw.get("stats", [{}])[0].get("splits", [])
    if not people:
        raise ValueError(
            f"Unexpected batting stats API response (season={season}). "
            f"Got keys: {list(raw.keys()) if isinstance(raw, dict) else type(raw).__name__}"
        )

    entries: list[BatterEntry] = []
    for split in people:
        stat = split.get("stat", {})
        player = split.get("player", {})
        team = split.get("team", {})
        league = team.get("league", {})
        division = team.get("division", {})

        # Map league id → short name
        league_id = int(league.get("id", 0))
        league_short = "AL" if league_id == 103 else ("NL" if league_id == 104 else "??")

        # Division name — normalise to match standings (e.g. "AL East")
        division_name = division.get("name", "Unknown")
        # API returns e.g. "American League East" — shorten
        division_name = _normalise_division_name(division_name)

        def _s(key: str, default: str = ".000") -> str:
            val = stat.get(key, default)
            return val if val and val != "" else default

        def _i(key: str) -> int:
            try:
                return int(stat.get(key, 0) or 0)
            except (ValueError, TypeError):
                return 0

        # Compute OPS if the API doesn't return it directly
        raw_ops = stat.get("ops", "")
        if not raw_ops:
            try:
                raw_ops = f"{float(_s('obp', '.000')) + float(_s('slg', '.000')):.3f}"
            except ValueError:
                raw_ops = ".000"

        pos_obj = player.get("primaryPosition", {})
        position = pos_obj.get("abbreviation", "") if isinstance(pos_obj, dict) else ""

        entry = BatterEntry(
            player_id=int(player.get("id", 0)),
            player_name=player.get("fullName", ""),
            jersey_number=str(player.get("primaryNumber", "") or ""),
            position=position,
            team_abbrev=team.get("abbreviation", "???"),
            team_name=team.get("name", ""),
            league_name=league_short,
            division_name=division_name,
            games=_i("gamesPlayed"),
            at_bats=_i("atBats"),
            plate_appearances=_i("plateAppearances"),
            hits=_i("hits"),
            home_runs=_i("homeRuns"),
            rbi=_i("rbi"),
            walks=_i("baseOnBalls"),
            strikeouts=_i("strikeOuts"),
            stolen_bases=_i("stolenBases"),
            avg=_s("avg"),
            obp=_s("obp"),
            slg=_s("slg"),
            ops=raw_ops,
        )
        entries.append(entry)

    return BattersBlock(
        as_of=datetime.datetime.now(),
        season=season,
        entries=entries,
    )


def _normalise_division_name(name: str) -> str:
    """Convert long division name from API to short form matching SCOPE_OPTIONS."""
    mapping = {
        "American League East":    "AL East",
        "American League Central": "AL Central",
        "American League West":    "AL West",
        "National League East":    "NL East",
        "National League Central": "NL Central",
        "National League West":    "NL West",
    }
    return mapping.get(name, name)


# ---------------------------------------------------------------------------
# Filter / sort
# ---------------------------------------------------------------------------

def filter_batters(block: BattersBlock, scope: str) -> list[BatterEntry]:
    """Return entries matching the given scope."""
    entries = block.entries
    if scope == "All MLB":
        return list(entries)
    if scope in ("AL", "NL"):
        return [e for e in entries if e.league_name == scope]
    if scope in ("AL East", "AL Central", "AL West",
                 "NL East", "NL Central", "NL West"):
        return [e for e in entries if e.division_name == scope]
    # Team scope — single team abbreviation
    return [e for e in entries if e.team_abbrev == scope]


def sort_and_trim(
    entries: list[BatterEntry],
    sort_label: str,
    top_n: int,
    min_pa: int,
) -> list[BatterEntry]:
    """
    Filter by minimum plate appearances, sort by the chosen stat (descending),
    and return the top N results.
    """
    field = SORT_STAT_FIELD_MAP.get(sort_label, "ops")
    filtered = [e for e in entries if e.plate_appearances >= min_pa]

    def sort_key(e: BatterEntry):
        val = getattr(e, field)
        if isinstance(val, str):
            # Strip leading '.' for floats stored as strings like ".312"
            try:
                return float(val)
            except ValueError:
                return 0.0
        return float(val) if val is not None else 0.0

    filtered.sort(key=sort_key, reverse=True)
    return filtered[:top_n]


# ---------------------------------------------------------------------------
# Cache layer
# ---------------------------------------------------------------------------

_mem: dict[int, tuple[BattersBlock, datetime.datetime]] = {}


def _disk_cache_path(working_dir: str, season: int) -> str:
    cache_dir = os.path.join(working_dir, "cache")
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f"batters_{season}.json")


def _block_to_dict(block: BattersBlock) -> dict:
    return {
        "as_of": block.as_of.isoformat(),
        "season": block.season,
        "entries": [asdict(e) for e in block.entries],
    }


def _dict_to_block(data: dict) -> BattersBlock:
    return BattersBlock(
        as_of=datetime.datetime.fromisoformat(data["as_of"]),
        season=data["season"],
        entries=[BatterEntry(**d) for d in data["entries"]],
    )


def _write_disk_cache(block: BattersBlock, working_dir: str, season: int) -> None:
    if not working_dir:
        return
    try:
        path = _disk_cache_path(working_dir, season)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(_block_to_dict(block), fh, indent=2)
        logger.debug("Batters disk cache written: %s", path)
    except Exception as exc:
        logger.warning("Could not write batters disk cache: %s", exc)


def _read_disk_cache(working_dir: str, season: int) -> Optional[BattersBlock]:
    if not working_dir:
        return None
    path = _disk_cache_path(working_dir, season)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        block = _dict_to_block(data)
        logger.debug("Batters disk cache read: %s (as_of=%s)", path, block.as_of)
        return block
    except Exception as exc:
        logger.warning("Could not read batters disk cache: %s", exc)
        return None


def _is_fresh(fetched_at: datetime.datetime, ttl_minutes: int) -> bool:
    age = datetime.datetime.now() - fetched_at
    return age.total_seconds() < ttl_minutes * 60


def fetch_batters_cached(
    season: Optional[int] = None,
    ttl_minutes: int = 15,
    working_dir: str = "",
    force_refresh: bool = False,
) -> tuple[BattersBlock, str]:
    """
    Return (BattersBlock, source) where source is 'live', 'memory', or 'disk'.
    Cache hierarchy: memory → disk → live API.
    """
    if season is None:
        season = datetime.date.today().year

    if not force_refresh:
        if season in _mem:
            block, fetched_at = _mem[season]
            if _is_fresh(fetched_at, ttl_minutes):
                return block, "memory"
        disk_block = _read_disk_cache(working_dir, season)
        if disk_block is not None and _is_fresh(disk_block.as_of, ttl_minutes):
            _mem[season] = (disk_block, disk_block.as_of)
            return disk_block, "disk"

    block = fetch_batters(season=season)
    _mem[season] = (block, block.as_of)
    _write_disk_cache(block, working_dir, season)
    return block, "live"


def clear_batters_cache(season: Optional[int] = None) -> None:
    if season is None:
        _mem.clear()
    else:
        _mem.pop(season, None)
