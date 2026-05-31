from __future__ import annotations

import os
import sys

from app.settings import Settings, init_working_dir
from app.ui.main_window import MainWindow


def main() -> None:
    # Determine config dir: always the default working dir location.
    default_cfg_dir = Settings().working_dir
    os.makedirs(default_cfg_dir, exist_ok=True)

    settings = Settings.load(default_cfg_dir)

    # Ensure the standard subfolder layout and readme exist.
    init_working_dir(settings.working_dir)

    app = MainWindow(settings)
    app.mainloop()


if __name__ == "__main__":
    main()
