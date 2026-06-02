from __future__ import annotations

import datetime
from dataclasses import dataclass

from PIL import Image, ImageDraw

from app.cards.base_card import CardConfig
from app.data.game_record_api import GameRecordBlock, GameEntry, SeriesEntry
from app.data.logo_cache import get_logo
from app.utils.font_manager import get_font

# ---------------------------------------------------------------------------
# Column definitions
# ---------------------------------------------------------------------------

# Games-mode columns and weights
_GAMES_COLS: list[str] = ["DATE", "H/A", "OPP", "SCORE", "W/L", "PITCHER", "REC"]
_GAMES_WEIGHTS: dict[str, float] = {
    "DATE":    1.1,
    "H/A":     0.55,
    "OPP":     1.8,
    "SCORE":   0.9,
    "W/L":     0.5,
    "PITCHER": 2.2,
    "REC":     0.85,
}

# Series result-only columns and weights
_SERIES_COLS: list[str] = ["OPP", "H/A", "DATES", "RESULT"]
_SERIES_WEIGHTS: dict[str, float] = {
    "OPP":    2.5,
    "H/A":    0.7,
    "DATES":  1.8,
    "RESULT": 1.0,
}

# Series+scores sub-row columns and weights (used as the card header in that mode)
_SERIES_SCORES_COLS: list[str] = ["DATE", "SCORE", "W/L", "PITCHER"]
_SERIES_SCORES_WEIGHTS: dict[str, float] = {
    "DATE":    1.1,
    "SCORE":   0.9,
    "W/L":     0.5,
    "PITCHER": 2.8,
}

_RIGHT_ALIGN: set[str] = {"SCORE", "REC", "RESULT"}
_CENTER_COLS: set[str] = {"H/A", "W/L"}

# Row tinting
_WIN_COLOR  = "#D4EDDA"
_LOSS_COLOR = "#FADADD"
_ALT_COLOR  = "#F4F7FA"  # light stripe for alternating same-result runs


def _pt_px(pt: float, dpi: int) -> int:
    return max(1, round(pt * dpi / 72))


def _record_pct(record: str) -> str:
    """Return '.xxx' win-pct string for a 'W-L' record, or '' on failure."""
    try:
        w, l = record.split("-")
        total = int(w) + int(l)
        if total == 0:
            return ""
        return f"{int(w) / total:.3f}".lstrip("0") or ".000"
    except Exception:
        return ""


def _col_widths_px(
    cols: list[str], weights: dict[str, float], total_px: int, padding_px: int
) -> list[int]:
    total_weight = sum(weights.get(c, 1.0) for c in cols)
    usable = max(1, total_px - padding_px * 2)
    widths: list[int] = []
    allocated = 0
    for i, col in enumerate(cols):
        if i == len(cols) - 1:
            widths.append(max(1, usable - allocated))
        else:
            w = max(1, round(usable * (weights.get(col, 1.0) / total_weight)))
            widths.append(w)
            allocated += w
    return widths


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class GameRecordCardConfig(CardConfig):
    team_abbrev: str = "NYY"
    team_name: str = "New York Yankees"
    mode: str = "games"            # "games" | "series"
    series_detail: str = "result_only"  # "result_only" | "scores"
    show_logos: bool = True
    show_summary: bool = True
    show_timestamp: bool = False

    # Colors
    title_bg: str = "#1a3a5c"
    title_fg: str = "#FFFFFF"
    header_bg: str = "#2c5f8a"
    header_fg: str = "#FFFFFF"
    summary_bg: str = "#1d4e78"
    summary_fg: str = "#FFFFFF"
    series_band_bg: str = "#2c5f8a"
    series_band_fg: str = "#FFFFFF"
    win_row_color: str = _WIN_COLOR
    loss_row_color: str = _LOSS_COLOR
    alt_row_color: str = _ALT_COLOR
    divider_color: str = "#CCCCCC"
    footer_color: str = "#666666"


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

