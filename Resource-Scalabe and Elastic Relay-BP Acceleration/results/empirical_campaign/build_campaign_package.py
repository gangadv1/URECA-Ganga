from __future__ import annotations

import csv
import hashlib
import json
import platform
import shutil
import subprocess
from pathlib import Path

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results" / "empirical_campaign"
RESULTS = ROOT / "results"
COMMIT = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT.parent, text=True).strip()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else ["status"]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def source_status(path: Path, source_type: str, status: str = "REUSED") -> dict[str, object]:
    return {
        "source_type": source_type,
        "git_commit": COMMIT,
        "script": "archived artifact; verified in this campaign environment",
        "configuration": "see source manifest/README",
        "seed": "see source manifest",
        "shots": "see source artifact",
        "runtime": "not recorded in source artifact",
        "status": status,
        "result_file": str(path.relative_to(ROOT.parent)),
        "notes": f"sha256={sha256(path)}",
    }


def build_p_tables() -> None:
    structural = read_csv(RESULTS / "folding-factor-sweep/p_sweep_structural.csv")
    trajectory = read_csv(RESULTS / "folding-factor-sweep/p_sweep_trajectory.csv")
    write_csv(OUT / "p_scaling/p_scaling_results.csv", structural)
    write_csv(OUT / "folding/folding_results.csv", [
        {**row, "source_type": "SOFTWARE-SIMULATED", "experiment_id": "folding_factor_sweep"}
        for row in structural
    ])
    write_csv(OUT / "p_scaling/trajectory_results.csv", trajectory)

    rows = [r for r in structural if r["layout"] == "original"]
    p = [int(r["P"]) for r in rows]
    cycles = [int(r["estimated_structural_cycles"]) for r in rows]
    utilization = [float(r["lane_utilization"]) * 100 for r in rows]
    fig, axis = plt.subplots(figsize=(6.5, 4.0))
    axis.plot(p, cycles, marker="o", label="structural cycles")
    axis.set_xlabel("Folding lanes P")
    axis.set_ylabel("Modeled structural cycles")
    axis.set_xticks(p)
    axis.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUT / "p_scaling/p_cycles.png", dpi=180)
    plt.close(fig)
    fig, axis = plt.subplots(figsize=(6.5, 4.0))
    axis.plot(p, utilization, marker="o", color="#c35b2c", label="lane utilization")
    axis.set_xlabel("Folding lanes P")
    axis.set_ylabel("Lane utilization (%)")
    axis.set_xticks(p)
    axis.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUT / "p_scaling/p_utilization.png", dpi=180)
    plt.close(fig)


def build_ba2_table() -> None:
    source = RESULTS / "bank-aware-folding-layout/variant_comparison.csv"
    rows = read_csv(source)
    for row in rows:
        row["source_type"] = "SOFTWARE-SIMULATED"
        row["experiment_id"] = "folding_heuristics_p4"
    write_csv(OUT / "ba2/ba2_results.csv", rows)
    fig, axis = plt.subplots(figsize=(7.0, 4.0))
    names = [r["variant"] for r in rows]
    retries = [int(r["retry_subsets"]) for r in rows]
    axis.bar(names, retries, color="#2c6e8f")
    axis.set_ylabel("Retry subsets")
    axis.set_title("P=4 folding heuristic comparison")
    axis.tick_params(axis="x", rotation=35)
    fig.tight_layout()
    fig.savefig(OUT / "ba2/heuristic_retries.png", dpi=180)
    plt.close(fig)


def build_metis_table() -> None:
    source = RESULTS / "graph-partitioning-metis/README.md"
    rows = [
        {"method": "random_balanced", "edge_cut": 0.749532 * 391320, "cut_percent": 74.9532, "boundary_checks_percent": 100.0, "boundary_faults_percent": 99.5543, "communication_volume": "NOT MEASURED", "source_type": "SOFTWARE-SIMULATED", "status": "REUSED"},
        {"method": "greedy_balanced", "edge_cut": 0.543698 * 391320, "cut_percent": 54.3698, "boundary_checks_percent": 100.0, "boundary_faults_percent": 97.2724, "communication_volume": "NOT MEASURED", "source_type": "SOFTWARE-SIMULATED", "status": "REUSED"},
        {"method": "metis_limited_selected", "edge_cut": 40882, "cut_percent": 10.4472, "boundary_checks_percent": 78.4722, "boundary_faults_percent": 34.5850, "communication_volume": "NOT MEASURED", "source_type": "SOFTWARE-SIMULATED", "status": "REUSED"},
    ]
    for row in rows:
        row.update(total_vertices=69480, total_edges=391320, balance_ratio="see source partition_metrics.json", source_file=str(source.relative_to(ROOT.parent)))
    write_csv(OUT / "metis/metis_partition_results.csv", rows)
    fig, axis = plt.subplots(figsize=(7.0, 4.0))
    axis.bar([r["method"] for r in rows], [r["cut_percent"] for r in rows], color=["#999999", "#c35b2c", "#2c6e8f"])
    axis.set_ylabel("Edge cut (%)")
    axis.tick_params(axis="x", rotation=25)
    fig.tight_layout()
    fig.savefig(OUT / "metis/edge_cut.png", dpi=180)
    plt.close(fig)


