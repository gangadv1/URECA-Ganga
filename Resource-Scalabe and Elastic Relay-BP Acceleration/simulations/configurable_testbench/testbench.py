"""Reproducible circuit-level Relay-BP testbench; no historical output writes."""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys

import numpy as np
import scipy
from scipy import sparse
import stim

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "reference"), str(ROOT / "fpga/verification/parallel_n2")]
from fixedpoint import FixedConfig
from relay_bp_fixed import FixedRelayBPDecoder, FixedRelayConfig, FixedRelayLegConfig
from gamma_rng_reference import vector

BASE_SEED = 0x6A09E667F3BCC909
CODE_NAMES = {"18_4_3": "_bb18_test", "72_12_6": "_bb72_test",
              "144_12_12": "gross_circuit_level/memory_Z_r12_p0p003",
              "288_12_18": "_bb288_test"}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


@dataclass(frozen=True)
class Config:
    code: str = "144_12_12"
    package: str | None = None
    physical_p: float = .003
    source_circuit: str | None = None
    N: int = 1
    P: int = 4
    sample_seed: int = 20250617
    trajectory_base_seed: int = BASE_SEED
    engine_seeds: list[int] | None = None
    shots: int = 1
    shot_offset: int = 0
    first_limit: int = 80
    later_limit: int = 60
    R: int = 32
    S: int = 1
    timing_model: str = "folding_original"
    sample_mode: str = "circuit"

    def validate(self):
        if self.code not in CODE_NAMES and self.code != "parameterized":
            raise ValueError("Unsupported BB code")
        if self.code == "parameterized" and not self.package:
            raise ValueError("Parameterized codes require an explicit validated package")
        if any(type(getattr(self, k)) is not int or getattr(self, k) < 1
               for k in ("N", "P", "shots", "first_limit", "later_limit", "R", "S")):
            raise ValueError("Counts must be positive integers")
        if self.S > self.R or self.shot_offset < 0:
            raise ValueError("Require S <= R and nonnegative shot offset")
        if not 0 < self.physical_p < 1:
            raise ValueError("Physical p must lie in (0,1)")
        if self.timing_model not in ("canonical_p4", "folding_original"):
            raise ValueError("Choose canonical_p4 or folding_original")
        if self.timing_model == "canonical_p4" and (self.P != 4 or self.S != 1):
            raise ValueError("Calibrated canonical timing requires P4/S1")
        if self.timing_model == "folding_original" and self.P not in (2, 4, 8):
            raise ValueError("Validated folding lane counts are P=2,4,8")
        if self.sample_mode not in ("circuit", "package", "canonical_paired"):
            raise ValueError("Unknown sample mode")
        seeds = [self.sample_seed, self.trajectory_base_seed] + (self.engine_seeds or [])
        if any(type(x) is not int or not 0 <= x < 2**64 for x in seeds):
            raise ValueError("Seeds must be unsigned 64-bit integers")
        if self.engine_seeds is not None and len(self.engine_seeds) != self.N:
            raise ValueError("Provide exactly N engine seeds")


