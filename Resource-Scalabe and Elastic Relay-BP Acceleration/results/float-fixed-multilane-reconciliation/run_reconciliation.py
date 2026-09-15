#!/usr/bin/env python3
"""Frozen-source, saved-input numerical and N=2 reconciliation. No STIM sampling."""
from __future__ import annotations

import os
# Keep independent bounded workers from oversubscribing BLAS threads.
for _name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ[_name] = "1"
import ast
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
import difflib
import hashlib
import importlib.util
import inspect
import json
import multiprocessing
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import traceback

import numpy as np
from scipy import sparse

OUT = Path(__file__).resolve().parent
PROJECT = OUT.parents[1]
REPO = PROJECT.parent
FLOAT = PROJECT / "reference/relay_bp_float.py"
FIXED = PROJECT / "reference/relay_bp_fixed.py"
N2 = PROJECT / "results/n1-vs-n2-hardware-latency/run_study.py"
RNG = PROJECT / "fpga/verification/parallel_n2/gamma_rng_reference.py"
SAMPLES = PROJECT / "results/circuit-level-multiseed/paired_samples.npz"
ARCHIVE = N2.parent / "per_shot_results.csv"
PACKAGE = PROJECT / "graphs/generated/gross_circuit_level/memory_Z_r12_p0p003"
RESCUES = [(20260809, 18), (20260810, 26), (20260811, 26)]
SUBSET = [(20260809, i) for i in range(30)] + RESCUES[1:]
sys.path.insert(0, str(FLOAT.parent))
from relay_bp_float import FloatRelayBPDecoder, RelayLegConfig
from relay_bp_fixed import FixedRelayBPDecoder, FixedRelayConfig, FixedRelayLegConfig
from fixedpoint import FixedConfig


def require(ok, message):
    if not ok:
        raise AssertionError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bits_hash(a):
    return hashlib.sha256(np.packbits(np.asarray(a, np.uint8)).tobytes()).hexdigest()


def array_hash(a):
    a = np.ascontiguousarray(a)
    return hashlib.sha256(str((a.shape, a.dtype.str)).encode() + a.tobytes()).hexdigest()


def plain(x):
    if isinstance(x, np.generic):
        return x.item()
    if isinstance(x, np.ndarray):
        return x.tolist()
    if isinstance(x, Path):
        return str(x)
    raise TypeError(type(x).__name__)


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, default=plain, allow_nan=False) + "\n")


def read_csv(path):
    with Path(path).open(newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fields=None):
    fields = fields or list(dict.fromkeys(k for row in rows for k in row)) or ["status"]
    with Path(path).open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def round_nearest(x):
    return (np.sign(x) * np.floor(np.abs(x) + 0.5)).astype(np.int64)


