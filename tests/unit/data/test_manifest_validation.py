"""Behavioral tests for the unified Week 2-4 manifest validator."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

from canospar.data.metadata_io import canonical_json_bytes
from canospar.data.validate_manifest import main, validate_manifest_file


def _row(*, dataset: str = "hcp", subject: str = "HCP_SYN_0001") -> dict[str, object]:
    hcp = dataset == "hcp"
    return {
        "contract_version": "1.1.0",
        "dataset": dataset,
        "source_release": "2025" if hcp else "ppmi-synthetic-current",
        "subject_id": subject,
        "visit_id": "baseline" if hcp else "BL",
        "group_id": subject,
        "family_id": None,
        "site_id": "unknown",
        "site_available": False,
        "site_source": (
            "not_available_open_access" if hcp else "unavailable_in_current_ppmi_export"
        ),
        "scanner_vendor": None if hcp else "siemens",
        "scanner_model": None if hcp else "prisma",
        "field_strength": None if hcp else 3.0,
        "normalized_protocol": None if hcp else "t1 | rest | dti",
        "scanner_batch_id": None if hcp else "a1b2c3d4e5f6",
        "age": 22.0 if hcp else None,
        "sex": None,
        "diagnosis": None if hcp else "PD",
        "diagnosis_source": None if hcp else "participant_status_enrollment_cohort",
        "target": None,
        "target_name": None,
        "target_date": None,
        "imaging_date": None if hcp else "2026-01-02",
        "imaging_clinical_interval_days": None,
        "t1_available": True,
        "t1_downloaded": False,
        "t1_preprocessed": False,
        "t1_qc_pass": None,
        "t1_path": "",
        "fmri_available": True,
        "fmri_downloaded": False,
        "fmri_preprocessed": False,
        "fmri_qc_pass": None,
        "fmri_path": "",
        "dwi_available": True,
        "dwi_downloaded": False,
        "dwi_preprocessed": False,
        "dwi_qc_pass": None,
        "dwi_path": "",
        "raw_qc_status": None,
        "exclusion_reason": "none",
        "availability_basis": ("acquisition_completion_fields" if hcp else "source_inventory"),
        "availability_snapshot_date": "2026-07-25",
        "cohort_status": "provisional",
        "row_status": "provisional" if hcp else "included",
        "source_manifest_hash": "a" * 64,
        "cohort_source": "hcp_official_unrelated" if hcp else "not_applicable",
        "unrelated_list_version": "S900" if hcp else "not_applicable",
        "kinship_control_method": ("official_unrelated_cohort" if hcp else "not_applicable"),
    }


def _write_manifest(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_bytes(canonical_json_bytes(rows) + b"\n")


def test_valid_manifest_reports_exact_contract_and_file_hash(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    _write_manifest(manifest, [_row()])

    result = validate_manifest_file(manifest)
    record = result.as_record()

    assert record["status"] == "PASS"
    assert record["manifest_sha256"] == hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert record["checks"]
    assert all(set(check) == {"name", "status", "count", "message"} for check in record["checks"])
    assert all(check["status"] == "PASS" for check in record["checks"])


def test_duplicate_key_and_schema_failure_are_aggregate_only(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    malformed = _row() | {"t1_downloaded": True}
    _write_manifest(manifest, [_row(), malformed])

    result = validate_manifest_file(manifest)
    serialized = json.dumps(result.as_record())

    assert result.status == "FAIL"
    assert any(
        check.name == "unique_subject_visit" and check.status == "FAIL" for check in result.checks
    )
    assert any(check.name == "schema" and check.status == "FAIL" for check in result.checks)
    assert "HCP_SYN_0001" not in serialized


def test_noncanonical_order_fails_and_changed_input_changes_hash(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    rows = [_row(subject="HCP_SYN_0002"), _row(subject="HCP_SYN_0001")]
    _write_manifest(first, rows)
    _write_manifest(second, list(reversed(rows)))

    first_result = validate_manifest_file(first)
    second_result = validate_manifest_file(second)

    assert first_result.status == "FAIL"
    assert any(
        check.name == "stable_sort_and_serialization" and check.status == "FAIL"
        for check in first_result.checks
    )
    assert second_result.status == "PASS"
    assert first_result.manifest_sha256 != second_result.manifest_sha256


def test_mixed_source_manifest_hashes_are_rejected(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    _write_manifest(
        manifest,
        [
            _row(subject="HCP_SYN_0001"),
            _row(subject="HCP_SYN_0002") | {"source_manifest_hash": "b" * 64},
        ],
    )

    result = validate_manifest_file(manifest)

    assert result.status == "FAIL"
    assert any(
        check.name == "source_manifest_hashes" and check.status == "FAIL" for check in result.checks
    )


def test_hcp_subject_must_be_unique_while_ppmi_retains_multiple_visits(
    tmp_path: Path,
) -> None:
    hcp_manifest = tmp_path / "hcp_generic.json"
    hcp_rows = [
        _row(),
        _row() | {"visit_id": "followup"},
    ]
    _write_manifest(hcp_manifest, hcp_rows)
    ppmi_manifest = tmp_path / "ppmi_generic.json"
    ppmi_rows = [
        _row(dataset="ppmi", subject="PPMI_SYN_0001"),
        _row(dataset="ppmi", subject="PPMI_SYN_0001") | {"visit_id": "V04"},
    ]
    _write_manifest(ppmi_manifest, ppmi_rows)

    hcp_result = validate_manifest_file(hcp_manifest)
    ppmi_result = validate_manifest_file(ppmi_manifest)

    assert hcp_result.status == "FAIL"
    assert any(
        check.name == "dataset_contract" and check.status == "FAIL" for check in hcp_result.checks
    )
    assert ppmi_result.status == "PASS"


def test_dataset_specific_invariants_and_path_privacy_are_enforced(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    personal_path = "C:" + "\\Us" + "ers\\Researcher\\private\\release"
    unsafe = _row(dataset="ppmi", subject="PPMI_SYN_0001") | {
        "source_release": personal_path,
        "diagnosis_source": "participant_status_enrollment_cohort",
    }
    _write_manifest(manifest, [unsafe])

    result = validate_manifest_file(manifest)

    assert result.status == "FAIL"
    assert any(check.name == "path_privacy" and check.status == "FAIL" for check in result.checks)
    assert "Researcher" not in json.dumps(result.as_record())


def test_embedded_windows_unc_path_fails_manifest_privacy(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    network_path = (
        "release=" + "\\\\" + "private-server\\restricted-share\\Researcher\\metadata-export"
    )
    _write_manifest(
        manifest,
        [
            _row(dataset="ppmi", subject="PPMI_SYN_0001")
            | {
                "source_release": network_path,
                "diagnosis_source": "participant_status_enrollment_cohort",
            }
        ],
    )

    result = validate_manifest_file(manifest)

    assert result.status == "FAIL"
    assert any(check.name == "path_privacy" and check.status == "FAIL" for check in result.checks)
    assert "private-server" not in json.dumps(result.as_record())


def test_cli_failure_is_nonzero_and_dry_run_writes_nothing(
    tmp_path: Path,
    capsys: object,
) -> None:
    manifest = tmp_path / "manifest.json"
    _write_manifest(manifest, [_row() | {"exclusion_reason": "free text"}])
    output = tmp_path / "output"

    exit_code = main(
        [
            "--manifest",
            str(manifest),
            "--output-dir",
            str(output),
            "--dry-run",
        ]
    )

    assert exit_code != 0
    assert not output.exists()
    console = capsys.readouterr()  # type: ignore[attr-defined]
    assert "HCP_SYN_" not in console.out + console.err


def test_standard_hcp_manifest_rejects_inconsistent_adjacent_evidence(tmp_path: Path) -> None:
    manifest = tmp_path / "hcp_manifest.json"
    _write_manifest(manifest, [_row()])
    (tmp_path / "hcp_provenance.json").write_bytes(
        canonical_json_bytes(
            {
                "cohort_status": "provisional",
                "availability_basis": "acquisition_completion_fields",
                "access_tier": "Open Access",
                "restricted_access": "not_approved",
                "unrelated_list_version": "S900",
                "processed_package_inventory": "formal_confirmed",
                "inputs": {"unrelated_list": {"sha256": "b" * 64}},
            }
        )
        + b"\n"
    )
    (tmp_path / "hcp_audit.json").write_bytes(
        canonical_json_bytes(
            {
                "targets": {
                    "CogFluidComp_Unadj": {},
                    "CogTotalComp_Unadj": {},
                    "PMAT24_A_CR": {},
                }
            }
        )
        + b"\n"
    )

    result = validate_manifest_file(manifest)

    assert result.status == "FAIL"
    assert any(
        check.name == "dataset_evidence" and check.status == "FAIL" for check in result.checks
    )


def test_standard_ppmi_manifest_rejects_concat_and_missing_inventory_evidence(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "ppmi_manifest.json"
    _write_manifest(manifest, [_row(dataset="ppmi", subject="PPMI_SYN_0001")])
    (tmp_path / "ppmi_provenance.json").write_bytes(
        canonical_json_bytes(
            {
                "availability_basis": "source_inventory",
                "inputs": {
                    name: {"sha256": "b" * 64}
                    for name in (
                        "mri_completion",
                        "archived_mri",
                        "t1_inventory",
                        "rsfmri_inventory",
                    )
                },
            }
        )
        + b"\n"
    )
    (tmp_path / "ppmi_sequence_audit.json").write_bytes(
        canonical_json_bytes(
            {
                "archive_join": {"method": "concat"},
                "visit_mapping": {"mapped": 1, "unknown": 0},
                "sequence_classification": {"modalities": {}, "reasons": {}},
                "site_status": "unavailable_in_current_ppmi_export",
            }
        )
        + b"\n"
    )

    result = validate_manifest_file(manifest)

    assert result.status == "FAIL"
    assert any(
        check.name == "dataset_evidence" and check.status == "FAIL" for check in result.checks
    )


def test_private_metadata_in_git_history_fails_even_after_deletion(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    repository = tmp_path / "repository"
    private_file = repository / "data" / "metadata" / "synthetic_probe.csv"
    private_file.parent.mkdir(parents=True)
    private_file.write_text("synthetic,value\n", encoding="utf-8")
    commands = (
        ("git", "init", "-q"),
        ("git", "config", "user.email", "synthetic@example.invalid"),
        ("git", "config", "user.name", "Synthetic Test"),
        ("git", "add", "data/metadata/synthetic_probe.csv"),
        ("git", "commit", "--no-verify", "-q", "-m", "synthetic history fixture"),
        ("git", "rm", "-q", "data/metadata/synthetic_probe.csv"),
        ("git", "commit", "--no-verify", "-q", "-m", "remove synthetic history fixture"),
    )
    isolated_git_environment = {
        name: value for name, value in os.environ.items() if not name.startswith("GIT_")
    }
    for command in commands:
        subprocess.run(
            command,
            cwd=repository,
            check=True,
            env=isolated_git_environment,
        )
    manifest = repository / "manifest.json"
    _write_manifest(manifest, [_row()])
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "contaminating-git-dir"))  # type: ignore[attr-defined]

    result = validate_manifest_file(manifest, repository_root=repository)

    assert result.status == "FAIL"
    assert any(
        check.name == "private_metadata_git_tracking" and check.status == "FAIL"
        for check in result.checks
    )
