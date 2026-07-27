"""Synthetic acceptance tests for the PPMI subject-visit imaging manifest."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

import canospar.data.ppmi_manifest as ppmi_manifest_module
from canospar.data.ppmi_manifest import PPMIManifestError, build_ppmi_manifest, main


def _csv(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def _config(path: Path) -> Path:
    path.write_text(
        "contract_version: '1.1.0'\n"
        "cohort: ppmi\n"
        "column_map: columns.yaml\n"
        "aliases_file: aliases.yaml\n"
        "visit_map: visits.yaml\n"
        "availability_snapshot_date: '2026-07-25'\n"
        "source_release: ppmi-current\n"
        "logical_inputs:\n"
        "  data_dictionary: {patterns: ['dictionary.csv']}\n"
        "  mri_completion:\n"
        "    patterns: ['completion.csv']\n"
        "    column_signature: [subject_id, visit, sequence_description]\n"
        "  participant_status: {patterns: ['participant.csv']}\n"
        "  archived_mri: {patterns: ['archived.csv'], required: false}\n",
        encoding="utf-8",
    )
    path.with_name("columns.yaml").write_text(
        "subject_id: PATNO\nvisit: EVENT_ID\nrecord_id: REC_ID\nsequence_description: SCAN_DESC\n"
        "scan_date: INFODT\nparticipant_status: ENROLL_STATUS\ncohort: COHORT\n"
        "cohort_definition: COHORT_DEFINITION\nprotocol: Imaging Protocol\n"
        "manufacturer: Manufacturer\nscanner_model: Scanner Model\n",
        encoding="utf-8",
    )
    path.with_name("aliases.yaml").write_text(
        "smri: [t1, mprage, spgr]\nfmri: [rest, rs-fmri, bold]\n"
        "dwi: [dti, dwi, diffusion]\nexclude: [localizer, scout, reverse phase, field map]\n",
        encoding="utf-8",
    )
    path.with_name("visits.yaml").write_text("Baseline: BL\nMonth 12: V04\n", encoding="utf-8")
    return path


def _metadata(root: Path) -> None:
    _csv(root / "dictionary.csv", ["field"], [["synthetic"]])
    headers = [
        "REC_ID",
        "PATNO",
        "EVENT_ID",
        "INFODT",
        "SCAN_DESC",
        "Imaging Protocol",
        "Manufacturer",
        "Scanner Model",
        "ENROLL_STATUS",
    ]
    _csv(
        root / "completion.csv",
        headers,
        [
            [
                "1",
                "PPMI_SYN_0001",
                "Baseline",
                "2026-01-01",
                "T1 MPRAGE",
                "SIEMENS Prisma 3T T1",
                "SIEMENS",
                "Prisma",
                "PD",
            ],
            [
                "2",
                "PPMI_SYN_0001",
                "Baseline",
                "2026-01-01",
                "rest BOLD",
                "SIEMENS Prisma 3T rest BOLD",
                "SIEMENS",
                "Prisma",
                "PD",
            ],
            [
                "3",
                "PPMI_SYN_0001",
                "Baseline",
                "2026-01-01",
                "DTI diffusion",
                "SIEMENS Prisma 3T DTI",
                "SIEMENS",
                "Prisma",
                "PD",
            ],
            [
                "4",
                "PPMI_SYN_0001",
                "Month 12",
                "2027-01-01",
                "T1 MPRAGE",
                "SIEMENS Prisma 3T T1",
                "SIEMENS",
                "Prisma",
                "PD",
            ],
            [
                "5",
                "PPMI_SYN_0002",
                "Baseline",
                "2026-01-01",
                "T1 MPRAGE",
                "GE 3T T1",
                "GE",
                "Discovery",
                "HC",
            ],
            [
                "6",
                "PPMI_SYN_0002",
                "Month 12",
                "2027-01-01",
                "rest BOLD",
                "GE 3T rest",
                "GE",
                "Discovery",
                "HC",
            ],
            [
                "7",
                "PPMI_SYN_0003",
                "Unknown visit",
                "2026-01-01",
                "T1 MPRAGE",
                "GE 3T T1",
                "GE",
                "Discovery",
                "HC",
            ],
        ],
    )
    _csv(root / "archived.csv", ["REC_ID", "ENROLL_STATUS", "SCAN_DESC"], [["1", "ARCHIVE", "DTI"]])
    _csv(
        root / "participant.csv",
        ["PATNO", "COHORT", "COHORT_DEFINITION", "ENROLL_STATUS"],
        [
            ["PPMI_SYN_0001", "fallback", "preferred", "active"],
            ["PPMI_SYN_0002", "fallback_two", "", "active"],
        ],
    )


def _inventory_config(path: Path) -> Path:
    path.write_text(
        "contract_version: '1.1.0'\n"
        "cohort: ppmi\n"
        "column_map: inventory_columns.yaml\n"
        "aliases_file: aliases.yaml\n"
        "visit_map: visits.yaml\n"
        "availability_snapshot_date: '2026-07-25'\n"
        "logical_inputs:\n"
        "  data_dictionary: {patterns: ['dictionary.csv']}\n"
        "  mri_completion:\n"
        "    patterns: ['completion.csv']\n"
        "    column_signature: [subject_id, visit, record_id]\n"
        "  t1_inventory: {patterns: ['t1.csv']}\n"
        "  rsfmri_inventory: {patterns: ['fmri.csv']}\n"
        "  dti_inventory: {patterns: ['dwi.csv']}\n",
        encoding="utf-8",
    )
    path.with_name("inventory_columns.yaml").write_text(
        "subject_id: PATNO\nvisit: EVENT_ID\nrecord_id: REC_ID\n"
        "form_date: INFODT\n"
        "inventory_subject_id: Subject ID\ninventory_visit: Visit\n"
        "inventory_description: Description\ninventory_study_date: Study Date\n"
        "inventory_protocol: Imaging Protocol\n",
        encoding="utf-8",
    )
    path.with_name("aliases.yaml").write_text(
        "smri: [t1, mprage]\nfmri: [rest, bold]\ndwi: [dti, diffusion]\n"
        "exclude: [localizer, reverse phase, nm-mt]\n",
        encoding="utf-8",
    )
    path.with_name("visits.yaml").write_text("Baseline: BL\n", encoding="utf-8")
    return path


def test_validates_partial_current_dates_for_audit_only(tmp_path: Path) -> None:
    root = tmp_path / "metadata"
    _csv(root / "dictionary.csv", ["field"], [["synthetic"]])
    _csv(
        root / "completion.csv",
        ["REC_ID", "PATNO", "EVENT_ID", "INFODT"],
        [["1", "PPMI_SYN_0099", "Baseline", "01/2026"]],
    )
    inventory_headers = ["Subject ID", "Visit", "Study Date", "Description", "Imaging Protocol"]
    _csv(
        root / "t1.csv",
        inventory_headers,
        [["PPMI_SYN_0099", "Baseline", "01/10/2026", "T1 MPRAGE", "Siemens Prisma 3T"]],
    )
    for name in ("fmri.csv", "dwi.csv"):
        _csv(root / name, inventory_headers, [])

    result = build_ppmi_manifest(_inventory_config(tmp_path / "inventory.yaml"), root)

    assert result.manifest[0]["visit_id"] == "BL"
    assert result.manifest[0]["imaging_date"] == "2026-01-10"
    assert result.manifest[0]["row_status"] == "excluded"


def test_uses_inventory_modalities_only_for_matching_current_subject_visit(tmp_path: Path) -> None:
    root = tmp_path / "metadata"
    _csv(root / "dictionary.csv", ["field"], [["synthetic"]])
    _csv(
        root / "completion.csv",
        ["REC_ID", "PATNO", "EVENT_ID"],
        [["1", "PPMI_SYN_0100", "Baseline"]],
    )
    inventory_headers = ["Subject ID", "Visit", "Study Date", "Description", "Imaging Protocol"]
    _csv(
        root / "t1.csv",
        inventory_headers,
        [["PPMI_SYN_0100", "Baseline", "2026-01-01", "T1 MPRAGE", "Siemens Prisma 3T"]],
    )
    _csv(
        root / "fmri.csv",
        inventory_headers,
        [["PPMI_SYN_0100", "Baseline", "2026-01-01", "rest BOLD", "Siemens Prisma 3T"]],
    )
    _csv(
        root / "dwi.csv",
        inventory_headers,
        [
            ["PPMI_SYN_0100", "Baseline", "2026-01-01", "DTI diffusion", "Siemens Prisma 3T"],
            ["PPMI_SYN_0101", "Baseline", "2026-01-01", "DTI diffusion", "Siemens Prisma 3T"],
        ],
    )

    result = build_ppmi_manifest(_inventory_config(tmp_path / "inventory.yaml"), root)

    assert len(result.manifest) == 1
    assert result.manifest[0]["row_status"] == "included"
    assert result.manifest[0]["imaging_date"] == "2026-01-01"
    assert result.audit["imaging_inventory_records"] == 4
    assert result.audit["orphan_inventory_records"] == 1


def test_resolves_inventory_visits_only_when_code_list_and_subject_event_are_unique(
    tmp_path: Path,
) -> None:
    root = tmp_path / "metadata"
    _csv(root / "dictionary.csv", ["field"], [["synthetic"]])
    _csv(
        root / "code_list.csv",
        ["ITM_NAME", "CODE", "DECODE"],
        [
            ["EVENT_ID", "BL", "Baseline"],
            ["EVENT_ID", "V01", "Month 12"],
            ["EVENT_ID", "V04", "Month12"],
        ],
    )
    _csv(
        root / "completion.csv",
        ["REC_ID", "PATNO", "EVENT_ID", "INFODT"],
        [
            ["1", "PPMI_SYN_0101", "V01", "2026-01-10"],
            ["2", "PPMI_SYN_0102", "V04", "2026-01-12"],
            ["3", "PPMI_SYN_0103", "V01", "2026-01-01"],
            ["4", "PPMI_SYN_0103", "V04", "2026-02-01"],
            ["5", "PPMI_SYN_0104", "V01", "2026-01-20"],
            ["6", "PPMI_SYN_0104", "V04", "2026-01-20"],
            ["7", "PPMI_SYN_0105", "BL", "2026-01-01"],
        ],
    )
    inventory_headers = ["Subject ID", "Visit", "Study Date", "Description", "Imaging Protocol"]
    _csv(
        root / "t1.csv",
        inventory_headers,
        [
            ["PPMI_SYN_0101", "Month 12", "2026-01-10", "T1 MPRAGE", "Siemens Prisma 3T"],
            ["PPMI_SYN_0102", "Month12", "2026-01-12", "T1 MPRAGE", "Siemens Prisma 3T"],
            ["PPMI_SYN_0103", "Month 12", "2026-02-01", "T1 MPRAGE", "Siemens Prisma 3T"],
            ["PPMI_SYN_0104", "Month 12", "2026-01-20", "T1 MPRAGE", "Siemens Prisma 3T"],
            ["PPMI_SYN_0105", "Not in code list", "2026-01-01", "T1 MPRAGE", "Siemens Prisma 3T"],
        ],
    )
    _csv(
        root / "fmri.csv",
        inventory_headers,
        [["PPMI_SYN_0101", "Month 12", "2026-01-10", "rest BOLD", "Siemens Prisma 3T"]],
    )
    _csv(
        root / "dwi.csv",
        inventory_headers,
        [["PPMI_SYN_0101", "Month 12", "2026-01-10", "DTI diffusion", "Siemens Prisma 3T"]],
    )
    config = _inventory_config(tmp_path / "inventory.yaml")
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "  data_dictionary: {patterns: ['dictionary.csv']}\n",
            "  data_dictionary: {patterns: ['dictionary.csv']}\n"
            "  code_list: {patterns: ['code_list.csv']}\n",
        ),
        encoding="utf-8",
    )
    config.with_name("visits.yaml").write_text(
        "visit_policy: code_list_subject_event\ndate_validation: audit_only\naliases: {}\n",
        encoding="utf-8",
    )

    result = build_ppmi_manifest(config, root)

    assert [
        (row["subject_id"], row["visit_id"]) for row in result.manifest if row["t1_available"]
    ] == [
        ("PPMI_SYN_0101", "V01"),
        ("PPMI_SYN_0102", "V04"),
    ]
    assert result.manifest[0]["subject_id"] == "PPMI_SYN_0101"
    assert result.manifest[0]["row_status"] == "included"
    assert result.audit["trimodal_subject_visit_count"] == 1
    assert result.audit["inventory_visit_resolution"] == {
        "code_list_candidates": 6,
        "subject_event_matched": 4,
        "date_validated": 7,
        "ambiguous": 2,
        "unmapped": 1,
    }


def test_rejects_companion_configuration_path_traversal(tmp_path: Path) -> None:
    root = tmp_path / "metadata"
    _metadata(root)
    config_path = tmp_path / "inside" / "ppmi.yaml"
    config_path.parent.mkdir()
    config = _config(config_path)
    outside = tmp_path / "outside_columns.yaml"
    outside.write_text(
        (config.parent / "columns.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "column_map: columns.yaml", "column_map: ../outside_columns.yaml"
        ),
        encoding="utf-8",
    )

    with pytest.raises(PPMIManifestError, match="invalid column_map"):
        build_ppmi_manifest(config, root)


def test_rejects_visit_map_configuration_path_traversal(tmp_path: Path) -> None:
    root = tmp_path / "metadata"
    _metadata(root)
    config_path = tmp_path / "inside" / "ppmi.yaml"
    config_path.parent.mkdir()
    config = _config(config_path)
    outside = tmp_path / "outside_visits.yaml"
    outside.write_text("Baseline: BL\n", encoding="utf-8")
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "visit_map: visits.yaml", "visit_map: ../outside_visits.yaml"
        ),
        encoding="utf-8",
    )

    with pytest.raises(PPMIManifestError, match="invalid visit_map"):
        build_ppmi_manifest(config, root)


def test_preserves_string_ids_multivisits_and_intersects_only_same_visit(tmp_path: Path) -> None:
    root = tmp_path / "metadata"
    _metadata(root)
    result = build_ppmi_manifest(_config(tmp_path / "ppmi.yaml"), root)

    assert [(row["subject_id"], row["visit_id"]) for row in result.manifest] == [
        ("PPMI_SYN_0001", "BL"),
        ("PPMI_SYN_0001", "V04"),
        ("PPMI_SYN_0002", "BL"),
        ("PPMI_SYN_0002", "V04"),
        ("PPMI_SYN_0003", "unknown"),
    ]
    assert result.manifest[0]["t1_available"] is True
    assert result.manifest[0]["fmri_available"] is True
    assert result.manifest[0]["dwi_available"] is True
    assert result.manifest[0]["row_status"] == "included"
    assert result.manifest[0]["scanner_model"] == "prisma"
    assert result.manifest[0]["diagnosis"] == "preferred"
    assert result.manifest[0]["diagnosis_source"] == "participant_status_enrollment_cohort"
    assert result.manifest[2]["diagnosis"] == "fallback_two"
    assert result.audit["participant_status"] == {
        "matched_subject_visits": 4,
        "missing_subject_visits": 1,
    }
    assert result.audit["enrollment_cohort_distribution"] == {
        "fallback_two": 2,
        "preferred": 2,
    }
    assert result.audit["enrollment_status_distribution"] == {"PD": 4, "HC": 3}
    assert result.manifest[1]["row_status"] == "excluded"
    assert result.manifest[3]["row_status"] == "excluded"
    assert result.audit["trimodal_subject_visit_count"] == 1


def test_current_table_left_joins_archive_without_concatenating_and_audits_conflicts(
    tmp_path: Path,
) -> None:
    root = tmp_path / "metadata"
    _metadata(root)
    result = build_ppmi_manifest(_config(tmp_path / "ppmi.yaml"), root)

    assert len(result.manifest) == 5
    assert result.audit["archive_join"]["enriched_records"] == 0
    assert result.audit["archive_join"]["conflicting_fields"] == {
        "participant_status": 1,
        "sequence_description": 1,
    }


def test_archive_duplicate_records_are_audited_and_never_used_to_enrich(tmp_path: Path) -> None:
    root = tmp_path / "metadata"
    _metadata(root)
    _csv(
        root / "archived.csv",
        ["REC_ID", "ENROLL_STATUS", "SCAN_DESC"],
        [["1", "ARCHIVE", "DTI"], ["1", "ARCHIVE", "DTI"]],
    )

    result = build_ppmi_manifest(_config(tmp_path / "ppmi.yaml"), root)

    assert result.audit["archive_join"]["duplicate_groups"] == 1
    assert result.audit["archive_join"]["duplicate_rows"] == 2
    assert result.audit["archive_join"]["enriched_records"] == 0


def test_unknown_visit_and_site_are_explicit_and_manufacturer_is_not_site(tmp_path: Path) -> None:
    root = tmp_path / "metadata"
    _metadata(root)
    result = build_ppmi_manifest(_config(tmp_path / "ppmi.yaml"), root)
    unknown = result.manifest[-1]

    assert unknown["visit_id"] == "unknown"
    assert unknown["exclusion_reason"] == "missing_visit_mapping"
    assert unknown["site_id"] == "unknown"
    assert unknown["site_available"] is False
    assert unknown["site_source"] == "unavailable_in_current_ppmi_export"
    assert unknown["scanner_vendor"] == "ge"
    assert unknown["cohort_source"] == "not_applicable"
    assert unknown["diagnosis"] is None


def test_cli_is_deterministic_and_dry_run_writes_nothing_or_subject_ids(
    tmp_path: Path, capsys
) -> None:  # type: ignore[no-untyped-def]
    root = tmp_path / "metadata"
    _metadata(root)
    config = _config(tmp_path / "ppmi.yaml")
    first = tmp_path / "one"
    second = tmp_path / "two"

    assert (
        main(["--config", str(config), "--metadata-root", str(root), "--output-dir", str(first)])
        == 0
    )
    assert (
        main(["--config", str(config), "--metadata-root", str(root), "--output-dir", str(second)])
        == 0
    )
    assert (
        main(
            [
                "--config",
                str(config),
                "--metadata-root",
                str(root),
                "--output-dir",
                str(tmp_path / "dry"),
                "--dry-run",
            ]
        )
        == 0
    )
    assert not (tmp_path / "dry").exists()
    assert "PPMI_SYN_" not in capsys.readouterr().out
    for name in (
        "ppmi_manifest.json",
        "ppmi_exclusions.json",
        "ppmi_sequence_audit.json",
        "ppmi_provenance.json",
    ):
        assert (first / name).read_bytes() == (second / name).read_bytes()


def test_cli_normalizes_output_write_error_without_disclosing_absolute_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "metadata"
    _metadata(root)
    raw_path = tmp_path / "private-ppmi-output-sentinel.json"

    def raise_raw_io_error(*_: object) -> str:
        raise OSError(5, "write failed", str(raw_path))

    monkeypatch.setattr(ppmi_manifest_module, "_write_json", raise_raw_io_error)
    assert (
        main(
            [
                "--config",
                str(_config(tmp_path / "ppmi.yaml")),
                "--metadata-root",
                str(root),
                "--output-dir",
                str(tmp_path / "out"),
            ]
        )
        == 2
    )

    stderr = capsys.readouterr().err
    assert stderr == "PPMI manifest failed: PPMI output cannot be written\n"
    assert str(raw_path) not in stderr
    assert raw_path.name not in stderr
