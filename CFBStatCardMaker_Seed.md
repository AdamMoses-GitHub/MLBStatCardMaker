# College Football Stat Card Maker — Project Seed Document

> **Purpose:** This document fully specifies the architecture, GUI layout, settings
> system, card-rendering pipeline, and file structure for a new Python desktop application
> called **CFB Stat Card Maker**.  It is a direct analog of the MLB Stat Card Maker,
> transplanted to college football data.  All GUI chrome, interaction patterns, and
> code conventions are preserved verbatim; only the domain (sport, data sources, tabs,
> stats) changes.

---

## 1. Technology Stack

| Concern | Choice |
|---|---|
| Language | Python 3.11+ |
| GUI framework | `tkinter` + `ttk` (stdlib — no extra GUI deps) |
| Image rendering | `Pillow` (PIL) |
| HTTP requests | `requests` |
| Settings persistence | JSON |
| Font | Roboto family (Regular, Bold, Condensed, CondensedBold, Italic) stored in `assets/fonts/Roboto/` |
| Data source | **cfbd** Python client (`cfbd` PyPI package) — wraps the College Football Data API at `https://api.collegefootballdata.com` |
| Logo source | ESPN CDN `https://a.espncdn.com/i/teamlogos/ncaa/500/{espn_id}.png` |
| Packaging | `run.py` at project root; `app/` package |

### `requirements.txt`
```
cfbd>=4.0
Pillow>=10.0
requests>=2.31
```

---

## 2. Project File Structure

```
CFBStatCardMaker/
├── run.py                        # entry point
├── requirements.txt
├── README.md
├── INSTALL_AND_USAGE.md
├── assets/
│   └── fonts/
│       └── Roboto/
│           ├── Roboto-Regular.ttf
│           ├── Roboto-Bold.ttf
│           ├── Roboto-Italic.ttf
│           ├── RobotoCondensed-Regular.ttf
│           └── RobotoCondensed-Bold.ttf
└── app/
    ├── __init__.py
    ├── main.py                   # main() entry, creates Settings + MainWindow
    ├── settings.py               # Settings dataclass + JSON load/save
    ├── cards/
    │   ├── __init__.py
    │   ├── base_card.py          # CardConfig base dataclass + canvas helper
    │   ├── standings_card.py     # Conference standings card
    │   ├── offense_card.py       # Top offensive players card
    │   ├── defense_card.py       # Top defensive players card
    │   ├── passing_card.py       # Top passers card
    │   ├── rushing_card.py       # Top rushers card
    │   ├── receiving_card.py     # Top receivers card
    │   ├── roster_card.py        # Team roster card
    │   ├── matchup_card.py       # Head-to-head team matchup card
    │   ├── career_card.py        # Player career stats card
    │   ├── history_card.py       # Season leaders history card
    │   └── game_record_card.py   # Team recent game results card
    ├── data/
    │   ├── __init__.py
    │   ├── cfb_api.py            # Core API wrapper (standings, schedule)
    │   ├── offense_api.py        # Offensive player stat fetching
    │   ├── defense_api.py        # Defensive player stat fetching
    │   ├── passing_api.py
    │   ├── rushing_api.py
    │   ├── receiving_api.py
    │   ├── roster_api.py
    │   ├── matchup_api.py
    │   ├── career_api.py
    │   ├── history_api.py
    │   ├── game_record_api.py
    │   └── logo_cache.py         # ESPN CDN logo downloader + disk cache
    ├── ui/
    │   ├── __init__.py
    │   ├── main_window.py        # MainWindow(tk.Tk) — notebook + bottom bar
    │   ├── standings_tab.py
    │   ├── offense_tab.py
    │   ├── defense_tab.py
    │   ├── passing_tab.py
    │   ├── rushing_tab.py
    │   ├── receiving_tab.py
    │   ├── roster_tab.py
    │   ├── matchup_tab.py
    │   ├── career_tab.py
    │   ├── history_tab.py
    │   ├── game_record_tab.py
    │   └── settings_tab.py
    └── utils/
        ├── __init__.py
        ├── font_manager.py       # Cached get_font() via lru_cache
        └── image_utils.py        # apply_export_margin()
```

---

## 3. Application Entry Points

### `run.py`
```python
"""Top-level launch script for CFB Stat Card Maker."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from app.main import main
if __name__ == "__main__":
    main()
```

### `app/main.py`
```python
from app.settings import Settings, init_working_dir
from app.ui.main_window import MainWindow
import os

def main() -> None:
    default_cfg_dir = Settings().working_dir
    os.makedirs(default_cfg_dir, exist_ok=True)
    settings = Settings.load(default_cfg_dir)
    init_working_dir(settings.working_dir)
    app = MainWindow(settings)
    app.mainloop()
```

---

## 4. Main Window Layout

**Class:** `MainWindow(tk.Tk)` in `app/ui/main_window.py`

```
┌─────────────────────────────────────────────────────────────┐
│  CFB Stat Card Maker                               [─][□][✕] │
├──────────────────────────────────────────────────────────────┤
│ [Standings][Off. Leaders][Def. Leaders][Passing][Rushing]    │
│ [Receiving][Team Roster][Matchup][Player Career]             │
│ [Game Record][Settings]                                      │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│   (active tab content — left controls + right preview)       │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│ [Open Output Directory]                          [Quit]      │
└──────────────────────────────────────────────────────────────┘
```

### Tab order (notebook labels with padding spaces)
1. `"  Standings  "`
2. `"  Off. Leaders  "`
3. `"  Def. Leaders  "`
4. `"  Passing  "`
5. `"  Rushing  "`
6. `"  Receiving  "`
7. `"  Team Roster  "`
8. `"  Matchup  "`
9. `"  Player Career  "`
10. `"  Game Record  "`
11. `"  Settings  "`

### Bottom bar (persistent across all tabs)
- `ttk.Separator` (horizontal) above buttons
- Left side: `ttk.Button("Open Output Directory")` — opens `{working_dir}/output/` in the OS file manager
- Right side: `ttk.Button("Quit")` — calls `_on_close()`

### `_on_close()` sequence
1. Call `tab.apply()` on every tab (persists UI → settings)
2. Save `window_geometry`
3. Call `settings.save(settings.working_dir)`
4. `self.destroy()`

---

## 5. Universal Tab Layout Pattern

**Every** content tab follows this identical structure:

