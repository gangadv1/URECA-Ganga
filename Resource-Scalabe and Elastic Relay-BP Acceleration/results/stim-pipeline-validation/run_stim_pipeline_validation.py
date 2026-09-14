#!/usr/bin/env python3
"""Small falsifiable controls for the current canonical circuit/decoder/scorer.

No historical artifacts or decoder code are written. Worker processes receive
an allowlisted NPZ payload without logical labels or realized error information.
"""
from __future__ import annotations

import ast
import csv
import hashlib
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import traceback

import numpy as np
import stim
from scipy import sparse

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
REPO = PROJECT.parent
PACKAGE = PROJECT / "graphs/generated/gross_circuit_level/memory_Z_r12_p0p003"
DECODER = PROJECT / "reference/relay_bp_float.py"
SCORER = PROJECT / "results/circuit-level-baseline/run_circuit_level_baseline.py"
SEED, DECODER_SEED = 20260808, 91
PROFILES = {
    "bounded": [(80, 0.125, None), (60, None, (-0.24, 0.66))],
    "tiny": [(1, 0.125, None)],
    "seed_probe": [(1, 0.125, None), (1, None, (-0.24, 0.66))],
}
SCHEDULE = {"noiseless": 16, "original": 4, "repeat": 4, "shuffled": 4,
            "tiny_budget": 4, "seed_probe_91": 2, "seed_probe_92": 2, "high_noise": 4}
CASE_NAMES = [
    "information_boundary", "noiseless_circuit", "logical_label_isolation",
    "shuffled_syndrome_negative_control", "invalid_correction_scoring",
    "syndrome_valid_logically_wrong", "nonconvergence_accounting",
    "same_seed_reproducibility", "changed_stim_seed", "changed_decoder_seed",
    "high_noise_destructive_control", "no_postselection_or_dropped_shots",
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ah(array):
    a = np.ascontiguousarray(array)
    return hashlib.sha256(str((a.shape, a.dtype.str)).encode() + a.tobytes()).hexdigest()


def require(condition, explanation):
    if not condition:
        raise AssertionError(explanation)


def plain(value):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(type(value).__name__)


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, default=plain, allow_nan=False) + "\n")


def worker(input_path, output_dir, profile, seed):
    """Actual decoder invocation, in a fresh process with no scoring payload."""
    sys.path.insert(0, str(DECODER.parent))
    from relay_bp_float import FloatRelayBPDecoder, RelayLegConfig

    allowed = {"h_data", "h_indices", "h_indptr", "h_shape", "probabilities", "syndromes"}
    with np.load(input_path, allow_pickle=False) as z:
        require(set(z.files) == allowed, "Unexpected decoder payload fields")
        h = sparse.csr_matrix((z["h_data"], z["h_indices"], z["h_indptr"]), shape=tuple(z["h_shape"]))
        p, syndromes = z["probabilities"], z["syndromes"]
    require(np.all((p > 0) & (p < 1)), "Invalid static fault probabilities")
    prior = np.log((1 - p) / p)
    prior.setflags(write=False)
    legs = tuple(RelayLegConfig(n, gamma=g, gamma_range=r) for n, g, r in PROFILES[profile])
    constructor = {"h_matrix": h, "leg_configs": legs, "S": 2 if profile == "seed_probe" else 1,
                   "R": len(legs), "seed": seed}
    inspect.signature(FloatRelayBPDecoder).bind(**constructor)
    decoder = FloatRelayBPDecoder(**constructor)
    require(decoder.iteration_callback is None and not decoder.trace_messages, "Unexpected decoder observation hook")
    forbidden = {"observed_logicals", "logical", "labels", "true_error", "faults", "expected_correction", "winner", "success"}
    require(not (forbidden & set(vars(decoder))), "Hidden information in decoder instance")
    require((decoder.h_matrix != h).nnz == 0, "Constructor changed the static graph")
    require(set(inspect.signature(decoder.decode).parameters) == {"prior", "syndrome", "trace_path"},
            "Decoder interface changed; boundary needs review")
    audit = {"payload_fields": sorted(allowed), "constructor_arguments": sorted(constructor),
             "call_arguments": ["prior", "syndrome"], "h_hash": ah(h.data) + ":" + ah(h.indices) + ":" + ah(h.indptr),
             "probability_hash": ah(p), "prior_hash": ah(prior), "decoder_sha256": sha(DECODER),
             "seed": seed, "profile": profile, "invocations": [], "errors": []}
    for i, syndrome in enumerate(syndromes):
        syndrome.setflags(write=False)
        calls = []
        state_before = json.dumps(decoder._rng.bit_generator.state, sort_keys=True)

        def trace(frame, event, arg):
            if event == "call" and frame.f_code is FloatRelayBPDecoder.decode.__code__:
                actual = frame.f_locals
                require(set(actual) == {"self", "prior", "syndrome", "trace_path"}, "Unexpected actual call locals")
                require(actual["self"] is decoder and actual["prior"] is prior and actual["syndrome"] is syndrome,
                        "Actual decoder input identity mismatch")
                require(actual["trace_path"] is None, "Unexpected trace-path input")
                calls.append({"shot": i, "prior_hash": ah(actual["prior"]), "syndrome_hash": ah(actual["syndrome"])})

        try:
            sys.setprofile(trace)
            result = decoder.decode(prior=prior, syndrome=syndrome)
            sys.setprofile(None)
            require(len(calls) == 1, "Actual decoder invocation was not traced exactly once")
            require(ah(prior) == audit["prior_hash"], "Static priors were mutated")
            calls[0].update(rng_before=state_before,
                            rng_after=json.dumps(decoder._rng.bit_generator.state, sort_keys=True),
                            result_seed=result.metadata["seed"], gamma_summaries=result.metadata["leg_gamma_summaries"])
            audit["invocations"].extend(calls)
            np.savez_compressed(Path(output_dir) / f"{i}.npz", correction=result.decoded_error,
                                converged=result.converged, iterations=result.total_iterations,
                                residual=result.final_syndrome)
        except Exception:
            sys.setprofile(None)
            audit["errors"].append({"shot": i, "error": traceback.format_exc()})
        dump(Path(output_dir) / "audit.json", audit)