def build_ler_table() -> None:
    source = RESULTS / "paper-ler-reproduction-expanded/per_p_summary.csv"
    rows = read_csv(source)
    for row in rows:
        row["source_type"] = "SOFTWARE-SIMULATED"
        row["experiment_id"] = "bounded_ler_campaign"
        row["status"] = "BOUNDED_ARCHIVED_RUN"
    write_csv(OUT / "ler/ler_results.csv", rows)
    fig, axis = plt.subplots(figsize=(6.5, 4.0))
    p = [float(r["p"]) for r in rows]
    ler = [float(r["logical_error_rate"]) for r in rows]
    high = [float(r["ler_wilson_95_high"]) for r in rows]
    axis.errorbar(p, ler, yerr=[ler[i] for i in range(len(ler))], uplims=True, fmt="o", label="observed LER")
    axis.scatter(p, high, marker="_", color="#c35b2c", label="Wilson upper bound")
    axis.set_xlabel("Physical error rate p")
    axis.set_ylabel("Logical error rate")
    axis.grid(alpha=0.25)
    axis.legend()
    fig.tight_layout()
    fig.savefig(OUT / "ler/ler_vs_p.png", dpi=180)
    plt.close(fig)


def build_operations_table() -> None:
    edges = 391320
    checks = 1728
    variables = 67752
    rows = []
    for n in (1, 2, 4):
        for p in (2, 4, 8):
            rows.append({
                "N": n, "P": p, "check_nodes": checks, "variable_nodes": variables, "incidences": edges,
                "check_message_updates_per_iteration": edges, "variable_message_updates_per_iteration": edges,
                "edge_message_accesses_per_iteration": 2 * edges, "syndrome_checks_per_iteration": checks,
                "operations_per_iteration": 4 * edges + checks, "total_operations_per_decode": "NOT MEASURED",
                "source_type": "ANALYTICAL", "status": "DERIVED_FROM_GRAPH_INCIDENCE", "notes": "Structural operation proxy only; no instruction-level profiler was run."
            })
    write_csv(OUT / "operations/operation_counts.csv", rows)


def build_blocked_campaign_tables() -> None:
    blocked = [{
        "status": "BLOCKED", "source_type": "BLOCKED", "git_commit": COMMIT,
        "reason": reason, "required_next_step": next_step,
    } for reason, next_step in (
        ("Unified frozen baseline was not selected for a new run", "Select and hash the Tier-2 package and paired cohort"),
        ("N=4 and complete N x P factorial are not present in archived evidence", "Run matched N=1/2/4 by P=2/4/8 with frozen seeds"),
    )]
    write_csv(OUT / "baseline.csv", blocked[:1])
    write_csv(OUT / "n_sweep.csv", blocked[1:])
    write_csv(OUT / "n_x_p_factorial.csv", blocked[1:])


def build_memory_and_rtl() -> None:
    memory_source = RESULTS / "relaybp-memory-m4-validation/validated_memory_model.csv"
    memory_rows = read_csv(memory_source)
    total = sum(int(r["total_bits"]) for r in memory_rows)
    write_csv(OUT / "memory/memory_results.csv", memory_rows + [{"component": "M4_total", "bits": "", "copies": "", "total_bits": total}])
    rtl = json.loads((RESULTS / "m4-memory-fabric-rtl/study_manifest.json").read_text())
    write_csv(OUT / "rtl/rtl_results.csv", [{"status": rtl["status"], "classification": rtl["classification"], **{k: rtl[k] for k in ("directed_tests", "stress_cycles_per_mode", "stress_trace_requests_per_mode", "template_trace_requests_per_mode", "trace_matches", "trace_mismatches", "message_assertion_failures", "shared_arbitration_stalls", "dropped_requests", "duplicated_responses", "same_address_dual_reads_tested", "full_decoder_integrated", "full_decoder_synthesized")}}])


