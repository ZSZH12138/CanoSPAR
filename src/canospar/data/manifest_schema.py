"""Validation for the complete contract-versioned unified manifest schema."""

from __future__ import annotations

import math
import re
from collections.abc import Collection, Mapping
from datetime import date
from numbers import Real
from pathlib import Path
from typing import Any

import yaml

CONTRACT_VERSION = "1.1.0"
_SCHEMA_PATH = Path(__file__).resolve().parents[3] / "configs" / "data" / "manifest_schema.yaml"
_MODALITIES = ("t1", "fmri", "dwi")
_REQUIRED_STRINGS = (
    "dataset",
    "source_release",
    "subject_id",
    "visit_id",
    "group_id",
    "site_id",
    "site_source",
    "availability_basis",
    "availability_snapshot_date",
    "cohort_status",
    "row_status",
    "cohort_source",
    "unrelated_list_version",
    "kinship_control_method",
)
_NULLABLE_STRINGS = (
    "scanner_vendor",
    "scanner_model",
    "normalized_protocol",
    "scanner_batch_id",
    "sex",
    "diagnosis",
    "diagnosis_source",
    "target_name",
    "target_date",
    "imaging_date",
    "raw_qc_status",
)
_EXCLUSION_REASONS = frozenset(
    {
        "none",
        "not_acquired",
        "not_in_source_inventory",
        "not_downloaded",
        "download_failed",
        "preprocessing_not_run",
        "preprocessing_failed",
        "qc_not_run",
        "qc_failed",
        "missing_target",
        "missing_visit_mapping",
        "ambiguous_sequence",
        "ambiguous_exam_state",
        "unknown",
        "not_applicable",
    }
)
_SAFE_FIELD_NAME = re.compile(r"[a-z][a-z0-9_]*")


class ManifestSchemaError(ValueError):
    """A row violates a versioned contract invariant."""


def load_manifest_schema() -> Mapping[str, Any]:
    data = yaml.safe_load(_SCHEMA_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ManifestSchemaError("manifest schema must be a mapping")
    return data


def _load_schema_field_names() -> frozenset[str]:
    row_fields = load_manifest_schema().get("row_fields")
    if not isinstance(row_fields, Mapping) or not all(isinstance(name, str) for name in row_fields):
        raise ManifestSchemaError("manifest schema must define named row fields")
    return frozenset(row_fields)


_SCHEMA_FIELD_NAMES = _load_schema_field_names()


def _non_empty(row: Mapping[str, object], name: str) -> None:
    if not isinstance(row.get(name), str) or not str(row[name]).strip():
        raise ManifestSchemaError(f"{name} must be a non-empty string")


def _nullable_string(row: Mapping[str, object], name: str) -> None:
    value = row.get(name)
    if value is not None and not isinstance(value, str):
        raise ManifestSchemaError(f"{name} must be a string or null")


def _nullable_number(row: Mapping[str, object], name: str) -> None:
    value = row.get(name)
    if value is not None and (
        isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value)
    ):
        raise ManifestSchemaError(f"{name} must be a finite number or null")


def _nullable_iso_date(row: Mapping[str, object], name: str) -> None:
    value = row.get(name)
    _nullable_string(row, name)
    if isinstance(value, str):
        try:
            date.fromisoformat(value)
        except ValueError as error:
            raise ManifestSchemaError(f"{name} must be ISO-8601 or null") from error


def _format_unexpected_field_names(names: Collection[object]) -> str:
    safe_names = {
        name if isinstance(name, str) and _SAFE_FIELD_NAME.fullmatch(name) else "<invalid>"
        for name in names
    }
    return ", ".join(sorted(safe_names))


