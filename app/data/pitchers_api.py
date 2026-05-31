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
class PitcherEntry:
    player_id: int
    player_name: str
    jersey_number: str     # e.g. "35", or "" if unknown
    team_abbrev: str
    team_name: str
    league_name: str       # "AL" or "NL"
    division_name: str     # e.g. "AL East"
    pitcher_type: str      # "SP" or "RP"
    wins: int
    losses: int
    era: str               # e.g. "3.45"
    games: int
    games_started: int
    innings_pitched: str   # decimal string, e.g. "67.3"
    strikeouts: int
    walks: int
    whip: str              # e.g. "1.12"
    saves: int
    holds: int
    home_runs: int


@dataclass
class PitchersBlock:
    """All pitching stats for a season, as fetched from the API."""
    as_of: datetime.datetime
    season: int
    entries: list[PitcherEntry]


# ---------------------------------------------------------------------------
# Sort stat options
# ---------------------------------------------------------------------------

# (label shown in UI, PitcherEntry field name)
SORT_STAT_OPTIONS: list[tuple[str, str]] = [
    ("ERA",  "era"),
    ("WHIP", "whip"),
    ("W",    "wins"),
    ("SO",   "strikeouts"),
    ("IP",   "innings_pitched"),
    ("SV",   "saves"),
    ("HLD",  "holds"),
    ("BB",   "walks"),
    ("HR",   "home_runs"),
    ("L",    "losses"),
]

SORT_STAT_LABELS = [label for label, _ in SORT_STAT_OPTIONS]
SORT_STAT_FIELD_MAP = {label: field for label, field in SORT_STAT_OPTIONS}

# Stats where lower is better — sorted ascending
ASCENDING_STATS: frozenset[str] = frozenset({"ERA", "WHIP", "BB", "HR", "L"})

# ---------------------------------------------------------------------------
# Scope / type options
# ---------------------------------------------------------------------------

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

PITCHER_SCOPE_OPTIONS = GROUP_SCOPES + ALL_TEAM_ABBREVS
PITCHER_TYPE_OPTIONS = ["All", "Starters", "Relievers"]


def is_team_scope(scope: str) -> bool:
    """True if scope is a single team abbreviation rather than a group."""
    return scope in ALL_TEAM_ABBREVS


# ---------------------------------------------------------------------------
# IP conversion helpers
# ---------------------------------------------------------------------------

