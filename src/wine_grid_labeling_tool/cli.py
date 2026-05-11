from __future__ import annotations

import argparse
from pathlib import Path

from .app import create_grid_csv, run_labeling_session


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wine-grid-labeler",
        description="Simple grid labeling CLI tool.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create an empty labeling CSV.")
    init_parser.add_argument("--rows", type=int, required=True, help="Number of rows.")
    init_parser.add_argument("--cols", type=int, required=True, help="Number of cols.")
    init_parser.add_argument(
        "--output",
        type=Path,
        default=Path("labels.csv"),
        help="Output CSV path (default: labels.csv).",
    )

    label_parser = subparsers.add_parser("label", help="Fill empty labels from terminal prompts.")
    label_parser.add_argument(
        "--input",
        type=Path,
        default=Path("labels.csv"),
        help="Input CSV path (default: labels.csv).",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "init":
        create_grid_csv(output_path=args.output, rows=args.rows, cols=args.cols)
        print(f"Created: {args.output}")
        return

    if args.command == "label":
        updated = run_labeling_session(input_path=args.input)
        print(f"Updated {updated} cell(s) in {args.input}")
        return

    parser.error("Unknown command")


if __name__ == "__main__":
    main()