def build_comparison_and_gari() -> None:
    n2 = json.loads((RESULTS / "n1-vs-n2-hardware-latency/aggregate_summary.json").read_text())
    write_csv(OUT / "relay_comparison/relay_comparison_results.csv", [
        {"architecture": "N=1 canonical fixed Relay-BP", "source_type": "SOFTWARE-SIMULATED", "status": "REUSED", "source_file": str((RESULTS / "n1-vs-n2-hardware-latency/aggregate_summary.json").relative_to(ROOT.parent)), "details": json.dumps(n2.get("n1_latency", {}), separators=(",", ":"))},
        {"architecture": "N=2 first-success Relay-BP", "source_type": "SOFTWARE-SIMULATED", "status": "REUSED", "source_file": str((RESULTS / "n1-vs-n2-hardware-latency/aggregate_summary.json").relative_to(ROOT.parent)), "details": json.dumps(n2.get("n2_latency", {}), separators=(",", ":"))},
        {"architecture": "Relay-BP + P=4 + BA2", "source_type": "SOFTWARE-SIMULATED", "status": "REUSED", "source_file": str((RESULTS / "final-software-model-summary/final_report.md").relative_to(ROOT.parent)), "details": "15.043% lower trajectory-weighted modeled mean than original P=4; exact archived equivalence."},
        {"architecture": "Full FPGA implementation", "source_type": "BLOCKED", "status": "BLOCKED", "source_file": "", "details": "Vivado and target FPGA part/constraints unavailable."},
    ])
    write_csv(OUT / "gari/gari_comparison.csv", [
        {"system": "GARI", "source_type": "LITERATURE", "status": "NOT_MATCHED", "cycles_or_latency": "paper-reported; not a matched software run", "bram": 704, "lut": 122393, "ff": 111697, "fmax_mhz": 274, "notes": "Literature values from results/gari-comparison/final_gari_comparison.md; not our measurement."},
        {"system": "URECA Relay-BP M4", "source_type": "ANALYTICAL/RTL-SIMULATED", "status": "NOT_MATCHED", "cycles_or_latency": "model-dependent", "bram": "analytical estimate", "lut": "NOT MEASURED", "ff": "NOT MEASURED", "fmax_mhz": "NOT MEASURED", "notes": "No apples-to-apples GARI software artifact verified."},
    ])


