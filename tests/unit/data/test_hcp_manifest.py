"""Synthetic acceptance tests for the provisional HCP manifest."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

import canospar.data.hcp_manifest as hcp_manifest_module
from canospar.data.hcp_manifest import HCPManifestError, build_hcp_manifest, main

TARGETS = ("CogFluidComp_Unadj", "CogTotalComp_Unadj", "PMAT24_A_CR")
SUBJECT_COLUMNS = [
    "Subject",
    "Age_in_Yrs",
    "T1_Count",
    "3T_RS-fMRI_Count",
    "3T_dMRI_Compl",
    "3T_Full_MR_Compl",
    "QC_Issue",
    "Release",
    "Acquisition",
    *TARGETS,
]
REQUIRED_SUBJECT_COLUMNS = [column for column in SUBJECT_COLUMNS if column != "Age_in_Yrs"]


def _csv(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def _configuration(path: Path, *, with_processed_imaging: bool = False) -> Path:
    logical_inputs = {
        "data_dictionary": {"patterns": ["dictionary.csv"], "required_columns": ["columnHeader"]},
        "unrelated_list": {"patterns": ["unrelated.csv"], "required_columns": ["Subject"]},
        "subject_export": {
            "patterns": ["subjects.csv"],
            "required_columns": REQUIRED_SUBJECT_COLUMNS,
        },
        "appendix_2025": {"patterns": ["appendix_2025.csv"], "required_columns": ["release"]},
        "access_record": {
            "patterns": ["access.csv"],
            "required_columns": ["access_tier", "status"],
        },
        "download_record": {"patterns": ["download_record.json"]},
        "download_manifest": {"patterns": ["download_manifest.json"]},
        "legacy_inventory": {"legacy_directory": "legacy", "required": False},
    }
    if with_processed_imaging:
        logical_inputs["s1200_processed_imaging"] = {"patterns": ["s1200_processed.csv"]}
    config = {
        "contract_version": "1.1.0",
        "cohort": "hcp",
        "column_map": "columns.yaml",
        "access": {"open_access": "approved", "restricted_access": "not_approved"},
        "availability_snapshot_date": "2025-01-31",
        "logical_inputs": logical_inputs,
        "manifest_defaults": {
            "cohort_source": "hcp_official_unrelated",
            "kinship_control_method": "official_unrelated_cohort",
        },
        "target_selection": {
            "primary_target": "CogFluidComp_Unadj",
            "secondary_targets": ["CogTotalComp_Unadj", "PMAT24_A_CR"],
            "task_type": "regression",
            "primary_metric": "MAE",
        },
    }
    path.write_text(json.dumps(config), encoding="utf-8")
    path.with_name("columns.yaml").write_text(
        "subject_id: Subject\n"
        "age: Age_in_Yrs\n"
        "t1_count: T1_Count\n"
        "fmri_count: 3T_RS-fMRI_Count\n"
        "dwi_complete: 3T_dMRI_Compl\n"
        "full_mr_complete: 3T_Full_MR_Compl\n"
        "qc_issue: QC_Issue\n"
        "fluid_cognition_target: CogFluidComp_Unadj\n"
        "total_cognition_target: CogTotalComp_Unadj\n"
        "matrix_reasoning_target: PMAT24_A_CR\n"
        "release: Release\n"
        "acquisition: Acquisition\n"
        "dictionary_field: columnHeader\n"
        "dictionary_definition: description\n",
        encoding="utf-8",
    )
    return path


def _metadata(root: Path) -> None:
    _csv(
        root / "dictionary.csv",
        ["columnHeader", "description"],
        [[target, "synthetic definition"] for target in TARGETS],
    )
    _csv(root / "unrelated.csv", ["Subject"], [["HCP_SYN_0007"], ["HCP_SYN_0008"]])
    _csv(
        root / "subjects.csv",
        SUBJECT_COLUMNS,
        [
            [
                "HCP_SYN_0007",
                "22",
                "1",
                "1",
                "true",
                "false",
                "flag",
                "2025",
                "yes",
                "100",
                "90",
                "20",
            ],
            ["HCP_SYN_0008", "23", "0", "1", "false", "true", "", "2025", "yes", "101", "", "21"],
            ["HCP_SYN_0099", "24", "1", "1", "true", "true", "", "2025", "yes", "102", "92", "22"],
        ],
    )
    _csv(root / "appendix_2025.csv", ["release"], [["HCP-YA 2025"]])
    _csv(
        root / "access.csv",
        ["access_tier", "status"],
        [["Open Access", "approved"], ["Restricted Access", "not approved"]],
    )
    (root / "download_record.json").write_text('{"status": "recorded"}', encoding="utf-8")
    (root / "download_manifest.json").write_text('{"files": []}', encoding="utf-8")


def _build(tmp_path: Path):  # type: ignore[no-untyped-def]
    metadata = tmp_path / "metadata"
    _metadata(metadata)
    return build_hcp_manifest(_configuration(tmp_path / "hcp.yaml"), metadata)


def test_unrelated_whitelist_leading_zero_completion_full_mr_and_qc_rules(tmp_path: Path) -> None:
    result = _build(tmp_path)

    assert [row["subject_id"] for row in result.manifest] == ["HCP_SYN_0007", "HCP_SYN_0008"]
    assert result.manifest[0]["group_id"] == "HCP_SYN_0007"
    assert result.manifest[0]["t1_available"] is True
    assert result.manifest[0]["fmri_available"] is True
    assert result.manifest[0]["dwi_available"] is True
    assert result.manifest[0]["dataset"] == "hcp"
    assert result.manifest[0]["source_release"] == "2025"
    assert result.manifest[0]["site_id"] == "unknown"
    assert result.manifest[0]["site_available"] is False
    assert result.manifest[0]["age"] == 22.0
    assert result.manifest[0]["target"] is None
    assert result.manifest[0]["target_name"] is None
    assert result.manifest[0]["t1_downloaded"] is False
    assert result.manifest[0]["t1_preprocessed"] is False
    assert result.manifest[0]["t1_qc_pass"] is None
    assert result.manifest[0]["raw_qc_status"] == "flag"
    assert result.manifest[0]["availability_snapshot_date"] == "2025-01-31"
    assert len(result.manifest[0]["source_manifest_hash"]) == 64
    assert result.manifest[1]["t1_available"] is False
    assert result.manifest[1]["dwi_available"] is False
    assert result.manifest[0]["family_id"] is None
    assert result.manifest[0]["fmri_downloaded"] is False
    assert result.manifest[0]["dwi_downloaded"] is False
    assert result.manifest[0]["dwi_path"] == ""
    assert result.audit["full_mr_audit"]["completed_count"] == 1


def test_completion_is_not_a_processed_inventory_and_targets_are_aggregate_only(
    tmp_path: Path,
) -> None:
    result = _build(tmp_path)

    assert result.provenance["cohort_status"] == "provisional"
    assert result.provenance["availability_basis"] == "acquisition_completion_fields"
    assert result.provenance["processed_package_inventory"] == "not_available"
    assert result.audit["status"] == "READY_FOR_USER_SELECTED_TASK"
    assert result.audit["primary_target"] == "CogFluidComp_Unadj"
    assert result.audit["secondary_targets"] == ["CogTotalComp_Unadj", "PMAT24_A_CR"]
    assert result.audit["task_type"] == "regression"
    assert result.audit["primary_metric"] == "MAE"
    assert set(result.audit["targets"]) == set(TARGETS)
    target = result.audit["targets"]["CogFluidComp_Unadj"]
    assert target["dictionary_definition"] == "synthetic definition"
    assert target["open_access"] is True
    assert target["data_type"] == "not_available"
    assert target["non_missing"] == 3
    assert target["unrelated_non_missing"] == 2
    assert target["provisional_trimodal_non_missing"] == 1
    assert target["missing_rate"] == 0
    assert target["unique_values"] == 3
    assert target["min"] == 100
    assert target["q1"] == 100.5
    assert target["median"] == 101
    assert target["q3"] == 101.5
    assert target["max"] == 102
    assert target["mean"] == 101
    assert target["std"] == 1
    assert target["outlier_count"] == 0
    assert target["age_coverage"] == {"non_missing": 3, "total": 3, "available": True}
    assert target["sex_coverage"] == {"non_missing": 0, "total": 3, "available": False}
    assert target["qc_issue_distribution"] == {"flag": 1, "none": 2}
    assert "HCP_SYN_0007" not in json.dumps(result.audit)
    for candidate_name in TARGETS:
        candidate = result.audit["targets"][candidate_name]
        assert set(candidate) >= {
            "dictionary_definition",
            "open_access",
            "data_type",
            "non_missing",
            "unrelated_non_missing",
            "provisional_trimodal_non_missing",
            "missing_rate",
            "unique_values",
            "min",
            "q1",
            "median",
            "q3",
            "max",
            "mean",
            "std",
            "outlier_count",
            "age_coverage",
            "sex_coverage",
            "qc_issue_distribution",
        }


def test_rejects_s1200_processed_imaging_but_not_a_dictionary_name(tmp_path: Path) -> None:
    metadata = tmp_path / "metadata"
    _metadata(metadata)
    (metadata / "s1200_processed.csv").write_text("inventory\nlegacy\n", encoding="utf-8")

    with pytest.raises(HCPManifestError, match="S1200 processed imaging"):
        build_hcp_manifest(
            _configuration(tmp_path / "hcp.yaml", with_processed_imaging=True), metadata
        )


def test_outputs_are_deterministic_and_do_not_place_subjects_in_console(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    metadata = tmp_path / "metadata"
    _metadata(metadata)
    config = _configuration(tmp_path / "hcp.yaml")
    first = tmp_path / "first"
    second = tmp_path / "second"

    assert (
        main(
            ["--config", str(config), "--metadata-root", str(metadata), "--output-dir", str(first)]
        )
        == 0
    )
    assert (
        main(
            ["--config", str(config), "--metadata-root", str(metadata), "--output-dir", str(second)]
        )
        == 0
    )

    console = capsys.readouterr().out
    assert console.count("HCP manifest") == 2
    assert "HCP_SYN_" not in console
    for name in (
        "hcp_manifest.json",
        "hcp_exclusions.json",
        "hcp_audit.json",
        "hcp_provenance.json",
    ):
        assert (first / name).read_bytes() == (second / name).read_bytes()


def test_cli_reports_logical_input_errors_without_rows(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    metadata = tmp_path / "metadata"
    _metadata(metadata)
    (metadata / "subjects.csv").write_text("Subject\nHCP_SYN_0007\n", encoding="utf-8")

    assert (
        main(
            [
                "--config",
                str(_configuration(tmp_path / "hcp.yaml")),
                "--metadata-root",
                str(metadata),
                "--output-dir",
                str(tmp_path / "out"),
                "--dry-run",
            ]
        )
        == 2
    )
    stderr = capsys.readouterr().err
    assert "subject_export" in stderr
    assert "HCP_SYN_" not in stderr


def test_cli_normalizes_missing_config_without_disclosing_absolute_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing_config = tmp_path / "private-hcp-config-sentinel.yaml"

    assert (
        main(
            [
                "--config",
                str(missing_config),
                "--metadata-root",
                str(tmp_path),
                "--output-dir",
                str(tmp_path / "out"),
                "--dry-run",
            ]
        )
        == 2
    )

    stderr = capsys.readouterr().err
    assert stderr == "HCP manifest failed: HCP configuration cannot be read\n"
    assert str(missing_config) not in stderr
    assert missing_config.name not in stderr


def test_cli_normalizes_raw_discovery_io_error_without_disclosing_absolute_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    raw_path = tmp_path / "private-discovery-sentinel.yaml"

    def raise_raw_io_error(_: Path) -> object:
        raise FileNotFoundError(2, "missing", str(raw_path))

    monkeypatch.setattr(hcp_manifest_module, "load_logical_inputs", raise_raw_io_error)
    assert (
        main(
            [
                "--config",
                str(_configuration(tmp_path / "hcp.yaml")),
                "--metadata-root",
                str(tmp_path / "metadata"),
                "--output-dir",
                str(tmp_path / "out"),
                "--dry-run",
            ]
        )
        == 2
    )

    stderr = capsys.readouterr().err
    assert stderr == "HCP manifest failed: HCP metadata discovery cannot be read\n"
    assert str(raw_path) not in stderr
    assert raw_path.name not in stderr


def test_cli_normalizes_output_write_error_without_disclosing_absolute_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    metadata = tmp_path / "metadata"
    _metadata(metadata)
    raw_path = tmp_path / "private-hcp-output-sentinel.json"

    def raise_raw_io_error(*_: object) -> None:
        raise OSError(5, "write failed", str(raw_path))

    monkeypatch.setattr(hcp_manifest_module, "_write_outputs", raise_raw_io_error)
    assert (
        main(
            [
                "--config",
                str(_configuration(tmp_path / "hcp.yaml")),
                "--metadata-root",
                str(metadata),
                "--output-dir",
                str(tmp_path / "out"),
            ]
        )
        == 2
    )

    stderr = capsys.readouterr().err
    assert stderr == "HCP manifest failed: HCP output cannot be written\n"
    assert str(raw_path) not in stderr
    assert raw_path.name not in stderr


@pytest.mark.parametrize(
    ("logical_input", "replacement", "message"),
    [
        (
            "subjects.csv",
            ",".join(SUBJECT_COLUMNS)
            + "\nHCP_SYN_0007,22,1,1,true,true,,2025,yes,1,2,3"
            + "\nHCP_SYN_0007,22,1,1,true,true,,2025,yes,1,2,3\n",
            "duplicate subject identifiers",
        ),
        (
            "subjects.csv",
            ",".join(SUBJECT_COLUMNS)
            + "\nHCP_SYN_0007,22,not-a-number,1,true,true,,2025,yes,1,2,3\n",
            "invalid completion fields",
        ),
        (
            "subjects.csv",
            ",".join(SUBJECT_COLUMNS) + "\nHCP_SYN_0007,22,1,1,maybe,true,,2025,yes,1,2,3\n",
            "invalid 3T_dMRI completion",
        ),
        (
            "subjects.csv",
            ",".join(SUBJECT_COLUMNS) + "\nHCP_SYN_0007,22,1,1,true,maybe,,2025,yes,1,2,3\n",
            "invalid 3T_Full_MR completion",
        ),
    ],
)
def test_rejects_invalid_logical_inputs_without_echoing_row_values(
    tmp_path: Path, logical_input: str, replacement: str, message: str
) -> None:
    metadata = tmp_path / "metadata"
    _metadata(metadata)
    (metadata / logical_input).write_text(replacement, encoding="utf-8")

    with pytest.raises(HCPManifestError, match=message) as error:
        build_hcp_manifest(_configuration(tmp_path / "hcp.yaml"), metadata)

    assert "HCP_SYN_" not in str(error.value)


def test_dry_run_does_not_create_outputs(tmp_path: Path) -> None:
    metadata = tmp_path / "metadata"
    _metadata(metadata)
    output = tmp_path / "out"

    assert (
        main(
            [
                "--config",
                str(_configuration(tmp_path / "hcp.yaml")),
                "--metadata-root",
                str(metadata),
                "--output-dir",
                str(output),
                "--dry-run",
            ]
        )
        == 0
    )
    assert not output.exists()


def test_rejects_configuration_missing_a_required_logical_input(tmp_path: Path) -> None:
    metadata = tmp_path / "metadata"
    _metadata(metadata)
    config_path = _configuration(tmp_path / "hcp.yaml")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    del config["logical_inputs"]["download_record"]
    config_path.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(HCPManifestError, match="download_record"):
        build_hcp_manifest(config_path, metadata)


def test_uses_recorded_manifest_snapshot_date_when_configuration_omits_it(tmp_path: Path) -> None:
    metadata = tmp_path / "metadata"
    _metadata(metadata)
    config_path = _configuration(tmp_path / "hcp.yaml")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    del config["availability_snapshot_date"]
    config_path.write_text(json.dumps(config), encoding="utf-8")
    (metadata / "download_manifest.json").write_text(
        '[{"downloaded_at": "2025-02-03T12:00:00Z"}]', encoding="utf-8"
    )

    assert (
        build_hcp_manifest(config_path, metadata).manifest[0]["availability_snapshot_date"]
        == "2025-02-03"
    )


def test_reads_bom_prefixed_download_manifest_for_recorded_snapshot_date(tmp_path: Path) -> None:
    metadata = tmp_path / "metadata"
    _metadata(metadata)
    config_path = _configuration(tmp_path / "hcp.yaml")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    del config["availability_snapshot_date"]
    config_path.write_text(json.dumps(config), encoding="utf-8")
    (metadata / "download_manifest.json").write_text(
        '\ufeff[{"downloaded_at": "2025-02-03T12:00:00Z"}]', encoding="utf-8"
    )

    assert (
        build_hcp_manifest(config_path, metadata).manifest[0]["availability_snapshot_date"]
        == "2025-02-03"
    )


def test_missing_optional_age_remains_null_and_is_reported_as_unavailable(tmp_path: Path) -> None:
    metadata = tmp_path / "metadata"
    _metadata(metadata)
    without_age = [column for column in SUBJECT_COLUMNS if column != "Age_in_Yrs"]
    _csv(
        metadata / "subjects.csv",
        without_age,
        [
            ["HCP_SYN_0007", "1", "1", "true", "false", "flag", "2025", "yes", "100", "90", "20"],
            ["HCP_SYN_0008", "0", "1", "false", "true", "", "2025", "yes", "101", "", "21"],
        ],
    )

    result = build_hcp_manifest(_configuration(tmp_path / "hcp.yaml"), metadata)
    assert result.manifest[0]["age"] is None
    assert result.audit["targets"]["CogFluidComp_Unadj"]["age_coverage"] == {
        "non_missing": 0,
        "total": 2,
        "available": False,
    }


@pytest.mark.parametrize(
    ("dictionary_headers", "dictionary_rows", "message"),
    [
        (["columnHeader", "description"], [["other", "synthetic"]], "missing candidate targets"),
        (["unmapped"], [["other"]], "missing columns"),
    ],
)
def test_rejects_invalid_dictionary_metadata(
    tmp_path: Path, dictionary_headers: list[str], dictionary_rows: list[list[str]], message: str
) -> None:
    metadata = tmp_path / "metadata"
    _metadata(metadata)
    _csv(metadata / "dictionary.csv", dictionary_headers, dictionary_rows)

    with pytest.raises(HCPManifestError, match=message):
        build_hcp_manifest(_configuration(tmp_path / "hcp.yaml"), metadata)


def test_dictionary_field_mapping_is_required(tmp_path: Path) -> None:
    metadata = tmp_path / "metadata"
    _metadata(metadata)
    config_path = _configuration(tmp_path / "hcp.yaml")
    column_map_path = config_path.with_name("columns.yaml")
    column_map_path.write_text(
        "\n".join(
            line
            for line in column_map_path.read_text(encoding="utf-8").splitlines()
            if not line.startswith("dictionary_field:")
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(HCPManifestError, match="dictionary field mapping"):
        build_hcp_manifest(config_path, metadata)


def test_dictionary_mapping_to_missing_column_fails_safely(tmp_path: Path) -> None:
    metadata = tmp_path / "metadata"
    _metadata(metadata)
    config_path = _configuration(tmp_path / "hcp.yaml")
    column_map_path = config_path.with_name("columns.yaml")
    column_map_path.write_text(
        column_map_path.read_text(encoding="utf-8").replace(
            "dictionary_field: columnHeader", "dictionary_field: unavailable_column"
        ),
        encoding="utf-8",
    )

    with pytest.raises(HCPManifestError, match="data_dictionary.*mapped field column"):
        build_hcp_manifest(config_path, metadata)


def test_rejects_missing_source_release_without_exposing_subject_value(tmp_path: Path) -> None:
    metadata = tmp_path / "metadata"
    _metadata(metadata)
    rows = [["HCP_SYN_0007", "22", "1", "1", "true", "true", "", "", "yes", "1", "2", "3"]]
    _csv(metadata / "subjects.csv", SUBJECT_COLUMNS, rows)

    with pytest.raises(HCPManifestError, match="missing source release") as error:
        build_hcp_manifest(_configuration(tmp_path / "hcp.yaml"), metadata)
    assert "HCP_SYN_" not in str(error.value)
