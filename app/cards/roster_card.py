from __future__ import annotations

import datetime
from dataclasses import dataclass

from PIL import Image, ImageDraw

from app.cards.base_card import CardConfig
from app.data.roster_api import RosterBlock, RosterEntry, POSITION_GROUPS
from app.data.logo_cache import get_logo
from app.utils.font_manager import get_font

# ---------------------------------------------------------------------------
# Column definitions
# ---------------------------------------------------------------------------

# Full column set
ALL_COLS   = ["#", "PLAYER", "POS", "B/T", "AGE"]

# Weights for proportional column widths
_COL_WEIGHTS: dict[str, float] = {
    "#":      0.65,
    "PLAYER": 4.0,
    "POS":    0.9,
    "B/T":    0.8,
    "AGE":    0.7,
}

_RIGHT_ALIGN_COLS: set[str] = {"AGE"}
_CENTER_COLS: set[str]      = {"#", "POS", "B/T"}

# Human-readable definitions for each column (used in explainer zone)
_COL_EXPLAINERS: dict[str, str] = {
    "#":   "Jersey #",
    "POS": "Position",
    "B/T": "Bats/Throws",
}

# Human-readable position abbreviations shown in the explainer zone
_POS_EXPLAINERS: dict[str, str] = {
    "C":   "Catcher",
    "1B":  "First Base",
    "2B":  "Second Base",
    "3B":  "Third Base",
    "SS":  "Shortstop",
    "LF":  "Left Field",
    "CF":  "Center Field",
    "RF":  "Right Field",
    "OF":  "Outfield",
    "DH":  "Designated Hitter",
    "SP":  "Starting Pitcher",
    "RP":  "Relief Pitcher",
    "P":   "Pitcher",
    "TWP": "Two-Way Player",
}
_POS_EXPL_ORDER: list[str] = [
    "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "OF",
    "DH", "SP", "RP", "P", "TWP",
]

# Group sub-header divider colors (alternating shades)
_GROUP_BG_COLORS: list[str] = [
    "#D6E4F7",  # light blue-grey
    "#D6EDD6",  # light green
    "#F7ECD6",  # light amber
    "#EDD6F7",  # light lavender
    "#D6F7F4",  # light teal
    "#F7D6D6",  # light rose
    "#EBF7D6",  # light lime
    "#F7F0D6",  # light gold
]
_GROUP_FG = "#1A2B3C"

