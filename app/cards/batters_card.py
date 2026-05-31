from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Optional

from PIL import Image, ImageDraw

from app.cards.base_card import CardConfig
from app.data.batters_api import BatterEntry, BattersBlock, is_team_scope
from app.data.logo_cache import get_logo
from app.utils.font_manager import get_font

# ---------------------------------------------------------------------------
# Column definitions
# ---------------------------------------------------------------------------

# Standard columns (no TEAM when scope is a single team — resolved at render time)
REDUCED_COLS       = ["RANK", "PLAYER", "TEAM", "AVG", "HR", "RBI", "OPS"]
STANDARD_COLS      = ["RANK", "PLAYER", "TEAM", "AVG", "HR", "RBI", "OBP", "SLG", "OPS"]
EXTENDED_COLS      = ["RANK", "PLAYER", "TEAM", "AVG", "HR", "RBI", "OBP", "SLG", "OPS",
                       "H", "AB", "BB", "SO", "SB"]
REDUCED_COLS_NT    = ["RANK", "PLAYER", "AVG", "HR", "RBI", "OPS"]
STANDARD_COLS_NT   = ["RANK", "PLAYER", "AVG", "HR", "RBI", "OBP", "SLG", "OPS"]
EXTENDED_COLS_NT   = ["RANK", "PLAYER", "AVG", "HR", "RBI", "OBP", "SLG", "OPS",
                       "H", "AB", "BB", "SO", "SB"]

EXTENDED_MIN_WIDTH_IN = 6.0
STANDARD_MIN_WIDTH_IN = 4.5

# Relative column weight ratios (PLAYER gets most space)
_COL_WEIGHTS: dict[str, float] = {
    "RANK":   0.85,
    "PLAYER": 3.5,
    "TEAM":   1.1,
    "AVG":    1.0,
    "HR":     0.8,
    "RBI":    0.8,
    "OBP":    1.0,
    "SLG":    1.0,
    "OPS":    1.0,
    "H":      0.8,
    "AB":     0.8,
    "BB":     0.8,
    "SO":     0.8,
    "SB":     0.7,
}

# Columns where values are right-aligned — only rate stats (all start with "0.")
# Integer stats (HR, RBI, H, AB, BB, SO, SB) are centered to match their headers
_RIGHT_ALIGN_COLS = {"AVG", "OBP", "SLG", "OPS"}

# Badge fill colours for ranks 1-3
_BADGE_COLORS = {
    1: "#D4AF37",  # gold
    2: "#C0C0C0",  # silver
    3: "#B87333",  # copper
}

# Darker outline ring to give an engraved medal look
_BADGE_OUTLINE_COLORS = {
    1: "#9A7B1A",  # deep gold
    2: "#808080",  # dark silver
    3: "#7A4A20",  # dark copper
}

# Human-readable definitions for each column (used in explainer zone)
_COL_EXPLAINERS: dict[str, str] = {
    "AVG": "Batting Avg",
    "HR":  "Home Runs",
    "RBI": "Runs Batted In",
    "OBP": "On-Base %",
    "SLG": "Slugging %",
    "OPS": "OBP + SLG",
    "H":   "Hits",
    "AB":  "At Bats",
    "BB":  "Walks",
    "SO":  "Strikeouts",
    "SB":  "Stolen Bases",
}

# Long-form expansions for scope labels and sort-stat names used in card titles
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

# Maps each non-team scope to the logo pseudo-abbrev used by logo_cache.py
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

_STAT_EXPAND: dict[str, str] = {
    "AVG": "Batting Average",
    "OBP": "On-Base Percentage",
    "SLG": "Slugging Percentage",
    "OPS": "OBP + Slugging",
    "HR":  "Home Runs",
    "RBI": "Runs Batted In",
    "H":   "Hits",
    "AB":  "At Bats",
    "BB":  "Walks",
    "SO":  "Strikeouts",
    "SB":  "Stolen Bases",
}


def suggest_column_mode(width_in: float) -> str:
    if width_in >= EXTENDED_MIN_WIDTH_IN:
        return "extended"
    if width_in >= STANDARD_MIN_WIDTH_IN:
        return "standard"
    return "reduced"


