from __future__ import annotations

import datetime
import json
import logging
import os
from dataclasses import asdict, dataclass, field

import statsapi

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Team id → abbreviation cache
# ---------------------------------------------------------------------------

_team_abbrev_cache: dict[int, str] = {}


def _get_team_abbrev(team_id: int) -> str:
    """Return abbreviation for a team id, fetching the teams list on first use."""
    if not _team_abbrev_cache:
        try:
            raw = statsapi.get("teams", {"sportId": 1, "activeStatus": "B"})
            for t in raw.get("teams", []):
                tid = t.get("id")
                abbrev = t.get("abbreviation", "")
                if tid and abbrev:
                    _team_abbrev_cache[int(tid)] = abbrev
        except Exception as exc:
            logger.warning("Could not fetch teams list: %s", exc)
    return _team_abbrev_cache.get(team_id, "---")

# ---------------------------------------------------------------------------
# IP helpers
# ---------------------------------------------------------------------------

def _ip_str_to_outs(ip: str) -> int:
    """Convert traditional IP string ('67.1' = 67 innings + 1 out) to total outs."""
    try:
        parts = str(ip).split(".")
        full  = int(parts[0])
        extra = int(parts[1]) if len(parts) > 1 else 0
        return full * 3 + min(extra, 2)
    except (ValueError, IndexError):
        return 0


def _outs_to_ip_str(outs: int) -> str:
    """Convert total outs back to traditional IP string ('67.1')."""
    if outs == 0:
        return "0.0"
    full  = outs // 3
    extra = outs %  3
    return f"{full}.{extra}"


def _outs_to_ip_decimal(outs: int) -> float:
    return outs / 3.0

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class CareerBattingEntry:
    season: int
    team_abbrev: str
    team_name: str
    multi_team: bool
    is_current_season: bool
    games: int
    at_bats: int
    hits: int
    home_runs: int
    rbi: int
    walks: int
    strikeouts: int
    stolen_bases: int
    avg: str
    obp: str
    slg: str
    ops: str


@dataclass
class CareerPitchingEntry:
    season: int
    team_abbrev: str
    team_name: str
    multi_team: bool
    is_current_season: bool
    games: int
    wins: int
    losses: int
    era: str
    innings_pitched: str
    strikeouts: int
    walks: int
    whip: str
    saves: int


@dataclass
class CareerBlock:
    player_id: int
    player_name: str
    current_team_abbrev: str
    stat_type: str              # "Batting" or "Pitching"
    entries: list               # list[CareerBattingEntry] or list[CareerPitchingEntry]
    as_of: datetime.datetime = field(default_factory=datetime.datetime.now)


# ---------------------------------------------------------------------------
# Memory cache
# ---------------------------------------------------------------------------

_mem: dict[tuple[int, str], tuple[CareerBlock, datetime.datetime]] = {}


def clear_career_cache() -> None:
    _mem.clear()


# ---------------------------------------------------------------------------
# Player search
# ---------------------------------------------------------------------------

def search_players(query: str) -> list[tuple[int, str, str]]:
    """
    Search for players by name.
    Returns [(player_id, full_name, current_team_abbrev), ...].
    """
    results = statsapi.lookup_player(query)
    if not results:
        return []
    out: list[tuple[int, str, str]] = []
    for p in results[:20]:
        pid  = int(p.get("id", 0))
        name = p.get("fullName", "")
        team = p.get("currentTeam", {})
        if isinstance(team, dict):
            # lookup_player only gives team id, no abbreviation
            team_id = team.get("id", 0)
            abbrev  = _get_team_abbrev(int(team_id)) if team_id else ""
            if abbrev == "---":
                abbrev = ""
        else:
            abbrev = ""
        if pid and name:
            out.append((pid, name, abbrev))
    return out


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _stat_i(stat_dict: dict, key: str, default: int = 0) -> int:
    try:
        return int(stat_dict.get(key, default) or 0)
    except (ValueError, TypeError):
        return default


def _stat_f(stat_dict: dict, key: str, default: float = 0.0) -> float:
    try:
        return float(stat_dict.get(key, default) or 0.0)
    except (ValueError, TypeError):
        return default


def _stat_s(stat_dict: dict, key: str, default: str = "---") -> str:
    v = stat_dict.get(key)
    if v is None or str(v).strip() == "":
        return default
    return str(v)


def _fmt_avg(hits: int, ab: int) -> str:
    if ab == 0:
        return ".000"
    v = hits / ab
    # Match MLB convention: ".220" not "0.220"
    s = f"{v:.3f}"
    return s.lstrip("0") or ".000"