def load_problem(cfg):
    """Load sparse Tier-2 incidence; the legacy dense Tier-1 loader is unsuitable."""
    cfg.validate()
    directory = Path(cfg.package).resolve() if cfg.package else ROOT / "graphs/generated" / CODE_NAMES[cfg.code]
    pkg = json.loads((directory / "package.json").read_text())
    manifest = json.loads((directory / "manifest.json").read_text())
    def file(key):
        path = (directory / pkg["files"][key]).resolve()
        if not path.is_relative_to(directory.resolve()):
            raise ValueError("Package path escapes package directory")
        return path
    required = {"circuit.stim", "faults.npz", "edge_lists.npz", "package.json"}
    hashes = manifest["provenance"]["artifact_hashes"]
    if not required.issubset(hashes):
        raise ValueError("Missing required package hashes")
    for name, expected in hashes.items():
        path = (directory / name).resolve()
        if not path.is_relative_to(directory.resolve()) or sha(path) != expected:
            raise ValueError(f"Package artifact hash mismatch: {name}")
    generic = cfg.code == "parameterized"
    if generic:
        construction = pkg.get("construction", {})
        algebra = module("parameterized_bb_validator", ROOT / "graphs/parameterized_bb.py")
        _, _, derived = algebra.construct(construction["l"], construction["m"], construction["A"], construction["B"])
        n, k, d = derived["n"], derived["k"], None
        if construction != manifest.get("construction") or any(construction[key] != derived[key] for key in derived):
            raise ValueError("Parameterized construction metadata differs from algebra")
    else:
        n, k, d = map(int, cfg.code.split("_"))
    if pkg.get("code_parameters",dict(n=n,k=k,d=d)) != dict(n=n,k=k,d=d):
        raise ValueError("Package code parameters mismatch")
    if generic:
        if pkg["tier"] != "tier-2-circuit-level" or pkg["code"] != "bb_" + construction["matrix_sha256"][:16]:
            raise ValueError("Wrong parameterized package identity/tier")
    elif pkg["tier"] != "tier-2-circuit-level" or pkg["code"] not in (
            "bb_" + cfg.code, "gross_144_12_12" if cfg.code == "144_12_12" else ""):
        raise ValueError("Wrong package code/tier")
    if not math.isclose(pkg["physical_error_probability"], cfg.physical_p, rel_tol=0, abs_tol=1e-15):
        raise ValueError("Physical p differs from selected source package")
    if (not math.isclose(manifest["circuit"]["physical_error_probability"],cfg.physical_p,
                         rel_tol=0,abs_tol=1e-15)
            or manifest["circuit"]["noisy_qec_rounds"] != pkg["rounds"]
            or pkg["observable_count"] != k):
        raise ValueError("Package/manifest physical/source metadata mismatch")
    circuit_path = file("circuit")
    if sha(circuit_path) != manifest["provenance"]["source_circuit_sha256"]:
        raise ValueError("Source circuit hash mismatch")
    if cfg.source_circuit and sha(cfg.source_circuit) != sha(circuit_path):
        raise ValueError("Supplied source circuit differs from package")
    circuit = stim.Circuit.from_file(str(circuit_path))
    builder = module("testbench_circuit_validator", ROOT / "graphs/build_circuit_level.py")
    if generic:
        builder.validate_parameterized_source(circuit, construction, cfg.physical_p, pkg["rounds"])
    else:
        builder.validate_source(circuit, circuit_path, cfg.code, cfg.physical_p, pkg["rounds"])
    c, v, o = (int(pkg[x]) for x in ("detector_count", "fault_count", "observable_count"))
    if (circuit.num_detectors, circuit.num_observables, circuit.num_qubits) != (c, o, 2*n) or o != k:
        raise ValueError("Circuit/package label dimensions mismatch")
    for key, value in (("detector_count", c), ("fault_count", v), ("observable_count", o)):
        if manifest["graph"][key] != value:
            raise ValueError("Manifest dimension mismatch")
    with np.load(file("edge_lists"), allow_pickle=False) as data:
        de, oe = data["detector_edges"].copy(), data["observable_edges"].copy()
    def incidence(edges, count):
        if edges.ndim != 2 or edges.shape[1] != 2 or not np.issubdtype(edges.dtype, np.integer):
            raise ValueError("Invalid incidence labels")
        if len(edges) and (edges.min() < 0 or edges[:, 0].max() >= v or edges[:, 1].max() >= count):
            raise ValueError("Incidence label out of range")
        matrix = sparse.csr_matrix((np.ones(len(edges), np.uint8), (edges[:, 1], edges[:, 0])), shape=(count, v))
        if matrix.nnz != len(edges):
            raise ValueError("Duplicate incidence")
        return matrix
    h, action = incidence(de, c), incidence(oe, o)
    if h.nnz != pkg["detector_edge_count"] or action.nnz != pkg["logical_edge_count"]:
        raise ValueError("Incidence count mismatch")
    with np.load(file("faults"), allow_pickle=False) as data:
        probabilities = data["probabilities"].copy()
        for key, matrix, count in (("detector", h, c), ("observable", action, o)):
            stored = sparse.csr_matrix((np.ones(len(data[key+"_indices"]), np.uint8),
                                        data[key+"_indices"], data[key+"_indptr"]), shape=(v, count)).T
            if (stored != matrix).nnz:
                raise ValueError("Fault CSR and edge labels disagree")
    if probabilities.shape != (v,) or not np.all(np.isfinite(probabilities) & (probabilities > 0) & (probabilities < 1)):
        raise ValueError("Invalid fault priors")
    return directory, pkg, manifest, circuit, h, action, np.log((1-probabilities)/probabilities)