# Short explanatory subtitle for each roster type (rendered below the title)
_ROSTER_TYPE_SUBTITLE: dict[str, str] = {
    "Active 26-Man": "Active 26-Man  ·  Players Eligible To Play Today",
    "40-Man":        "40-Man  ·  Full Roster Including IL & Optioned Players",
    "Main Starters": "Main Starters  ·  Projected Starting Lineup",
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


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class RosterCardConfig(CardConfig):
    team_abbrev: str = "NYY"
    roster_type: str = "Active 26-Man"
    group_by_position: bool = True
    show_jersey_number: bool = True
    show_bats_throws: bool = True
    show_age: bool = True
    show_logos: bool = True
    show_timestamp: bool = False
    hide_pitchers: bool = False
    hide_dh: bool = False
    show_col_explainers: bool = False
    col_explainer_sep: str = "="

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

class RosterCardRenderer:

    def __init__(self, config: RosterCardConfig, block: RosterBlock,
                 working_dir: str = ""):
        self.config = config
        self.block  = block
        self.working_dir = working_dir

    def render(self) -> Image.Image:
        cfg     = self.config
        entries = list(self.block.entries)
        _exclude: set[str] = set()
        if cfg.hide_pitchers:
            _exclude |= {"Starting Pitchers", "Relievers / Closers"}
        if cfg.hide_dh:
            _exclude.add("DH")
        if _exclude:
            entries = [e for e in entries if e.position_group not in _exclude]
        self.rendered_count = len(entries)
        img     = cfg.new_canvas()
        draw    = ImageDraw.Draw(img)

        W, H  = cfg.width_px, cfg.height_px
        PAD   = max(8, round(W * 0.012))

        # Active columns
        cols = self._active_cols()

        # Estimate row count (entries + group headers if grouped)
        num_rows = len(entries)
        if cfg.group_by_position:
            num_rows += len(self._groups_present(entries))

        title_h      = max(38, round(H * 0.105))
        col_header_h = max(16, round(H * 0.055))
        footer_h     = max(12, round(H * 0.04)) if cfg.show_timestamp else 0
        _expl_font_sz = max(7, _pt_px(6, cfg.dpi))
        _expl_line_h  = max(8, round(_expl_font_sz * 1.6))
        if cfg.show_col_explainers:
            _sep = cfg.col_explainer_sep
            _seen_pos = {e.position_code for e in entries}
            pos_expl_items = [
                f"{p}{_sep}{_POS_EXPLAINERS[p]}"
                for p in _POS_EXPL_ORDER if p in _seen_pos and p in _POS_EXPLAINERS
            ]
            explainer_h = _expl_line_h * (2 + (2 if pos_expl_items else 0)) + 8
        else:
            pos_expl_items = []
            explainer_h   = 0
        available_h  = H - title_h - col_header_h - footer_h - explainer_h - PAD
        row_h        = max(12, available_h // max(num_rows, 1))

        _title_zone_h    = round(title_h * 0.60)   # top zone: team name
        _sub_zone_h      = title_h - _title_zone_h    # bottom zone: roster type
        title_font_size  = min(max(10, round(_title_zone_h * 0.52)), _pt_px(18, cfg.dpi))
        sub_font_size    = min(max(7,  round(_sub_zone_h   * 0.55)), _pt_px(9,  cfg.dpi))
        header_font_size = min(max(8,  round(col_header_h  * 0.52)), _pt_px(10, cfg.dpi))
        row_font_size    = min(max(7,  round(row_h * 0.50)),        _pt_px(10, cfg.dpi))
        group_font_size  = max(6, round(row_h * 0.46))
        footer_font_size = (
            min(max(7, round(footer_h * 0.60)), _pt_px(8, cfg.dpi))
            if footer_h else 8
        )

        title_font  = get_font(title_font_size,  bold=True)
        sub_font    = get_font(sub_font_size)
        header_font = get_font(header_font_size, bold=True, condensed=True)
        row_font    = get_font(row_font_size,     condensed=True)
        group_font  = get_font(group_font_size,   bold=True, condensed=True)
        footer_font = get_font(footer_font_size)
        expl_font   = get_font(_expl_font_sz) if cfg.show_col_explainers else None

        col_widths = _col_widths_px(cols, W, PAD)
        logo_sz    = max(8, round(row_h * 0.65)) if cfg.show_logos else 0

        y = 0

        # --- Title bar ---
        _tlogo_sz = _title_zone_h - 6
        draw.rectangle([0, 0, W, title_h], fill=cfg.title_bg)
        title_text = f"{self.block.team_name} Roster"
        sub_text   = _ROSTER_TYPE_SUBTITLE.get(
            self.block.roster_type, self.block.roster_type)
        if cfg.show_logos:
            tlogo = get_logo(cfg.team_abbrev, _tlogo_sz, self.working_dir)
        else:
            tlogo = None

        if tlogo:
            gap    = 8
            tbbox  = title_font.getbbox(title_text)
            text_w = tbbox[2] - tbbox[0]
            group_w = _tlogo_sz + gap + text_w
            group_x = max(PAD, (W - group_w) // 2)
            ly = (_title_zone_h - _tlogo_sz) // 2
            img.paste(tlogo, (group_x, ly), tlogo)
            th = tbbox[3] - tbbox[1]
            tx = group_x + _tlogo_sz + gap
            ty = (_title_zone_h - th) // 2 - tbbox[1]
            draw.text((tx, ty), title_text, font=title_font, fill=cfg.title_fg)
        else:
            self._draw_centered_text_in_range(
                draw, title_text, PAD, W, 0, _title_zone_h, title_font, cfg.title_fg)
        # Subtitle: roster type explanation in the lower portion of the title bar
        self._draw_centered_text_in_range(
            draw, sub_text, PAD, W, _title_zone_h, _sub_zone_h, sub_font, cfg.title_fg)
        y += title_h

        # --- Column header row ---
        draw.rectangle([0, y, W, y + col_header_h], fill=cfg.header_bg)
        x = PAD
        for col, cw in zip(cols, col_widths):
            if col in _CENTER_COLS:
                self._draw_centered_col(draw, col, x, cw, y, col_header_h,
                                        header_font, cfg.header_fg)
            elif col in _RIGHT_ALIGN_COLS:
                self._draw_right_col(draw, col, x, cw, y, col_header_h,
                                     header_font, cfg.header_fg)
            else:
                self._draw_left_text(draw, col, x + 3, y, col_header_h,
                                     header_font, cfg.header_fg)
            x += cw
        draw.line([0, y + col_header_h - 1, W, y + col_header_h - 1],
                  fill=cfg.divider_color)
        y += col_header_h

        # --- Data rows ---
        if cfg.group_by_position:
            self._render_grouped(
                draw, img, entries, cols, col_widths,
                y, row_h, logo_sz,
                row_font, group_font,
                W, PAD, cfg,
                groups_present=self._groups_present(entries)
            )
        else:
            self._render_flat(
                draw, img, entries, cols, col_widths,
                y, row_h, logo_sz,
                row_font,
                W, PAD, cfg
            )

        # --- Footer ---
        if cfg.show_timestamp and footer_h:
            ts = self.block.as_of.strftime("Data as of %b %d, %Y  %I:%M %p")
            draw.rectangle([0, H - footer_h, W, H], fill=cfg.bg_color)
            self._draw_centered_text(draw, ts, H - footer_h, footer_h,
                                     footer_font, cfg.footer_color, W)

        # --- Column explainers ---
        if cfg.show_col_explainers and explainer_h > 0 and expl_font:
            sep       = cfg.col_explainer_sep
            col_items = [f"{col}{sep}{_COL_EXPLAINERS[col]}"
                         for col in cols if col in _COL_EXPLAINERS]
            dot       = "  ·  "
            avail_w   = W - PAD * 2
            zone_top  = H - footer_h - explainer_h
            draw.rectangle([0, zone_top, W, zone_top + explainer_h], fill=cfg.bg_color)
            draw.line([PAD, zone_top + 1, W - PAD, zone_top + 1], fill=cfg.divider_color)

            def _draw_expl_section(items: list, y_top: int, zone_h: int) -> None:
                full_text = dot.join(items)
                bbox0 = expl_font.getbbox(full_text)
                tw = bbox0[2] - bbox0[0]
                if tw <= avail_w:
                    th = bbox0[3] - bbox0[1]
                    tx = (W - tw) // 2
                    ty = y_top + (zone_h - th) // 2 - bbox0[1]
                    draw.text((tx, ty), full_text, font=expl_font, fill=cfg.footer_color)
                else:
                    mid    = max(1, len(items) // 2)
                    lines  = [dot.join(items[:mid]), dot.join(items[mid:])]
                    line_h = zone_h // 2
                    for i, line_text in enumerate(lines):
                        lbbox = expl_font.getbbox(line_text)
                        lw    = lbbox[2] - lbbox[0]
                        lx    = max(PAD, (W - lw) // 2)
                        ly_t  = y_top + i * line_h + (line_h - (lbbox[3] - lbbox[1])) // 2 - lbbox[1]
                        draw.text((lx, ly_t), line_text, font=expl_font, fill=cfg.footer_color)

            col_zone_h = _expl_line_h * 2
            _draw_expl_section(col_items, zone_top + 4, col_zone_h)

            if pos_expl_items:
                pos_zone_top = zone_top + col_zone_h + 6
                draw.line([PAD, pos_zone_top, W - PAD, pos_zone_top],
                          fill=cfg.divider_color)
                _draw_expl_section(pos_expl_items, pos_zone_top + 2, _expl_line_h * 2)

        return img

    # ------------------------------------------------------------------
    # Row rendering helpers
    # ------------------------------------------------------------------

    def _render_grouped(self, draw, img, entries, cols, col_widths,
                        y_start, row_h, logo_sz, row_font, group_font,
                        W, PAD, cfg, groups_present=None):
        if groups_present is None:
            groups_present = self._groups_present(entries)
        group_bg_cycle = {g: _GROUP_BG_COLORS[i % len(_GROUP_BG_COLORS)]
                          for i, g in enumerate(groups_present)}

        by_group: dict[str, list[RosterEntry]] = {}
        for e in entries:
            by_group.setdefault(e.position_group, []).append(e)

        y = y_start
        row_idx = 0
        for group in groups_present:
            group_entries = by_group.get(group, [])
            if not group_entries:
                continue
            # Group header row
            gbg = group_bg_cycle.get(group, "#E8EEF4")
            draw.rectangle([0, y, W, y + row_h], fill=gbg)
            label = f"\u2014  {group.upper()}  \u2014"
            self._draw_centered_text_in_range(
                draw, label, PAD, W, y, row_h, group_font, _GROUP_FG)
            draw.line([0, y + row_h - 1, W, y + row_h - 1],
                      fill=cfg.divider_color)
            y += row_h

            for entry in group_entries:
                row_bg = cfg.row_alt_color if (row_idx % 2 == 0) else cfg.row_color
                y = self._draw_data_row(
                    draw, img, entry, cols, col_widths,
                    y, row_h, logo_sz, row_font, W, PAD, cfg, row_bg)
                row_idx += 1

    def _render_flat(self, draw, img, entries, cols, col_widths,
                     y_start, row_h, logo_sz, row_font, W, PAD, cfg):
        y = y_start
        for row_idx, entry in enumerate(entries):
            row_bg = cfg.row_alt_color if (row_idx % 2 == 0) else cfg.row_color
            y = self._draw_data_row(
                draw, img, entry, cols, col_widths,
                y, row_h, logo_sz, row_font, W, PAD, cfg, row_bg)

    def _draw_data_row(self, draw, img, entry: RosterEntry,
                       cols, col_widths, y, row_h, logo_sz,
                       row_font, W, PAD, cfg, row_bg) -> int:
        draw.rectangle([0, y, W, y + row_h], fill=row_bg)
        x = PAD
        for col, cw in zip(cols, col_widths):
            if col == "#":
                self._draw_centered_col(draw, entry.jersey_number or "\u2013",
                                        x, cw, y, row_h, row_font, cfg.text_color)
            elif col == "PLAYER":
                # Optionally prefix with small logo
                tx = x
                if cfg.show_logos and self.working_dir and logo_sz > 0:
                    pass   # team logo not needed per-row (same team)
                name = entry.player_name
                avail = cw - 6
                bbox  = row_font.getbbox(name)
                if (bbox[2] - bbox[0]) > avail:
                    parts = name.split()
                    if len(parts) > 1:
                        # First initial + last name
                        name = f"{parts[0][0]}. {parts[-1]}"
                self._draw_left_text(draw, name, tx + 3, y, row_h,
                                     row_font, cfg.text_color)
            elif col == "POS":
                self._draw_centered_col(draw, entry.position_code,
                                        x, cw, y, row_h, row_font, cfg.text_color)
            elif col == "B/T":
                bt = f"{entry.bats}/{entry.throws}"
                self._draw_centered_col(draw, bt, x, cw, y, row_h,
                                        row_font, cfg.text_color)
            elif col == "AGE":
                age_str = str(entry.age) if entry.age else "\u2013"
                self._draw_right_col(draw, age_str, x, cw, y, row_h,
                                     row_font, cfg.text_color)
            x += cw
        draw.line([PAD, y + row_h - 1, W - PAD, y + row_h - 1],
                  fill=cfg.divider_color)
        return y + row_h

    # ------------------------------------------------------------------
    # Column helpers
    # ------------------------------------------------------------------

    def _active_cols(self) -> list[str]:
        cfg  = self.config
        cols = []
        if cfg.show_jersey_number:
            cols.append("#")
        cols.append("PLAYER")
        cols.append("POS")
        if cfg.show_bats_throws:
            cols.append("B/T")
        if cfg.show_age:
            cols.append("AGE")
        return cols

    def _groups_present(self, entries=None) -> list[str]:
        src = entries if entries is not None else self.block.entries
        seen = {e.position_group for e in src}
        return [g for g in POSITION_GROUPS if g in seen]

    # ------------------------------------------------------------------
    # Text drawing utilities
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