```
Tab (ttk.Frame)
└── ttk.PanedWindow (orient=horizontal, fill=both, expand=True, padx=8, pady=8)
    ├── controls (ttk.Frame, width=290, weight=0)
    │   └── [stacked LabelFrames — see §6]
    └── preview_frame (ttk.LabelFrame, text="Preview", weight=1)
        └── tk.Canvas (bg="#CCCCCC", width=480, height=320)
            └── (thumbnail PhotoImage centered on canvas)
```

The paned divider lets the user resize the left control panel vs. the right preview.

---

## 6. Standard Control Panel Sections

Every tab's left panel contains these sections **in this order**, using
`ttk.LabelFrame` widgets stacked vertically with `pack(fill="x", padx=8, pady=4)`.

### 6.1 Card Size
```
LabelFrame "Card Size"
├── Row: Label "W (in):"  Spinbox(2.0–24.0, step=0.5)  Label "H (in):"  Spinbox
├── Checkbutton "Use global card size" (disables spinboxes when checked)
└── Label (orientation hint: "Landscape" or "Portrait", color #555555)
```
- Spinboxes bind `<FocusOut>`, `<<Increment>>`, `<<Decrement>>` → `_on_size_changed()`
- `_on_size_changed()` calls `_update_col_suggestion()` (if applicable) and triggers a live preview re-render

### 6.2 Scope  *(league/conference filter tabs)*
```
LabelFrame "Scope"
└── ttk.Combobox (readonly, values=SCOPE_OPTIONS)
```

### 6.3 Card-specific filter sections
Varies per tab — documented per-tab in §9.

### 6.4 Display Options
```
LabelFrame "Display Options"
├── Checkbutton "Show team logos"
├── Checkbutton "Show 'data as of' timestamp"
└── Checkbutton "Show column explainers"
```
*(not all options appear on every tab — match what makes sense)*

### 6.5 Background Color
```
LabelFrame "Background Color"
└── Row: Entry(width=9, hex color)  Label(swatch, relief=sunken)  Button("Pick…")
```
- Entry traces `"write"` → updates swatch
- Button opens `colorchooser.askcolor()`

### 6.6 Fetch & Preview
```
ttk.Separator (horizontal)
Row: Button("Fetch & Preview")  Button("↺ Refresh", width=9)
Button("Full Preview…", state=disabled until card rendered)
Label (status/error, wraplength=260, foreground=#aa2200)
```
- `"Fetch & Preview"` runs a background thread (sets `_fetching=True`, disables button)
- Thread calls the appropriate API fetch function, then renders the card, then posts result to main thread via `after()`
- `"↺ Refresh"` forces a cache-bypass re-fetch
- `"Full Preview…"` opens the rendered `Image` in a `Toplevel` scrollable window

### 6.7 Export
```
LabelFrame "Export"
├── Label "Filename (no extension):"
├── Entry (textvariable=_export_name_var, width=24)
├── Checkbutton "Append timestamp to filename"
└── Row: Button("Export PNG")  Button("Export JPG")
    (both disabled until card rendered)
```
Export writes to `{working_dir}/output/{filename}[_{timestamp}].{ext}`

---

## 7. Preview Panel Behavior

- **Thumbnail** `THUMB_W=480, THUMB_H=320` — the rendered PIL `Image` is fit inside this bounding box (aspect-ratio preserved) using `Image.thumbnail()`
- The thumbnail is displayed as a `tk.Canvas` with `create_image()` centered
- The full-res `Image` is kept as `self._card_image` for export
- **Full Preview** opens a `tk.Toplevel` with a `tk.Canvas` wrapped in both scrollbars; the full-size image is shown at screen-friendly zoom (max 90% of screen dimensions)

---

## 8. Settings Tab

**Class:** `SettingsTab(ttk.Frame)` in `app/ui/settings_tab.py`

The Settings tab uses a simple vertical stack of `ttk.LabelFrame` sections (no
PanedWindow, no preview panel):

### 8.1 Working Directory
```
LabelFrame "Working Directory"
├── Label "Output folder for cards, logos, and settings:"
└── Row: Entry(width=52)  Button("Browse…")  Button("Open…")
```
`Browse…` → `filedialog.askdirectory()`
`Open…` → `os.startfile()` / `subprocess.Popen(["open", ...])` / `xdg-open`

### 8.2 Default Card Size
```
LabelFrame "Default Card Size"
└── Row: Label "Width (in):"  Spinbox(1–24, 0.5)
         Label "Height (in):" Spinbox(1–24, 0.5)
         Label "(Landscape)" or "(Portrait)"
```

### 8.3 Export DPI
```
LabelFrame "Export DPI"
└── Row: Radiobuttons [72, 150, 300, 600, 900, 1200, 1500, 1800]
         Label "Custom:"  Spinbox(72–1200, step=50)
```

### 8.4 Default Background Color
```
LabelFrame "Default Background Color"
└── Row: Entry(width=10, hex)  Label(swatch)  Button("Pick Color…")
```

### 8.5 Data Cache
```
LabelFrame "Data Cache"
├── Row: Label "API cache TTL:"  Spinbox(1–1440, step=5)  Label "minutes"
├── Label (explanation text, foreground=#555555, wraplength=420)
└── Button "Clear Memory Cache"
```

### 8.6 Column Explainer Separator
```
LabelFrame "Column Explainer Separator"
└── Row: Radiobutton("=  · e.g. OPS=OBP+SLG")
         Radiobutton(":  · e.g. OPS: OBP+SLG")
         Radiobutton("–  · e.g. OPS–OBP+SLG")
```

### 8.7 Export Canvas Margin
```
LabelFrame "Export Canvas Margin"
└── Row: Spinbox(0.0–20.0, step=0.5)  Label "%"
         Label "Adds a border of this size around the card on export (PNG/JPG only)."
```

### 8.8 Save button
`ttk.Button("Save Settings", anchor="e")` — calls `self.apply()`

---

## 9. Tab Specifications (CFB Domain)

### 9.1 Standings Tab

**Card:** `StandingsCardRenderer` / `StandingsCardConfig`
**Data source:** `cfb_api.fetch_standings(season, conference)`

**Control sections (after Card Size):**
- **Season** — `Spinbox` (year range, default = current season)
- **Scope** — `Combobox` values: `["All FBS", "ACC", "Big 12", "Big Ten", "SEC", "Pac-12", "American", "Mountain West", "Sun Belt", "MAC", "C-USA", "Independents"]`
- **Columns** — Radiobuttons:
  - `auto` "Auto (suggested)"
  - `standard` "Standard  (W L PCT)"
  - `extended` "Extended  (+Conf PF PA)"