def dem_graph(circuit):
    """Independently extract whole DEM mechanisms, without sampling fault IDs."""
    dem = circuit.detector_error_model(decompose_errors=False, flatten_loops=True)
    dr, dc, ar, ac, probabilities = [], [], [], [], []
    for inst in dem:
        if inst.type != "error":
            continue
        ds, obs = set(), set()
        for target in inst.targets_copy():
            if target.is_relative_detector_id():
                ds.symmetric_difference_update([target.val])
            elif target.is_logical_observable_id():
                obs.symmetric_difference_update([target.val])
            elif not target.is_separator():
                raise ValueError(f"Unsupported DEM target: {target}")
        j = len(probabilities)
        probabilities.append(inst.args_copy()[0])
        dr.extend(sorted(ds)); dc.extend([j] * len(ds))
        ar.extend(sorted(obs)); ac.extend([j] * len(obs))
    h = sparse.csr_matrix((np.ones(len(dr), np.uint8), (dr, dc)), shape=(dem.num_detectors, len(probabilities)))
    a = sparse.csr_matrix((np.ones(len(ar), np.uint8), (ar, ac)), shape=(dem.num_observables, len(probabilities)))
    return h, a, np.array(probabilities), dem


def circuit_metadata(circuit):
    groups = [i for i in circuit.flattened() if i.name in {"M", "MX"}]
    noisy = [i for i in groups if i.gate_args_copy()]
    z = [i for i in noisy if i.name == "M"]
    x = [i for i in noisy if i.name == "MX"]
    require(len(z) == len(x) and all(len(i.targets_copy()) == 72 for i in noisy), "Unexpected QEC readout structure")
    channels = {}
    for i in circuit.flattened():
        if stim.gate_data(i.name).is_noisy_gate:
            require(i.name in {"X_ERROR", "Z_ERROR", "DEPOLARIZE1", "DEPOLARIZE2", "M", "MX"},
                    f"Unreviewed stochastic instruction {i.name}")
        if i.name in {"X_ERROR", "Z_ERROR", "DEPOLARIZE1", "DEPOLARIZE2", "M", "MX"} and i.gate_args_copy():
            channels.setdefault(i.name, set()).update(i.gate_args_copy())
    values = set(v for vs in channels.values() for v in vs)
    require(len(values) == 1, "Noise probability is not uniform")
    final = groups[-1]
    require(final.name == "M" and not final.gate_args_copy() and
            {t.value for t in final.targets_copy()} == set(range(144)), "Unexpected final data readout")
    return {k: getattr(circuit, k) for k in ("num_qubits", "num_measurements", "num_detectors", "num_observables")} | {
        "physical_p": next(iter(values)), "qec_rounds": len(z), "data_qubits": 144,
        "basis": "memory-Z", "noise_channels": {k: sorted(v) for k, v in channels.items()},
        "round_derivation": "count of paired noisy 72-target M/MX ancilla-readout groups",
        "code_distance_independently_verified": False}


