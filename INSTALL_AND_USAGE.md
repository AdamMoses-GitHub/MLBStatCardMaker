# MLB Stat Card Maker — Installation & Usage

## Feature Recap

- Generate **10 distinct MLB stat card types** as exportable PNG or JPEG images
- **Standings** — any MLB scope (All MLB, AL, NL, or any single division), with standard or extended columns
- **Top Batters / Top Pitchers** — league, division, or team leaderboards with sortable stats and configurable row count
- **Triple Crown** — AVG, HR, RBI (batters) and W, SO, ERA (pitchers) leaders side-by-side
- **Season Leaders** — historical year-over-year stat leaders across a configurable date range
- **Team Roster** — active 26-man, full 40-man, or coaching staff, grouped by position
- **Head-to-Head Matchup** — season stat comparison between any two teams
- **Player Career Stats** — full season-by-season batting or pitching career for any player
- **Game Record** — last N games or series results for any team, with W/L color coding and date sort

---

## Installation

### Method A — Conda (Recommended)

Best for keeping this isolated from your system Python.

```bash
# 1. Clone the repo
git clone https://github.com/AdamMoses-GitHub/MLBStatCardMaker.git
cd MLBStatCardMaker

# 2. Create a conda environment
conda create -p ./.conda python=3.11 -y
conda activate ./.conda

# 3. Install dependencies
pip install -r requirements.txt

# 4. Launch
python run.py
```

### Method B — pip + venv (Quick)

```bash
git clone https://github.com/AdamMoses-GitHub/MLBStatCardMaker.git
cd MLBStatCardMaker

python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt
python run.py
```

---

## Launching the App

```bash
python run.py
```

The app opens a tabbed desktop window. On first launch it creates a `~/MLBStatCards/` folder for your settings, cache, and exported cards. You can change this path in the **Settings** tab.

---

## Usage Workflows

### 1. Standings Card

**Scenario:** You want a clean, shareable AL East standings image for your group chat.

1. Click the **Standings** tab.
2. Set **Scope** to `AL East`.
3. Choose **Column Mode** — `Auto` picks Extended or Standard based on card width.
4. Check **Show Logos** if you want team logos in the first column.
5. Click **Fetch & Preview**.
6. Adjust card size (width/height in inches) until the layout looks right.
7. Click **Export PNG** — the file lands in `<working_dir>/output/standings/`.

**Example:** You want to settle a debate about whether the Red Sox are actually in last place. Set scope to `AL East`, fetch, export, and share. They are.

---

### 2. Top Batters / Top Pitchers Card

**Scenario:** It's Monday morning and you want to know who leads the NL in OPS this season.

1. Click the **Top Batters** tab.
2. Set **Scope** to `NL` and **Sort By** to `OPS`.
3. Set **Top N** to 15 and **Min PA** to 75 (filters out two-week wonders).
4. Click **Fetch & Preview**.
5. Toggle **Show Rank Badges**, **Show Position**, or **Show Jersey #** to taste.
6. Export when satisfied.

**Example:** Same workflow on the **Top Pitchers** tab with Sort By = `ERA` and Pitcher Type = `Starter` to generate a "NL Cy Young Watch" card.

---

### 3. Team Roster Card

**Scenario:** You need a quick reference sheet for your fantasy baseball draft.

1. Click the **Team Roster** tab.
2. Pick the team from the **Team** dropdown.
3. Choose **Roster Type**: `Active 26-Man` for the current roster, `Full 40-Man` for depth.
4. Toggle **Group by Position** on — it sections the card by C, IF, OF, SP, RP.
5. Toggle **Show Jersey #** if you want it.
6. Fetch, preview, export.

**Example:** You're doing a keeper league and need to cross-reference a team's pitching depth. Pull the 40-man, export, and screenshot it into your notes.

---

### 4. Game Record Card

**Scenario:** You want a card showing the Yankees' last 10 games with W/L color coding.

1. Click the **Game Record** tab.
2. Select team: `New York Yankees`.
3. Set **Mode** to `Games` and **Count (N)** to `10`.
4. Set **Date Sort** to `Newest first`.
5. Enable **Show Summary** — the header band shows `Last 10 games: 7-3 · Season: 36-23 (.610)`.
6. Fetch & Preview.
7. Switch **Mode** to `Series` and **Series Detail** to `Scores` to see individual game results grouped by opponent series.

