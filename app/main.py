from __future__ import annotations

import os
import sys

from app.settings import Settings
from app.ui.main_window import MainWindow


def main() -> None:
    # Determine config dir: use working_dir from existing settings.json,
    # or fall back to the default location, or CWD.
    default_cfg_dir = Settings().working_dir
    os.makedirs(default_cfg_dir, exist_ok=True)

    settings = Settings.load(default_cfg_dir)

    app = MainWindow(settings)
    app.mainloop()


if __name__ == "__main__":
    main()
