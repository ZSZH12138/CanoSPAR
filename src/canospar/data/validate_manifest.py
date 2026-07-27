"""Aggregate-only validation for deterministic Week 2-4 manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PureWindowsPath
from typing import Literal, TypeAlias

import yaml

from canospar.data.manifest_schema import (
    CONTRACT_VERSION,
    ManifestSchemaError,
    validate_manifest_row,
)
from canospar.data.metadata_io import canonical_json_bytes

CheckStatus: TypeAlias = Literal["PASS", "WARN", "FAIL"]
ValidationStatus: TypeAlias = Literal["PASS", "PARTIAL", "FAIL"]

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_SCHEMA = _PROJECT_ROOT / "configs" / "data" / "manifest_schema.yaml"
_IDENTIFIER_FIELDS = ("subject_id", "visit_id", "group_id")
_DATE_FIELDS = ("availability_snapshot_date", "target_date", "imaging_date")
_MODALITIES = ("t1", "fmri", "dwi")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_SCIENTIFIC_ID = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)[eE][+-]?\d+")
_WINDOWS_UNC_PATH = re.compile(r"(?i)(?<![:/\\])(?:\\\\|//)[^\\/\r\n\"']+[\\/][^\r\n\"']+")


@dataclass(frozen=True)
class ValidationCheck:
    """One privacy-preserving aggregate validation result."""

    name: str
    status: CheckStatus
    count: int
    message: str

    def as_record(self) -> dict[str, str | int]:
        return {
            "name": self.name,
            "status": self.status,
            "count": self.count,
            "message": self.message,
        }


@dataclass(frozen=True)
class ManifestValidationResult:
    """Machine-readable manifest validation result."""

    status: ValidationStatus
    manifest_sha256: str
    checks: tuple[ValidationCheck, ...]

    def as_record(self) -> dict[str, object]:
        return {
            "status": self.status,
            "manifest_sha256": self.manifest_sha256,
            "checks": [check.as_record() for check in self.checks],
        }


def _check(name: str, failures: int, message: str) -> ValidationCheck:
    return ValidationCheck(name, "FAIL" if failures else "PASS", failures, message)


def _read_rows(path: Path) -> tuple[list[Mapping[str, object]], bytes, ValidationCheck]:
    try:
        raw = path.read_bytes()
    except OSError:
        return [], b"", _check("manifest_json", 1, "manifest cannot be read")
    try:
        decoded = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return [], raw, _check("manifest_json", 1, "manifest is not valid UTF-8 JSON")
    if not isinstance(decoded, list) or not all(isinstance(row, Mapping) for row in decoded):
        return [], raw, _check("manifest_json", 1, "manifest must be a JSON row array")
    rows = [row for row in decoded if isinstance(row, Mapping)]
    return rows, raw, _check("manifest_json", 0, "manifest is a JSON row array")


def _schema_contract_check(schema_path: Path) -> ValidationCheck:
    try:
        schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return _check("schema_contract", 1, "schema configuration cannot be read")
    valid = isinstance(schema, Mapping) and schema.get("contract_version") == CONTRACT_VERSION
    return _check(
        "schema_contract",
        int(not valid),
        "schema contract version matches" if valid else "schema contract version is unsupported",
    )


def _schema_check(rows: Sequence[Mapping[str, object]]) -> ValidationCheck:
    failures = 0
    for row in rows:
        try:
            validate_manifest_row(row)
        except ManifestSchemaError:
            failures += 1
    return _check("schema", failures, "rows conform to the exact manifest schema")


def _unique_key_check(rows: Sequence[Mapping[str, object]]) -> ValidationCheck:
    keys = [
        (row.get("subject_id"), row.get("visit_id"))
        for row in rows
        if isinstance(row.get("subject_id"), str) and isinstance(row.get("visit_id"), str)
    ]
    failures = len(keys) - len(set(keys)) + (len(rows) - len(keys))
    return _check("unique_subject_visit", failures, "composite subject-visit keys are unique")


def _identifier_check(rows: Sequence[Mapping[str, object]]) -> ValidationCheck:
    failures = 0
    for row in rows:
        for field in _IDENTIFIER_FIELDS:
            value = row.get(field)
            if (
                not isinstance(value, str)
                or not value
                or value.endswith(".0")
                or _SCIENTIFIC_ID.fullmatch(value) is not None
            ):
                failures += 1
    return _check("identifier_strings", failures, "identifiers are canonical strings")


def _date_check(rows: Sequence[Mapping[str, object]]) -> ValidationCheck:
    failures = 0
    for row in rows:
        for field in _DATE_FIELDS:
            value = row.get(field)
            if value is None and field != "availability_snapshot_date":
                continue
            try:
                if not isinstance(value, str):
                    raise ValueError
                date.fromisoformat(value)
            except ValueError:
                failures += 1
    return _check("iso_dates", failures, "dates are ISO-8601 calendar dates")


def _state_check(rows: Sequence[Mapping[str, object]]) -> ValidationCheck:
    failures = 0
    for row in rows:
        if type(row.get("site_available")) is not bool:
            failures += 1
        for modality in _MODALITIES:
            available = row.get(f"{modality}_available")
            downloaded = row.get(f"{modality}_downloaded")
            preprocessed = row.get(f"{modality}_preprocessed")
            qc_pass = row.get(f"{modality}_qc_pass")
            path = row.get(f"{modality}_path")
            if type(available) is not bool or type(downloaded) is not bool:
                failures += 1
                continue
            if type(preprocessed) is not bool or (
                qc_pass is not None and type(qc_pass) is not bool
            ):
                failures += 1
            if (downloaded and not available) or (preprocessed and not downloaded):
                failures += 1
            if qc_pass is not None and not preprocessed:
                failures += 1
            if (bool(path) and not downloaded) or not isinstance(path, str):
                failures += 1
    return _check(
        "availability_state_transitions",
        failures,
        "availability, download, preprocessing and QC states are consistent",
    )


def _stable_serialization_check(
    rows: Sequence[Mapping[str, object]], raw: bytes
) -> ValidationCheck:
    ordered = sorted(rows, key=lambda row: (str(row.get("subject_id")), str(row.get("visit_id"))))
    canonical = canonical_json_bytes(ordered) + b"\n"
    failures = int(list(rows) != ordered) + int(raw != canonical)
    return _check(
        "stable_sort_and_serialization",
        failures,
        "rows and JSON bytes use the canonical deterministic representation",
    )


def _source_hash_check(rows: Sequence[Mapping[str, object]]) -> ValidationCheck:
    values = [row.get("source_manifest_hash") for row in rows]
    failures = sum(
        not isinstance(value, str) or _SHA256.fullmatch(value) is None for value in values
    )
    failures += int(len(set(values)) > 1)
    return _check("source_manifest_hashes", failures, "source hashes are lowercase SHA-256")


def _contract_version_check(rows: Sequence[Mapping[str, object]]) -> ValidationCheck:
    failures = sum(row.get("contract_version") != CONTRACT_VERSION for row in rows)
    return _check("contract_version", failures, "all rows use the current contract")


def _is_absolute_path_text(value: str) -> bool:
    normalized = value.strip()
    return (
        PureWindowsPath(normalized).is_absolute()
        or Path(normalized).is_absolute()
        or _WINDOWS_UNC_PATH.search(normalized) is not None
        or re.search(r"(?i)\b[a-z]:[\\/](?:users|documents and settings)[\\/]", normalized)
        is not None
    )


def _path_privacy_check(rows: Sequence[Mapping[str, object]]) -> ValidationCheck:
    failures = sum(
        _is_absolute_path_text(value)
        for row in rows
        for value in row.values()
        if isinstance(value, str)
    )
    return _check("path_privacy", failures, "rows contain no personal absolute paths")


def _private_git_tracking_check(repository_root: Path) -> ValidationCheck:
    commands = (
        ("git", "ls-files", "--", "data/metadata"),
        ("git", "diff", "--cached", "--name-only", "--", "data/metadata"),
        ("git", "log", "--all", "--format=%H", "--", "data/metadata"),
    )
    tracked: set[str] = set()
    isolated_git_environment = {
        name: value for name, value in os.environ.items() if not name.startswith("GIT_")
    }
    try:
        for command in commands:
            result = subprocess.run(
                command,
                cwd=repository_root,
                capture_output=True,
                text=True,
                check=False,
                env=isolated_git_environment,
            )
            if result.returncode != 0:
                raise OSError
            tracked.update(line for line in result.stdout.splitlines() if line.strip())
    except OSError:
        return ValidationCheck(
            "private_metadata_git_tracking",
            "WARN",
            0,
            "Git governance status could not be determined",
        )
    return _check(
        "private_metadata_git_tracking",
        len(tracked),
        "private metadata has no tracked, staged or historical files",
    )


def _dataset_check(rows: Sequence[Mapping[str, object]]) -> ValidationCheck:
    failures = 0
    datasets = {row.get("dataset") for row in rows}
    if len(datasets) != 1 or not datasets.issubset({"hcp", "ppmi"}):
        failures += 1
    hcp_subjects = [row.get("subject_id") for row in rows if row.get("dataset") == "hcp"]
    failures += len(hcp_subjects) - len(set(hcp_subjects))
    for row in rows:
        if row.get("dataset") == "hcp":
            failures += int(row.get("cohort_status") != "provisional")
            failures += int(row.get("availability_basis") != "acquisition_completion_fields")
            failures += int(row.get("family_id") is not None)
            failures += int(row.get("group_id") != row.get("subject_id"))
            release = str(row.get("source_release", "")).casefold()
            failures += int("2017" in release or ("s1200" in release and "processed" in release))
        elif row.get("dataset") == "ppmi":
            failures += int(row.get("availability_basis") != "source_inventory")
            failures += int(row.get("site_id") != "unknown")
            failures += int(row.get("site_available") is not False)
            failures += int(
                row.get("diagnosis") is not None
                and row.get("diagnosis_source") != "participant_status_enrollment_cohort"
            )
    return _check(
        "dataset_contract",
        failures,
        "dataset-specific HCP/PPMI manifest invariants hold",
    )


def _json_mapping(path: Path) -> Mapping[str, object] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, Mapping) else None


def _input_hash_is_valid(inputs: object, logical_name: str) -> bool:
    if not isinstance(inputs, Mapping):
        return False
    record = inputs.get(logical_name)
    return (
        isinstance(record, Mapping)
        and isinstance(value := record.get("sha256"), str)
        and _SHA256.fullmatch(value) is not None
    )


def _hcp_evidence_failures(
    provenance: Mapping[str, object] | None,
    audit: Mapping[str, object] | None,
    rows: Sequence[Mapping[str, object]],
) -> int:
    if provenance is None or audit is None:
        return 1
    failures = 0
    expected = {
        "cohort_status": "provisional",
        "availability_basis": "acquisition_completion_fields",
        "access_tier": "Open Access",
        "restricted_access": "not_approved",
        "unrelated_list_version": "S900",
        "processed_package_inventory": "not_available",
    }
    failures += sum(provenance.get(name) != value for name, value in expected.items())
    failures += int(not _input_hash_is_valid(provenance.get("inputs"), "unrelated_list"))
    input_manifest_hash = provenance.get("input_manifest_hash")
    failures += sum(row.get("source_manifest_hash") != input_manifest_hash for row in rows)
    targets = audit.get("targets")
    failures += int(
        not isinstance(targets, Mapping)
        or set(targets) != {"CogFluidComp_Unadj", "CogTotalComp_Unadj", "PMAT24_A_CR"}
    )
    return failures


def _ppmi_evidence_failures(
    provenance: Mapping[str, object] | None,
    audit: Mapping[str, object] | None,
    rows: Sequence[Mapping[str, object]],
) -> int:
    if provenance is None or audit is None:
        return 1
    failures = int(provenance.get("availability_basis") != "source_inventory")
    required_inputs = (
        "mri_completion",
        "archived_mri",
        "t1_inventory",
        "rsfmri_inventory",
        "dti_inventory",
    )
    failures += sum(
        not _input_hash_is_valid(provenance.get("inputs"), name) for name in required_inputs
    )
    input_manifest_hash = provenance.get("input_manifest_hash")
    failures += sum(row.get("source_manifest_hash") != input_manifest_hash for row in rows)
    archive = audit.get("archive_join")
    failures += int(
        not isinstance(archive, Mapping) or archive.get("method") != "left_join_on_record_id"
    )
    visit_mapping = audit.get("visit_mapping")
    sequence = audit.get("sequence_classification")
    failures += int(
        not isinstance(visit_mapping, Mapping)
        or not all(name in visit_mapping for name in ("mapped", "unknown"))
    )
    failures += int(
        not isinstance(sequence, Mapping)
        or not isinstance(sequence.get("modalities"), Mapping)
        or not isinstance(sequence.get("reasons"), Mapping)
    )
    failures += int(audit.get("site_status") != "unavailable_in_current_ppmi_export")
    return failures


def _dataset_evidence_check(
    manifest_path: Path, rows: Sequence[Mapping[str, object]]
) -> ValidationCheck:
    """Cross-check standard builder artifacts without requiring row-level source data."""
    if manifest_path.name == "hcp_manifest.json":
        failures = _hcp_evidence_failures(
            _json_mapping(manifest_path.with_name("hcp_provenance.json")),
            _json_mapping(manifest_path.with_name("hcp_audit.json")),
            rows,
        )
    elif manifest_path.name == "ppmi_manifest.json":
        failures = _ppmi_evidence_failures(
            _json_mapping(manifest_path.with_name("ppmi_provenance.json")),
            _json_mapping(manifest_path.with_name("ppmi_sequence_audit.json")),
            rows,
        )
    else:
        failures = 0
    return _check(
        "dataset_evidence",
        failures,
        "builder provenance and aggregate audits satisfy dataset checks",
    )


def validate_manifest_file(
    manifest_path: Path,
    schema_path: Path | None = None,
    *,
    repository_root: Path | None = None,
) -> ManifestValidationResult:
    """Validate one canonical JSON manifest without retaining row-level diagnostics."""
    rows, raw, json_check = _read_rows(manifest_path)
    digest = hashlib.sha256(raw).hexdigest()
    checks = (
        json_check,
        _schema_contract_check(schema_path or _DEFAULT_SCHEMA),
        _schema_check(rows),
        _unique_key_check(rows),
        _identifier_check(rows),
        _date_check(rows),
        _state_check(rows),
        _stable_serialization_check(rows, raw),
        _source_hash_check(rows),
        _contract_version_check(rows),
        _path_privacy_check(rows),
        _dataset_check(rows),
        _dataset_evidence_check(manifest_path, rows),
        _private_git_tracking_check(repository_root or _PROJECT_ROOT),
    )
    if any(check.status == "FAIL" for check in checks):
        status: ValidationStatus = "FAIL"
    elif any(check.status == "WARN" for check in checks):
        status = "PARTIAL"
    else:
        status = "PASS"
    return ManifestValidationResult(status, digest, checks)


def _write_result(result: ManifestValidationResult, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "manifest_validation_summary.json"
    output.write_bytes(canonical_json_bytes(result.as_record()) + b"\n")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a canonical metadata manifest.")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--schema", type=Path, default=_DEFAULT_SCHEMA)
    parser.add_argument("--output-dir", type=Path, default=Path("reports/data_qc/week02_04"))
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        result = validate_manifest_file(arguments.manifest, arguments.schema)
        if not arguments.dry_run:
            output = _write_result(result, arguments.output_dir)
            print(
                f"Manifest validation {result.status}: output={output.name} "
                f"sha256={result.manifest_sha256}"
            )
        else:
            print(f"Manifest validation dry-run {result.status}: sha256={result.manifest_sha256}")
    except Exception as error:  # defensive CLI boundary; never echo paths or row values
        print(f"Manifest validation failed: {type(error).__name__}", file=sys.stderr)
        return 2
    return int(result.status == "FAIL")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