def round_div16(x):
    return np.where(x < 0, -((np.abs(x) + 8) // 16), (np.abs(x) + 8) // 16).astype(np.int64)


def graph():
    with np.load(PACKAGE / "edge_lists.npz") as z:
        de, oe = z["detector_edges"], z["observable_edges"]
    with np.load(PACKAGE / "faults.npz") as z:
        p = z["probabilities"]
    h = sparse.csr_matrix((np.ones(len(de), np.uint8), (de[:, 1], de[:, 0])), shape=(1728, len(p)))
    a = sparse.csr_matrix((np.ones(len(oe), np.uint8), (oe[:, 1], oe[:, 0])), shape=(12, len(p)))
    return h, a, np.log((1 - p) / p)


def score(h, a, decision, syndrome, logical):
    valid = np.array_equal(np.asarray(h @ decision).ravel() & 1, syndrome)
    match = np.array_equal(np.asarray(a @ decision).ravel() & 1, logical)
    return dict(syndrome_valid=bool(valid), logical_match=bool(match), success=bool(valid and match),
                outcome_class="NONCONVERGED" if not valid else "VALID_CORRECT" if match else "VALID_LOGICAL_FAILURE")


def signature(legs):
    digest = hashlib.sha256()
    for leg in legs:
        digest.update(str(leg.max_iterations).encode())
        digest.update(np.asarray(leg.gamma, dtype=np.float64).tobytes())
    return digest.hexdigest()


class ArithmeticAudit:
    """Independent integer transition oracle; observes but never mutates decoder arrays.

    Check updates use segmented reductions; variable sums use integer add.at,
    not the decoder's check loop or floating-point bincount implementation.
    """
    def __init__(self, h, prior, syndrome, legs, float_events=None):
        self.h, self.prior, self.syndrome, self.legs = h, prior, syndrome, legs
        self.ev = h.indices
        self.ec = np.repeat(np.arange(h.shape[0]), np.diff(h.indptr))
        self.starts = h.indptr[:-1]
        self.degree = np.diff(h.indptr)
        require(np.all(self.degree > 0), "Oracle needs nonempty checks")
        self.prior_q = np.clip(round_nearest(prior), -131072, 131071)
        self.previous = self.prior_q.copy()
        self.nu = None
        self.leg = -1
        self.count = 0
        self.errors = []
        self.events = []
        self.saturation_events = []
        self.float_events = float_events
        self.first_decision_divergence = None
        self.first_numerical_evidence = None
        self.saturation_totals = dict(physical_prior=int(np.count_nonzero(round_nearest(prior) != self.prior_q)),
                                      lambda_bias=0, check_messages=0, guard_accumulator=0,
                                      variable_messages=0, marginals=0)
        self.max_integer_magnitude = 0
        self.rtl_stage_divergences = []

    def checks(self, nu, syndrome, fixed):
        magnitude = np.abs(nu)
        minimum = np.minimum.reduceat(magnitude, self.starts)
        is_min = magnitude == minimum[self.ec]
        nmin = np.add.reduceat(is_min.astype(np.int64), self.starts)
        sentinel = np.iinfo(np.int64).max if fixed else np.finfo(float).max
        second = np.minimum.reduceat(np.where(is_min, sentinel, magnitude), self.starts)
        outgoing = np.where(is_min & (nmin[self.ec] == 1), second[self.ec], minimum[self.ec])
        negative = (nu < 0).astype(np.int64)
        nnegative = np.add.reduceat(negative, self.starts)
        sign = 1 - 2 * ((syndrome[self.ec].astype(np.int64) + nnegative[self.ec] - negative) & 1)
        outgoing = sign * outgoing
        single = self.degree[self.ec] == 1
        outgoing[single] = sign[single] * (131071 if fixed else np.finfo(float).max)
        return outgoing

    def clipped(self, x, category, lo=-131072, hi=131071):
        self.saturation_totals[category] += int(np.count_nonzero((x < lo) | (x > hi)))
        self.max_integer_magnitude = max(self.max_integer_magnitude, int(np.max(np.abs(x), initial=0)))
        return np.clip(x, lo, hi)

    def __call__(self, event):
        li, it = int(event["leg_index"]), int(event["iteration"])
        before = dict(self.saturation_totals)
        if li != self.leg:
            self.nu = self.prior_q[self.ev].copy()
            self.leg = li
        gamma = np.asarray(self.legs[li].gamma)
        if gamma.ndim == 0:
            gamma = np.full(self.h.shape[1], gamma)
        encoded = round_nearest(gamma * 16)
        numerator = (16 - encoded) * self.prior_q + encoded * self.previous
        self.max_integer_magnitude = max(self.max_integer_magnitude, int(np.max(np.abs(numerator))))
        bias = self.clipped(round_div16(numerator), "lambda_bias")
        mu_raw = self.checks(self.nu, self.syndrome, True)
        # Degree-one checks bypass _sat in the actual implementation.
        mu = self.clipped(mu_raw, "check_messages")
        incoming = np.zeros(self.h.shape[1], np.int64)
        np.add.at(incoming, self.ev, mu)
        incoming = self.clipped(incoming, "guard_accumulator", -2097152, 2097151)
        nu = self.clipped(bias[self.ev] + incoming[self.ev] - mu, "variable_messages")
        marginal = self.clipped(bias + incoming, "marginals")
        decision = (marginal <= 0).astype(np.uint8)
        residual = (self.h @ decision) % 2 ^ self.syndrome
        expected = dict(gamma_int=encoded, lambda_bias=bias, check_to_var=mu,
                        var_to_check=nu, beliefs=marginal, decoded_error=decision, residual=residual)
        for key, value in expected.items():
            if not np.array_equal(value, event[key]):
                self.errors.append(dict(leg=li, iteration=it, field=key,
                                        maximum_delta=float(np.max(np.abs(value.astype(float) - event[key].astype(float))))))
        if any(self.saturation_totals[k] != event["saturation_counts"].get(k, 0) for k in self.saturation_totals):
            self.errors.append(dict(leg=li, iteration=it, field="saturation_counts"))
        delta = {k: self.saturation_totals[k] - before[k] for k in before if self.saturation_totals[k] != before[k]}
        if delta:
            self.saturation_events.append(dict(leg=li, iteration=it, global_iteration=event["global_iteration"], counts=delta))
        rtl_nu = np.clip(marginal[self.ev] - mu, -131072, 131071)
        if not np.array_equal(nu, rtl_nu):
            self.rtl_stage_divergences.append(dict(leg=li, iteration=it, edges=int(np.count_nonzero(nu != rtl_nu))))
        packed = np.packbits(decision)
        record = dict(leg=li, iteration=it, global_iteration=int(event["global_iteration"]),
                      decision_hash=bits_hash(decision), residual_weight=int(residual.sum()),
                      belief_min=int(marginal.min()), belief_max=int(marginal.max()))
        if self.float_events is not None and (li, it) in self.float_events:
            other = self.float_events[(li, it)]
            hd = int(np.unpackbits(packed ^ other["decision_packed"]).sum())
            record["float_decision_hamming"] = hd
            if hd and self.first_decision_divergence is None:
                self.first_decision_divergence = dict(leg=li, iteration=it, global_iteration=record["global_iteration"], hamming_distance=hd)
            if li == 0 and it == 1:
                self.first_numerical_evidence = dict(
                    prior_quantization_max=float(np.max(np.abs(self.prior - self.prior_q))),
                    prior_quantization_mean=float(np.mean(np.abs(self.prior - self.prior_q))),
                    first_bias_max_difference=float(np.max(np.abs(other["first_bias"] - bias))),
                    first_belief_max_difference=float(np.max(np.abs(other["first_beliefs"] - marginal))))
        self.events.append(record)
        self.nu, self.previous = nu, marginal
        self.count += 1


def result_fields(prefix, result, h, a, syndrome, logical):
    s = score(h, a, result.decoded_error, syndrome, logical)
    require(result.converged == s["syndrome_valid"], "Decoder convergence differs from independent syndrome check")
    require(np.array_equal(result.final_syndrome, (h @ result.decoded_error) % 2 ^ syndrome), "Decoder residual mismatch")
    return {prefix + k: v for k, v in dict(converged=result.converged, iterations=result.total_iterations,
                                          relay_legs=result.relay_legs, correction_hash=bits_hash(result.decoded_error), **s).items()}


def fixed_config(legs):
    return FixedRelayConfig(fixed=FixedConfig(b=18, g=4, M=16, clip=None, separate_scale=True), leg_configs=legs, S=1, R=32, seed=0)


def independent_winner(lanes):
    candidates = [(x["result_cycles"], i) for i, x in enumerate(lanes) if x["syndrome_converged"]]
    return min(candidates)[1] if candidates else -1


def shot_job(key):
    """Run actual N2 task independently from standalone fixed and float runs."""
    sample_seed, shot = key
    sid = f"{sample_seed}_{shot:03d}"
    module = load_module("current_n2", N2)
    h, a, prior = graph()
    with np.load(SAMPLES) as z:
        si = list(z["sample_seeds"]).index(sample_seed)
        syndrome = z["syndromes"][si, shot].astype(np.uint8)
        logical = z["observed_logicals"][si, shot].astype(np.uint8)
    syndrome.setflags(write=False); prior.setflags(write=False)
    seeds = module.seeds(sample_seed, shot)
    schedules = [module.gamma_legs(seed) for seed in seeds]
    evidence, traces, row = {}, {}, dict(shot_id=sid, sample_seed=sample_seed, shot=shot,
                                       syndrome_hash=bits_hash(syndrome), logical_hash=bits_hash(logical),
                                       lane0_seed=seeds[0], lane1_seed=seeds[1])
    float_events = {}
    float_first_oracle = {}

    def observe_float(event):
        li, it = int(event["leg_index"]), int(event["iteration"])
        record = dict(decision_packed=np.packbits(event["decoded_error"]),
                      residual_weight=int(event["residual"].sum()))
        if li == 0 and it == 1:
            record.update(first_bias=event["lambda_bias"].copy(), first_beliefs=event["beliefs"].copy())
            oracle = ArithmeticAudit(h, prior, syndrome, schedules[0][0])
            expected_mu = oracle.checks(prior[h.indices], syndrome, False)
            incoming = np.zeros(h.shape[1], float); np.add.at(incoming, h.indices, expected_mu)
            expected_bias = (1 - .125) * prior + .125 * prior
            float_first_oracle.update(bias_max_delta=float(np.max(np.abs(expected_bias - event["lambda_bias"]))),
                                      belief_max_delta=float(np.max(np.abs(expected_bias + incoming - event["beliefs"]))))
        float_events[(li, it)] = record

    fl = tuple(RelayLegConfig(x.max_iterations, gamma=x.gamma) for x in schedules[0][0])
    fdecoder = FloatRelayBPDecoder(h, leg_configs=fl, S=1, R=32, seed=0, iteration_callback=observe_float)
    fr = fdecoder.decode(prior, syndrome)
    print(f"{sid}: float complete ({fr.total_iterations} iterations)", flush=True)
    standalone, audits = [], []
    for lane in (0, 1):
        oracle = ArithmeticAudit(h, prior, syndrome, schedules[lane][0], float_events if lane == 0 else None)
        decoder = FixedRelayBPDecoder(h, fixed_config(schedules[lane][0]), iteration_callback=oracle)
        result = decoder.decode(prior, syndrome)
        standalone.append(result); audits.append(oracle)
        traces[f"lane{lane}"] = dict(iterations_checked=oracle.count, oracle_errors=oracle.errors,
                                     saturation_events=oracle.saturation_events, saturation_totals=oracle.saturation_totals,
                                     max_integer_magnitude=oracle.max_integer_magnitude,
                                     int64_overflow_events=0 if oracle.max_integer_magnitude < 2**63 else "UNKNOWN",
                                     rtl_saturation_order_divergences=oracle.rtl_stage_divergences,
                                     first_decision_divergence=oracle.first_decision_divergence,
                                     first_numerical_evidence=oracle.first_numerical_evidence, events=oracle.events)
        print(f"{sid}: standalone fixed lane {lane} complete ({result.total_iterations} iterations)", flush=True)
    row.update(result_fields("float_", fr, h, a, syndrome, logical))
    row.update(result_fields("fixed_", standalone[0], h, a, syndrome, logical))
    for lane, result in enumerate(standalone):
        row.update(result_fields(f"standalone_lane{lane}_", result, h, a, syndrome, logical))
    row.update(correction_hamming_distance=int(np.count_nonzero(fr.decoded_error != standalone[0].decoded_error)),
               same_final_correction=np.array_equal(fr.decoded_error, standalone[0].decoded_error),
               same_convergence_class=fr.converged == standalone[0].converged,
               same_logical_class=row["float_outcome_class"] == row["fixed_outcome_class"])
    aligned = signature(fl) == signature(schedules[0][0])
    numerical_explained = aligned and not any(o.errors for o in audits) and max(float_first_oracle.values()) <= 1e-12
    exact = row["same_final_correction"] and row["same_convergence_class"] and row["same_logical_class"] and fr.total_iterations == standalone[0].total_iterations and fr.relay_legs == standalone[0].relay_legs
    if not aligned:
        classification = "PARAMETER_MISMATCH"
    elif any(o.errors for o in audits):
        classification = "IMPLEMENTATION_MISMATCH"
    elif not row["same_convergence_class"]:
        classification = "CONVERGENCE_CLASS_CHANGE"
    elif not row["same_logical_class"]:
        classification = "LOGICAL_CLASS_CHANGE"
    elif exact:
        classification = "EXACT_MATCH"
    elif numerical_explained:
        classification = "QUANTIZATION_ONLY"
    elif audits[0].first_decision_divergence:
        classification = "EARLY_DECISION_DIVERGENCE"
    else:
        classification = "UNRESOLVED"
    row.update(classification=classification, numerical_origin_explained=numerical_explained,
               float_fixed_schedule_hash=signature(fl), first_float_oracle_max_delta=max(float_first_oracle.values()))

    captured, calls = [], []

    def trace(frame, event, arg):
        if event == "call" and frame.f_code is FixedRelayBPDecoder.decode.__code__:
            actual = frame.f_locals
            require(set(actual) == {"self", "prior", "syndrome", "trace_path"}, "Unexpected N2 decoder entry inputs")
            lane = len(calls)
            require(lane < 2, "Unexpected third N2 decoder")
            require(np.array_equal(actual["prior"], prior) and np.array_equal(actual["syndrome"], syndrome), "N2 inputs differ from standalone inputs")
            d = actual["self"]
            require((d.h_matrix != h).nnz == 0 and d.R == 32 and d.S == 1 and d.seed == 0 and d.fixed == fixed_config(schedules[lane][0]).fixed,
                    "N2 decoder configuration differs")
            require(signature(d.config.leg_configs) == signature(schedules[lane][0]), "N2 lane schedule differs")
            require(d.iteration_callback is None and actual["trace_path"] is None, "N2 decode unexpectedly instrumented")
            calls.append(dict(lane=lane, actual_arguments=sorted(k for k in actual if k != "self"),
                              syndrome_hash=bits_hash(actual["syndrome"]), prior_hash=array_hash(actual["prior"]),
                              schedule_hash=signature(d.config.leg_configs)))
        if event == "return" and frame.f_code is module.decode_one.__code__:
            captured.append(arg)

    try:
        sys.setprofile(trace)
        ensemble = module.task((si, shot, sample_seed, syndrome, logical))
    finally:
        sys.setprofile(None)
    require(len(captured) == len(calls) == 2, "Did not observe exactly two actual N2 lane calls")
    for lane, (actual, expected) in enumerate(zip(captured, standalone)):
        agrees = (np.array_equal(actual["decision"], expected.decoded_error) and
                  actual["syndrome_converged"] == int(expected.converged) and
                  actual["iterations"] == expected.total_iterations and actual["legs"] == expected.relay_legs)
        row[f"lane{lane}_standalone_agreement"] = agrees
        row[f"lane{lane}_completion_cycles"] = actual["result_cycles"]
        evidence[f"multilane_lane{lane}_correction"] = actual["decision"]
    winner = independent_winner(captured)
    row.update(selected_winner=ensemble["winner"], independent_winner=winner,
               arbiter_agreement=winner == ensemble["winner"], ensemble_failure=bool(ensemble["global_failure"]),
               ensemble_success=bool(ensemble["n2_logical_correct"]), ensemble_syndrome_valid=bool(ensemble["n2_syndrome_converged"]),
               both_failed_reported_correctly=bool(ensemble["global_failure"]) == all(not x["syndrome_converged"] for x in captured),
               any_valid_reported_correctly=bool(ensemble["n2_syndrome_converged"]) == any(x["syndrome_converged"] for x in captured),
               ensemble_modeled_cycles=ensemble["n2_cycles"], rescue=bool(ensemble["parallel_rescue"]))
    evidence.update(float_correction=fr.decoded_error, fixed_lane0_correction=standalone[0].decoded_error,
                    fixed_lane1_correction=standalone[1].decoded_error, syndrome=syndrome, logical=logical)
    traces.update(actual_n2_calls=calls, float_first_iteration_oracle=float_first_oracle,
                  float_events=[dict(leg=li, iteration=it, decision_hash=hashlib.sha256(v["decision_packed"].tobytes()).hexdigest(),
                                     residual_weight=v["residual_weight"]) for (li, it), v in float_events.items()],
                  ensemble_raw=ensemble, lane_gamma_seeds=list(seeds))
    for key in ("first_bias", "first_beliefs"):
        evidence["float_" + key] = float_events[(0, 1)][key]
    write_json(OUT / "checkpoints" / f"{sid}.json", dict(row=row, trace=traces))
    np.savez_compressed(OUT / "checkpoints" / f"{sid}.npz", **evidence)
    return row


class DefaultPathNormalizer(ast.NodeTransformer):
    """Compare source ASTs with telemetry disabled and relay_handoff=True only.

    These transformations are documented, limited to observer/metadata code and
    the explicit default handoff branch. They do not normalize arithmetic.
    """
    removed = {"iteration_callback", "relay_handoff", "leg_gamma_summaries"}

    def visit_ImportFrom(self, node):
        if node.module == "typing":
            node.names = [n for n in node.names if n.name != "Callable"]
        return node

    def visit_arguments(self, node):
        defaults = [None] * (len(node.args) - len(node.defaults)) + list(node.defaults)
        kept = [(a, d) for a, d in zip(node.args, defaults) if a.arg not in self.removed]
        node.args = [a for a, d in kept]
        node.defaults = [d for a, d in kept if d is not None]
        kept_kw = [(a, d) for a, d in zip(node.kwonlyargs, node.kw_defaults) if a.arg not in self.removed]
        node.kwonlyargs = [a for a, d in kept_kw]; node.kw_defaults = [d for a, d in kept_kw]
        return self.generic_visit(node)

    def visit_If(self, node):
        if "self.iteration_callback" in ast.unparse(node.test):
            return None
        return self.generic_visit(node)

    def visit_IfExp(self, node):
        if ast.unparse(node.test) == "self.relay_handoff":
            return self.visit(node.body)
        return self.generic_visit(node)

    def visit_Assign(self, node):
        if any(ast.unparse(t) in {"self.iteration_callback", "self.relay_handoff", "leg_gamma_summaries"} for t in node.targets):
            return None
        return self.generic_visit(node)

    def visit_AnnAssign(self, node):
        if ast.unparse(node.target) == "leg_gamma_summaries":
            return None
        return self.generic_visit(node)

    def visit_Expr(self, node):
        if isinstance(node.value, ast.Call) and ast.unparse(node.value.func) == "leg_gamma_summaries.append":
            return None
        return self.generic_visit(node)

    def visit_Dict(self, node):
        removed = self.removed | {"saturation_counts"}
        keep = [(k, v) for k, v in zip(node.keys, node.values) if not (isinstance(k, ast.Constant) and k.value in removed)]
        node.keys = [k for k, v in keep]; node.values = [v for k, v in keep]
        return self.generic_visit(node)


def historical_reconciliation():
    objects = subprocess.check_output(["git", "rev-list", "--objects", "--all"], cwd=REPO, text=True).splitlines()
    reachable = {line.split()[0] for line in objects if "relay_bp_float.py" in line or "relay_bp_fixed.py" in line}
    fsck = subprocess.run(["git", "fsck", "--full", "--no-reflogs", "--unreachable"], cwd=REPO, capture_output=True, text=True)
    require(fsck.returncode == 0, "Git object integrity inspection failed")
    unreachable = {line.split()[-1] for line in fsck.stdout.splitlines() if line.startswith("unreachable blob ")}
    sources = {}
    for oid in sorted(reachable | unreachable):
        data = subprocess.check_output(["git", "cat-file", "blob", oid], cwd=REPO)
        sources[hashlib.sha256(data).hexdigest()] = (oid, data, oid in reachable)
    records = []
    for name, path in [("circuit-level-baseline", FLOAT), ("n1-vs-n2-hardware-latency", FIXED), ("paper-ler-reproduction-expanded", FLOAT)]:
        manifest_path = PROJECT / "results" / name / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        commit = manifest.get("git_commit", manifest.get("software", {}).get("git_commit"))
        expected = manifest.get("canonical_float_sha256", manifest.get("software", {}).get("canonical_float_source_sha256", manifest.get("hashes", {}).get("fixed_decoder")))
        at_commit = subprocess.run(["git", "show", f"{commit}:{path.relative_to(REPO)}"], cwd=REPO, capture_output=True)
        rec = dict(study=name, historical_commit=commit, historical_decoder_hash=expected,
                   current_decoder_hash=sha(path), manifest_sha256=sha(manifest_path),
                   recorded_commit_source_recoverable=at_commit.returncode == 0,
                   recorded_commit_source_matches_hash=hashlib.sha256(at_commit.stdout).hexdigest() == expected,
                   exact_source_recoverable=expected in sources)
        if expected not in sources:
            rec.update(classification="UNKNOWN", meaningful_differences="Exact historical source not recoverable; do not substitute recorded commit source")
        else:
            oid, historical, reachable_in_history = sources[expected]
            target = OUT / "historical_sources" / f"{name}_{path.name}.txt"
            target.write_bytes(historical)
            current = path.read_text()
            delta = "".join(difflib.unified_diff(historical.decode().splitlines(True), current.splitlines(True), fromfile=f"git-blob:{oid}", tofile=str(path)))
            diff_path = target.with_suffix(".diff")
            diff_path.write_text(delta)
            old_ast = DefaultPathNormalizer().visit(ast.parse(historical))
            new_ast = DefaultPathNormalizer().visit(ast.parse(current))
            equal = ast.dump(old_ast) == ast.dump(new_ast)
            rec.update(recovered_blob=oid, reachable_from_committed_file_history=reachable_in_history,
                       recovered_source_path=str(target), source_diff_path=str(diff_path),
                       normalized_default_path_ast_equal=equal,
                       classification=("PARAMETER_ONLY_CHANGE" if name == "circuit-level-baseline" else "NO_MEANINGFUL_CHANGE") if equal else "UNKNOWN",
                       meaningful_differences=("Adds disabled-by-default observation callbacks and metadata; baseline additionally adds relay_handoff switch with unchanged True default. Arithmetic AST unchanged after only documented observer/default-branch normalization."
                                               if equal else "Differences remain after documented default-path normalization; inspect saved source diff."))
        records.append(rec)
    return dict(studies=records, reachable_decoder_blobs_searched=len(reachable), unreachable_blobs_searched=len(unreachable),
                warning="Baseline exact source recovered from unreachable Git object, not the recorded commit. Copy preserved to prevent Git garbage collection loss.",
                normalization="Remove callback parameter/assignment/guarded call, Callable import, gamma-summary metadata, added trace saturation metadata; specialize relay_handoff=True. No arithmetic expressions removed.")


def implementation_inventory(head):
    paths = [FLOAT, FIXED, N2, RNG, PROJECT / "reference/fixedpoint.py", PROJECT / "reference/relay_reference.py",
             PROJECT / "results/parallel-trajectory-model/run_parallel_model.py",
             PROJECT / "simulations/parallel_relay/parallel_relay_decoder.py",
             PROJECT / "relay_models/parallel_lanes/parallel_lane_models.py",
             PROJECT / "fpga/model/parallel_relay_fpga_model.py", PROJECT / "fpga/model/relay_engine.py"]
    paths += sorted((PROJECT / "fpga/rtl").rglob("*.sv"))
    frozen = []
    for path in paths:
        committed = subprocess.check_output(["git", "show", f"{head}:{path.relative_to(REPO)}"], cwd=REPO)
        require(committed == path.read_bytes(), f"Source differs from frozen HEAD: {path}")
        frozen.append(dict(path=str(path), sha256=sha(path), git_head=head, matches_committed_bytes=True))
    return dict(selection_status="UNAMBIGUOUS_FOR_ARCHIVED_N2_SOFTWARE_PATH",
                selection_evidence="run_study.py imports canonical FixedRelayBPDecoder and hardware gamma_rng_reference; its raw CSV identifies all three requested rescues. RTL top and controller are recorded and separately checked, not substituted for software.",
                frozen_sources=frozen,
                selected=[
                    dict(role="float", path=str(FLOAT), entry_point="FloatRelayBPDecoder.decode(prior, syndrome)",
                         constructor_signature=str(inspect.signature(FloatRelayBPDecoder)), defaults=dict(S=1, R=301, first_limit=80, later_limit=60,
                         gamma_first=.125, gamma_later=[-.24,.66], seed=0, rng="persistent numpy default_rng per instance"),
                         stopping="syndrome-valid solution; collect S candidates or exhaust R", selection="minimum original-prior dot correction among valid candidates; S=1 here"),
                    dict(role="fixed", path=str(FIXED), entry_point="FixedRelayBPDecoder.decode(prior, syndrome)",
                         defaults=dict(b=4,g=2,M=8,S=1,R="None -> length of leg_configs",leg_configs="one leg, 10 iterations, gamma=0",seed=0),
                         study_configuration=dict(b=18,g=4,M=16,S=1,R=32,first_limit=80,later_limit=60),
                         alternatives=["BlockFloatingRelayBPDecoder", "SeparatedExponentRelayBPDecoder", "reference/relay_reference.py:FixedPointRelayBPDecoder (legacy)"],
                         stopping="H correction == syndrome; collect S or exhaust configured legs",selection="minimum unquantized input-prior dot correction among valid candidates"),
                    dict(role="multilane", path=str(N2), entry_point="task((seed_index, shot, sample_seed, syndrome, logical))",lane_entry="decode_one -> FixedRelayBPDecoder.decode",
                         defaults=dict(N=2,P=4,R=32,S=1,first_limit=80,later_limit=60,b=18,g=4,M=16),
                         gamma="first encoded 2/16; later hardware xorshift64 rejection mapping, encoded -4..11 divided by 16",
                         seed="seeds(sample_seed, shot) uses splitmix and independent s0/s1; internal NumPy seed=0 unused with explicit gamma arrays",
                         stopping="each lane syndrome-valid or budget exhausted; earliest valid modeled result cycle wins; ties lane0",
                         logical_labels="present in scoring wrapper only; actual decode invocation profiled separately")],
                alternatives=[
                    dict(path="fpga/rtl/relay_bp_parallel_n2_p4.sv",role="actual N2 RTL top",defaults="C=12,V=20,E=76,L=2,P=4,USE_INTERNAL_RNG=0; limits and gamma are input ports",scope="Not a 32-shot full RTL run; standalone arbiter and numerical RTL fixture executed"),
                    dict(path="results/parallel-trajectory-model/run_parallel_model.py",role="earlier canonical fixed software ensemble",settings="R32, gamma later [-.12,.54], NumPy seeds 9100+shot+engine*1000003, iteration-based selection; main also includes N4, not run"),
                    dict(path="fpga/model/parallel_relay_fpga_model.py",role="behavioral demo",reason="RelayEngine initializes heuristic residual from syndrome weight and lane bias; not canonical H-based decoder"),
                    dict(path="simulations/parallel_relay/parallel_relay_decoder.py",role="legacy threaded ensemble",reason="Legacy decoder/observation-model family; not current canonical hardware-seeded study"),
                    dict(path="relay_models/parallel_lanes/parallel_lane_models.py",role="re-export of legacy threaded and behavioral models"),
                    dict(path="reference/relay_bp_fixed.py",role="block-floating and separated-exponent alternatives",reason="Not instantiated by selected N2 run_study.py")])


def numerical_audit():
    values = np.array([-131073., -131072., -131071.5, -8.5, -1.5, -.5, -.49, 0, .49, .5, 1.5, 8.5, 131070.5, 131071., 131072.])
    small = sparse.csr_matrix(np.array([[1,1]], np.uint8))
    decoder = FixedRelayBPDecoder(small, fixed_config((FixedRelayLegConfig(1, gamma=.125),)))
    decoder._saturations = {}
    quantized = decoder._sat(round_nearest(values), "representative")
    gamma_values = np.array([-.24,-.21875,-.1875,0,.03125,.125,.66,.6875])
    gamma_integer = round_nearest(gamma_values * 16)
    integers = np.array([-25,-24,-23,-9,-8,-7,0,7,8,9,23,24,25], np.int64)
    actual_rounding = decoder._round_div_array(integers,16)
    require(np.array_equal(actual_rounding, round_div16(integers)), "Numerical rounding helper mismatch")
    rows = [dict(quantity="message_or_prior", value=x, encoded=q, reconstructed=q, absolute_error=abs(x-q), saturated=round_nearest(np.array([x]))[0] != q) for x,q in zip(values,quantized)]
    rows += [dict(quantity="gamma",value=x,encoded=q,reconstructed=q/16,absolute_error=abs(x-q/16),saturated=False) for x,q in zip(gamma_values,gamma_integer)]
    write_csv(OUT / "numerical_values.csv", rows)
    _,_,prior = graph(); qp=np.clip(round_nearest(prior),-131072,131071)
    return dict(priors_and_messages=dict(total_width=18,fractional_bits=0,range=[-131072,131071],rounding="nearest, ties away from zero",saturation="signed clamp; no modular wrap"),
                gamma=dict(rtl_width=5,fractional_bits=4,scale=16,hardware_encoded_range=[-4,11],python_storage="int64, no standalone 5-bit clamp; selected schedule remains representable"),
                intermediate_sums=dict(guard_width=22,fractional_bits=0,range=[-2097152,2097151],python_temporary="int64; bincount floating accumulation exact for these bounded integers"),
                normalization="none; no block-floating/normalization in selected class",
                representative_max_absolute_quantization_error=float(np.max(np.abs(values-quantized))),
                representative_mean_absolute_quantization_error=float(np.mean(np.abs(values-quantized))),
                representative_saturation_events=decoder._saturations["representative"],
                representative_overflow_events=0,representative_gamma_max_error=float(np.max(np.abs(gamma_values-gamma_integer/16))),
                actual_prior_max_error=float(np.max(np.abs(prior-qp))),actual_prior_mean_error=float(np.mean(np.abs(prior-qp))),
                actual_prior_saturation_events=int(np.count_nonzero(round_nearest(prior)!=qp)),
                rounding_inputs=integers.tolist(),rounding_outputs=actual_rounding.tolist(),
                overflow_definition="Out-of-range guard inputs are saturation events; int64 wrap checked against bounded integer magnitudes, not inferred from absence of warnings.")


def arbitration_controls():
    tree = ast.parse(N2.read_text())
    task = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="task")
    names={"successes","winner","n2cycles","selected"}
    nodes=[n for n in task.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in names for t in n.targets)]
    require(len(nodes)==4,"Cannot identify actual N2 arbitration statements")
    source="\n".join(ast.unparse(n) for n in nodes)
    require("logical" not in source,"Logical information appears in winner selection")
    subscript_keys={n.slice.value for node in nodes for n in ast.walk(node) if isinstance(n,ast.Subscript) and isinstance(n.slice,ast.Constant) and isinstance(n.slice.value,str)}
    require(subscript_keys <= {"result_cycles","syndrome_converged"},"Undeclared arbitration information dependency")
    code=compile(ast.Module(body=nodes,type_ignores=[]),str(N2),"exec")
    rows=[]
    for c0 in (0,1):
        for c1 in (0,1):
            for t0,t1 in [(10,20),(20,10),(10,10)]:
                for l0,l1 in [(0,0),(0,1),(1,0),(1,1)]:
                    lanes=[dict(syndrome_converged=c,result_cycles=t,logical_correct=l) for c,t,l in [(c0,t0,l0),(c1,t1,l1)]]
                    env=dict(e0=lanes[0],e1=lanes[1]);exec(code,env)
                    expected=independent_winner(lanes)
                    rows.append(dict(candidate0=c0,candidate1=c1,cycles0=t0,cycles1=t1,logical0=l0,logical1=l1,
                                     winner=env["winner"],expected_winner=expected,agreement=env["winner"]==expected))
    write_csv(OUT/"arbiter_controls.csv",rows)
    return dict(status="PASS" if all(r["agreement"] for r in rows) else "FAIL",cases=len(rows),actual_source=source,
                source_lines=[n.lineno for n in nodes],logical_label_dependency=False,
                coverage="both fail; each single success; both succeed at unequal times and ties; every combination of logical labels")


