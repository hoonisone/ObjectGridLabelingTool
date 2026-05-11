from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .grid_types import GridObject, ImageLabelState

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def list_images(folder: Path) -> list[Path]:
    return sorted(
        [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS],
        key=lambda p: p.name.lower(),
    )


def sidecar_path_for(image_path: Path) -> Path:
    return image_path.with_suffix(".grid_labels.json")


def labelme_json_path_for(image_path: Path) -> Path:
    return image_path.with_suffix(".json")


def load_image_state(image_path: Path) -> ImageLabelState:
    sidecar_path = sidecar_path_for(image_path)
    if sidecar_path.exists():
        state = _load_sidecar(image_path, sidecar_path)
        if state.objects:
            return state

    return ImageLabelState(image_path=image_path, objects=_load_from_labelme(image_path), dirty=False)


def save_image_state(state: ImageLabelState) -> None:
    target = sidecar_path_for(state.image_path)
    serialized_objects: list[dict[str, Any]] = []
    for obj in state.objects:
        record: dict[str, Any] = {
            "object_id": obj.object_id,
            "px": obj.px,
            "py": obj.py,
            "col": obj.col,
            "row": obj.row,
            "source": obj.source,
            "label": obj.label,
            "shape_type": obj.shape_type,
        }
        if obj.source == "labelme":
            if obj.original_shapes:
                record["original_shapes"] = obj.original_shapes
            elif obj.points:
                # Backward compatibility for older states without original_shapes.
                record["points"] = obj.points
        else:
            # Manually created object is persisted as a point object.
            record["points"] = [[obj.px, obj.py]]
            record["shape_type"] = "point"
        serialized_objects.append(record)

    payload = {
        "version": 1,
        "image": state.image_path.name,
        "objects": serialized_objects,
    }
    with target.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    state.dirty = False


def _load_sidecar(image_path: Path, sidecar_path: Path) -> ImageLabelState:
    try:
        with sidecar_path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
    except (json.JSONDecodeError, OSError):
        return ImageLabelState(image_path=image_path, objects=[], dirty=False)

    objects: list[GridObject] = []
    for item in payload.get("objects", []):
        try:
            original_shapes = _read_original_shapes(item)
            point_list = _read_points_from_item(item, original_shapes)
            px = item.get("px")
            py = item.get("py")
            if px is None or py is None:
                px, py = _representative_point(point_list)

            obj = GridObject(
                object_id=str(item["object_id"]),
                px=float(px),
                py=float(py),
                col=_maybe_int(item.get("col")),
                row=_maybe_int(item.get("row")),
                source=str(item.get("source", "unknown")),
                label=str(item.get("label", "")),
                shape_type=str(item.get("shape_type", _shape_type_from_shapes(original_shapes))),
                points=[[float(x), float(y)] for x, y in point_list],
                original_shapes=original_shapes,
            )
            objects.append(obj)
        except (KeyError, TypeError, ValueError):
            continue

    return ImageLabelState(image_path=image_path, objects=objects, dirty=False)


def _load_from_labelme(image_path: Path) -> list[GridObject]:
    json_path = labelme_json_path_for(image_path)
    if not json_path.exists():
        return []

    try:
        with json_path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    grouped: dict[str, dict[str, Any]] = {}
    standalone_index = 0

    for shape in payload.get("shapes", []):
        parsed_points = _points_from_shape(shape)
        if not parsed_points:
            continue

        raw_id = shape.get("id")
        if raw_id is None:
            raw_id = shape.get("group_id")

        if raw_id is None:
            key = f"_shape_{standalone_index}"
            standalone_index += 1
        else:
            key = f"id_{raw_id}"

        entry = grouped.get(key)
        if entry is None:
            entry = {
                "points": [],
                "label": str(shape.get("label", "")),
                "shapes": [],
                "shape_types": set(),
                "col": shape.get("col"),
                "row": shape.get("row"),
            }
            grouped[key] = entry

        entry_points = entry["points"]
        assert isinstance(entry_points, list)
        entry_points.extend(parsed_points)
        entry_shapes = entry["shapes"]
        assert isinstance(entry_shapes, list)
        entry_shapes.append(shape)
        entry_shape_types = entry["shape_types"]
        assert isinstance(entry_shape_types, set)
        entry_shape_types.add(str(shape.get("shape_type", "polygon")))

        if not entry.get("label"):
            entry["label"] = str(shape.get("label", ""))
        if entry.get("col") is None:
            entry["col"] = shape.get("col")
        if entry.get("row") is None:
            entry["row"] = shape.get("row")

    objects: list[GridObject] = []
    for key, entry in grouped.items():
        points = entry["points"]
        assert isinstance(points, list)
        if not points:
            continue

        rep_x, rep_y = _representative_point(points)

        label = str(entry.get("label", ""))
        object_id = key.replace("_shape_", "s")
        original_shapes = [shape for shape in entry.get("shapes", []) if isinstance(shape, dict)]
        shape_types = entry.get("shape_types", set())
        dominant_shape_type = "point" if shape_types == {"point"} else "polygon"
        objects.append(
            GridObject(
                object_id=object_id,
                px=rep_x,
                py=rep_y,
                source="labelme",
                label=label,
                shape_type=dominant_shape_type,
                points=[[float(x), float(y)] for x, y in points],
                original_shapes=original_shapes,
                col=_maybe_int(entry.get("col")),
                row=_maybe_int(entry.get("row")),
            )
        )
    return objects


def _read_original_shapes(item: dict[str, Any]) -> list[dict[str, Any]]:
    raw = item.get("original_shapes")
    if not isinstance(raw, list):
        return []
    return [shape for shape in raw if isinstance(shape, dict)]


def _read_points_from_item(
    item: dict[str, Any], original_shapes: list[dict[str, Any]]
) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    if original_shapes:
        for shape in original_shapes:
            points.extend(_points_from_shape(shape))
        if points:
            return points

    raw_points = item.get("points")
    if isinstance(raw_points, list):
        for point in raw_points:
            try:
                x = float(point[0])
                y = float(point[1])
            except (TypeError, ValueError, IndexError):
                continue
            points.append((x, y))
    return points


def _points_from_shape(shape: dict[str, Any]) -> list[tuple[float, float]]:
    raw_points = shape.get("points")
    if not isinstance(raw_points, list):
        return []
    parsed: list[tuple[float, float]] = []
    for p in raw_points:
        try:
            parsed.append((float(p[0]), float(p[1])))
        except (TypeError, ValueError, IndexError):
            continue
    return parsed


def _representative_point(points: list[tuple[float, float]]) -> tuple[float, float]:
    if not points:
        return (0.0, 0.0)
    # Representative point: use the lowest y-value point (top-most).
    # If multiple points share min y, use their average x.
    min_y = min(y for _, y in points)
    min_y_points = [(x, y) for x, y in points if y == min_y]
    rep_x = sum(x for x, _ in min_y_points) / len(min_y_points)
    rep_y = min_y
    return (rep_x, rep_y)


def _shape_type_from_shapes(shapes: list[dict[str, Any]]) -> str:
    if not shapes:
        return "point"
    shape_types = {str(shape.get("shape_type", "polygon")) for shape in shapes}
    return "point" if shape_types == {"point"} else "polygon"


def _maybe_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
