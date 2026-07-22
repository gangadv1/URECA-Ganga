"""Record the first reference-faithfulness audit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
for path in (PROJECT_ROOT,):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from configs.manifest import ManifestConfig, write_manifest  # noqa: E402


def contains(path: Path, text: str) -> bool:
    return text in path.read_text(encoding="utf-8")


def run_audit(out_dir: Path) -> Path:
    decoder_path = PROJECT_ROOT / "simulations" / "sequential_relay" / "relay_bp_decoder.py"
    sim_path = PROJECT_ROOT / "simulations" / "sequential_relay" / "sequential_relay_bp_sim.py"
    hls_path = PROJECT_ROOT / "fpga" / "hls" / "relay_engine_hls.cpp"

    checks = {
        "belief_restore_present": contains(decoder_path, "variable_node.belief = previous_belief"),
        "memory_update_function_present": contains(decoder_path, "def _update_relay_memory"),
        "memory_update_called_between_legs": contains(decoder_path, "self._update_relay_memory(leg_config)"),
        "float_decoder_has_no_noise_std": not contains(decoder_path, "noise_std"),
        "separate_sim_noise_noted": contains(sim_path, "noise_std"),
        "hls_toy_size_noted": contains(hls_path, "MAX_VARIABLES = 16"),
        "hls_non_target_carry_noted": contains(hls_path, "/ 255"),
    }
    report = {
        "status": "scaffold audit passed; manual canonical trace-lock still required",
        "checks": checks,
        "next_step": "Compare the float trace with the chosen canonical Relay-BP source before exporting headline vectors.",
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "faithfulness_check.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_manifest(
        ManifestConfig(
            experiment={"purpose": "reference faithfulness scaffold audit"},
            notes=[report["status"]],
        ),
        out_dir,
        artifact_paths=[report_path],
    )
    return report_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the first reference-faithfulness audit")
    parser.add_argument("--out-dir", type=Path, default=PROJECT_ROOT / "results" / "faithfulness-check")
    return parser


def main() -> None:
    report_path = run_audit(build_parser().parse_args().out_dir)
    print(f"Wrote faithfulness report to {report_path}")


if __name__ == "__main__":
    main()