def rtl_controls():
    """Small existing arbiter test plus targeted saturation-order counterexample."""
    iv, vvp = shutil.which("iverilog"), shutil.which("vvp")
    if not iv or not vvp:
        return dict(status="NOT_RUN",reason="Icarus Verilog unavailable")
    tb = OUT/"tb_variable_saturation_reconciliation.sv"
    tb.write_text('''`timescale 1ns/1ps
module tb_variable_saturation_reconciliation;
 reg [3:0] degree=2; reg signed [17:0] physical_prior=0,previous_marginal=0;
 reg signed [4:0] gamma_q=0; reg signed [17:0] mu_in[0:1];
 wire signed [17:0] bias,marginal,nu_out[0:1],weight_contribution;
 wire signed [21:0] incoming_sum; wire hard_decision,accumulator_saturated,bias_saturated,marginal_saturated;
 wire [1:0] nu_saturated;
 relay_bp_variable_node_18 #(.MAX_DEGREE(2)) dut(.*);
 initial begin
  physical_prior=8;previous_marginal=8;mu_in[0]=2;mu_in[1]=3;
  #10; $display("NUMERIC 0 %0d %0d %0d %0d %0d",bias,incoming_sum,marginal,nu_out[0],nu_out[1]);
  physical_prior=131000;previous_marginal=131000;mu_in[0]=100;mu_in[1]=100;
  #10; $display("NUMERIC 1 %0d %0d %0d %0d %0d",bias,incoming_sum,marginal,nu_out[0],nu_out[1]);
  physical_prior=-131000;previous_marginal=-131000;mu_in[0]=-100;mu_in[1]=-100;
  #10; $display("NUMERIC 2 %0d %0d %0d %0d %0d",bias,incoming_sum,marginal,nu_out[0],nu_out[1]);
  $finish;
 end
endmodule
''')
    logs, commands = {}, []
    with tempfile.TemporaryDirectory(prefix="reconcile-rtl-") as temp:
        for name, top, sources in [
            ("arbiter","tb_relay_bp_first_success_arbiter_n2",[PROJECT/"fpga/rtl/relay_bp_first_success_arbiter_n2.sv",PROJECT/"fpga/testbench/tb_relay_bp_first_success_arbiter_n2.sv"]),
            ("variable","tb_variable_saturation_reconciliation",[PROJECT/"fpga/rtl/relay_bp_variable_node_18.sv",PROJECT/"fpga/rtl/relay_bp_bias18.sv",PROJECT/"fpga/rtl/relay_bp_round_div16.sv",PROJECT/"fpga/rtl/relay_bp_sat18.sv",tb])]:
            command=[iv,"-g2012","-DRELAY_BP_SIM_ASSERT","-s",top,"-o",str(Path(temp)/name),*map(str,sources)]
            commands.append(command)
            compiled=subprocess.run(command,capture_output=True,text=True,timeout=30)
            (OUT/f"rtl_{name}_compile.log").write_text(compiled.stdout+compiled.stderr)
            require(compiled.returncode==0,f"RTL {name} compile failed")
            command=[vvp,str(Path(temp)/name)];commands.append(command)
            simulation=subprocess.run(command,capture_output=True,text=True,timeout=30)
            logs[name]=simulation.stdout+simulation.stderr
            (OUT/f"rtl_{name}.log").write_text(logs[name])
            require(simulation.returncode==0,f"RTL {name} simulation execution failed")
    expected=[(8,[2,3]),(131000,[100,100]),(-131000,[-100,-100])]
    rows=[]
    for line in logs["variable"].splitlines():
        if not line.startswith("NUMERIC "):
            continue
        cid,bias,total,marginal,nu0,nu1=map(int,line.split()[1:])
        p,mu=expected[cid]
        fixed_nu=np.clip(p+sum(mu)-np.array(mu),-131072,131071)
        rtl_equation=np.clip(np.clip(p+sum(mu),-131072,131071)-np.array(mu),-131072,131071)
        rows.append(dict(case=cid,prior=p,mu=mu,rtl_bias=bias,rtl_sum=total,rtl_marginal=marginal,
                         rtl_nu=[nu0,nu1],fixed_equation_nu=fixed_nu.tolist(),
                         rtl_equation_verified=np.array_equal([nu0,nu1],rtl_equation),
                         software_rtl_equal=np.array_equal([nu0,nu1],fixed_nu),
                         classification="EXACT_MATCH" if np.array_equal([nu0,nu1],fixed_nu) else "IMPLEMENTATION_MISMATCH"))
    require(len(rows)==3,"Missing numerical RTL observations")
    write_json(OUT/"rtl_numerical_comparison.json",rows)
    return dict(status="PASS" if all(r["software_rtl_equal"] for r in rows) else "FAIL",
                arbiter_status="PASS" if "cases=7" in logs["arbiter"] and "failures=0" in logs["arbiter"] else "FAIL",
                numerical_cases=rows,commands=commands,
                scope="RTL arbiter and variable-node primitive only; not full Gross RTL decoding",
                source_evidence={"python":str(FIXED)+":256-260","rtl_primitive":str(PROJECT/"fpga/rtl/relay_bp_variable_node_18.sv")+":38",
                                 "rtl_integrated_controller":str(PROJECT/"fpga/rtl/relay_bp_variable_controller_p4.sv")+":100-103"},
                finding="Software forms nu from unclipped bias+sum; RTL subtracts mu from already saturated marginal. These operations differ at saturation and are not a scheduling difference. Candidate-weight arithmetic also uses rounded RTL priors vs original float input priors in software; S=1 avoids multi-candidate ranking here.")