- **Display Options** — Show logos, Show timestamp, Show column explainers

**Default card size:** 6.0 × 4.0 in

**Card column sets:**
- `STANDARD_COLS = ["TEAM", "W", "L", "PCT"]`
- `EXTENDED_COLS = ["TEAM", "W", "L", "PCT", "CONF_W", "CONF_L", "PF", "PA", "STK"]`

**Column explainers:**
```python
{
    "W":      "Wins",
    "L":      "Losses",
    "PCT":    "Win %",
    "CONF_W": "Conf Wins",
    "CONF_L": "Conf Losses",
    "PF":     "Points For",
    "PA":     "Points Against",
    "STK":    "Current Streak",
}
```

**Settings fields (prefix `standings_`):**
`scope`, `season`, `column_mode`, `show_logos`, `show_timestamp`, `show_col_explainers`,
`width_in` (6.0), `height_in` (4.0), `use_global_size`, `bg_color`,
`export_filename` ("standings_card"), `append_timestamp`

---

### 9.2 Off. Leaders Tab

**Card:** `OffenseCardRenderer` / `OffenseCardConfig`
**Data source:** `offense_api.fetch_offense(season, conference, stat_type, top_n, min_plays)`

**Control sections (after Card Size):**
- **Season** — `Spinbox`
- **Scope** — `Combobox` (same conference list as Standings)
- **Stat Type** — Radiobuttons: `["Scoring", "Total Offense", "Rushing Offense", "Passing Offense"]`
- **Query Options:**
  - `Spinbox` "Top N" (default 10, range 5–25)
  - `Spinbox` "Min plays" (default 200)
- **Display Options** — Show logos, Show rank badges, Show timestamp, Show column explainers

**Default card size:** 7.0 × 5.0 in

**Column sets:**
```python
STANDARD_COLS = ["RANK", "TEAM", "G", "PTS", "PPG"]
EXTENDED_COLS = ["RANK", "TEAM", "G", "PTS", "PPG", "YDS", "YPG", "PLAYS", "YPP"]
```

**Column explainers:**
```python
{
    "G":     "Games Played",
    "PTS":   "Total Points",
    "PPG":   "Points Per Game",
    "YDS":   "Total Yards",
    "YPG":   "Yards Per Game",
    "PLAYS": "Total Plays",
    "YPP":   "Yards Per Play",
}
```

**Settings fields (prefix `offense_`):**
`scope`, `season`, `stat_type`, `top_n`, `min_plays`, `column_mode`,
`show_logos`, `show_rank_badges`, `show_timestamp`, `show_col_explainers`,
`width_in` (7.0), `height_in` (5.0), `use_global_size`, `bg_color`,
`export_filename` ("offense_card"), `append_timestamp`

---

### 9.3 Def. Leaders Tab

**Card:** `DefenseCardRenderer` / `DefenseCardConfig`
**Data source:** `defense_api.fetch_defense(season, conference, stat_type, top_n)`

**Control sections (after Card Size):**
- **Season** — `Spinbox`
- **Scope** — `Combobox`
- **Stat Type** — Radiobuttons: `["Scoring Defense", "Total Defense", "Rush Defense", "Pass Defense", "Sacks", "Interceptions"]`
- **Query Options:** Top N spinbox (default 10)
- **Display Options** — Show logos, Show rank badges, Show timestamp, Show column explainers

**Default card size:** 7.0 × 5.0 in

**Column sets:**
```python
STANDARD_COLS = ["RANK", "TEAM", "G", "PTS", "PPG"]
EXTENDED_COLS = ["RANK", "TEAM", "G", "PTS", "PPG", "YDS", "YPG", "SACKS", "INT"]
```

**Column explainers:**
```python
{
    "G":     "Games Played",
    "PTS":   "Points Allowed",
    "PPG":   "Points Allowed/Game",
    "YDS":   "Total Yards Allowed",
    "YPG":   "Yards Allowed/Game",
    "SACKS": "Sacks",
    "INT":   "Interceptions",
}
```

**Settings fields (prefix `defense_`):**
`scope`, `season`, `stat_type`, `top_n`, `column_mode`,
`show_logos`, `show_rank_badges`, `show_timestamp`, `show_col_explainers`,
`width_in` (7.0), `height_in` (5.0), `use_global_size`, `bg_color`,
`export_filename` ("defense_card"), `append_timestamp`

---

### 9.4 Passing Tab

**Card:** `PassingCardRenderer` / `PassingCardConfig`
**Data source:** `passing_api.fetch_passers(season, conference, top_n, min_att)`

**Control sections (after Card Size):**
- **Season** — `Spinbox`
- **Scope** — `Combobox`
- **Query Options:**
  - `Combobox` "Sort by" — `["YDS", "TD", "RATING", "CMP_PCT", "YPA"]`
  - `Spinbox` "Top N" (default 10)
  - `Spinbox` "Min att" (default 100)
- **Display Options** — Show logos, Show rank badges, Show jersey number, Show timestamp, Show column explainers

**Default card size:** 7.0 × 5.0 in

**Column sets:**
```python
STANDARD_COLS = ["RANK", "PLAYER", "TEAM", "CMP", "ATT", "YDS", "TD", "INT", "RATING"]
EXTENDED_COLS = ["RANK", "PLAYER", "TEAM", "CMP", "ATT", "CMP_PCT", "YDS", "YPA", "TD", "INT", "RATING"]
```

**Column explainers:**
```python
{
    "CMP":     "Completions",
    "ATT":     "Attempts",
    "CMP_PCT": "Completion %",
    "YDS":     "Passing Yards",
    "YPA":     "Yards Per Attempt",
    "TD":      "Touchdowns",
    "INT":     "Interceptions",
    "RATING":  "Passer Rating",
}
```

**Settings fields (prefix `passing_`):**
`scope`, `season`, `sort_stat`, `top_n`, `min_att`, `column_mode`,
`show_logos`, `show_rank_badges`, `show_jersey_number`, `show_timestamp`, `show_col_explainers`,
`width_in` (7.0), `height_in` (5.0), `use_global_size`, `bg_color`,
`export_filename` ("passing_card"), `append_timestamp`

---

### 9.5 Rushing Tab

**Card:** `RushingCardRenderer` / `RushingCardConfig`
**Data source:** `rushing_api.fetch_rushers(season, conference, top_n, min_car)`

