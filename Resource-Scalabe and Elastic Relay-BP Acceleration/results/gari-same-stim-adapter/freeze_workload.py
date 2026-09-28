#!/usr/bin/env python3
"""Inspect frozen artifacts; never sample a circuit or invoke a decoder."""
from __future__ import annotations

import csv
import hashlib
import json
import platform
import subprocess
from pathlib import Path

import numpy as np
import stim

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
PACKAGE = ROOT / "graphs/generated/gross_circuit_level/memory_Z_r12_p0p003"
CIRCUIT = PACKAGE / "circuit.stim"
DEM = PACKAGE / "detector_error_model.dem"
SAMPLES = ROOT / "results/circuit-level-multiseed/paired_samples.npz"
ARCHIVE = ROOT / "results/n1-vs-n2-hardware-latency/per_shot_results.csv"
EXPECTED_HASHES = {
    CIRCUIT: "839d2fa8ce95c62e32e2d465fb646a835e184be6ceca6e4b32f046f5c506cd20",
    DEM: "76eb991fc30617b4ac194978d5a6f9cdd382270c8c60b30fbb69535f865f9325",
    SAMPLES: "acc4290dd1ff30a7436a9b22fea2e5bb11238559be2506c111e8b2ce75e0eded",
    ARCHIVE: "4de985f1df5dda81abdd19a7198998ef1fc718d05abd207a2d418ed2f22f08f9",
    PACKAGE / "manifest.json": "c6eac5f571fc5f60a75f9f8ba99a78a24542a6aabecb6a56333f5f95acc74609",
    PACKAGE / "edge_lists.npz": "256b43714d9d257e95038520bac71ad38f207f0fb4cf8c18eeb5b1e74c6856ad",
    PACKAGE / "faults.npz": "6d741bfb9db734aad5f1cf36d9829b5f25bab2a0570b7599041ccf2896d7f390",
    PACKAGE / "detector_coordinates.npz": "06998d507af9fc852612ad0e795b43d64d53285fffc8d5d4abdb1038c19e68c7",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def packed_hash(bits: np.ndarray) -> str:
    return hashlib.sha256(np.packbits(bits, bitorder="big").tobytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def write_csv(path: Path, rows: list[dict]) -> None:
    require(bool(rows), f"Empty evidence table: {path}")
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def detector_lineage(circuit: stim.Circuit) -> list[dict]:
    """Resolve every detector record reference to its measurement gate/qubit.

    This circuit uses only single-qubit M/MX measurements. Unknown measurement
    types fail closed because the final record count is checked against Stim.
    No coordinate sorting or assumption about equal X/Z halves is used.
    """
    measurements = []
    records = []
    coordinates = circuit.get_detector_coordinates()
    basis_for_gate = {"M": "Z", "MX": "X", "MY": "Y", "MR": "Z", "MRX": "X", "MRY": "Y"}
    for instruction_index, instruction in enumerate(circuit.flattened()):
        if instruction.name in basis_for_gate:
            for target in instruction.targets_copy():
                require(target.is_qubit_target, "Unsupported measurement target")
                measurements.append({
                    "record_index": len(measurements),
                    "instruction_index": instruction_index,
                    "gate": instruction.name,
                    "qubit": target.value,
                    "basis": basis_for_gate[instruction.name],
                })
        elif instruction.name == "DETECTOR":
            references = instruction.targets_copy()
            require(all(t.is_measurement_record_target for t in references), "Unsupported detector target")
            offsets = [t.value for t in references]
            absolute_indices = [len(measurements) + offset for offset in offsets]
            require(all(0 <= index < len(measurements) for index in absolute_indices), "Detector record out of bounds")
            proof = [measurements[index] for index in absolute_indices]
            bases = sorted({item["basis"] for item in proof})
            require(len(bases) == 1, "Detector mixes measurement bases")
            detector_id = len(records)
            records.append({
                "raw_detector_id": detector_id,
                "basis": bases[0],
                "coordinates_json": json.dumps(coordinates[detector_id], separators=(",", ":")),
                "detector_instruction_index": instruction_index,
                "measurement_count_at_declaration": len(measurements),
                "rec_offsets_json": json.dumps(offsets, separators=(",", ":")),
                "absolute_record_indices_json": json.dumps(absolute_indices, separators=(",", ":")),
                "measurement_proof_json": json.dumps(proof, separators=(",", ":")),
            })
    require(len(measurements) == circuit.num_measurements, "Unrecognized measurements in circuit")
    require(len(records) == circuit.num_detectors, "Detector count mismatch")
    require(sum(row["basis"] == "Z" for row in records) == 936, "Unexpected Z detector count")
    require(sum(row["basis"] == "X" for row in records) == 792, "Unexpected X detector count")
    with np.load(PACKAGE / "detector_coordinates.npz", allow_pickle=False) as packaged:
        require(np.array_equal(packaged["coordinate_lengths"], np.ones(1728, dtype=np.int16)), "Unexpected coordinate lengths")
        require(np.array_equal(packaged["coordinates"], np.asarray([coordinates[i] for i in range(1728)])), "Packaged coordinate mismatch")
    return records


def main() -> None:
    verified_hashes = {}
    for path, expected in EXPECTED_HASHES.items():
        actual = sha256(path)
        require(actual == expected, f"Frozen SHA256 mismatch: {path}: {actual}")
        verified_hashes[relative(path)] = {"expected_sha256": expected, "actual_sha256": actual, "match": True}

    circuit = stim.Circuit.from_file(str(CIRCUIT))
    dem = stim.DetectorErrorModel.from_file(str(DEM))
    require((circuit.num_qubits, circuit.num_detectors, circuit.num_observables) == (288, 1728, 12), "Circuit dimensions changed")
    require((dem.num_detectors, dem.num_observables, dem.num_errors) == (1728, 12, 67752), "DEM dimensions changed")
    package_manifest = json.loads((PACKAGE / "manifest.json").read_text())
    sampling_manifest = json.loads((ROOT / "results/circuit-level-multiseed/manifest.json").read_text())
    n1_manifest = json.loads((ROOT / "results/n1-vs-n2-hardware-latency/manifest.json").read_text())
    joint_manifest = json.loads((ROOT / "results/canonical-n1-n2-n4-joint-sweep/archive_manifest.json").read_text())
    require(sampling_manifest["software"]["stim"] == "1.15.0", "Generation Stim version changed")
    require(n1_manifest["hashes"]["samples"] == EXPECTED_HASHES[SAMPLES], "Canonical N1/N2 sample manifest mismatch")
    require(joint_manifest["sample_hash"] == EXPECTED_HASHES[SAMPLES], "Canonical joint archive sample manifest mismatch")

    with np.load(SAMPLES, allow_pickle=False) as samples:
        syndromes = samples["syndromes"]
        labels = samples["observed_logicals"]
        seeds = samples["sample_seeds"]
        probabilities = samples["probabilities"]
    require(syndromes.shape == (5, 128, 1728) and syndromes.dtype == np.bool_, "Unexpected syndrome panel")
    require(labels.shape == (5, 128, 12) and labels.dtype == np.bool_, "Unexpected observable panel")
    require(seeds.tolist() == list(range(20260809, 20260814)), "Unexpected sampling seed panel")
    with np.load(PACKAGE / "faults.npz", allow_pickle=False) as faults:
        require(np.array_equal(probabilities, faults["probabilities"]), "Frozen sample static priors differ from DEM package")
    with np.load(PACKAGE / "edge_lists.npz", allow_pickle=False) as edges:
        require(edges["detector_edges"].shape == (391320, 2), "Detector incidence dimensions changed")
        require(edges["observable_edges"].shape == (110971, 2), "Observable incidence dimensions changed")

    with ARCHIVE.open(newline="") as stream:
        archived_rows = list(csv.DictReader(stream))
    keys = [(int(row["sample_seed"]), int(row["shot"])) for row in archived_rows]
    expected_keys = {(seed, shot) for seed in seeds[:4] for shot in range(32)}
    require(len(keys) == len(set(keys)) == 128 and set(keys) == expected_keys, "Canonical 128-shot selection changed")
    key_rows = []
    for row in archived_rows:
        seed, shot = int(row["sample_seed"]), int(row["shot"])
        sample_index = int(np.flatnonzero(seeds == seed)[0])
        detector_hash = packed_hash(syndromes[sample_index, shot])
        logical_hash = packed_hash(labels[sample_index, shot])
        require(detector_hash == row["detector_sample_hash"], f"Syndrome mismatch: {seed}/{shot}")
        require(logical_hash == row["logical_sample_hash"], f"Logical label mismatch: {seed}/{shot}")
        key_rows.append({
            "case_id": f"{seed}_{shot:03d}",
            "sample_seed": seed,
            "seed_index": sample_index,
            "shot": shot,
            "syndrome_weight": int(syndromes[sample_index, shot].sum()),
            "logical_label_weight": int(labels[sample_index, shot].sum()),
            "detector_sample_hash": detector_hash,
            "archived_detector_sample_hash": row["detector_sample_hash"],
            "logical_sample_hash": logical_hash,
            "archived_logical_sample_hash": row["logical_sample_hash"],
            "both_hashes_match": True,
        })
    key_rows.sort(key=lambda row: (row["sample_seed"], row["shot"]))
    lineage = detector_lineage(circuit)
    write_csv(OUT / "common_shot_keys.csv", key_rows)
    write_csv(OUT / "detector_lineage.csv", lineage)

    manifest = {
        "schema_version": 1,
        "status": "PASS",
        "scope": "Read-only verification of existing circuit, samples, canonical shot identities, and measurement lineage; no sampling or decoding",
        "ureca_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "circuit": {
            "path": relative(CIRCUIT), "sha256": EXPECTED_HASHES[CIRCUIT],
            "code": "[[144,12,12]]", "memory_basis": "Z", "noisy_qec_rounds": 12,
            "physical_error_probability": 0.003, "noise_model": "uniform_circuit",
            "final_perfect_measurement": True, "qubits": 288, "detectors": 1728, "observables": 12,
        },
        "dem": {
            "path": relative(DEM), "sha256": EXPECTED_HASHES[DEM], "fault_count": 67752,
            "H_shape": [1728, 67752], "A_shape": [12, 67752],
            "detector_incidence_count": 391320, "observable_incidence_count": 110971,
            "full_hypergraph_retained": True,
        },
        "sample_artifact": {
            "path": relative(SAMPLES), "sha256": EXPECTED_HASHES[SAMPLES],
            "stored_shots": 640, "stored_sample_seeds": seeds.tolist(), "shots_per_seed": 128,
            "syndrome_shape": list(syndromes.shape), "logical_label_shape": list(labels.shape),
            "generation_stim_version": sampling_manifest["software"]["stim"],
            "generation_manifest": "results/circuit-level-multiseed/manifest.json",
            "generation_project_commit": sampling_manifest["software"]["git_commit"],
            "generation_manifest_reported_dirty_worktree": sampling_manifest["software"]["git_worktree_dirty"],
            "sampling_protocol": "circuit.compile_detector_sampler(seed=seed).sample(128, separate_observables=True)",
            "regenerated": False,
        },
        "canonical_common_set": {
            "shots": 128, "sample_seeds": seeds[:4].tolist(), "shot_indices_per_seed": list(range(32)),
            "archived_results": relative(ARCHIVE), "archived_results_sha256": EXPECTED_HASHES[ARCHIVE],
            "selected_by": "All canonical N=1/N=2 archived (sample_seed,shot) keys; no outcome-based selection",
            "detector_hash_matches": 128, "logical_label_hash_matches": 128, "mismatches": 0,
            "row_hash_convention": "SHA256(np.packbits(bits, bitorder='big').tobytes())",
            "common_shot_keys": relative(OUT / "common_shot_keys.csv"),
            "common_shot_keys_sha256": sha256(OUT / "common_shot_keys.csv"),
            "canonical_joint_archive_validation": joint_manifest["validation"],
        },
        "detector_order": {
            "raw_order": "Stim DETECTOR declaration order; sampler columns saved unchanged",
            "basis_source": "Resolve each rec offset against the preceding measurement record and inspect actual M/MX instruction",
            "basis_counts": {"Z": 936, "X": 792},
            "coordinate_dimension": 1,
            "coordinate_sorting_applied": False,
            "lineage_path": relative(OUT / "detector_lineage.csv"),
            "lineage_sha256": sha256(OUT / "detector_lineage.csv"),
            "Z_raw_indices": [row["raw_detector_id"] for row in lineage if row["basis"] == "Z"],
            "X_raw_indices": [row["raw_detector_id"] for row in lineage if row["basis"] == "X"],
        },
        "priors": {
            "source": relative(PACKAGE / "faults.npz"), "count": 67752,
            "sample_artifact_probabilities_equal_package": True,
            "min_probability": float(probabilities.min()), "max_probability": float(probabilities.max()),
            "sampled_physical_errors_used": False,
        },
        "verified_input_hashes": verified_hashes,
        "inspection_environment": {"python": platform.python_version(), "stim": stim.__version__, "numpy": np.__version__},
        "script": {"path": relative(Path(__file__).resolve()), "sha256": sha256(Path(__file__))},
        "scope_notes": [
            "The primary common set is the 128-shot N=1/N=2 subset; the NPZ contains 640 stored shots.",
            "The package's 16-shot self-check at seed 20250617 is a separate panel and was not substituted.",
            "Logical labels are read only for provenance hash verification here, never passed to a decoder.",
            "No physical-error vector is loaded; no Relay-BP corrections or outcomes influence shot selection.",
        ],
    }
    (OUT / "common_workload_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (OUT / "provenance_notes.md").write_text("""# Frozen workload provenance

`freeze_workload.py` reads the existing committed artifacts, verifies their
SHA256 values, and writes evidence tables. It never calls a sampler or decoder.

## Canonical subset and full stored panel

The sample artifact is `results/circuit-level-multiseed/paired_samples.npz`.
It holds 640 shots: seeds 20260809–20260813, 128 shots per seed. The primary
common set is the **128 shots already used by canonical N=1/N=2**: seeds
20260809–20260812, shot indices 0–31. All 128 syndrome hashes and all 128
logical-label hashes match the canonical archive; there are zero mismatches.
`common_shot_keys.csv` retains both newly computed and archived hashes.
Selection uses archived shot keys only and does not inspect decoder outcomes.

Evidence (paths relative to the project directory):

- `results/n1-vs-n2-hardware-latency/run_study.py:14` names the circuit package
  and frozen sample artifact; lines 70–72 select the stored seed/shot panel.
- The same file's line 53 writes packed syndrome/logical hashes. Lines 38–44
  pass identical syndrome and static priors to both actual decoders; the
  logical label is used after `d.decode(priors,syndrome)` only for scoring.
- `results/n1-vs-n2-hardware-latency/manifest.json` records 128 shots, the four
  seeds, and the same sample artifact SHA256.
- `results/canonical-n1-n2-n4-joint-sweep/run_canonical_joint_sweep.py:50–68`
  selects the 128 archived keys and validates their syndrome/logical hashes.
- Its `archive_manifest.json` reports E0/E1/N2 exact agreement and zero
  mismatches. The common-workload manifest preserves that historical result.

## Circuit and generation version

The circuit is Gross [[144,12,12]], memory Z, 12 noisy QEC rounds, p=0.003,
uniform-circuit noise with final perfect measurement. The dimensions are
288 circuit qubits, 1,728 detectors, 12 observables, and 67,752 DEM faults.
The frozen full hypergraph DEM is retained; no graphlike decomposition occurs.

- `graphs/generated/gross_circuit_level/memory_Z_r12_p0p003/manifest.json:2–25`
  supplies circuit/noise/dimension metadata; lines 33–42 supply hashes.
- `results/circuit-level-multiseed/manifest.json:19–29` gives the original
  sample panel; lines 73–79 record **Stim 1.15.0** for generation. Its recorded
  generation commit had a dirty worktree; byte hashes freeze the artifacts.
- `results/circuit-level-multiseed/run_multiseed_validation.py:216–232` reads
  the exact circuit, samples with `separate_observables=True`, repeats each
  fixed seed to check determinism, and saves the arrays without reordering.
- The inspection environment is separately recorded; no claim is made that
  a current Stim version would reproduce old samples by resampling.

The package's own 16-shot seed-20250617 self-check is a different dataset.
It is not used as the common panel.

## Detector declaration order and measurement lineage

Raw columns are Stim DETECTOR declaration order. `detector_lineage.csv`
resolves every raw detector's `rec[...]` offsets to absolute measurement
record indices, measurement gate names, physical qubits, and flattened
instruction indices. Basis follows the actual referenced M/MX instructions;
all 1,728 detector records use a single measurement basis.

- Z/M detectors: raw 0–71; 72+144k through 143+144k for k=0..10;
  and raw 1656–1727. Total **936**.
- X/MX detectors: raw 144+144k through 215+144k for k=0..10. Total **792**.

Coordinates are one-dimensional and are not sorted raw IDs. The consecutive
72-detector blocks start with coordinate ranges 72–143, 288–359, 216–287,
504–575, 432–503, and end 2448–2519, 2376–2447, 2664–2735. No coordinate
sorting or equal-halves X/Z assumption is valid. The packaged coordinate
array is checked against the circuit's own detector-coordinate map.

`circuit.stim:24549` begins raw detector 0, `DETECTOR(72) rec[-1872]`.
Its measurement is M qubit 216. Raw detector 144 references MX qubit 144.
The final Z block refers to six final data M outcomes and one ancilla M
outcome per detector. These facts come from static circuit lineage only.

## Inspection command

From the project directory:

```sh
../.venv/bin/python results/gari-same-stim-adapter/freeze_workload.py
```

No circuit or sample artifact is modified or regenerated by this script.
""")
    print(json.dumps({"status": "PASS", "canonical_shots": 128, "stored_shots": 640,
                      "syndrome_and_label_hash_mismatches": 0, "detector_lineage_records": 1728,
                      "outputs": ["common_workload_manifest.json", "common_shot_keys.csv", "detector_lineage.csv", "provenance_notes.md"]}, indent=2))


if __name__ == "__main__":
    main()
