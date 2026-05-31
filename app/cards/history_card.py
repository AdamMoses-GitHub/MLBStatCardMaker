from __future__ import annotations

import datetime
from dataclasses import dataclass

from PIL import Image, ImageDraw

from app.cards.base_card import CardConfig
from app.data.history_api import HistoryBlock, HistoryEntry
from app.data.batters_api import is_team_scope as _batters_is_team_scope
from app.data.logo_cache import get_logo
from app.utils.font_manager import get_font

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Gold highlight for the current season row
_CURRENT_SEASON_BG  = "#FFF8DC"   # cornsilk — warm gold tint
_CURRENT_SEASON_FG  = "#5A4000"   # dark amber text (optional, unused — row uses normal fg)

# Maps each non-team scope to the logo pseudo-abbrev
_SCOPE_LOGO: dict[str, str] = {
    "All MLB":    "MLB",
    "AL":         "AL",
    "NL":         "NL",
    "AL East":    "AL EAST",
    "AL Central": "AL CENTRAL",
    "AL West":    "AL WEST",
    "NL East":    "NL EAST",
    "NL Central": "NL CENTRAL",
    "NL West":    "NL WEST",
}

_SCOPE_EXPAND: dict[str, str] = {
    "AL":         "American League",
    "NL":         "National League",
    "AL East":    "American League East",
    "AL Central": "American League Central",
    "AL West":    "American League West",
    "NL East":    "National League East",
    "NL Central": "National League Central",
    "NL West":    "National League West",
}

_STAT_EXPAND: dict[str, str] = {
    # Batting
    "OPS":  "OBP + Slugging",
    "AVG":  "Batting Average",
    "HR":   "Home Runs",
    "RBI":  "Runs Batted In",
    "OBP":  "On-Base Percentage",
    "SLG":  "Slugging Percentage",
    "H":    "Hits",
    "BB":   "Walks",
    "SB":   "Stolen Bases",
    # Pitching
    "ERA":  "Earned Run Average",
    "WHIP": "Walks + Hits per IP",
    "W":    "Wins",
    "SO":   "Strikeouts",
    "IP":   "Innings Pitched",
    "SV":   "Saves",
    "HLD":  "Holds",
    "L":    "Losses",
}

# Column layout — fixed, always the same
_COLUMNS     = ["YEAR", "PLAYER", "TEAM", "STAT"]

# Relative weight ratios
_COL_WEIGHTS: dict[str, float] = {
    "YEAR":   0.9,
    "PLAYER": 3.5,
    "TEAM":   1.1,
    "STAT":   1.0,
}


def _pt_px(pt: float, dpi: int) -> int:
    return max(1, round(pt * dpi / 72))


def _col_widths_px(columns: list[str], total_px: int, padding_px: int) -> list[int]:
    total_weight = sum(_COL_WEIGHTS.get(c, 1.0) for c in columns)
    usable = max(1, total_px - padding_px * 2)
    widths: list[int] = []
    allocated = 0
    for i, col in enumerate(columns):
        if i == len(columns) - 1:
            widths.append(max(1, usable - allocated))
        else:
            w = max(1, round(usable * (_COL_WEIGHTS.get(col, 1.0) / total_weight)))
            widths.append(w)
            allocated += w
    return widths


def _is_team_scope(scope: str) -> bool:
    return _batters_is_team_scope(scope)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class HistoryCardConfig(CardConfig):
    scope: str = "All MLB"
    stat_type: str = "Batting"   # "Batting" or "Pitching"
    sort_stat: str = "OPS"
    show_logos: bool = True
    show_timestamp: bool = False
    title_override: str = ""

    # Colors
    header_bg: str = "#1a3a5c"
    header_fg: str = "#FFFFFF"
    title_bg: str = "#1a3a5c"
    title_fg: str = "#FFFFFF"
    row_alt_color: str = "#EEF2F7"
    row_color: str = "#FFFFFF"
    divider_color: str = "#CCCCCC"
    text_color: str = "#111111"
    footer_color: str = "#888888"


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

