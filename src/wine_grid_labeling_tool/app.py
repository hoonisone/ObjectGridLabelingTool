from __future__ import annotations

import csv
from pathlib import Path


def create_grid_csv(output_path: Path, rows: int, cols: int) -> None:
    if rows <= 0 or cols <= 0:
        raise ValueError("rows and cols must be positive integers.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["row", "col", "label"])
        writer.writeheader()
        for row in range(1, rows + 1):
            for col in range(1, cols + 1):
                writer.writerow({"row": row, "col": col, "label": ""})


def run_labeling_session(input_path: Path) -> int:
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    with input_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    required_columns = {"row", "col", "label"}
    if not rows and reader.fieldnames is None:
        raise ValueError("Input CSV is empty.")
    if reader.fieldnames is None or not required_columns.issubset(set(reader.fieldnames)):
        raise ValueError("Input CSV must contain columns: row, col, label")

    updated_count = 0
    for record in rows:
        current = (record.get("label") or "").strip()
        if current:
            continue

        row = record.get("row", "?")
        col = record.get("col", "?")
        value = input(f"Label for cell (row={row}, col={col}): ").strip()
        record["label"] = value
        updated_count += 1

    with input_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["row", "col", "label"])
        writer.writeheader()
        writer.writerows(rows)

    return updated_count
