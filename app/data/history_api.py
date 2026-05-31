from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass
from typing import Callable, Optional

from app.data.batters_api import (
    fetch_batters_cached,
    filter_batters,
    sort_and_trim as batters_sort_and_trim,
    SORT_STAT_LABELS as BATTER_SORT_LABELS,
    SORT_STAT_FIELD_MAP as BATTER_FIELD_MAP,
)
from app.data.pitchers_api import (
    fetch_pitchers_cached,
    filter_pitchers,
    sort_and_trim as pitchers_sort_and_trim,
    SORT_STAT_LABELS as PITCHER_SORT_LABELS,
    SORT_STAT_FIELD_MAP as PITCHER_FIELD_MAP,
    ASCENDING_STATS as PITCHER_ASCENDING,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stat options exposed to UI
# ---------------------------------------------------------------------------

BATTING_SORT_LABELS  = BATTER_SORT_LABELS   # ["OPS", "AVG", "HR", ...]
PITCHING_SORT_LABELS = PITCHER_SORT_LABELS  # ["ERA", "WHIP", "W", ...]

STAT_TYPE_OPTIONS = ["Batting", "Pitching"]

# Companion stats shown alongside each primary sort stat
_BATTING_COMPANIONS: dict[str, tuple[str, str]] = {
    "OPS":  ("AVG", "HR"),
    "AVG":  ("OBP", "HR"),
    "HR":   ("RBI", "AVG"),
    "RBI":  ("HR",  "AVG"),
    "OBP":  ("AVG", "SLG"),
    "SLG":  ("OBP", "HR"),
    "H":    ("AVG", "RBI"),
    "BB":   ("OBP", "AVG"),
    "SB":   ("AVG", "HR"),
}

_PITCHING_COMPANIONS: dict[str, tuple[str, str]] = {
    "ERA":  ("WHIP", "SO"),
    "WHIP": ("ERA",  "SO"),
    "W":    ("SO",   "ERA"),
    "SO":   ("ERA",  "WHIP"),
    "IP":   ("SO",   "ERA"),
    "SV":   ("ERA",  "WHIP"),
    "HLD":  ("ERA",  "WHIP"),
    "BB":   ("ERA",  "WHIP"),
    "HR":   ("ERA",  "WHIP"),
    "L":    ("ERA",  "WHIP"),
}

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class HistoryEntry:
    season: int
    player_name: str
    team_abbrev: str
    team_name: str
    stat_value: str        # display string, e.g. ".982" or "2.45"
    is_current_season: bool
    extra_stat_1_label: str = ""
    extra_stat_1_value: str = ""
    extra_stat_2_label: str = ""
    extra_stat_2_value: str = ""


YEAR_SORT_OPTIONS = ["Ascending", "Descending"]


@dataclass
class HistoryBlock:
    as_of: datetime.datetime
    stat_label: str        # e.g. "OPS" or "ERA"
    stat_type: str         # "Batting" or "Pitching"
    scope: str             # e.g. "All MLB", "AL East", "NYY"
    year_start: int
    year_end: int
    year_sort: str         # "Ascending" or "Descending"
    entries: list[HistoryEntry]   # one per season, order matches year_sort


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def _read_extra_stats(player, companions: tuple, field_map: dict) -> list[tuple[str, str]]:
    """Return [(label, value), (label, value)] for up to 2 companion stats."""
    result: list[tuple[str, str]] = []
    for label in companions[:2]:
        fld = field_map.get(label, "")
        if fld:
            result.append((label, str(getattr(player, fld, ""))))
        else:
            result.append(("", ""))
    while len(result) < 2:
        result.append(("", ""))
    return result


def fetch_history(
    scope: str,
    stat_type: str,
    sort_stat: str,
    year_start: int,
    year_end: int,
    min_pa: int,
    min_ip: float,
    min_g: int,
    pitcher_type: str,
    ttl_minutes: int,
    working_dir: str,
    force_refresh: bool,
    year_sort: str = "Ascending",
    progress_cb: Optional[Callable[[int, int, int], None]] = None,
) -> HistoryBlock:
    """
    For each season in [year_start, year_end], fetch the relevant stats block,
    filter/sort, and return the #1 player for that season.

    progress_cb(current_year, index_1based, total) — called after each fetch.
    Raises ValueError if no data found for every year.
    """
    current_year = datetime.date.today().year
    seasons = list(range(year_start, year_end + 1))
    total   = len(seasons)
    entries: list[HistoryEntry] = []
    errors: list[str] = []

    for idx, season in enumerate(seasons, start=1):
        if progress_cb:
            progress_cb(season, idx, total)
        try:
            if stat_type == "Batting":
                block, _ = fetch_batters_cached(
                    season=season,
                    ttl_minutes=ttl_minutes,
                    working_dir=working_dir,
                    force_refresh=force_refresh,
                )
                filtered = filter_batters(block, scope)
                trimmed  = batters_sort_and_trim(filtered, sort_stat, 1, min_pa)
                if not trimmed:
                    logger.debug("History: no batting result for %d %s", season, scope)
                    continue
                top = trimmed[0]
                field = BATTER_FIELD_MAP.get(sort_stat, "ops")
                raw   = getattr(top, field)
                value = str(raw) if not isinstance(raw, float) else f"{raw:.3f}"
                _companions = _BATTING_COMPANIONS.get(sort_stat, ())
                _extra = _read_extra_stats(top, _companions, BATTER_FIELD_MAP)
            else:
                block, _ = fetch_pitchers_cached(
                    season=season,
                    ttl_minutes=ttl_minutes,
                    working_dir=working_dir,
                    force_refresh=force_refresh,
                )
                filtered = filter_pitchers(block, scope, pitcher_type)
                trimmed  = pitchers_sort_and_trim(
                    filtered, sort_stat, 1, min_ip, min_g, pitcher_type)
                if not trimmed:
                    logger.debug("History: no pitching result for %d %s", season, scope)
                    continue
                top   = trimmed[0]
                field = PITCHER_FIELD_MAP.get(sort_stat, "era")
                value = str(getattr(top, field))
                _companions = _PITCHING_COMPANIONS.get(sort_stat, ())
                _extra = _read_extra_stats(top, _companions, PITCHER_FIELD_MAP)

            entries.append(HistoryEntry(
                season=season,
                player_name=top.player_name,
                team_abbrev=top.team_abbrev,
                team_name=top.team_name,
                stat_value=value,
                is_current_season=(season == current_year),
                extra_stat_1_label=_extra[0][0],
                extra_stat_1_value=_extra[0][1],
                extra_stat_2_label=_extra[1][0],
                extra_stat_2_value=_extra[1][1],
            ))
        except Exception as exc:
            logger.warning("History: could not fetch season %d: %s", season, exc)
            errors.append(str(season))

    if not entries:
        detail = f" (failed years: {', '.join(errors)})" if errors else ""
        raise ValueError(
            f"No history data found for scope '{scope}', "
            f"{stat_type} {sort_stat}, {year_start}–{year_end}{detail}."
        )

    if year_sort == "Descending":
        entries = list(reversed(entries))

    return HistoryBlock(
        as_of=datetime.datetime.now(),
        stat_label=sort_stat,
        stat_type=stat_type,
        scope=scope,
        year_start=year_start,
        year_end=year_end,
        year_sort=year_sort,
        entries=entries,
    )