def _ip_traditional_to_decimal(ip_str: str) -> str:
    """
    Convert MLB traditional IP notation to a decimal string for display.

    Traditional: '67.1' means 67 innings + 1 out (1/3 inning).
    Decimal:     '67.1' → '67.3',  '67.2' → '67.7',  '67.0' → '67.0'.
    """
    try:
        parts = str(ip_str).split(".")
        whole = int(parts[0])
        thirds = int(parts[1]) if len(parts) > 1 else 0
        if thirds == 0:
            return f"{whole}.0"
        if thirds == 1:
            return f"{whole + 1 / 3:.1f}"   # 67.333… → "67.3"
        return f"{whole + 2 / 3:.1f}"        # 67.666… → "67.7"
    except (ValueError, IndexError):
        return "0.0"


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def fetch_pitchers(season: Optional[int] = None) -> PitchersBlock:
    """
    Fetch individual pitching stats for the given season from the MLB Stats API.
    Returns a PitchersBlock with all players.
    """
    if season is None:
        season = datetime.date.today().year

    raw = statsapi.get(
        "stats",
        {
            "stats": "season",
            "season": season,
            "group": "pitching",
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
            f"Unexpected pitching stats API response (season={season}). "
            f"Got keys: {list(raw.keys()) if isinstance(raw, dict) else type(raw).__name__}"
        )

    entries: list[PitcherEntry] = []
    for split in people:
        stat   = split.get("stat",   {})
        player = split.get("player", {})
        team   = split.get("team",   {})
        league   = team.get("league",   {})
        division = team.get("division", {})

        league_id    = int(league.get("id", 0))
        league_short = "AL" if league_id == 103 else ("NL" if league_id == 104 else "??")
        division_name = _normalise_division_name(division.get("name", "Unknown"))

        def _s(key: str, default: str = "0.00") -> str:
            val = stat.get(key, default)
            return val if val and val != "" else default

        def _i(key: str) -> int:
            try:
                return int(stat.get(key, 0) or 0)
            except (ValueError, TypeError):
                return 0

        games_started = _i("gamesStarted")
        pitcher_type  = "SP" if games_started > 0 else "RP"

        ip_raw     = stat.get("inningsPitched", "0.0") or "0.0"
        ip_decimal = _ip_traditional_to_decimal(ip_raw)

        era_raw = stat.get("era", "") or ""
        if not era_raw or era_raw in ("-.--", "-"):
            era_raw = "99.99"   # sentinel — no ERA (0 IP or no ER allowed)

        whip_raw = stat.get("whip", "") or ""
        if not whip_raw or whip_raw in ("-.--", "-"):
            ip_f = float(ip_decimal)
            if ip_f > 0:
                whip_raw = f"{(_i('baseOnBalls') + _i('hits')) / ip_f:.2f}"
            else:
                whip_raw = "99.99"

        entry = PitcherEntry(
            player_id     = int(player.get("id", 0)),
            player_name   = player.get("fullName", ""),
            jersey_number = str(player.get("primaryNumber", "") or ""),
            team_abbrev   = team.get("abbreviation", "???"),
            team_name     = team.get("name", ""),
            league_name   = league_short,
            division_name = division_name,
            pitcher_type  = pitcher_type,
            wins          = _i("wins"),
            losses        = _i("losses"),
            era           = era_raw,
            games         = _i("gamesPlayed"),
            games_started = games_started,
            innings_pitched = ip_decimal,
            strikeouts    = _i("strikeOuts"),
            walks         = _i("baseOnBalls"),
            whip          = whip_raw,
            saves         = _i("saves"),
            holds         = _i("holds"),
            home_runs     = _i("homeRuns"),
        )
        entries.append(entry)

    return PitchersBlock(
        as_of=datetime.datetime.now(),
        season=season,
        entries=entries,
    )


def _normalise_division_name(name: str) -> str:
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

def filter_pitchers(
    block: PitchersBlock,
    scope: str,
    pitcher_type: str,
) -> list[PitcherEntry]:
    """Return entries matching the given scope and pitcher type."""
    entries: list[PitcherEntry] = block.entries

    # --- Scope ---
    if scope == "All MLB":
        pass
    elif scope in ("AL", "NL"):
        entries = [e for e in entries if e.league_name == scope]
    elif scope in ("AL East", "AL Central", "AL West",
                   "NL East", "NL Central", "NL West"):
        entries = [e for e in entries if e.division_name == scope]
    else:
        # Single team abbreviation
        entries = [e for e in entries if e.team_abbrev == scope]

    # --- Pitcher type ---
    if pitcher_type == "Starters":
        entries = [e for e in entries if e.pitcher_type == "SP"]
    elif pitcher_type == "Relievers":
        entries = [e for e in entries if e.pitcher_type == "RP"]

    return list(entries)


def sort_and_trim(
    entries: list[PitcherEntry],
    sort_label: str,
    top_n: int,
    min_ip: float,
    min_g: int,
    pitcher_type: str,
) -> list[PitcherEntry]:
    """
    Apply the qualifying threshold, sort by the chosen stat, return top N.

    Relievers qualify by min games appeared; all others by min innings pitched.
    ERA / WHIP / BB / HR / L sort ascending (lower is better).
    """
    # Qualifier
    if pitcher_type == "Relievers":
        filtered = [e for e in entries if e.games >= min_g]
    else:
        filtered = [e for e in entries
                    if float(e.innings_pitched) >= min_ip]

    field     = SORT_STAT_FIELD_MAP.get(sort_label, "era")
    ascending = sort_label in ASCENDING_STATS

    def sort_key(e: PitcherEntry) -> float:
        val = getattr(e, field)
        if isinstance(val, str):
            try:
                return float(val)
            except ValueError:
                return 0.0
        return float(val) if val is not None else 0.0

    filtered.sort(key=sort_key, reverse=not ascending)
    return filtered[:top_n]


# ---------------------------------------------------------------------------
# Cache layer
# ---------------------------------------------------------------------------

_mem: dict[int, tuple[PitchersBlock, datetime.datetime]] = {}


def _disk_cache_path(working_dir: str, season: int) -> str:
    cache_dir = os.path.join(working_dir, "cache")
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f"pitchers_{season}.json")


def _block_to_dict(block: PitchersBlock) -> dict:
    return {
        "as_of":   block.as_of.isoformat(),
        "season":  block.season,
        "entries": [asdict(e) for e in block.entries],
    }


def _dict_to_block(data: dict) -> PitchersBlock:
    return PitchersBlock(
        as_of=datetime.datetime.fromisoformat(data["as_of"]),
        season=data["season"],
        entries=[PitcherEntry(**d) for d in data["entries"]],
    )


def _write_disk_cache(block: PitchersBlock, working_dir: str, season: int) -> None:
    if not working_dir:
        return
    try:
        path = _disk_cache_path(working_dir, season)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(_block_to_dict(block), fh, indent=2)
        logger.debug("Pitchers disk cache written: %s", path)
    except Exception as exc:
        logger.warning("Could not write pitchers disk cache: %s", exc)


def _read_disk_cache(working_dir: str, season: int) -> Optional[PitchersBlock]:
    if not working_dir:
        return None
    path = _disk_cache_path(working_dir, season)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        block = _dict_to_block(data)
        logger.debug("Pitchers disk cache read: %s (as_of=%s)", path, block.as_of)
        return block
    except Exception as exc:
        logger.warning("Could not read pitchers disk cache: %s", exc)
        return None


def _is_fresh(fetched_at: datetime.datetime, ttl_minutes: int) -> bool:
    age = datetime.datetime.now() - fetched_at
    return age.total_seconds() < ttl_minutes * 60


def fetch_pitchers_cached(
    season: Optional[int] = None,
    ttl_minutes: int = 15,
    working_dir: str = "",
    force_refresh: bool = False,
) -> tuple[PitchersBlock, str]:
    """
    Return (PitchersBlock, source) where source is 'live', 'memory', or 'disk'.
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

    block = fetch_pitchers(season=season)
    _mem[season] = (block, block.as_of)
    _write_disk_cache(block, working_dir, season)
    return block, "live"


def clear_pitchers_cache(season: Optional[int] = None) -> None:
    if season is None:
        _mem.clear()
    else:
        _mem.pop(season, None)
