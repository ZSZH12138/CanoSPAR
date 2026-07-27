"""End-to-end synthetic acceptance tests for the Week 2-4 metadata pipeline."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

from canospar.data import (
    audit_manifest,
    hcp_manifest,
    metadata_discovery,
    ppmi_manifest,
    validate_manifest,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "metadata"
HCP_ROOT = FIXTURES / "hcp_synthetic"
PPMI_ROOT = FIXTURES / "ppmi_synthetic"


def _run_pipeline(output: Path) -> dict[str, bytes]:
    hcp_output = output / "hcp"
    ppmi_output = output / "ppmi"
    reports = output / "reports"
    source_inventory = output / "source_inventory"
    calls = (
        lambda: metadata_discovery.main(
            [
                "--config",
                str(HCP_ROOT / "hcp.yaml"),
                "--metadata-root",
                str(HCP_ROOT / "data"),
                "--output-dir",
                str(source_inventory / "hcp"),
            ]
        ),
        lambda: metadata_discovery.main(
            [
                "--config",
                str(PPMI_ROOT / "ppmi.yaml"),
                "--metadata-root",
                str(PPMI_ROOT / "data"),
                "--output-dir",
                str(source_inventory / "ppmi"),
            ]
        ),
        lambda: hcp_manifest.main(
            [
                "--config",
                str(HCP_ROOT / "hcp.yaml"),
                "--metadata-root",
                str(HCP_ROOT / "data"),
                "--output-dir",
                str(hcp_output),
            ]
        ),
        lambda: ppmi_manifest.main(
            [
                "--config",
                str(PPMI_ROOT / "ppmi.yaml"),
                "--metadata-root",
                str(PPMI_ROOT / "data"),
                "--output-dir",
                str(ppmi_output),
            ]
        ),
        lambda: validate_manifest.main(
            [
                "--manifest",
                str(hcp_output / "hcp_manifest.json"),
                "--output-dir",
                str(reports / "hcp"),
            ]
        ),
        lambda: validate_manifest.main(
            [
                "--manifest",
                str(ppmi_output / "ppmi_manifest.json"),
                "--output-dir",
                str(reports / "ppmi"),
            ]
        ),
        lambda: audit_manifest.main(
            [
                "--manifest",
                str(hcp_output / "hcp_manifest.json"),
                "--dataset",
                "hcp",
                "--output-dir",
                str(reports / "hcp"),
            ]
        ),
        lambda: audit_manifest.main(
            [
                "--manifest",
                str(ppmi_output / "ppmi_manifest.json"),
                "--dataset",
                "ppmi",
                "--output-dir",
                str(reports / "ppmi"),
                "--config",
                str(PPMI_ROOT / "ppmi.yaml"),
                "--metadata-root",
                str(PPMI_ROOT / "data"),
            ]
        ),
    )
    assert [call() for call in calls] == [0] * len(calls)
    files = sorted(path for path in output.rglob("*") if path.is_file())
    return {path.relative_to(output).as_posix(): path.read_bytes() for path in files}


def _copy_isolated_fixture_project(destination: Path) -> Path:
    project = destination / "project"
    for relative in (
        Path("src"),
        Path("workflow"),
        Path("configs"),
        Path("tests") / "fixtures" / "metadata",
    ):
        source = PROJECT_ROOT / relative
        shutil.copytree(source, project / relative, dirs_exist_ok=True)
    shutil.copy2(PROJECT_ROOT / "pyproject.toml", project / "pyproject.toml")
    return project


def _run_isolated_snakemake(
    project: Path,
    *targets: str,
    forceall: bool = False,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ | {
        "PYTHONPATH": str(PROJECT_ROOT / "src"),
        "CUDA_VISIBLE_DEVICES": "",
    }
    command = [
        sys.executable,
        "-m",
        "snakemake",
        "-s",
        "workflow/Snakefile",
        *targets,
        "--cores",
        "1",
    ]
    if forceall:
        command.append("--forceall")
    return subprocess.run(
        command,
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_fixture_pipeline_delete_and_rerun_is_byte_identical(
    tmp_path: Path,
    capsys: object,
) -> None:
    output = tmp_path / "week02_04"

    first = _run_pipeline(output)
    first_hashes = {
        name: hashlib.sha256(content).hexdigest()
        for name, content in first.items()
        if name.endswith("_manifest.json")
    }
    shutil.rmtree(output)
    second = _run_pipeline(output)
    second_hashes = {
        name: hashlib.sha256(content).hexdigest()
        for name, content in second.items()
        if name.endswith("_manifest.json")
    }

    assert first == second
    assert first_hashes == second_hashes
    assert len(first_hashes) == 2
    hcp_target_audit = json.loads(first["hcp/hcp_audit.json"])
    target_audit = json.loads(first["reports/ppmi/ppmi_target_candidate_audit.json"])
    task_gate = json.loads(first["reports/ppmi/ppmi_task_gate.json"])
    assert hcp_target_audit["primary_target"] == "CogFluidComp_Unadj"
    assert hcp_target_audit["secondary_targets"] == [
        "CogTotalComp_Unadj",
        "PMAT24_A_CR",
    ]
    assert hcp_target_audit["task_type"] == "regression"
    assert hcp_target_audit["primary_metric"] == "MAE"
    assert b"_SYN_" not in first["reports/ppmi/ppmi_target_candidate_audit.json"]
    assert b"_SYN_" not in first["reports/ppmi/ppmi_task_gate.json"]
    assert set(target_audit["branches"]) == {"candidate_A", "candidate_B"}
    assert all(
        set(policies) == {"prefer_off", "prefer_on", "unique_only"}
        for policies in target_audit["branches"].values()
    )
    assert target_audit["audit"]["coverage_horizons"] == [
        "baseline",
        "12",
        "24",
        "48",
    ]
    assert target_audit["audit"]["primary_target"] == "candidate_A"
    assert target_audit["audit"]["primary_policy"] == "prefer_off"
    assert task_gate["status"] == "READY_FOR_USER_SELECTED_TASK"
    assert task_gate["primary_target"] == "candidate_A"
    assert task_gate["primary_policy"] == "prefer_off"
    assert task_gate["sensitivity_policies"] == ["unique_only", "prefer_on"]
    assert set(task_gate) == {
        "status",
        "basis_horizon",
        "primary_target",
        "target_definition",
        "primary_policy",
        "secondary_targets",
        "sensitivity_policies",
        "branches",
    }
    primary_gate = task_gate["branches"]["candidate_A"]["prefer_off"]
    assert primary_gate["final_task_selected"] is True
    assert primary_gate["required_confirmations"] == []
    assert target_audit["audit"]["part_iii_duplicate_audit"]["duplicate_subject_visit_groups"] == 1
    assert task_gate["basis_horizon"] == "24"
    assert all(
        gate["basis_horizon"] == "24"
        for policies in task_gate["branches"].values()
        for gate in policies.values()
    )
    console = capsys.readouterr()  # type: ignore[attr-defined]
    assert "_SYN_" not in console.out + console.err


def test_fixture_pipeline_never_opens_a_network_socket(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    def blocked_socket(*args: object, **kwargs: object) -> socket.socket:
        del args, kwargs
        raise AssertionError("fixture pipeline attempted network access")

    monkeypatch.setattr(socket, "socket", blocked_socket)  # type: ignore[attr-defined]

    outputs = _run_pipeline(tmp_path / "offline")

    assert "hcp/hcp_manifest.json" in outputs
    assert "ppmi/ppmi_manifest.json" in outputs


def test_snakemake_fixture_target_is_cpu_only_and_private_target_is_not_default(
    tmp_path: Path,
) -> None:
    project = _copy_isolated_fixture_project(tmp_path / "snakemake_project")
    completed = _run_isolated_snakemake(
        project,
        "metadata_fixture",
        forceall=True,
    )

    assert completed.returncode == 0, completed.stderr
    output = f"{completed.stdout}\n{completed.stderr}".casefold()
    assert "metadata_fixture" in output
    assert "metadata_private" not in output
    assert "data/metadata" not in output


def test_snakemake_rebuilds_deleted_manifest_evidence_sidecars(tmp_path: Path) -> None:
    project = _copy_isolated_fixture_project(tmp_path / "sidecar_project")
    initial = _run_isolated_snakemake(project, "metadata_fixture", forceall=True)
    assert initial.returncode == 0, initial.stderr
    sidecars = (
        project / "artifacts/manifests/week02_04/fixture/hcp/hcp_provenance.json",
        project / "artifacts/manifests/week02_04/fixture/hcp/hcp_audit.json",
        project / "artifacts/manifests/week02_04/fixture/ppmi/ppmi_provenance.json",
        project / "artifacts/manifests/week02_04/fixture/ppmi/ppmi_sequence_audit.json",
    )
    for sidecar in sidecars:
        sidecar.unlink()

    completed = _run_isolated_snakemake(
        project,
        "metadata_fixture",
    )

    assert completed.returncode == 0, completed.stderr
    assert all(sidecar.exists() for sidecar in sidecars)
    output = f"{completed.stdout}\n{completed.stderr}"
    for rule_name in (
        "fixture_hcp_manifest",
        "fixture_ppmi_manifest",
        "fixture_hcp_validation",
        "fixture_ppmi_validation",
        "fixture_hcp_audit",
        "fixture_ppmi_audit",
    ):
        assert rule_name in output


def test_real_metadata_is_ignored_and_untracked() -> None:
    ignored = subprocess.run(
        ["git", "check-ignore", "--quiet", "data/metadata/synthetic_probe.csv"],
        cwd=PROJECT_ROOT,
        check=False,
    )
    tracked = subprocess.run(
        ["git", "ls-files", "--", "data/metadata"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert ignored.returncode == 0
    assert tracked.returncode == 0
    assert tracked.stdout.strip() == ""