def _fmt_obp(hits: int, walks: int, hbp: int, ab: int, sf: int) -> str:
    den = ab + walks + hbp + sf
    if den == 0:
        return ".000"
    v = (hits + walks + hbp) / den
    s = f"{v:.3f}"
    return s.lstrip("0") or ".000"


def _fmt_slg(total_bases: int, ab: int) -> str:
    if ab == 0:
        return ".000"
    v = total_bases / ab
    s = f"{v:.3f}"
    return s.lstrip("0") or ".000"


def _fmt_era(earned_runs: int, total_outs: int) -> str:
    if total_outs == 0:
        return "0.00"
    era = earned_runs * 27.0 / total_outs
    return f"{era:.2f}"


def _fmt_whip(bb: int, h: int, total_outs: int) -> str:
    if total_outs == 0:
        return "0.00"
    ip = _outs_to_ip_decimal(total_outs)
    if ip == 0:
        return "0.00"
    return f"{(bb + h) / ip:.2f}"


def _current_year() -> int:
    return datetime.date.today().year


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def fetch_career(
    player_id: int,
    player_name: str,
    stat_type: str,          # "Batting" or "Pitching"
    year_start: int,
    year_end: int,
    ttl_minutes: int,
    working_dir: str,
    force_refresh: bool,
) -> CareerBlock:
    now      = datetime.datetime.now()
    cache_key = (player_id, stat_type)

    # Memory cache
    if not force_refresh and cache_key in _mem:
        block, ts = _mem[cache_key]
        if (now - ts).total_seconds() < ttl_minutes * 60:
            return _apply_year_filter(block, year_start, year_end)

    # Disk cache
    group      = "hitting" if stat_type == "Batting" else "pitching"
    group_slug = "batting" if stat_type == "Batting" else "pitching"
    cache_dir  = os.path.join(working_dir, "cache")
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, f"career_{player_id}_{group_slug}.json")

    if not force_refresh and os.path.isfile(cache_file):
        mtime = datetime.datetime.fromtimestamp(os.path.getmtime(cache_file))
        if (now - mtime).total_seconds() < ttl_minutes * 60:
            try:
                block = _load_disk_cache(cache_file, stat_type)
                _mem[cache_key] = (block, mtime)
                return _apply_year_filter(block, year_start, year_end)
            except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
                try:
                    os.remove(cache_file)
                    logger.warning("Removed corrupt career cache %s: %s", cache_file, exc)
                except OSError:
                    logger.warning("Ignoring corrupt career cache: %s", cache_file)


    # Live fetch
    block = _fetch_live(player_id, player_name, stat_type, group)

    # Save to disk
    try:
        _save_disk_cache(cache_file, block)
    except Exception as exc:
        logger.warning("Could not write career cache: %s", exc)

    _mem[cache_key] = (block, now)
    return _apply_year_filter(block, year_start, year_end)


def _fetch_live(
    player_id: int,
    player_name: str,
    stat_type: str,
    group: str,
) -> CareerBlock:
    raw = statsapi.get(
        "person",
        {
            "personId": player_id,
            "hydrate":  f"stats(group={group},type=yearByYear,gameType=R),currentTeam",
        },
    )

    people = raw.get("people", [])
    if not people:
        raise ValueError(f"Player id {player_id} not found.")

    person    = people[0]
    stats_list = person.get("stats", [])

    splits: list[dict] = []
    for stat_obj in stats_list:
        splits.extend(stat_obj.get("splits", []))

    # Filter to MLB (sportId=1)
    mlb_splits = [
        s for s in splits
        if s.get("sport", {}).get("id") == 1
        or str(s.get("sport", {}).get("abbreviation", "")).upper() in ("MLB", "MAJ")
    ]

    # Attempt to read current team abbreviation
    current_team_abbrev = ""
    ct = person.get("currentTeam", {})
    if isinstance(ct, dict) and ct.get("id"):
        current_team_abbrev = _get_team_abbrev(int(ct["id"]))
        if current_team_abbrev == "---":
            current_team_abbrev = ""
    if not current_team_abbrev and mlb_splits:
        latest = max(mlb_splits, key=lambda s: int(s.get("season", 0) or 0))
        team_id = latest.get("team", {}).get("id", 0)
        if team_id:
            current_team_abbrev = _get_team_abbrev(int(team_id))

    # Group by season
    from collections import defaultdict
    by_season: dict[int, list[dict]] = defaultdict(list)
    for s in mlb_splits:
        season = int(s.get("season", 0) or 0)
        if season:
            by_season[season].append(s)

    current_yr = _current_year()

    if stat_type == "Batting":
        entries = _build_batting_entries(by_season, current_yr)
    else:
        entries = _build_pitching_entries(by_season, current_yr)

    # Sort by season ascending
    entries.sort(key=lambda e: e.season)

    return CareerBlock(
        player_id=player_id,
        player_name=player_name,
        current_team_abbrev=current_team_abbrev,
        stat_type=stat_type,
        entries=entries,
        as_of=datetime.datetime.now(),
    )


