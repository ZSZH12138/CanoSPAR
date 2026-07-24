"""Subprocess evidence for the CPU-only smoke CLI."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from omegaconf import OmegaConf

from canospar.utils.hashing import hash_yaml_config

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _run_smoke(output_dir: Path, *overrides: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "canospar.utils.smoke_test",
            f"paths.output_dir={output_dir.as_posix()}",
            *overrides,
        ],
        cwd=_PROJECT_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )


def test_smoke_cli_writes_the_three_fresh_artifacts_with_a_shared_config_hash() -> None:
    output_dir = Path("artifacts") / f"smoke-integration-{uuid4().hex}"
    destination = _PROJECT_ROOT / output_dir
    try:
        result = _run_smoke(output_dir)

        assert result.returncode == 0, result.stderr
        config_path = destination / "resolved_config.yaml"
        provenance_path = destination / "provenance.json"
        report_path = destination / "smoke_report.json"
        assert {path.name for path in destination.iterdir()} == {
            config_path.name,
            provenance_path.name,
            report_path.name,
        }
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["status"] == "success"
        assert report["seed"] == 7
        assert report["device"] == "cpu"
        assert report["num_graphs"] == 3
        assert report["total_nodes"] == 12
        assert report["total_edges"] == 18
        assert report["feature_dim"] == 3
        assert report["modalities"] == ["smri", "dmri", "fmri"]
        assert report["relations"] == [
            "morphological_similarity",
            "structural_connectivity",
            "positive_functional_connectivity",
        ]
        assert report["batch_shape"] == [12, 3]
        assert (
            hash_yaml_config(OmegaConf.load(config_path))
            == provenance["config_hash"]
            == report["config_hash"]
        )
        assert provenance["cuda_available"] is False
        assert json.loads(result.stdout) == {
            "config_hash": report["config_hash"],
            "device": "cpu",
            "num_graphs": 3,
            "status": "success",
        }
    finally:
        shutil.rmtree(destination, ignore_errors=True)


def test_smoke_cli_repeats_the_structure_and_hash_for_the_same_configuration() -> None:
    output_dir = Path("artifacts") / f"smoke-repeat-{uuid4().hex}"
    destination = _PROJECT_ROOT / output_dir
    try:
        first = _run_smoke(output_dir, "random_seed=19")
        first_report = json.loads((destination / "smoke_report.json").read_text(encoding="utf-8"))
        second = _run_smoke(output_dir, "random_seed=19")
        second_report = json.loads((destination / "smoke_report.json").read_text(encoding="utf-8"))

        assert first.returncode == second.returncode == 0
        assert first_report["config_hash"] == second_report["config_hash"]
        assert first_report["structure"] == second_report["structure"]
    finally:
        shutil.rmtree(destination, ignore_errors=True)


def test_smoke_cli_rejects_cuda_without_creating_success_artifacts() -> None:
    output_dir = Path("artifacts") / f"smoke-cuda-{uuid4().hex}"
    destination = _PROJECT_ROOT / output_dir

    result = _run_smoke(output_dir, "device=cuda")

    assert result.returncode != 0
    assert not destination.exists()