def resolve_columns(config: BattersCardConfig) -> list[str]:
    mode = config.column_mode
    if mode == "auto":
        mode = suggest_column_mode(config.width_in)
    no_team = is_team_scope(config.scope)
    if mode == "extended":
        return EXTENDED_COLS_NT if no_team else EXTENDED_COLS
    if mode == "reduced":
        return REDUCED_COLS_NT if no_team else REDUCED_COLS
    return STANDARD_COLS_NT if no_team else STANDARD_COLS


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


def _get_col_value(entry: BatterEntry, col: str, rank: int) -> str:
    mapping = {
        "RANK":   str(rank),
        "PLAYER": entry.player_name,
        "TEAM":   entry.team_abbrev,
        "AVG":    entry.avg,
        "HR":     str(entry.home_runs),
        "RBI":    str(entry.rbi),
        "OBP":    entry.obp,
        "SLG":    entry.slg,
        "OPS":    entry.ops,
        "H":      str(entry.hits),
        "AB":     str(entry.at_bats),
        "BB":     str(entry.walks),
        "SO":     str(entry.strikeouts),
        "SB":     str(entry.stolen_bases),
    }
    return mapping.get(col, "")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class BattersCardConfig(CardConfig):
    scope: str = "All MLB"
    column_mode: str = "auto"       # "standard", "extended", "auto"
    sort_stat: str = "OPS"
    top_n: int = 10
    min_pa: int = 50
    show_timestamp: bool = False
    title_override: str = ""

    show_rank_badges: bool = True
    show_logos: bool = True
    simple_title: bool = False
    show_jersey_number: bool = False
    show_position: bool = False
    show_col_explainers: bool = False
    col_explainer_sep: str = "="

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

