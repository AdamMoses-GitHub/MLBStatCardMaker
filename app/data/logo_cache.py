from __future__ import annotations

import os
import io
import logging
from typing import Optional

import requests
from PIL import Image, UnidentifiedImageError

logger = logging.getLogger(__name__)

_HTTP = requests.Session()
_HTTP.headers.update({"User-Agent": "MLBStatCardMaker/1.0"})

# MLB static CDN team logo URL (PNG, fallback only)
_LOGO_PNG_TEMPLATE = "https://content.mlb.com/images/teams/logos/small/{team_id}.png"

# Fallback: ESPN CDN (uses team abbrev)
_ESPN_LOGO_TEMPLATE = "https://a.espncdn.com/i/teamlogos/mlb/500/{abbrev}.png"

# Map team abbreviation → MLB team ID
# Uses abbreviations as returned by the MLB Stats API (e.g. "AZ" not "ARI")
TEAM_ID_MAP: dict[str, int] = {
    "AZ":  109, "ATL": 144, "BAL": 110, "BOS": 111, "CHC": 112,
    "CWS": 145, "CIN": 113, "CLE": 114, "COL": 115, "DET": 116,
    "HOU": 117, "KC":  118, "LAA": 108, "LAD": 119, "MIA": 146,
    "MIL": 158, "MIN": 142, "NYM": 121, "NYY": 147, "ATH": 133,
    "PHI": 143, "PIT": 134, "SD":  135, "SEA": 136, "SF":  137,
    "STL": 138, "TB":  139, "TEX": 140, "TOR": 141, "WSH": 120,
}

# ESPN CDN uses different abbreviations for some teams.
# Map MLB API abbrev → ESPN abbrev when they differ.
_ESPN_ABBREV_OVERRIDE: dict[str, str] = {
    "AZ":  "ari",   # Diamondbacks: API says AZ, ESPN says ari
    "ATH": "oak",   # Athletics: API says ATH, ESPN still uses oak
}

# Pseudo-abbrevs for league/MLB scope logos (not real team codes).
# ESPN serves AL and NL at the normal teamlogos path; MLB uses the leagues path.
_LEAGUE_LOGO_URL: dict[str, str] = {
    "MLB":        "https://a.espncdn.com/i/teamlogos/leagues/500/mlb.png",
    "AL":         "https://a.espncdn.com/i/teamlogos/mlb/500/al.png",
    "NL":         "https://a.espncdn.com/i/teamlogos/mlb/500/nl.png",
    # Divisions fall back to their parent league logo
    "AL EAST":    "https://a.espncdn.com/i/teamlogos/mlb/500/al.png",
    "AL CENTRAL": "https://a.espncdn.com/i/teamlogos/mlb/500/al.png",
    "AL WEST":    "https://a.espncdn.com/i/teamlogos/mlb/500/al.png",
    "NL EAST":    "https://a.espncdn.com/i/teamlogos/mlb/500/nl.png",
    "NL CENTRAL": "https://a.espncdn.com/i/teamlogos/mlb/500/nl.png",
    "NL WEST":    "https://a.espncdn.com/i/teamlogos/mlb/500/nl.png",
}


def _cache_path(working_dir: str, abbrev: str) -> str:
    logos_dir = os.path.join(working_dir, "logos")
    os.makedirs(logos_dir, exist_ok=True)
    return os.path.join(logos_dir, f"{abbrev}.png")


def _download_image(url: str, timeout: int = 8) -> Optional[Image.Image]:
    try:
        resp = _HTTP.get(url, timeout=timeout)
        resp.raise_for_status()
        return Image.open(io.BytesIO(resp.content)).convert("RGBA")
    except (requests.RequestException, UnidentifiedImageError, OSError) as exc:
        logger.warning("Logo download failed (%s): %s", url, exc)
        return None


def _save_cache_image(path: str, image: Image.Image) -> None:
    tmp_path = f"{path}.tmp"
    try:
        image.save(tmp_path, "PNG")
        os.replace(tmp_path, path)
    except OSError:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        raise


def get_logo(abbrev: str, size_px: int, working_dir: str) -> Optional[Image.Image]:
    """
    Return a PIL Image of the team logo at size_px × size_px.
    Downloads from ESPN CDN on first use and caches to working_dir/logos/.
    Returns None on any failure.
    """
    abbrev = abbrev.upper()

    # Reject sentinel / placeholder values that can never resolve to a real logo
    if not abbrev or abbrev in ("---", "UNK", "N/A") or not abbrev.replace(" ", "").isalnum():
        return None

    cache = _cache_path(working_dir, abbrev)

    # Return cached version if it exists
    if os.path.isfile(cache):
        try:
            with Image.open(cache) as cached:
                img = cached.convert("RGBA")
            img = img.resize((size_px, size_px), Image.LANCZOS)
            return img
        except (UnidentifiedImageError, OSError) as exc:
            logger.warning("Logo cache corrupt for %s — deleting and re-downloading: %s", abbrev, exc)
            try:
                os.remove(cache)
            except OSError:
                pass

    # League/scope logos (MLB, AL, NL, divisions) use a fixed URL
    league_url = _LEAGUE_LOGO_URL.get(abbrev)
    if league_url:
        img = _download_image(league_url)
        if img is not None:
            try:
                _save_cache_image(cache, img)
            except OSError as exc:
                logger.warning("Could not persist league logo cache for %s: %s", abbrev, exc)
            img = img.resize((size_px, size_px), Image.LANCZOS)
            return img
        return None

    # Download from ESPN CDN
    espn_abbrev = _ESPN_ABBREV_OVERRIDE.get(abbrev, abbrev.lower())
    url = _ESPN_LOGO_TEMPLATE.format(abbrev=espn_abbrev)
    img = _download_image(url)
    if img is not None:
        try:
            _save_cache_image(cache, img)
        except OSError as exc:
            logger.warning("Could not persist logo cache for %s: %s", abbrev, exc)
        img = img.resize((size_px, size_px), Image.LANCZOS)
        return img

    # Fallback: MLB static CDN
    team_id = TEAM_ID_MAP.get(abbrev)
    if team_id:
        url2 = _LOGO_PNG_TEMPLATE.format(team_id=team_id)
        img = _download_image(url2)
        if img is not None:
            try:
                _save_cache_image(cache, img)
            except OSError as exc:
                logger.warning("Could not persist fallback logo cache for %s: %s", abbrev, exc)
            img = img.resize((size_px, size_px), Image.LANCZOS)
            return img

    return None


def clear_logo_cache(working_dir: str) -> None:
    logos_dir = os.path.join(working_dir, "logos")
    if os.path.isdir(logos_dir):
        for f in os.listdir(logos_dir):
            if f.endswith(".png"):
                try:
                    os.remove(os.path.join(logos_dir, f))
                except OSError as exc:
                    logger.warning("Could not remove cached logo %s: %s", f, exc)