def align_configuration(module):
    require((module.R,module.S,module.FIRST_LIMIT,module.LATER_LIMIT,module.P)==(32,1,80,60,4),
            "Frozen N2 study configuration differs from predeclared reconciliation")
    rows=[
        ("H","saved package detector/fault CSR","identical","identical","ALIGNED"),
        ("A","saved package logical-incidence CSR; scoring only","identical","identical","ALIGNED"),
        ("prior source","static DEM log((1-p)/p)","same input, rounded to integer","same fixed input","ALIGNED_SOURCE_NUMERIC_DIFFERENCE"),
        ("R",32,32,32,"ALIGNED"),
        ("S",1,1,1,"ALIGNED"),
        ("first iteration limit",80,80,80,"ALIGNED"),
        ("later iteration limit",60,60,60,"ALIGNED"),
        ("gamma","exact hardware-realized encoded vector /16","same vector; exactly representable","same vector for corresponding lane","ALIGNED"),
        ("trajectory seed","lane0 hardware s0; NumPy seed0 inactive","lane0 s0 / lane1 s1; NumPy seed0 inactive","s0/s1 from recorded sample ID","ALIGNED_PER_LANE"),
        ("relay handoff","previous leg final marginal","same with quantization","same fixed decoder","ALIGNED_SEMANTICS"),
        ("stopping","first syndrome-valid candidate or R exhaustion","same","each lane same; first valid modeled completion wins","ALIGNED_PER_LANE"),
        ("candidate validity","H e_hat = syndrome","same","same","ALIGNED"),
        ("candidate selection","S1 first valid; original-prior weight metadata","same","first valid result cycle; ties lane0","ENSEMBLE_RULE_DIFFERENT_BY_DESIGN"),
        ("numeric representation","float64","signed18 integer, signed22 guard, gamma /16","same software fixed format","EXPECTED_NUMERICAL_DIFFERENCE"),
    ]
    result=[dict(parameter=p,float=f,fixed=q,multilane=m,status=s) for p,f,q,m,s in rows]
    write_csv(OUT/"configuration_alignment.csv",result)
    return dict(rows=result,comparison_scope="Float vs fixed lane0 under exactly realized hardware gamma, not either constructor's unrelated defaults; fixed standalone lane0/lane1 vs actual N2 task separately.",
                direct_algorithm_configuration_equivalence=True,bit_identical_numeric_representation=False,
                warning="Does not compare ensemble outcome to single-lane outcome as an implementation error. Does not claim the full RTL datapath matches software.")


