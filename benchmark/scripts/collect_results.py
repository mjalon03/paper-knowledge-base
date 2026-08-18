"""Create one evaluator-friendly directory from per-document normalized results."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for result_path in sorted(args.input_dir.glob("*/normalized/*.json")):
        shutil.copy2(result_path, args.output_dir / result_path.name)


if __name__ == "__main__":
    main()
