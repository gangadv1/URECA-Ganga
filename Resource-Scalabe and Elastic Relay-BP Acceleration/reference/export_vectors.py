"""Export small integer vectors for RTL unit tests."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
for path in (CURRENT_DIR, PROJECT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from configs.manifest import ManifestConfig, write_manifest  # noqa: E402
from fixedpoint import FixedConfig, check_node_update, memory_mix, round_div_power_of_two, sat_b  # noqa: E402


def write_vectors(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    config = FixedConfig(b=4, g=2, M=8, clip=7)
    path = out_dir / "directed_vectors.csv"
    rows = [
        {"name": "sat_high", "input": "100", "expected": sat_b(100, config)},
        {"name": "sat_low", "input": "-100", "expected": sat_b(-100, config)},
        {"name": "round_pos_half", "input": "1/2", "expected": round_div_power_of_two(1, 1)},
        {"name": "round_neg_half", "input": "-1/2", "expected": round_div_power_of_two(-1, 1)},
        {"name": "memory_beta_zero", "input": "prev=3,new=-5,beta=0", "expected": memory_mix(3, -5, 0, config)},
        {"name": "memory_beta_full", "input": "prev=3,new=-5,beta=8", "expected": memory_mix(3, -5, 8, config)},
        {"name": "memory_beta_half", "input": "prev=3,new=-5,beta=4", "expected": memory_mix(3, -5, 4, config)},
        {"name": "check_node_equal", "input": "[3,-3,3],syn=0", "expected": " ".join(map(str, check_node_update([3, -3, 3], 0, config)))},
    ]
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["name", "input", "expected"])
        writer.writeheader()
        writer.writerows(rows)
    return [path]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export small fixed-point vectors")
    parser.add_argument("--out-dir", type=Path, default=PROJECT_ROOT / "verification" / "vectors")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    artifacts = write_vectors(args.out_dir)
    write_manifest(
        ManifestConfig(
            arithmetic={"b": 4, "g": 2, "M": 8, "clip": 7, "rounding": "nearest ties away from zero"},
            experiment={"purpose": "directed fixed-point vectors"},
        ),
        args.out_dir,
        artifact_paths=artifacts,
    )
    print(f"Wrote vectors to {args.out_dir}")


if __name__ == "__main__":
    main()

