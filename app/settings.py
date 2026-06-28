from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


DEFAULT_WORKING_DIR = str(Path.home() / "MLBStatCards")


@dataclass
class Settings:
    working_dir: str = DEFAULT_WORKING_DIR
    card_width_in: float = 6.0
    card_height_in: float = 4.0
    dpi: int = 300
    bg_color: str = "#FFFFFF"

    # Standings-specific
    standings_scope: str = "All MLB"
    standings_column_mode: str = "auto"   # "standard", "extended", "auto"
    standings_show_logos: bool = True
    standings_show_timestamp: bool = False
    standings_width_in: float = 6.0
    standings_height_in: float = 4.0
    standings_use_global_size: bool = False
    standings_bg_color: str = "#FFFFFF"
    standings_export_filename: str = "standings_card"
    standings_append_timestamp: bool = True

    # Batters-specific
    batters_scope: str = "All MLB"
    batters_column_mode: str = "auto"
    batters_sort_stat: str = "OPS"
    batters_top_n: int = 10
    batters_min_pa: int = 50
    batters_show_timestamp: bool = False
    batters_simple_title: bool = False
    batters_show_rank_badges: bool = True
    batters_show_jersey_number: bool = False
    batters_show_position: bool = False
    batters_show_logos: bool = True
    batters_width_in: float = 7.0
    batters_height_in: float = 5.0
    batters_use_global_size: bool = False
    batters_bg_color: str = "#FFFFFF"
    batters_export_filename: str = "batters_card"
    batters_append_timestamp: bool = True

    # Pitchers-specific
    pitchers_scope: str = "All MLB"
    pitchers_pitcher_type: str = "All"
    pitchers_column_mode: str = "auto"
    pitchers_sort_stat: str = "ERA"
    pitchers_top_n: int = 10
    pitchers_min_ip: float = 30.0
    pitchers_min_g: int = 10
    pitchers_show_timestamp: bool = False
    pitchers_simple_title: bool = False
    pitchers_show_rank_badges: bool = True
    pitchers_show_jersey_number: bool = False
    pitchers_show_logos: bool = True
    pitchers_width_in: float = 7.0
    pitchers_height_in: float = 5.0
    pitchers_use_global_size: bool = False
    pitchers_bg_color: str = "#FFFFFF"
    pitchers_export_filename: str = "pitchers_card"
    pitchers_append_timestamp: bool = True

    # History-specific
    history_scope: str = "All MLB"
    history_stat_type: str = "Batting"
    history_sort_stat: str = "OPS"
    history_year_start: int = 0        # 0 = auto (current_year - 6)
    history_year_end: int = 0          # 0 = auto (current_year)
    history_pitcher_type: str = "All"
    history_min_pa: int = 100
    history_min_ip: float = 80.0
    history_min_g: int = 20
    history_show_logos: bool = True
    history_show_timestamp: bool = False
    history_show_col_explainers: bool = False
    history_width_in: float = 6.0
    history_height_in: float = 5.0
    history_use_global_size: bool = False
    history_bg_color: str = "#FFFFFF"
    history_export_filename: str = "history_card"
    history_append_timestamp: bool = True
    history_year_sort: str = "Ascending"

    # Roster-specific
    roster_team: str = "New York Yankees"
    roster_type: str = "Active 26-Man"
    roster_group_by_position: bool = True
    roster_show_jersey_number: bool = True
    roster_show_bats_throws: bool = True
    roster_show_age: bool = True
    roster_show_logos: bool = True
    roster_show_timestamp: bool = False
    roster_hide_pitchers: bool = False
    roster_hide_dh: bool = False
    roster_width_in: float = 5.0
    roster_height_in: float = 7.0
    roster_use_global_size: bool = False
    roster_bg_color: str = "#FFFFFF"
    roster_export_filename: str = "roster_card"
    roster_append_timestamp: bool = True

    # Matchup-specific
    matchup_team_a: str = "New York Yankees"
    matchup_team_b: str = "Los Angeles Dodgers"
    matchup_season: int = 0          # 0 = auto (current year)
    matchup_stat_set: str = "Standard"
    matchup_win_highlight_color: str = "#D4EDDA"
    matchup_show_logos: bool = True
    matchup_show_timestamp: bool = False
    matchup_width_in: float = 6.5
    matchup_height_in: float = 5.5
    matchup_use_global_size: bool = False
    matchup_bg_color: str = "#FFFFFF"
    matchup_export_filename: str = "matchup_card"
    matchup_append_timestamp: bool = True

    # Triple Crown card
    triple_crown_scope: str = "All MLB"
    triple_crown_stat_type: str = "Batting"
    triple_crown_top_n: int = 10
    triple_crown_season: int = 0          # 0 = current year
    triple_crown_min_pa: int = 50
    triple_crown_min_ip: float = 30.0
    triple_crown_min_g: int = 10
    triple_crown_pitcher_type: str = "All"
    triple_crown_show_logos: bool = True
    triple_crown_show_rank_badges: bool = True
    triple_crown_show_timestamp: bool = False
    triple_crown_batting_stats: list = field(default_factory=lambda: ["AVG", "HR", "RBI"])
    triple_crown_pitching_stats: list = field(default_factory=lambda: ["W", "SO", "ERA"])
    triple_crown_width_in: float = 9.0
    triple_crown_height_in: float = 6.0
    triple_crown_use_global_size: bool = False
    triple_crown_bg_color: str = "#FFFFFF"
    triple_crown_export_filename: str = "triple_crown_card"
    triple_crown_append_timestamp: bool = True

    # Player Career card
    career_stat_type: str = "Batting"
    career_player_id: int = 0
    career_player_name: str = ""
    career_current_team_abbrev: str = ""
    career_year_start: int = 0            # 0 = full career start
    career_year_end: int = 0              # 0 = full career end
    career_year_sort: str = "Ascending"
    career_recent_players: list = field(default_factory=list)  # [{id,name,team}, ...]
    career_show_logos: bool = True
    career_highlight_current: bool = True
    career_show_timestamp: bool = False
    career_show_col_explainers: bool = False
    career_width_in: float = 7.0
    career_height_in: float = 6.0
    career_use_global_size: bool = False
    career_bg_color: str = "#FFFFFF"
    career_export_filename: str = "career_card"
    career_append_timestamp: bool = True

    # Game Record card
    game_record_team: str = "New York Yankees"
    game_record_mode: str = "games"              # "games" | "series"
    game_record_n: int = 10
    game_record_series_detail: str = "result_only"   # "result_only" | "scores"
    game_record_show_logos: bool = True
    game_record_show_summary: bool = True
    game_record_show_timestamp: bool = False
    game_record_width_in: float = 6.0
    game_record_height_in: float = 8.0           # portrait default
    game_record_use_global_size: bool = False
    game_record_bg_color: str = "#FFFFFF"
    game_record_export_filename: str = "game_record_card"
    game_record_append_timestamp: bool = True
    game_record_date_sort: str = "desc"       # "asc" | "desc"

    # Column explainers (all cards)
    standings_show_col_explainers: bool = False
    batters_show_col_explainers: bool = False
    pitchers_show_col_explainers: bool = False
    roster_show_col_explainers: bool = False
    matchup_show_col_explainers: bool = False
    col_explainer_sep: str = "="

    # Export canvas margin
    export_canvas_margin_pct: float = 0.0

    # Data cache
    data_cache_ttl_minutes: int = 15

    # UI state
    window_geometry: str = ""

    _path: str = field(default="", repr=False, compare=False)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    @classmethod
    def load(cls, config_dir: str) -> "Settings":
        # One-time migration: move root settings.json → settings/settings.json
        old_path    = os.path.join(config_dir, "settings.json")
        settings_dir = os.path.join(config_dir, "settings")
        path        = os.path.join(settings_dir, "settings.json")
        if os.path.isfile(old_path) and not os.path.isfile(path):
            os.makedirs(settings_dir, exist_ok=True)
            shutil.move(old_path, path)
            logger.info("Migrated settings.json → settings/settings.json")
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                # Remove internal/unknown keys before constructing
                known = {f.name for f in cls.__dataclass_fields__.values()
                         if not f.name.startswith("_")}
                ignored = [k for k in data if k not in known]
                if ignored:
                    logger.debug("Settings: ignored unknown keys: %s", ignored)
                filtered = {k: v for k, v in data.items() if k in known}
                obj = cls(**filtered)
                obj._path = path
                return obj
            except Exception as exc:
                logger.warning("Could not load settings from %s: %s — using defaults", path, exc)
        obj = cls()
        obj._path = path
        return obj

    def save(self, config_dir: str | None = None) -> None:
        if config_dir:
            self._path = os.path.join(config_dir, "settings", "settings.json")
        if not self._path:
            return
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        data = {k: v for k, v in asdict(self).items() if not k.startswith("_")}
        tmp_path = f"{self._path}.tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
            os.replace(tmp_path, self._path)
        except OSError as exc:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass
            logger.warning("Could not save settings to %s: %s", self._path, exc)


