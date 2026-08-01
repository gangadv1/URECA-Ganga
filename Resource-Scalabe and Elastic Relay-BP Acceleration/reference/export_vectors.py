"""Export deterministic RTL-ready vectors from the Python Relay-BP golden reference."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

import numpy as np

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
for path in (CURRENT_DIR, PROJECT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from configs.manifest import ManifestConfig, write_manifest  # noqa: E402
from fixedpoint import (  # noqa: E402
    FixedConfig,
    beta_to_int,
    check_node_update,
    clip_to_bounds,
    memory_mix,
    round_div_power_of_two,
    sat_b,
    scale_beta,
    signed_add,
    signed_mul,
    signed_sub,
    widened_product,
    widened_sum,
)
from graph_loader import load_graph_package  # noqa: E402
from relay_bp_fixed import FixedRelayBPDecoder, FixedRelayConfig, FixedRelayLegConfig  # noqa: E402


RTL_VECTOR_VERSION = 1
DEFAULT_GRAPH_PACKAGE = PROJECT_ROOT / "graphs" / "generated" / "gross_code_capacity" / "package.json"
DEFAULT_OUT_DIR = PROJECT_ROOT / "verification" / "vectors"


def _packed_bits(values: list[int]) -> tuple[int, str]:
    packed = 0
    for index, value in enumerate(values):
        packed |= (int(value) & 0x1) << index
    width = max(1, len(values))
    digits = max(1, (width + 3) // 4)
    return width, f"{packed:0{digits}x}"


def _packed_signed_nibbles(values: list[int]) -> tuple[int, str]:
    packed = 0
    for index, value in enumerate(values):
        packed |= (int(value) & 0xF) << (4 * index)
    width = max(1, 4 * len(values))
    digits = max(1, (width + 3) // 4)
    return width, f"{packed:0{digits}x}"


def deterministic_cases(checks: int, variables: int, shots: int, seed: int) -> list[dict[str, object]]:
    rng = np.random.default_rng(seed)
    cases: list[dict[str, object]] = []
    base_patterns = [
        np.zeros(checks, dtype=np.uint8),
        np.ones(checks, dtype=np.uint8),
        np.tile(np.array([0, 1], dtype=np.uint8), checks // 2 + 1)[:checks],
        np.tile(np.array([1, 0, 1], dtype=np.uint8), checks // 3 + 1)[:checks],
    ]
    for index, syndrome in enumerate(base_patterns[:shots]):
        prior = rng.integers(-7, 8, size=variables, dtype=int)
        cases.append({"case_id": f"case_{index:02d}", "seed": seed + index, "syndrome": syndrome.astype(int).tolist(), "prior": prior.astype(int).tolist()})
    while len(cases) < shots:
        case_index = len(cases)
        syndrome = rng.integers(0, 2, size=checks, dtype=np.uint8)
        prior = rng.integers(-7, 8, size=variables, dtype=int)
        cases.append({"case_id": f"case_{case_index:02d}", "seed": seed + case_index, "syndrome": syndrome.astype(int).tolist(), "prior": prior.astype(int).tolist()})
    return cases


def directed_primitive_rows() -> list[dict[str, object]]:
    config = FixedConfig(b=4, g=2, M=8, clip=7)
    return [
        {"name": "add_pos", "inputs": [3, 4], "expected": signed_add(3, 4)},
        {"name": "add_neg", "inputs": [-3, -4], "expected": signed_add(-3, -4)},
        {"name": "sub_pos", "inputs": [3, 4], "expected": signed_sub(3, 4)},
        {"name": "sub_neg", "inputs": [-3, -4], "expected": signed_sub(-3, -4)},
        {"name": "mul_posneg", "inputs": [3, -4], "expected": signed_mul(3, -4)},
        {"name": "widened_product", "inputs": [-7, 7], "expected": widened_product(-7, 7)},
        {"name": "widened_sum", "inputs": [7, -3, -4, 10], "expected": widened_sum([7, -3, -4, 10])},
        {"name": "clip_high", "inputs": [12, -5, 5], "expected": clip_to_bounds(12, -5, 5)},
        {"name": "clip_low", "inputs": [-12, -5, 5], "expected": clip_to_bounds(-12, -5, 5)},
        {"name": "sat_high", "inputs": [12], "expected": sat_b(12, config)},
        {"name": "sat_low", "inputs": [-12], "expected": sat_b(-12, config)},
        {"name": "round_half_pos", "inputs": [5, 1], "expected": round_div_power_of_two(5, 1)},
        {"name": "round_half_neg", "inputs": [-5, 1], "expected": round_div_power_of_two(-5, 1)},
        {"name": "beta_scale_zero", "inputs": [0.0, 8], "expected": scale_beta(0.0, 8)},
        {"name": "beta_scale_half", "inputs": [0.5, 8], "expected": scale_beta(0.5, 8)},
        {"name": "beta_scale_one", "inputs": [1.0, 8], "expected": scale_beta(1.0, 8)},
        {"name": "memory_mix_zero_beta", "inputs": [3, -5, 0], "expected": memory_mix(3, -5, 0, config)},
        {"name": "memory_mix_half_beta", "inputs": [3, -5, 4], "expected": memory_mix(3, -5, 4, config)},
        {"name": "memory_mix_full_beta", "inputs": [3, -5, 8], "expected": memory_mix(3, -5, 8, config)},
        {"name": "check_node_equal", "inputs": [[3, -3, 3], 0], "expected": check_node_update([3, -3, 3], 0, config)},
    ]


def build_fixed_decoder(graph_matrix: np.ndarray) -> FixedRelayBPDecoder:
    return FixedRelayBPDecoder(
        graph_matrix,
        FixedRelayConfig(
            fixed=FixedConfig(b=4, g=2, M=8, clip=7, separate_scale=True),
            leg_configs=(
                FixedRelayLegConfig((0.25, 0.50, 0.50), carry_gamma=0.25),
                FixedRelayLegConfig((0.10, 0.20, 0.30), carry_gamma=0.50),
            ),
            max_iterations_per_leg=3,
            gamma_scale=16,
        ),
    )


def export_rtl_vectors(package_path: Path, out_dir: Path, shots: int, seed: int) -> dict[str, object]:
    graph = load_graph_package(package_path)
    decoder = build_fixed_decoder(graph.h_matrix)
    cases = deterministic_cases(graph.h_matrix.shape[0], graph.h_matrix.shape[1], shots, seed)

    case_rows: list[dict[str, object]] = []
    for case in cases:
        result = decoder.decode(case["prior"], case["syndrome"])
        expected = {
            "converged": result.converged,
            "total_iterations": result.total_iterations,
            "relay_legs": result.relay_legs,
            "decoded_error": result.decoded_error.astype(int).tolist(),
            "final_syndrome": result.final_syndrome.astype(int).tolist(),
            "beliefs": result.beliefs.astype(int).tolist(),
            "relay_memory": result.relay_memory.astype(int).tolist(),
            "trace": [asdict(record) for record in result.trace],
        }
        case_rows.append(
            {
                "case_id": case["case_id"],
                "seed": case["seed"],
                "syndrome": case["syndrome"],
                "prior": case["prior"],
                "gamma_schedule": [list(leg.gamma_schedule) for leg in decoder._decoder.config.leg_configs],
                "relay_parameters": {
                    "max_iterations_per_leg": decoder._decoder.config.max_iterations_per_leg,
                    "gamma_scale": decoder._decoder.config.gamma_scale,
                    "leg_configs": [
                        {"gamma_schedule": list(leg.gamma_schedule), "carry_gamma": leg.carry_gamma}
                        for leg in decoder._decoder.config.leg_configs
                    ],
                },
                "fixed_point": {
                    "b": decoder._decoder.fixed.b,
                    "g": decoder._decoder.fixed.g,
                    "M": decoder._decoder.fixed.M,
                    "clip": decoder._decoder.fixed.clip,
                    "separate_scale": decoder._decoder.fixed.separate_scale,
                },
                "graph": {
                    "tier": graph.metadata.get("tier"),
                    "source_graph_hash": graph.metadata.get("source_graph_hash"),
                    "detector_count": int(graph.h_matrix.shape[0]),
                    "fault_count": int(graph.h_matrix.shape[1]),
                    "edge_count": int(graph.h_matrix.sum()),
                    "hx_shape": graph.metadata.get("hx_shape"),
                    "hz_shape": graph.metadata.get("hz_shape"),
                },
                "expected": expected,
            }
        )

    rtl_vectors = {
        "format_version": RTL_VECTOR_VERSION,
        "graph_package": str(package_path),
        "graph": {
            "tier": graph.metadata.get("tier"),
            "source_graph_hash": graph.metadata.get("source_graph_hash"),
            "detector_count": int(graph.h_matrix.shape[0]),
            "fault_count": int(graph.h_matrix.shape[1]),
            "edge_count": int(graph.h_matrix.sum()),
            "hx_shape": graph.metadata.get("hx_shape"),
            "hz_shape": graph.metadata.get("hz_shape"),
        },
        "reference": {
            "kind": "python-fixed-point-golden-reference",
            "implementation": "reference/relay_bp_fixed.py via reference/relay_reference.py",
        },
        "vectors": case_rows,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "rtl_vectors.json"
    json_path.write_text(json.dumps(rtl_vectors, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    csv_path = out_dir / "rtl_vectors.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(
            target,
            fieldnames=[
                "case_id",
                "seed",
                "converged",
                "total_iterations",
                "relay_legs",
                "syndrome",
                "prior",
                "final_syndrome",
                "decoded_error",
            ],
        )
        writer.writeheader()
        for case in case_rows:
            expected = case["expected"]
            writer.writerow(
                {
                    "case_id": case["case_id"],
                    "seed": case["seed"],
                    "converged": int(expected["converged"]),
                    "total_iterations": expected["total_iterations"],
                    "relay_legs": expected["relay_legs"],
                    "syndrome": json.dumps(case["syndrome"]),
                    "prior": json.dumps(case["prior"]),
                    "final_syndrome": json.dumps(expected["final_syndrome"]),
                    "decoded_error": json.dumps(expected["decoded_error"]),
                }
            )

    replay_case_path = out_dir / "rtl_replay_case.json"
    replay_case = case_rows[0]
    replay_case_path.write_text(json.dumps(replay_case, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    primitive_path = out_dir / "rtl_primitives.json"
    primitive_path.write_text(json.dumps({"format_version": RTL_VECTOR_VERSION, "tests": directed_primitive_rows()}, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    sv_pkg_path = out_dir / "rtl_vectors_pkg.sv"
    pkg_lines = [
        "package rtl_vectors_pkg;",
        f"  localparam int RTL_VECTOR_VERSION = {RTL_VECTOR_VERSION};",
        f"  localparam int CASE_COUNT = {len(case_rows)};",
        f"  localparam int CHECKS = {int(graph.h_matrix.shape[0])};",
        f"  localparam int VARIABLES = {int(graph.h_matrix.shape[1])};",
        f"  localparam int B = 4;",
        "",
    ]
    for case_index, case in enumerate(case_rows):
        expected = case["expected"]
        syndrome_width, syndrome_hex = _packed_bits([int(bit) for bit in case["syndrome"]])
        prior_width, prior_hex = _packed_signed_nibbles([int(value) for value in case["prior"]])
        decoded_width, decoded_hex = _packed_bits([int(bit) for bit in expected["decoded_error"]])
        residual_width, residual_hex = _packed_bits([int(bit) for bit in expected["final_syndrome"]])
        pkg_lines.extend(
            [
                f"  localparam logic [CHECKS-1:0] SYNDROME_{case_index} = {syndrome_width}'h{syndrome_hex};",
                f"  localparam logic signed [VARIABLES*B-1:0] PRIOR_{case_index} = {prior_width}'h{prior_hex};",
                f"  localparam logic [VARIABLES-1:0] DECIDED_{case_index} = {decoded_width}'h{decoded_hex};",
                f"  localparam logic [CHECKS-1:0] RESIDUAL_{case_index} = {residual_width}'h{residual_hex};",
                f"  localparam int CONVERGED_{case_index} = {1 if expected['converged'] else 0};",
                f"  localparam int TOTAL_ITERATIONS_{case_index} = {int(expected['total_iterations'])};",
                f"  localparam int RELAY_LEGS_{case_index} = {int(expected['relay_legs'])};",
                "",
            ]
        )
    pkg_lines.extend([
        "  function automatic logic [CHECKS-1:0] syndrome_case(input int index);",
        "    case (index)",
    ])
    for case_index in range(len(case_rows)):
        pkg_lines.append(f"      {case_index}: syndrome_case = SYNDROME_{case_index};")
    pkg_lines.extend([
        "      default: syndrome_case = '0;",
        "    endcase",
        "  endfunction",
        "",
        "  function automatic logic signed [VARIABLES*B-1:0] prior_case(input int index);",
        "    case (index)",
    ])
    for case_index in range(len(case_rows)):
        pkg_lines.append(f"      {case_index}: prior_case = PRIOR_{case_index};")
    pkg_lines.extend([
        "      default: prior_case = '0;",
        "    endcase",
        "  endfunction",
        "",
        "  function automatic logic signed [3:0] prior_word_case(input int case_index, input int word_index);",
        "    case (case_index)",
    ])
    for case_index, case in enumerate(case_rows):
        pkg_lines.append("      %d: begin" % case_index)
        pkg_lines.append("        case (word_index)")
        for word_index, value in enumerate(case["prior"]):
            pkg_lines.append(f"          {word_index}: prior_word_case = {int(value)};")
        pkg_lines.extend([
            "          default: prior_word_case = '0;",
            "        endcase",
            "      end",
        ])
    pkg_lines.extend([
        "      default: prior_word_case = '0;",
        "    endcase",
        "  endfunction",
        "",
        "  function automatic logic [VARIABLES-1:0] decided_case(input int index);",
        "    case (index)",
    ])
    for case_index in range(len(case_rows)):
        pkg_lines.append(f"      {case_index}: decided_case = DECIDED_{case_index};")
    pkg_lines.extend([
        "      default: decided_case = '0;",
        "    endcase",
        "  endfunction",
        "",
        "  function automatic logic [CHECKS-1:0] residual_case(input int index);",
        "    case (index)",
    ])
    for case_index in range(len(case_rows)):
        pkg_lines.append(f"      {case_index}: residual_case = RESIDUAL_{case_index};")
    pkg_lines.extend([
        "      default: residual_case = '0;",
        "    endcase",
        "  endfunction",
        "",
        "  function automatic int converged_case(input int index);",
        "    case (index)",
    ])
    for case_index in range(len(case_rows)):
        pkg_lines.append(f"      {case_index}: converged_case = CONVERGED_{case_index};")
    pkg_lines.extend([
        "      default: converged_case = 0;",
        "    endcase",
        "  endfunction",
        "",
        "  function automatic int iterations_case(input int index);",
        "    case (index)",
    ])
    for case_index in range(len(case_rows)):
        pkg_lines.append(f"      {case_index}: iterations_case = TOTAL_ITERATIONS_{case_index};")
    pkg_lines.extend([
        "      default: iterations_case = 0;",
        "    endcase",
        "  endfunction",
        "",
        "  function automatic int legs_case(input int index);",
        "    case (index)",
    ])
    for case_index in range(len(case_rows)):
        pkg_lines.append(f"      {case_index}: legs_case = RELAY_LEGS_{case_index};")
    pkg_lines.extend([
        "      default: legs_case = 0;",
        "    endcase",
        "  endfunction",
        "endpackage",
        "",
    ])
    sv_pkg_path.write_text("\n".join(pkg_lines), encoding="utf-8")

    artifacts = [json_path, csv_path, replay_case_path, primitive_path, sv_pkg_path]
    write_manifest(
        ManifestConfig(
            graph={
                "tier": graph.metadata.get("tier"),
                "source_graph_hash": graph.metadata.get("source_graph_hash"),
                "detector_count": int(graph.h_matrix.shape[0]),
                "fault_count": int(graph.h_matrix.shape[1]),
                "edge_count": int(graph.h_matrix.sum()),
            },
            arithmetic={"b": 4, "g": 2, "M": 8, "clip": 7, "separate_scale": True, "gamma_scale": 16},
            experiment={"purpose": "deterministic RTL vector export", "shots": shots, "seed": seed},
            notes=["These vectors are Python-generated RTL scaffolding and must be compared exactly."],
        ),
        out_dir,
        artifact_paths=artifacts,
    )
    return rtl_vectors


def write_legacy_artifacts(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    config = FixedConfig(b=4, g=2, M=8, clip=7)
    directed_rows = directed_primitive_rows()
    csv_path = out_dir / "directed_vectors.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["name", "inputs", "expected"])
        writer.writeheader()
        writer.writerows(
            {"name": row["name"], "inputs": json.dumps(row["inputs"]), "expected": json.dumps(row["expected"])}
            for row in directed_rows
        )
    sv_path = out_dir / "memory_mix_vectors.svh"
    rng = np.random.default_rng(20260724)
    vectors = [(int(rng.integers(-7, 8)), int(rng.integers(-7, 8)), int(rng.integers(0, 9))) for _ in range(64)]

    def vector_function(name: str, values: list[int]) -> str:
        cases = "\n".join(f"      {index}: {name} = {value};" for index, value in enumerate(values))
        return f"function automatic integer {name}(input integer index);\n  case (index)\n{cases}\n    default: {name} = 0;\n  endcase\nendfunction\n"

    sv_path.write_text(
        "// Generated by reference/export_vectors.py from Python fixedpoint.py.\n"
        f"localparam integer MEMORY_MIX_VECTOR_COUNT = {len(vectors)};\n"
        + vector_function("memory_mix_prev", [item[0] for item in vectors])
        + vector_function("memory_mix_new", [item[1] for item in vectors])
        + vector_function("memory_mix_beta", [item[2] for item in vectors])
        + vector_function("memory_mix_expected", [memory_mix(prev, new, beta, config) for prev, new, beta in vectors]),
        encoding="utf-8",
    )
    return [csv_path, sv_path]


def _artifact_bytes(paths: list[Path]) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in paths}


def export_all(package_path: Path, out_dir: Path, shots: int, seed: int) -> list[Path]:
    rtl_vectors = export_rtl_vectors(package_path, out_dir, shots, seed)
    legacy_paths = write_legacy_artifacts(out_dir)
    return [out_dir / "rtl_vectors.json", out_dir / "rtl_vectors.csv", out_dir / "rtl_replay_case.json", out_dir / "rtl_primitives.json", out_dir / "manifest.json", *legacy_paths]


def check_deterministic(package_path: Path, out_dir: Path, shots: int, seed: int) -> None:
    if not out_dir.exists():
        raise FileNotFoundError(f"Missing output directory: {out_dir}")
    expected_paths = [out_dir / name for name in ["rtl_vectors.json", "rtl_vectors.csv", "rtl_replay_case.json", "rtl_primitives.json", "directed_vectors.csv", "memory_mix_vectors.svh"]]
    for path in expected_paths:
        if not path.exists():
            raise FileNotFoundError(f"Missing expected artifact: {path}")
    if not (out_dir / "manifest.json").exists():
        raise FileNotFoundError(f"Missing expected artifact: {out_dir / 'manifest.json'}")
    with tempfile.TemporaryDirectory() as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        export_all(package_path, temp_dir, shots, seed)
        for path in expected_paths:
            regenerated = temp_dir / path.name
            if path.read_bytes() != regenerated.read_bytes():
                raise RuntimeError(f"Deterministic replay mismatch for {path.name}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export deterministic RTL vectors from the Relay-BP Python golden reference")
    parser.add_argument("--package", type=Path, default=DEFAULT_GRAPH_PACKAGE)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--shots", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20260801)
    parser.add_argument("--check", action="store_true", help="Regenerate the vectors in a temp directory and compare them byte-for-byte.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.check:
        check_deterministic(args.package, args.out_dir, args.shots, args.seed)
        print("RTL vector replay check passed")
        return
    export_all(args.package, args.out_dir, args.shots, args.seed)
    print(args.out_dir / "rtl_vectors.json")


if __name__ == "__main__":
    main()
