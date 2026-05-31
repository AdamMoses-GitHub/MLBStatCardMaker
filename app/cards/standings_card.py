from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Optional

from PIL import Image, ImageDraw

from app.cards.base_card import CardConfig
from app.data.mlb_api import StandingsEntry, StandingsBlock, filter_standings, group_by_division
from app.data.logo_cache import get_logo
from app.utils.font_manager import get_font

# ---------------------------------------------------------------------------
# Column definitions
# ---------------------------------------------------------------------------

STANDARD_COLS = ["TEAM", "W", "L", "PCT", "GB"]
EXTENDED_COLS = ["TEAM", "W", "L", "PCT", "GB", "HOME", "AWAY", "L10", "STK"]

# Minimum card width (inches) to comfortably show extended columns
EXTENDED_MIN_WIDTH_IN = 5.0

# Relative column weight ratios (TEAM gets the remainder)
_COL_WEIGHTS: dict[str, float] = {
    "TEAM": 3.0,
    "W":    0.9,
    "L":    0.9,
    "PCT":  1.1,
    "GB":   1.1,
    "HOME": 1.3,
    "AWAY": 1.3,
    "L10":  1.0,
    "STK":  1.0,
}

# Human-readable definitions for each column (used in explainer zone)
_COL_EXPLAINERS: dict[str, str] = {
    "W":    "Wins",
    "L":    "Losses",
    "PCT":  "Win%",
    "GB":   "Games Behind",
    "HOME": "Home Record",
    "AWAY": "Away Record",
    "L10":  "Last 10 Games",
    "STK":  "Current Streak",
}

# Long-form expansions for scope labels used in card titles
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

# Maps each scope to the logo pseudo-abbrev used by logo_cache.py
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


@dataclass
class StandingsCardConfig(CardConfig):
    scope: str = "All MLB"
    column_mode: str = "auto"     # "standard", "extended", "auto"
    show_logos: bool = True
    show_timestamp: bool = False
    show_col_explainers: bool = False
    col_explainer_sep: str = "="
    title_override: str = ""

    # Colors
    header_bg: str = "#1a3a5c"
    header_fg: str = "#FFFFFF"
    title_bg: str = "#1a3a5c"
    title_fg: str = "#FFFFFF"
    row_alt_color: str = "#EEF2F7"
    row_color: str = "#FFFFFF"
    divider_color: str = "#CCCCCC"
    div_header_bg: str = "#2c5f8a"
    div_header_fg: str = "#FFFFFF"
    text_color: str = "#111111"
    footer_color: str = "#888888"


def suggest_column_mode(width_in: float) -> str:
    """Return 'extended' or 'standard' based on card width."""
    return "extended" if width_in >= EXTENDED_MIN_WIDTH_IN else "standard"


def resolve_columns(config: StandingsCardConfig) -> list[str]:
    mode = config.column_mode
    if mode == "auto":
        mode = suggest_column_mode(config.width_in)
    return EXTENDED_COLS if mode == "extended" else STANDARD_COLS


def _pt_px(pt: float, dpi: int) -> int:
    """Convert a point size to pixels at the given DPI."""
    return max(1, round(pt * dpi / 72))


def _col_widths_px(columns: list[str], total_px: int, padding_px: int) -> list[int]:
    """Distribute total_px across columns according to weight ratios."""
    total_weight = sum(_COL_WEIGHTS.get(c, 1.0) for c in columns)
    usable = max(1, total_px - padding_px * 2)  # clamp: never negative
    widths = []
    allocated = 0
    for i, col in enumerate(columns):
        if i == len(columns) - 1:
            widths.append(max(1, usable - allocated))
        else:
            w = max(1, round(usable * (_COL_WEIGHTS.get(col, 1.0) / total_weight)))
            widths.append(w)
            allocated += w
    return widths


def _get_col_value(entry: StandingsEntry, col: str) -> str:
    mapping = {
        "TEAM": entry.team_abbrev,
        "W":    str(entry.wins),
        "L":    str(entry.losses),
        "PCT":  entry.pct,
        "GB":   entry.gb,
        "HOME": entry.home_record,
        "AWAY": entry.away_record,
        "L10":  entry.last_ten,
        "STK":  entry.streak,
    }
    return mapping.get(col, "")


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