**Control sections (after Card Size):**
- **Season** — `Spinbox`
- **Scope** — `Combobox`
- **Query Options:**
  - `Combobox` "Sort by" — `["YDS", "TD", "YPC", "CAR"]`
  - `Spinbox` "Top N" (default 10)
  - `Spinbox` "Min carries" (default 50)
- **Display Options** — Show logos, Show rank badges, Show jersey number, Show timestamp, Show column explainers

**Default card size:** 7.0 × 5.0 in

**Column sets:**
```python
STANDARD_COLS = ["RANK", "PLAYER", "TEAM", "CAR", "YDS", "AVG", "TD"]
EXTENDED_COLS = ["RANK", "PLAYER", "TEAM", "CAR", "YDS", "AVG", "TD", "LNG", "20+"]
```

**Column explainers:**
```python
{
    "CAR": "Carries",
    "YDS": "Rushing Yards",
    "AVG": "Avg Yards/Carry",
    "TD":  "Touchdowns",
    "LNG": "Longest Run",
    "20+": "Runs 20+ Yards",
}
```

**Settings fields (prefix `rushing_`):**
`scope`, `season`, `sort_stat`, `top_n`, `min_carries`, `column_mode`,
`show_logos`, `show_rank_badges`, `show_jersey_number`, `show_timestamp`, `show_col_explainers`,
`width_in` (7.0), `height_in` (5.0), `use_global_size`, `bg_color`,
`export_filename` ("rushing_card"), `append_timestamp`

---

### 9.6 Receiving Tab

**Card:** `ReceivingCardRenderer` / `ReceivingCardConfig`
**Data source:** `receiving_api.fetch_receivers(season, conference, top_n, min_rec)`

**Control sections (after Card Size):**
- **Season** — `Spinbox`
- **Scope** — `Combobox`
- **Query Options:**
  - `Combobox` "Sort by" — `["YDS", "REC", "TD", "YPR"]`
  - `Spinbox` "Top N" (default 10)
  - `Spinbox` "Min receptions" (default 20)
- **Display Options** — Show logos, Show rank badges, Show jersey number, Show timestamp, Show column explainers

**Default card size:** 7.0 × 5.0 in

**Column sets:**
```python
STANDARD_COLS = ["RANK", "PLAYER", "TEAM", "REC", "YDS", "AVG", "TD"]
EXTENDED_COLS = ["RANK", "PLAYER", "TEAM", "REC", "YDS", "AVG", "TD", "LNG", "TGT"]
```

**Column explainers:**
```python
{
    "REC": "Receptions",
    "YDS": "Receiving Yards",
    "AVG": "Avg Yards/Reception",
    "TD":  "Touchdowns",
    "LNG": "Longest Reception",
    "TGT": "Targets",
}
```

**Settings fields (prefix `receiving_`):**
`scope`, `season`, `sort_stat`, `top_n`, `min_rec`, `column_mode`,
`show_logos`, `show_rank_badges`, `show_jersey_number`, `show_timestamp`, `show_col_explainers`,
`width_in` (7.0), `height_in` (5.0), `use_global_size`, `bg_color`,
`export_filename` ("receiving_card"), `append_timestamp`

---

### 9.7 Team Roster Tab

**Card:** `RosterCardRenderer` / `RosterCardConfig`
**Data source:** `roster_api.fetch_roster(team, season)`

**Control sections (after Card Size):**
- **Team** — `Combobox` (full FBS team list)
- **Season** — `Spinbox`
- **Display Options:**
  - Checkbutton "Group by position"
  - Checkbutton "Show jersey number"
  - Checkbutton "Show hometown / state"
  - Checkbutton "Show year (Fr/So/Jr/Sr)"
  - Checkbutton "Show height / weight"
  - Checkbutton "Show team logo"
  - Checkbutton "Show timestamp"
  - Checkbutton "Hide offensive linemen"
  - Checkbutton "Hide special teams"

**Default card size:** 5.0 × 7.0 in (portrait)

**Settings fields (prefix `roster_`):**
`team`, `season`, `group_by_position`, `show_jersey_number`, `show_hometown`,
`show_year`, `show_height_weight`, `show_logos`, `show_timestamp`,
`hide_ol`, `hide_st`,
`width_in` (5.0), `height_in` (7.0), `use_global_size`, `bg_color`,
`export_filename` ("roster_card"), `append_timestamp`

---

### 9.8 Matchup Tab

**Card:** `MatchupCardRenderer` / `MatchupCardConfig`
**Data source:** `matchup_api.fetch_matchup(team_a, team_b, season)`

**Control sections (after Card Size):**
- **Team A** — `Combobox` (full FBS team list)
- **Team B** — `Combobox`
- **Season** — `Spinbox` (default 0 = current season)
- **Stat Set** — Radiobuttons: `["Standard", "Advanced"]`
  - Standard: overall record, PPG, total yards/game, turnovers
  - Advanced: EPA/play, success rate, explosiveness
- **Display Options:**
  - Checkbutton "Show team logos"
  - Checkbutton "Show timestamp"
  - Color picker "Win highlight color" (default `"#D4EDDA"`)

**Default card size:** 6.5 × 5.5 in

**Settings fields (prefix `matchup_`):**
`team_a`, `team_b`, `season`, `stat_set`, `win_highlight_color`,
`show_logos`, `show_timestamp`,
`width_in` (6.5), `height_in` (5.5), `use_global_size`, `bg_color`,
`export_filename` ("matchup_card"), `append_timestamp`

---

### 9.9 Player Career Tab

**Card:** `CareerCardRenderer` / `CareerCardConfig`
**Data source:** `career_api.fetch_career(player_id, stat_type)`, `career_api.search_players(query)`

**Control sections (after Card Size):**
- **Player** — `LabelFrame "Player"`
  - `Entry` + `Button("Search")` → populates `Listbox` / `Combobox` with matches
  - Recent-players `Combobox` (last 5 searched, stored in settings)
- **Stat Type** — Radiobuttons: `["Passing", "Rushing", "Receiving", "Defense"]`
- **Season Range:**
  - `Spinbox` "From year" (0 = career start)
  - `Spinbox` "To year" (0 = career end)
  - `Combobox` "Sort" — `["Ascending", "Descending"]`
- **Display Options:**
  - Checkbutton "Show team logo"
  - Checkbutton "Highlight most recent season"
  - Checkbutton "Show timestamp"
  - Checkbutton "Show column explainers"

**Default card size:** 7.0 × 6.0 in

