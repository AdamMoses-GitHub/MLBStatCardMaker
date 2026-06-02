from __future__ import annotations

import datetime
import json
import logging
import os
from dataclasses import asdict, dataclass
from typing import Optional

import statsapi

from app.data.roster_api import TEAM_NAMES, ABBREV_TO_NAME, _TEAM_ID_MAP

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class GameEntry:
    date: str              # display string, e.g. "May 31"
    game_date: str         # ISO "2026-05-31" for sorting / grouping
    opponent_name: str
    opponent_abbrev: str
    opponent_id: int
    is_home: bool
    team_score: int
    opp_score: int
    win: bool
    pitcher: str           # winning pitcher if win, losing pitcher if loss
    save_pitcher: str      # closer who earned the save, or ""
    record: str            # cumulative record at this game, e.g. "32-19"


@dataclass
class SeriesEntry:
    opponent_name: str
    opponent_abbrev: str
    opponent_id: int
    is_home: bool
    date_range: str        # e.g. "May 28–30"
    series_result: str     # e.g. "W 2-1", "L 1-2", "S 1-1"
    games: list[GameEntry]


@dataclass
class GameRecordBlock:
    as_of: datetime.datetime
    team_name: str
    team_abbrev: str
    team_id: int
    mode: str              # "games" | "series"
    entries: list          # list[GameEntry] or list[SeriesEntry]
    overall_record: str    # full-season record, e.g. "32-19"
    span_record: str       # W-L just within the displayed span, e.g. "7-3"


# ---------------------------------------------------------------------------
# Opponent abbrev lookup (opponent_id → abbrev)
# ---------------------------------------------------------------------------

_ID_TO_ABBREV: dict[int, str] = {v: k for k, v in _TEAM_ID_MAP.items()}


def _abbrev_for_id(team_id: int, fallback_name: str) -> str:
    abbrev = _ID_TO_ABBREV.get(team_id)
    if abbrev:
        return abbrev
    # Try to derive from full name
    for full, ab in TEAM_NAMES.items():
        if full.lower() == fallback_name.lower():
            return ab
    return fallback_name[:3].upper()


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _cache_path(working_dir: str, team_abbrev: str, season: int) -> str:
    cache_dir = os.path.join(working_dir, "cache")
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f"game_record_{team_abbrev}_{season}.json")


def _date_display(iso_date: str) -> str:
    """Convert '2026-05-31' to 'May 31'."""
    try:
        d = datetime.date.fromisoformat(iso_date)
        return d.strftime("%b %-d") if os.name != "nt" else d.strftime("%b %#d")
    except (ValueError, AttributeError):
        return iso_date


def _series_result_str(wins: int, losses: int) -> str:
    if wins > losses:
        return f"W {wins}-{losses}"
    if losses > wins:
        return f"L {wins}-{losses}"
    return f"S {wins}-{losses}"


# ---------------------------------------------------------------------------
# Serialisation helpers (for JSON cache)
# ---------------------------------------------------------------------------

def _block_to_dict(block: GameRecordBlock) -> dict:
    d = asdict(block)
    d["as_of"] = block.as_of.isoformat()
    return d


def _block_from_dict(data: dict, mode: str, n: int) -> GameRecordBlock:
    as_of = datetime.datetime.fromisoformat(data["as_of"])
    raw_entries = data.get("entries", [])
    if mode == "games":
        entries = [GameEntry(**e) for e in raw_entries]
    else:
        entries = []
        for s in raw_entries:
            games = [GameEntry(**g) for g in s.get("games", [])]
            entries.append(SeriesEntry(
                opponent_name=s["opponent_name"],
                opponent_abbrev=s["opponent_abbrev"],
                opponent_id=s["opponent_id"],
                is_home=s["is_home"],
                date_range=s["date_range"],
                series_result=s["series_result"],
                games=games,
            ))
    return GameRecordBlock(
        as_of=as_of,
        team_name=data["team_name"],
        team_abbrev=data["team_abbrev"],
        team_id=data["team_id"],
        mode=mode,
        entries=entries,
        overall_record=data.get("overall_record", ""),
        span_record=data.get("span_record", ""),
    )


# ---------------------------------------------------------------------------
# Public fetch
# ---------------------------------------------------------------------------

def fetch_game_record(
    team_name: str,
    mode: str,
    n: int,
    date_sort: str = "desc",
    ttl_minutes: int = 15,
    working_dir: str = "",
    force_refresh: bool = False,
) -> GameRecordBlock:
    """
    Fetch the last *n* completed games (mode='games') or series (mode='series')
    for *team_name* in the current MLB season.

    Results are cached per-team/season in cache/game_record_{abbrev}_{year}.json.
    Cache key includes all raw game data; n/mode slicing happens at read time so
    the same cache serves any combination of n and mode.
    """
    team_abbrev = TEAM_NAMES.get(team_name, team_name[:3].upper())
    team_id = _TEAM_ID_MAP.get(team_abbrev)
    if team_id is None:
        raise ValueError(f"Unknown team: {team_name!r}")

    season = datetime.date.today().year
    cache = _cache_path(working_dir, team_abbrev, season) if working_dir else ""

    raw_games: list[dict] = []
    use_cache = False

    if cache and not force_refresh and os.path.isfile(cache):
        age_min = (datetime.datetime.now().timestamp() - os.path.getmtime(cache)) / 60.0
        if age_min < ttl_minutes:
            try:
                with open(cache, "r", encoding="utf-8") as fh:
                    stored = json.load(fh)
                raw_games = stored.get("raw_games", [])
                use_cache = True
            except Exception as exc:
                logger.warning("Game record cache read failed for %s: %s", team_abbrev, exc)

    if not use_cache:
        today = datetime.date.today()
        start = datetime.date(season, 1, 1)
        raw_games = statsapi.schedule(
            team=team_id,
            start_date=start.strftime("%m/%d/%Y"),
            end_date=today.strftime("%m/%d/%Y"),
            sportId=1,
        )
        # Keep only completed regular-season games
        raw_games = [
            g for g in raw_games
            if g.get("status") == "Final" and g.get("game_type") == "R"
        ]
        if cache:
            try:
                with open(cache, "w", encoding="utf-8") as fh:
                    json.dump({"raw_games": raw_games}, fh, indent=2, default=str)
            except Exception as exc:
                logger.warning("Game record cache write failed for %s: %s", team_abbrev, exc)

    return _build_block(raw_games, team_name, team_abbrev, team_id, mode, n, date_sort)


# ---------------------------------------------------------------------------
# Build block from raw schedule data
# ---------------------------------------------------------------------------