def build_manifest_and_evidence() -> None:
    entries = [
        {"experiment_id": "environment", "experiment_name": "isolated campaign environment", **source_status(ROOT / "requirements.txt", "MEASURED", "COMPLETE")},
        {"experiment_id": "p_sweep", "experiment_name": "P=2/4/8 folding sweep", **source_status(RESULTS / "folding-factor-sweep/p_sweep_structural.csv", "SOFTWARE-SIMULATED")},
        {"experiment_id": "ba2_heuristics", "experiment_name": "folding heuristic comparison", **source_status(RESULTS / "bank-aware-folding-layout/variant_comparison.csv", "SOFTWARE-SIMULATED")},
        {"experiment_id": "metis", "experiment_name": "METIS partition quality", **source_status(RESULTS / "graph-partitioning-metis/partition_metrics.json", "SOFTWARE-SIMULATED")},
        {"experiment_id": "ler", "experiment_name": "bounded LER sweep", **source_status(RESULTS / "paper-ler-reproduction-expanded/per_p_summary.csv", "SOFTWARE-SIMULATED", "BOUNDED")},
        {"experiment_id": "n1_n2", "experiment_name": "N=1 versus N=2 first-success", **source_status(RESULTS / "n1-vs-n2-hardware-latency/aggregate_summary.json", "SOFTWARE-SIMULATED")},
        {"experiment_id": "m4_validation", "experiment_name": "M4 memory/equivalence validation", **source_status(RESULTS / "relaybp-memory-m4-validation/study_manifest.json", "ANALYTICAL/SOFTWARE-SIMULATED")},
        {"experiment_id": "m4_rtl", "experiment_name": "M4 RTL fabric simulation", **source_status(RESULTS / "m4-memory-fabric-rtl/study_manifest.json", "RTL-SIMULATED")},
        {"experiment_id": "gari", "experiment_name": "GARI comparison", **source_status(RESULTS / "gari-comparison/final_gari_comparison.md", "LITERATURE/BLOCKED", "NOT_MATCHED")},
        {"experiment_id": "n4_factorial", "experiment_name": "N=4 factorial", "source_type": "BLOCKED", "git_commit": COMMIT, "script": "", "configuration": "N=4 not present in archived evidence", "seed": "", "shots": "", "runtime": "", "status": "BLOCKED", "result_file": "", "notes": "Requires new controlled decoder run."},
        {"experiment_id": "fpga_synthesis", "experiment_name": "Vivado synthesis/timing", "source_type": "BLOCKED", "git_commit": COMMIT, "script": "", "configuration": "target part and Vivado unavailable", "seed": "", "shots": "", "runtime": "", "status": "BLOCKED", "result_file": "", "notes": "Analytical BRAM is not FPGA measurement."},
    ]
    write_csv(OUT / "experiment_manifest.csv", entries)
    evidence = [
        {"claim": "P=4 original modeled structural cycles", "metric": "estimated_structural_cycles", "value": 4758697, "unit": "cycles", "source_type": "SOFTWARE-SIMULATED", "experiment_id": "p_sweep", "source_file": "results/folding-factor-sweep/p_sweep_structural.csv", "git_commit": COMMIT, "confidence/status": "archived exact row"},
        {"claim": "BA2 reduces P=4 retry subsets", "metric": "retry_subsets", "value": "336291 -> 142566", "unit": "subsets", "source_type": "SOFTWARE-SIMULATED", "experiment_id": "ba2_heuristics", "source_file": "results/bank-aware-folding-layout/variant_comparison.csv", "git_commit": COMMIT, "confidence/status": "archived exact row"},
        {"claim": "METIS selected edge cut", "metric": "cut_percent", "value": 10.4472, "unit": "%", "source_type": "SOFTWARE-SIMULATED", "experiment_id": "metis", "source_file": "results/graph-partitioning-metis/README.md", "git_commit": COMMIT, "confidence/status": "limited METIS baseline"},
        {"claim": "M4 RTL trace equivalence", "metric": "trace_mismatches", "value": 0, "unit": "mismatches", "source_type": "RTL-SIMULATED", "experiment_id": "m4_rtl", "source_file": "results/m4-memory-fabric-rtl/study_manifest.json", "git_commit": COMMIT, "confidence/status": "standalone fabric only"},
        {"claim": "LER p=0.005 bounded point estimate", "metric": "logical_error_rate", "value": 0.07421875, "unit": "LER", "source_type": "SOFTWARE-SIMULATED", "experiment_id": "ler", "source_file": "results/paper-ler-reproduction-expanded/per_p_summary.csv", "git_commit": COMMIT, "confidence/status": "19/256 logical failures; bounded archived run"},
        {"claim": "GARI hardware resources", "metric": "BRAM/LUT/FF/Fmax", "value": "704 / 122393 / 111697 / 274", "unit": "reported literature units", "source_type": "LITERATURE", "experiment_id": "gari", "source_file": "results/gari-comparison/final_gari_comparison.md", "git_commit": COMMIT, "confidence/status": "not matched and not our measurement"},
    ]
    write_csv(OUT / "evidence_matrix.csv", evidence)


