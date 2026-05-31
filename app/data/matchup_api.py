from __future__ import annotations

import datetime
import json
import logging
import os
from dataclasses import asdict, dataclass
from typing import Optional

import statsapi

from app.data.roster_api import ABBREV_TO_NAME, TEAM_NAME_OPTIONS, TEAM_NAMES, _TEAM_ID_MAP

logger = logging.getLogger(__name__)

# Re-export for UI convenience
MATCHUP_TEAM_NAME_OPTIONS = TEAM_NAME_OPTIONS

# ---------------------------------------------------------------------------
# Stat sets
# ---------------------------------------------------------------------------

STAT_SET_OPTIONS = ["Standard", "Extended"]

# Rows in each set: (label, TeamStats field, lower_is_better)
_STANDARD_ROWS: list[tuple[str, str, bool]] = [
    ("W-L",    "wl",         False),
    ("RS/G",   "rs_per_g",   False),
    ("ERA",    "era",        True),
    ("WHIP",   "whip",       True),
    ("AVG",    "avg",        False),
    ("HR",     "hr",         False),
    ("OPS",    "ops",        False),
    ("SO",     "so_pitch",   False),
    ("SB",     "sb",         False),
    ("SV",     "sv",         False),
]

_EXTENDED_ROWS: list[tuple[str, str, bool]] = _STANDARD_ROWS + [
    ("RA/G",   "ra_per_g",   True),
    ("BB",     "bb_pitch",   True),
    ("HR Alw", "hr_pitch",   True),
    ("SHO",    "sho",        False),
]


def get_stat_rows(stat_set: str) -> list[tuple[str, str, bool]]:
    return _EXTENDED_ROWS if stat_set == "Extended" else _STANDARD_ROWS


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class TeamStats:
    team_abbrev: str
    team_name: str
    # Derived display values — all stored as strings for display
    wl: str          # "94-68"
    wins: int
    losses: int
    rs_per_g: str    # "5.24"
    ra_per_g: str    # "4.23"
    avg: str         # ".251"
    hr: int
    ops: str         # ".787"
    sb: int
    era: str         # "3.91"
    whip: str        # "1.25"
    so_pitch: int
    sv: int
    bb_pitch: int
    hr_pitch: int    # HR allowed by pitching
    sho: int


@dataclass
class MatchupBlock:
    as_of: datetime.datetime
    season: int
    team_a: TeamStats
    team_b: TeamStats


# ---------------------------------------------------------------------------
# Numeric comparison helpers
# ---------------------------------------------------------------------------

def _float_val(s: str) -> float:
    """Parse a display string to float for comparison; return 0.0 on failure."""
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def compare(field: str, a_val: str, b_val: str, lower_is_better: bool
            ) -> int:
    """
    Return -1 if A wins, 1 if B wins, 0 if tie.
    For 'wl' compares wins (int).
    """
    if field == "wl":
        # compare wins
        try:
            aw = int(a_val.split("-")[0])
            bw = int(b_val.split("-")[0])
        except (ValueError, IndexError):
            return 0
        if aw > bw:
            return -1
        if bw > aw:
            return 1
        return 0

    a = _float_val(a_val)
    b = _float_val(b_val)
    if a == b:
        return 0
    if lower_is_better:
        return -1 if a < b else 1
    else:
        return -1 if a > b else 1


# ---------------------------------------------------------------------------
# Fetch & cache
# ---------------------------------------------------------------------------

def _cache_path(working_dir: str, abbrev_a: str, abbrev_b: str, season: int) -> str:
    cache_dir = os.path.join(working_dir, "cache")
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f"matchup_{abbrev_a}_{abbrev_b}_{season}.json")


