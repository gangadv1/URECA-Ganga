#!/usr/bin/env python3
"""Software-only P=4 access model for original and reordered graph layouts."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy import sparse

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
GRAPH = ROOT / "graphs/generated/gross_circuit_level/memory_Z_r12_p0p003"
PART = ROOT / "results/graph-partitioning-metis"
ARCHIVE = ROOT / "results/n1-vs-n2-hardware-latency/per_shot_results.csv"
P = 4


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, default=lambda x: x.item() if isinstance(x, np.generic) else x.tolist()) + "\n")


def sha_array(value: np.ndarray) -> str:
    value = np.ascontiguousarray(value)
    h = hashlib.sha256()
    h.update(str(value.dtype).encode())
    h.update(str(value.shape).encode())
    h.update(value.tobytes())
    return h.hexdigest()


def load_problem():
    package = json.loads((GRAPH / "package.json").read_text())
    c, v = package["detector_count"], package["fault_count"]
    with np.load(GRAPH / "edge_lists.npz") as data:
        de = np.asarray(data["detector_edges"], dtype=np.int64)
    h = sparse.csr_matrix((np.ones(len(de), np.uint8), (de[:, 1], de[:, 0])), shape=(c, v))
    h.sort_indices()
    with np.load(PART / "permutations.npz") as data:
        co = np.asarray(data["check_old_to_new"], dtype=np.int64)
        cn = np.asarray(data["check_new_to_old"], dtype=np.int64)
        fo = np.asarray(data["fault_old_to_new"], dtype=np.int64)
        fn = np.asarray(data["fault_new_to_old"], dtype=np.int64)
    selected = json.loads((PART / "selected_partition.json").read_text())
    cp = np.asarray(selected["check_partitions"], dtype=np.int8)
    fp = np.asarray(selected["fault_partitions"], dtype=np.int8)
    if (c, v, h.nnz) != (1728, 67752, 391320):
        raise RuntimeError("Unexpected canonical graph dimensions")
    return h, co, cn, fo, fn, cp, fp


def original_edge_tables(h: sparse.csr_matrix):
    """Return original edge endpoints and variable-to-edge lists."""
    c, v = h.shape
    edge_check = np.repeat(np.arange(c, dtype=np.int64), np.diff(h.indptr))
    edge_fault = h.indices.astype(np.int64, copy=True)
    lists = [[] for _ in range(v)]
    for edge, fault in enumerate(edge_fault):
        lists[int(fault)].append(edge)
    return edge_check, edge_fault, [np.asarray(x, dtype=np.int64) for x in lists]


def layouts(h, co, cn, fo, fn):
    ec, ev, old_var_edges = original_edge_tables(h)
    original = dict(
        name="original",
        check_order=np.arange(h.shape[0]), fault_order=np.arange(h.shape[1]),
        check_edges=[np.arange(h.indptr[c], h.indptr[c + 1], dtype=np.int64) for c in range(h.shape[0])],
        variable_edges=old_var_edges, edge_fault=ev.copy(), edge_check=ec.copy(),
        edge_rule="Original check-CSR edge IDs and original node IDs.")

    # Node-only means mathematical nodes move, while every message retains its old edge ID.
    node_check_edges = [np.arange(h.indptr[old], h.indptr[old + 1], dtype=np.int64) for old in cn]
    node_variable_edges = [old_var_edges[old].copy() for old in fn]
    node_only = dict(
        name="metis_node_only", check_order=cn.copy(), fault_order=fn.copy(),
        check_edges=node_check_edges, variable_edges=node_variable_edges,
        edge_fault=fo[ev], edge_check=co[ec],
        edge_rule="Checks/faults use METIS IDs; original edge/message IDs are retained exactly.")

    # Assign edge IDs in new check order. Inside a check, new fault ID order groups fault partitions.
    tuples = [(int(co[ec[e]]), int(fo[ev[e]]), int(e)) for e in range(len(ev))]
    new_to_old_edge = np.asarray([x[2] for x in sorted(tuples)], dtype=np.int64)
    old_to_new_edge = np.empty(len(ev), dtype=np.int64)
    old_to_new_edge[new_to_old_edge] = np.arange(len(ev), dtype=np.int64)
    edge_check_new = co[ec[new_to_old_edge]]
    edge_fault_new = fo[ev[new_to_old_edge]]
    check_edges = []
    for check in range(h.shape[0]):
        check_edges.append(np.flatnonzero(edge_check_new == check).astype(np.int64))
    variable_edges = [[] for _ in range(h.shape[1])]
    for edge, fault in enumerate(edge_fault_new):
        variable_edges[int(fault)].append(edge)
    edge_reordered = dict(
        name="metis_partition_edge_reorder", check_order=cn.copy(), fault_order=fn.copy(),
        check_edges=check_edges,
        variable_edges=[np.asarray(x, dtype=np.int64) for x in variable_edges],
        edge_fault=edge_fault_new, edge_check=edge_check_new,
        old_to_new_edge=old_to_new_edge, new_to_old_edge=new_to_old_edge,
        edge_rule="Sort incidences by (new check ID, new fault ID, old edge ID), then assign consecutive edge IDs.")
    return original, node_only, edge_reordered


def chunks(values):
    for start in range(0, len(values), P):
        yield np.asarray(values[start:start + P], dtype=np.int64)


def stable_bank_subsets(addresses):
    """Mirror the RTL: first pending lane for each address%4 bank wins."""
    pending = list(map(int, addresses))
    issued = []
    while pending:
        seen = set()
        subset = []
        remain = []
        for address in pending:
            bank = address % P
            if bank not in seen:
                seen.add(bank)
                subset.append(address)
            else:
                remain.append(address)
        issued.append(subset)
        pending = remain
    return issued


def empty_phase(name):
    return dict(phase=name, logical_accesses=0, issued_groups=0, conflict_events=0,
                retry_subsets=0, lane_hist={str(i): 0 for i in range(1, 5)},
                node_retry=defaultdict(int), partition_logical=[0, 0, 0, 0])


def add_group(metric, addresses, node=None, partition=None, conflict_split=False):
    addresses = list(map(int, addresses))
    metric["logical_accesses"] += len(addresses)
    subsets = stable_bank_subsets(addresses) if conflict_split else [addresses]
    metric["issued_groups"] += len(subsets)
    retries = max(0, len(subsets) - 1)
    metric["conflict_events"] += retries
    metric["retry_subsets"] += retries
    if retries and node is not None:
        metric["node_retry"][int(node)] += retries
    if partition is not None:
        metric["partition_logical"][int(partition)] += len(addresses)
    for subset in subsets:
        metric["lane_hist"][str(len(subset))] += 1


def finalize(metric):
    groups = metric["issued_groups"]
    active = sum(int(k) * v for k, v in metric["lane_hist"].items())
    metric["mean_active_lanes"] = active / groups if groups else 0.0
    metric["mean_lane_utilization"] = metric["mean_active_lanes"] / P
    metric["full_4_lane_fraction"] = metric["lane_hist"]["4"] / groups if groups else 0.0
    worst = sorted(metric.pop("node_retry").items(), key=lambda x: (-x[1], x[0]))[:10]
    metric["worst_local_nodes"] = [{"node": n, "retry_subsets": r} for n, r in worst]
    return metric


def profile(layout, cp, fp):
    phases = {x: empty_phase(x) for x in ("check", "variable", "convergence", "relay_init")}
    # Check: three scalar node reads, two contiguous nu passes, one contiguous mu write.
    for new_c, edges in enumerate(layout["check_edges"]):
        part = int(cp[int(layout["check_order"][new_c])])
        for _ in range(3): add_group(phases["check"], [new_c], new_c, part)
        for edge_chunk in chunks(edges):
            add_group(phases["check"], edge_chunk, new_c, part)
            add_group(phases["check"], edge_chunk, new_c, part)
            add_group(phases["check"], edge_chunk, new_c, part)
    # Variable: seven scalar state transactions, packed permutation read, mu gather, nu write.
    for new_v, edges in enumerate(layout["variable_edges"]):
        part = int(fp[int(layout["fault_order"][new_v])])
        for _ in range(7): add_group(phases["variable"], [new_v], new_v, part)
        for edge_chunk in chunks(edges):
            add_group(phases["variable"], np.arange(len(edge_chunk)), new_v, part)  # packed VE word
            add_group(phases["variable"], edge_chunk, new_v, part, True)
            add_group(phases["variable"], edge_chunk, new_v, part, True)
    # Convergence: three scalar reads, packed edge-fault read, arbitrary decision gather.
    for new_c, edges in enumerate(layout["check_edges"]):
        part = int(cp[int(layout["check_order"][new_c])])
        for _ in range(3): add_group(phases["convergence"], [new_c], new_c, part)
        for edge_chunk in chunks(edges):
            add_group(phases["convergence"], np.arange(len(edge_chunk)), new_c, part)
            add_group(phases["convergence"], layout["edge_fault"][edge_chunk], new_c, part, True)
    # Relay init traverses global consecutive edge-ID chunks.
    for edge_chunk in chunks(np.arange(len(layout["edge_fault"],), dtype=np.int64)):
        part = int(fp[int(layout["fault_order"][int(layout["edge_fault"][edge_chunk[0]])])])
        add_group(phases["relay_init"], edge_chunk, int(edge_chunk[0]), part)
        add_group(phases["relay_init"], layout["edge_fault"][edge_chunk], int(edge_chunk[0]), part, True)
        add_group(phases["relay_init"], edge_chunk, int(edge_chunk[0]), part)

    for key in phases: finalize(phases[key])
    qv = sum(math.ceil(len(x) / P) for x in layout["variable_edges"])
    qc = sum(math.ceil(len(x) / P) for x in layout["check_edges"])
    qe = math.ceil(len(layout["edge_fault"]) / P)
    c, v = len(layout["check_edges"]), len(layout["variable_edges"])
    rv = phases["variable"]["retry_subsets"] // 2
    rc = phases["convergence"]["retry_subsets"]
    rr = phases["relay_init"]["retry_subsets"]
    phases["check"]["estimated_cycles"] = 9 * c + 5 * qc + 1
    phases["variable"]["estimated_cycles"] = 14 * v + 8 * qv + 5 * rv + 1
    phases["convergence"]["estimated_cycles"] = 8 * c + 6 * qc + 3 * rc + 1
    phases["relay_init"]["estimated_cycles"] = 8 * qe + 3 * rr + 1
    total = empty_phase("all_phases_once")
    for phase in phases.values():
        for field in ("logical_accesses", "issued_groups", "conflict_events", "retry_subsets"):
            total[field] += phase[field]
        for lane in total["lane_hist"]: total["lane_hist"][lane] += phase["lane_hist"][lane]
        total["partition_logical"] = [a + b for a, b in zip(total["partition_logical"], phase["partition_logical"])]
    total["node_retry"] = defaultdict(int)
    finalize(total)
    total["estimated_cycles"] = sum(x["estimated_cycles"] for x in phases.values())
    return phases, total


def pct(new, old):
    return None if old == 0 else 100.0 * (new - old) / old


def small_example():
    edges = [(0, 0), (0, 1), (0, 2), (1, 1), (1, 2), (1, 3), (2, 0), (2, 2), (2, 3)]
    # A deterministic illustrative partition. Fault IDs are grouped P0 then P1.
    cp = [0, 1, 1]; fp = [0, 0, 1, 1]
    old_groups = [[i for i in range(s, min(s + 4, len(edges)))] for s in range(0, len(edges), 4)]
    order = sorted(range(len(edges)), key=lambda e: (cp[edges[e][0]], fp[edges[e][1]], edges[e][0], edges[e][1], e))
    old_to_new = {old: new for new, old in enumerate(order)}
    lines = ["Small 3-check / 4-variable P=4 access example", "", "Original edges:"]
    lines += [f"e{i}: C{c}--V{v} (fault bank V{v}%4={v%4})" for i, (c, v) in enumerate(edges)]
    lines += ["", "Original global edge groups:"] + [str(g) for g in old_groups]
    lines += ["", "Partition assignment:", "P0: C0, V0, V1", "P1: C1, C2, V2, V3",
              "", "Partition-aware edge order (old -> new):"]
    lines += [f"e{old} -> e{old_to_new[old]}: C{edges[old][0]}--V{edges[old][1]}" for old in order]
    new_groups = [[f"e{i}:C{edges[old][0]}--V{edges[old][1]}" for i, old in enumerate(order[s:s + 4], start=s)] for s in range(0, len(order), 4)]
    lines += ["", "Reordered global edge groups:"] + [str(g) for g in new_groups]
    lines += ["", "Observation:",
              "Consecutive edge-ID groups never conflict in edge-message RAM because their IDs occupy distinct modulo-4 banks.",
              "Fault/decision gathers can still conflict whenever a group contains repeated fault-ID modulo-4 banks.",
              "With only four variables, V0..V3 already occupy distinct banks; this fixture therefore explains where conflicts remain, but does not manufacture a disappearing conflict."]
    (OUT / "small_graph_folding_example.txt").write_text("\n".join(lines) + "\n")


def trajectory_aggregate(phase_profiles):
    rows = list(csv.DictReader(ARCHIVE.open()))
    out = {}
    for name, phases in phase_profiles.items():
        iteration = sum(phases[p]["estimated_cycles"] for p in ("check", "variable", "convergence"))
        relay = phases["relay_init"]["estimated_cycles"]
        totals = np.asarray([int(r["e0_iterations"]) * iteration + int(r["e0_legs"]) * relay for r in rows], dtype=np.int64)
        out[name] = dict(iteration_cycles=iteration, relay_init_cycles=relay, shots=len(rows),
                         mean=float(totals.mean()), p50=float(np.percentile(totals, 50)),
                         p90=float(np.percentile(totals, 90)), p95=float(np.percentile(totals, 95)),
                         p99=float(np.percentile(totals, 99)), minimum=int(totals.min()), maximum=int(totals.max()))
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    h, co, cn, fo, fn, cp, fp = load_problem()
    variants = layouts(h, co, cn, fo, fn)
    profiles, totals = {}, {}
    for layout in variants:
        profiles[layout["name"]], totals[layout["name"]] = profile(layout, cp, fp)

    # Validate current RTL counter equations against the archived one-iteration reference.
    expected = {"check": 508753, "variable": 2489173, "convergence": 790855, "relay_init": 969916}
    model_validation = {p: profiles["original"][p]["estimated_cycles"] == n for p, n in expected.items()}
    if not all(model_validation.values()):
        raise RuntimeError(f"Original schedule model did not reproduce RTL reference: {model_validation}")

    # Connectivity and reversible edge-identity checks for variant C.
    er = variants[2]
    edge_inverse = np.array_equal(er["old_to_new_edge"][er["new_to_old_edge"]], np.arange(h.nnz))
    original_pairs = np.c_[variants[0]["edge_check"], variants[0]["edge_fault"]]
    restored_pairs = np.c_[cn[er["edge_check"]], fn[er["edge_fault"]]][er["old_to_new_edge"]]
    connectivity_exact = np.array_equal(original_pairs, restored_pairs)
    if not edge_inverse or not connectivity_exact:
        raise RuntimeError("Edge reorder invariance failure")

    phase_rows = []
    lane_rows = []
    for name, phases in profiles.items():
        for phase, m in phases.items():
            phase_rows.append({k: m[k] for k in ("phase", "logical_accesses", "issued_groups", "conflict_events", "retry_subsets", "mean_active_lanes", "mean_lane_utilization", "full_4_lane_fraction", "estimated_cycles")} | {"variant": name, "partition_logical": json.dumps(m["partition_logical"]), "worst_local_nodes": json.dumps(m["worst_local_nodes"])})
            for lane, count in m["lane_hist"].items():
                lane_rows.append(dict(variant=name, phase=phase, active_lanes=int(lane), issued_groups=count, fraction=count/m["issued_groups"]))
    with (OUT / "phase_metrics.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(phase_rows[0])); w.writeheader(); w.writerows(phase_rows)
    with (OUT / "lane_utilization.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(lane_rows[0])); w.writeheader(); w.writerows(lane_rows)

    base = totals["original"]
    comparison = []
    for name, m in totals.items():
        row = dict(variant=name)
        for key in ("logical_accesses", "issued_groups", "conflict_events", "retry_subsets", "mean_active_lanes", "mean_lane_utilization", "full_4_lane_fraction", "estimated_cycles"):
            row[key] = m[key]; row[key + "_absolute_vs_original"] = m[key] - base[key]; row[key + "_percent_vs_original"] = pct(m[key], base[key])
        comparison.append(row)
    with (OUT / "variant_comparison.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(comparison[0])); w.writeheader(); w.writerows(comparison)
    with (OUT / "layout_summary.csv").open("w", newline="") as f:
        fields = ["variant", "edge_rule", "edge_ids_changed", "fault_ids_changed"]
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for x in variants: w.writerow(dict(variant=x["name"], edge_rule=x["edge_rule"], edge_ids_changed=x["name"].endswith("edge_reorder"), fault_ids_changed=x["name"] != "original"))

    trajectory = trajectory_aggregate(profiles)
    write_json(OUT / "conflict_summary.json", dict(variants={k: dict(total=totals[k], phases=profiles[k]) for k in totals}, trajectory_scaled_e0_archive=trajectory))
    small_example()
    manifest = dict(
        status="complete", scope="software-only structural P=4 access model; no RTL or decoder execution",
        graph=str(GRAPH.relative_to(ROOT)), selected_partition_seed=2, P=4,
        bank_mapping="logical address modulo 4", retry_rule="stable first pending lane per bank",
        grouping="up to four consecutive incidences per current RTL node/edge traversal",
        node_only_edge_identity_preserved=True, edge_reorder_rule=er["edge_rule"],
        invariance=dict(edge_permutation_inverse=edge_inverse, detector_fault_connectivity_exact=connectivity_exact,
                        nodes_unchanged=True, edges_unchanged=True, decoder_not_run=True),
        model_validation=dict(reference="fpga/verification/tier2_p0p003/verification_summary.json gamma_source_boundary phase cycles", expected_cycles=expected, exact=model_validation),
        hashes=dict(check_old_to_new=sha_array(co), fault_old_to_new=sha_array(fo), edge_new_to_old=sha_array(er["new_to_old_edge"])),
        trajectory_scaling=dict(archive=str(ARCHIVE.relative_to(ROOT)), trajectory="N=1/E0 archived iterations and relay legs; schedules themselves are state-independent", summaries=trajectory))
    write_json(OUT / "study_manifest.json", manifest)
    node = totals["metis_node_only"]
    edge = totals["metis_partition_edge_reorder"]
    (OUT / "README.md").write_text(f"""# Graph-partitioning P=4 folding/access model

