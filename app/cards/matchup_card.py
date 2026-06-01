from __future__ import annotations

import datetime
from dataclasses import dataclass

from PIL import Image, ImageDraw

from app.cards.base_card import CardConfig
from app.data.matchup_api import MatchupBlock, TeamStats, compare, get_stat_rows
from app.data.logo_cache import get_logo
from app.utils.font_manager import get_font

# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------

# Column proportions: left stat value | center label | right stat value
_LEFT_W   = 2.0
_CENTER_W = 1.4
_RIGHT_W  = 2.0
_TOTAL_W  = _LEFT_W + _CENTER_W + _RIGHT_W

_WIN_HIGHLIGHT_DEFAULT = "#D4EDDA"   # soft green
_TIE_BG  = None                      # no highlight

# Explainer text for each stat abbreviation used in the center label column
_COL_EXPLAINERS: dict[str, str] = {
    "W-L":    "Wins – Losses",
    "RS/G":   "Runs Scored per Game",
    "ERA":    "Earned Run Average",
    "WHIP":   "Walks + Hits per IP",
    "AVG":    "Batting Average",
    "HR":     "Home Runs",
    "OPS":    "On-base + Slugging",
    "SO":     "Strikeouts (pitching)",
    "SB":     "Stolen Bases",
    "SV":     "Saves",
    "RA/G":   "Runs Allowed per Game",
    "BB":     "Walks Allowed",
    "HR Alw": "Home Runs Allowed",
    "SHO":    "Shutouts",
}


def _pt_px(pt: float, dpi: int) -> int:
    return max(1, round(pt * dpi / 72))


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class MatchupCardConfig(CardConfig):
    team_a_abbrev: str = "NYY"
    team_b_abbrev: str = "LAD"
    season: int = 2026
    stat_set: str = "Standard"
    win_highlight_color: str = _WIN_HIGHLIGHT_DEFAULT
    show_logos: bool = True
    show_timestamp: bool = False
    show_col_explainers: bool = False
    col_explainer_sep: str = "="

    # Colors
    title_bg: str    = "#1a3a5c"
    title_fg: str    = "#FFFFFF"
    header_bg: str   = "#1a3a5c"
    header_fg: str   = "#FFFFFF"
    label_bg: str    = "#F0F4F8"   # center column background
    label_fg: str    = "#333333"
    row_alt_color: str = "#F7F9FB"
    row_color: str   = "#FFFFFF"
    divider_color: str = "#CCCCCC"
    text_color: str  = "#111111"
    footer_color: str = "#888888"


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