def fetch_matchup(
    team_a_abbrev: str,
    team_b_abbrev: str,
    season: int,
    ttl_minutes: int = 15,
    working_dir: str = "",
    force_refresh: bool = False,
) -> MatchupBlock:
    # Normalise order for cache key so NYY-LAD and LAD-NYY share the same file
    cache_key_a, cache_key_b = sorted([team_a_abbrev, team_b_abbrev])
    cache = (
        _cache_path(working_dir, cache_key_a, cache_key_b, season)
        if working_dir else ""
    )

    if cache and not force_refresh and os.path.isfile(cache):
        age_min = (
            datetime.datetime.now().timestamp() - os.path.getmtime(cache)
        ) / 60.0
        if age_min < ttl_minutes:
            try:
                with open(cache, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                # Re-order so team_a/team_b match the requested order
                block = _block_from_dict(data)
                if block.team_a.team_abbrev != team_a_abbrev:
                    block.team_a, block.team_b = block.team_b, block.team_a
                return block
            except Exception as exc:
                logger.warning("Matchup cache read failed: %s", exc)

    block = _do_fetch(team_a_abbrev, team_b_abbrev, season)

    if cache:
        try:
            with open(cache, "w", encoding="utf-8") as fh:
                json.dump(_block_to_dict(block), fh, indent=2, default=str)
        except Exception as exc:
            logger.warning("Matchup cache write failed: %s", exc)

    return block


def _do_fetch(abbrev_a: str, abbrev_b: str, season: int) -> MatchupBlock:
    id_a = _TEAM_ID_MAP.get(abbrev_a)
    id_b = _TEAM_ID_MAP.get(abbrev_b)
    if id_a is None:
        raise ValueError(f"Unknown team abbreviation: {abbrev_a!r}")
    if id_b is None:
        raise ValueError(f"Unknown team abbreviation: {abbrev_b!r}")

    stats_a = _fetch_team_stats(id_a, abbrev_a, season)
    stats_b = _fetch_team_stats(id_b, abbrev_b, season)

    return MatchupBlock(
        as_of=datetime.datetime.now(),
        season=season,
        team_a=stats_a,
        team_b=stats_b,
    )


def _fetch_team_stats(team_id: int, abbrev: str, season: int) -> TeamStats:
    # --- Hitting ---
    hit_raw = statsapi.get(
        "team_stats",
        {"teamId": team_id, "season": season, "group": "hitting",
         "gameType": "R", "stats": "season"},
    )
    hit = hit_raw.get("stats", [{}])[0].get("splits", [{}])
    hit_stat = hit[0].get("stat", {}) if hit else {}

    # --- Pitching ---
    pit_raw = statsapi.get(
        "team_stats",
        {"teamId": team_id, "season": season, "group": "pitching",
         "gameType": "R", "stats": "season"},
    )
    pit = pit_raw.get("stats", [{}])[0].get("splits", [{}])
    pit_stat = pit[0].get("stat", {}) if pit else {}

    games   = int(pit_stat.get("gamesPlayed") or hit_stat.get("gamesPlayed") or 1)
    wins    = int(pit_stat.get("wins", 0))
    losses  = int(pit_stat.get("losses", 0))
    runs_scored  = int(hit_stat.get("runs", 0))
    runs_allowed = int(pit_stat.get("runs", 0))

    rs_per_g = f"{runs_scored  / games:.2f}" if games else "0.00"
    ra_per_g = f"{runs_allowed / games:.2f}" if games else "0.00"

    return TeamStats(
        team_abbrev=abbrev,
        team_name=ABBREV_TO_NAME.get(abbrev, abbrev),
        wl=f"{wins}-{losses}",
        wins=wins,
        losses=losses,
        rs_per_g=rs_per_g,
        ra_per_g=ra_per_g,
        avg=str(hit_stat.get("avg", ".000")),
        hr=int(hit_stat.get("homeRuns", 0)),
        ops=str(hit_stat.get("ops", ".000")),
        sb=int(hit_stat.get("stolenBases", 0)),
        era=str(pit_stat.get("era", "0.00")),
        whip=str(pit_stat.get("whip", "0.00")),
        so_pitch=int(pit_stat.get("strikeOuts", 0)),
        sv=int(pit_stat.get("saves", 0)),
        bb_pitch=int(pit_stat.get("baseOnBalls", 0)),
        hr_pitch=int(pit_stat.get("homeRuns", 0)),
        sho=int(pit_stat.get("shutouts", 0)),
    )


# ---------------------------------------------------------------------------
# JSON serialisation
# ---------------------------------------------------------------------------

def _block_to_dict(block: MatchupBlock) -> dict:
    return {
        "as_of":  block.as_of.isoformat(),
        "season": block.season,
        "team_a": asdict(block.team_a),
        "team_b": asdict(block.team_b),
    }


def _block_from_dict(data: dict) -> MatchupBlock:
    return MatchupBlock(
        as_of=datetime.datetime.fromisoformat(data["as_of"]),
        season=data["season"],
        team_a=TeamStats(**data["team_a"]),
        team_b=TeamStats(**data["team_b"]),
    )
