from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class AppConfig:
    zoom_min: float = 0.5
    zoom_max: float = 3.0
    zoom_sensitivity: float = 0.15


def load_app_config(config_path: Path) -> AppConfig:
    if not config_path.exists():
        return AppConfig()

    try:
        with config_path.open("r", encoding="utf-8") as f:
            payload = yaml.safe_load(f) or {}
    except OSError:
        return AppConfig()
    except yaml.YAMLError:
        return AppConfig()

    if not isinstance(payload, dict):
        return AppConfig()

    zoom_min = _read_float(payload, "zoom_min", 0.5)
    zoom_max = _read_float(payload, "zoom_max", 3.0)
    zoom_sensitivity = _read_float(payload, "zoom_sensitivity", 0.15)

    if zoom_min <= 0:
        zoom_min = 0.5
    if zoom_max < zoom_min:
        zoom_max = zoom_min
    if zoom_sensitivity <= 0:
        zoom_sensitivity = 0.15

    return AppConfig(
        zoom_min=zoom_min,
        zoom_max=zoom_max,
        zoom_sensitivity=zoom_sensitivity,
    )


def _read_float(payload: dict[str, Any], key: str, default: float) -> float:
    value = payload.get(key, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