def build_reports() -> None:
    (OUT / "professor_questions.md").write_text("""# Professor's Questions — Answered with Numbers\n\n## Q1. What proves METIS improves locality?\nMETIS reduced the archived balanced edge-cut ratio from 74.9532% for random to 10.4472% for the selected limited run, with 40,882 cut edges on 391,320 incidences. This is partition quality evidence, not proof of bank locality. In the P=4 access model, METIS node-only instead increased retries by 2.222% and modeled structural cycles by 0.471% versus original, so graph edge cut did not translate into this memory-locality objective.\n\n## Q2–Q3. Why P=4, and what about P=8?\nThe archived original-layout model has 7,205,045, 4,758,697, and 3,198,386 structural cycles at P=2, 4, and 8. Lane utilization is 80.037%, 60.272%, and 44.077%. Thus P=8 lowers modeled cycles but uses twice the lanes/banks of P=4 and has lower utilization. This supports P=4 only as a documented resource/utilization trade-off; it does not prove global optimality.\n\n## Q4. Proposed architecture versus base Relay-BP\nThe strongest archived software-model result is BA2: P=4 structural cycles 4,758,697 to 4,283,590 (-9.984%) and trajectory-weighted modeled mean 726,388,133 to 617,117,727 (-15.043%), with exact archived equivalence. These are software-simulated/model results, not FPGA timing.\n\n## Q5. GARI comparison\nGARI values in this package are literature-reported and not matched. The local audit found no verified public GARI software reproduction run. Direct latency/resource ranking is therefore unavailable.\n\n## Q6. How much memory is saved?\nThe M4 validation stores 32,933,564 bits (3.926 MiB) and reports 894 ideal or 925 four-bank BRAM36-equivalent capacity; these are analytical estimates. They are not measured FPGA BRAM.\n\n## Q7. Cycles/operations\nP-cycle distributions are available in `p_scaling/trajectory_results.csv`. The operation table is explicitly analytical and structural: 391,320 incidences per check/variable message direction and 4*391,320+1,728 = 1,566,? operations in the stated proxy; it is not an instruction-level profiler.\n\n## Q8–Q9. RTL and FPGA\nThe standalone M4 RTL run reports 16,506 trace matches, zero mismatches, zero assertion failures, zero dropped/duplicated requests, and 706 same-address dual reads. Full Relay-BP RTL integration is false. FPGA synthesis is blocked because Vivado and target part/constraints are unavailable.\n\n## Q10. Evidence classes\nSee `evidence_matrix.csv` and `experiment_manifest.csv`.\n\n## Explicit limitations\nThe available LER run is bounded: 512 shots at p=0.001–0.003, 272 at p=0.004, and 256 at p=0.005; p=0.005 includes 19 logical failures and 19 non-convergences. N=4, a complete 3x3 factorial, a 10,000-shot campaign, instruction-level operation distributions, COACCESS-GREEDY, matched GARI software, and FPGA synthesis remain blocked or not yet measured.\n""", encoding="utf-8")
    (OUT / "FINAL_CAMPAIGN_SUMMARY.md").write_text("""# Empirical Campaign Summary\n\n## Status\n**PARTIALLY COMPLETE.** The package contains verified archived software/analytical/RTL evidence and newly normalized CSVs/plots. It does not claim completion of every requested experiment.\n\n## Environment\nIsolated `.venv`: Python 3.13.6, NumPy 2.2.6, SciPy 1.15.3, STIM 1.15.0, PyMatching 2.3.1, Matplotlib 3.10.7, PyMetis 2025.2.2; arm64 macOS; commit `""" + COMMIT + """`. Icarus is available; Vivado is unavailable.\n\n## Completed/recovered\n- P=2/4/8 folding structural and trajectory distributions.\n- Original, METIS variants, BA1/BA2/BA3 heuristic comparison.\n- Bounded p=0.001–0.005 LER table with Wilson bounds and long-tail metadata.\n- N=1/N=2 archived first-success comparison.\n- M4 analytical memory/equivalence evidence.\n- M4 standalone RTL simulation.\n- GARI literature comparison with non-comparability labels.\n\n## Main numerical findings\n- Original P=2/4/8 modeled cycles: 7,205,045 / 4,758,697 / 3,198,386.\n- Original P=2/4/8 utilization: 80.037% / 60.272% / 44.077%.\n- BA2 at P=4: 336,291 to 142,566 retries (-57.606%); 4,758,697 to 4,283,590 structural cycles (-9.984%).\n- METIS cut: 10.4472% selected versus 74.9532% random balanced, but METIS node-only increased P=4 modeled retries/cycles.\n- Bounded LER: p=0.005 observed 19/256 = 0.07421875; p=0.001–0.004 had zero observed logical failures in the archived bounded samples, so upper bounds are reported in CSV.\n- M4 RTL: 16,506 matches, zero mismatches/assertions/dropped/duplicated requests.\n\n## Blocked/not yet measured\nN=4 and complete N×P factorial, complete 10,000-shot LER points, instruction-level operations, COACCESS-GREEDY, matched GARI software, full integrated Relay-BP RTL, and FPGA synthesis/timing/resource measurements.\n\n## Provenance\nEvery normalized table points to its source artifact in `experiment_manifest.csv`; claim-level traceability is in `evidence_matrix.csv`. Analytical BRAM and operation values are not hardware measurements.\n""", encoding="utf-8")
    report = OUT / "professor_questions.md"
    report.write_text(report.read_text(encoding="utf-8").replace("1,566,?", "1,567,008"), encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    build_p_tables()
    build_ba2_table()
    build_metis_table()
    build_ler_table()
    build_operations_table()
    build_blocked_campaign_tables()
    build_memory_and_rtl()
    build_comparison_and_gari()
    build_manifest_and_evidence()
    build_reports()
    print(f"Wrote campaign package under {OUT}")


if __name__ == "__main__":
    main()
