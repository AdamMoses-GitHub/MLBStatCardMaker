# MLB Stat Card Maker

*Because copy-pasting box scores into a spreadsheet is a skill nobody asked for.*

![Version](https://img.shields.io/badge/version-1.0.0-blue) ![Python](https://img.shields.io/badge/python-3.10%2B-blue?logo=python) ![License](https://img.shields.io/badge/license-MIT-green)

![App Screenshot](INSERT_IMAGE_URL_HERE)

---

## About

Keeping up with MLB stats means juggling a browser, ESPN, Baseball Reference, and a prayer — all to answer "who's leading the AL in ERA right now?" There's no single tool that pulls live stats and turns them into clean, printable, shareable images.

**MLB Stat Card Maker** fixes that. It's a desktop app that fetches live MLB data and renders it into polished, configurable stat cards you can export as PNG or JPEG. Pick a card type, set your scope, hit Fetch — done. No web scraping glue code, no Excel macros, no nonsense.

GitHub: [https://github.com/AdamMoses-GitHub/MLBStatCardMaker](https://github.com/AdamMoses-GitHub/MLBStatCardMaker)

---

## What It Does

### The Main Features

- **10 card types** — Standings, Top Batters, Top Pitchers, Triple Crown, Season Leaders, Team Roster, Head-to-Head Matchup, Player Career Stats, and Game Record
- **Live MLB data** via the `mlb-statsapi` and `pybaseball` libraries, with intelligent local caching so you're not hammering the API on every click
- **Configurable scope** — filter by All MLB, AL, NL, any division, or a single team depending on the card type
- **Team logos** on every card that supports them, auto-downloaded and cached locally
- **Export to PNG or JPEG** at your chosen DPI, with optional timestamp appended to filenames
- **Per-card size overrides** — each card type has its own width/height settings independent of the global default

### The Nerdy Stuff

- Rendered entirely in Python using **Pillow** — no browser, no WebView, no Electron, no dependencies heavier than a PIL `ImageDraw`
- **Proportional column layout engine** — every card uses a weight-ratio system so columns scale gracefully at any DPI or card size
- **JSON cache layer** with configurable TTL per data type — fetches are fast after the first run
- **Dataclass-based settings** with full JSON round-trip persistence — no registry, no INI files
- Card renderer outputs a standard `PIL.Image.Image` — trivially testable and composable outside the GUI

---

## Quick Start

See [INSTALL_AND_USAGE.md](INSTALL_AND_USAGE.md) for the full guide.

```bash
git clone https://github.com/AdamMoses-GitHub/MLBStatCardMaker.git
cd MLBStatCardMaker
pip install -r requirements.txt
python run.py
```

---

## Tech Stack

| Component | Purpose | Why This One |
|---|---|---|
| [mlb-statsapi](https://github.com/toddrob99/MLB-StatsAPI) | Live game data, standings, schedules, rosters | Official MLB Stats API wrapper; the closest thing to a blessed Python client |
| [pybaseball](https://github.com/jldbc/pybaseball) | Historical batting/pitching stats | Best-in-class scraper for Baseball Reference & FanGraphs data |
| [Pillow](https://python-pillow.org/) | Card image rendering | Battle-tested imaging library; no native deps, runs everywhere Python runs |
| [requests](https://requests.readthedocs.io/) | Logo downloads and HTTP | The obvious choice |
| tkinter / ttk | Desktop GUI | Bundled with Python; zero extra install weight for a utility app |

---

## License

MIT — do whatever you want, just don't blame us when you spend three hours tweaking card colors.

## Contributing

PRs welcome. Open an issue first for anything beyond a small fix.

<sub>mlb stats, baseball cards, sabermetrics, standings tracker, pitching stats, batting stats, python baseball, mlb api, stat generator, roster card, player career stats, head to head matchup, triple crown leaders, season leaders, game log, series results, pillow image, tkinter desktop app, baseball python, mlb tools</sub>