def validate_manifest_row(row: Mapping[str, object]) -> dict[str, object]:
    """Validate one full Section 9 row without coercing identifiers or paths."""
    if not isinstance(row, Mapping):
        raise ManifestSchemaError("manifest row must be a mapping")
    result = dict(row)
    missing_fields = sorted(_SCHEMA_FIELD_NAMES.difference(result))
    if missing_fields:
        raise ManifestSchemaError(f"missing manifest fields: {', '.join(missing_fields)}")
    unexpected_fields = set(result).difference(_SCHEMA_FIELD_NAMES)
    if unexpected_fields:
        raise ManifestSchemaError(
            f"unexpected manifest fields: {_format_unexpected_field_names(unexpected_fields)}"
        )
    if result.get("contract_version") != CONTRACT_VERSION:
        raise ManifestSchemaError("contract_version must equal 1.1.0")
    for field in _REQUIRED_STRINGS:
        _non_empty(result, field)
    if result["dataset"] not in {"hcp", "ppmi"}:
        raise ManifestSchemaError("dataset must be hcp or ppmi")
    if result["group_id"] != result["subject_id"]:
        raise ManifestSchemaError("group_id must equal subject_id")
    if result.get("family_id") is not None:
        raise ManifestSchemaError(
            "family_id must be null while HCP Restricted Access is unapproved"
        )
    for field in _NULLABLE_STRINGS:
        _nullable_string(result, field)
    for field in ("target_date", "imaging_date"):
        _nullable_iso_date(result, field)
    snapshot_date = result.get("availability_snapshot_date")
    try:
        if not isinstance(snapshot_date, str):
            raise ValueError
        date.fromisoformat(snapshot_date)
    except ValueError as error:
        raise ManifestSchemaError("availability_snapshot_date must be ISO-8601") from error
    for field in ("age", "target", "field_strength", "imaging_clinical_interval_days"):
        _nullable_number(result, field)
    if type(result.get("site_available")) is not bool:
        raise ManifestSchemaError("site_available must be boolean")
    if result["cohort_status"] not in {"provisional", "frozen"}:
        raise ManifestSchemaError("cohort_status is invalid")
    if result["row_status"] not in {"provisional", "included", "excluded"}:
        raise ManifestSchemaError("row_status is invalid")
    if result["availability_basis"] not in {"acquisition_completion_fields", "source_inventory"}:
        raise ManifestSchemaError("availability_basis is invalid")
    if result.get("exclusion_reason") not in _EXCLUSION_REASONS:
        raise ManifestSchemaError("exclusion_reason is invalid")
    for modality in _MODALITIES:
        for suffix in ("available", "downloaded", "preprocessed"):
            field = f"{modality}_{suffix}"
            if type(result.get(field)) is not bool:
                raise ManifestSchemaError(f"{field} must be boolean")
        qc_field = f"{modality}_qc_pass"
        if result.get(qc_field) is not None and type(result[qc_field]) is not bool:
            raise ManifestSchemaError(f"{qc_field} must be boolean or null")
        path_field = f"{modality}_path"
        if not isinstance(result.get(path_field), str):
            raise ManifestSchemaError(f"{path_field} must be a string")
        if result[f"{modality}_downloaded"] is not False:
            raise ManifestSchemaError(f"{modality}_downloaded must be false in M0")
        if result[f"{modality}_preprocessed"] is not False:
            raise ManifestSchemaError(f"{modality}_preprocessed must be false in M0")
        if result[qc_field] is not None:
            raise ManifestSchemaError(f"{qc_field} must be null in M0")
        if result[path_field] != "":
            raise ManifestSchemaError(f"{path_field} must be empty in M0")
    source_hash = result.get("source_manifest_hash")
    if not isinstance(source_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", source_hash):
        raise ManifestSchemaError("source_manifest_hash must be a lowercase SHA-256")
    hcp_fields = ("cohort_source", "unrelated_list_version", "kinship_control_method")
    sentinel_count = sum(result[field] == "not_applicable" for field in hcp_fields)
    if result["dataset"] == "ppmi":
        if sentinel_count != 3:
            raise ManifestSchemaError("PPMI provenance fields must all equal not_applicable")
        if result["site_id"] != "unknown" or result["site_available"] is not False:
            raise ManifestSchemaError("PPMI site must be unknown and unavailable")
    elif sentinel_count != 0 or result["cohort_source"] != "hcp_official_unrelated":
        raise ManifestSchemaError("HCP cohort provenance is invalid")
    elif result["kinship_control_method"] != "official_unrelated_cohort":
        raise ManifestSchemaError(
            "kinship_control_method must be official_unrelated_cohort for HCP"
        )
    return result
