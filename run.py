from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wine_grid_labeling_tool.app_config import load_app_config
from wine_grid_labeling_tool.gui_main import main


if __name__ == "__main__":
    config = load_app_config(ROOT / "config.yml")
    main(config)