def samples(cfg, directory, pkg, circuit):
    stop = cfg.shot_offset + cfg.shots
    if cfg.sample_mode == "circuit":
        detectors, logicals = circuit.compile_detector_sampler(seed=cfg.sample_seed).sample(stop, separate_observables=True)
    elif cfg.sample_mode == "package":
        if cfg.sample_seed != pkg["sample_seed"] or stop > pkg["sample_shots"]:
            raise ValueError("Archived package seed/shot request mismatch")
        with np.load(directory / pkg["files"]["circuit_samples"], allow_pickle=False) as data:
            detectors, logicals = data["detectors"], data["observables"]
    else:
        locked = json.loads((ROOT / "results/n-scaling-canonical/manifest.json").read_text())
        archive = ROOT / "results/circuit-level-multiseed/paired_samples.npz"
        if (sha(directory / "manifest.json") != locked["hashes"]["package_manifest"]
                or sha(archive) != locked["hashes"]["samples"]):
            raise ValueError("Canonical samples require the exact locked graph and sample hashes")
        with np.load(archive, allow_pickle=False) as data:
            indices = np.flatnonzero(data["sample_seeds"] == cfg.sample_seed)
            if len(indices) != 1:
                raise ValueError("Canonical sample seed absent")
            detectors, logicals = data["syndromes"][indices[0]], data["observed_logicals"][indices[0]]
    if (detectors.ndim != 2 or logicals.ndim != 2 or len(detectors) < stop
            or len(logicals) != len(detectors) or detectors.shape[1] != pkg["detector_count"]
            or logicals.shape[1] != pkg["observable_count"]
            or not np.all((detectors == 0) | (detectors == 1))
            or not np.all((logicals == 0) | (logicals == 1))):
        raise ValueError("Invalid detector/logical sample labels")
    return detectors[cfg.shot_offset:stop].astype(np.uint8), logicals[cfg.shot_offset:stop].astype(np.uint8)


def splitmix(x):
    x = (x + 0x9e3779b97f4a7c15) & ((1 << 64)-1)
    z = ((x ^ (x >> 30)) * 0xbf58476d1ce4e5b9) & ((1 << 64)-1)
    z = ((z ^ (z >> 27)) * 0x94d049bb133111eb) & ((1 << 64)-1)
    return (z ^ (z >> 31)) & ((1 << 64)-1)


def trajectory_seeds(cfg, shot):
    if cfg.engine_seeds is not None:
        return cfg.engine_seeds
    seeds = [splitmix(cfg.trajectory_base_seed ^ cfg.sample_seed ^ (shot * 0x100000001b3))]
    while len(seeds) < cfg.N:
        seeds.append(splitmix(seeds[-1] ^ 0xd1b54a32d192ed03))
    return seeds


def configure_folding(fm, p):
    """Adapt an isolated structural service module to the selected P."""
    fm.P = p
    def empty(name):
        from collections import defaultdict
        return dict(phase=name, logical_accesses=0, issued_groups=0, conflict_events=0,
                    retry_subsets=0, lane_hist={str(i): 0 for i in range(1,p+1)},
                    node_retry=defaultdict(int), partition_logical=[0,0,0,0])
    def finalize(m):
        groups = m["issued_groups"]
        active = sum(int(k)*v for k,v in m["lane_hist"].items())
        m["mean_active_lanes"] = active/groups if groups else 0
        m["mean_lane_utilization"] = m["mean_active_lanes"]/p
        m["full_P_lane_fraction"] = m["lane_hist"][str(p)]/groups if groups else 0
        m.pop("node_retry")
        return m
    fm.empty_phase, fm.finalize = empty, finalize
    return fm


def folding(h, p):
    """Reuse archived original-layout service model, never BA2/Gross permutations."""
    fm = configure_folding(module("testbench_fold", ROOT / "results/graph-partitioning-folding-model/run_folding_layout_comparison.py"), p)
    ec, ev, ve = fm.original_edge_tables(h)
    layout = dict(check_order=np.arange(h.shape[0]), fault_order=np.arange(h.shape[1]),
                  check_edges=[np.arange(h.indptr[c],h.indptr[c+1]) for c in range(h.shape[0])],
                  variable_edges=ve, edge_fault=ev, edge_check=ec)
    phases, total = fm.profile(layout, np.zeros(h.shape[0],int), np.zeros(h.shape[1],int))
    return phases, total


def timing(cfg, directory, h):
    if cfg.timing_model == "canonical_p4":
        locked = json.loads((ROOT / "results/n-scaling-canonical/manifest.json").read_text())
        if sha(directory / "edge_lists.npz") != json.loads((ROOT / "graphs/generated/gross_circuit_level/memory_Z_r12_p0p003/manifest.json").read_text())["provenance"]["artifact_hashes"]["edge_lists.npz"]:
            raise ValueError("Canonical calibration is restricted to the exact Gross incidence graph")
        return {k:locked["cycle_model"][k] for k in ("check","variable","convergence","relay_init")}, None
    phases, total = folding(h,cfg.P)
    return {k:v["estimated_cycles"] for k,v in phases.items()}, dict(phases=phases, all_phases_once=total)


