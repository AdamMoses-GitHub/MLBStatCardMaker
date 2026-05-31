from __future__ import annotations

import datetime
from dataclasses import dataclass

from PIL import Image, ImageDraw

from app.cards.base_card import CardConfig
from app.data.triple_crown_api import TripleCrownBlock
from app.data.batters_api import is_team_scope
from app.data.logo_cache import get_logo
from app.utils.font_manager import get_font

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_STAT_EXPAND: dict[str, str] = {
    "AVG": "Batting Average",
    "HR":  "Home Runs",
    "RBI": "Runs Batted In",
    "W":   "Wins",
    "SO":  "Strikeouts",
    "ERA": "Earned Run Avg",
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

# Distinct dark colors for the three panel sub-headers
_PANEL_HEADER_COLORS: list[str] = [
    "#1a3a5c",  # deep blue
    "#5c1a2a",  # deep crimson
    "#1a5c2a",  # deep green
]

_BADGE_COLORS = {
    1: "#D4AF37",
    2: "#C0C0C0",
    3: "#B87333",
}
_BADGE_OUTLINE_COLORS = {
    1: "#9A7B1A",
    2: "#808080",
    3: "#7A4A20",
}

# Proportional weight for sub-columns within each panel
_BADGE_W  = 0.50
_PLAYER_W = 3.00
_TEAM_W   = 1.60
_STAT_W   = 1.20
_TOTAL_W  = _BADGE_W + _PLAYER_W + _TEAM_W + _STAT_W


def _pt_px(pt: float, dpi: int) -> int:
    return max(1, round(pt * dpi / 72))


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class TripleCrownCardConfig(CardConfig):
    scope: str = "All MLB"
    stat_type: str = "Batting"
    top_n: int = 10
    show_logos: bool = True
    show_rank_badges: bool = True
    show_timestamp: bool = False
    title_override: str = ""

    # Colors
    title_bg: str = "#1a3a5c"
    title_fg: str = "#FFFFFF"
    panel_header_fg: str = "#FFFFFF"
    row_alt_color: str = "#EEF2F7"
    row_color: str = "#FFFFFF"
    divider_color: str = "#CCCCCC"
    text_color: str = "#111111"
    footer_color: str = "#888888"


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

class TripleCrownCardRenderer:

    def __init__(self, config: TripleCrownCardConfig, block: TripleCrownBlock,
                 working_dir: str = ""):
        self.config      = config
        self.block       = block
        self.working_dir = working_dir

    def render(self) -> Image.Image:
        cfg   = self.config
        block = self.block
        img   = cfg.new_canvas()
        draw  = ImageDraw.Draw(img)

        W, H  = cfg.width_px, cfg.height_px
        PAD   = max(8, round(W * 0.012))
        GUTTER = max(4, round(W * 0.008))

        num_rows = max((len(c.entries) for c in block.columns), default=1)

        title_h      = max(24, round(H * 0.07))
        sub_h        = max(18, round(H * 0.055))
        footer_h     = max(12, round(H * 0.04)) if cfg.show_timestamp else 0
        available_h  = H - title_h - sub_h - footer_h - PAD
        row_h        = max(14, available_h // max(num_rows, 1))

        title_font_size  = min(max(10, round(title_h * 0.52)),  _pt_px(18, cfg.dpi))
        sub_font_size    = min(max(8,  round(sub_h   * 0.52)),  _pt_px(11, cfg.dpi))
        row_font_size    = min(max(7,  round(row_h   * 0.52)),  _pt_px(11, cfg.dpi))
        footer_font_size = (min(max(7, round(footer_h * 0.60)), _pt_px(8,  cfg.dpi))
                            if footer_h else 8)

        title_font  = get_font(title_font_size,  bold=True)
        sub_font    = get_font(sub_font_size,     bold=True, condensed=True)
        row_font    = get_font(row_font_size,     condensed=True)
        footer_font = get_font(footer_font_size)

        logo_sz = max(8, round(row_h * 0.65)) if cfg.show_logos else 0
        no_team = is_team_scope(cfg.scope)

        # Panel geometry
        usable_w = W - PAD * 2 - GUTTER * 2
        panel_w  = max(10, usable_w // 3)
        panel_xs = [
            PAD,
            PAD + panel_w + GUTTER,
            PAD + 2 * (panel_w + GUTTER),
        ]

        # Sub-column widths inside each panel — drop team column for single-team scope
        badge_w  = max(1, round(panel_w * _BADGE_W  / _TOTAL_W))
        stat_w   = max(1, round(panel_w * _STAT_W   / _TOTAL_W))
        team_w   = max(1, round(panel_w * _TEAM_W   / _TOTAL_W)) if not no_team else 0
        player_w = max(1, panel_w - badge_w - stat_w - team_w)

        y = 0

        # --- Title bar ---
        draw.rectangle([0, y, W, y + title_h], fill=cfg.title_bg)
        scope = cfg.scope
        _scope_logo_abbrev = (
            block.columns[0].entries[0].team_abbrev
            if is_team_scope(scope) and block.columns and block.columns[0].entries
            else _SCOPE_LOGO.get(scope)
        )
        title_text = cfg.title_override or self._title_text(title_font, W - PAD * 2)
        if cfg.show_logos and self.working_dir and _scope_logo_abbrev:
            tlogo = get_logo(_scope_logo_abbrev, title_h - 8, self.working_dir)
            if tlogo:
                gap     = 8
                tl_sz   = title_h - 8
                tbbox   = title_font.getbbox(title_text)
                text_w  = tbbox[2] - tbbox[0]
                group_w = tl_sz + gap + text_w
                gx      = max(PAD, (W - group_w) // 2)
                ly      = y + (title_h - tl_sz) // 2
                img.paste(tlogo, (gx, ly), tlogo)
                th = tbbox[3] - tbbox[1]
                tx = gx + tl_sz + gap
                ty = y + (title_h - th) // 2 - tbbox[1]
                draw.text((tx, ty), title_text, font=title_font, fill=cfg.title_fg)
            else:
                self._draw_centered(draw, title_text, y, title_h, title_font,
                                    cfg.title_fg, W)
        else:
            self._draw_centered(draw, title_text, y, title_h, title_font,
                                cfg.title_fg, W)
        y += title_h

        # --- Panel sub-headers ---
        for col_idx, (tc_col, px) in enumerate(zip(block.columns, panel_xs)):
            hdr_color = _PANEL_HEADER_COLORS[col_idx % len(_PANEL_HEADER_COLORS)]
            draw.rectangle([px, y, px + panel_w, y + sub_h], fill=hdr_color)
            long_stat = _STAT_EXPAND.get(tc_col.stat_label, tc_col.stat_label)
            hdr_text  = f"{tc_col.stat_label}  \u2014  {long_stat}"
            # Truncate if needed
            avail = panel_w - 8
            while hdr_text and sub_font.getbbox(hdr_text)[2] > avail:
                hdr_text = hdr_text[:-1]
            self._draw_centered_range(draw, hdr_text, px, px + panel_w,
                                      y, sub_h, sub_font, cfg.panel_header_fg)
        y += sub_h

        # --- Data rows ---
        for row_idx in range(num_rows):
            row_bg = cfg.row_alt_color if (row_idx % 2 == 0) else cfg.row_color
            draw.rectangle([0, y, W, y + row_h], fill=row_bg)

            for tc_col, px in zip(block.columns, panel_xs):
                if row_idx >= len(tc_col.entries):
                    continue
                entry = tc_col.entries[row_idx]
                rank  = entry.rank

                # Rank badge
                if cfg.show_rank_badges and rank in _BADGE_COLORS:
                    bsz = max(8, min(badge_w - 6, round(row_h * 0.60)))
                    bx  = px + (badge_w - bsz) // 2
                    by  = y  + (row_h   - bsz) // 2
                    ow  = max(1, round(bsz * 0.12))
                    draw.ellipse([bx, by, bx + bsz, by + bsz],
                                 fill=_BADGE_COLORS[rank],
                                 outline=_BADGE_OUTLINE_COLORS[rank], width=ow)
                self._draw_centered_box(draw, str(rank), px, badge_w,
                                        y, row_h, row_font, "#1a1a1a")

                # Player name (last-name fallback)
                name = entry.player_name
                px_name = px + badge_w
                avail_name = player_w - 4
                if row_font.getbbox(name)[2] > avail_name:
                    parts = name.split()
                    name  = parts[-1] if parts else name
                self._draw_left(draw, name, px_name + 2, y, row_h,
                                row_font, cfg.text_color)

                # Team (logo + abbrev)
                if not no_team:
                    tx = px + badge_w + player_w
                    if cfg.show_logos and self.working_dir and logo_sz > 0:
                        logo = get_logo(entry.team_abbrev, logo_sz, self.working_dir)
                        if logo:
                            ly = y + (row_h - logo_sz) // 2
                            img.paste(logo, (tx, ly), logo)
                            tx += logo_sz + 2
                    self._draw_left(draw, entry.team_abbrev, tx, y, row_h,
                                    row_font, cfg.text_color)

                # Stat value (right-aligned)
                sx = px + badge_w + player_w + team_w
                self._draw_right_box(draw, entry.stat_value, sx, stat_w,
                                     y, row_h, row_font, cfg.text_color)

            draw.line([PAD, y + row_h - 1, W - PAD, y + row_h - 1],
                      fill=cfg.divider_color)
            y += row_h

        # Vertical gutter lines between panels
        gutter_top = title_h
        gutter_bot = y
        for i in (1, 2):
            gx = PAD + i * panel_w + (i - 1) * GUTTER + GUTTER // 2
            draw.line([gx, gutter_top, gx, gutter_bot],
                      fill=cfg.divider_color, width=1)

        # --- Footer ---
        if cfg.show_timestamp and footer_h:
            ts = block.as_of.strftime("Data as of %b %d, %Y  %I:%M %p")
            draw.rectangle([0, H - footer_h, W, H], fill=cfg.bg_color)
            self._draw_centered(draw, ts, H - footer_h, footer_h,
                                footer_font, cfg.footer_color, W)

        return img

    # ------------------------------------------------------------------
    # Title text
    # ------------------------------------------------------------------

    def _title_text(self, font, avail_w: int) -> str:
        cfg        = self.config
        block      = self.block
        scope      = cfg.scope
        year       = block.season
        long_scope = _SCOPE_EXPAND.get(scope, scope)
        label_s    = scope if scope != "All MLB" else "MLB"
        label_l    = long_scope if scope != "All MLB" else "MLB"

        if cfg.stat_type == "Batting":
            long   = f"{label_l} Batting Race Leaders {year}"
            medium = f"{label_l} Triple Crown Race {year}"
            short  = f"{label_s} Triple Crown {year}"
        else:
            long   = f"{label_l} Pitching Race Leaders {year}"
            medium = f"{label_l} Pitching Crown Race {year}"
            short  = f"{label_s} Pitching Crown {year}"

        for candidate in (long, medium, short):
            if font.getbbox(candidate)[2] <= avail_w:
                return candidate
        return short

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
    def _draw_centered_range(draw, text, x0, x1, y, h, font, color):
        bbox = font.getbbox(text)
        tw   = bbox[2] - bbox[0]
        th   = bbox[3] - bbox[1]
        x    = x0 + ((x1 - x0) - tw) // 2 - bbox[0]
        ty   = y + (h - th) // 2 - bbox[1]
        draw.text((x, ty), text, font=font, fill=color)

    @staticmethod
    def _draw_centered_box(draw, text, box_x, box_w, row_y, row_h, font, color):
        bbox = font.getbbox(text)
        tw   = bbox[2] - bbox[0]
        th   = bbox[3] - bbox[1]
        x    = box_x + (box_w - tw) // 2 - bbox[0]
        ty   = row_y + (row_h - th) // 2 - bbox[1]
        draw.text((x, ty), text, font=font, fill=color)

    @staticmethod
    def _draw_left(draw, text, x, row_y, row_h, font, color):
        bbox = font.getbbox(text)
        th   = bbox[3] - bbox[1]
        ty   = row_y + (row_h - th) // 2 - bbox[1]
        draw.text((x, ty), text, font=font, fill=color)

    @staticmethod
    def _draw_right_box(draw, text, box_x, box_w, row_y, row_h, font, color):
        bbox = font.getbbox(text)
        tw   = bbox[2] - bbox[0]
        th   = bbox[3] - bbox[1]
        x    = box_x + box_w - tw - 5 - bbox[0]
        ty   = row_y + (row_h - th) // 2 - bbox[1]
        draw.text((x, ty), text, font=font, fill=color)