Software-only comparison of the canonical Tier-2 graph in three layouts: original, METIS node IDs with original edge/message IDs, and a deterministic partition-aware edge-ID reorder. No RTL, decoder equations, graph incidences, or validated trajectories are changed.

The model mirrors the current controllers: groups contain up to four consecutive traversal entries; bank is `logical_address % 4`; conflicts are retried using the stable first-pending-lane-per-bank subset. Its original-layout phase-cycle equations reproduce all four phase counters in the Tier-2 RTL verification summary exactly.

Node-only reordering deliberately retains old edge/message IDs. The separate edge variant sorts incidences by `(new check ID, new fault ID, old edge ID)` and assigns consecutive edge IDs. This is an access-layout experiment only; Relay-BP was not rerun with the new edge order.

## Full-graph result

| Layout | Retry subsets | Mean active lanes | Full-4 fraction | One-iteration-plus-init cycles |
|---|---:|---:|---:|---:|
| Original | {base['retry_subsets']:,} | {base['mean_active_lanes']:.6f} | {base['full_4_lane_fraction']:.6%} | {base['estimated_cycles']:,} |
| METIS nodes only | {node['retry_subsets']:,} | {node['mean_active_lanes']:.6f} | {node['full_4_lane_fraction']:.6%} | {node['estimated_cycles']:,} |
| METIS + edge reorder | {edge['retry_subsets']:,} | {edge['mean_active_lanes']:.6f} | {edge['full_4_lane_fraction']:.6%} | {edge['estimated_cycles']:,} |

Node-only changes retries by {pct(node['retry_subsets'], base['retry_subsets']):+.3f}% and modeled cycles by {pct(node['estimated_cycles'], base['estimated_cycles']):+.3f}%. The edge-reordered variant changes retries by {pct(edge['retry_subsets'], base['retry_subsets']):+.3f}% and modeled cycles by {pct(edge['estimated_cycles'], base['estimated_cycles']):+.3f}%. These are software-model effects, not FPGA speedup measurements.

Run with `../.venv/bin/python results/graph-partitioning-folding-model/run_folding_layout_comparison.py`.
""")
    print(json.dumps(dict(status="complete", model_validation=model_validation, totals=totals, trajectory=trajectory), indent=2))


if __name__ == "__main__":
    main()