def high_noise(circuit, p):
    """Typed transformation of this audited uniform-noise instruction set."""
    result = stim.Circuit()
    supported = {"X_ERROR", "Z_ERROR", "DEPOLARIZE1", "DEPOLARIZE2", "M", "MX"}
    for inst in circuit.flattened():
        args = inst.gate_args_copy()
        if inst.name in supported and args:
            require(len(args) == 1 and args[0] == 0.003, "Unrecognized original noise parameter")
            inst = stim.CircuitInstruction(inst.name, inst.targets_copy(), [p], tag=inst.tag)
        result.append(inst)
    require(result.without_noise() == circuit.without_noise(), "High-noise transformation changed circuit semantics")
    return result


def scoring_code():
    """Execute the actual five canonical scoring assignments, not copied formulas."""
    tree = ast.parse(SCORER.read_text())
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    names = ["predicted_syndromes", "predicted_logicals", "syndrome_valid", "logical_action_match", "logically_correct"]
    nodes = [n for n in ast.walk(main) if isinstance(n, ast.Assign) and len(n.targets) == 1
             and isinstance(n.targets[0], ast.Name) and n.targets[0].id in names]
    nodes.sort(key=lambda n: n.lineno)
    require([n.targets[0].id for n in nodes] == names, "Canonical scoring structure changed; automatic verification unavailable")
    return compile(ast.Module(body=nodes, type_ignores=[]), str(SCORER), "exec"), [n.lineno for n in nodes]


def canonical_invocation_audit():
    """Fail closed if the historical entry script no longer has the reviewed flow."""
    tree = ast.parse(SCORER.read_text())
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    assigned = {}
    for node in ast.walk(main):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            assigned.setdefault(node.targets[0].id, []).append(node)
    expected = {"lambdas": "np.log((1.0 - probabilities) / probabilities)",
                "results": "[decoder.decode(lambdas, syndrome) for syndrome in syndromes]"}
    evidence = {}
    for name, expression in expected.items():
        nodes = assigned.get(name, [])
        require(len(nodes) == 1 and ast.dump(nodes[0].value) == ast.dump(ast.parse(expression, mode="eval").body),
                f"Cannot automatically establish canonical {name} information/filtering boundary")
        evidence[name] = dict(line=nodes[0].lineno, expression=expression)
    evidence["scope"] = "Canonical baseline static-prior and unfiltered decode-comprehension AST checked; this suite dynamically counts its own worker/scorer/save stages. Historical interrupted jobs are not certified."
    return evidence


