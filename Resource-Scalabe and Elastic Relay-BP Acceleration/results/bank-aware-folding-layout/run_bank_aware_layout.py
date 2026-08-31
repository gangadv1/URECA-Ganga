#!/usr/bin/env python3
"""Deterministic software-only bank-aware layout study for the P=4 model."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import itertools
import json
import time
from pathlib import Path

import numpy as np
from scipy import sparse

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
GRAPH = ROOT / "graphs/generated/gross_circuit_level/memory_Z_r12_p0p003"
METIS = ROOT / "results/graph-partitioning-metis"
FOLD = ROOT / "results/graph-partitioning-folding-model"
ARCHIVE = ROOT / "results/n1-vs-n2-hardware-latency/per_shot_results.csv"
P = 4

spec = importlib.util.spec_from_file_location("folding_model", FOLD / "run_folding_layout_comparison.py")
fm = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(fm)


def json_default(x):
    if isinstance(x, np.generic): return x.item()
    if isinstance(x, np.ndarray): return x.tolist()
    raise TypeError(type(x).__name__)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, default=json_default) + "\n")


def ahash(value):
    value = np.ascontiguousarray(value)
    h = hashlib.sha256()
    h.update(str(value.dtype).encode()); h.update(str(value.shape).encode()); h.update(value.tobytes())
    return h.hexdigest()


def load():
    pkg = json.loads((GRAPH / "package.json").read_text())
    c, v, o = pkg["detector_count"], pkg["fault_count"], pkg["observable_count"]
    with np.load(GRAPH / "edge_lists.npz") as z:
        de = np.asarray(z["detector_edges"], np.int64)
        oe = np.asarray(z["observable_edges"], np.int64)
    with np.load(GRAPH / "faults.npz") as z: probabilities = np.asarray(z["probabilities"], np.float64)
    h = sparse.csr_matrix((np.ones(len(de), np.uint8), (de[:, 1], de[:, 0])), shape=(c, v)); h.sort_indices()
    a = sparse.csr_matrix((np.ones(len(oe), np.uint8), (oe[:, 1], oe[:, 0])), shape=(o, v)); a.sort_indices()
    ec, ev, variable_edges = fm.original_edge_tables(h)
    selected = json.loads((METIS / "selected_partition.json").read_text())
    cp = np.asarray(selected["check_partitions"], np.int8)
    fp = np.asarray(selected["fault_partitions"], np.int8)
    with np.load(METIS / "permutations.npz") as z:
        co, cn = np.asarray(z["check_old_to_new"]), np.asarray(z["check_new_to_old"])
        fo, fn = np.asarray(z["fault_old_to_new"]), np.asarray(z["fault_new_to_old"])
    return dict(C=c, V=v, O=o, E=len(de), de=de, oe=oe, p=probabilities, H=h, A=a,
                edge_check=ec, edge_fault=ev, variable_edges=variable_edges,
                check_part=cp, fault_part=fp, co=co, cn=cn, fo=fo, fn=fn)


def pair_matrix(n, groups, group_weights=None):
    """Sparse symmetric pair co-occurrence matrix, with duplicate pairs summed."""
    rows, cols, values = [], [], []
    if group_weights is None: group_weights = itertools.repeat(1.0)
    for group, weight in zip(groups, group_weights):
        values0 = list(map(int, group))
        for i in range(len(values0)):
            for j in range(i + 1, len(values0)):
                if values0[i] == values0[j]: continue
                rows += [values0[i], values0[j]]; cols += [values0[j], values0[i]]; values += [weight, weight]
    matrix = sparse.coo_matrix((np.asarray(values, np.float64), (rows, cols)), shape=(n, n)).tocsr()
    matrix.sum_duplicates(); matrix.sort_indices()
    return matrix


def build_cooccurrence(g):
    check_groups = [chunk for c in range(g["C"]) for chunk in fm.chunks(g["edge_fault"][g["H"].indptr[c]:g["H"].indptr[c + 1]])]
    relay_groups = [g["edge_fault"][chunk] for chunk in fm.chunks(np.arange(g["E"], dtype=np.int64))]
    edge_groups = [chunk for edges in g["variable_edges"] for chunk in fm.chunks(edges)]
    fault_conv = pair_matrix(g["V"], check_groups)
    fault_relay = pair_matrix(g["V"], relay_groups)
    edge_variable = pair_matrix(g["E"], edge_groups)
    # Each added convergence/relay retry costs three controller cycles. An edge collision
    # appears in both MU and NU, whose combined retry sensitivity is five cycles.
    fault_weighted = 3.0 * fault_conv + 3.0 * fault_relay
    edge_weighted = 5.0 * edge_variable
    sparse.save_npz(OUT / "fault_cooccurrence_convergence.npz", fault_conv)
    sparse.save_npz(OUT / "fault_cooccurrence_relay_init.npz", fault_relay)
    sparse.save_npz(OUT / "fault_cooccurrence_weighted.npz", fault_weighted)
    sparse.save_npz(OUT / "edge_cooccurrence_variable.npz", edge_variable)
    sparse.save_npz(OUT / "edge_cooccurrence_weighted.npz", edge_weighted)
    fault_work = np.asarray(g["H"].sum(axis=0)).ravel().astype(np.float64) * 2.0
    edge_work = np.full(g["E"], 2.0)
    summary = dict(
        fault=dict(convergence_groups=len(check_groups), relay_groups=len(relay_groups),
                   convergence_unique_pairs=fault_conv.nnz // 2, relay_unique_pairs=fault_relay.nnz // 2,
                   weighted_unique_pairs=fault_weighted.nnz // 2),
        edge=dict(variable_groups=len(edge_groups), unique_pairs=edge_variable.nnz // 2),
        cycle_sensitivity=dict(variable_mu_plus_nu=5, convergence=3, relay_init=3))
    return fault_weighted.tocsr(), edge_weighted.tocsr(), fault_work, edge_work, summary


def residue_capacities(n):
    return np.asarray([len(range(r, n, P)) for r in range(P)], np.int64)


def greedy_residues(graph, work, locality, balance_lambda, locality_lambda):
    """Greedy weighted coloring with exact address-residue capacities."""
    n = graph.shape[0]
    degree = np.asarray(graph.sum(axis=1)).ravel()
    order = np.lexsort((np.arange(n), -degree))
    capacities = residue_capacities(n)
    counts = np.zeros(P, np.int64); loads = np.zeros(P, np.float64)
    assignment = np.full(n, -1, np.int8)
    target_work = max(float(work.sum()) / P, 1.0)
    conflict_scale = max(float(degree.mean()), 1.0)
    for item in order:
        start, end = graph.indptr[item], graph.indptr[item + 1]
        neighbors, weights = graph.indices[start:end], graph.data[start:end]
        assigned = assignment[neighbors]
        conflict = np.bincount(assigned[assigned >= 0], weights=weights[assigned >= 0], minlength=P)
        choices = []
        for residue in range(P):
            if counts[residue] >= capacities[residue]: continue
            balance = balance_lambda * conflict_scale * ((loads[residue] + work[item]) / target_work)
            local = locality_lambda * conflict_scale * (residue != int(locality[item]))
            choices.append((float(conflict[residue] + balance + local), int(counts[residue]), residue))
        _, _, chosen = min(choices)
        assignment[item] = chosen; counts[chosen] += 1; loads[chosen] += work[item]
    if not np.array_equal(np.bincount(assignment, minlength=P), capacities): raise RuntimeError("Residue capacity failure")
    same_cost = 0.0
    for item in range(n):
        start, end = graph.indptr[item], graph.indptr[item + 1]
        neighbors = graph.indices[start:end]
        same_cost += float(graph.data[start:end][assignment[neighbors] == assignment[item]].sum())
    same_cost *= 0.5
    return assignment, dict(counts=counts, workloads=loads, workload_imbalance=max(abs(loads / (work.sum() / P) - 1)), weighted_same_residue_cost=float(same_cost))


def permutation_from_residues(residues):
    n = len(residues); old_to_new = np.empty(n, np.int64)
    for residue in range(P):
        items = np.flatnonzero(residues == residue)
        slots = np.arange(residue, n, P, dtype=np.int64)
        if len(items) != len(slots): raise RuntimeError("Residue/slot capacity mismatch")
        old_to_new[items] = slots
    new_to_old = np.empty(n, np.int64); new_to_old[old_to_new] = np.arange(n)
    if not np.array_equal(old_to_new % P, residues): raise RuntimeError("Address modulo assignment failure")
    return old_to_new, new_to_old


def bank_layout(name, g, fault_residue, edge_residue):
    fo, fn = permutation_from_residues(fault_residue)
    eo, en = permutation_from_residues(edge_residue)
    check_edges = [eo[np.arange(g["H"].indptr[c], g["H"].indptr[c + 1], dtype=np.int64)] for c in range(g["C"])]
    variable_edges = [eo[g["variable_edges"][old]].copy() for old in fn]
    return dict(name=name, check_order=np.arange(g["C"]), fault_order=fn,
                check_edges=check_edges, variable_edges=variable_edges,
                edge_fault=fo[g["edge_fault"][en]], edge_check=g["edge_check"][en],
                fault_old_to_new=fo, fault_new_to_old=fn, edge_old_to_new=eo, edge_new_to_old=en,
                fault_residues=fault_residue, edge_residues=edge_residue,
                edge_rule="Preserve original neighborhood order; remap each old message identity to its assigned modulo-4 address slot.")


def invariance(g, layout):
    fo, fn = layout["fault_old_to_new"], layout["fault_new_to_old"]
    eo, en = layout["edge_old_to_new"], layout["edge_new_to_old"]
    hp = g["H"][:, fn].tocsr(); ap = g["A"][:, fn].tocsr(); pp = g["p"][fn]
    hback, aback, pback = hp[:, fo], ap[:, fo], pp[fo]
    restored_edge_check = layout["edge_check"][eo]
    restored_edge_fault = fn[layout["edge_fault"][eo]]
    report = dict(
        H_inverse_exact=bool((hback != g["H"]).nnz == 0), A_inverse_exact=bool((aback != g["A"]).nnz == 0),
        probabilities_inverse_exact=bool(np.array_equal(pback, g["p"])),
        detector_fault_incidences_exact=bool(np.array_equal(restored_edge_check, g["edge_check"]) and np.array_equal(restored_edge_fault, g["edge_fault"])),
        observable_fault_incidences_exact=bool((aback != g["A"]).nnz == 0),
        fault_permutation_reversible=bool(np.array_equal(fo[fn], np.arange(g["V"]))),
        edge_permutation_reversible=bool(np.array_equal(eo[en], np.arange(g["E"]))),
        fault_residue_exact=bool(np.array_equal(fo % P, layout["fault_residues"])),
        edge_residue_exact=bool(np.array_equal(eo % P, layout["edge_residues"])),
        no_missing_or_duplicated_faults=bool(np.array_equal(np.sort(fn), np.arange(g["V"]))),
        no_missing_or_duplicated_edges=bool(np.array_equal(np.sort(en), np.arange(g["E"]))),
        neighborhood_membership_unchanged=True,
        neighborhood_iteration_order_changed=True,
        decoder_rerun_required=True)
    required = [value for key, value in report.items() if key not in ("neighborhood_iteration_order_changed", "decoder_rerun_required")]
    if not all(required): raise RuntimeError(f"Invariance failure for {layout['name']}: {report}")
    return report, hp, ap, pp


def metric_row(name, phases, total, bank_stats=None):
    return dict(variant=name, total_requested_accesses=total["logical_accesses"], issued_groups=total["issued_groups"],
                retry_subsets=total["retry_subsets"], variable_mu_retries=phases["variable"]["retry_subsets"] // 2,
                variable_nu_retries=phases["variable"]["retry_subsets"] // 2,
                convergence_retries=phases["convergence"]["retry_subsets"], relay_init_retries=phases["relay_init"]["retry_subsets"],
                mean_active_lanes=total["mean_active_lanes"], lane_utilization=total["mean_lane_utilization"],
                full_four_lane_fraction=total["full_4_lane_fraction"], estimated_structural_cycles=total["estimated_cycles"],
                fault_bank_workload="" if bank_stats is None else json.dumps(bank_stats["fault"]["workloads"].tolist()),
                edge_bank_workload="" if bank_stats is None else json.dumps(bank_stats["edge"]["workloads"].tolist()),
                maximum_bank_workload_imbalance="" if bank_stats is None else max(bank_stats["fault"]["workload_imbalance"], bank_stats["edge"]["workload_imbalance"]))


def layout_bank_stats(layout, g, fault_work, edge_work):
    if "fault_old_to_new" in layout:
        fo = layout["fault_old_to_new"]
    else:
        fo = np.empty(g["V"], np.int64); fo[layout["fault_order"]] = np.arange(g["V"])
    if "edge_old_to_new" in layout:
        eo = layout["edge_old_to_new"]
    elif "old_to_new_edge" in layout:
        eo = layout["old_to_new_edge"]
    else:
        eo = np.arange(g["E"], dtype=np.int64)
    fl = np.bincount(fo % P, weights=fault_work, minlength=P)
    el = np.bincount(eo % P, weights=edge_work, minlength=P)
    return dict(fault=dict(workloads=fl, workload_imbalance=float(max(abs(fl / (fl.sum() / P) - 1)))),
                edge=dict(workloads=el, workload_imbalance=float(max(abs(el / (el.sum() / P) - 1)))))


def cycle_scale(rows, profiles):
    archive = list(csv.DictReader(ARCHIVE.open()))
    result = []
    for row in rows:
        name = row["variant"]; phases = profiles[name]
        iteration = sum(phases[x]["estimated_cycles"] for x in ("check", "variable", "convergence"))
        relay = phases["relay_init"]["estimated_cycles"]
        values = np.asarray([int(x["e0_iterations"]) * iteration + int(x["e0_legs"]) * relay for x in archive], np.int64)
        result.append(dict(variant=name, iteration_cycles=iteration, relay_init_cycles=relay, mean=float(values.mean()),
                           p50=float(np.percentile(values, 50)), p90=float(np.percentile(values, 90)),
                           p95=float(np.percentile(values, 95)), p99=float(np.percentile(values, 99)), maximum=int(values.max())))
    return result


def small_example():
    lines = ["Small graph bank-aware residue example", "", "Variable groups:",
             "V0: e0,e6", "V1: e1,e3", "V2: e2,e4,e7", "V3: e5,e8", "",
             "Illustrative bad original residues:", "faults V0,V1,V2,V3 -> 0,0,1,1", "edges e2,e4,e7 -> 2,2,3",
             "Conflicts: C0 decision group contains V0/V1 on bank 0; V2 variable group contains e2/e4 on bank 2.", "",
             "Bank-aware reassignment:", "faults V0,V1,V2,V3 -> 0,1,2,3", "edges e2,e4,e7 -> 0,1,2",
             "Removed: the listed C0 decision and V2 message conflicts.",
             "Remaining: conflicts can still occur in another group when global capacity forces co-accessed items to share a residue.",
             "The full heuristic minimizes this static co-occurrence cost while enforcing exact residue capacities."]
    (OUT / "small_graph_example.txt").write_text("\n".join(lines) + "\n")


def main():
    OUT.mkdir(parents=True, exist_ok=True); start = time.perf_counter(); g = load()
    fw, ew, fault_work, edge_work, co_summary = build_cooccurrence(g)
    edge_locality = g["fault_part"][g["edge_fault"]]
    definitions = {
        "BA1": dict(balance_lambda=0.0, locality_lambda=0.0, description="weighted same-residue conflict cost only, with mandatory exact residue capacities"),
        "BA2": dict(balance_lambda=0.25, locality_lambda=0.0, description="conflict cost plus access-workload balance penalty"),
        "BA3": dict(balance_lambda=0.25, locality_lambda=0.10, description="BA2 plus weak preference for residue equal to METIS partition ID")}
    ba_layouts, assignment_stats = {}, {}
    for name, cfg in definitions.items():
        fr, fs = greedy_residues(fw, fault_work, g["fault_part"], cfg["balance_lambda"], cfg["locality_lambda"])
        er, es = greedy_residues(ew, edge_work, edge_locality, cfg["balance_lambda"], cfg["locality_lambda"])
        ba_layouts[name] = bank_layout(name, g, fr, er)
        assignment_stats[name] = dict(fault=fs, edge=es)

    original, metis_node, metis_edge = fm.layouts(g["H"], g["co"], g["cn"], g["fo"], g["fn"])
    all_layouts = [original, metis_node, metis_edge] + [ba_layouts[x] for x in definitions]
    profiles, totals = {}, {}
    for layout in all_layouts: profiles[layout["name"]], totals[layout["name"]] = fm.profile(layout, g["check_part"], g["fault_part"])
    names = ["original", "metis_node_only", "metis_partition_edge_reorder", "BA1", "BA2", "BA3"]
    bank_stats = {layout["name"]: layout_bank_stats(layout, g, fault_work, edge_work) for layout in all_layouts}
    rows = [metric_row(name, profiles[name], totals[name], bank_stats[name]) for name in names]
    base = rows[0]
    for row in rows:
        row["retry_change_percent_vs_original"] = 100 * (row["retry_subsets"] / base["retry_subsets"] - 1)
        row["cycle_change_percent_vs_original"] = 100 * (row["estimated_structural_cycles"] / base["estimated_structural_cycles"] - 1)
    with (OUT / "variant_comparison.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    phase_rows = []
    for name in names:
        for phase, m in profiles[name].items():
            phase_rows.append(dict(variant=name, phase=phase, requested_accesses=m["logical_accesses"], issued_groups=m["issued_groups"],
                                   retry_subsets=m["retry_subsets"], mean_active_lanes=m["mean_active_lanes"], lane_utilization=m["mean_lane_utilization"],
                                   full_four_lane_fraction=m["full_4_lane_fraction"], estimated_cycles=m["estimated_cycles"]))
    with (OUT / "phase_metrics.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(phase_rows[0])); w.writeheader(); w.writerows(phase_rows)
    lane_rows = []
    for name in names:
        for phase, m in profiles[name].items():
            for lane, count in m["lane_hist"].items():
                lane_rows.append(dict(variant=name, phase=phase, active_lanes=int(lane), issued_groups=count,
                                      fraction=count / m["issued_groups"]))
    with (OUT / "lane_utilization.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(lane_rows[0])); w.writeheader(); w.writerows(lane_rows)
    cycle_rows = cycle_scale(rows, profiles)
    with (OUT / "cycle_summary.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(cycle_rows[0])); w.writeheader(); w.writerows(cycle_rows)

    acceptable = rows[3:]
    best_row = min(acceptable, key=lambda x: (x["estimated_structural_cycles"], x["retry_subsets"], x["variant"]))
    best = best_row["variant"]; layout = ba_layouts[best]
    inv, hp, ap, pp = invariance(g, layout)
    np.savez_compressed(OUT / "permutations.npz", fault_old_to_new=layout["fault_old_to_new"], fault_new_to_old=layout["fault_new_to_old"],
                        edge_old_to_new=layout["edge_old_to_new"], edge_new_to_old=layout["edge_new_to_old"])
    sparse.save_npz(OUT / "H_bank_aware.npz", hp); sparse.save_npz(OUT / "A_bank_aware.npz", ap)
    np.savez_compressed(OUT / "probabilities_bank_aware.npz", probabilities=pp)
    write_json(OUT / "invariance_report.json", dict(selected_variant=best, checks=inv,
               hashes={k: ahash(layout[k]) for k in ("fault_old_to_new", "fault_new_to_old", "edge_old_to_new", "edge_new_to_old")}))
    for kind, count, locality in (("faults", g["V"], g["fault_part"]), ("edges", g["E"], edge_locality)):
        with (OUT / f"bank_assignments_{kind}.csv").open("w", newline="") as f:
            fields = [f"original_{kind[:-1]}_id", "metis_locality_partition"] + [f"{x}_residue" for x in definitions]
            w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
            for item in range(count):
                rec = {fields[0]: item, "metis_locality_partition": int(locality[item])}
                for name in definitions:
                    mapping = ba_layouts[name][f"{kind[:-1]}_old_to_new"]
                    rec[f"{name}_residue"] = int(mapping[item] % P)
                w.writerow(rec)
    small_example()
    write_json(OUT / "study_manifest.json", dict(status="complete", scope="static graph/access structure only; no shot labels or outcomes used",
               graph=str(GRAPH.relative_to(ROOT)), P=P, objective_cycle_weights=co_summary["cycle_sensitivity"], cooccurrence=co_summary,
               variants=definitions, selected_variant=best, selection_rule="minimum modeled structural cycles, then retries, then name",
               address_construction="old item assigned to address slots residue + 4*k; original ID order within each residue",
               invariance=inv, neighborhood_order_changed=True, decoder_rerun_required=True,
               runtime_seconds=time.perf_counter() - start, cycle_scaling_archive=str(ARCHIVE.relative_to(ROOT))))
    (OUT / "objective_definition.md").write_text("""# Bank-aware objective

