"""Resumable deterministic expansion of the canonical Relay-BP LER screening."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import scipy
import stim
from scipy import sparse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_DIR = PROJECT_ROOT / "reference"
sys.path.insert(0, str(REFERENCE_DIR))
from relay_bp_float import FloatRelayBPDecoder  # noqa: E402

OUT = Path(__file__).resolve().parent
ORIGINAL = PROJECT_ROOT / "results/paper-ler-reproduction"
PACKAGES = PROJECT_ROOT / "graphs/generated/gross_circuit_level"
P_VALUES = (0.001, 0.002, 0.003, 0.004, 0.005)
ORIGINAL_SHOTS = 256
MAX_SHOTS = 10_000
TARGET_FAILURES = 20
BATCH_SIZE = 256
EXPECTED = (1728, 67752, 12)
UPSTREAM = "d185194ba0cb4101ced4340d82b2ee6d42f225f0"


def tag(p: float) -> str:
    return format(p, ".12g").replace(".", "p")


def package_dir(p: float) -> Path:
    return PACKAGES / f"memory_Z_r12_p{tag(p)}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wilson(failures: int, shots: int) -> tuple[float, float]:
    z = 1.959963984540054
    q = failures / shots
    den = 1 + z * z / shots
    center = (q + z * z / (2 * shots)) / den
    radius = z * math.sqrt(q * (1 - q) / shots + z * z / (4 * shots * shots)) / den
    return max(0.0, center - radius), min(1.0, center + radius)


def seeds(p: float, batch: int) -> tuple[int, int]:
    p_index = P_VALUES.index(p) + 1
    return 202608120000 + p_index * 10_000 + batch, 250601779 + p_index * 100_000 + batch


def load_problem(p: float):
    d = package_dir(p)
    package = json.loads((d / "package.json").read_text())
    manifest = json.loads((d / "manifest.json").read_text())
    assert (package["detector_count"], package["fault_count"], package["observable_count"]) == EXPECTED
    assert package["memory_basis"] == "Z" and package["noisy_rounds"] == 12
    assert package["final_perfect_measurement"] and math.isclose(package["physical_error_probability"], p)
    assert manifest["provenance"]["upstream_commit"] == UPSTREAM
    with np.load(d / "edge_lists.npz") as z:
        de, oe = z["detector_edges"], z["observable_edges"]
    with np.load(d / "faults.npz") as z:
        probabilities = z["probabilities"]
    h = sparse.csr_matrix((np.ones(len(de), np.uint8), (de[:, 1], de[:, 0])), shape=EXPECTED[:2])
    a = sparse.csr_matrix((np.ones(len(oe), np.uint8), (oe[:, 1], oe[:, 0])), shape=(EXPECTED[2], EXPECTED[1]))
    return d, h, a, probabilities, stim.Circuit.from_file(str(d / "circuit.stim"))


def outcome_hash(syndrome: np.ndarray, logical: np.ndarray) -> str:
    packed = np.packbits(np.concatenate((syndrome, logical)).astype(np.uint8))
    return hashlib.sha256(packed.tobytes()).hexdigest()


def run_batch(p: float, batch: int, count: int) -> tuple[dict, list[dict]]:
    d, h, a, probabilities, circuit = load_problem(p)
    sample_seed, decoder_seed = seeds(p, batch)
    sample = circuit.compile_detector_sampler(seed=sample_seed).sample(count, separate_observables=True)
    repeat = circuit.compile_detector_sampler(seed=sample_seed).sample(count, separate_observables=True)
    if not all(np.array_equal(x, y) for x, y in zip(sample, repeat)):
        raise RuntimeError("fixed-seed circuit sampling was not reproducible")
    syndromes, logicals = sample
    decoder = FloatRelayBPDecoder(h, S=1, R=301, seed=decoder_seed)
    llr = np.log((1 - probabilities) / probabilities)
    rows = []
    for offset, (syndrome, logical) in enumerate(zip(syndromes, logicals)):
        result = decoder.decode(llr, syndrome)
        correction = result.decoded_error
        predicted_syndrome = np.asarray(h @ correction).reshape(-1).astype(np.uint8) & 1
        predicted_logical = np.asarray(a @ correction).reshape(-1).astype(np.uint8) & 1
        converged = bool(np.array_equal(predicted_syndrome, syndrome))
        logical_match = bool(np.array_equal(predicted_logical, logical))
        rows.append({
            "p": p, "batch": batch, "batch_offset": offset, "source": "expanded",
            "sample_seed": sample_seed, "decoder_seed": decoder_seed,
            "outcome_sha256": outcome_hash(syndrome, logical),
            "syndrome_weight": int(syndrome.sum()), "observed_logical_weight": int(logical.sum()),
            "syndrome_converged": int(converged), "logical_action_match": int(logical_match),
            "logically_correct": int(converged and logical_match),
            "syndrome_valid_logical_error": int(converged and not logical_match),
            "non_converged": int(not converged),
            "iterations": result.total_iterations, "relay_legs": result.relay_legs,
            "valid_solutions": result.solutions_found,
            "selected_solution_weight": "" if result.metadata["best_weight"] is None else result.metadata["best_weight"],
        })
    packed = np.packbits(np.concatenate((syndromes, logicals), axis=1).astype(np.uint8), axis=1)
    info = {
        "p": p, "batch": batch, "shots": count, "sample_seed": sample_seed,
        "decoder_seed": decoder_seed, "sample_matrix_sha256": hashlib.sha256(packed.tobytes()).hexdigest(),
        "failures": sum(1 - r["logically_correct"] for r in rows),
        "non_convergence": sum(r["non_converged"] for r in rows),
        "syndrome_valid_logical_errors": sum(r["syndrome_valid_logical_error"] for r in rows),
    }
    return info, rows


def import_original() -> tuple[list[dict], list[dict]]:
    original_rows = list(csv.DictReader((ORIGINAL / "per_shot_results.csv").open()))
    original_summary = json.loads((ORIGINAL / "summary.json").read_text())
    rows, batches = [], []
    for summary in original_summary:
        p = float(summary["p"]); _, _, _, _, circuit = load_problem(p)
        syndrome, logical = circuit.compile_detector_sampler(seed=summary["sample_seed"]).sample(
            ORIGINAL_SHOTS, separate_observables=True
        )
        group = [r for r in original_rows if float(r["p"]) == p]
        for offset, old in enumerate(group):
            rows.append({
                "p": p, "batch": 0, "batch_offset": offset, "source": "original_screening",
                "sample_seed": int(old["sample_seed"]), "decoder_seed": int(old["decoder_seed"]),
                "outcome_sha256": outcome_hash(syndrome[offset], logical[offset]),
                "syndrome_weight": int(old["syndrome_weight"]),
                "observed_logical_weight": int(old["observed_logical_weight"]),
                "syndrome_converged": int(old["syndrome_converged"]),
                "logical_action_match": int(old["logical_action_match"]),
                "logically_correct": int(old["logically_correct"]),
                "syndrome_valid_logical_error": int(old["syndrome_valid_logical_error"]),
                "non_converged": int(old["non_converged"]), "iterations": int(old["iterations"]),
                "relay_legs": int(old["relay_legs"]), "valid_solutions": int(old["valid_solutions"]),
                "selected_solution_weight": old["selected_solution_weight"],
            })
        packed = np.packbits(np.concatenate((syndrome, logical), axis=1).astype(np.uint8), axis=1)
        batches.append({
            "p": p, "batch": 0, "shots": ORIGINAL_SHOTS, "sample_seed": summary["sample_seed"],
            "decoder_seed": summary["decoder_seed"], "sample_matrix_sha256": hashlib.sha256(packed.tobytes()).hexdigest(),
            "failures": summary["logical_failures"], "non_convergence": summary["non_convergence"],
            "syndrome_valid_logical_errors": summary["syndrome_valid_logical_errors"],
        })
    return rows, batches


def read_state() -> tuple[list[dict], list[dict]]:
    path = OUT / "per_shot_results.csv"
    if not path.exists(): return import_original()
    with path.open() as f: rows = list(csv.DictReader(f))
    numeric_int = {"batch", "batch_offset", "sample_seed", "decoder_seed", "syndrome_weight",
                   "observed_logical_weight", "syndrome_converged", "logical_action_match", "logically_correct",
                   "syndrome_valid_logical_error", "non_converged", "iterations", "relay_legs", "valid_solutions"}
    for row in rows:
        row["p"] = float(row["p"])
        for key in numeric_int: row[key] = int(row[key])
    return rows, json.loads((OUT / "batches.json").read_text())


def write_state(rows: list[dict], batches: list[dict]) -> None:
    rows.sort(key=lambda r: (r["p"], r["batch"], r["batch_offset"]))
    batches.sort(key=lambda r: (r["p"], r["batch"]))
    with (OUT / "per_shot_results.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    (OUT / "batches.json").write_text(json.dumps(batches, indent=2) + "\n")
    summaries = []
    for p in P_VALUES:
        g = [r for r in rows if r["p"] == p]; n = len(g)
        failures = sum(1-r["logically_correct"] for r in g); conv = sum(r["syndrome_converged"] for r in g)
        svle = sum(r["syndrome_valid_logical_error"] for r in g); nonconv = n-conv
        its = np.array([r["iterations"] for r in g]); legs = np.array([r["relay_legs"] for r in g])
        lo, hi = wilson(failures, n)
        summaries.append({
            "p": p, "shots": n, "logical_failures": failures, "logical_error_rate": failures/n,
            "ler_wilson_95_low": lo, "ler_wilson_95_high": hi, "logical_error_rate_over_p": failures/n/p,
            "ler_over_p_wilson_95_low": lo/p, "ler_over_p_wilson_95_high": hi/p,
            "syndrome_converged_shots": conv, "syndrome_convergence_rate": conv/n,
            "syndrome_valid_logical_errors": svle, "non_convergence": nonconv,
            "average_iterations": float(its.mean()), "p50_iterations": float(np.percentile(its,50)),
            "p90_iterations": float(np.percentile(its,90)), "p99_iterations": float(np.percentile(its,99)),
            "maximum_iterations": int(its.max()), "average_relay_legs": float(legs.mean()),
            "maximum_relay_legs": int(legs.max()), "target_reached": failures >= TARGET_FAILURES,
            "shot_limit_reached": n >= MAX_SHOTS,
        })
    (OUT / "summary.json").write_text(json.dumps(summaries, indent=2) + "\n")
    with (OUT / "per_p_summary.csv").open("w", newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(summaries[0])); w.writeheader(); w.writerows(summaries)


def check_duplicates(rows: list[dict], batches: list[dict]) -> dict:
    seed_pairs=[(b["p"],b["sample_seed"]) for b in batches]
    matrix_hashes=[b["sample_matrix_sha256"] for b in batches]
    if len(seed_pairs)!=len(set(seed_pairs)) or len(matrix_hashes)!=len(set(matrix_hashes)):
        raise RuntimeError("duplicate batch seed or complete sample matrix detected")
    counts={}
    for r in rows: counts[r["outcome_sha256"]]=counts.get(r["outcome_sha256"],0)+1
    return {
        "unique_batch_seeds": True, "unique_complete_batch_sample_matrices": True,
        "repeated_outcome_patterns": sum(v-1 for v in counts.values() if v>1),
        "note": "Repeated detector/logical outcomes can occur naturally; unique seeds and complete batch hashes exclude accidental batch replay."
    }


def write_manifest(rows: list[dict], batches: list[dict]) -> None:
    duplicate_check=check_duplicates(rows,batches)
    manifest={
        "study":"expanded canonical Relay-BP paper-LER validation", "continues_original_screening":True,
        "original_results":"results/paper-ler-reproduction", "target_failures_per_p":TARGET_FAILURES,
        "maximum_shots_per_p":MAX_SHOTS, "batch_size":BATCH_SIZE,
        "decoder":{"implementation":"reference/relay_bp_float.py","S":1,"R":301,
            "first_leg":{"gamma":0.125,"max_iterations":80},
            "later_legs":{"per_node_gamma_uniform":[-0.24,0.66],"max_iterations":60},
            "prior":"per-fault DEM LLR log((1-p_j)/p_j)","non_convergence_is_failure":True},
        "circuit":{"code":"gross [[144,12,12]]","memory_basis":"Z","noisy_rounds":12,
                   "detectors":1728,"faults":67752,"logical_observables":12},
        "duplicate_check":duplicate_check,
        "runtime_stop": {
            "stopped_early": True,
            "reason": "Canonical sparse Python decoding developed extreme 301-leg tails; completed batches were preserved rather than launching blindly toward 10,000 shots.",
            "incomplete_batches_excluded": [
                {"p": 0.004, "batch": 1, "requested_shots": 256, "superseded_by_completed_shots": 16},
                {"p": 0.005, "batch": 1, "requested_shots": 256},
                {"p": 0.005, "batch": 1, "requested_shots": 16}
            ]
        },
        "package_hashes":{f"{p:.3f}":{"manifest_sha256":sha256(package_dir(p)/"manifest.json"),
            "source_sha256":json.loads((package_dir(p)/"manifest.json").read_text())["provenance"]["source_circuit_sha256"]} for p in P_VALUES},
        "canonical_float_sha256":sha256(REFERENCE_DIR/"relay_bp_float.py"),
        "software":{"numpy":np.__version__,"scipy":scipy.__version__,"stim":stim.__version__,
                    "git_commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=PROJECT_ROOT.parent,text=True).strip()},
        "artifacts":["manifest.json","summary.json","per_p_summary.csv","per_shot_results.csv","batches.json","run_expanded_ler.py"]}
    (OUT/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--rounds",type=int,default=1)
    parser.add_argument("--batch-size",type=int,default=BATCH_SIZE)
    parser.add_argument("--p",type=float,action="append",choices=P_VALUES)
    args=parser.parse_args(); OUT.mkdir(parents=True,exist_ok=True)
    rows,batches=read_state(); write_state(rows,batches); write_manifest(rows,batches)
    for _ in range(args.rounds):
        tasks=[]
        for p in (tuple(args.p) if args.p else P_VALUES):
            g=[r for r in rows if r["p"]==p]; failures=sum(1-r["logically_correct"] for r in g)
            if failures>=TARGET_FAILURES or len(g)>=MAX_SHOTS: continue
            batch=max((b["batch"] for b in batches if b["p"]==p),default=0)+1
            tasks.append((p,batch,min(args.batch_size,MAX_SHOTS-len(g))))
        if not tasks: break
        with ProcessPoolExecutor(max_workers=len(tasks)) as ex:
            fs={ex.submit(run_batch,*task):task for task in tasks}
            for f in as_completed(fs):
                info,new=f.result(); rows.extend(new); batches.append(info)
                write_state(rows,batches); write_manifest(rows,batches)
                print(f"p={info['p']:.3f} batch={info['batch']} failures={info['failures']}/{info['shots']}",flush=True)
    print((OUT/"summary.json").read_text())


if __name__ == "__main__": main()
