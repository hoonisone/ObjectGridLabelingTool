from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class GridObject:
    object_id: str
    px: float
    py: float
    col: Optional[int] = None
    row: Optional[int] = None
    source: str = "labelme"
    label: str = ""
    shape_type: str = "point"
    points: list[list[float]] = field(default_factory=list)
    original_shapes: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ImageLabelState:
    image_path: Path
    objects: list[GridObject] = field(default_factory=list)
    dirty: bool = False