**Column sets by stat type:**
```python
PASSING_COLS  = ["YEAR", "TEAM", "G", "CMP", "ATT", "YDS", "TD", "INT", "RATING"]
RUSHING_COLS  = ["YEAR", "TEAM", "G", "CAR", "YDS", "AVG", "TD"]
RECEIVING_COLS= ["YEAR", "TEAM", "G", "REC", "YDS", "AVG", "TD"]
DEFENSE_COLS  = ["YEAR", "TEAM", "G", "TKL", "SACKS", "INT", "PD", "FF"]
```

**Settings fields (prefix `career_`):**
`stat_type`, `player_id`, `player_name`, `current_team_abbrev`,
`year_start`, `year_end`, `year_sort`, `recent_players` (list of `{id, name, team}`),
`show_logos`, `highlight_current`, `show_timestamp`, `show_col_explainers`,
`width_in` (7.0), `height_in` (6.0), `use_global_size`, `bg_color`,
`export_filename` ("career_card"), `append_timestamp`

---

### 9.10 Game Record Tab

**Card:** `GameRecordCardRenderer` / `GameRecordCardConfig`
**Data source:** `game_record_api.fetch_game_record(team, season, n, mode)`

**Control sections (after Card Size):**
- **Team** — `Combobox` (full FBS team list)
- **Season** — `Spinbox`
- **Mode** — Radiobuttons: `["games", "series"]`
  - `games`: show last N individual game results
  - `series`: show last N series/opponents
- **N** — `Spinbox` "Number of games/series" (default 10)
- **Series Detail** *(visible only when mode=series)* — Radiobuttons:
  - `"result_only"` "Result only"
  - `"scores"` "With scores"
- **Display Options:**
  - Checkbutton "Show team logo"
  - Checkbutton "Show summary (W-L record)"
  - Checkbutton "Show timestamp"
- **Date Sort** — Radiobuttons: `["Descending (newest first)", "Ascending (oldest first)"]`

**Default card size:** 6.0 × 8.0 in (portrait)

**Settings fields (prefix `game_record_`):**
`team`, `season`, `mode`, `n`, `series_detail`, `show_logos`, `show_summary`,
`show_timestamp`, `date_sort`,
`width_in` (6.0), `height_in` (8.0), `use_global_size`, `bg_color`,
`export_filename` ("game_record_card"), `append_timestamp`

---

## 10. Settings Dataclass

**File:** `app/settings.py`

```python
from __future__ import annotations
import json, logging, os, shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)
DEFAULT_WORKING_DIR = str(Path.home() / "CFBStatCards")


@dataclass
class Settings:
    working_dir: str = DEFAULT_WORKING_DIR
    card_width_in: float = 6.0
    card_height_in: float = 4.0
    dpi: int = 300
    bg_color: str = "#FFFFFF"

    # Global column explainer separator
    col_explainer_sep: str = "="

    # Export canvas margin
    export_canvas_margin_pct: float = 0.0

    # Data cache TTL
    data_cache_ttl_minutes: int = 15

    # UI state
    window_geometry: str = ""

    # ---- Standings ----
    standings_scope: str = "All FBS"
    standings_season: int = 0           # 0 = current season
    standings_column_mode: str = "auto"
    standings_show_logos: bool = True
    standings_show_timestamp: bool = False
    standings_show_col_explainers: bool = False
    standings_width_in: float = 6.0
    standings_height_in: float = 4.0
    standings_use_global_size: bool = False
    standings_bg_color: str = "#FFFFFF"
    standings_export_filename: str = "standings_card"
    standings_append_timestamp: bool = True

    # ---- Offense ----
    offense_scope: str = "All FBS"
    offense_season: int = 0
    offense_stat_type: str = "Scoring"
    offense_top_n: int = 10
    offense_min_plays: int = 200
    offense_column_mode: str = "auto"
    offense_show_logos: bool = True
    offense_show_rank_badges: bool = True
    offense_show_timestamp: bool = False
    offense_show_col_explainers: bool = False
    offense_width_in: float = 7.0
    offense_height_in: float = 5.0
    offense_use_global_size: bool = False
    offense_bg_color: str = "#FFFFFF"
    offense_export_filename: str = "offense_card"
    offense_append_timestamp: bool = True

    # ---- Defense ----
    defense_scope: str = "All FBS"
    defense_season: int = 0
    defense_stat_type: str = "Scoring Defense"
    defense_top_n: int = 10
    defense_column_mode: str = "auto"
    defense_show_logos: bool = True
    defense_show_rank_badges: bool = True
    defense_show_timestamp: bool = False
    defense_show_col_explainers: bool = False
    defense_width_in: float = 7.0
    defense_height_in: float = 5.0
    defense_use_global_size: bool = False
    defense_bg_color: str = "#FFFFFF"
    defense_export_filename: str = "defense_card"
    defense_append_timestamp: bool = True

    # ---- Passing ----
    passing_scope: str = "All FBS"
    passing_season: int = 0
    passing_sort_stat: str = "YDS"
    passing_top_n: int = 10
    passing_min_att: int = 100
    passing_column_mode: str = "auto"
    passing_show_logos: bool = True
    passing_show_rank_badges: bool = True
    passing_show_jersey_number: bool = False
    passing_show_timestamp: bool = False
    passing_show_col_explainers: bool = False
    passing_width_in: float = 7.0
    passing_height_in: float = 5.0
    passing_use_global_size: bool = False
    passing_bg_color: str = "#FFFFFF"
    passing_export_filename: str = "passing_card"
    passing_append_timestamp: bool = True

    # ---- Rushing ----
    rushing_scope: str = "All FBS"
    rushing_season: int = 0
    rushing_sort_stat: str = "YDS"
    rushing_top_n: int = 10
    rushing_min_carries: int = 50
    rushing_column_mode: str = "auto"
    rushing_show_logos: bool = True
    rushing_show_rank_badges: bool = True
    rushing_show_jersey_number: bool = False
    rushing_show_timestamp: bool = False
    rushing_show_col_explainers: bool = False
    rushing_width_in: float = 7.0
    rushing_height_in: float = 5.0
    rushing_use_global_size: bool = False
    rushing_bg_color: str = "#FFFFFF"
    rushing_export_filename: str = "rushing_card"
    rushing_append_timestamp: bool = True

    # ---- Receiving ----
    receiving_scope: str = "All FBS"
    receiving_season: int = 0
    receiving_sort_stat: str = "YDS"
    receiving_top_n: int = 10
    receiving_min_rec: int = 20
    receiving_column_mode: str = "auto"
    receiving_show_logos: bool = True
    receiving_show_rank_badges: bool = True
    receiving_show_jersey_number: bool = False
    receiving_show_timestamp: bool = False
    receiving_show_col_explainers: bool = False
    receiving_width_in: float = 7.0
    receiving_height_in: float = 5.0
    receiving_use_global_size: bool = False
    receiving_bg_color: str = "#FFFFFF"
    receiving_export_filename: str = "receiving_card"
    receiving_append_timestamp: bool = True

    # ---- Roster ----
    roster_team: str = "Alabama"
    roster_season: int = 0
    roster_group_by_position: bool = True
    roster_show_jersey_number: bool = True
    roster_show_hometown: bool = True
    roster_show_year: bool = True
    roster_show_height_weight: bool = False
    roster_show_logos: bool = True
    roster_show_timestamp: bool = False
    roster_hide_ol: bool = False
    roster_hide_st: bool = False
    roster_width_in: float = 5.0
    roster_height_in: float = 7.0
    roster_use_global_size: bool = False
    roster_bg_color: str = "#FFFFFF"
    roster_export_filename: str = "roster_card"
    roster_append_timestamp: bool = True

    # ---- Matchup ----
    matchup_team_a: str = "Alabama"
    matchup_team_b: str = "Georgia"
    matchup_season: int = 0
    matchup_stat_set: str = "Standard"
    matchup_win_highlight_color: str = "#D4EDDA"
    matchup_show_logos: bool = True
    matchup_show_timestamp: bool = False
    matchup_width_in: float = 6.5
    matchup_height_in: float = 5.5
    matchup_use_global_size: bool = False
    matchup_bg_color: str = "#FFFFFF"
    matchup_export_filename: str = "matchup_card"
    matchup_append_timestamp: bool = True

    # ---- Career ----
    career_stat_type: str = "Passing"
    career_player_id: int = 0
    career_player_name: str = ""
    career_current_team_abbrev: str = ""
    career_year_start: int = 0
    career_year_end: int = 0
    career_year_sort: str = "Ascending"
    career_recent_players: list = field(default_factory=list)
    career_show_logos: bool = True
    career_highlight_current: bool = True
    career_show_timestamp: bool = False
    career_show_col_explainers: bool = False
    career_width_in: float = 7.0
    career_height_in: float = 6.0
    career_use_global_size: bool = False
    career_bg_color: str = "#FFFFFF"
    career_export_filename: str = "career_card"
    career_append_timestamp: bool = True

    # ---- Game Record ----
    game_record_team: str = "Alabama"
    game_record_season: int = 0
    game_record_mode: str = "games"
    game_record_n: int = 10
    game_record_series_detail: str = "result_only"
    game_record_show_logos: bool = True
    game_record_show_summary: bool = True
    game_record_show_timestamp: bool = False
    game_record_date_sort: str = "desc"
    game_record_width_in: float = 6.0
    game_record_height_in: float = 8.0
    game_record_use_global_size: bool = False
    game_record_bg_color: str = "#FFFFFF"
    game_record_export_filename: str = "game_record_card"
    game_record_append_timestamp: bool = True

    # ---- Per-tab column explainers ----
    standings_show_col_explainers: bool = False
    offense_show_col_explainers: bool = False
    defense_show_col_explainers: bool = False
    passing_show_col_explainers: bool = False
    rushing_show_col_explainers: bool = False
    receiving_show_col_explainers: bool = False
    roster_show_col_explainers: bool = False
    matchup_show_col_explainers: bool = False

    _path: str = field(default="", repr=False, compare=False)
```