class Campaign:
    def __init__(self):
        self.cases, self.rows, self.arrays, self.accounting, self.audits = [], [], {}, {}, []
        self.code, self.scorer_lines = scoring_code()

    def case(self, name, shots, expected, action):
        try:
            observed = action()
            status, notes = "PASS", ""
            if isinstance(observed, tuple):
                status, observed, notes = observed
        except Exception:
            status, observed, notes = "FAIL", "Assertion or execution failure", traceback.format_exc()
        self.cases.append(dict(case_name=name, status=status, shots=shots, expected_behavior=expected,
                               observed_behavior=observed, notes=notes))
        print(f"{name}: {status} — {observed}", flush=True)

    def score(self, h, a, correction, syndrome, logical):
        predicted = np.asarray(h.astype(np.int64) @ correction.astype(np.int64)).ravel() % 2
        action = np.asarray(a.astype(np.int64) @ correction.astype(np.int64)).ravel() % 2
        valid, match = bool(np.array_equal(predicted, syndrome)), bool(np.array_equal(action, logical))
        env = dict(np=np, h_matrix=h, action_matrix=a, corrections=correction[None, :],
                   syndromes=syndrome[None, :], observed_logicals=logical[None, :])
        exec(self.code, env)
        require(valid == bool(env["syndrome_valid"][0]) and match == bool(env["logical_action_match"][0])
                and (valid and match) == bool(env["logically_correct"][0]), "Independent and canonical scorer disagree")
        return dict(syndrome_valid=valid, logical_match=match, success=valid and match,
                    residual_weight=int(np.count_nonzero(predicted ^ syndrome)),
                    logical_residual_weight=int(np.count_nonzero(action ^ logical)))

    def panel(self, name, h, a, probabilities, syndrome, labels, profile="bounded", seed=DECODER_SEED):
        n = SCHEDULE[name]
        count = dict(scheduled_shots=n, sampled_shots=len(syndrome), decoded_shots=0, scored_shots=0, saved_shots=0,
                     exception_shots=0, timeout_shots=0)
        self.accounting[name] = count
        require(len(syndrome) == len(labels) == n, "Sample count differs from predeclared schedule")
        outputs = []
        self.arrays[name + "_syndromes"] = syndrome
        self.arrays[name + "_logical_labels"] = labels
        with tempfile.TemporaryDirectory(prefix="stim-boundary-") as temp:
            root = Path(temp)
            payload = root / "decoder_inputs.npz"
            np.savez_compressed(payload, h_data=h.data, h_indices=h.indices, h_indptr=h.indptr,
                                h_shape=h.shape, probabilities=probabilities, syndromes=syndrome)
            process_error = None
            try:
                result = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), "--worker",
                                         str(payload), str(root), profile, str(seed)],
                                        cwd=root, capture_output=True, text=True,
                                        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
                if result.returncode:
                    process_error = result.stderr or f"Worker exit {result.returncode}"
            except Exception:
                process_error = traceback.format_exc()
            audit_path = root / "audit.json"
            audit = json.loads(audit_path.read_text()) if audit_path.exists() else {"errors": [{"error": process_error}]}
            audit["panel"] = name
            self.audits.append(audit)
            if not process_error and not audit.get("errors"):
                require(audit["probability_hash"] == ah(probabilities), "Worker probability payload differs from static DEM")
                require(audit["h_hash"] == ah(h.data) + ":" + ah(h.indices) + ":" + ah(h.indptr), "Worker H differs from static graph")
                require([r["syndrome_hash"] for r in audit["invocations"]] == [ah(s) for s in syndrome], "Actual decoder syndromes differ from scheduled inputs")
            for i in range(n):
                row = dict(panel=name, shot=i, profile=profile, decoder_seed=seed,
                           detector_weight=int(syndrome[i].sum()), error="")
                output = root / f"{i}.npz"
                if not output.exists():
                    row.update(error=process_error or json.dumps(audit.get("errors")), success=False,
                               syndrome_valid=False, logical_match=False, converged=False)
                    count["exception_shots"] += 1
                    outputs.append(None)
                else:
                    with np.load(output) as z:
                        record = {k: z[k].copy() for k in z.files}
                    count["decoded_shots"] += 1
                    self.arrays[f"{name}_correction_{i}"] = record["correction"]
                    self.arrays[f"{name}_residual_{i}"] = record["residual"]
                    try:
                        row.update(self.score(h, a, record["correction"], syndrome[i], labels[i]),
                                   converged=bool(record["converged"]), iterations=int(record["iterations"]),
                                   correction_hash=ah(record["correction"]))
                        require(row["converged"] == row["syndrome_valid"], "Decoder convergence disagrees with H correction check")
                        expected_residual = (h @ record["correction"]) % 2 ^ syndrome[i]
                        require(np.array_equal(record["residual"], expected_residual), "Decoder residual disagrees with independent check")
                        count["scored_shots"] += 1
                    except Exception:
                        row.update(error=traceback.format_exc(), success=False)
                        count["exception_shots"] += 1
                    outputs.append(record)
                self.rows.append(row)
            require(not process_error and not audit.get("errors") and count["exception_shots"] == 0,
                    f"Panel {name} retained failed/missing shots: {count}")
        print(f"panel {name}: {n} shots decoded and scored", flush=True)
        return outputs

    def candidate(self, name, h, a, correction, syndrome, logical):
        score = self.score(h, a, correction, syndrome, logical)
        self.arrays[f"candidate_{name}"] = correction
        return dict(candidate=name, correction_hash=ah(correction), **score)


def bitvector(values):
    value = 0
    for i in np.flatnonzero(values):
        value |= 1 << int(i)
    return value


def unpack_bits(value, length):
    out = np.zeros(length, np.uint8)
    while value:
        bit = value & -value
        out[bit.bit_length() - 1] = 1
        value ^= bit
    return out


def solve_augmented(h, a, syndrome, logical):
    """GF(2) column elimination on actual [H; A], with a correction witness.

    Scoring-only construction. Never supplied as a decoder input or feedback.
    """
    matrix = sparse.vstack([h, a], format="csc")
    target = bitvector(np.concatenate([syndrome, logical]))
    pivots = {}
    for column in range(matrix.shape[1]):
        v = sum(1 << int(r) for r in matrix.indices[matrix.indptr[column]:matrix.indptr[column + 1]])
        combination = 1 << column
        while v:
            pivot = v.bit_length() - 1
            if pivot not in pivots:
                pivots[pivot] = (v, combination)
                break
            old, old_combination = pivots[pivot]
            v ^= old
            combination ^= old_combination
        # Attempt solving only when rank increased, avoiding dense factorization.
        if v:
            remaining, solution = target, 0
            while remaining and remaining.bit_length() - 1 in pivots:
                old, old_combination = pivots[remaining.bit_length() - 1]
                remaining ^= old
                solution ^= old_combination
            if not remaining:
                return unpack_bits(solution, h.shape[1]), {"columns_examined": column + 1, "rank": len(pivots)}
    raise ValueError(f"NOT-CONSTRUCTED: target outside span of actual [H;A]; rank={len(pivots)}")


