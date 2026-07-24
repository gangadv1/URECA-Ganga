"""Build the gross-code parity-check matrices."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np


ELL = 12
M_DIM = 6
CELL_COUNT = ELL * M_DIM
QUBIT_COUNT = 2 * CELL_COUNT
A_TERMS = ((3, 0), (0, 1), (0, 2))
B_TERMS = ((0, 3), (1, 0), (2, 0))


@dataclass(frozen=True)
class GrossCodeSummary:
    code_name: str
    n: int
    k: int
    d: int
    ell: int
    m: int
    hx_shape: tuple[int, int]
    hz_shape: tuple[int, int]
    hx_row_weight_min: int
    hx_row_weight_max: int
    hz_row_weight_min: int
    hz_row_weight_max: int
    hx_col_weight_min: int
    hx_col_weight_max: int
    hz_col_weight_min: int
    hz_col_weight_max: int
    commute: bool
    content_hash: str


def cell_index(x: int, y: int) -> int:
    return (x % ELL) * M_DIM + (y % M_DIM)


def build_block(terms: tuple[tuple[int, int], ...]) -> np.ndarray:
    """Build one 72 by 72 circulant block."""
    block = np.zeros((CELL_COUNT, CELL_COUNT), dtype=np.uint8)
    for x in range(ELL):
        for y in range(M_DIM):
            row = cell_index(x, y)
            for dx, dy in terms:
                col = cell_index(x + dx, y + dy)
                block[row, col] ^= 1
    return block


def build_matrices() -> tuple[np.ndarray, np.ndarray]:
    """Return `Hx` and `Hz` for the gross code."""
    a_block = build_block(A_TERMS)
    b_block = build_block(B_TERMS)
    hx = np.concatenate([a_block, b_block], axis=1)
    hz = np.concatenate([b_block.T, a_block.T], axis=1)
    return hx.astype(np.uint8), hz.astype(np.uint8)


def content_hash(hx: np.ndarray, hz: np.ndarray) -> str:
    digest = hashlib.sha256()
    digest.update(b"gross-code-v1")
    digest.update(hx.tobytes())
    digest.update(hz.tobytes())
    return digest.hexdigest()


def matrices_commute(hx: np.ndarray, hz: np.ndarray) -> bool:
    return bool(np.all((hx @ hz.T) % 2 == 0))


def summarize(hx: np.ndarray, hz: np.ndarray) -> GrossCodeSummary:
    hx_rows = hx.sum(axis=1)
    hz_rows = hz.sum(axis=1)
    hx_cols = hx.sum(axis=0)
    hz_cols = hz.sum(axis=0)
    return GrossCodeSummary(
        code_name="gross [[144,12,12]]",
        n=144,
        k=12,
        d=12,
        ell=ELL,
        m=M_DIM,
        hx_shape=tuple(int(v) for v in hx.shape),
        hz_shape=tuple(int(v) for v in hz.shape),
        hx_row_weight_min=int(hx_rows.min()),
        hx_row_weight_max=int(hx_rows.max()),
        hz_row_weight_min=int(hz_rows.min()),
        hz_row_weight_max=int(hz_rows.max()),
        hx_col_weight_min=int(hx_cols.min()),
        hx_col_weight_max=int(hx_cols.max()),
        hz_col_weight_min=int(hz_cols.min()),
        hz_col_weight_max=int(hz_cols.max()),
        commute=matrices_commute(hx, hz),
        content_hash=content_hash(hx, hz),
    )


def write_outputs(out_dir: Path) -> GrossCodeSummary:
    hx, hz = build_matrices()
    summary = summarize(hx, hz)
    if not summary.commute:
        raise RuntimeError("Hx and Hz do not commute")

    out_dir.mkdir(parents=True, exist_ok=True)
    np.savetxt(out_dir / "hx.csv", hx, fmt="%d", delimiter=",")
    np.savetxt(out_dir / "hz.csv", hz, fmt="%d", delimiter=",")
    (out_dir / "summary.json").write_text(json.dumps(asdict(summary), indent=2) + "\n", encoding="utf-8")
    (out_dir / "logical_masks.json").write_text(
        json.dumps(
            {
                "status": "placeholder",
                "note": "Logical masks are needed before headline logical-error results.",
                "masks": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build gross-code Hx and Hz matrices")
    parser.add_argument("--out-dir", type=Path, default=Path(__file__).resolve().parent / "generated" / "gross_code")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    summary = write_outputs(args.out_dir)
    print(f"Wrote gross-code matrices to {args.out_dir}")
    print(f"Hx shape: {summary.hx_shape}")
    print(f"Hz shape: {summary.hz_shape}")
    print(f"Commute: {summary.commute}")
    print(f"Hash: {summary.content_hash}")


if __name__ == "__main__":
    main()