The static objective penalizes pairs of mathematical items that occur in one current P=4 request group and receive the same address residue. Fault-pair weights are `3*convergence occurrences + 3*relay-init occurrences`; edge-pair weights are `5*variable occurrences`, reflecting the controller-cycle cost of retries across MU and NU. Exact address-residue capacities are mandatory. BA2 adds access-workload balance; BA3 adds a weak METIS-partition preference. No syndrome, convergence, logical, or tail labels enter construction.

This pairwise objective is a transparent surrogate for the exact retry-subset evaluator. Final selection always uses the unchanged exact folding model.
""")
    best_cycle = next(x for x in cycle_rows if x["variant"] == best)
    (OUT / "README.md").write_text(f"""# Bank-aware P=4 folding layout

Software-only static layout experiment. No RTL, graph connectivity, decoder equations, or trajectory state changed.

Six layouts were evaluated with the unchanged P=4 model. Selected `{best}` by minimum structural cycles, then retry subsets. It has {best_row['retry_subsets']:,} retries ({best_row['retry_change_percent_vs_original']:+.3f}% versus original) and {best_row['estimated_structural_cycles']:,} structural cycles ({best_row['cycle_change_percent_vs_original']:+.3f}%). Archived E0 scaling gives mean {best_cycle['mean']:,.0f}, p95 {best_cycle['p95']:,.0f}, and p99 {best_cycle['p99']:,.0f} modeled cycles.

All selected permutations and graph data round-trip exactly. The mathematical neighborhoods are unchanged, but the new fault IDs change their sorted sparse iteration order. A paired decoder-equivalence check is therefore required before combining this layout with another decoder study. These are modeled folding-efficiency results, not FPGA speedup or decoding claims.
""")
    print(json.dumps(dict(status="complete", selected=best, comparison=rows, cycle_summary=cycle_rows, invariance=inv), indent=2))


if __name__ == "__main__": main()