class BattersCardRenderer:

    def __init__(self, config: BattersCardConfig, entries: list[BatterEntry],
                 block: BattersBlock, working_dir: str = ""):
        self.config = config
        self.entries = entries   # already filtered, sorted, trimmed
        self.block = block
        self.working_dir = working_dir
        self.last_warning: str | None = None

    def render(self) -> Image.Image:
        cfg = self.config
        img = cfg.new_canvas()
        draw = ImageDraw.Draw(img)

        columns = resolve_columns(cfg)
        W, H = cfg.width_px, cfg.height_px
        PAD = max(8, round(W * 0.012))

        # --- Font sizing ---
        num_rows = len(self.entries)
        title_h       = max(24, round(H * 0.07))
        col_header_h  = max(16, round(H * 0.055))
        footer_h      = max(12, round(H * 0.04)) if cfg.show_timestamp else 0
        _expl_font_sz = max(7, _pt_px(6, cfg.dpi))
        _expl_line_h  = max(8, round(_expl_font_sz * 1.6))
        explainer_h   = (_expl_line_h * 2 + 6) if cfg.show_col_explainers else 0
        available_h   = H - title_h - col_header_h - footer_h - explainer_h - PAD
        row_h         = max(14, available_h // max(num_rows, 1))
        self.last_warning = None
        if cfg.show_col_explainers:
            min_row_h = _pt_px(7, cfg.dpi)
            if row_h < min_row_h:
                row_pt = round(row_h * 72 / cfg.dpi, 1)
                self.last_warning = (
                    f"Explainers leave rows at {row_pt}pt "
                    f"(min ~7pt) — increase card height or disable explainers"
                )

        title_font_size  = min(max(10, round(title_h * 0.52)),      _pt_px(18, cfg.dpi))
        header_font_size = min(max(8,  round(col_header_h * 0.52)), _pt_px(10, cfg.dpi))
        row_font_size    = min(max(7,  round(row_h * 0.52)),        _pt_px(11, cfg.dpi))
        footer_font_size = min(max(7,  round(footer_h * 0.60)),     _pt_px(8,  cfg.dpi)) if footer_h else 8

        title_font  = get_font(title_font_size, bold=True)
        header_font = get_font(header_font_size, bold=True, condensed=True)
        row_font    = get_font(row_font_size, condensed=True)
        footer_font = get_font(footer_font_size)

        col_widths = _col_widths_px(columns, W, PAD)
        logo_sz = max(8, round(row_h * 0.65)) if cfg.show_logos else 0

        y = 0

        # --- Title bar ---
        _tlogo_sz = title_h - 8
        _scope_logo_abbrev = (
            self.entries[0].team_abbrev if is_team_scope(cfg.scope)
            else _SCOPE_LOGO.get(cfg.scope)
        )
        _has_title_logo = (
            cfg.show_logos and bool(self.working_dir)
            and _scope_logo_abbrev is not None
            and (is_team_scope(cfg.scope) or bool(self.entries))
        )
        _title_avail = max(1, (W - PAD * 2 - _tlogo_sz - 8) if _has_title_logo
                           else (W - PAD * 2))
        title_text = cfg.title_override or self._title_text(title_font, _title_avail)
        draw.rectangle([0, y, W, y + title_h], fill=cfg.title_bg)
        if _has_title_logo:
            tlogo = get_logo(_scope_logo_abbrev, _tlogo_sz, self.working_dir)
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
                self._draw_centered_text_in_range(
                    draw, title_text, PAD, W, y, title_h, title_font, cfg.title_fg)
        else:
            self._draw_centered_text_in_range(
                draw, title_text, PAD, W, y, title_h, title_font, cfg.title_fg)
        y += title_h

        # --- Column header row ---
        draw.rectangle([0, y, W, y + col_header_h], fill=cfg.header_bg)
        x = PAD
        for col, cw in zip(columns, col_widths):
            lbl = "#" if col == "RANK" else col
            if col == "RANK":
                self._draw_centered_col(draw, lbl, x, cw, y, col_header_h,
                                        header_font, cfg.header_fg)
            elif col == "PLAYER":
                self._draw_left_text(draw, lbl, x, y, col_header_h,
                                     header_font, cfg.header_fg)
            elif col in _RIGHT_ALIGN_COLS:
                self._draw_right_col(draw, lbl, x, cw, y, col_header_h,
                                     header_font, cfg.header_fg)
            else:
                self._draw_centered_col(draw, lbl, x, cw, y, col_header_h,
                                        header_font, cfg.header_fg)
            x += cw
        # Divider line under header
        draw.line([0, y + col_header_h - 1, W, y + col_header_h - 1],
                  fill=cfg.divider_color)
        y += col_header_h

        # --- Data rows ---
        for rank_idx, entry in enumerate(self.entries, start=1):
            alt = (rank_idx % 2 == 0)
            row_bg = cfg.row_alt_color if alt else cfg.row_color
            draw.rectangle([0, y, W, y + row_h], fill=row_bg)

            x = PAD
            for col, cw in zip(columns, col_widths):
                val = _get_col_value(entry, col, rank_idx)
                if col == "RANK":
                    if cfg.show_rank_badges and rank_idx in _BADGE_COLORS:
                        badge_size = max(8, min(cw - 8, round(row_h * 0.60)))
                        bx = x + (cw - badge_size) // 2
                        by = y + (row_h - badge_size) // 2
                        outline_w = max(1, round(badge_size * 0.12))
                        # Darker shade of the medal colour for the outline
                        outline_col = _BADGE_OUTLINE_COLORS[rank_idx]
                        draw.ellipse([bx, by, bx + badge_size, by + badge_size],
                                     fill=_BADGE_COLORS[rank_idx],
                                     outline=outline_col, width=outline_w)
                    self._draw_centered_col(draw, val, x, cw, y, row_h,
                                            row_font, "#1a1a1a")
                elif col == "PLAYER":
                    avail_w = cw - 6
                    name = entry.player_name
                    jersey = f" #{entry.jersey_number}" if (cfg.show_jersey_number and entry.jersey_number) else ""
                    pos    = f" ({entry.position})"    if (cfg.show_position   and entry.position)       else ""
                    full = name + jersey + pos
                    if row_font.getbbox(full)[2] > avail_w:
                        # drop position suffix first, then jersey number, then truncate name
                        full = name + jersey
                        if row_font.getbbox(full)[2] > avail_w:
                            full = name
                            if row_font.getbbox(full)[2] > avail_w:
                                parts = name.split()
                                full = parts[-1] if parts else name
                    self._draw_left_text(draw, full, x, y, row_h, row_font, cfg.text_color)
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
                elif col in _RIGHT_ALIGN_COLS:
                    self._draw_right_col(draw, val, x, cw, y, row_h,
                                         row_font, cfg.text_color)
                else:
                    self._draw_centered_col(draw, val, x, cw, y, row_h,
                                            row_font, cfg.text_color)
                x += cw

            # Bottom divider
            draw.line([PAD, y + row_h - 1, W - PAD, y + row_h - 1],
                      fill=cfg.divider_color)
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
            self._draw_centered_text(draw, ts, H - footer_h, footer_h,
                                     footer_font, cfg.footer_color, W)

        return img

    # ------------------------------------------------------------------
    # Text helpers
    # ------------------------------------------------------------------

    def _title_text(self, font, avail_w: int) -> str:
        cfg = self.config
        scope = cfg.scope
        sort = cfg.sort_stat
        n = cfg.top_n
        simple = cfg.simple_title
        if is_team_scope(scope) and self.entries:
            team_name = self.entries[0].team_name
            if simple:
                return f"{team_name} Top Batters"
            short = f"{team_name} Top {n} by {sort}"
            long_stat = _STAT_EXPAND.get(sort, sort)
            long = f"{team_name} Top {n} by {long_stat}"
            if long != short:
                bbox = font.getbbox(long)
                if (bbox[2] - bbox[0]) <= avail_w:
                    return long
            return short
        long_scope = _SCOPE_EXPAND.get(scope, scope)
        label_s = scope if scope != "All MLB" else "MLB"
        label_l = long_scope if scope != "All MLB" else "MLB"
        if simple:
            short  = f"{label_s} Top Batters"
            long   = f"{label_l} Top Batters"
            bbox = font.getbbox(long)
            if (bbox[2] - bbox[0]) <= avail_w:
                return long
            return short
        long_stat = _STAT_EXPAND.get(sort, sort)
        short  = f"{label_s} Top {n} Batters by {sort}"
        medium = f"{label_s} Top {n} Batters by {long_stat}"
        long   = f"{label_l} Top {n} Batters by {long_stat}"
        bbox = font.getbbox(long)
        if (bbox[2] - bbox[0]) <= avail_w:
            return long
        bbox = font.getbbox(medium)
        if (bbox[2] - bbox[0]) <= avail_w:
            return medium
        return short

    @staticmethod
    def _draw_centered_text(draw, text, y, h, font, color, width):
        bbox = font.getbbox(text)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        x = (width - tw) // 2 - bbox[0]
        ty = y + (h - th) // 2 - bbox[1]
        draw.text((x, ty), text, font=font, fill=color)

    @staticmethod
    def _draw_centered_text_in_range(draw, text, x0, x1, y, h, font, color):
        """Center text horizontally within [x0, x1]."""
        bbox = font.getbbox(text)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        x = x0 + ((x1 - x0) - tw) // 2 - bbox[0]
        ty = y + (h - th) // 2 - bbox[1]
        draw.text((x, ty), text, font=font, fill=color)

    @staticmethod
    def _draw_centered_col(draw, text, col_x, col_w, row_y, row_h, font, color):
        bbox = font.getbbox(text)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        x = col_x + (col_w - tw) // 2 - bbox[0]
        ty = row_y + (row_h - th) // 2 - bbox[1]
        draw.text((x, ty), text, font=font, fill=color)

    @staticmethod
    def _draw_left_text(draw, text, x, row_y, row_h, font, color):
        bbox = font.getbbox(text)
        th = bbox[3] - bbox[1]
        ty = row_y + (row_h - th) // 2 - bbox[1]
        draw.text((x, ty), text, font=font, fill=color)

    @staticmethod
    def _draw_right_col(draw, text, col_x, col_w, row_y, row_h, font, color):
        """Right-align text within a column with a small right margin."""
        bbox = font.getbbox(text)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        x = col_x + col_w - tw - 5 - bbox[0]
        ty = row_y + (row_h - th) // 2 - bbox[1]
        draw.text((x, ty), text, font=font, fill=color)