class MatchupCardRenderer:

    def __init__(self, config: MatchupCardConfig, block: MatchupBlock,
                 working_dir: str = ""):
        self.config = config
        self.block  = block
        self.working_dir = working_dir

    def render(self) -> Image.Image:
        cfg   = self.config
        block = self.block
        img   = cfg.new_canvas()
        draw  = ImageDraw.Draw(img)

        W, H  = cfg.width_px, cfg.height_px
        PAD   = max(6, round(W * 0.010))

        rows  = get_stat_rows(cfg.stat_set)
        # header rows: title bar + team header row
        n_data_rows   = len(rows)
        n_total_rows  = n_data_rows + 1   # +1 team-name header row

        title_h      = max(20, round(H * 0.08))
        team_hdr_h   = max(28, round(H * 0.12))
        footer_h     = max(10, round(H * 0.04)) if cfg.show_timestamp else 0
        _expl_line_h = max(9, round(H * 0.028))
        explainer_h  = (_expl_line_h * 2 + 6) if cfg.show_col_explainers else 0
        available_h  = H - title_h - team_hdr_h - footer_h - explainer_h - PAD
        row_h        = max(12, available_h // max(n_data_rows, 1))

        title_font_size = min(max(9,  round(title_h    * 0.50)), _pt_px(16, cfg.dpi))
        hdr_font_size   = min(max(8,  round(team_hdr_h * 0.32)), _pt_px(14, cfg.dpi))
        label_font_size = min(max(7,  round(row_h      * 0.48)), _pt_px(10, cfg.dpi))
        val_font_size   = min(max(7,  round(row_h      * 0.52)), _pt_px(11, cfg.dpi))
        footer_font_size = (
            min(max(7, round(footer_h * 0.60)), _pt_px(8, cfg.dpi))
            if footer_h else 8
        )

        title_font  = get_font(title_font_size,  bold=True)
        hdr_font    = get_font(hdr_font_size,    bold=True)
        label_font  = get_font(label_font_size,  bold=True, condensed=True)
        val_font    = get_font(val_font_size,     bold=False, condensed=True)
        footer_font = get_font(footer_font_size)

        # Column x positions and widths
        usable_w = W - PAD * 2
        lw = round(usable_w * _LEFT_W   / _TOTAL_W)
        cw = round(usable_w * _CENTER_W / _TOTAL_W)
        rw = max(1, usable_w - lw - cw)

        lx = PAD           # left column start
        cx = PAD + lw      # center column start
        rx = PAD + lw + cw # right column start

        y = 0

        # ---- Title bar ----
        draw.rectangle([0, 0, W, title_h], fill=cfg.title_bg)
        title_text = (
            f"{block.team_a.team_abbrev} vs {block.team_b.team_abbrev}"
            f"  \u2014  {block.season}"
        )
        _tlogo_sz = title_h - 8
        if cfg.show_logos:
            logo_a = get_logo(block.team_a.team_abbrev, _tlogo_sz, self.working_dir)
            logo_b = get_logo(block.team_b.team_abbrev, _tlogo_sz, self.working_dir)
        else:
            logo_a = logo_b = None

        if logo_a and logo_b:
            gap = 6
            tbbox  = title_font.getbbox(title_text)
            text_w = tbbox[2] - tbbox[0]
            group_w = _tlogo_sz + gap + text_w + gap + _tlogo_sz
            group_x = max(PAD, (W - group_w) // 2)
            ly = (title_h - _tlogo_sz) // 2
            img.paste(logo_a, (group_x, ly), logo_a)
            tx = group_x + _tlogo_sz + gap
            th = tbbox[3] - tbbox[1]
            ty = (title_h - th) // 2 - tbbox[1]
            draw.text((tx, ty), title_text, font=title_font, fill=cfg.title_fg)
            img.paste(logo_b, (tx + text_w + gap, ly), logo_b)
        else:
            self._draw_center_text(draw, title_text, 0, title_h, W, title_font, cfg.title_fg)
        y += title_h

        # ---- Team header row ----
        draw.rectangle([0, y, W, y + team_hdr_h], fill=cfg.header_bg)
        hdr_logo_sz = team_hdr_h - 10

        for team, x_start, col_w, align in [
            (block.team_a, lx, lw, "left"),
            (block.team_b, rx, rw, "right"),
        ]:
            logo = get_logo(team.team_abbrev, hdr_logo_sz, self.working_dir) if cfg.show_logos else None
            name = team.team_name
            # Truncate if needed
            max_text_w = col_w - (hdr_logo_sz + 6 if logo else 0) - 6
            bbox = hdr_font.getbbox(name)
            if (bbox[2] - bbox[0]) > max_text_w:
                # Try abbreviation
                name = team.team_abbrev

            if align == "left":
                tx = x_start + 4
                if logo:
                    ly = y + (team_hdr_h - hdr_logo_sz) // 2
                    img.paste(logo, (tx, ly), logo)
                    tx += hdr_logo_sz + 6
                self._draw_vcenter_text(draw, name, tx, y, team_hdr_h, hdr_font, cfg.header_fg)
            else:
                # right-aligned: text then logo
                name_bbox = hdr_font.getbbox(name)
                name_w    = name_bbox[2] - name_bbox[0]
                logo_gap  = (hdr_logo_sz + 6) if logo else 0
                group_w   = name_w + logo_gap
                group_x   = x_start + col_w - group_w - 4
                group_x   = max(x_start, group_x)
                self._draw_vcenter_text(draw, name, group_x, y, team_hdr_h, hdr_font, cfg.header_fg)
                if logo:
                    lx2 = group_x + name_w + 6
                    ly  = y + (team_hdr_h - hdr_logo_sz) // 2
                    img.paste(logo, (lx2, ly), logo)

        # Center "vs" label
        self._draw_center_text(draw, "vs", cx, team_hdr_h, cw, label_font,
                               cfg.header_fg, y_offset=y)
        draw.line([0, y + team_hdr_h - 1, W, y + team_hdr_h - 1], fill=cfg.divider_color)
        y += team_hdr_h

        # ---- Stat rows ----
        for row_idx, (label, field, lower_is_better) in enumerate(rows):
            row_bg = cfg.row_alt_color if (row_idx % 2 == 0) else cfg.row_color
            draw.rectangle([0, y, W, y + row_h], fill=row_bg)

            # Center label column — always distinct bg
            draw.rectangle([cx, y, cx + cw, y + row_h], fill=cfg.label_bg)

            # Get values
            a_raw = getattr(block.team_a, field)
            b_raw = getattr(block.team_b, field)
            a_val = str(a_raw)
            b_val = str(b_raw)

            # Determine winner
            winner = compare(field, a_val, b_val, lower_is_better)
            hl = cfg.win_highlight_color

            if winner == -1:   # A wins
                draw.rectangle([lx, y, lx + lw, y + row_h], fill=hl)
            elif winner == 1:  # B wins
                draw.rectangle([rx, y, rx + rw, y + row_h], fill=hl)

            # Draw values
            self._draw_center_text(draw, a_val, lx, row_h, lw, val_font,
                                   cfg.text_color, y_offset=y)
            self._draw_center_text(draw, label, cx, row_h, cw, label_font,
                                   cfg.label_fg, y_offset=y)
            self._draw_center_text(draw, b_val, rx, row_h, rw, val_font,
                                   cfg.text_color, y_offset=y)

            draw.line([PAD, y + row_h - 1, W - PAD, y + row_h - 1],
                      fill=cfg.divider_color)
            y += row_h

        # ---- Footer ----
        if cfg.show_timestamp and footer_h:
            ts = block.as_of.strftime("Data as of %b %d, %Y  %I:%M %p")
            draw.rectangle([0, H - footer_h, W, H], fill=cfg.bg_color)
            self._draw_center_text(draw, ts, 0, footer_h, W, footer_font,
                                   cfg.footer_color, y_offset=H - footer_h)

        # ---- Column explainers ----
        if cfg.show_col_explainers and explainer_h > 0:
            sep   = cfg.col_explainer_sep
            rows_for_expl = get_stat_rows(cfg.stat_set)
            items = [
                f"{label} {sep} {_COL_EXPLAINERS.get(label, label)}"
                for label, _, _ in rows_for_expl
            ]
            zone_top = H - footer_h - explainer_h
            draw.rectangle([0, zone_top, W, zone_top + explainer_h], fill=cfg.bg_color)
            expl_font_size = max(6, round(_expl_line_h * 0.62))
            expl_font = get_font(expl_font_size, condensed=True)
            inner_h   = explainer_h - 4
            # Two-column layout: split items into two roughly equal rows
            half = (len(items) + 1) // 2
            line1 = "  \u00b7  ".join(items[:half])
            line2 = "  \u00b7  ".join(items[half:])
            avail_w = W - PAD * 2
            for line in (line1, line2):
                while line and expl_font.getbbox(line)[2] > avail_w:
                    line = line.rsplit("  \u00b7  ", 1)[0]
            line_h = _expl_line_h
            y1 = zone_top + 3
            y2 = y1 + line_h
            self._draw_center_text(draw, line1, PAD, line_h, W - PAD * 2,
                                   expl_font, "#666666", y_offset=y1)
            self._draw_center_text(draw, line2, PAD, line_h, W - PAD * 2,
                                   expl_font, "#666666", y_offset=y2)

        return img

    # ------------------------------------------------------------------
    # Text helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _draw_center_text(draw, text, x, h, w, font, color, y_offset: int = 0):
        bbox = font.getbbox(text)
        tw   = bbox[2] - bbox[0]
        th   = bbox[3] - bbox[1]
        tx   = x + (w - tw) // 2 - bbox[0]
        ty   = y_offset + (h - th) // 2 - bbox[1]
        draw.text((tx, ty), text, font=font, fill=color)

    @staticmethod
    def _draw_vcenter_text(draw, text, x, row_y, row_h, font, color):
        bbox = font.getbbox(text)
        th   = bbox[3] - bbox[1]
        ty   = row_y + (row_h - th) // 2 - bbox[1]
        draw.text((x, ty), text, font=font, fill=color)