**Example:** After a rough week, you want to see exactly which series cost the team. Switch to Series + Scores view — each opponent gets a band header with the series result, and the individual game rows sit underneath, sorted newest-first.

---

### 5. Head-to-Head Matchup Card

**Scenario:** Two teams are playing tonight and you want a side-by-side season-stat comparison.

1. Click the **Matchup** tab.
2. Set **Team A** and **Team B** from the dropdowns.
3. Choose **Stat Set** (`Standard` or `Extended`).
4. Toggle **Show Logos** on.
5. Fetch & Preview — each stat row highlights the better side in green.
6. Export.

**Example:** Yankees vs. Dodgers. Standard stat set. The highlighted cells tell the whole story faster than any broadcast breakdown.

---

## Development

### Project Structure

```
MLBStatCardMaker/
├── run.py                    # Entry point
├── requirements.txt
├── .gitignore
├── app/
│   ├── main.py               # App bootstrap, settings init
│   ├── settings.py           # All settings, JSON persistence
│   ├── cards/                # Card renderers (one per card type)
│   │   ├── base_card.py      # CardConfig base class, canvas factory
│   │   ├── batters_card.py
│   │   ├── pitchers_card.py
│   │   ├── standings_card.py
│   │   ├── roster_card.py
│   │   ├── history_card.py
│   │   ├── matchup_card.py
│   │   ├── career_card.py
│   │   ├── triple_crown_card.py
│   │   └── game_record_card.py
│   ├── data/                 # API fetchers + cache layer (one per data domain)
│   │   ├── mlb_api.py        # Standings
│   │   ├── batters_api.py
│   │   ├── pitchers_api.py
│   │   ├── roster_api.py     # Also holds TEAM_NAMES, ABBREV_TO_NAME
│   │   ├── history_api.py
│   │   ├── matchup_api.py
│   │   ├── career_api.py
│   │   ├── triple_crown_api.py
│   │   ├── game_record_api.py
│   │   └── logo_cache.py     # Team logo download + disk cache
│   ├── ui/                   # tkinter tabs (one per card type + settings)
│   │   ├── main_window.py
│   │   ├── settings_tab.py
│   │   ├── standings_tab.py
│   │   ├── batter_tab.py
│   │   ├── pitcher_tab.py
│   │   ├── history_tab.py
│   │   ├── roster_tab.py
│   │   ├── matchup_tab.py
│   │   ├── career_tab.py
│   │   ├── triple_crown_tab.py
│   │   └── game_record_tab.py
│   └── utils/
│       ├── font_manager.py   # Roboto font loader
│       └── image_utils.py
└── assets/
    └── fonts/
        └── Roboto/           # Bundled Roboto + RobotoCondensed TTFs
```

### Key Directories

| Directory | Contents |
|---|---|
| `app/cards/` | Pure rendering logic. Each file receives a typed `Block` dataclass and a `Config` dataclass, returns a `PIL.Image.Image`. No GUI or I/O here. |
| `app/data/` | API fetch + local JSON cache. Each module exposes a `fetch_*()` function and typed result dataclasses. |
| `app/ui/` | tkinter tab widgets. Each tab owns its own settings load/save via `apply()`. |
| `assets/fonts/` | Bundled Roboto fonts — no system font dependency. |
| `<working_dir>/cache/` | Auto-managed JSON cache files. Safe to delete to force a full refresh. |
| `<working_dir>/output/` | Exported card images, organized in per-card-type subdirectories. |
| `<working_dir>/logos/` | Downloaded team logo PNGs, cached indefinitely. |

### Running Tests

There is no test runner configured yet. Individual modules can be exercised directly:

```bash
# Quick data smoke-test example
python -c "
from app.data.game_record_api import fetch_game_record
import tempfile
block = fetch_game_record('New York Yankees', mode='games', n=5, working_dir=tempfile.mkdtemp())
print(block.overall_record, [e.date for e in block.entries])
"
```

---

## Requirements

| Package | Version | Purpose |
|---|---|---|
| `mlb-statsapi` | ≥ 0.4 | Standings, rosters, schedules, game data |
| `Pillow` | ≥ 10.0 | Card image rendering |
| `requests` | ≥ 2.31 | Logo downloads |
| `pybaseball` | ≥ 2.2 | Historical batting/pitching stats |
| Python | ≥ 3.10 | `match` statements, `|` union types |

> **Note:** `tkinter` is required but is bundled with standard Python distributions. If your Python was installed without it (common on some Linux distros), install it via your package manager: `sudo apt install python3-tk`.