def compare_archive(rows):
    archive={(int(r['sample_seed']),int(r['shot'])):r for r in read_csv(ARCHIVE)}
    correction_sources=[PROJECT/"results/graph-partitioning-relaybp-equivalence-full/n1_paired_results.csv",
                        PROJECT/"results/graph-partitioning-relaybp-equivalence-full/e1_paired_results.csv"]
    correction_records=[{(int(r['sample_seed']),int(r['shot'])):r for r in read_csv(path)} for path in correction_sources]
    history=[]
    for row in rows:
        if "error" in row:
            continue
        key=(row['sample_seed'],row['shot']);old=archive[key]
        require(row['syndrome_hash']==old['detector_sample_hash'] and row['logical_hash']==old['logical_sample_hash'],"Archived sample identity mismatch")
        entry=dict(shot_id=row['shot_id'],same_sample_identity=True)
        for lane in (0,1):
            prefix=f"standalone_lane{lane}_";oldprefix=f"e{lane}_"
            entry[f"lane{lane}_same_success_class"]=row[prefix+'success']==bool(int(old[oldprefix+'logical_correct']))
            entry[f"lane{lane}_same_convergence_class"]=row[prefix+'converged']==bool(int(old[oldprefix+'syndrome_converged']))
            entry[f"lane{lane}_iteration_difference"]=row[prefix+'iterations']-int(old[oldprefix+'iterations'])
            entry[f"lane{lane}_relay_leg_difference"]=row[prefix+'relay_legs']-int(old[oldprefix+'legs'])
            supplement=correction_records[lane].get(key)
            if supplement and supplement['syndrome_hash']==row['syndrome_hash'] and int(supplement['gamma_seed'])==row[f'lane{lane}_seed']:
                same_hash=supplement['correction_hash']==row[prefix+'correction_hash']
                entry[f"lane{lane}_correction_hash_equal"]=same_hash
                entry[f"lane{lane}_correction_difference"]="0 (matching archived packed-bit SHA-256)" if same_hash else "UNKNOWN hamming count; archived correction hash differs"
            else:
                entry[f"lane{lane}_correction_hash_equal"]="UNKNOWN"
                entry[f"lane{lane}_correction_difference"]="UNKNOWN: no matching raw correction/hash evidence"
        entry['winner_matches']=row['selected_winner']==int(old['winner'])
        entry['modeled_cycle_difference']=row['ensemble_modeled_cycles']-int(old['n2_cycles'])
        entry['historical_rescue']=key in RESCUES
        entry['current_rescue']=row['rescue']
        entry['rescue_status']=("REPRODUCED" if row['rescue'] else "NOT_REPRODUCED_UNRESOLVED") if key in RESCUES else "NOT_A_PREDECLARED_RESCUE"
        entry['exact_match']=all(entry[f'lane{lane}_same_success_class'] and entry[f'lane{lane}_same_convergence_class'] and
                                 entry[f'lane{lane}_iteration_difference']==entry[f'lane{lane}_relay_leg_difference']==0 and
                                 entry[f'lane{lane}_correction_hash_equal'] is True for lane in (0,1)) and entry['winner_matches'] and entry['modeled_cycle_difference']==0
        history.append(entry)
        row.update({"historical_"+k:v for k,v in entry.items() if k!='shot_id'})
    write_csv(OUT/'historical_current_comparison.csv',history)
    return dict(rows=history,exact_matches=sum(r['exact_match'] for r in history),shots=len(history),
                rescue_rows=[r for r in history if r['historical_rescue']],
                correction_evidence=[dict(path=str(p),sha256=sha(p)) for p in correction_sources],
                note="Primary N2 CSV has no correction vectors; secondary raw paired-equivalence CSV supplies exact correction hashes after syndrome and gamma-seed identity checks. No numeric Hamming difference is invented from a hash.")