**`load()` / `save()` pattern:**
- Settings file lives at `{working_dir}/settings/settings.json`
- `load()` reads JSON, strips unknown keys, passes known keys as `**kwargs` to constructor
- `save()` calls `json.dump(asdict(obj), ...)` skipping `_path`
- One-time migration: if `settings.json` at root exists but not in `settings/`, move it

**`init_working_dir(working_dir)` helper:**
Creates subdirs `output/`, `logos/`, `settings/`, and writes a `README.txt` explaining the folder.

---

## 11. Base Card Infrastructure

### `app/cards/base_card.py`

```python
@dataclass
class CardConfig:
    width_in: float = 6.0
    height_in: float = 4.0
    dpi: int = 300
    bg_color: str = "#FFFFFF"

    @property
    def width_px(self) -> int: return round(self.width_in * self.dpi)

    @property
    def height_px(self) -> int: return round(self.height_in * self.dpi)

    @property
    def is_landscape(self) -> bool: return self.width_in >= self.height_in

    def new_canvas(self) -> Image.Image:
        return Image.new("RGB", (self.width_px, self.height_px),
                         _validate_color(self.bg_color))

    def export(self, image: Image.Image, path: str, fmt: str = "PNG") -> str:
        # Creates dirs, handles JPEG alpha conversion, fixes extension
        ...
```

### Card Renderer pattern

Each card module (`standings_card.py`, etc.) contains:
1. **`XxxCardConfig(CardConfig)`** — dataclass with card-specific display options and color fields
2. **`XxxCardRenderer`** — class with `render(data, config, working_dir) -> Image.Image`
3. **`suggest_column_mode(width_in) -> str`** — returns `"extended"` or `"standard"` based on width threshold

### Standard card color fields (on every `XxxCardConfig`)
```python
header_bg:      str = "#1a3a5c"   # column header background
header_fg:      str = "#FFFFFF"
title_bg:       str = "#1a3a5c"   # card title bar background
title_fg:       str = "#FFFFFF"
row_alt_color:  str = "#EEF2F7"   # alternating row tint
row_color:      str = "#FFFFFF"
divider_color:  str = "#CCCCCC"
div_header_bg:  str = "#2c5f8a"   # group/section sub-header background
div_header_fg:  str = "#FFFFFF"
text_color:     str = "#111111"
footer_color:   str = "#888888"
```

### Rank badge colors
```python
_BADGE_COLORS = {1: "#D4AF37", 2: "#C0C0C0", 3: "#B87333"}   # gold, silver, copper
_BADGE_OUTLINE_COLORS = {1: "#9A7B1A", 2: "#808080", 3: "#7A4A20"}
```

---

## 12. Card Rendering Layout (visual anatomy)

All stat-table cards follow this vertical layout on the PIL canvas:

