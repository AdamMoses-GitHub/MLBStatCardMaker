from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Optional

from app.data.batters_api import (
    fetch_batters_cached,
    filter_batters,
    sort_and_trim as batters_sort_and_trim,
    SORT_STAT_FIELD_MAP as BATTER_FIELD_MAP,
)
from app.data.pitchers_api import (
    fetch_pitchers_cached,
    filter_pitchers,
    sort_and_trim as pitchers_sort_and_trim,
    SORT_STAT_FIELD_MAP as PITCHER_FIELD_MAP,
)

# ---------------------------------------------------------------------------
# Stat groups
# ---------------------------------------------------------------------------

# Batting triple-crown stats in display order: (UI label, BatterEntry field)
BATTING_TRIPLE: list[tuple[str, str]] = [
    ("AVG", "avg"),
    ("HR",  "home_runs"),
    ("RBI", "rbi"),
]

# Pitching crown stats in display order: (UI label, PitcherEntry field)
PITCHING_TRIPLE: list[tuple[str, str]] = [
    ("W",   "wins"),
    ("SO",  "strikeouts"),
    ("ERA", "era"),
]

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class TripleCrownEntry:
    rank: int
    player_name: str
    team_abbrev: str
    team_name: str
    stat_value: str


@dataclass
class TripleCrownColumn:
    stat_label: str                  # e.g. "AVG"
    entries: list[TripleCrownEntry]


@dataclass
class TripleCrownBlock:
    as_of: datetime.datetime
    stat_type: str                   # "Batting" or "Pitching"
    scope: str
    season: int
    columns: list[TripleCrownColumn] # always 3, in BATTING/PITCHING_TRIPLE order


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def fetch_triple_crown(
    scope: str,
    stat_type: str,
    top_n: int,
    min_pa: int,
    min_ip: float,
    min_g: int,
    pitcher_type: str,
    season: Optional[int],
    ttl_minutes: int,
    working_dir: str,
    force_refresh: bool,
    batting_stats: Optional[list] = None,
    pitching_stats: Optional[list] = None,
) -> TripleCrownBlock:
    if season is None:
        season = datetime.date.today().year

    columns: list[TripleCrownColumn] = []

    if stat_type == "Batting":
        # Resolve which (label, field) pairs to use
        if batting_stats and len(batting_stats) == 3:
            stat_pairs = [
                (lbl, BATTER_FIELD_MAP[lbl])
                for lbl in batting_stats
                if lbl in BATTER_FIELD_MAP
            ]
        else:
            stat_pairs = []
        if len(stat_pairs) != 3:
            stat_pairs = list(BATTING_TRIPLE)
        block, _ = fetch_batters_cached(
            season=season,
            ttl_minutes=ttl_minutes,
            working_dir=working_dir,
            force_refresh=force_refresh,
        )
        filtered = filter_batters(block, scope)
        for label, field in stat_pairs:
            trimmed = batters_sort_and_trim(filtered, label, top_n, min_pa)
            entries: list[TripleCrownEntry] = []
            for rank, e in enumerate(trimmed, start=1):
                raw = getattr(e, field)
                if isinstance(raw, float):
                    val = f"{raw:.3f}"
                elif field in ("avg", "obp", "slg", "ops"):
                    val = str(raw)
                else:
                    val = str(raw)
                entries.append(TripleCrownEntry(
                    rank=rank,
                    player_name=e.player_name,
                    team_abbrev=e.team_abbrev,
                    team_name=e.team_name,
                    stat_value=val,
                ))
            columns.append(TripleCrownColumn(stat_label=label, entries=entries))
    else:
        # Resolve which (label, field) pairs to use
        if pitching_stats and len(pitching_stats) == 3:
            stat_pairs = [
                (lbl, PITCHER_FIELD_MAP[lbl])
                for lbl in pitching_stats
                if lbl in PITCHER_FIELD_MAP
            ]
        else:
            stat_pairs = []
        if len(stat_pairs) != 3:
            stat_pairs = list(PITCHING_TRIPLE)
        block, _ = fetch_pitchers_cached(
            season=season,
            ttl_minutes=ttl_minutes,
            working_dir=working_dir,
            force_refresh=force_refresh,
        )
        filtered = filter_pitchers(block, scope, pitcher_type)
        for label, field in stat_pairs:
            trimmed = pitchers_sort_and_trim(
                filtered, label, top_n, min_ip, min_g, pitcher_type)
            entries = []
            for rank, e in enumerate(trimmed, start=1):
                entries.append(TripleCrownEntry(
                    rank=rank,
                    player_name=e.player_name,
                    team_abbrev=e.team_abbrev,
                    team_name=e.team_name,
                    stat_value=str(getattr(e, field)),
                ))
            columns.append(TripleCrownColumn(stat_label=label, entries=entries))

    if not columns or not any(c.entries for c in columns):
        raise ValueError(
            f"No triple crown data found for scope '{scope}', "
            f"{stat_type}, season {season}."
        )

    return TripleCrownBlock(
        as_of=datetime.datetime.now(),
        stat_type=stat_type,
        scope=scope,
        season=season,
        columns=columns,
    )