def main():
    campaign = Campaign()
    summary = dict(provenance={}, circuit_metadata={}, decoder_metadata={}, case_results=[],
                   shot_accounting={}, warnings=[
                       "Small fixed panels and truncated budgets: no LER, performance, N=4, or N×P claim.",
                       "Current decoder is tested; historical decoder/hash reconciliation remains outstanding.",
                       "Process/input isolation and runtime tracing are not an adversarial OS security sandbox.",
                       "Initial attempt rejected STIM's own lossy DEM text roundtrip; preserved in attempt_001_dem_roundtrip. Exact serialized DEM and NPZ incidence/probability checks replace inappropriate in-memory roundtrip equality.",
                       "Noiseless samples use the original static DEM priors; high-noise samples use a newly derived matching DEM.",
                       "Shuffled syndromes have no physical label pairing; their scores are diagnostic only."], overall_status="FAIL")
    try:
        circuit = stim.Circuit.from_file(str(PACKAGE / "circuit.stim"))
        summary["provenance"] = dict(git_head=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
                                     git_status_at_start=subprocess.check_output(["git", "status", "--short"], cwd=REPO, text=True),
                                     python=sys.version, stim_version=stim.__version__, numpy_version=np.__version__,
                                     circuit_path=str(PACKAGE / "circuit.stim"), circuit_sha256=sha(PACKAGE / "circuit.stim"),
                                     package_sha256=sha(PACKAGE / "package.json"), validation_script_sha256=sha(__file__),
                                     scoring_implementation_path=str(SCORER), scoring_sha256=sha(SCORER),
                                     scoring_assignment_lines=campaign.scorer_lines)
        summary["canonical_invocation_audit"] = canonical_invocation_audit()
        summary["circuit_metadata"] = circuit_metadata(circuit)
        summary["decoder_metadata"] = dict(implementation_path=str(DECODER), implementation_sha256=sha(DECODER),
                                            profiles=PROFILES, normal_S=1, seed_probe_S=2,
                                            decoder_seed=DECODER_SEED, stim_seed=SEED,
                                            rng_lifetime="one persistent decoder RNG per panel, identical shot order on replay")
        h, a, probabilities, dem = dem_graph(circuit)
        summary["circuit_metadata"].update(dem_fault_count=dem.num_errors, detector_edges=h.nnz)
        with np.load(PACKAGE / "edge_lists.npz") as z:
            de, oe = z["detector_edges"], z["observable_edges"]
            stored_h = sparse.csr_matrix((np.ones(len(de), np.uint8), (de[:, 1], de[:, 0])), shape=h.shape)
            stored_a = sparse.csr_matrix((np.ones(len(oe), np.uint8), (oe[:, 1], oe[:, 0])), shape=a.shape)
        with np.load(PACKAGE / "faults.npz") as z:
            require(np.array_equal(probabilities, z["probabilities"]), "Circuit DEM and package probabilities differ")
        require((h != stored_h).nnz == 0 and (a != stored_a).nnz == 0, "Circuit DEM and package incidence differ")
        saved_dem = stim.DetectorErrorModel.from_file(str(PACKAGE / "detector_error_model.dem"))
        require(str(dem) == str(saved_dem), "Saved DEM text differs from circuit-derived DEM text")
        summary["provenance"]["dem_text_roundtrip"] = dict(
            serialized_equal=True, in_memory_equal=dem == saved_dem,
            maximum_error_probability_delta=max(abs(x.args_copy()[0] - y.args_copy()[0])
                                                for x, y in zip(dem, saved_dem) if x.type == "error"),
            note="Builder writes str(dem). NPZ probabilities and both incidence matrices were separately checked exactly.")
        summary["provenance"]["package_rederived_exactly"] = True

        noiseless = circuit.without_noise()
        require(all(getattr(noiseless, k) == getattr(circuit, k) for k in
                    ("num_qubits", "num_measurements", "num_detectors", "num_observables")), "Noiseless structure count mismatch")
        zs, zl = noiseless.compile_detector_sampler(seed=SEED).sample(16, separate_observables=True)
        summary["circuit_metadata"]["noiseless_sha256"] = hashlib.sha256(str(noiseless).encode()).hexdigest()
        # Stop, rather than adapt expected outcomes, if noiseless semantics fail.
        require(not zs.any() and not zl.any(), "STOP: actual noiseless circuit produced detector/observable flips")
        zero = campaign.panel("noiseless", h, a, probabilities, zs, zl)
        campaign.case("noiseless_circuit", 16, "Actual noiseless circuit has zero events and every correction succeeds",
                      lambda: require(all(r["success"] for r in campaign.rows if r["panel"] == "noiseless"), "False noiseless failure") or "16/16 successful; zero detector and logical flips")

        ss, ll = circuit.compile_detector_sampler(seed=SEED).sample(4, separate_observables=True)
        ss, ll = ss.astype(np.uint8), ll.astype(np.uint8)
        original = campaign.panel("original", h, a, probabilities, ss, ll)
        # Logical-label mutation is made in the parent before the isolated replay.
        altered_labels = ll.copy(); altered_labels[:, 0] ^= 1
        rs, rl = circuit.compile_detector_sampler(seed=SEED).sample(4, separate_observables=True)
        repeat = campaign.panel("repeat", h, a, probabilities, rs.astype(np.uint8), rl.astype(np.uint8))

        def equal_outputs(left, right):
            return all(all(np.array_equal(x[k], y[k]) for k in ("correction", "converged", "iterations", "residual"))
                       for x, y in zip(left, right))

        def label_test():
            require(equal_outputs(original, repeat), "Identical decoder payload replay changed outputs")
            comparisons = []
            for i, output in enumerate(original):
                before = campaign.score(h, a, output["correction"], ss[i], ll[i])
                after = campaign.score(h, a, output["correction"], ss[i], altered_labels[i])
                comparisons.append(dict(shot=i, original=before, altered=after))
            summary["label_isolation_comparisons"] = comparisons
            campaign.arrays["altered_scoring_labels"] = altered_labels
            require(any(x["original"]["logical_match"] != x["altered"]["logical_match"] for x in comparisons), "Label perturbation did not exercise changed scoring")
            return "Corrections, convergence, iterations and residuals identical; scoring-side label changes detected"

        campaign.case("logical_label_isolation", 4, "Only scoring may change when labels change", label_test)
        campaign.case("same_seed_reproducibility", 4, "Samples and decoder outputs bit-exact",
                      lambda: require(np.array_equal(ss, rs) and np.array_equal(ll, rl) and equal_outputs(original, repeat),
                                      "Same-seed mismatch") or "All sample bits, corrections, convergence, iterations and residuals match")
        ds, dl = circuit.compile_detector_sampler(seed=SEED + 1).sample(4, separate_observables=True)
        campaign.arrays.update(changed_stim_syndromes=ds, changed_stim_labels=dl)
        campaign.case("changed_stim_seed", 4, "Changed seed does not replay the identical sample panel",
                      lambda: require(not (np.array_equal(ss, ds) and np.array_equal(ll, dl)), "Changed seed panel identical") or "Changed STIM seed changes sample panel")

        permutation = np.random.default_rng(401).permutation(h.shape[0])
        shuffled = ss[:, permutation]
        campaign.arrays["detector_permutation"] = permutation
        corrupt = campaign.panel("shuffled", h, a, probabilities, shuffled, ll)

        def shuffle_test():
            require(not np.array_equal(ss, shuffled), "Permutation did not alter input")
            comparisons = []
            for i, (orig, bad) in enumerate(zip(original, corrupt)):
                oldscore = campaign.score(h, a, orig["correction"], ss[i], ll[i])
                diagnostic = campaign.score(h, a, bad["correction"], shuffled[i], ll[i])
                physical = campaign.score(h, a, bad["correction"], ss[i], ll[i])
                comparisons.append(dict(shot=i, same_correction=np.array_equal(orig["correction"], bad["correction"]),
                                        same_convergence=bool(orig["converged"] == bad["converged"]),
                                        same_residual=np.array_equal(orig["residual"], bad["residual"]),
                                        same_score=oldscore == diagnostic, original_score=oldscore,
                                        shuffled_diagnostic_score=diagnostic, against_original_sample=physical))
            summary["shuffled_comparisons"] = comparisons
            require(any(not x["same_correction"] or not x["same_residual"] for x in comparisons), "Corrupted syndromes silently treated as equivalent")
            return "Corrupted-input behavior differs; per-shot comparison retained; diagnostic labels are not a physical LER"

        campaign.case("shuffled_syndrome_negative_control", 4, "Unpermuted graph must not silently accept syndrome permutation as equivalent", shuffle_test)

        def invalid_test():
            require(ss[0].any(), "Fixed first real shot has zero syndrome; zero-correction control not exercised")
            valid, evidence = solve_augmented(h, a, ss[0], ll[0])
            flip = valid.copy(); column = int(np.flatnonzero(np.diff(h.tocsc().indptr))[0]); flip[column] ^= 1
            random = np.random.default_rng(402).integers(0, 2, h.shape[1], dtype=np.uint8)
            candidates = [("known_valid", valid), ("zero", np.zeros(h.shape[1], np.uint8)), ("one_bit_flip", flip), ("random", random)]
            scores = [campaign.candidate(name, h, a, c, ss[0], ll[0]) for name, c in candidates]
            summary["invalid_correction_evidence"] = dict(constructive_solve=evidence, scores=scores, shot=0)
            require(scores[0]["success"], "Constructed valid correction did not score success")
            require(all(not x["syndrome_valid"] and not x["success"] for x in scores[1:]), "Invalid correction accepted or negative fixture not exercised")
            return "Zero, one-bit-flipped, and deterministic random candidates are syndrome-invalid and unsuccessful; valid reference succeeds"

        campaign.case("invalid_correction_scoring", 1, "Invalid corrections never score success; no decoder involved", invalid_test)

        def wrong_logical():
            wrong = ll[0].copy(); wrong[0] ^= 1
            try:
                candidate, evidence = solve_augmented(h, a, ss[0], wrong)
            except ValueError as error:
                return "WARNING", "UNSATISFIED/NOT-CONSTRUCTED", str(error)
            score = campaign.candidate("syndrome_valid_logically_wrong", h, a, candidate, ss[0], ll[0])
            summary["wrong_logical_evidence"] = dict(constructive_solve=evidence, score=score, flipped_logical_index=0, shot=0)
            require(score["syndrome_valid"] and not score["logical_match"] and not score["success"], "Wrong-logical candidate not rejected correctly")
            return "Actual [H;A] GF(2) solution: syndrome_valid=true, logical_match=false, success=false"

        campaign.case("syndrome_valid_logically_wrong", 1, "Syndrome-valid wrong logical action must fail", wrong_logical)
        tiny = campaign.panel("tiny_budget", h, a, probabilities, ss, ll, "tiny")

        def nonconvergence():
            rows = [r for r in campaign.rows if r["panel"] == "tiny_budget"]
            failures = [r for r in rows if not r["converged"]]
            require(len(rows) == 4 and failures and all(not r["success"] for r in failures), "Non-convergence accounting not exercised or incorrect")
            return f"{len(failures)} non-converged shots counted as failures; denominator remains 4"

        campaign.case("nonconvergence_accounting", 4, "One-iteration failures stay in denominator", nonconvergence)
        probe0 = campaign.panel("seed_probe_91", h, a, probabilities, ss[:2], ll[:2], "seed_probe", 91)
        probe1 = campaign.panel("seed_probe_92", h, a, probabilities, ss[:2], ll[:2], "seed_probe", 92)

        def seed_test():
            x, y = campaign.audits[-2:]
            require(all(r["result_seed"] == 91 for r in x["invocations"]) and all(r["result_seed"] == 92 for r in y["invocations"]), "Seed did not reach decoder metadata")
            require(x["invocations"][0]["rng_before"] != y["invocations"][0]["rng_before"], "RNG states identical for changed seed")
            require(all(r["rng_before"] != r["rng_after"] for audit in (x, y) for r in audit["invocations"]), "Randomized relay leg was not exercised")
            require(x["invocations"][0]["gamma_summaries"] != y["invocations"][0]["gamma_summaries"], "Changed RNG did not change sampled gamma evidence")
            return f"Seed reaches instance/result/RNG state and randomized relay leg; corrections identical={equal_outputs(probe0, probe1)} (not required to differ)"

        campaign.case("changed_decoder_seed", 2, "Seed propagates into actual RNG state; output changes not mandatory", seed_test)
        elevated = high_noise(circuit, 0.02)
        hh, ha, hp, _ = dem_graph(elevated)
        hs, hl = elevated.compile_detector_sampler(seed=SEED).sample(4, separate_observables=True)
        summary["high_noise_metadata"] = circuit_metadata(elevated) | {"circuit_sha256": hashlib.sha256(str(elevated).encode()).hexdigest(),
                                                                      "dem_fault_count": hh.shape[1], "probability_hash": ah(hp)}
        campaign.panel("high_noise", hh, ha, hp, hs.astype(np.uint8), hl.astype(np.uint8))

        def destructive():
            rows = [r for r in campaign.rows if r["panel"] == "high_noise"]
            result = dict(detector_weights=[r["detector_weight"] for r in rows],
                          convergence_rate=sum(r["converged"] for r in rows) / 4,
                          logical_failure_count=sum(not r["success"] for r in rows),
                          nonconvergence_count=sum(not r["converged"] for r in rows),
                          noiseless_detector_weights=zs.sum(axis=1).tolist())
            summary["high_noise_observations"] = result
            require(any(result["detector_weights"]) and result["logical_failure_count"] > 0, "Elevated noise did not produce destructive behavior under this fixed control")
            return json.dumps(result)

        campaign.case("high_noise_destructive_control", 4, "Elevated noise produces events and at least one failure under fixed bounded settings", destructive)

        def boundary():
            require(len(campaign.audits) == len(campaign.accounting), "Missing worker audits")
            for audit in campaign.audits:
                n = campaign.accounting[audit["panel"]]["scheduled_shots"]
                require(not audit["errors"] and len(audit["invocations"]) == n, "Boundary trace missing or failed")
                require(audit["call_arguments"] == ["prior", "syndrome"] and audit["decoder_sha256"] == sha(DECODER), "Decoder invocation boundary differs")
            return "Every actual decode call traced; isolated allowlisted payload has static H/probabilities and syndrome only; labels/A/candidate truth excluded"

        campaign.case("information_boundary", sum(c["scheduled_shots"] for c in campaign.accounting.values()),
                      "Automatically establish legitimate-only actual invocation", boundary)
    except Exception:
        summary["fatal_error"] = traceback.format_exc()
        print(summary["fatal_error"], flush=True)
    finally:
        # Always serialize every scheduled shot, including exceptions. No result-dependent filtering.
        for name, counts in campaign.accounting.items():
            existing = {r["shot"] for r in campaign.rows if r["panel"] == name}
            for i in range(counts["scheduled_shots"]):
                if i not in existing:
                    campaign.rows.append(dict(panel=name, shot=i, success=False, error="Missing stage output; campaign failed"))
                    counts["exception_shots"] += 1
        fields = sorted({k for r in campaign.rows for k in r}) or ["panel", "shot", "error"]
        with (HERE / "per_shot_results.csv").open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader(); writer.writerows(campaign.rows)
        np.savez_compressed(HERE / "validation_evidence.npz", **campaign.arrays)
        with (HERE / "per_shot_results.csv").open(newline="") as f:
            saved = list(csv.DictReader(f))

        def accounting():
            for name, counts in campaign.accounting.items():
                records = [r for r in saved if r["panel"] == name]
                counts["saved_shots"] = len(records)
                require(sorted(int(r["shot"]) for r in records) == list(range(counts["scheduled_shots"])), "Missing or duplicate saved shot IDs")
                require(len({counts[k] for k in ("scheduled_shots", "sampled_shots", "decoded_shots", "scored_shots", "saved_shots")}) == 1,
                        f"Stage counts differ: {name}: {counts}")
                require(counts["exception_shots"] == counts["timeout_shots"] == 0, "Exceptions/timeouts recorded; validation failed")
            require(bool(campaign.accounting), "No campaign panels executed")
            return f"{len(saved)} invocation records read back; all five stage counts and shot IDs agree; failures retained"

        campaign.case("no_postselection_or_dropped_shots", len(saved), "All scheduled/sample/decode/score/save counts equal", accounting)
        present = {r["case_name"] for r in campaign.cases}
        for name in CASE_NAMES:
            if name not in present:
                campaign.cases.append(dict(case_name=name, status="FAIL", shots=0, expected_behavior="Required validation executes",
                                           observed_behavior="NOT RUN: prerequisite failed", notes=summary.get("fatal_error", "Unknown prerequisite error")))
        campaign.cases.sort(key=lambda r: CASE_NAMES.index(r["case_name"]))
        summary.update(case_results=campaign.cases, shot_accounting=campaign.accounting, boundary_audits=campaign.audits)
        summary["predeclared_decoder_schedule"] = SCHEDULE
        summary["auxiliary_sampling"] = {"changed_stim_seed": {"scheduled": 4, "purpose": "sampling-only reproducibility; not a decoder/LER panel"}}
        summary["overall_status"] = "FAIL" if summary.get("fatal_error") or any(r["status"] == "FAIL" for r in campaign.cases) else "PASS_WITH_WARNINGS"
        summary["safe_for_performance_campaign"] = False
        summary["performance_gate_reason"] = "Small controls do not reconcile historical source hashes, interrupted LER batches, fixed-point/N-lane equivalence, or benchmark protocol."
        summary["artifacts"] = {p.name: sha(p) for p in [HERE / "per_shot_results.csv", HERE / "validation_evidence.npz"]}
        with (HERE / "validation_cases.csv").open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["case_name", "status", "shots", "expected_behavior", "observed_behavior", "notes"])
            writer.writeheader(); writer.writerows(campaign.cases)
        dump(HERE / "validation_summary.json", summary)
        print("\n=== STIM PIPELINE VALIDATION ===")
        for case in campaign.cases:
            print(f"{case['case_name']}: {case['status']}")
        print(f"OVERALL: {summary['overall_status']}")
    return 1 if summary["overall_status"] == "FAIL" else 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        worker(Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4], int(sys.argv[5]))
    else:
        raise SystemExit(main())
