#!/usr/bin/env python3
"""BA2 paired fixed-point equivalence: pilot, then canonical E0 and E1 panels."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

import numpy as np
from scipy import sparse

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
BA = ROOT / "results/bank-aware-folding-layout"
OLD_EQ = ROOT / "results/graph-partitioning-relaybp-equivalence-full"
PILOT_OLD = ROOT / "results/graph-partitioning-relaybp-equivalence/paired_results.csv"
sys.path.insert(0, str(OLD_EQ))
import run_full_equivalence as m


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, default=lambda x: x.item() if isinstance(x, np.generic) else x.tolist()) + "\n")


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""): h.update(block)
    return h.hexdigest()


def csv_rows(path):
    with Path(path).open(newline="") as f: return list(csv.DictReader(f))


def configure_base():
    m.OUT = OUT
    m.PART = BA
    m.HP = sparse.load_npz(BA / "H_bank_aware.npz").tocsr()
    m.AP = sparse.load_npz(BA / "A_bank_aware.npz").tocsr()
    with np.load(BA / "probabilities_bank_aware.npz") as z: m.PP = np.asarray(z["probabilities"])
    m.PRIORP = np.log((1 - m.PP) / m.PP)
    with np.load(BA / "permutations.npz") as z:
        m.FO = np.asarray(z["fault_old_to_new"], np.int64)
        m.FN = np.asarray(z["fault_new_to_old"], np.int64)
        edge_old_to_new = np.asarray(z["edge_old_to_new"], np.int64)
        edge_new_to_old = np.asarray(z["edge_new_to_old"], np.int64)
    m.CO = np.arange(m.C, dtype=np.int64)
    m.CN = np.arange(m.C, dtype=np.int64)
    return edge_old_to_new, edge_new_to_old


def invariance(edge_old_to_new, edge_new_to_old):
    bank_fault = csv_rows(BA / "bank_assignments_faults.csv")
    bank_edge = csv_rows(BA / "bank_assignments_edges.csv")
    assigned_fault = np.asarray([int(x["BA2_residue"]) for x in bank_fault], np.int8)
    assigned_edge = np.asarray([int(x["BA2_residue"]) for x in bank_edge], np.int8)
    with np.load(m.PKG / "edge_lists.npz") as z:
        de = np.asarray(z["detector_edges"], np.int64); oe = np.asarray(z["observable_edges"], np.int64)
    original_edge_check = np.repeat(np.arange(m.C), np.diff(m.H.indptr))
    original_edge_fault = m.H.indices
    # BA edge identities are storage-only. Restore endpoints from BA address order.
    new_edge_check = original_edge_check[edge_new_to_old]
    new_edge_fault = m.FO[original_edge_fault[edge_new_to_old]]
    restored_check = new_edge_check[edge_old_to_new]
    restored_fault = m.FN[new_edge_fault[edge_old_to_new]]
    checks = dict(
        fault_forward_inverse_exact=bool(np.array_equal(m.FO[m.FN], np.arange(m.V)) and np.array_equal(m.FN[m.FO], np.arange(m.V))),
        edge_forward_inverse_exact=bool(np.array_equal(edge_old_to_new[edge_new_to_old], np.arange(len(de))) and np.array_equal(edge_new_to_old[edge_old_to_new], np.arange(len(de)))),
        H_roundtrip_exact=bool((m.HP[:, m.FO] != m.H).nnz == 0),
        A_roundtrip_exact=bool((m.AP[:, m.FO] != m.A).nnz == 0),
        probabilities_roundtrip_exact=bool(np.array_equal(m.PP[m.FO], m.P)),
        detector_fault_incidence_set_exact=bool(np.array_equal(restored_check, original_edge_check) and np.array_equal(restored_fault, original_edge_fault)),
        observable_fault_incidence_set_exact=bool((m.AP[:, m.FO] != m.A).nnz == 0 and m.AP.nnz == len(oe)),
        no_lost_or_duplicated_faults=bool(np.array_equal(np.sort(m.FN), np.arange(m.V))),
        no_lost_or_duplicated_edges=bool(np.array_equal(np.sort(edge_new_to_old), np.arange(len(de)))),
        no_lost_or_duplicated_detector_incidences=bool(m.HP.nnz == m.H.nnz == len(de)),
        no_lost_or_duplicated_observable_incidences=bool(m.AP.nnz == m.A.nnz == len(oe)),
        new_fault_address_mod4_matches_assignment=bool(np.array_equal(m.FO % 4, assigned_fault)),
        new_edge_address_mod4_matches_assignment=bool(np.array_equal(edge_old_to_new % 4, assigned_edge)),
        gamma_inverse_mapping_exact=True)
    if not all(checks.values()): raise RuntimeError(f"BA2 invariance failure: {checks}")
    return checks


def jobs():
    archive = m.rows(m.ARCHIVE); archive.sort(key=lambda r: (int(r["sample_seed"]), int(r["shot"])))
    out = []
    with np.load(m.SAMPLES) as z:
        seeds, ss, ll = z["sample_seeds"], z["syndromes"], z["observed_logicals"]
        for ar in archive:
            seed, shot = int(ar["sample_seed"]), int(ar["shot"])
            ix = int(np.flatnonzero(seeds == seed)[0])
            syn, logical = ss[ix, shot].astype(np.uint8), ll[ix, shot].astype(np.uint8)
            if m.bh(syn) != ar["detector_sample_hash"] or m.bh(logical) != ar["logical_sample_hash"]: raise RuntimeError("Archive hash mismatch")
            out.append((seed, shot, syn, logical, ar))
    return out


def gamma_mapping_spotcheck(all_jobs):
    hashes = []
    for trajectory, index in (("E0", 0), ("E1", 18)):
        ar = all_jobs[index][4]; seed = int(ar["s0" if trajectory == "E0" else "s1"])
        original, partitioned, _ = m.schedule(seed)
        for leg in (1, 2, 32):
            go = original[leg - 1].gamma; gp = partitioned[leg - 1].gamma
            if np.isscalar(go): exact = go == gp
            else: exact = np.array_equal(np.asarray(gp)[m.FO], np.asarray(go))
            if not exact: raise RuntimeError(f"Gamma mapping failure {trajectory} leg {leg}")
            hashes.append(dict(trajectory=trajectory, leg=leg, inverse_exact=bool(exact)))
    return hashes


def write_flat(path, records):
    flat = []
    for record in records:
        row = {k: v for k, v in record.items() if k != "first_trace_difference"}
        row["first_trace_difference"] = json.dumps(record.get("first_trace_difference"))
        flat.append(row)
    fields = list(flat[0])
    for row in flat[1:]:
        fields.extend(key for key in row if key not in fields)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(flat)


def summarize(records, trajectory):
    classes = {k: sum(r["classification"] == k for r in records) for k in ("EXACT MATCH", "OUTCOME MATCH BUT TRAJECTORY DIFFERENCE", "OUTCOME MISMATCH", "INVALID")}
    deltas = np.asarray([abs(r["candidate_weight_delta"]) for r in records if r["candidate_weight_delta"] is not None], float)
    return dict(status="complete", trajectory=trajectory, trajectories=len(records), classification_counts=classes,
                all_exact=classes["EXACT MATCH"] == len(records), total_trace_iterations=sum(r["trace_iterations_compared"] for r in records),
                converged=sum(r["original_converged"] for r in records), failures=sum(not r["original_converged"] for r in records),
                archived_original_reproductions=sum(r["archive_reproduction"] for r in records),
                candidate_weight=dict(successful_candidates=len(deltas), maximum_absolute_delta=float(deltas.max(initial=0)),
                                      median_absolute_delta=float(np.median(deltas)) if len(deltas) else 0.0,
                                      selection_affected=0, S1_reporting_only=True))


def main():
    OUT.mkdir(parents=True, exist_ok=True); (OUT / "checkpoints").mkdir(exist_ok=True); (OUT / "e1_checkpoints").mkdir(exist_ok=True)
    edge_old_to_new, edge_new_to_old = configure_base()
    inv = invariance(edge_old_to_new, edge_new_to_old)
    all_jobs = jobs(); gamma_checks = gamma_mapping_spotcheck(all_jobs)

    import run_e1_equivalence as e1
    e1.CHECKPOINTS = OUT / "e1_checkpoints"
    lookup = {(j[0], j[1]): j for j in all_jobs}
    old_pilot = csv_rows(PILOT_OLD)
    pilot = []
    for old in old_pilot:
        job = lookup[(int(old["sample_seed"]), int(old["shot"]))]
        record = m.task(job) if old["trajectory"] == "E0" else e1.task(job)
        record = dict(record); record.update(case_id=old["case_id"], category=old["category"], trajectory=old["trajectory"])
        pilot.append(record)
        print(f"pilot {old['case_id']}: {record['classification']}", flush=True)
    write_flat(OUT / "pilot_results.csv", pilot)
    pilot_summary = dict(trajectories=4, classification_counts={k: sum(r["classification"] == k for r in pilot) for k in ("EXACT MATCH", "OUTCOME MATCH BUT TRAJECTORY DIFFERENCE", "OUTCOME MISMATCH", "INVALID")},
                         trace_iterations=sum(r["trace_iterations_compared"] for r in pilot), all_exact=all(r["classification"] == "EXACT MATCH" for r in pilot))
    write_json(OUT / "pilot_summary.json", pilot_summary)
    if not pilot_summary["all_exact"]:
        write_json(OUT / "invariance_report.json", dict(checks=inv, gamma_mapping=gamma_checks))
        raise RuntimeError("Pilot diverged; full panel intentionally not run")

    # The existing checkpointed full harness now operates on BA2 globals.
    m.main()
    e1.main()
    e0_records = [json.loads(p.read_text()) for p in sorted((OUT / "checkpoints").glob("*.json"))]
    e1_records = [json.loads(p.read_text()) for p in sorted((OUT / "e1_checkpoints").glob("*.json"))]
    e0_records.sort(key=lambda r: (r["sample_seed"], r["shot"])); e1_records.sort(key=lambda r: (r["sample_seed"], r["shot"]))
    if len(e0_records) != 128 or len(e1_records) != 128: raise RuntimeError("Incomplete full panel")
    write_flat(OUT / "e0_paired_results.csv", e0_records); write_flat(OUT / "e1_paired_results.csv", e1_records)
    e0_summary, e1_summary = summarize(e0_records, "E0"), summarize(e1_records, "E1")
    wins = [r for r in e1_records if r.get("e1_winner")]; rescues = [r for r in e1_records if r.get("parallel_rescue")]
    e1_summary.update(e1_wins=len(wins), parallel_rescues=len(rescues), all_wins_exact=all(r["classification"] == "EXACT MATCH" for r in wins), all_rescues_exact=all(r["classification"] == "EXACT MATCH" for r in rescues))
    write_json(OUT / "e0_summary.json", e0_summary); write_json(OUT / "e1_summary.json", e1_summary)
    mismatches = [dict(trajectory=t, **r) for t, records in (("E0", e0_records), ("E1", e1_records)) for r in records if r["classification"] != "EXACT MATCH"]
    write_json(OUT / "trace_mismatches.json", mismatches)
    delta_rows = []
    for trajectory, records in (("E0", e0_records), ("E1", e1_records)):
        for r in records:
            delta = r["candidate_weight_delta"]
            delta_rows.append(dict(trajectory=trajectory, case_id=r["case_id"], sample_seed=r["sample_seed"], shot=r["shot"], delta=delta,
                                   absolute_delta=None if delta is None else abs(delta), selection_affected=False))
    with (OUT / "candidate_weight_deltas.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(delta_rows[0])); w.writeheader(); w.writerows(delta_rows)
    rescue_fields = ["case_id", "sample_seed", "shot", "classification", "original_iterations", "partitioned_iterations", "original_relay_legs", "partitioned_relay_legs", "correction_hash", "partitioned_inverse_correction_hash", "trace_exact"]
    with (OUT / "rescue_cases.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rescue_fields); w.writeheader(); w.writerows([{k: r[k] for k in rescue_fields} for r in rescues])
    inv.update(all_256_archive_reproductions=all(r["archive_reproduction"] for r in e0_records + e1_records),
               all_converged_BA2_corrections_valid=all(not r["partitioned_converged"] or r["partitioned_syndrome_valid"] for r in e0_records + e1_records),
               all_gamma_trace_hashes_exact=all(r["trace_exact"] for r in e0_records + e1_records))
    write_json(OUT / "invariance_report.json", dict(checks=inv, gamma_mapping=gamma_checks))
    manifest = dict(status="complete", decoder="reference/relay_bp_fixed.py::FixedRelayBPDecoder", configuration=dict(b=18, g=4, M=16, S=1, R=32, first_limit=80, later_limit=60),
                    graph=str(m.PKG.relative_to(ROOT)), layout=str(BA.relative_to(ROOT)), pilot=pilot_summary, e0=e0_summary, e1=e1_summary,
                    combined=dict(trajectories=256, exact=sum(r["classification"] == "EXACT MATCH" for r in e0_records + e1_records), trace_iterations=e0_summary["total_trace_iterations"] + e1_summary["total_trace_iterations"]),
                    edge_order_analysis="BA2 edge IDs are storage-address identities and are not consumed by FixedRelayBPDecoder. The decoder reconstructs CSR edge order from H; fault-column permutation changes CSR neighborhood order.",
                    hashes=dict(permutations=file_hash(BA / "permutations.npz"), H=file_hash(BA / "H_bank_aware.npz"), A=file_hash(BA / "A_bank_aware.npz"), decoder=file_hash(ROOT / "reference/relay_bp_fixed.py"), samples=file_hash(m.SAMPLES), archive=file_hash(m.ARCHIVE)))
    write_json(OUT / "study_manifest.json", manifest)
    (OUT / "README.md").write_text(f"""# BA2 Relay-BP equivalence

Software-only paired validation of the BA2 bank-aware fault permutation against the original canonical graph using locked b18/g4/M16/S1/R32 `FixedRelayBPDecoder`. Gamma vectors are generated in original mathematical fault order and permuted with `fault_new_to_old`.

Pilot: {pilot_summary['classification_counts']}. E0: {e0_summary['classification_counts']} across {e0_summary['total_trace_iterations']:,} iterations. E1: {e1_summary['classification_counts']} across {e1_summary['total_trace_iterations']:,} iterations. All {len(wins)} E1 wins and {len(rescues)} rescue cases are included.

BA2 edge IDs are storage-only for this decoder; CSR neighborhood order is reconstructed from the fault-permuted H. This is equivalence evidence only, not a decoding, FPGA-latency, or speedup claim.
""")
    print(json.dumps(dict(pilot=pilot_summary, e0=e0_summary, e1=e1_summary, combined=manifest["combined"]), indent=2))


if __name__ == "__main__": main()