def report(summary):
    counts=summary.get('float_fixed_counts',{})
    multi=summary.get('multilane_checks',{})
    history=summary.get('current_historical_reproduction',{})
    print("\n=== FLOAT / FIXED / MULTILANE RECONCILIATION ===")
    print("\nFLOAT VS FIXED")
    for label,key in [('shots','shots'),('exact matches','EXACT_MATCH'),('quantization-only differences','QUANTIZATION_ONLY'),
                      ('convergence-class changes','CONVERGENCE_CLASS_CHANGE'),('logical-class changes','LOGICAL_CLASS_CHANGE'),('unresolved mismatches','unresolved')]:
        print(f"{label}: {counts.get(key, 'NOT RUN')}")
    print("\nMULTILANE")
    for label,key in [('lane-0 standalone agreement','lane0_standalone'),('lane-1 standalone agreement','lane1_standalone'),('arbiter agreement','arbiter')]:
        print(f"{label}: {multi.get(key, 'NOT RUN')}")
    rescues=history.get('rescue_rows',[])
    print('rescues reproduced:',sum(r['rescue_status']=='REPRODUCED' for r in rescues))
    print('historical rescues not reproduced:',sum(r['rescue_status']!='REPRODUCED' for r in rescues))
    print("\nHISTORICAL VERSION CHECK")
    for rec in summary.get('historical_versions',{}).get('studies',[]):
        print(f"{rec['study']}: {rec['classification']} (exact source recovered={rec['exact_source_recoverable']})")
    print("\nOVERALL:",summary['overall_status'])