def decode_engine(h, priors, syndrome, seed, cfg, costs):
    """No logical action, observed logical labels or sampled faults enter decoding."""
    state = seed
    legs = [FixedRelayLegConfig(cfg.first_limit, gamma=.125)]
    words = [0]
    for _ in range(1,cfg.R):
        values, _, state, rejected = vector(state,h.shape[1])
        legs.append(FixedRelayLegConfig(cfg.later_limit,gamma=np.asarray(values,dtype=float)/16))
        words.append(h.shape[1]+rejected)
    decoder = FixedRelayBPDecoder(h,FixedRelayConfig(
        fixed=FixedConfig(b=18,g=4,M=16,clip=None,separate_scale=True),
        leg_configs=tuple(legs),R=cfg.R,S=cfg.S,seed=0))
    result = decoder.decode(priors,syndrome)
    decision = result.decoded_error.astype(np.uint8)
    valid = bool(np.array_equal(np.asarray(h@decision).ravel()&1,syndrome))
    phase_cycles = result.total_iterations*sum(costs[k] for k in ("check","variable","convergence")) + result.relay_legs*costs["relay_init"]
    natural = phase_cycles
    if cfg.timing_model == "canonical_p4":
        natural += h.shape[1]+9+8*(result.total_iterations-result.relay_legs)
        natural += sum(words[1:result.relay_legs])+9*max(0,result.relay_legs-1)
        if valid and result.relay_legs > 1:
            natural += 2
    completion = natural - int(valid) if cfg.timing_model == "canonical_p4" else natural
    return dict(decision=decision, syndrome_converged=valid, iterations=result.total_iterations,
                legs=result.relay_legs, natural_cycles=int(natural), result_cycles=int(completion),
                seed=int(seed), rng_words=int(sum(words[1:result.relay_legs])))


def score(h, action, decision, syndrome, logical):
    valid = bool(np.array_equal(np.asarray(h@decision).ravel()&1,syndrome))
    correct = bool(np.array_equal(np.asarray(action@decision).ravel()&1,logical))
    return dict(nonconvergence=int(not valid), syndrome_valid_logical_error=int(valid and not correct),
                total_failure=int(not valid or not correct))


def select(engines):
    successes = [(e["result_cycles"],i) for i,e in enumerate(engines) if e["syndrome_converged"]]
    return min(successes) if successes else (max(e["result_cycles"] for e in engines),-1)


def describe(values):
    if not values:
        return None
    a = np.asarray(values,dtype=float)
    return dict(count=len(values),mean=float(a.mean()),p50=float(np.percentile(a,50)),
                p95=float(np.percentile(a,95)),max=float(a.max()))


def rate(k,n):
    z = 1.959963984540054
    p = k/n; denominator = 1+z*z/n
    center = (p+z*z/(2*n))/denominator
    radius = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/denominator
    return dict(count=k,shots=n,rate=p,wilson95=[max(0,center-radius),min(1,center+radius)])