class HistoryCardRenderer:

    def __init__(self, config: HistoryCardConfig, block: HistoryBlock,
                 working_dir: str = ""):
        self.config     = config
        self.block      = block
        self.working_dir = working_dir
        self.last_warning: str | None = None

    def render(self) -> Image.Image:
        cfg      = self.config
        entries  = self.block.entries   # ordered oldest → newest
        img      = cfg.new_canvas()
        draw     = ImageDraw.Draw(img)

        W, H  = cfg.width_px, cfg.height_px
        PAD   = max(8, round(W * 0.012))
        cols  = _COLUMNS

        # --- Font sizing ---
        num_rows     = max(len(entries), 1)
        title_h      = max(24, round(H * 0.07))
        col_header_h = max(16, round(H * 0.055))
        footer_h     = max(12, round(H * 0.04)) if cfg.show_timestamp else 0
        available_h  = H - title_h - col_header_h - footer_h - PAD
        row_h        = max(14, available_h // num_rows)

        title_font_size  = min(max(10, round(title_h * 0.52)),      _pt_px(18, cfg.dpi))
        header_font_size = min(max(8,  round(col_header_h * 0.52)), _pt_px(10, cfg.dpi))
        row_font_size    = min(max(7,  round(row_h * 0.52)),        _pt_px(11, cfg.dpi))
        footer_font_size = (
            min(max(7, round(footer_h * 0.60)), _pt_px(8, cfg.dpi))
            if footer_h else 8
        )

        title_font  = get_font(title_font_size,  bold=True)
        header_font = get_font(header_font_size, bold=True, condensed=True)
        row_font    = get_font(row_font_size,     condensed=True)
        footer_font = get_font(footer_font_size)

        col_widths = _col_widths_px(cols, W, PAD)
        logo_sz    = max(8, round(row_h * 0.65)) if cfg.show_logos else 0

        y = 0

        # --- Title bar ---
        _tlogo_sz = title_h - 8
        _scope_logo_abbrev = (
            entries[0].team_abbrev if (_is_team_scope(cfg.scope) and entries)
            else _SCOPE_LOGO.get(cfg.scope)
        )
        _has_title_logo = (
            cfg.show_logos and bool(self.working_dir)
            and _scope_logo_abbrev is not None
        )
        _title_avail = max(1, (W - PAD * 2 - _tlogo_sz - 8) if _has_title_logo
                           else (W - PAD * 2))
        title_text = cfg.title_override or self._title_text(title_font, _title_avail)

        draw.rectangle([0, y, W, y + title_h], fill=cfg.title_bg)
        if _has_title_logo:
            tlogo = get_logo(_scope_logo_abbrev, _tlogo_sz, self.working_dir)
            if tlogo:
                gap     = 8
                tbbox   = title_font.getbbox(title_text)
                text_w  = tbbox[2] - tbbox[0]
                group_w = _tlogo_sz + gap + text_w
                group_x = max(PAD, (W - group_w) // 2)
                ly = y + (title_h - _tlogo_sz) // 2
                img.paste(tlogo, (group_x, ly), tlogo)
                th = tbbox[3] - tbbox[1]
                tx = group_x + _tlogo_sz + gap
                ty = y + (title_h - th) // 2 - tbbox[1]
                draw.text((tx, ty), title_text, font=title_font, fill=cfg.title_fg)
            else:
                self._draw_centered_text_in_range(
                    draw, title_text, PAD, W, y, title_h, title_font, cfg.title_fg)
        else:
            self._draw_centered_text_in_range(
                draw, title_text, PAD, W, y, title_h, title_font, cfg.title_fg)
        y += title_h

        # --- Column header row ---
        draw.rectangle([0, y, W, y + col_header_h], fill=cfg.header_bg)
        x = PAD
        for col, cw in zip(cols, col_widths):
            lbl = cfg.sort_stat if col == "STAT" else col
            if col == "PLAYER":
                self._draw_left_text(draw, lbl, x, y, col_header_h,
                                     header_font, cfg.header_fg)
            elif col == "STAT":
                self._draw_right_col(draw, lbl, x, cw, y, col_header_h,
                                     header_font, cfg.header_fg)
            else:
                self._draw_centered_col(draw, lbl, x, cw, y, col_header_h,
                                        header_font, cfg.header_fg)
            x += cw
        draw.line([0, y + col_header_h - 1, W, y + col_header_h - 1],
                  fill=cfg.divider_color)
        y += col_header_h

        # --- Data rows ---
        for row_idx, entry in enumerate(entries):
            if entry.is_current_season:
                row_bg = _CURRENT_SEASON_BG
            else:
                row_bg = cfg.row_alt_color if (row_idx % 2 == 0) else cfg.row_color
            draw.rectangle([0, y, W, y + row_h], fill=row_bg)

            x = PAD
            for col, cw in zip(cols, col_widths):
                if col == "YEAR":
                    year_str = str(entry.season)
                    self._draw_centered_col(draw, year_str, x, cw, y, row_h,
                                            row_font, cfg.text_color)
                elif col == "PLAYER":
                    avail_w = cw - 6
                    name = entry.player_name
                    if row_font.getbbox(name)[2] > avail_w:
                        parts = name.split()
                        name  = parts[-1] if parts else name
                    self._draw_left_text(draw, name, x, y, row_h,
                                         row_font, cfg.text_color)
                elif col == "TEAM":
                    tx = x
                    if cfg.show_logos and self.working_dir and logo_sz > 0:
                        logo = get_logo(entry.team_abbrev, logo_sz, self.working_dir)
                        if logo:
                            ly = y + (row_h - logo_sz) // 2
                            img.paste(logo, (tx, ly), logo)
                            tx += logo_sz + 3
                    self._draw_left_text(draw, entry.team_abbrev, tx, y, row_h,
                                         row_font, cfg.text_color)
                elif col == "STAT":
                    self._draw_right_col(draw, entry.stat_value, x, cw, y, row_h,
                                         row_font, cfg.text_color)
                x += cw

            draw.line([PAD, y + row_h - 1, W - PAD, y + row_h - 1],
                      fill=cfg.divider_color)
            y += row_h

        # --- Footer ---
        if cfg.show_timestamp and footer_h:
            ts = self.block.as_of.strftime("Data as of %b %d, %Y  %I:%M %p")
            draw.rectangle([0, H - footer_h, W, H], fill=cfg.bg_color)
            self._draw_centered_text(draw, ts, H - footer_h, footer_h,
                                     footer_font, cfg.footer_color, W)

        return img

    # ------------------------------------------------------------------
    # Title text
    # ------------------------------------------------------------------

    def _title_text(self, font, avail_w: int) -> str:
        cfg        = self.config
        block      = self.block
        scope      = cfg.scope
        stat       = block.stat_label
        y1, y2     = block.year_start, block.year_end
        long_stat  = _STAT_EXPAND.get(stat, stat)
        long_scope = _SCOPE_EXPAND.get(scope, scope)
        label_s    = scope if scope != "All MLB" else "MLB"
        label_l    = long_scope if scope != "All MLB" else "MLB"

        long   = f"{label_l} {long_stat} Leaders {y1}\u2013{y2}"
        medium = f"{label_l} {stat} Leaders {y1}\u2013{y2}"
        short  = f"{label_s} {stat} Leaders {y1}\u2013{y2}"
        for candidate in (long, medium, short):
            bbox = font.getbbox(candidate)
            if (bbox[2] - bbox[0]) <= avail_w:
                return candidate
        return short

    # ------------------------------------------------------------------
    # Text helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _draw_centered_text(draw, text, y, h, font, color, width):
        bbox = font.getbbox(text)
        tw   = bbox[2] - bbox[0]
        th   = bbox[3] - bbox[1]
        x    = (width - tw) // 2 - bbox[0]
        ty   = y + (h - th) // 2 - bbox[1]
        draw.text((x, ty), text, font=font, fill=color)

    @staticmethod
    def _draw_centered_text_in_range(draw, text, x0, x1, y, h, font, color):
        bbox = font.getbbox(text)
        tw   = bbox[2] - bbox[0]
        th   = bbox[3] - bbox[1]
        x    = x0 + ((x1 - x0) - tw) // 2 - bbox[0]
        ty   = y + (h - th) // 2 - bbox[1]
        draw.text((x, ty), text, font=font, fill=color)

    @staticmethod
    def _draw_centered_col(draw, text, col_x, col_w, row_y, row_h, font, color):
        bbox = font.getbbox(text)
        tw   = bbox[2] - bbox[0]
        th   = bbox[3] - bbox[1]
        x    = col_x + (col_w - tw) // 2 - bbox[0]
        ty   = row_y + (row_h - th) // 2 - bbox[1]
        draw.text((x, ty), text, font=font, fill=color)

    @staticmethod
    def _draw_left_text(draw, text, x, row_y, row_h, font, color):
        bbox = font.getbbox(text)
        th   = bbox[3] - bbox[1]
        ty   = row_y + (row_h - th) // 2 - bbox[1]
        draw.text((x, ty), text, font=font, fill=color)

    @staticmethod
    def _draw_right_col(draw, text, col_x, col_w, row_y, row_h, font, color):
        bbox = font.getbbox(text)
        tw   = bbox[2] - bbox[0]
        th   = bbox[3] - bbox[1]
        x    = col_x + col_w - tw - 5 - bbox[0]
        ty   = row_y + (row_h - th) // 2 - bbox[1]
        draw.text((x, ty), text, font=font, fill=color)
