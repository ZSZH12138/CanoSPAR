"""Tests for unified, contract-versioned manifest schema validation."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
import yaml

from canospar.data.manifest_schema import ManifestSchemaError, validate_manifest_row


def _row() -> dict[str, object]:
    return {
        "contract_version": "1.1.0",
        "dataset": "hcp",
        "source_release": "2025",
        "cohort_source": "hcp_official_unrelated",
        "unrelated_list_version": "S900",
        "kinship_control_method": "official_unrelated_cohort",
        "subject_id": "0007",
        "visit_id": "baseline",
        "group_id": "0007",
        "site_id": "unknown",
        "site_available": False,
        "site_source": "unavailable",
        "family_id": None,
        "scanner_vendor": None,
        "scanner_model": None,
        "field_strength": None,
        "normalized_protocol": None,
        "scanner_batch_id": None,
        "age": 25.0,
        "sex": None,
        "diagnosis": None,
        "diagnosis_source": None,
        "target": None,
        "target_name": None,
        "target_date": None,
        "imaging_date": None,
        "imaging_clinical_interval_days": None,
        "t1_available": True,
        "fmri_available": False,
        "dwi_available": False,
        "t1_downloaded": False,
        "t1_preprocessed": False,
        "t1_qc_pass": None,
        "t1_path": "",
        "fmri_downloaded": False,
        "fmri_preprocessed": False,
        "fmri_qc_pass": None,
        "fmri_path": "",
        "dwi_downloaded": False,
        "dwi_preprocessed": False,
        "dwi_qc_pass": None,
        "dwi_path": "",
        "raw_qc_status": None,
        "exclusion_reason": "none",
        "availability_basis": "acquisition_completion_fields",
        "availability_snapshot_date": "2026-07-26",
        "cohort_status": "provisional",
        "row_status": "provisional",
        "source_manifest_hash": "a" * 64,
    }


def test_validates_hcp_and_ppmi_provenance_rules() -> None:
    assert validate_manifest_row(_row())["subject_id"] == "0007"
    ppmi = _row() | {
        "dataset": "ppmi",
        "cohort_source": "not_applicable",
        "unrelated_list_version": "not_applicable",
        "kinship_control_method": "not_applicable",
    }
    assert validate_manifest_row(ppmi)["cohort_source"] == "not_applicable"


def test_schema_has_exact_section_9_field_names() -> None:
    schema_path = Path(__file__).resolve().parents[3] / "configs" / "data" / "manifest_schema.yaml"
    schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))

    assert set(schema["row_fields"]) == set(_row())


@pytest.mark.parametrize("deprecated_field", ["downloaded", "preprocessed", "qc_pass"])
def test_rejects_fields_outside_the_exact_schema(deprecated_field: str) -> None:
    with pytest.raises(
        ManifestSchemaError, match=rf"unexpected manifest fields: {deprecated_field}"
    ):
        validate_manifest_row(_row() | {deprecated_field: False})


def test_rejects_missing_fields_from_the_exact_schema() -> None:
    incomplete = _row()
    del incomplete["scanner_vendor"]

    with pytest.raises(ManifestSchemaError, match="missing manifest fields: scanner_vendor"):
        validate_manifest_row(incomplete)


def test_rejects_non_string_field_names_with_a_safe_error() -> None:
    malformed = cast(dict[str, object], _row() | {1: False})

    with pytest.raises(ManifestSchemaError, match="unexpected manifest fields: <invalid>"):
        validate_manifest_row(malformed)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"contract_version": "1.0.0"}, "contract_version"),
        ({"dataset": "other"}, "dataset"),
        ({"site_available": "false"}, "site_available"),
        ({"subject_id": ""}, "subject_id"),
        ({"family_id": "family"}, "family_id"),
        ({"cohort_source": "not_applicable"}, "provenance"),
        ({"kinship_control_method": "family_id_grouping"}, "kinship_control_method"),
        ({"t1_downloaded": "false"}, "t1_downloaded"),
    ],
)
def test_rejects_invalid_enum_nullable_and_type_rules(
    change: dict[str, object], message: str
) -> None:
    with pytest.raises(ManifestSchemaError, match=message):
        validate_manifest_row(_row() | change)


def test_rejects_missing_section_9_field_and_ppmi_non_sentinel_provenance() -> None:
    incomplete = _row()
    del incomplete["source_manifest_hash"]
    with pytest.raises(ManifestSchemaError, match="source_manifest_hash"):
        validate_manifest_row(incomplete)

    ppmi = _row() | {
        "dataset": "ppmi",
        "cohort_source": "not_applicable",
        "unrelated_list_version": "not_applicable",
        "kinship_control_method": "official_unrelated_cohort",
    }
    with pytest.raises(ManifestSchemaError, match="not_applicable"):
        validate_manifest_row(ppmi)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"cohort_status": "open"}, "cohort_status"),
        ({"row_status": "pending"}, "row_status"),
        ({"exclusion_reason": "free_text"}, "exclusion_reason"),
        ({"availability_basis": "other"}, "availability_basis"),
        ({"group_id": "different"}, "group_id"),
        ({"t1_downloaded": True}, "t1_downloaded"),
        ({"fmri_path": "nonempty"}, "fmri_path"),
        ({"availability_snapshot_date": "not-a-date"}, "availability_snapshot_date"),
    ],
)
def test_rejects_schema_enums_and_m0_relational_violations(
    change: dict[str, object], message: str
) -> None:
    with pytest.raises(ManifestSchemaError, match=message):
        validate_manifest_row(_row() | change)


def test_rejects_ppmi_site_and_hcp_family_or_modality_violations() -> None:
    ppmi_site = _row() | {
        "dataset": "ppmi",
        "cohort_source": "not_applicable",
        "unrelated_list_version": "not_applicable",
        "kinship_control_method": "not_applicable",
        "site_id": "site_a",
        "site_available": True,
    }
    with pytest.raises(ManifestSchemaError, match="PPMI site"):
        validate_manifest_row(ppmi_site)

    with pytest.raises(ManifestSchemaError, match="family_id"):
        validate_manifest_row(_row() | {"family_id": "family"})