# ---------------------------------------------------------------------------
# Working-directory initialisation
# ---------------------------------------------------------------------------

_README = """\
MLB Stat Card Maker — Working Directory
========================================

This folder is managed by MLB Stat Card Maker.

Subfolders:
  settings/       App configuration (settings.json)
  cache/          Cached API data — auto-refreshed per the TTL setting
  logos/          Cached team logo images
  output/
    standings/    Exported standings card images
    batters/      Exported top batters card images
    pitchers/     Exported top pitchers card images
    history/      Exported season leaders card images
    roster/       Exported team roster card images
    matchup/      Exported head-to-head matchup card images

Files in cache/ and logos/ can be safely deleted; they are re-created
automatically.  Do not edit settings.json by hand.
"""


def init_working_dir(working_dir: str) -> None:
    """Create the standard subfolder layout and a readme on first use."""
    for subdir in (
        "settings",
        "cache",
        "logos",
        os.path.join("output", "standings"),
        os.path.join("output", "batters"),
        os.path.join("output", "pitchers"),
        os.path.join("output", "history"),
        os.path.join("output", "roster"),
        os.path.join("output", "matchup"),
    ):
        os.makedirs(os.path.join(working_dir, subdir), exist_ok=True)
    readme = os.path.join(working_dir, "readme.txt")
    if not os.path.exists(readme):
        tmp_path = f"{readme}.tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as fh:
                fh.write(_README)
            os.replace(tmp_path, readme)
        except OSError:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass
