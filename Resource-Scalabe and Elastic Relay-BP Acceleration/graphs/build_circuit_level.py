"""Build reproducible Tier-2 circuit-level bicycle-bivariate STIM packages."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import numpy as np

try:
    import stim
except ModuleNotFoundError as error:  # pragma: no cover - exercised by CLI users
    raise SystemExit("STIM is required: install the 'stim' Python package") from error


CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
REPO_ROOT = PROJECT_ROOT.parent
UPSTREAM_COMMIT = "d185194ba0cb4101ced4340d82b2ee6d42f225f0"
UPSTREAM_REPOSITORY = "https://github.com/trmue/relay"
DEFAULT_P = 0.003
DEFAULT_ROUNDS = 12
DEFAULT_SHOTS = 16
DEFAULT_SEED = 20250617

BB_CODES = {
    "18_4_3": {
        "n": 18, "k": 4, "d": 3, "rounds": 3,
        "source_prefix": "bb_18_4_3",
        "A": "x+1+y", "B": "x+1+xy^2",
    },
    "72_12_6": {
        "n": 72, "k": 12, "d": 6, "rounds": 6,
        "source_prefix": "bb_72_12_6",
        "A": "x^3+y+y^2", "B": "y^3+x+x^2",
    },
    "144_12_12": {
        "n": 144, "k": 12, "d": 12, "rounds": 12,
        "source_prefix": "gross_144_12_12",
        "A": "x^3+y+y^2", "B": "y^3+x+x^2",
    },
    "288_12_18": {
        "n": 288, "k": 12, "d": 18, "rounds": 18,
        "source_prefix": "bb_288_12_18",
        "A": "x^3+y^2+y^7", "B": "y^3+x+x^2",
    },
}
DEFAULT_CODE = "144_12_12"


def probability_label(probability: float) -> str:
    return format(probability, ".12g")


def default_source(code: str, probability: float) -> Path:
    cfg = BB_CODES[code]
    label = probability_label(probability)
    return (
        CURRENT_DIR / "sources" / "relay_official" / "bicycle_bivariate"
        / f"{cfg['source_prefix']}_memory_Z_r{cfg['rounds']}_p{label}.stim"
    )


def default_output(code: str, probability: float) -> Path:
    cfg = BB_CODES[code]
    label = probability_label(probability).replace(".", "p")
    directory = "gross_circuit_level" if code == "144_12_12" else f"bb_{code}_circuit_level"
    return (
        CURRENT_DIR / "generated" / directory
        / f"memory_Z_r{cfg['rounds']}_p{label}"
    )


def upstream_source_path(code: str, probability: float) -> str:
    cfg = BB_CODES[code]
    label = probability_label(probability)
    return "tests/testdata/bicycle_bivariate/" + (
        f"circuit=bicycle_bivariate_{code}_memory_Z,"
        f"distance={cfg['d']},rounds={cfg['rounds']},"
        f"error_rate={label},noise_model=uniform_circuit,basis=CX,"
        f"A={cfg['A']},B={cfg['B']}.stim"
    )

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_blob_sha1(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip()


def extract_faults(dem: stim.DetectorErrorModel) -> tuple[np.ndarray, list[list[int]], list[list[int]], np.ndarray]:
    probabilities: list[float] = []
    detector_targets: list[list[int]] = []
    observable_targets: list[list[int]] = []
    separator_counts: list[int] = []
    for instruction in dem:
        if instruction.type != "error":
            continue
        args = instruction.args_copy()
        if len(args) != 1:
            raise RuntimeError(f"Unexpected DEM error arguments: {instruction}")
        detectors: set[int] = set()
        observables: set[int] = set()
        separators = 0
        for target in instruction.targets_copy():
            if target.is_relative_detector_id():
                detectors.symmetric_difference_update((target.val,))
            elif target.is_logical_observable_id():
                observables.symmetric_difference_update((target.val,))
            elif target.is_separator():
                separators += 1
            else:
                raise RuntimeError(f"Unsupported DEM target in: {instruction}")
        probabilities.append(float(args[0]))
        detector_targets.append(sorted(detectors))
        observable_targets.append(sorted(observables))
        separator_counts.append(separators)
    return (
        np.asarray(probabilities, dtype=np.float64),
        detector_targets,
        observable_targets,
        np.asarray(separator_counts, dtype=np.int16),
    )


def to_csr_rows(rows: list[list[int]]) -> tuple[np.ndarray, np.ndarray]:
    indptr = np.zeros(len(rows) + 1, dtype=np.int64)
    if rows:
        indptr[1:] = np.cumsum([len(row) for row in rows], dtype=np.int64)
    indices = np.fromiter((value for row in rows for value in row), dtype=np.int32, count=int(indptr[-1]))
    return indptr, indices


def incidence_edges(rows: list[list[int]]) -> np.ndarray:
    count = sum(len(row) for row in rows)
    edges = np.empty((count, 2), dtype=np.int32)
    cursor = 0
    for fault, targets in enumerate(rows):
        end = cursor + len(targets)
        if end > cursor:
            edges[cursor:end, 0] = fault
            edges[cursor:end, 1] = targets
        cursor = end
    return edges


def detector_coordinate_array(circuit: stim.Circuit) -> tuple[np.ndarray, np.ndarray]:
    coordinates = circuit.get_detector_coordinates()
    lengths = np.asarray([len(coordinates.get(index, [])) for index in range(circuit.num_detectors)], dtype=np.int16)
    width = int(lengths.max(initial=0))
    values = np.full((circuit.num_detectors, width), np.nan, dtype=np.float64)
    for index in range(circuit.num_detectors):
        coordinate = coordinates.get(index, [])
        values[index, : len(coordinate)] = coordinate
    return values, lengths


def write_incidence(
    path: Path,
    probabilities: np.ndarray,
    detector_targets: list[list[int]],
    observable_targets: list[list[int]],
    separator_counts: np.ndarray,
) -> None:
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(["fault_index", "probability", "detectors", "observables", "separator_count"])
        for index, probability in enumerate(probabilities):
            writer.writerow(
                [
                    index,
                    format(float(probability), ".17g"),
                    " ".join(map(str, detector_targets[index])),
                    " ".join(map(str, observable_targets[index])),
                    int(separator_counts[index]),
                ]
            )


def validate_source(
    circuit: stim.Circuit,
    source_path: Path,
    code: str,
    probability: float,
    rounds: int,
) -> dict[str, Any]:
    cfg = BB_CODES[code]

    if rounds != cfg["rounds"]:
        raise ValueError(
            f"Code [[{cfg['n']},{cfg['k']},{cfg['d']}]] requires "
            f"{cfg['rounds']} rounds in the pinned official Relay source; got {rounds}."
        )

    filename_match = re.search(r"_r(\d+)_p([0-9.]+)\.stim$", source_path.name)
    if filename_match:
        source_rounds = int(filename_match.group(1))
        source_probability = float(filename_match.group(2))
        if source_rounds != rounds or not np.isclose(
            source_probability, probability, rtol=0, atol=1e-15
        ):
            raise ValueError(
                "Requested parameters do not match the source circuit filename"
            )

    if circuit.num_observables != cfg["k"]:
        raise ValueError(
            f"Expected {cfg['k']} logical observables for [[{cfg['n']},{cfg['k']},{cfg['d']}]], "
            f"got {circuit.num_observables}"
        )

    flattened = list(circuit.flattened())
    noisy_gate_names = {
        "X_ERROR",
        "Y_ERROR",
        "Z_ERROR",
        "DEPOLARIZE1",
        "DEPOLARIZE2",
        "M",
        "MX",
        "MY",
        "MR",
        "MRX",
        "MRY",
    }
    noisy_instructions = [
        instruction
        for instruction in flattened
        if instruction.name in noisy_gate_names and instruction.gate_args_copy()
    ]
    noise_values = sorted({float(value) for instruction in noisy_instructions for value in instruction.gate_args_copy()})
    if noise_values != [probability]:
        raise ValueError(f"Source circuit noise values {noise_values} do not match requested p={probability}")
    perfect_measurements = [instruction for instruction in flattened if "disable_noise" in str(instruction)]
    return {
        "has_final_noise_disabled_measurement": bool(perfect_measurements),
        "final_noise_disabled_measurement_count": len(perfect_measurements),
        "noisy_instruction_count": len(noisy_instructions),
        "noise_probability_values": noise_values,
        "tick_count": circuit.num_ticks,
    }


def sample_and_verify(
    circuit: stim.Circuit,
    dem: stim.DetectorErrorModel,
    detector_targets: list[list[int]],
    observable_targets: list[list[int]],
    shots: int,
    seed: int,
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    def circuit_sample() -> tuple[np.ndarray, np.ndarray]:
        return circuit.compile_detector_sampler(seed=seed).sample(shots, separate_observables=True)

    circuit_detectors, circuit_observables = circuit_sample()
    repeat_detectors, repeat_observables = circuit_sample()
    if not np.array_equal(circuit_detectors, repeat_detectors) or not np.array_equal(circuit_observables, repeat_observables):
        raise RuntimeError("Circuit sampling was not reproducible for a fixed seed")

    def dem_sample() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        return dem.compile_sampler(seed=seed).sample(shots, return_errors=True)

    dem_detectors, dem_observables, dem_faults = dem_sample()
    repeat_dem_detectors, repeat_dem_observables, repeat_dem_faults = dem_sample()
    if not all(
        np.array_equal(left, right)
        for left, right in zip(
            (dem_detectors, dem_observables, dem_faults),
            (repeat_dem_detectors, repeat_dem_observables, repeat_dem_faults),
        )
    ):
        raise RuntimeError("DEM sampling was not reproducible for a fixed seed")

    detector_edges = incidence_edges(detector_targets)
    observable_edges = incidence_edges(observable_targets)
    reconstructed_detectors = np.zeros_like(dem_detectors)
    reconstructed_observables = np.zeros_like(dem_observables)
    for fault, detector in detector_edges:
        reconstructed_detectors[:, detector] ^= dem_faults[:, fault]
    for fault, observable in observable_edges:
        reconstructed_observables[:, observable] ^= dem_faults[:, fault]
    if not np.array_equal(dem_detectors, reconstructed_detectors):
        raise RuntimeError("Extracted detector incidence does not reproduce DEM samples")
    if not np.array_equal(dem_observables, reconstructed_observables):
        raise RuntimeError("Extracted logical incidence does not reproduce DEM samples")

    return (
        {"detectors": circuit_detectors, "observables": circuit_observables},
        {"detectors": dem_detectors, "observables": dem_observables, "faults": dem_faults},
    )


def validate_parameterized_source(circuit, construction, probability, rounds):
    """Validate the explicit existing GARI/Gong three-term memory-Z profile."""
    if construction.get("noise_model") != "gari_uniform_p_memory_z":
        raise ValueError("Unsupported parameterized circuit noise profile")
    n, k = construction["n"], construction["k"]
    if (circuit.num_qubits, circuit.num_observables, circuit.num_detectors) != (2*n, k, (n//2)*(rounds+1)):
        raise ValueError("Parameterized circuit/code/round dimensions disagree")
    instructions = list(circuit.flattened())
    noisy = [i for i in instructions if i.name in {"X_ERROR", "Z_ERROR", "DEPOLARIZE1", "DEPOLARIZE2"}]
    values = sorted({v for i in noisy for v in i.gate_args_copy()})
    if values != [probability]:
        raise ValueError("Generated circuit does not match physical p")
    # Existing generator measures all data perfectly after its noisy rounds.
    last_measurement = [i for i in instructions if i.name == "M"]
    if not last_measurement or len(last_measurement[-1].targets_copy()) != n or last_measurement[-1].gate_args_copy():
        raise ValueError("Expected final perfect data measurement")
    circuit.detector_error_model(decompose_errors=False, flatten_loops=True)
    return dict(has_final_noise_disabled_measurement=True,
                final_noise_disabled_measurement_count=1, noisy_instruction_count=len(noisy),
                noise_probability_values=values, tick_count=circuit.num_ticks,
                final_measurement_convention="noiseless M on all data; no disable_noise annotation",
                generator_profile="existing GARI/Gong memory-Z; not canonical Relay uniform_circuit")


def write_package(source_path: Path, out_dir: Path, code: str, probability: float, rounds: int, shots: int, seed: int, *, construction: dict[str, Any] | None = None) -> Path:
    source_path = source_path.resolve()
    out_dir = out_dir.resolve()

    if not source_path.exists():
        raise FileNotFoundError(
            f"No audited source circuit for p={probability}: {source_path}. "
            "Provide --source-circuit; do not rescale compiled circuit probabilities."
        )
    circuit = stim.Circuit.from_file(str(source_path))
    if construction is None:
        source_validation = validate_source(circuit, source_path, code, probability, rounds)
    else:
        if out_dir.exists():
            raise FileExistsError("Parameterized packages require a fresh output directory")
        source_validation = validate_parameterized_source(circuit, construction, probability, rounds)
    dem = circuit.detector_error_model(decompose_errors=False, flatten_loops=True)
    probabilities, detector_targets, observable_targets, separator_counts = extract_faults(dem)
    if len(probabilities) != dem.num_errors:
        raise RuntimeError("Fault extraction count differs from STIM DEM error count")

    circuit_samples, dem_samples = sample_and_verify(
        circuit, dem, detector_targets, observable_targets, shots, seed
    )
    detector_indptr, detector_indices = to_csr_rows(detector_targets)
    observable_indptr, observable_indices = to_csr_rows(observable_targets)
    detector_edges = incidence_edges(detector_targets)
    observable_edges = incidence_edges(observable_targets)
    detector_coordinates, detector_coordinate_lengths = detector_coordinate_array(circuit)

    out_dir.mkdir(parents=True, exist_ok=True)
    circuit_path = out_dir / "circuit.stim"
    dem_path = out_dir / "detector_error_model.dem"
    faults_path = out_dir / "faults.npz"
    edges_path = out_dir / "edge_lists.npz"
    coordinates_path = out_dir / "detector_coordinates.npz"
    incidence_path = out_dir / "incidence.csv"
    circuit_samples_path = out_dir / "circuit_samples.npz"
    dem_samples_path = out_dir / "dem_samples.npz"
    package_path = out_dir / "package.json"
    manifest_path = out_dir / "manifest.json"

    shutil.copyfile(source_path, circuit_path)
    dem_path.write_text(str(dem) + "\n", encoding="utf-8")
    np.savez_compressed(
        faults_path,
        probabilities=probabilities,
        detector_indptr=detector_indptr,
        detector_indices=detector_indices,
        observable_indptr=observable_indptr,
        observable_indices=observable_indices,
        separator_counts=separator_counts,
    )
    np.savez_compressed(edges_path, detector_edges=detector_edges, observable_edges=observable_edges)
    np.savez_compressed(
        coordinates_path,
        coordinates=detector_coordinates,
        coordinate_lengths=detector_coordinate_lengths,
    )
    write_incidence(incidence_path, probabilities, detector_targets, observable_targets, separator_counts)
    np.savez_compressed(circuit_samples_path, **circuit_samples)
    np.savez_compressed(dem_samples_path, **dem_samples)

    artifact_paths = [
        circuit_path,
        dem_path,
        faults_path,
        edges_path,
        coordinates_path,
        incidence_path,
        circuit_samples_path,
        dem_samples_path,
    ]
    cfg = BB_CODES[code] if construction is None else construction

    package = {
        "tier": "tier-2-circuit-level",
        "loader_contract_version": 1,
        "code": "gross_144_12_12" if code == "144_12_12" else f"bb_{code}",
        "code_parameters": {
            "n": cfg["n"],
            "k": cfg["k"],
            "d": cfg["d"],
        },
        "memory_basis": "Z",
        "rounds": rounds,
        "noisy_rounds": rounds,
        "final_perfect_measurement": source_validation["has_final_noise_disabled_measurement"],
        "physical_error_probability": probability,
        "qubit_count": circuit.num_qubits,
        "detector_count": dem.num_detectors,
        "fault_count": dem.num_errors,
        "observable_count": dem.num_observables,
        "detector_edge_count": int(len(detector_edges)),
        "logical_edge_count": int(len(observable_edges)),
        "max_detector_fault_degree": max(map(len, detector_targets), default=0),
        "max_logical_fault_degree": max(map(len, observable_targets), default=0),
        "sample_shots": shots,
        "sample_seed": seed,
        "logical_masks_available": dem.num_observables > 0 and len(observable_edges) > 0,
        "files": {path.stem: path.name for path in artifact_paths},
    }
    if construction is not None:
        package["construction"] = construction
        package["noise_model"] = construction["noise_model"]
    package_path.write_text(json.dumps(package, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    artifact_paths.append(package_path)
    manifest = {
        "schema_version": 1,
        "graph": {
            "code": f"BB [[{cfg['n']},{cfg['k']},{cfg['d']}]]",
            "tier": "tier-2-circuit-level",
            "detector_count": dem.num_detectors,
            "fault_count": dem.num_errors,
            "observable_count": dem.num_observables,
            "detector_edge_count": int(len(detector_edges)),
            "logical_edge_count": int(len(observable_edges)),
            "detector_incidence_sha256": sha256_file(edges_path),
        },
        "circuit": {
            "memory_basis": "Z",
            "noisy_qec_rounds": rounds,
            "final_perfect_measurement": source_validation["has_final_noise_disabled_measurement"],
            "physical_error_probability": probability,
            "noise_model": "uniform_circuit" if construction is None else construction["noise_model"],
            "stim_version": stim.__version__,
            **source_validation,
        },
        "sampling": {
            "shots": shots,
            "seed": seed,
            "circuit_detector_shape": list(circuit_samples["detectors"].shape),
            "circuit_observable_shape": list(circuit_samples["observables"].shape),
            "dem_fault_shape": list(dem_samples["faults"].shape),
            "fixed_seed_reproducible": True,
            "extracted_incidence_verified_against_dem_samples": True,
        },
        "provenance": {
            "project_git_commit": git_commit(),
            "upstream_repository": UPSTREAM_REPOSITORY if construction is None else None,
            "upstream_commit": UPSTREAM_COMMIT if construction is None else None,
            "upstream_source_path": upstream_source_path(code, probability) if construction is None else None,
            "upstream_source_blob_sha1": git_blob_sha1(source_path),
            "source_circuit_sha256": sha256_file(source_path),
            "artifact_hashes": {path.name: sha256_file(path) for path in artifact_paths},
            "artifact_paths": [
                path.relative_to(PROJECT_ROOT).as_posix()
                if path.is_relative_to(PROJECT_ROOT)
                else path.relative_to(out_dir).as_posix()
                for path in artifact_paths
            ],
        },
        "notes": [
            "The exact full hypergraph DEM is retained; no graphlike decomposition was forced.",
            "Logical masks are the fault-to-observable incidence in faults.npz and edge_lists.npz.",
            "This package is separate from and does not replace the Tier-1 package.",
        ],
    }
    if construction is not None:
        manifest["construction"] = construction
        manifest["graph"]["code"] = f"BB [[{cfg['n']},{cfg['k']}]] (distance unknown)"
        manifest["provenance"]["generated_source_blob_sha1"] = manifest["provenance"].pop("upstream_source_blob_sha1")
        manifest["provenance"]["generator_sources"] = construction["generator_sources"]
    if not out_dir.is_relative_to(PROJECT_ROOT):
        # External packages remain relocatable: paths resolve beside manifest.json.
        manifest["provenance"]["artifact_path_base"] = "manifest_directory"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a Tier-2 bicycle-bivariate circuit-level STIM/DEM package"
    )
    parser.add_argument(
        "--code",
        choices=sorted(BB_CODES),
        default=DEFAULT_CODE,
        help="BB code as n_k_d",
    )
    parser.add_argument("--probability", type=float, default=DEFAULT_P)
    parser.add_argument("--rounds", type=int)
    parser.add_argument("--shots", type=int, default=DEFAULT_SHOTS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--source-circuit", type=Path)
    parser.add_argument("--out-dir", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()

    if not 0 < args.probability < 1:
        raise SystemExit("--probability must be between 0 and 1")
    if args.shots <= 0:
        raise SystemExit("--shots must be positive")

    cfg = BB_CODES[args.code]
    rounds = args.rounds if args.rounds is not None else cfg["rounds"]

    source_path = args.source_circuit or default_source(
        args.code, args.probability
    )
    out_dir = args.out_dir or default_output(
        args.code, args.probability
    )

    manifest_path = write_package(
        source_path,
        out_dir,
        args.code,
        args.probability,
        rounds,
        args.shots,
        args.seed,
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    print(f"Wrote Tier-2 package: {manifest_path}")
    print(f"Code: {manifest['graph']['code']}")
    print(f"Detectors: {manifest['graph']['detector_count']}")
    print(f"Faults: {manifest['graph']['fault_count']}")
    print(f"Observables: {manifest['graph']['observable_count']}")


if __name__ == "__main__":
    main()