class StandingsCardRenderer:

    def __init__(self, config: StandingsCardConfig, block: StandingsBlock,
                 working_dir: str = ""):
        self.config = config
        self.block = block
        self.working_dir = working_dir
        self.last_warning: str | None = None

    def render(self) -> Image.Image:
        cfg = self.config
        img = cfg.new_canvas()
        draw = ImageDraw.Draw(img)

        columns = resolve_columns(cfg)
        entries = filter_standings(self.block, cfg.scope)
        groups = group_by_division(entries)

        W, H = cfg.width_px, cfg.height_px
        PAD = max(8, round(W * 0.012))

        # Count rows: division headers + team rows
        num_divs = len(groups)
        num_teams = len(entries)
        # +1 for title bar, +1 for column header
        reserved_rows = 2
        total_data_rows = num_divs + num_teams

        # --- Font sizing ---
        title_h = max(24, round(H * 0.07))
        col_header_h = max(16, round(H * 0.055))
        footer_h = max(12, round(H * 0.04)) if cfg.show_timestamp else 0
        _expl_font_sz = max(7, _pt_px(6, cfg.dpi))
        _expl_line_h  = max(8, round(_expl_font_sz * 1.6))
        explainer_h   = (_expl_line_h * 2 + 6) if cfg.show_col_explainers else 0
        available_h = H - title_h - col_header_h - footer_h - explainer_h - PAD
        row_h = max(14, available_h // max(total_data_rows, 1))
        self.last_warning = None
        if cfg.show_col_explainers:
            min_row_h = _pt_px(7, cfg.dpi)
            if row_h < min_row_h:
                row_pt = round(row_h * 72 / cfg.dpi, 1)
                self.last_warning = (
                    f"Explainers leave rows at {row_pt}pt "
                    f"(min ~7pt) — increase card height or disable explainers"
                )

        # Cap font sizes at sensible physical point values
        title_font_size   = min(max(10, round(title_h * 0.52)),      _pt_px(18, cfg.dpi))
        header_font_size  = min(max(8,  round(col_header_h * 0.52)), _pt_px(10, cfg.dpi))
        row_font_size     = min(max(7,  round(row_h * 0.52)),        _pt_px(11, cfg.dpi))
        div_font_size     = min(max(7,  round(row_h * 0.48)),        _pt_px(10, cfg.dpi))
        footer_font_size  = min(max(7,  round(footer_h * 0.60)),     _pt_px(8,  cfg.dpi)) if footer_h else 8

        title_font = get_font(title_font_size, bold=True)
        header_font = get_font(header_font_size, bold=True, condensed=True)
        row_font = get_font(row_font_size, condensed=True)
        div_font = get_font(div_font_size, bold=True, condensed=True)
        footer_font = get_font(footer_font_size)

        # Logo size = row_h minus small padding
        logo_sz = max(8, row_h - 4)

        # Column widths
        col_widths = _col_widths_px(columns, W, PAD)

        y = 0

        # --- Title bar ---
        _tlogo_sz = title_h - 8
        _tlogo_abbrev = _SCOPE_LOGO.get(cfg.scope) if self.working_dir else None
        title_text = cfg.title_override or self._title_text(title_font, W - PAD * 2)
        draw.rectangle([0, y, W, y + title_h], fill=cfg.title_bg)
        if _tlogo_abbrev:
            tlogo = get_logo(_tlogo_abbrev, _tlogo_sz, self.working_dir)
            if tlogo:
                gap = 8
                tbbox = title_font.getbbox(title_text)
                text_w = tbbox[2] - tbbox[0]
                group_w = _tlogo_sz + gap + text_w
                group_x = max(PAD, (W - group_w) // 2)
                ly = y + (title_h - _tlogo_sz) // 2
                img.paste(tlogo, (group_x, ly), tlogo)
                th = tbbox[3] - tbbox[1]
                tx = group_x + _tlogo_sz + gap
                ty = y + (title_h - th) // 2 - tbbox[1]
                draw.text((tx, ty), title_text, font=title_font, fill=cfg.title_fg)
            else:
                self._draw_centered_text(draw, title_text, y, title_h, title_font, cfg.title_fg, W)
        else:
            self._draw_centered_text(draw, title_text, y, title_h, title_font, cfg.title_fg, W)
        y += title_h

        # --- Column header row ---
        draw.rectangle([0, y, W, y + col_header_h], fill=cfg.header_bg)
        x = PAD
        for col, cw in zip(columns, col_widths):
            label = col
            if col == "TEAM":
                self._draw_left_text(draw, label, x, y, col_header_h, header_font, cfg.header_fg)
            else:
                self._draw_centered_col(draw, label, x, cw, y, col_header_h, header_font, cfg.header_fg)
            x += cw
        y += col_header_h

        # --- Data rows ---
        for div_name, div_entries in groups.items():
            # Division sub-header (only when showing multiple divisions)
            if num_divs > 1:
                draw.rectangle([0, y, W, y + row_h], fill=cfg.div_header_bg)
                self._draw_left_text(draw, f"  {div_name}", PAD, y, row_h, div_font, cfg.div_header_fg)
                y += row_h

            # Reset stripe within each division so row 1 is always white
            alt = False
            for entry in div_entries:
                row_bg = cfg.row_alt_color if alt else cfg.row_color
                draw.rectangle([0, y, W, y + row_h], fill=row_bg)
                alt = not alt

                x = PAD
                for col, cw in zip(columns, col_widths):
                    if col == "TEAM":
                        tx = x
                        if cfg.show_logos and self.working_dir:
                            logo = get_logo(entry.team_abbrev, logo_sz, self.working_dir)
                            if logo:
                                ly = y + (row_h - logo_sz) // 2
                                img.paste(logo, (tx, ly), logo)
                                tx += logo_sz + 3
                        # Measure available width and choose full name or abbrev
                        avail_w = cw - (tx - x) - 6
                        name_str = entry.team_name
                        if row_font.getbbox(name_str)[2] > avail_w:
                            name_str = entry.team_abbrev
                        self._draw_left_text(draw, name_str, tx, y, row_h, row_font, cfg.text_color)
                    else:
                        val = _get_col_value(entry, col)
                        self._draw_centered_col(draw, val, x, cw, y, row_h, row_font, cfg.text_color)
                    x += cw

                # Bottom divider
                draw.line([PAD, y + row_h - 1, W - PAD, y + row_h - 1], fill=cfg.divider_color)
                y += row_h

        # --- Column explainers ---
        if cfg.show_col_explainers and explainer_h > 0:
            expl_font = get_font(_expl_font_sz)
            sep = cfg.col_explainer_sep
            items = [f"{col}{sep}{_COL_EXPLAINERS[col]}"
                     for col in columns if col in _COL_EXPLAINERS]
            dot = "  ·  "
            zone_top = H - footer_h - explainer_h
            draw.rectangle([0, zone_top, W, zone_top + explainer_h], fill=cfg.bg_color)
            draw.line([PAD, zone_top + 1, W - PAD, zone_top + 1], fill=cfg.divider_color)
            inner_top = zone_top + 4
            inner_h = explainer_h - 4
            avail_w = W - PAD * 2
            full_text = dot.join(items)
            bbox0 = expl_font.getbbox(full_text)
            tw = bbox0[2] - bbox0[0]
            if tw <= avail_w:
                th = bbox0[3] - bbox0[1]
                tx = (W - tw) // 2
                ty = inner_top + (inner_h - th) // 2 - bbox0[1]
                draw.text((tx, ty), full_text, font=expl_font, fill=cfg.footer_color)
            else:
                mid = max(1, len(items) // 2)
                lines = [dot.join(items[:mid]), dot.join(items[mid:])]
                for i, line_text in enumerate(lines):
                    lbbox = expl_font.getbbox(line_text)
                    lw = lbbox[2] - lbbox[0]
                    if lw > avail_w:
                        while len(line_text) > 4 and \
                              expl_font.getbbox(line_text + "\u2026")[2] > avail_w:
                            line_text = line_text[:-1]
                        line_text = line_text.rstrip(" ·") + "\u2026"
                        lbbox = expl_font.getbbox(line_text)
                    lh = lbbox[3] - lbbox[1]
                    tx = (W - (lbbox[2] - lbbox[0])) // 2
                    ty = inner_top + i * _expl_line_h + (_expl_line_h - lh) // 2 - lbbox[1]
                    draw.text((tx, ty), line_text, font=expl_font, fill=cfg.footer_color)

        # --- Footer timestamp ---
        if cfg.show_timestamp and footer_h:
            ts = self.block.as_of.strftime("Data as of %b %d, %Y  %I:%M %p")
            draw.rectangle([0, H - footer_h, W, H], fill=cfg.bg_color)
            self._draw_centered_text(draw, ts, H - footer_h, footer_h, footer_font, cfg.footer_color, W)

        return img

    # ------------------------------------------------------------------
    # Text helpers
    # ------------------------------------------------------------------

    def _title_text(self, font, avail_w: int) -> str:
        scope = self.config.scope
        short = "MLB Standings" if scope == "All MLB" else f"{scope} Standings"
        long_scope = _SCOPE_EXPAND.get(scope, scope)
        long = "MLB Standings" if scope == "All MLB" else f"{long_scope} Standings"
        if long != short:
            bbox = font.getbbox(long)
            if (bbox[2] - bbox[0]) <= avail_w:
                return long
        return short

    @staticmethod
    def _draw_centered_text(draw: ImageDraw.ImageDraw, text: str, y: int, h: int,
                             font, color: str, width: int) -> None:
        bbox = font.getbbox(text)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        x = (width - tw) // 2 - bbox[0]
        ty = y + (h - th) // 2 - bbox[1]
        draw.text((x, ty), text, font=font, fill=color)

    @staticmethod
    def _draw_centered_col(draw: ImageDraw.ImageDraw, text: str, col_x: int,
                            col_w: int, row_y: int, row_h: int, font, color: str) -> None:
        bbox = font.getbbox(text)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        x = col_x + (col_w - tw) // 2 - bbox[0]
        ty = row_y + (row_h - th) // 2 - bbox[1]
        draw.text((x, ty), text, font=font, fill=color)

    @staticmethod
    def _draw_left_text(draw: ImageDraw.ImageDraw, text: str, x: int,
                         row_y: int, row_h: int, font, color: str) -> None:
        bbox = font.getbbox(text)
        th = bbox[3] - bbox[1]
        ty = row_y + (row_h - th) // 2
        draw.text((x, ty), text, font=font, fill=color)
