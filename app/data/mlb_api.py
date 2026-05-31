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
class StandingsEntry:
    team_id: int
    team_name: str
    team_abbrev: str
    division_id: int
    division_name: str
    league_name: str   # "AL" or "NL"
    wins: int
    losses: int
    pct: str           # e.g. ".600"
    gb: str            # e.g. "3.0" or "-" for first place
    home_record: str   # e.g. "25-12"
    away_record: str   # e.g. "20-15"
    last_ten: str      # e.g. "7-3"
    streak: str        # e.g. "W3"
    division_rank: int
    wild_card_rank: Optional[int] = None
    elimination_number: Optional[str] = None
    magic_number: Optional[str] = None


@dataclass
class StandingsBlock:
    """All standings data, grouped by division."""
    as_of: datetime.datetime
    divisions: dict[str, list[StandingsEntry]]   # key = "AL East" etc.
    leagues: dict[str, list[StandingsEntry]]     # key = "AL" / "NL"
    all_teams: list[StandingsEntry]


# ---------------------------------------------------------------------------
# Division / league maps
# ---------------------------------------------------------------------------

# MLB Stats API division IDs → (league short, display name)
DIVISION_MAP: dict[int, tuple[str, str]] = {
    200: ("AL", "AL West"),
    201: ("AL", "AL East"),
    202: ("AL", "AL Central"),
    203: ("NL", "NL West"),
    204: ("NL", "NL East"),
    205: ("NL", "NL Central"),
}

SCOPE_OPTIONS = [
    "All MLB",
    "AL",
    "NL",
    "AL East",
    "AL Central",
    "AL West",
    "NL East",
    "NL Central",
    "NL West",
]


def _split_record(split_records: list, record_type: str) -> str:
    """Return 'W-L' string for a given split type, or '0-0' if not found."""
    for r in split_records:
        if r.get("type") == record_type:
            return f"{r['wins']}-{r['losses']}"
    return "0-0"


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def fetch_standings(season: Optional[int] = None) -> StandingsBlock:
    """Fetch current-season standings from the MLB Stats API."""
    if season is None:
        season = datetime.date.today().year

    raw = statsapi.get(
        "standings",
        {
            "leagueId": "103,104",
            "season": season,
            "standingsTypes": "regularSeason",
            "hydrate": "team(league),division",
        },
    )

    if not isinstance(raw, dict) or not raw.get("records"):
        raise ValueError(
            f"Unexpected standings API response structure (season={season}). "
            f"Got keys: {list(raw.keys()) if isinstance(raw, dict) else type(raw).__name__}"
        )

    divisions: dict[str, list[StandingsEntry]] = {}
    leagues: dict[str, list[StandingsEntry]] = {"AL": [], "NL": []}
    all_teams: list[StandingsEntry] = []

    for record in raw.get("records", []):
        div_info = record.get("division", {})
        div_id = int(div_info.get("id", 0))
        league_short, division_name = DIVISION_MAP.get(div_id, ("??", "Unknown"))
        entries: list[StandingsEntry] = []

        for team_rec in record.get("teamRecords", []):
            team = team_rec.get("team", {})
            split_records = team_rec.get("records", {}).get("splitRecords", [])
            streak_info = team_rec.get("streak", {})
            streak_code = streak_info.get("streakCode", "")

            entry = StandingsEntry(
                team_id=int(team.get("id", 0)),
                team_name=team.get("name", ""),
                team_abbrev=team.get("abbreviation", "???"),
                division_id=div_id,
                division_name=division_name,
                league_name=league_short,
                wins=int(team_rec.get("wins", 0)),
                losses=int(team_rec.get("losses", 0)),
                pct=team_rec.get("winningPercentage", ".000"),
                gb=str(team_rec.get("gamesBack", "-")),
                home_record=_split_record(split_records, "home"),
                away_record=_split_record(split_records, "away"),
                last_ten=_split_record(split_records, "lastTen"),
                streak=streak_code,
                division_rank=int(team_rec.get("divisionRank", 0)),
                wild_card_rank=team_rec.get("wildCardRank"),
                elimination_number=str(team_rec.get("eliminationNumber") or ""),
                magic_number=str(team_rec.get("magicNumber") or ""),
            )
            entries.append(entry)
            all_teams.append(entry)
            leagues.setdefault(league_short, []).append(entry)

        divisions[division_name] = entries

    return StandingsBlock(
        as_of=datetime.datetime.now(),
        divisions=divisions,
        leagues=leagues,
        all_teams=all_teams,
    )


def filter_standings(block: StandingsBlock, scope: str) -> list[StandingsEntry]:
    """Return the subset of entries matching the selected scope."""
    if scope == "All MLB":
        return block.all_teams
    if scope in ("AL", "NL"):
        return block.leagues.get(scope, [])
    # Specific division
    return block.divisions.get(scope, [])


