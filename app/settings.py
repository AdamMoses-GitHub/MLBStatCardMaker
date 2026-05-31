from __future__ import annotations

import json
import logging
import os
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
    batters_show_logos: bool = True
    batters_width_in: float = 7.0
    batters_height_in: float = 5.0
    batters_bg_color: str = "#FFFFFF"
    batters_export_filename: str = "batters_card"
    batters_append_timestamp: bool = True

    # Column explainers (both cards)
    standings_show_col_explainers: bool = False
    batters_show_col_explainers: bool = False
    col_explainer_sep: str = "="

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
        path = os.path.join(config_dir, "settings.json")
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
            self._path = os.path.join(config_dir, "settings.json")
        if not self._path:
            return
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        data = {k: v for k, v in asdict(self).items() if not k.startswith("_")}
        with open(self._path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