def _build_batting_entries(
    by_season: dict[int, list[dict]],
    current_yr: int,
) -> list[CareerBattingEntry]:
    entries: list[CareerBattingEntry] = []

    for season, splits in by_season.items():
        multi = len(splits) > 1

        # Check if any split is a "2 Teams" summary
        total_split = None
        for s in splits:
            team_name = s.get("team", {}).get("name", "")
            if "Team" in team_name or team_name == "":
                total_split = s
                break

        if total_split is not None and multi:
            splits_to_use = [total_split]
        else:
            splits_to_use = splits

        # Aggregate
        ab   = sum(_stat_i(s["stat"], "atBats")        for s in splits_to_use)
        hits = sum(_stat_i(s["stat"], "hits")          for s in splits_to_use)
        hr   = sum(_stat_i(s["stat"], "homeRuns")      for s in splits_to_use)
        rbi  = sum(_stat_i(s["stat"], "rbi")           for s in splits_to_use)
        bb   = sum(_stat_i(s["stat"], "baseOnBalls")   for s in splits_to_use)
        so   = sum(_stat_i(s["stat"], "strikeOuts")    for s in splits_to_use)
        sb   = sum(_stat_i(s["stat"], "stolenBases")   for s in splits_to_use)
        g    = sum(_stat_i(s["stat"], "gamesPlayed")   for s in splits_to_use)
        hbp  = sum(_stat_i(s["stat"], "hitByPitch")    for s in splits_to_use)
        sf   = sum(_stat_i(s["stat"], "sacFlies")      for s in splits_to_use)
        tb   = sum(_stat_i(s["stat"], "totalBases")    for s in splits_to_use)

        avg = _fmt_avg(hits, ab)

        # Use API-provided rate stats when single team; compute from totals when multi
        if not multi or total_split is not None:
            # Single team or we have a total row
            s_ref = splits_to_use[0]["stat"]
            obp = _stat_s(s_ref, "obp", ".000")
            slg = _stat_s(s_ref, "slg", ".000")
            ops = _stat_s(s_ref, "ops", ".000")
            # Normalise: mlb statsapi may return ".000" when no data
            if obp == ".000" and ab == 0:
                obp = slg = ops = "---"
        else:
            # Multiple teams, no total split — compute from counting stats
            obp = _fmt_obp(hits, bb, hbp, ab, sf)
            slg = _fmt_slg(tb, ab) if tb else "---"
            if slg != "---":
                try:
                    ops = f"{float(obp) + float(slg):.3f}"
                except ValueError:
                    ops = "---"
            else:
                ops = "---"

        if multi:
            # Collect per-team abbreviations from the individual splits
            # (skip the synthetic "2 Teams" totals row which has no real team id)
            per_team_splits = [
                s for s in splits
                if s.get("team", {}).get("id", 0)
                and "Team" not in s.get("team", {}).get("name", "")
            ]
            abbrevs = [
                _get_team_abbrev(int(s["team"]["id"]))
                for s in per_team_splits
            ]
            if len(abbrevs) == 2:
                team_abbrev = f"{abbrevs[0]}/{abbrevs[1]}"
            elif len(abbrevs) > 2:
                team_abbrev = f"{len(abbrevs)} TM"
            else:
                team_abbrev = "2 TM"  # fallback if splits unexpectedly empty
            team_name = "Multiple Teams"
        else:
            t = splits_to_use[0].get("team", {})
            team_id     = t.get("id", 0)
            team_abbrev = _get_team_abbrev(int(team_id)) if team_id else "---"
            team_name   = t.get("name", "")

        entries.append(CareerBattingEntry(
            season=season,
            team_abbrev=team_abbrev,
            team_name=team_name,
            multi_team=multi,
            is_current_season=(season == current_yr),
            games=g,
            at_bats=ab,
            hits=hits,
            home_runs=hr,
            rbi=rbi,
            walks=bb,
            strikeouts=so,
            stolen_bases=sb,
            avg=avg,
            obp=obp,
            slg=slg,
            ops=ops,
        ))

    return entries


