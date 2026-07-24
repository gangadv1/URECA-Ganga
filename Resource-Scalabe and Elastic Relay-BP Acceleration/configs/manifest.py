"""Write simple manifests beside generated outputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parent


@dataclass(frozen=True)
class ManifestConfig:
    """The main settings for one generated artifact or run."""

    graph: dict[str, Any] = field(default_factory=dict)
    circuit: dict[str, Any] = field(default_factory=dict)
    decoder: dict[str, Any] = field(default_factory=dict)
    arithmetic: dict[str, Any] = field(default_factory=dict)
    architecture: dict[str, Any] = field(default_factory=dict)
    hardware: dict[str, Any] = field(default_factory=dict)
    experiment: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def sha256_file(path: Path) -> str:
    """Hash one file."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def current_git_commit(repo_root: Path = REPO_ROOT) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip()


def git_status_for(path: Path, repo_root: Path = REPO_ROOT) -> str:
    try:
        result = subprocess.run(
            ["git", "status", "--short", str(path)],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return result.stdout.strip()


def hash_sot_docs(sot_dir: Path | None = None) -> dict[str, str]:
    """Hash proposal docs that define the current target."""
    directory = sot_dir or (REPO_ROOT / "master-proposal")
    if not directory.exists():
        return {}
    hashes: dict[str, str] = {}
    for path in sorted(directory.glob("*.md")):
        hashes[str(path.relative_to(REPO_ROOT))] = sha256_file(path)
    return hashes


def write_manifest(
    config: ManifestConfig,
    out_dir: Path,
    artifact_paths: Iterable[Path] = (),
    sot_dir: Path | None = None,
) -> Path:
    """Write `manifest.json` in `out_dir` and return its path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    artifact_hashes = {
        str(path): sha256_file(path)
        for path in sorted(Path(p) for p in artifact_paths)
        if Path(path).exists() and Path(path).is_file()
    }
    data = asdict(config)
    data["provenance"] = {
        "git_commit": current_git_commit(),
        "artifact_hashes": artifact_hashes,
        "sot_doc_hashes": hash_sot_docs(sot_dir),
        "sot_git_status": git_status_for(REPO_ROOT / "master-proposal"),
    }
    output_path = out_dir / "manifest.json"
    output_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Write a small environment manifest")
    parser.add_argument("--out-dir", type=Path, default=PROJECT_ROOT / "results" / "env-check")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = ManifestConfig(
        hardware={
            "iverilog": shutil_which("iverilog"),
            "verilator": shutil_which("verilator"),
        },
        experiment={"purpose": "environment check"},
        notes=["This manifest is a quick local environment record."],
    )
    path = write_manifest(config, args.out_dir)
    print(path)


def shutil_which(command: str) -> str | None:
    from shutil import which

    return which(command)


if __name__ == "__main__":
    main()

