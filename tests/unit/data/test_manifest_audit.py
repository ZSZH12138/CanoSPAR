"""Tests for aggregate-only HCP/PPMI manifest audits."""

from __future__ import annotations

import json
from pathlib import Path

from canospar.data.audit_manifest import _write_ppmi_target_audit, audit_manifest_file, main
from canospar.data.metadata_io import canonical_json_bytes


def _ppmi_row(subject: str, visit: str, *, trimodal: bool) -> dict[str, object]:
    return {
        "contract_version": "1.1.0",
        "dataset": "ppmi",
        "source_release": "ppmi-synthetic-current",
        "subject_id": subject,
        "visit_id": visit,
        "group_id": subject,
        "family_id": None,
        "site_id": "unknown",
        "site_available": False,
        "site_source": "unavailable_in_current_ppmi_export",
        "scanner_vendor": "siemens",
        "scanner_model": "prisma",
        "field_strength": 3.0,
        "normalized_protocol": "t1 | rest | dti",
        "scanner_batch_id": "a1b2c3d4e5f6",
        "age": None,
        "sex": None,
        "diagnosis": "PD",
        "diagnosis_source": "participant_status_enrollment_cohort",
        "target": None,
        "target_name": None,
        "target_date": None,
        "imaging_date": "2026-01-02",
        "imaging_clinical_interval_days": None,
        "t1_available": True,
        "t1_downloaded": False,
        "t1_preprocessed": False,
        "t1_qc_pass": None,
        "t1_path": "",
        "fmri_available": trimodal,
        "fmri_downloaded": False,
        "fmri_preprocessed": False,
        "fmri_qc_pass": None,
        "fmri_path": "",
        "dwi_available": trimodal,
        "dwi_downloaded": False,
        "dwi_preprocessed": False,
        "dwi_qc_pass": None,
        "dwi_path": "",
        "raw_qc_status": None,
        "exclusion_reason": "none" if trimodal else "not_in_source_inventory",
        "availability_basis": "source_inventory",
        "availability_snapshot_date": "2026-07-25",
        "cohort_status": "provisional",
        "row_status": "included" if trimodal else "excluded",
        "source_manifest_hash": "a" * 64,
        "cohort_source": "not_applicable",
        "unrelated_list_version": "not_applicable",
        "kinship_control_method": "not_applicable",
    }


def _write(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_bytes(canonical_json_bytes(rows) + b"\n")


def test_ppmi_task_gate_records_selected_primary_branch_and_all_sensitivities(
    tmp_path: Path,
) -> None:
    payload = {
        "audit": {
            "status": "READY_FOR_USER_SELECTED_TASK",
            "primary_target": "candidate_A",
            "target_definition": "MDS-UPDRS Part III follow-up score minus baseline score",
            "primary_policy": "prefer_off",
            "secondary_targets": ["candidate_B"],
            "sensitivity_policies": ["unique_only", "prefer_on"],
        },
        "branches": {
            candidate: {
                policy: {"24": {"task_gate": {"recommendation": "STRESS_TEST_ONLY"}}}
                for policy in ("unique_only", "prefer_off", "prefer_on")
            }
            for candidate in ("candidate_A", "candidate_B")
        },
    }

    _write_ppmi_target_audit(payload, tmp_path)

    task_gate = json.loads((tmp_path / "ppmi_task_gate.json").read_text(encoding="utf-8"))
    assert task_gate["primary_target"] == "candidate_A"
    assert (
        task_gate["target_definition"] == "MDS-UPDRS Part III follow-up score minus baseline score"
    )
    assert task_gate["primary_policy"] == "prefer_off"
    assert task_gate["secondary_targets"] == ["candidate_B"]
    assert task_gate["sensitivity_policies"] == ["unique_only", "prefer_on"]
    assert set(task_gate["branches"]) == {"candidate_A", "candidate_B"}
    assert set(task_gate["branches"]["candidate_A"]) == {
        "unique_only",
        "prefer_off",
        "prefer_on",
    }


def test_ppmi_audit_counts_subject_visits_and_modalities_without_ids(tmp_path: Path) -> None:
    manifest = tmp_path / "ppmi.json"
    _write(
        manifest,
        [
            _ppmi_row("PPMI_SYN_0001", "BL", trimodal=True),
            _ppmi_row("PPMI_SYN_0001", "V04", trimodal=False),
            _ppmi_row("PPMI_SYN_0002", "BL", trimodal=True),
        ],
    )

    audit = audit_manifest_file(manifest, "ppmi")
    serialized = json.dumps(audit.as_record())

    assert audit.status == "PASS"
    assert audit.summary["row_count"] == 3
    assert audit.summary["distinct_subject_count"] == 2
    assert audit.summary["trimodal_subject_visit_count"] == 2
    assert audit.summary["modality_available_counts"] == {"dwi": 2, "fmri": 2, "t1": 3}
    assert "PPMI_SYN_" not in serialized


def test_audit_rejects_dataset_mismatch_and_cli_returns_nonzero(tmp_path: Path) -> None:
    manifest = tmp_path / "ppmi.json"
    _write(manifest, [_ppmi_row("PPMI_SYN_0001", "BL", trimodal=True)])
    output = tmp_path / "audit"

    assert audit_manifest_file(manifest, "hcp").status == "FAIL"
    assert (
        main(
            [
                "--manifest",
                str(manifest),
                "--dataset",
                "hcp",
                "--output-dir",
                str(output),
            ]
        )
        != 0
    )
    record = json.loads((output / "hcp_initial_audit.json").read_text(encoding="utf-8"))
    assert record["status"] == "FAIL"


def test_audit_dry_run_does_not_create_output(tmp_path: Path) -> None:
    manifest = tmp_path / "ppmi.json"
    _write(manifest, [_ppmi_row("PPMI_SYN_0001", "BL", trimodal=True)])
    output = tmp_path / "audit"

    assert (
        main(
            [
                "--manifest",
                str(manifest),
                "--dataset",
                "ppmi",
                "--output-dir",
                str(output),
                "--dry-run",
            ]
        )
        == 0
    )
    assert not output.exists()