def _build_block(
    raw_games: list[dict],
    team_name: str,
    team_abbrev: str,
    team_id: int,
    mode: str,
    n: int,
    date_sort: str = "desc",
) -> GameRecordBlock:
    # Sort chronologically (API usually returns in order, but be safe)
    raw_games = sorted(raw_games, key=lambda g: g.get("game_date", ""))

    # Build GameEntry list with cumulative record
    game_entries: list[GameEntry] = []
    season_wins = 0
    season_losses = 0

    for g in raw_games:
        home_id = int(g.get("home_id", 0))
        away_id = int(g.get("away_id", 0))
        is_home = (home_id == team_id)
        opp_id  = away_id if is_home else home_id
        opp_name = g.get("away_name") if is_home else g.get("home_name")
        opp_name = opp_name or "Unknown"
        opp_abbrev = _abbrev_for_id(opp_id, opp_name)

        team_score = int(g.get("home_score", 0) if is_home else g.get("away_score", 0))
        opp_score  = int(g.get("away_score", 0) if is_home else g.get("home_score", 0))
        win = g.get("winning_team") == team_name

        if win:
            season_wins += 1
            pitcher = g.get("winning_pitcher") or ""
        else:
            season_losses += 1
            pitcher = g.get("losing_pitcher") or ""

        save = g.get("save_pitcher") or ""
        iso_date = g.get("game_date", "")
        record = f"{season_wins}-{season_losses}"

        game_entries.append(GameEntry(
            date=_date_display(iso_date),
            game_date=iso_date,
            opponent_name=opp_name,
            opponent_abbrev=opp_abbrev,
            opponent_id=opp_id,
            is_home=is_home,
            team_score=team_score,
            opp_score=opp_score,
            win=win,
            pitcher=pitcher,
            save_pitcher=save,
            record=record,
        ))

    overall_record = f"{season_wins}-{season_losses}"
    as_of = datetime.datetime.now()

    if mode == "games":
        last_n = game_entries[-n:] if n < len(game_entries) else game_entries
        if date_sort == "asc":
            last_n = list(last_n)          # oldest first (already chronological)
        else:
            last_n = list(reversed(last_n))  # newest first
        span_w = sum(1 for e in last_n if e.win)
        span_l = len(last_n) - span_w
        span_record = f"{span_w}-{span_l}"
        return GameRecordBlock(
            as_of=as_of,
            team_name=team_name,
            team_abbrev=team_abbrev,
            team_id=team_id,
            mode=mode,
            entries=last_n,
            overall_record=overall_record,
            span_record=span_record,
        )

    else:  # series mode
        series_list = _group_into_series(game_entries)
        last_n_series = series_list[-n:] if n < len(series_list) else series_list
        if date_sort == "asc":
            last_n_series = list(last_n_series)
        else:
            last_n_series = list(reversed(last_n_series))
        # Apply same sort direction to games within each series
        if date_sort == "desc":
            last_n_series = [
                SeriesEntry(
                    opponent_name=s.opponent_name,
                    opponent_abbrev=s.opponent_abbrev,
                    opponent_id=s.opponent_id,
                    is_home=s.is_home,
                    date_range=s.date_range,
                    series_result=s.series_result,
                    games=list(reversed(s.games)),
                )
                for s in last_n_series
            ]
        span_w = sum(1 for s in last_n_series if s.series_result.startswith("W"))
        span_l = sum(1 for s in last_n_series if s.series_result.startswith("L"))
        span_s = sum(1 for s in last_n_series if s.series_result.startswith("S"))
        if span_s:
            span_record = f"{span_w}-{span_l}-{span_s}"
        else:
            span_record = f"{span_w}-{span_l}"
        return GameRecordBlock(
            as_of=as_of,
            team_name=team_name,
            team_abbrev=team_abbrev,
            team_id=team_id,
            mode=mode,
            entries=last_n_series,
            overall_record=overall_record,
            span_record=span_record,
        )


def _group_into_series(games: list[GameEntry]) -> list[SeriesEntry]:
    """Group consecutive games vs. same opponent into SeriesEntry objects."""
    if not games:
        return []

    series_list: list[SeriesEntry] = []
    current_games: list[GameEntry] = [games[0]]
    current_opp_id = games[0].opponent_id

    for g in games[1:]:
        if g.opponent_id == current_opp_id:
            current_games.append(g)
        else:
            series_list.append(_make_series(current_games))
            current_games = [g]
            current_opp_id = g.opponent_id

    series_list.append(_make_series(current_games))
    return series_list


def _make_series(games: list[GameEntry]) -> SeriesEntry:
    wins   = sum(1 for g in games if g.win)
    losses = len(games) - wins
    result = _series_result_str(wins, losses)

    start_date = games[0].game_date
    end_date   = games[-1].game_date
    if start_date == end_date:
        date_range = games[0].date
    else:
        start_d = _date_display(start_date)
        end_d   = _date_display(end_date)
        # If same month, collapse "May 28–30"
        try:
            s = datetime.date.fromisoformat(start_date)
            e = datetime.date.fromisoformat(end_date)
            if s.month == e.month:
                day_end = e.strftime("%-d") if os.name != "nt" else e.strftime("%#d")
                date_range = f"{start_d}\u2013{day_end}"
            else:
                date_range = f"{start_d}\u2013{end_d}"
        except ValueError:
            date_range = f"{start_d}\u2013{end_d}"

    first = games[0]
    return SeriesEntry(
        opponent_name=first.opponent_name,
        opponent_abbrev=first.opponent_abbrev,
        opponent_id=first.opponent_id,
        is_home=first.is_home,
        date_range=date_range,
        series_result=result,
        games=games,
    )
