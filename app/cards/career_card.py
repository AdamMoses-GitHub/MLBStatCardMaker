from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Union

from PIL import Image, ImageDraw

from app.cards.base_card import CardConfig
from app.data.career_api import CareerBlock, CareerBattingEntry, CareerPitchingEntry
from app.data.logo_cache import get_logo
from app.utils.font_manager import get_font

# ---------------------------------------------------------------------------
# Column definitions
# ---------------------------------------------------------------------------

BATTING_COLS_FULL    = ["YEAR", "TEAM", "AVG", "HR", "RBI", "OBP", "SLG", "OPS"]
BATTING_COLS_REDUCED = ["YEAR", "TEAM", "AVG", "HR", "RBI", "OPS"]
PITCHING_COLS_FULL   = ["YEAR", "TEAM", "W", "L", "ERA", "IP", "SO", "WHIP"]
PITCHING_COLS_REDUCED = ["YEAR", "TEAM", "W", "L", "ERA", "SO"]

# Inches below which we switch to reduced columns
REDUCED_BELOW_IN = 5.5

# Proportional widths per column
_COL_WEIGHTS: dict[str, float] = {
    "YEAR": 0.80,
    "TEAM": 1.20,
    "AVG":  0.90,
    "HR":   0.65,
    "RBI":  0.70,
    "OBP":  0.90,
    "SLG":  0.90,
    "OPS":  0.90,
    "W":    0.60,
    "L":    0.60,
    "ERA":  0.85,
    "IP":   0.85,
    "SO":   0.75,
    "WHIP": 0.85,
}

# Human-readable column headers
_COL_HEADERS: dict[str, str] = {
    "YEAR": "Year",
    "TEAM": "Team",
    "AVG":  "AVG",
    "HR":   "HR",
    "RBI":  "RBI",
    "OBP":  "OBP",
    "SLG":  "SLG",
    "OPS":  "OPS",
    "W":    "W",
    "L":    "L",
    "ERA":  "ERA",
    "IP":   "IP",
    "SO":   "SO",
    "WHIP": "WHIP",
}

# Alignment: "L" left, "C" center, "R" right
_COL_ALIGN: dict[str, str] = {
    "YEAR": "C",
    "TEAM": "L",
    "AVG":  "R",
    "HR":   "C",
    "RBI":  "C",
    "OBP":  "R",
    "SLG":  "R",
    "OPS":  "R",
    "W":    "C",
    "L":    "C",
    "ERA":  "R",
    "IP":   "R",
    "SO":   "C",
    "WHIP": "R",
}

# Current-season highlight background (same tint as history card)
_CURRENT_SEASON_BG = "#FFF8DC"

_MULTILOADED_ABBREVS = ("2 TM", "3 TM", "4 TM", "5 TM")

_COL_EXPLAINERS: dict[str, str] = {
    "YEAR": "Season",
    "TEAM": "Team",
    "AVG":  "Batting Average",
    "HR":   "Home Runs",
    "RBI":  "Runs Batted In",
    "OBP":  "On-Base Pct",
    "SLG":  "Slugging Pct",
    "OPS":  "OBP + SLG",
    "W":    "Wins",
    "L":    "Losses",
    "ERA":  "Earned Run Avg",
    "IP":   "Innings Pitched",
    "SO":   "Strikeouts",
    "WHIP": "Walks+Hits per IP",
}


def _pt_px(pt: float, dpi: int) -> int:
    return max(1, round(pt * dpi / 72))