def group_by_division(entries: list[StandingsEntry]) -> dict[str, list[StandingsEntry]]:
    """Re-group a flat entry list by division name (preserves insertion order)."""
    result: dict[str, list[StandingsEntry]] = {}
    for e in entries:
        result.setdefault(e.division_name, []).append(e)
    return result


# ---------------------------------------------------------------------------
# Cache layer
# ---------------------------------------------------------------------------
# Memory cache: season → (StandingsBlock, fetched_at datetime)
_mem: dict[int, tuple[StandingsBlock, datetime.datetime]] = {}


def _disk_cache_path(working_dir: str, season: int) -> str:
    cache_dir = os.path.join(working_dir, "cache")
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f"standings_{season}.json")


def _block_to_dict(block: StandingsBlock) -> dict:
    """Serialize a StandingsBlock to a JSON-safe dict."""
    def entries_to_list(entries: list[StandingsEntry]) -> list[dict]:
        return [asdict(e) for e in entries]

    return {
        "as_of": block.as_of.isoformat(),
        "divisions": {k: entries_to_list(v) for k, v in block.divisions.items()},
        "leagues":   {k: entries_to_list(v) for k, v in block.leagues.items()},
        "all_teams": entries_to_list(block.all_teams),
    }


def _dict_to_block(data: dict) -> StandingsBlock:
    """Deserialize a StandingsBlock from a dict (as produced by _block_to_dict)."""
    def list_to_entries(lst: list[dict]) -> list[StandingsEntry]:
        return [StandingsEntry(**d) for d in lst]

    return StandingsBlock(
        as_of=datetime.datetime.fromisoformat(data["as_of"]),
        divisions={k: list_to_entries(v) for k, v in data["divisions"].items()},
        leagues=  {k: list_to_entries(v) for k, v in data["leagues"].items()},
        all_teams=list_to_entries(data["all_teams"]),
    )


def _write_disk_cache(block: StandingsBlock, working_dir: str, season: int) -> None:
    if not working_dir:
        return
    try:
        path = _disk_cache_path(working_dir, season)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(_block_to_dict(block), fh, indent=2)
        logger.debug("Standings disk cache written: %s", path)
    except Exception as exc:
        logger.warning("Could not write standings disk cache: %s", exc)


def _read_disk_cache(working_dir: str, season: int) -> Optional[StandingsBlock]:
    if not working_dir:
        return None
    path = _disk_cache_path(working_dir, season)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        block = _dict_to_block(data)
        logger.debug("Standings disk cache read: %s (as_of=%s)", path, block.as_of)
        return block
    except Exception as exc:
        logger.warning("Could not read standings disk cache: %s", exc)
        return None


def _is_fresh(fetched_at: datetime.datetime, ttl_minutes: int) -> bool:
    age = datetime.datetime.now() - fetched_at
    return age.total_seconds() < ttl_minutes * 60


def fetch_standings_cached(
    season: Optional[int] = None,
    ttl_minutes: int = 15,
    working_dir: str = "",
    force_refresh: bool = False,
) -> tuple[StandingsBlock, str]:
    """
    Return (StandingsBlock, source) where source is one of:
      "live"   – freshly fetched from the MLB API
      "memory" – served from in-process memory cache
      "disk"   – served from the on-disk JSON cache (e.g. after app restart)

    Cache hierarchy (fastest first):
      1. Memory cache  — checked first; zero I/O
      2. Disk cache    — used on a cold start or after app restart
      3. Live API      — fetched when both caches are cold or stale

    After a live fetch, both the memory and disk caches are updated.
    force_refresh=True skips caches and always fetches live.
    """
    if season is None:
        season = datetime.date.today().year

    if not force_refresh:
        # 1. Memory cache
        if season in _mem:
            block, fetched_at = _mem[season]
            if _is_fresh(fetched_at, ttl_minutes):
                return block, "memory"

        # 2. Disk cache
        disk_block = _read_disk_cache(working_dir, season)
        if disk_block is not None and _is_fresh(disk_block.as_of, ttl_minutes):
            # Warm the memory cache from disk
            _mem[season] = (disk_block, disk_block.as_of)
            return disk_block, "disk"

    # 3. Live fetch
    block = fetch_standings(season=season)
    _mem[season] = (block, block.as_of)
    _write_disk_cache(block, working_dir, season)
    return block, "live"


def clear_standings_cache(season: Optional[int] = None) -> None:
    """Evict memory cache entries. Pass season=None to clear all."""
    if season is None:
        _mem.clear()
    else:
        _mem.pop(season, None)