def _build_pitching_entries(
    by_season: dict[int, list[dict]],
    current_yr: int,
) -> list[CareerPitchingEntry]:
    entries: list[CareerPitchingEntry] = []

    for season, splits in by_season.items():
        multi = len(splits) > 1

        # Check if any split is a totals row
        total_split = None
        for s in splits:
            team_name = s.get("team", {}).get("name", "")
            if "Team" in team_name or team_name == "":
                total_split = s
                break

        if total_split is not None and multi:
            splits_to_use = [total_split]
        else:
            splits_to_use = splits

        g   = sum(_stat_i(s["stat"], "gamesPlayed")   for s in splits_to_use)
        w   = sum(_stat_i(s["stat"], "wins")          for s in splits_to_use)
        lo  = sum(_stat_i(s["stat"], "losses")        for s in splits_to_use)
        so  = sum(_stat_i(s["stat"], "strikeOuts")    for s in splits_to_use)
        bb  = sum(_stat_i(s["stat"], "baseOnBalls")   for s in splits_to_use)
        sv  = sum(_stat_i(s["stat"], "saves")         for s in splits_to_use)
        er  = sum(_stat_i(s["stat"], "earnedRuns")    for s in splits_to_use)
        h   = sum(_stat_i(s["stat"], "hits")          for s in splits_to_use)

        # Sum IP via outs
        total_outs = sum(
            _ip_str_to_outs(_stat_s(s["stat"], "inningsPitched", "0.0"))
            for s in splits_to_use
        )
        ip_str = _outs_to_ip_str(total_outs)

        # ERA and WHIP
        if not multi or total_split is not None:
            s_ref = splits_to_use[0]["stat"]
            era   = _stat_s(s_ref, "era",  "0.00")
            whip  = _stat_s(s_ref, "whip", "0.00")
        else:
            era  = _fmt_era(er, total_outs)
            whip = _fmt_whip(bb, h, total_outs)

        if multi:
            per_team_splits = [
                s for s in splits
                if s.get("team", {}).get("id", 0)
                and "Team" not in s.get("team", {}).get("name", "")
            ]
            abbrevs = [
                _get_team_abbrev(int(s["team"]["id"]))
                for s in per_team_splits
            ]
            if len(abbrevs) == 2:
                team_abbrev = f"{abbrevs[0]}/{abbrevs[1]}"
            elif len(abbrevs) > 2:
                team_abbrev = f"{len(abbrevs)} TM"
            else:
                team_abbrev = "2 TM"
            team_name = "Multiple Teams"
        else:
            t = splits_to_use[0].get("team", {})
            team_id     = t.get("id", 0)
            team_abbrev = _get_team_abbrev(int(team_id)) if team_id else "---"
            team_name   = t.get("name", "")

        entries.append(CareerPitchingEntry(
            season=season,
            team_abbrev=team_abbrev,
            team_name=team_name,
            multi_team=multi,
            is_current_season=(season == current_yr),
            games=g,
            wins=w,
            losses=lo,
            era=era,
            innings_pitched=ip_str,
            strikeouts=so,
            walks=bb,
            whip=whip,
            saves=sv,
        ))

    return entries


# ---------------------------------------------------------------------------
# Year filtering
# ---------------------------------------------------------------------------

def _apply_year_filter(block: CareerBlock, year_start: int,
                        year_end: int) -> CareerBlock:
    if year_start == 0 and year_end == 0:
        return block
    filtered = [
        e for e in block.entries
        if (year_start == 0 or e.season >= year_start)
        and (year_end   == 0 or e.season <= year_end)
    ]
    from dataclasses import replace
    return CareerBlock(
        player_id=block.player_id,
        player_name=block.player_name,
        current_team_abbrev=block.current_team_abbrev,
        stat_type=block.stat_type,
        entries=filtered,
        as_of=block.as_of,
    )


# ---------------------------------------------------------------------------
# Disk cache I/O
# ---------------------------------------------------------------------------

def _save_disk_cache(path: str, block: CareerBlock) -> None:
    payload: dict = {
        "player_id":           block.player_id,
        "player_name":         block.player_name,
        "current_team_abbrev": block.current_team_abbrev,
        "stat_type":           block.stat_type,
        "as_of":               block.as_of.isoformat(),
        "entries":             [asdict(e) for e in block.entries],
    }
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp_path, path)


def _load_disk_cache(path: str, stat_type: str) -> CareerBlock:
    with open(path, "r", encoding="utf-8") as f:
        d = json.load(f)
    as_of = datetime.datetime.fromisoformat(d["as_of"])
    if stat_type == "Batting":
        cls = CareerBattingEntry
    else:
        cls = CareerPitchingEntry
    entries = [cls(**e) for e in d["entries"]]
    return CareerBlock(
        player_id=d["player_id"],
        player_name=d["player_name"],
        current_team_abbrev=d.get("current_team_abbrev", ""),
        stat_type=d["stat_type"],
        entries=entries,
        as_of=as_of,
    )