def _entry_value(entry: Union[CareerBattingEntry, CareerPitchingEntry],
                  col: str) -> str:
    """Return the display string for a given column."""
    if col == "YEAR":
        return str(entry.season)
    if col == "TEAM":
        return entry.team_abbrev
    # Batting
    if isinstance(entry, CareerBattingEntry):
        mapping = {
            "AVG": entry.avg, "HR": str(entry.home_runs),
            "RBI": str(entry.rbi), "OBP": entry.obp,
            "SLG": entry.slg, "OPS": entry.ops,
        }
        return mapping.get(col, "")
    # Pitching
    mapping = {
        "W":   str(entry.wins),       "L":   str(entry.losses),
        "ERA": entry.era,             "IP":  entry.innings_pitched,
        "SO":  str(entry.strikeouts), "WHIP": entry.whip,
    }
    return mapping.get(col, "")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class CareerCardConfig(CardConfig):
    stat_type: str = "Batting"
    show_logos: bool = True
    highlight_current: bool = True
    show_timestamp: bool = False
    show_col_explainers: bool = False
    col_explainer_sep: str = "="
    year_sort: str = "Ascending"   # "Ascending" or "Descending"
    title_override: str = ""

    # Colors
    title_bg: str = "#1a3a5c"
    title_fg: str = "#FFFFFF"
    header_bg: str = "#1a3a5c"
    header_fg: str = "#FFFFFF"
    row_alt_color: str = "#EEF2F7"
    row_color: str = "#FFFFFF"
    divider_color: str = "#CCCCCC"
    text_color: str = "#111111"
    footer_color: str = "#888888"


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

