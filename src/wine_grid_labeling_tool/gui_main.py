from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from .app_config import AppConfig


def run(config: AppConfig | None = None) -> None:
    from .gui_app import GridLabelingApp

    root = tk.Tk()
    app = GridLabelingApp(root, config=config or AppConfig())
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


def main(config: AppConfig | None = None) -> None:
    try:
        run(config=config)
    except ModuleNotFoundError as exc:
        missing = str(exc)
        if "PIL" in missing or "yaml" in missing:
            extra = "Pillow와 PyYAML" if "yaml" in missing else "Pillow"
            messagebox.showerror(
                "필수 패키지 누락",
                f"{extra}가 설치되어야 합니다.\n\npip install -e .",
            )
            return
        raise