def main():
    OUT.mkdir(exist_ok=True)
    (OUT/'checkpoints').mkdir(exist_ok=True)
    (OUT/'historical_sources').mkdir(exist_ok=True)
    rows=[]
    summary=dict(overall_status="FAIL",state="PREPARING",warnings=[],planned_shots=len(SUBSET),
                 exact_command=f".venv/bin/python -B '{Path(__file__).resolve().relative_to(REPO)}'")
    try:
        head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()
        summary['provenance']=dict(git_head=head,git_status_at_start=subprocess.check_output(['git','status','--short'],cwd=REPO,text=True),
                                   python=sys.version,numpy_version=np.__version__,runner_sha256=sha(__file__))
        summary['implementations']=implementation_inventory(head)
        module=load_module('n2_inspection',N2)
        summary['configuration_alignment']=align_configuration(module)
        summary['historical_versions']=historical_reconciliation()
        summary['numerical_audit']=numerical_audit()
        summary['arbiter_controls']=arbitration_controls()
        try:
            summary['rtl_controls']=rtl_controls()
        except Exception:
            summary['rtl_controls']=dict(status="FAIL",error=traceback.format_exc())
        with np.load(SAMPLES) as z:
            available_seeds=z['sample_seeds'].tolist()
            shape=z['syndromes'].shape;logical_shape=z['observed_logicals'].shape
            for seed,shot in SUBSET:
                require(seed in available_seeds and shot < shape[1],"Requested saved sample unavailable")
            _,_,prior=graph()
            require(np.array_equal(np.log((1-z['probabilities'])/z['probabilities']),prior),"Sample archive static probabilities differ from package")
        prior_validation=PROJECT/'results/stim-pipeline-validation/validation_evidence.npz'
        with np.load(prior_validation) as z:
            validation_available=int(z['original_syndromes'].shape[0])
        summary['saved_panel']=dict(path=str(SAMPLES),sha256=sha(SAMPLES),available_shots=int(shape[0]*shape[1]),
                                    detector_shape=shape,logical_label_shape=logical_shape,seeds=available_seeds,
                                    subset=[dict(sample_seed=s,shot=i) for s,i in SUBSET],
                                    selection_rule="First 30 shots of first saved seed, plus the two additional predeclared historical rescue IDs; 32 total. No new sampling.",
                                    fallback_reason=f"Previous validation archive contains only {validation_available} ordinary real syndromes, fewer than desired panel.",
                                    selection_bias="Rescue-enriched diagnostic panel; no statistical performance inference")
        summary['archive']=dict(path=str(ARCHIVE),sha256=sha(ARCHIVE))
        saved_rows={(int(r['sample_seed']),int(r['shot'])):r for r in read_csv(ARCHIVE)}
        require(all(saved_rows[k]['parallel_rescue']=='1' for k in RESCUES),"Named rescue IDs not confirmed by raw evidence")
        summary['state']='RUNNING'
        write_json(OUT/'reconciliation_summary.json',summary)
        print('Frozen configuration and historical-source inspection complete.',flush=True)
        print('RTL control status:',summary['rtl_controls']['status'],flush=True)
        print('Running predeclared 32-shot saved panel with three bounded worker processes.',flush=True)
        context=multiprocessing.get_context('spawn')
        with ProcessPoolExecutor(max_workers=3,mp_context=context) as pool:
            futures={pool.submit(shot_job,key):key for key in SUBSET}
            for future in as_completed(futures):
                key=futures[future]
                try:
                    row=future.result()
                except Exception:
                    row=dict(shot_id=f'{key[0]}_{key[1]:03d}',sample_seed=key[0],shot=key[1],
                             classification='IMPLEMENTATION_MISMATCH',error=traceback.format_exc())
                    write_json(OUT/'checkpoints'/f"{row['shot_id']}_error.json",row)
                rows.append(row)
                rows.sort(key=lambda r:(r['sample_seed'],r['shot']))
                write_csv(OUT/'per_shot_comparison.csv',rows)
                summary['completed_shots']=len(rows)
                write_json(OUT/'reconciliation_summary.json',summary)
                print(f"Completed {len(rows)}/32: {row['shot_id']} {row['classification']}",flush=True)
        summary['current_historical_reproduction']=compare_archive(rows)
        counts={key:sum(r['classification']==key for r in rows) for key in
                ['EXACT_MATCH','QUANTIZATION_ONLY','EARLY_DECISION_DIVERGENCE','CONVERGENCE_CLASS_CHANGE','LOGICAL_CLASS_CHANGE','PARAMETER_MISMATCH','IMPLEMENTATION_MISMATCH','UNRESOLVED']}
        counts.update(shots=len(rows),unresolved=sum(not r.get('numerical_origin_explained',False) for r in rows),
                      explained_convergence_class_changes=sum(r['classification']=='CONVERGENCE_CLASS_CHANGE' and r.get('numerical_origin_explained',False) for r in rows))
        summary['float_fixed_counts']=counts
        checks={}
        for label,field in [('lane0_standalone','lane0_standalone_agreement'),('lane1_standalone','lane1_standalone_agreement'),
                            ('arbiter','arbiter_agreement'),('both_fail','both_failed_reported_correctly'),('any_valid','any_valid_reported_correctly')]:
            checks[label]=dict(status='PASS' if len(rows)==32 and all(r.get(field,False) for r in rows) else 'FAIL',
                               agreeing=sum(bool(r.get(field,False)) for r in rows),shots=len(rows))
        checks['logical_label_independence']=summary['arbiter_controls']['status']
        summary['multilane_checks']=checks
        packed={};mismatches=[];sat=[];oracle_errors=[];rtl_exercised=[]
        for row in rows:
            sid=row['shot_id'];p=OUT/'checkpoints'/f'{sid}.npz'
            if p.exists():
                with np.load(p) as z:
                    for k in z.files:
                        packed[sid+'_'+k]=z[k]
                trace=json.loads((OUT/'checkpoints'/f'{sid}.json').read_text())['trace']
                for lane in ('lane0','lane1'):
                    sat += [dict(shot_id=sid,lane=lane,**event) for event in trace[lane]['saturation_events']]
                    oracle_errors += [dict(shot_id=sid,lane=lane,**event) for event in trace[lane]['oracle_errors']]
                    rtl_exercised += [dict(shot_id=sid,lane=lane,**event) for event in trace[lane]['rtl_saturation_order_divergences']]
            if row['classification']!='EXACT_MATCH':
                mismatches.append(dict(shot_id=sid,scope='float_vs_fixed',classification=row['classification'],
                                       numerical_origin_explained=row.get('numerical_origin_explained',False),
                                       evidence_path=str(OUT/'checkpoints'/f'{sid}.json'),notes=row.get('error','Per-iteration integer oracle and first decision/numeric divergence retained')))
        for case in summary.get('rtl_controls',{}).get('numerical_cases',[]):
            if not case['software_rtl_equal']:
                mismatches.append(dict(shot_id=f"rtl_fixture_{case['case']}",scope='software_vs_RTL_variable_node',classification='IMPLEMENTATION_MISMATCH',
                                       numerical_origin_explained=False,evidence_path=str(OUT/'rtl_numerical_comparison.json'),
                                       notes='Saturation before subtraction in RTL vs after subtraction in canonical fixed; not equivalent algorithms at representable boundary inputs'))
        for entry in summary['current_historical_reproduction']['rows']:
            if not entry['exact_match']:
                mismatches.append(dict(shot_id=entry['shot_id'],scope='current_vs_historical_N2',classification='UNRESOLVED',evidence_path=str(OUT/'historical_current_comparison.csv'),notes='Current results differ; exact historical source change alone does not establish cause'))
        summary['real_run_numerics']=dict(saturation_events=sat,oracle_errors=oracle_errors,software_rtl_saturation_order_exercised=rtl_exercised,
                                          observed_int64_overflow_events=0 if not oracle_errors else 'UNKNOWN')
        np.savez_compressed(OUT/'reconciliation_evidence.npz',**packed)
        if mismatches:
            write_csv(OUT/'mismatch_details.csv',mismatches)
        summary['warnings'] += [
            'Float/fixed exact match means final correction, convergence/outcome, iteration and leg counts; internal real/integer messages are not expected bit-identical.',
            'The N2 software study runs both trajectories to natural completion and models first-success selection; this is not a full concurrent RTL execution.',
            'No new STIM samples, N4 runs, NxP runs, or hardware performance measurements were made.',
            'Baseline source recovered from an unreachable Git blob; recorded baseline commit alone does not reproduce its generating source.',
            'R32 and realized hardware gamma schedules intentionally align the existing N2 experiment; unmodified float constructor defaults use R301 and a different gamma-generation path.',
            'Candidate-weight metadata differs between software original-prior weighting and RTL rounded-prior weighting; S1 prevents multi-candidate ranking effects in this panel.'
        ]
        failures=[]
        if len(rows)!=len(SUBSET) or any('error' in r for r in rows):failures.append('Missing or exception shot records')
        if counts['unresolved']:failures.append('Float/fixed numerical differences not fully explained')
        if any(v['status']=='FAIL' for v in checks.values() if isinstance(v,dict)):failures.append('N2 lane/arbitration mismatch')
        if checks['logical_label_independence']!='PASS':failures.append('Logical-label isolation of arbitration failed')
        if summary['rtl_controls']['status']=='FAIL':failures.append('Confirmed software/RTL saturation-order mismatch or RTL execution failure; inspect control evidence')
        if any(s['classification']=='UNKNOWN' for s in summary['historical_versions']['studies']):failures.append('Historical source differences unresolved')
        if any(not r['exact_match'] for r in summary['current_historical_reproduction']['rows']):failures.append('Current/history differences require explanation')
        summary['failure_reasons']=failures
        summary['overall_status']='FAIL' if failures else 'PASS_WITH_WARNINGS' if summary['warnings'] else 'PASS'
        summary['state']='COMPLETE'
        summary['safe_to_proceed_canonical_N4']=not failures
    except Exception:
        summary.update(overall_status='FAIL',state='STOPPED',fatal_error=traceback.format_exc(),safe_to_proceed_canonical_N4=False)
        print(summary['fatal_error'],flush=True)
    finally:
        write_csv(OUT/'per_shot_comparison.csv',rows)
        summary['artifact_hashes']={str(p.relative_to(OUT)):sha(p) for p in OUT.rglob('*') if p.is_file() and p.name!='reconciliation_summary.json'}
        write_json(OUT/'reconciliation_summary.json',summary)
        report(summary)
    return int(summary['overall_status']=='FAIL')


if __name__=='__main__':
    raise SystemExit(main())