```
┌──────────────────────────────────────┐  ← card top
│  [logo]   CARD TITLE                 │  ← title bar (dark bg, white text)
│           Subtitle / scope / season  │
├──────────────────────────────────────┤
│  COL1  │  COL2  │  COL3  │  COL4    │  ← column header row (dark bg)
├──────────────────────────────────────┤
│  val   │  val   │  val   │  val     │  ← data rows (alternating white/#EEF2F7)
│  val   │  val   │  val   │  val     │
│  ...                                 │
├──────────────────────────────────────┤
│  [col explainers, if enabled]        │  ← footer zone
│  Data as of: [timestamp]             │
└──────────────────────────────────────┘  ← card bottom
```

- Title bar: roughly 10–12% of card height
- Column header row: ~6% of card height
- Data rows: share the remaining space equally
- Footer: ~5–8% of card height (only if explainers or timestamp are shown)

---

## 13. Font Manager

**File:** `app/utils/font_manager.py`

```python
from functools import lru_cache
from pathlib import Path
from PIL import ImageFont

_FONT_DIR = Path(__file__).parent.parent.parent / "assets" / "fonts" / "Roboto"

_FONT_FILES = {
    ("Roboto", False, False, False): "Roboto-Regular.ttf",
    ("Roboto", True,  False, False): "Roboto-Bold.ttf",
    ("Roboto", False, True,  False): "RobotoCondensed-Regular.ttf",
    ("Roboto", True,  True,  False): "RobotoCondensed-Bold.ttf",
    ("Roboto", False, False, True):  "Roboto-Italic.ttf",
}

@lru_cache(maxsize=256)
def get_font(size: int, bold=False, condensed=False, italic=False,
             family="Roboto") -> ImageFont.FreeTypeFont:
    key = (family, bold, condensed, italic)
    filename = _FONT_FILES.get(key, "Roboto-Regular.ttf")
    path = _FONT_DIR / filename
    if not path.exists():
        return ImageFont.load_default()
    return ImageFont.truetype(str(path), size)
```

---

## 14. Logo Cache

**File:** `app/data/logo_cache.py`

```python
def get_logo(abbrev: str, size_px: int, working_dir: str) -> Optional[Image.Image]:
    """
    Return PIL Image of team logo at size_px × size_px.
    Downloads from ESPN CDN on first use and caches to {working_dir}/logos/{abbrev}.png.
    Returns None on any failure.
    """
```

**ESPN CDN URL pattern for CFB:**
`https://a.espncdn.com/i/teamlogos/ncaa/500/{espn_id}.png`

ESPN uses numeric IDs for NCAA teams.  Maintain a `TEAM_ESPN_ID_MAP: dict[str, int]`
mapping team abbreviation/slug → ESPN numeric ID.  Since CFB has 130+ FBS teams,
seed the map with at least all Power 4 + Group of 5 teams.

**Conference logo URLs:**
```python
_CONF_LOGO_URL = {
    "SEC":          "https://a.espncdn.com/i/teamlogos/ncaa_conf/500/8.png",
    "BIG_TEN":      "https://a.espncdn.com/i/teamlogos/ncaa_conf/500/4.png",
    "BIG_12":       "https://a.espncdn.com/i/teamlogos/ncaa_conf/500/12.png",
    "ACC":          "https://a.espncdn.com/i/teamlogos/ncaa_conf/500/1.png",
    "PAC_12":       "https://a.espncdn.com/i/teamlogos/ncaa_conf/500/9.png",
    "AMERICAN":     "https://a.espncdn.com/i/teamlogos/ncaa_conf/500/151.png",
    "MOUNTAIN_WEST":"https://a.espncdn.com/i/teamlogos/ncaa_conf/500/17.png",
    "SUN_BELT":     "https://a.espncdn.com/i/teamlogos/ncaa_conf/500/37.png",
    "MAC":          "https://a.espncdn.com/i/teamlogos/ncaa_conf/500/5.png",
    "CUSA":         "https://a.espncdn.com/i/teamlogos/ncaa_conf/500/11.png",
}
```

Cache logic is identical to MLB: check `{working_dir}/logos/{abbrev}.png`, download if missing.

---

## 15. Image Utilities

**File:** `app/utils/image_utils.py` — unchanged from MLB version

```python
def apply_export_margin(img: Image.Image, bg_color: str, margin_pct: float) -> Image.Image:
    """Add a proportional border around the image.  margin_pct is % of card dimensions."""
    if margin_pct <= 0:
        return img
    pad_x = max(1, round(img.width  * margin_pct / 100))
    pad_y = max(1, round(img.height * margin_pct / 100))
    canvas = Image.new(img.mode, (img.width + pad_x*2, img.height + pad_y*2), bg_color)
    canvas.paste(img, (pad_x, pad_y))
    return canvas
```

---

## 16. Data Layer Architecture

Each `*_api.py` module follows this pattern:

```python
# 1. Data models (dataclasses)
@dataclass
class XxxEntry:
    team_name: str
    team_abbrev: str
    ...

@dataclass
class XxxBlock:
    as_of: datetime.datetime
    entries: list[XxxEntry]

# 2. Fetch function (calls cfbd client)
def fetch_xxx(season: int, conference: str, ...) -> XxxBlock:
    ...

# 3. In-memory cache (dict keyed on call params, with TTL)
_cache: dict[tuple, tuple[datetime.datetime, XxxBlock]] = {}

def fetch_xxx_cached(season, conference, ..., ttl_minutes=15) -> XxxBlock:
    key = (season, conference, ...)
    if key in _cache:
        ts, block = _cache[key]
        if (datetime.datetime.now() - ts).seconds < ttl_minutes * 60:
            return block
    block = fetch_xxx(season, conference, ...)
    _cache[key] = (datetime.datetime.now(), block)
    return block

def clear_xxx_cache() -> None:
    _cache.clear()

# 4. Filter / sort helpers
def filter_xxx(block: XxxBlock, ...) -> list[XxxEntry]: ...
def sort_and_trim(entries: list[XxxEntry], sort_stat: str, top_n: int) -> list[XxxEntry]: ...
```

### CFBD API Client Usage

```python
import cfbd

configuration = cfbd.Configuration()
configuration.api_key["Authorization"] = f"Bearer {api_key}"
api_client = cfbd.ApiClient(configuration)

# Examples:
games_api  = cfbd.GamesApi(api_client)
stats_api  = cfbd.StatsApi(api_client)
teams_api  = cfbd.TeamsApi(api_client)
rankings_api = cfbd.RankingsApi(api_client)
```