class GameRecordCardRenderer:

    def __init__(self, config: GameRecordCardConfig, block: GameRecordBlock,
                 working_dir: str = ""):
        self.config = config
        self.block  = block
        self.working_dir = working_dir
        self.last_warning: str = ""
        self.rendered_count: int = 0

    def render(self) -> Image.Image:
        cfg   = self.config
        block = self.block
        self.last_warning = ""

        img  = cfg.new_canvas()
        draw = ImageDraw.Draw(img)
        W, H = cfg.width_px, cfg.height_px
        PAD  = max(8, round(W * 0.018))

        # Warn if card is very narrow
        if cfg.width_in < 4.5:
            self.last_warning = "Card width < 4.5\" — columns may be cramped"

        # ---- Height zones ----
        title_h   = max(36, round(H * 0.10))
        summary_h = max(20, round(H * 0.055)) if cfg.show_summary else 0
        hdr_h     = max(16, round(H * 0.055))
        footer_h  = max(12, round(H * 0.04)) if cfg.show_timestamp else 0
        body_h    = H - title_h - summary_h - hdr_h - footer_h - PAD

        # Estimate rows that fit
        if block.mode == "games" or (block.mode == "series"
                                     and cfg.series_detail == "result_only"):
            n_entries = len(block.entries)
        else:
            # series + scores: count bands + game sub-rows
            n_entries = sum(1 + len(s.games) for s in block.entries)  # type: ignore[attr-defined]

        min_row_h = max(12, _pt_px(8, cfg.dpi))
        rows_fit  = max(1, body_h // min_row_h)
        if n_entries > rows_fit:
            self.last_warning = (
                f"Only {rows_fit} row{'s' if rows_fit != 1 else ''} fit at this card size"
                f" — increase height or reduce N"
            )

        row_h = max(min_row_h, body_h // max(n_entries, 1))

        # ---- Font sizes ----
        title_font_sz  = min(max(10, round(title_h * 0.48)), _pt_px(18, cfg.dpi))
        hdr_font_sz    = min(max(8,  round(hdr_h   * 0.50)), _pt_px(10, cfg.dpi))
        row_font_sz    = min(max(7,  round(row_h   * 0.48)), _pt_px(10, cfg.dpi))
        sum_font_sz    = min(max(7,  round(summary_h * 0.52)), _pt_px(9, cfg.dpi))
        band_font_sz   = min(max(7,  round(hdr_h   * 0.50)), _pt_px(10, cfg.dpi))
        footer_font_sz = min(max(7,  round(footer_h * 0.60)), _pt_px(8, cfg.dpi)) if footer_h else 8

        title_font  = get_font(title_font_sz,  bold=True)
        hdr_font    = get_font(hdr_font_sz,    bold=True, condensed=True)
        row_font    = get_font(row_font_sz,     condensed=True)
        sum_font    = get_font(sum_font_sz,     bold=True)
        band_font   = get_font(band_font_sz,    bold=True, condensed=True)
        footer_font = get_font(footer_font_sz)

        # Column widths
        if block.mode == "games":
            cols    = _GAMES_COLS
            weights = _GAMES_WEIGHTS
        elif cfg.series_detail == "scores":
            cols    = _SERIES_SCORES_COLS
            weights = _SERIES_SCORES_WEIGHTS
        else:
            cols    = _SERIES_COLS
            weights = _SERIES_WEIGHTS
        col_widths = _col_widths_px(cols, weights, W, PAD)

        logo_sz = max(8, round(row_h * 0.65)) if cfg.show_logos else 0

        y = 0

        # ============================
        # Title bar
        # ============================
        draw.rectangle([0, 0, W, title_h], fill=cfg.title_bg)
        title_text = f"{block.team_name}"
        sub_text   = "Season Game Record"
        _tlogo_sz  = title_h - 8

        tlogo = None
        if cfg.show_logos:
            tlogo = get_logo(cfg.team_abbrev, _tlogo_sz, self.working_dir)

        if tlogo:
            gap    = 8
            tbbox  = title_font.getbbox(title_text)
            text_w = tbbox[2] - tbbox[0]
            group_w = _tlogo_sz + gap + text_w
            group_x = max(PAD, (W - group_w) // 2)
            ly = (title_h - _tlogo_sz) // 2
            img.paste(tlogo, (group_x, ly), tlogo)
            th = tbbox[3] - tbbox[1]
            tx = group_x + _tlogo_sz + gap
            ty = (title_h - th) // 2 - tbbox[1]
            draw.text((tx, ty), title_text, font=title_font, fill=cfg.title_fg)
        else:
            self._centered_text(draw, title_text, 0, title_h, W, title_font, cfg.title_fg)

        y += title_h

        # ============================
        # Summary band
        # ============================
        if cfg.show_summary and summary_h:
            draw.rectangle([0, y, W, y + summary_h], fill=cfg.summary_bg)
            overall_pct = _record_pct(block.overall_record)
            pct_str = f" ({overall_pct})" if overall_pct else ""
            if block.mode == "games":
                n = len(block.entries)
                summary_text = f"Last {n} game{'s' if n != 1 else ''}: {block.span_record} · Season: {block.overall_record}{pct_str}"
            else:
                n = len(block.entries)
                summary_text = f"Last {n} series: {block.span_record} · Season: {block.overall_record}{pct_str}"
            self._centered_text(draw, summary_text, y, summary_h, W, sum_font, cfg.summary_fg)
            y += summary_h

        # ============================
        # Column header row
        # ============================
        draw.rectangle([0, y, W, y + hdr_h], fill=cfg.header_bg)
        x = PAD
        for col, cw in zip(cols, col_widths):
            if col in _CENTER_COLS:
                self._centered_col(draw, col, x, cw, y, hdr_h, hdr_font, cfg.header_fg)
            elif col in _RIGHT_ALIGN:
                self._right_col(draw, col, x, cw, y, hdr_h, hdr_font, cfg.header_fg)
            else:
                self._left_text(draw, col, x + 3, y, hdr_h, hdr_font, cfg.header_fg)
            x += cw
        draw.line([0, y + hdr_h - 1, W, y + hdr_h - 1], fill=cfg.divider_color)
        y += hdr_h

        # ============================
        # Data rows
        # ============================
        if block.mode == "games":
            self._render_games(
                draw, img, block.entries, cols, col_widths,
                y, row_h, logo_sz, row_font, W, PAD, cfg
            )
        else:
            self._render_series(
                draw, img, block.entries, cols, col_widths,
                y, row_h, logo_sz, row_font, band_font, W, PAD, cfg
            )

        # ============================
        # Footer / timestamp
        # ============================
        if cfg.show_timestamp and footer_h:
            ts = block.as_of.strftime("Data as of %b %d, %Y  %I:%M %p")
            draw.rectangle([0, H - footer_h, W, H], fill=cfg.bg_color)
            self._centered_text(draw, ts, H - footer_h, footer_h, W, footer_font, cfg.footer_color)

        self.rendered_count = len(block.entries)
        return img

    # ------------------------------------------------------------------
    # Games mode renderer
    # ------------------------------------------------------------------

    def _render_games(self, draw, img, entries: list[GameEntry], cols, col_widths,
                      y_start, row_h, logo_sz, row_font, W, PAD, cfg):
        # Alternating color: within same consecutive W/W or L/L runs, use alt
        for i, entry in enumerate(entries):
            base_color = cfg.win_row_color if entry.win else cfg.loss_row_color
            # Use subtle alt stripe for same-result consecutive pairs
            if i > 0 and entries[i - 1].win == entry.win:
                row_color = self._blend(base_color, cfg.alt_row_color, 0.35)
            else:
                row_color = base_color

            y = y_start + i * row_h
            draw.rectangle([0, y, W, y + row_h], fill=row_color)
            draw.line([0, y + row_h - 1, W, y + row_h - 1], fill=cfg.divider_color)

            ha_text = "vs" if entry.is_home else "@"
            wl_text = "W" if entry.win else "L"
            score_text = f"{entry.team_score}-{entry.opp_score}"

            values = {
                "DATE":    entry.date,
                "H/A":     ha_text,
                "OPP":     entry.opponent_abbrev,
                "SCORE":   score_text,
                "W/L":     wl_text,
                "PITCHER": entry.pitcher,
                "REC":     entry.record,
            }

            x = PAD
            for col, cw in zip(cols, col_widths):
                val = values.get(col, "")
                if col == "OPP" and logo_sz and entry.opponent_abbrev:
                    self._draw_logo_text(
                        img, draw, entry.opponent_abbrev, val,
                        x, y, cw, row_h, logo_sz, row_font, "#222222"
                    )
                elif col in _CENTER_COLS:
                    color = "#226622" if (col == "W/L" and entry.win) else \
                            "#aa2200" if (col == "W/L") else "#222222"
                    self._centered_col(draw, val, x, cw, y, row_h, row_font, color)
                elif col in _RIGHT_ALIGN:
                    self._right_col(draw, val, x, cw, y, row_h, row_font, "#222222")
                else:
                    self._left_text(draw, val, x + 3, y, row_h, row_font, "#222222")
                x += cw

    # ------------------------------------------------------------------
    # Series mode renderer
    # ------------------------------------------------------------------

    def _render_series(self, draw, img, entries: list[SeriesEntry], cols, col_widths,
                       y_start, row_h, logo_sz, row_font, band_font, W, PAD, cfg):
        y = y_start
        for i, series in enumerate(entries):
            if cfg.series_detail == "result_only":
                base = cfg.win_row_color if series.series_result.startswith("W") else \
                       cfg.loss_row_color if series.series_result.startswith("L") else \
                       cfg.alt_row_color
                if i > 0 and (entries[i - 1].series_result[0] == series.series_result[0]):
                    row_color = self._blend(base, cfg.alt_row_color, 0.35)
                else:
                    row_color = base

                draw.rectangle([0, y, W, y + row_h], fill=row_color)
                draw.line([0, y + row_h - 1, W, y + row_h - 1], fill=cfg.divider_color)

                ha_text = "vs" if series.is_home else "@"
                values = {
                    "OPP":    series.opponent_abbrev,
                    "H/A":    ha_text,
                    "DATES":  series.date_range,
                    "RESULT": series.series_result,
                }

                x = PAD
                for col, cw in zip(cols, col_widths):
                    val = values.get(col, "")
                    if col == "OPP" and logo_sz and series.opponent_abbrev:
                        self._draw_logo_text(
                            img, draw, series.opponent_abbrev, val,
                            x, y, cw, row_h, logo_sz, row_font, "#222222"
                        )
                    elif col in _CENTER_COLS:
                        self._centered_col(draw, val, x, cw, y, row_h, row_font, "#222222")
                    elif col in _RIGHT_ALIGN:
                        res_color = "#226622" if val.startswith("W") else \
                                    "#aa2200" if val.startswith("L") else "#555555"
                        self._right_col(draw, val, x, cw, y, row_h, row_font, res_color)
                    else:
                        self._left_text(draw, val, x + 3, y, row_h, row_font, "#222222")
                    x += cw
                y += row_h

            else:
                # Series band header
                ha_text = "vs" if series.is_home else "@"
                wins  = sum(1 for g in series.games if g.win)
                losses = len(series.games) - wins
                band_text = (
                    f"{ha_text} {series.opponent_abbrev}  ·  "
                    f"{series.date_range}  ·  {series.series_result}"
                )
                draw.rectangle([0, y, W, y + row_h], fill=cfg.series_band_bg)
                draw.line([0, y + row_h - 1, W, y + row_h - 1], fill=cfg.divider_color)

                if logo_sz and series.opponent_abbrev:
                    self._draw_logo_text(
                        img, draw, series.opponent_abbrev, band_text,
                        PAD, y, W - PAD * 2, row_h, logo_sz, band_font, cfg.series_band_fg
                    )
                else:
                    self._left_text(draw, band_text, PAD + 4, y, row_h, band_font, cfg.series_band_fg)
                y += row_h

                # Individual game sub-rows
                for j, game in enumerate(series.games):
                    g_base = cfg.win_row_color if game.win else cfg.loss_row_color
                    g_color = self._blend(g_base, cfg.alt_row_color, 0.2) if j % 2 else g_base
                    draw.rectangle([0, y, W, y + row_h], fill=g_color)
                    draw.line([0, y + row_h - 1, W, y + row_h - 1], fill=cfg.divider_color)

                    score_text = f"{game.team_score}-{game.opp_score}"
                    wl_text    = "W" if game.win else "L"
                    wl_color   = "#226622" if game.win else "#aa2200"

                    values = {
                        "DATE":    game.date,
                        "SCORE":   score_text,
                        "W/L":     wl_text,
                        "PITCHER": game.pitcher,
                    }

                    x = PAD
                    for col, cw in zip(cols, col_widths):
                        val = values.get(col, "")
                        if col in _CENTER_COLS:
                            color = wl_color if col == "W/L" else "#222222"
                            self._centered_col(draw, val, x, cw, y, row_h, row_font, color)
                        elif col in _RIGHT_ALIGN:
                            self._right_col(draw, val, x, cw, y, row_h, row_font, "#222222")
                        else:
                            self._left_text(draw, val, x + 3, y, row_h, row_font, "#222222")
                        x += cw
                    y += row_h

    # ------------------------------------------------------------------
    # Drawing helpers
    # ------------------------------------------------------------------

    def _centered_text(self, draw, text: str, y: int, zone_h: int,
                       W: int, font, color: str) -> None:
        bbox = font.getbbox(text)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text(
            ((W - tw) // 2, y + (zone_h - th) // 2 - bbox[1]),
            text, font=font, fill=color
        )

    def _centered_col(self, draw, text: str, x: int, cw: int,
                      y: int, row_h: int, font, color: str) -> None:
        bbox = font.getbbox(text)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text(
            (x + (cw - tw) // 2, y + (row_h - th) // 2 - bbox[1]),
            text, font=font, fill=color
        )

    def _right_col(self, draw, text: str, x: int, cw: int,
                   y: int, row_h: int, font, color: str) -> None:
        bbox = font.getbbox(text)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text(
            (x + cw - tw - 4, y + (row_h - th) // 2 - bbox[1]),
            text, font=font, fill=color
        )

    def _left_text(self, draw, text: str, x: int, y: int,
                   row_h: int, font, color: str) -> None:
        bbox = font.getbbox(text)
        th = bbox[3] - bbox[1]
        draw.text(
            (x, y + (row_h - th) // 2 - bbox[1]),
            text, font=font, fill=color
        )

    def _draw_logo_text(self, img, draw, abbrev: str, text: str,
                        x: int, y: int, cw: int, row_h: int,
                        logo_sz: int, font, color: str) -> None:
        logo = get_logo(abbrev, logo_sz, self.working_dir)
        lx = x + 2
        if logo:
            ly = y + (row_h - logo_sz) // 2
            img.paste(logo, (lx, max(y, ly)), logo)
            text_x = lx + logo_sz + 3
        else:
            text_x = lx
        bbox = font.getbbox(text)
        th = bbox[3] - bbox[1]
        draw.text(
            (text_x, y + (row_h - th) // 2 - bbox[1]),
            text, font=font, fill=color
        )

    @staticmethod
    def _blend(hex1: str, hex2: str, t: float) -> str:
        """Linear interpolation between two hex colors at factor t (0=hex1, 1=hex2)."""
        try:
            r1, g1, b1 = int(hex1[1:3], 16), int(hex1[3:5], 16), int(hex1[5:7], 16)
            r2, g2, b2 = int(hex2[1:3], 16), int(hex2[3:5], 16), int(hex2[5:7], 16)
            r = round(r1 + (r2 - r1) * t)
            g = round(g1 + (g2 - g1) * t)
            b = round(b1 + (b2 - b1) * t)
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return hex1