def run(cfg, output):
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError("Output must be a new directory")
    if output.is_relative_to(ROOT) and not output.is_relative_to(Path(__file__).parent):
        raise ValueError("Repository outputs must be under the new configurable_testbench directory")
    directory,pkg,manifest,circuit,h,action,priors = load_problem(cfg)
    detectors,logicals = samples(cfg,directory,pkg,circuit)
    costs,fold = timing(cfg,directory,h)
    rows,engine_rows = [],[]
    for offset,(syndrome,logical) in enumerate(zip(detectors,logicals)):
        shot = cfg.shot_offset+offset
        engines = [decode_engine(h,priors,syndrome,seed,cfg,costs) for seed in trajectory_seeds(cfg,shot)]
        cycles,winner = select(engines)
        scored = dict(nonconvergence=1,syndrome_valid_logical_error=0,total_failure=1) if winner<0 else score(h,action,engines[winner]["decision"],syndrome,logical)
        rows.append(dict(shot=shot,winner_engine=winner,**scored,modeled_completion_cycles=cycles,
                         winner_iterations=None if winner<0 else engines[winner]["iterations"],
                         winner_legs=None if winner<0 else engines[winner]["legs"],
                         uncancelled_natural_work=sum(e["natural_cycles"] for e in engines),
                         provisioned_lane_cycles=cfg.N*cfg.P*cycles,
                         same_cycle_successes=sum(e["syndrome_converged"] and e["result_cycles"]==cycles for e in engines),
                         detector_hash=hashlib.sha256(syndrome.tobytes()).hexdigest(),
                         logical_hash=hashlib.sha256(logical.tobytes()).hexdigest()))
        for i,e in enumerate(engines):
            engine_rows.append(dict(shot=shot,engine=i,**{k:v for k,v in e.items() if k!="decision"},
                                    **score(h,action,e["decision"],syndrome,logical),
                                    decision_hash=hashlib.sha256(e["decision"].tobytes()).hexdigest()))
    summary = {k:rate(sum(r[k] for r in rows),cfg.shots) for k in
               ("total_failure","nonconvergence","syndrome_valid_logical_error")}
    summary.update(modeled_latency_cycles=describe([r["modeled_completion_cycles"] for r in rows]),
                   winner_iterations=describe([r["winner_iterations"] for r in rows if r["winner_iterations"] is not None]),
                   winner_legs=describe([r["winner_legs"] for r in rows if r["winner_legs"] is not None]),
                   per_engine_iterations={str(i):describe([e["iterations"] for e in engine_rows if e["engine"]==i]) for i in range(cfg.N)},
                   per_engine_legs={str(i):describe([e["legs"] for e in engine_rows if e["engine"]==i]) for i in range(cfg.N)},
                   folding_metrics=fold, timing_phase_costs=costs,
                   cancellation_aware_executed_work=None, cancellation_ack_or_drain_cycles=None,
                   elapsed_cycle_PE_utilization=None, measured_hardware_latency=None,
                   unavailable_reason="No per-engine cancellation/phase/issue timestamps; folding occupancy is over issue groups only",
                   timing_scope=("Locked Gross P4/S1 calibration including controller/RNG overhead"
                                 if cfg.timing_model=="canonical_p4" else
                                 "Original-layout structural service extrapolation; excludes controller/RNG overhead"),
                   folding_scope="One execution of each phase; occupancy denominator is issued groups, not elapsed cycles",
                   quantity_kind="modeled_software_cycles_not_measured_FPGA_timing")
    # Only allocate outputs after successful decoding/scoring; never replace archives.
    output.mkdir(parents=True,exist_ok=False)
    for name,data in (("per_shot.csv",rows),("per_engine.csv",engine_rows)):
        with (output/name).open("w",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=list(data[0]));writer.writeheader();writer.writerows(data)
    (output/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    provenance=dict(configuration=asdict(cfg),package_directory=str(directory),
                    dimensions=dict(detectors=h.shape[0],faults=h.shape[1],observables=action.shape[0]),
                    input_hashes={"package":sha(directory/"package.json"),"manifest":sha(directory/"manifest.json"),
                                  "source":manifest["provenance"]["source_circuit_sha256"]},
                    implementation_hashes={str(p.relative_to(ROOT)):sha(p) for p in
                        (Path(__file__),ROOT/"reference/relay_bp_fixed.py",ROOT/"reference/fixedpoint.py",
                         ROOT/"fpga/verification/parallel_n2/gamma_rng_reference.py",
                         ROOT/"graphs/build_circuit_level.py",ROOT/"results/graph-partitioning-folding-model/run_folding_layout_comparison.py")},
                    output_hashes={name:sha(output/name) for name in ("per_shot.csv","per_engine.csv","summary.json")},
                    versions=dict(python=sys.version,numpy=np.__version__,scipy=scipy.__version__,stim=stim.__version__),
                    git_commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
                    assumptions=["Dedicated P lanes per trajectory; no shared pool or cross-engine contention",
                                 "First eligible syndrome-valid decoder completion wins; lowest index breaks ties",
                                 "All-fail waits for last engine; natural engine execution recorded without cancellation",
                                 "folding_original extrapolates archived service formulas; excludes RNG/controller overhead",
                                 "canonical_p4 uses locked graph/P4/S1 calibration; no hardware timing measured"])
    if cfg.sample_mode=="canonical_paired":
        provenance["input_hashes"]["paired_samples"]=sha(ROOT/"results/circuit-level-multiseed/paired_samples.npz")
    (output/"manifest.json").write_text(json.dumps(provenance,indent=2)+"\n")
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",type=Path,required=True,help="JSON Config fields; paths relative to working directory")
    parser.add_argument("--output",type=Path,required=True,help="Fresh isolated directory")
    args=parser.parse_args()
    cfg=Config(**json.loads(args.config.read_text()))
    result=run(cfg,args.output)
    print(json.dumps({k:result[k] for k in ("total_failure","nonconvergence","syndrome_valid_logical_error","modeled_latency_cycles")},indent=2))


if __name__=="__main__":
    main()