**API key handling:**
- Store the user's CFBD API key in settings (`settings.cfbd_api_key: str = ""`)
- Display an API key entry field in the **Settings** tab under a new `LabelFrame "API Key"`
- If no key is configured, show an informational error in status labels; disable Fetch buttons

---

## 17. Scope / Conference Options

```python
SCOPE_OPTIONS = [
    "All FBS",
    "SEC",
    "Big Ten",
    "Big 12",
    "ACC",
    "Pac-12",
    "American Athletic",
    "Mountain West",
    "Sun Belt",
    "MAC",
    "Conference USA",
    "Independents",
]
```

---

## 18. Tab-to-Module Mapping Summary

| Tab label | Tab class | Card class | API module |
|---|---|---|---|
| Standings | `StandingsTab` | `StandingsCardRenderer` | `cfb_api` |
| Off. Leaders | `OffenseTab` | `OffenseCardRenderer` | `offense_api` |
| Def. Leaders | `DefenseTab` | `DefenseCardRenderer` | `defense_api` |
| Passing | `PassingTab` | `PassingCardRenderer` | `passing_api` |
| Rushing | `RushingTab` | `RushingCardRenderer` | `rushing_api` |
| Receiving | `ReceivingTab` | `ReceivingCardRenderer` | `receiving_api` |
| Team Roster | `RosterTab` | `RosterCardRenderer` | `roster_api` |
| Matchup | `MatchupTab` | `MatchupCardRenderer` | `matchup_api` |
| Player Career | `CareerTab` | `CareerCardRenderer` | `career_api` |
| Game Record | `GameRecordTab` | `GameRecordCardRenderer` | `game_record_api` |
| Settings | `SettingsTab` | *(none)* | *(none)* |

---

## 19. Key Behavioral Notes (port these exactly)

1. **Background threading for fetches** — every "Fetch & Preview" button spawns a
   `threading.Thread`, sets `self._fetching = True`, disables the fetch button, and
   posts results back to tkinter via `self.after(0, callback)`.  Never update widgets
   from a non-main thread.

2. **`apply()` method on every tab** — serializes all UI `tkinter.Variable` values back
   into `self.settings.*` fields.  Called by `MainWindow._on_close()`.

3. **`_on_use_global_size_changed()`** — when "Use global card size" is checked, read
   `settings.card_width_in` / `settings.card_height_in` into the tab's spinboxes and
   disable them; uncheck restores the tab's own stored size.

4. **Orientation label** — `"(Landscape)"` when W ≥ H, `"(Portrait)"` otherwise.
   Updates on every spinbox change.

5. **Column suggestion label** — for tabs with column mode=auto, show a small blue label
   like `"→ Extended columns suggested"` or `"→ Standard columns suggested"` based on
   current card width.

6. **Export path** — always `{working_dir}/output/{export_filename}[_{YYYYMMDD_HHMMSS}].{ext}`

7. **In-memory cache TTL** — use `settings.data_cache_ttl_minutes`; the "↺ Refresh"
   button bypasses the cache by calling the non-cached fetch directly.

8. **Settings persistence path** — `{working_dir}/settings/settings.json`.
   Settings are saved on `_on_close()` and on "Save Settings" button in Settings tab.

9. **Full Preview window** — `tk.Toplevel` with `tk.Canvas` + both `ttk.Scrollbar`s
   (horizontal + vertical).  Image is placed via `create_image()`.  Title shows card
   dimensions in pixels.

10. **Logo caching** — logos are saved to `{working_dir}/logos/` once downloaded.
    Corrupt cache files (unreadable images) are deleted and re-downloaded automatically.

11. **Export margin** — call `apply_export_margin(card_image, bg_color, margin_pct)`
    *before* calling `config.export()`.  Only applies on PNG/JPG export, not preview.

12. **Color swatch swatches** — `tk.Label` with `width=3`, `relief="sunken"`,
    `background=<hex>`.  Update via `.config(background=...)` in the `trace_add("write", ...)` callback.

---

## 20. Additional Settings Tab Section (CFB-specific)

Add this section to the Settings tab **before** "Save Settings":

### API Key
```
LabelFrame "College Football Data API Key"
├── Label "Required for all data fetches. Get a free key at https://collegefootballdata.com"
│         (foreground=#555555)
├── Row: Entry(textvariable=_api_key_var, width=52, show="*")
│        Button("Show/Hide")  Button("Test Key")
└── Label (status, e.g. "✓ Key valid" or "✗ Key invalid", updated by Test Key button)
```

Add to `Settings` dataclass:
```python
cfbd_api_key: str = ""
```

---

## 21. Working Directory Subdirectory Layout

After `init_working_dir(working_dir)`:
```
{working_dir}/
├── output/          ← exported PNG/JPG cards
├── logos/           ← cached team logo PNGs
├── settings/        ← settings.json
└── README.txt       ← explains the folder contents
```

---

## 22. Naming Conventions

- Tab classes: `XxxTab(ttk.Frame)` in `app/ui/xxx_tab.py`
- Card config classes: `XxxCardConfig(CardConfig)` in `app/cards/xxx_card.py`
- Card renderer classes: `XxxCardRenderer` in `app/cards/xxx_card.py`
- API fetch functions: `fetch_xxx(...)` and `fetch_xxx_cached(...)` in `app/data/xxx_api.py`
- Settings field prefix: matches the tab's short name (e.g. `passing_`, `rushing_`)
- Internal tkinter vars: `self._xxx_var` (e.g. `self._scope_var`, `self._top_n_var`)
- Internal PIL state: `self._card_image`, `self._thumb_photo`, `self._fetching`

---

## 23. Differences from MLB Version (Summary)

| Aspect | MLB | CFB |
|---|---|---|
| App name | MLB Stat Card Maker | CFB Stat Card Maker |
| Default working dir | `~/MLBStatCards` | `~/CFBStatCards` |
| Data client | `mlb-statsapi` + `pybaseball` | `cfbd` |
| API auth | None (public) | Bearer token (free CFBD key) |
| Scope options | League / division | Conference |
| Tab: player stats | Batters, Pitchers, Triple Crown | Passing, Rushing, Receiving |
| Tab: leaders | Season Leaders (Batting/Pitching) | Off. Leaders, Def. Leaders |
| Logo source | ESPN CDN (MLB team IDs) | ESPN CDN (NCAA numeric IDs) |
| Season format | Calendar year | Academic year (e.g. 2024) |
| Stat type toggle | Batting / Pitching | Passing / Rushing / Receiving / Defense |
| Card color scheme | Navy `#1a3a5c` | Same defaults (easily changed per school colors) |