class CareerCardRenderer:

    def __init__(self, config: CareerCardConfig, block: CareerBlock,
                 working_dir: str = ""):
        self.config      = config
        self.block       = block
        self.working_dir = working_dir

    def render(self) -> Image.Image:
        cfg   = self.config
        block = self.block
        img   = cfg.new_canvas()
        draw  = ImageDraw.Draw(img)

        W, H = cfg.width_px, cfg.height_px
        PAD  = max(8, round(W * 0.012))

        num_rows = len(block.entries)

        # Apply year sort order (block.entries are always stored ascending)
        entries = block.entries if cfg.year_sort != "Descending" else list(reversed(block.entries))

        title_h    = max(32, round(H * 0.105))
        hdr_h      = max(18, round(H * 0.055))
        footer_h   = max(12, round(H * 0.04)) if cfg.show_timestamp else 0
        _expl_font_sz = max(7, _pt_px(6, cfg.dpi))
        _expl_line_h  = max(8, round(_expl_font_sz * 1.6))
        explainer_h   = (_expl_line_h * 2 + 6) if cfg.show_col_explainers else 0
        avail_h    = H - title_h - hdr_h - footer_h - explainer_h - PAD
        row_h      = max(14, avail_h // max(num_rows, 1))

        title_font_size  = min(max(10, round(title_h * 0.45)),   _pt_px(18, cfg.dpi))
        sub_font_size    = min(max(7,  round(title_h * 0.27)),   _pt_px(10, cfg.dpi))
        hdr_font_size    = min(max(8,  round(hdr_h   * 0.52)),   _pt_px(11, cfg.dpi))
        row_font_size    = min(max(7,  round(row_h   * 0.52)),   _pt_px(11, cfg.dpi))
        footer_font_size = (min(max(7, round(footer_h * 0.60)), _pt_px(8,  cfg.dpi))
                            if footer_h else 8)

        title_font  = get_font(title_font_size, bold=True)
        sub_font    = get_font(sub_font_size)
        hdr_font    = get_font(hdr_font_size, bold=True, condensed=True)
        row_font    = get_font(row_font_size, condensed=True)
        footer_font = get_font(footer_font_size)

        logo_sz      = max(8, round(row_h * 0.65)) if cfg.show_logos else 0
        title_logo_sz = title_h - 12

        # Choose columns based on card width
        use_full = (cfg.width_in >= REDUCED_BELOW_IN)
        if cfg.stat_type == "Batting":
            cols = BATTING_COLS_FULL if use_full else BATTING_COLS_REDUCED
        else:
            cols = PITCHING_COLS_FULL if use_full else PITCHING_COLS_REDUCED

        # Drop TEAM column when the player spent their whole career with one team
        _single_team = (
            len(entries) > 0
            and not any(e.multi_team for e in entries)
            and len({e.team_abbrev for e in entries}) == 1
        )
        if _single_team:
            cols = [c for c in cols if c != "TEAM"]

        # Column widths (proportional over usable width)
        usable_w = W - PAD * 2
        total_w  = sum(_COL_WEIGHTS[c] for c in cols)
        col_widths = {
            c: max(1, round(usable_w * _COL_WEIGHTS[c] / total_w))
            for c in cols
        }
        # Give any leftover pixels to the last column
        allocated = sum(col_widths[c] for c in cols[:-1])
        col_widths[cols[-1]] = max(1, usable_w - allocated)

        # Column x positions
        col_x: dict[str, int] = {}
        cx = PAD
        for c in cols:
            col_x[c] = cx
            cx += col_widths[c]

        y = 0

        # ----------------------------------------------------------------
        # Title bar — two zones: 60% player name, 40% stat-type subtitle
        # ----------------------------------------------------------------
        draw.rectangle([0, y, W, y + title_h], fill=cfg.title_bg)

        title_zone_h = round(title_h * 0.60)
        sub_zone_h   = title_h - title_zone_h

        title_text = cfg.title_override or block.player_name
        sub_text   = f"Career {'Batting' if cfg.stat_type == 'Batting' else 'Pitching'} Stats"

        # Title: player name + current team logo
        if (cfg.show_logos and self.working_dir
                and block.current_team_abbrev
                and block.current_team_abbrev not in _MULTILOADED_ABBREVS):
            tlogo = get_logo(block.current_team_abbrev, title_logo_sz, self.working_dir)
            if tlogo:
                gap    = 8
                tbbox  = title_font.getbbox(title_text)
                text_w = tbbox[2] - tbbox[0]
                grp_w  = title_logo_sz + gap + text_w
                gx     = max(PAD, (W - grp_w) // 2)
                ly     = y + (title_zone_h - title_logo_sz) // 2
                img.paste(tlogo, (gx, ly), tlogo)
                th = tbbox[3] - tbbox[1]
                tx = gx + title_logo_sz + gap
                ty = y + (title_zone_h - th) // 2 - tbbox[1]
                draw.text((tx, ty), title_text, font=title_font, fill=cfg.title_fg)
            else:
                self._draw_centered(draw, title_text, y, title_zone_h,
                                    title_font, cfg.title_fg, W)
        else:
            self._draw_centered(draw, title_text, y, title_zone_h,
                                title_font, cfg.title_fg, W)

        # Subtitle
        self._draw_centered(draw, sub_text, y + title_zone_h, sub_zone_h,
                            sub_font, cfg.title_fg, W)
        y += title_h

        # ----------------------------------------------------------------
        # Column header row
        # ----------------------------------------------------------------
        draw.rectangle([0, y, W, y + hdr_h], fill=cfg.header_bg)
        for col in cols:
            hdr_text = _COL_HEADERS[col]
            align    = _COL_ALIGN[col]
            self._draw_cell(draw, hdr_text, col_x[col], col_widths[col],
                            y, hdr_h, hdr_font, cfg.header_fg, align)
        y += hdr_h

        # ----------------------------------------------------------------
        # Data rows
        # ----------------------------------------------------------------
        for row_idx, entry in enumerate(entries):
            alt = (row_idx % 2 == 0)
            if cfg.highlight_current and entry.is_current_season:
                row_bg = _CURRENT_SEASON_BG
            else:
                row_bg = cfg.row_alt_color if alt else cfg.row_color
            draw.rectangle([0, y, W, y + row_h], fill=row_bg)

            for col in cols:
                if col == "TEAM" and not entry.multi_team:
                    tx = col_x[col]
                    if cfg.show_logos and self.working_dir and logo_sz > 0:
                        logo = get_logo(entry.team_abbrev, logo_sz, self.working_dir)
                        if logo:
                            ly = y + (row_h - logo_sz) // 2
                            img.paste(logo, (tx, ly), logo)
                            tx += logo_sz + 2
                    self._draw_left(draw, entry.team_abbrev, tx, y, row_h,
                                    row_font, cfg.text_color)
                else:
                    val   = _entry_value(entry, col)
                    align = _COL_ALIGN[col]
                    self._draw_cell(draw, val, col_x[col], col_widths[col],
                                    y, row_h, row_font, cfg.text_color, align)

            # Row divider
            draw.line([PAD, y + row_h - 1, W - PAD, y + row_h - 1],
                      fill=cfg.divider_color)
            y += row_h

        # ----------------------------------------------------------------
        # Footer
        # ----------------------------------------------------------------
        if cfg.show_timestamp and footer_h:
            ts = block.as_of.strftime("Data as of %b %d, %Y  %I:%M %p")
            draw.rectangle([0, H - footer_h, W, H], fill=cfg.bg_color)
            self._draw_centered(draw, ts, H - footer_h, footer_h,
                                footer_font, cfg.footer_color, W)

        # ----------------------------------------------------------------
        # Column explainers
        # ----------------------------------------------------------------
        if cfg.show_col_explainers and explainer_h > 0:
            expl_font = get_font(_expl_font_sz)
            sep   = cfg.col_explainer_sep
            items = [f"{col}{sep}{_COL_EXPLAINERS[col]}"
                     for col in cols if col in _COL_EXPLAINERS]
            dot = "  \u00b7  "
            zone_top = H - footer_h - explainer_h
            draw.rectangle([0, zone_top, W, zone_top + explainer_h], fill=cfg.bg_color)
            draw.line([PAD, zone_top + 1, W - PAD, zone_top + 1], fill=cfg.divider_color)
            inner_top = zone_top + 4
            inner_h   = explainer_h - 4
            avail_w   = W - PAD * 2
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
                        line_text = line_text.rstrip(" \u00b7") + "\u2026"
                        lbbox = expl_font.getbbox(line_text)
                    lh = lbbox[3] - lbbox[1]
                    tx = (W - (lbbox[2] - lbbox[0])) // 2
                    ty = inner_top + i * _expl_line_h + (_expl_line_h - lh) // 2 - lbbox[1]
                    draw.text((tx, ty), line_text, font=expl_font, fill=cfg.footer_color)

        return img

    # ------------------------------------------------------------------
    # Text helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _draw_centered(draw, text, y, h, font, color, width):
        bbox = font.getbbox(text)
        tw   = bbox[2] - bbox[0]
        th   = bbox[3] - bbox[1]
        x    = (width - tw) // 2 - bbox[0]
        ty   = y + (h - th) // 2 - bbox[1]
        draw.text((x, ty), text, font=font, fill=color)

    @staticmethod
    def _draw_left(draw, text, x, row_y, row_h, font, color):
        bbox = font.getbbox(text)
        th   = bbox[3] - bbox[1]
        ty   = row_y + (row_h - th) // 2 - bbox[1]
        draw.text((x, ty), text, font=font, fill=color)

    def _draw_cell(self, draw, text: str, cx: int, cw: int,
                   row_y: int, row_h: int, font, color: str, align: str) -> None:
        bbox = font.getbbox(text)
        tw   = bbox[2] - bbox[0]
        th   = bbox[3] - bbox[1]
        ty   = row_y + (row_h - th) // 2 - bbox[1]
        INNER_PAD = 4
        if align == "C":
            x = cx + (cw - tw) // 2 - bbox[0]
        elif align == "R":
            x = cx + cw - tw - INNER_PAD - bbox[0]
        else:  # "L"
            x = cx + INNER_PAD - bbox[0]
        draw.text((x, ty), text, font=font, fill=color)
