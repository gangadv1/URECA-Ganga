#!/usr/bin/env python3
"""Construct a deterministic scorer-only logical-kernel witness.

Reads frozen static DEM incidence data only. Does not load a sampled syndrome,
logical label, decoder, correction, or physical-error realization.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
PACKAGE = PROJECT / "graphs/generated/gross_circuit_level/memory_Z_r12_p0p003"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mask(indices) -> int:
    value = 0
    for index in indices:
        value ^= 1 << int(index)
    return value


def support(value: int) -> list[int]:
    result = []
    while value:
        bit = value & -value
        result.append(bit.bit_length() - 1)
        value ^= bit
    return result


def construct() -> dict:
    with np.load(PACKAGE / "faults.npz", allow_pickle=False) as frozen:
        di = frozen["detector_indptr"]
        dr = frozen["detector_indices"]
        oi = frozen["observable_indptr"]
        lr = frozen["observable_indices"]
    package = json.loads((PACKAGE / "package.json").read_text())
    pivots: dict[int, tuple[int, int, int]] = {}
    dependencies_examined = 0
    witness = 0
    logical_mask = 0
    for column in range(len(di) - 1):
        detector_mask = mask(dr[di[column] : di[column + 1]])
        action = mask(lr[oi[column] : oi[column + 1]])
        combination = 1 << column
        while detector_mask:
            pivot = detector_mask.bit_length() - 1
            if pivot not in pivots:
                pivots[pivot] = (detector_mask, action, combination)
                break
            old_detector, old_action, old_combination = pivots[pivot]
            detector_mask ^= old_detector
            action ^= old_action
            combination ^= old_combination
        if detector_mask == 0:
            dependencies_examined += 1
            if action:
                witness, logical_mask = combination, action
                break
    if not witness:
        raise RuntimeError("No nontrivial logical kernel witness in frozen DEM")

    columns = support(witness)
    syndrome = 0
    logical = 0
    for column_index in columns:
        syndrome ^= mask(dr[di[column_index] : di[column_index + 1]])
        logical ^= mask(lr[oi[column_index] : oi[column_index + 1]])
    assert syndrome == 0 and logical == logical_mask and logical != 0

    # Independently verify using the separate frozen edge-list artifact.
    with np.load(PACKAGE / "edge_lists.npz", allow_pickle=False) as frozen:
        detector_edges = frozen["detector_edges"]
        observable_edges = frozen["observable_edges"]
    selected = np.zeros(package["fault_count"], dtype=np.bool_)
    selected[columns] = True
    detector_sum = np.bincount(
        detector_edges[selected[detector_edges[:, 0]], 1],
        minlength=package["detector_count"],
    ) % 2
    logical_sum = np.bincount(
        observable_edges[selected[observable_edges[:, 0]], 1],
        minlength=package["observable_count"],
    ) % 2
    assert not detector_sum.any()
    assert mask(np.flatnonzero(logical_sum)) == logical
    return {
        "status": "PASS",
        "purpose": "Scorer-only negative fixture; never a decoder input or repair",
        "algorithm": "Ascending original DEM columns; GF(2) elimination at highest set detector bit; stop at first zero-detector dependency with nonzero logical action",
        "inputs": {
            name: {"path": str((PACKAGE / name).relative_to(PROJECT)), "sha256": sha256(PACKAGE / name)}
            for name in ("faults.npz", "edge_lists.npz", "package.json")
        },
        "sample_artifacts_read": [],
        "decoder_invocations": 0,
        "fault_count": int(package["fault_count"]),
        "detector_count": int(package["detector_count"]),
        "observable_count": int(package["observable_count"]),
        "columns_examined": int(column + 1),
        "detector_rank_at_stop": len(pivots),
        "dependencies_examined": dependencies_examined,
        "support_indices": columns,
        "support_weight": len(columns),
        "logical_mask_integer": logical,
        "logical_support_indices": support(logical),
        "logical_vector": logical_sum.astype(int).tolist(),
        "proof": {
            "fault_incidence_detector_residual_weight": 0,
            "edge_list_detector_residual_weight": int(detector_sum.sum()),
            "edge_list_logical_action_weight": int(logical_sum.sum()),
            "independent_artifacts_agree": True,
            "zero_syndrome_zero_label_expected": {
                "syndrome_valid": True,
                "logical_action_match": False,
                "logically_correct": False,
            },
        },
    }


if __name__ == "__main__":
    evidence = construct()
    output = HERE / "logical_kernel_witness.json"
    output.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps({key: evidence[key] for key in (
        "status", "support_weight", "logical_mask_integer", "columns_examined", "detector_rank_at_stop"
    )}, sort_keys=True))
