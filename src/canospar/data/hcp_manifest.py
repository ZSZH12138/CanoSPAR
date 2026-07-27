"""Build privacy-preserving, provisional HCP metadata manifests.

This module deliberately audits acquisition-completion metadata only.  It neither
downloads nor processes imaging, and it never treats a completion flag as proof
of a downloaded or processed package.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml

from canospar.data.manifest_schema import validate_manifest_row
from canospar.data.metadata_discovery import (
    DiscoveryError,
    discover_logical_inputs,
    load_logical_inputs,
)
from canospar.data.metadata_io import canonical_json_bytes, csv_columns, read_csv_table
from canospar.data.provenance import manifest_provenance

TARGET_COLUMNS = ("CogFluidComp_Unadj", "CogTotalComp_Unadj", "PMAT24_A_CR")
_REQUIRED_INPUTS = frozenset(
    {
        "data_dictionary",
        "unrelated_list",
        "subject_export",
        "appendix_2025",
        "access_record",
        "download_record",
        "download_manifest",
    }
)
_BOOLEAN_TOKENS = {"1": True, "true": True, "yes": True, "0": False, "false": False, "no": False}


class HCPManifestError(ValueError):
    """Raised when a logical HCP metadata input violates the protocol."""


@dataclass(frozen=True)
class HCPManifestResult:
    """In-memory outputs. Audit and provenance deliberately contain no subject IDs."""

    manifest: tuple[dict[str, object], ...]
    exclusions: dict[str, object]
    audit: dict[str, object]
    provenance: dict[str, object]


def _read_config(path: Path) -> Mapping[str, object]:
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise HCPManifestError("HCP configuration cannot be read") from error
    if not isinstance(loaded, Mapping):
        raise HCPManifestError("HCP configuration is invalid")
    return loaded


def _column_map(config_path: Path, config: Mapping[str, object]) -> Mapping[str, str]:
    relative_path = config.get("column_map")
    if not isinstance(relative_path, str) or Path(relative_path).is_absolute():
        raise HCPManifestError("HCP column map is invalid")
    try:
        loaded = yaml.safe_load((config_path.parent / relative_path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise HCPManifestError("HCP column map cannot be read") from error
    if not isinstance(loaded, Mapping):
        raise HCPManifestError("HCP column map is invalid")
    required = (
        "subject_id",
        "t1_count",
        "fmri_count",
        "dwi_complete",
        "full_mr_complete",
        "qc_issue",
        "fluid_cognition_target",
        "total_cognition_target",
        "matrix_reasoning_target",
        "age",
        "release",
        "acquisition",
    )
    result = {key: loaded.get(key) for key in required}
    if not all(isinstance(value, str) and value for value in result.values()):
        raise HCPManifestError("HCP column map is missing required fields")
    normalized = {key: str(value) for key, value in result.items()}
    dictionary_field = loaded.get("dictionary_field")
    if not isinstance(dictionary_field, str) or not dictionary_field:
        raise HCPManifestError("HCP dictionary field mapping is missing")
    normalized["dictionary_field"] = dictionary_field
    dictionary_definition = loaded.get("dictionary_definition")
    if dictionary_definition is not None:
        if not isinstance(dictionary_definition, str) or not dictionary_definition:
            raise HCPManifestError("HCP dictionary definition mapping is invalid")
        normalized["dictionary_definition"] = dictionary_definition
    return normalized


def _require_protocol_config(config: Mapping[str, object]) -> None:
    if config.get("contract_version") != "1.1.0" or config.get("cohort") != "hcp":
        raise HCPManifestError("HCP configuration has an unsupported contract")
    inputs = config.get("logical_inputs")
    if not isinstance(inputs, Mapping):
        raise HCPManifestError("HCP configuration is missing logical inputs")
    missing = sorted(_REQUIRED_INPUTS.difference(inputs))
    if missing:
        raise HCPManifestError(f"HCP configuration is missing logical input '{missing[0]}'")
    access = config.get("access")
    if not isinstance(access, Mapping) or access.get("open_access") != "approved":
        raise HCPManifestError("HCP Open Access approval is not recorded")
    if access.get("restricted_access") != "not_approved":
        raise HCPManifestError("HCP Restricted Access must be not_approved")
    for name in inputs:
        if isinstance(name, str) and "s1200" in name.casefold() and "processed" in name.casefold():
            raise HCPManifestError("HCP configuration rejects S1200 processed imaging")


def _target_selection(config: Mapping[str, object]) -> dict[str, object] | None:
    """Read an explicit task selection while retaining aggregate target auditing."""
    selection = config.get("target_selection")
    if selection is None:
        return None
    if not isinstance(selection, Mapping):
        raise HCPManifestError("HCP target selection is invalid")
    primary = selection.get("primary_target")
    secondary = selection.get("secondary_targets")
    if (
        primary != "CogFluidComp_Unadj"
        or not isinstance(secondary, list)
        or secondary != ["CogTotalComp_Unadj", "PMAT24_A_CR"]
        or selection.get("task_type") != "regression"
        or selection.get("primary_metric") != "MAE"
    ):
        raise HCPManifestError("HCP target selection is unsupported")
    return {
        "primary_target": primary,
        "secondary_targets": list(secondary),
        "task_type": "regression",
        "primary_metric": "MAE",
    }


def _read_unique_ids(path: Path, column: str, *, logical_name: str) -> set[str]:
    try:
        rows = read_csv_table(path)
    except (OSError, ValueError) as error:
        raise HCPManifestError(f"logical input '{logical_name}' cannot be read") from error
    identifiers = [row.get(column, "") for row in rows]
    if any(not isinstance(value, str) or not value.strip() for value in identifiers):
        raise HCPManifestError(f"logical input '{logical_name}' has invalid subject identifiers")
    if len(identifiers) != len(set(identifiers)):
        raise HCPManifestError(f"logical input '{logical_name}' has duplicate subject identifiers")
    return set(identifiers)


def _completion_boolean(value: str, *, logical_name: str, field: str) -> bool:
    """Accept only documented binary completion tokens; never guess unknown values."""
    token = value.strip().casefold()
    if token not in _BOOLEAN_TOKENS:
        raise HCPManifestError(f"logical input '{logical_name}' has invalid {field} completion")
    return _BOOLEAN_TOKENS[token]


def _positive(value: str, *, logical_name: str) -> bool:
    try:
        return float(value) > 0
    except (TypeError, ValueError) as error:
        raise HCPManifestError(
            f"logical input '{logical_name}' has invalid completion fields"
        ) from error


def _safe_float(value: str, *, logical_name: str) -> float | None:
    if not value.strip():
        return None
    try:
        number = float(value)
    except ValueError as error:
        raise HCPManifestError(
            f"logical input '{logical_name}' has invalid target values"
        ) from error
    return number if math.isfinite(number) else None


def _snapshot_date(config: Mapping[str, object], download_manifest_path: Path) -> str:
    """Use only an explicit recorded date; never use wall-clock time."""
    value = config.get("availability_snapshot_date")
    if value is None:
        try:
            decoded = json.loads(download_manifest_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as error:
            raise HCPManifestError("logical input 'download_manifest' cannot be read") from error
        if isinstance(decoded, list):
            records = decoded
        elif isinstance(decoded, Mapping):
            records = decoded.get("files", [])
        else:
            records = []
        if isinstance(records, list):
            dates: list[str] = []
            for record in records:
                if isinstance(record, Mapping):
                    recorded_date = record.get("downloaded_at")
                    if isinstance(recorded_date, str):
                        dates.append(recorded_date)
            value = max(dates)[:10] if dates else None
    if not isinstance(value, str):
        raise HCPManifestError("HCP input has no recorded availability snapshot date")
    try:
        from datetime import date

        date.fromisoformat(value)
    except ValueError as error:
        raise HCPManifestError(
            "HCP configuration has invalid availability_snapshot_date"
        ) from error
    return value


def _dictionary_metadata(path: Path, columns: Mapping[str, str]) -> dict[str, dict[str, str]]:
    """Read only declared dictionary metadata, never subject-level data."""
    try:
        rows = read_csv_table(path)
        headers = set(csv_columns(path))
    except (OSError, ValueError) as error:
        raise HCPManifestError("logical input 'data_dictionary' cannot be read") from error
    field_column = columns["dictionary_field"]
    if field_column not in headers:
        raise HCPManifestError("logical input 'data_dictionary' lacks mapped field column")
    definition_column = columns.get("dictionary_definition")
    if definition_column is not None and definition_column not in headers:
        raise HCPManifestError("logical input 'data_dictionary' lacks mapped definition column")
    records = {row.get(field_column, ""): row for row in rows}
    metadata: dict[str, dict[str, str]] = {}
    for target in TARGET_COLUMNS:
        record = records.get(target)
        if record is None:
            raise HCPManifestError("logical input 'data_dictionary' is missing candidate targets")
        metadata[target] = {
            "dictionary_definition": record.get(definition_column, "not_available")
            if definition_column is not None
            else "not_available",
            "data_type": "not_available",
        }
    return metadata


def _percentile(values: Sequence[float], fraction: float) -> float:
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def _target_summary(values: Sequence[float]) -> dict[str, object]:
    ordered = sorted(values)
    if not ordered:
        return {
            "non_missing": 0,
            "unique_values": 0,
            "min": None,
            "q1": None,
            "median": None,
            "q3": None,
            "max": None,
            "mean": None,
            "std": None,
            "outlier_count": 0,
        }
    q1, q3 = _percentile(ordered, 0.25), _percentile(ordered, 0.75)
    spread = q3 - q1
    return {
        "non_missing": len(ordered),
        "unique_values": len(set(ordered)),
        "min": ordered[0],
        "q1": q1,
        "median": _percentile(ordered, 0.5),
        "q3": q3,
        "max": ordered[-1],
        "mean": statistics.fmean(ordered),
        "std": statistics.stdev(ordered) if len(ordered) > 1 else 0.0,
        "outlier_count": sum(
            value < q1 - 1.5 * spread or value > q3 + 1.5 * spread for value in ordered
        ),
    }


def _write_outputs(result: HCPManifestResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payloads: tuple[tuple[str, object], ...] = (
        ("hcp_manifest.json", list(result.manifest)),
        ("hcp_exclusions.json", result.exclusions),
        ("hcp_audit.json", result.audit),
        ("hcp_provenance.json", result.provenance),
    )
    for name, payload in payloads:
        (output_dir / name).write_bytes(canonical_json_bytes(payload) + b"\n")


def build_hcp_manifest(config_path: Path, metadata_root: Path) -> HCPManifestResult:
    """Build a deterministic provisional HCP manifest without exposing row values in errors."""
    config = _read_config(config_path)
    _require_protocol_config(config)
    target_selection = _target_selection(config)
    columns = _column_map(config_path, config)
    try:
        discovered = discover_logical_inputs(metadata_root, load_logical_inputs(config_path))
    except DiscoveryError as error:
        raise HCPManifestError(str(error)) from error
    except (OSError, ValueError, yaml.YAMLError) as error:
        raise HCPManifestError("HCP metadata discovery cannot be read") from error
    try:
        subject_path = _input_path(metadata_root, config, "subject_export")
        unrelated_path = _input_path(metadata_root, config, "unrelated_list")
        dictionary_path = _input_path(metadata_root, config, "data_dictionary")
        download_manifest_path = _input_path(metadata_root, config, "download_manifest")
    except HCPManifestError:
        raise
    input_provenance = manifest_provenance(discovered)
    snapshot_date = _snapshot_date(config, download_manifest_path)
    dictionary_metadata = _dictionary_metadata(dictionary_path, columns)
    unrelated_ids = _read_unique_ids(
        unrelated_path, columns["subject_id"], logical_name="unrelated_list"
    )
    try:
        subject_rows = read_csv_table(subject_path)
        subject_columns = set(csv_columns(subject_path))
    except (OSError, ValueError) as error:
        raise HCPManifestError("logical input 'subject_export' cannot be read") from error
    target_columns = {
        TARGET_COLUMNS[0]: columns["fluid_cognition_target"],
        TARGET_COLUMNS[1]: columns["total_cognition_target"],
        TARGET_COLUMNS[2]: columns["matrix_reasoning_target"],
    }
    missing_target_columns = [
        target
        for target, source_column in target_columns.items()
        if source_column not in subject_columns
    ]
    if missing_target_columns:
        raise HCPManifestError("logical input 'subject_export' is missing target columns")
    subject_ids = [row.get(columns["subject_id"], "") for row in subject_rows]
    if any(not value.strip() for value in subject_ids) or len(subject_ids) != len(set(subject_ids)):
        raise HCPManifestError(
            "logical input 'subject_export' has invalid or duplicate subject identifiers"
        )
    candidates = [row for row in subject_rows if row[columns["subject_id"]] in unrelated_ids]
    manifest: list[dict[str, object]] = []
    full_mr_completed_count = 0
    for row in sorted(candidates, key=lambda item: item[columns["subject_id"]]):
        subject_id = row[columns["subject_id"]]
        source_release = row.get(columns["release"], "").strip()
        if not source_release:
            raise HCPManifestError("logical input 'subject_export' has missing source release")
        full_mr_completed_count += _completion_boolean(
            row.get(columns["full_mr_complete"], ""),
            logical_name="subject_export",
            field="3T_Full_MR",
        )
        manifest_row: dict[str, object] = {
            "dataset": "hcp",
            "source_release": source_release,
            "contract_version": "1.1.0",
            "subject_id": subject_id,
            "visit_id": "baseline",
            "group_id": subject_id,
            "site_id": "unknown",
            "site_available": False,
            "site_source": "not_available_open_access",
            "family_id": None,
            "scanner_vendor": None,
            "scanner_model": None,
            "field_strength": None,
            "normalized_protocol": None,
            "scanner_batch_id": None,
            "age": _safe_float(row.get(columns["age"], ""), logical_name="subject_export"),
            "sex": None,
            "diagnosis": None,
            "diagnosis_source": None,
            "target": None,
            "target_name": None,
            "target_date": None,
            "imaging_date": None,
            "imaging_clinical_interval_days": None,
            "t1_available": _positive(
                row.get(columns["t1_count"], ""), logical_name="subject_export"
            ),
            "t1_downloaded": False,
            "t1_preprocessed": False,
            "t1_qc_pass": None,
            "t1_path": "",
            "fmri_available": _positive(
                row.get(columns["fmri_count"], ""), logical_name="subject_export"
            ),
            "fmri_downloaded": False,
            "fmri_preprocessed": False,
            "fmri_qc_pass": None,
            "fmri_path": "",
            "dwi_available": _completion_boolean(
                row.get(columns["dwi_complete"], ""),
                logical_name="subject_export",
                field="3T_dMRI",
            ),
            "dwi_downloaded": False,
            "dwi_preprocessed": False,
            "dwi_qc_pass": None,
            "dwi_path": "",
            "raw_qc_status": row.get(columns["qc_issue"], "") or None,
            "exclusion_reason": "none",
            "availability_basis": "acquisition_completion_fields",
            "availability_snapshot_date": snapshot_date,
            "cohort_source": "hcp_official_unrelated",
            "unrelated_list_version": "S900",
            "kinship_control_method": "official_unrelated_cohort",
            "cohort_status": "provisional",
            "row_status": "provisional",
            "source_manifest_hash": input_provenance["input_manifest_hash"],
        }
        manifest.append(validate_manifest_row(manifest_row))
    target_audit: dict[str, object] = {}
    candidate_ids = {row[columns["subject_id"]] for row in candidates}
    tri_modal_ids = {
        row["subject_id"]
        for row in manifest
        if bool(row["t1_available"]) and bool(row["fmri_available"]) and bool(row["dwi_available"])
    }
    for target, source_column in target_columns.items():
        all_values = [
            _safe_float(row.get(source_column, ""), logical_name="subject_export")
            for row in subject_rows
        ]
        unrelated_values = [
            _safe_float(row.get(source_column, ""), logical_name="subject_export")
            for row in subject_rows
            if row[columns["subject_id"]] in candidate_ids
        ]
        tri_modal_values = [
            _safe_float(row.get(source_column, ""), logical_name="subject_export")
            for row in subject_rows
            if row[columns["subject_id"]] in tri_modal_ids
        ]
        present = [value for value in all_values if value is not None]
        summary = _target_summary(present)
        target_rows = [
            row
            for row in subject_rows
            if _safe_float(row.get(source_column, ""), logical_name="subject_export") is not None
        ]
        target_audit[target] = {
            **summary,
            **dictionary_metadata[target],
            "open_access": True,
            "unrelated_non_missing": sum(value is not None for value in unrelated_values),
            "provisional_trimodal_non_missing": sum(
                value is not None for value in tri_modal_values
            ),
            "missing_rate": 1 - len(present) / len(subject_rows) if subject_rows else None,
            "age_coverage": {
                "non_missing": sum(
                    _safe_float(row.get(columns["age"], ""), logical_name="subject_export")
                    is not None
                    for row in target_rows
                ),
                "total": len(target_rows),
                "available": columns["age"] in subject_columns,
            },
            "sex_coverage": {"non_missing": 0, "total": len(target_rows), "available": False},
            "qc_issue_distribution": {
                value: sum(
                    (row.get(columns["qc_issue"], "") or "none") == value for row in target_rows
                )
                for value in sorted(
                    {row.get(columns["qc_issue"], "") or "none" for row in target_rows}
                )
            },
        }
    exclusions: dict[str, object] = {
        "not_in_official_unrelated_whitelist": len(subject_rows) - len(candidates),
        "input_subject_count": len(subject_rows),
        "candidate_subject_count": len(candidates),
    }
    audit: dict[str, object] = {
        "status": "READY_FOR_USER_SELECTED_TASK"
        if target_selection is not None
        else "TARGET_CONFIRMATION_REQUIRED",
        "primary_target": target_selection["primary_target"] if target_selection else None,
        "secondary_targets": target_selection["secondary_targets"] if target_selection else [],
        "task_type": target_selection["task_type"] if target_selection else None,
        "primary_metric": target_selection["primary_metric"] if target_selection else None,
        "target_selection": "configured" if target_selection else "not_automatic",
        "full_mr_audit": {"completed_count": full_mr_completed_count},
        "qc_issue_audit": {
            "soft_marker_count": sum(bool(row.get(columns["qc_issue"], "")) for row in candidates),
        },
        "targets": target_audit,
    }
    provenance = {
        **input_provenance,
        "cohort_status": "provisional",
        "availability_basis": "acquisition_completion_fields",
        "access_tier": "Open Access",
        "restricted_access": "not_approved",
        "unrelated_list_version": "S900",
        "processed_package_inventory": "not_available",
    }
    return HCPManifestResult(tuple(manifest), exclusions, audit, provenance)


def _input_path(metadata_root: Path, config: Mapping[str, object], logical_name: str) -> Path:
    """Resolve the same safe, deterministic configured source as discovery."""
    inputs = config.get("logical_inputs")
    if not isinstance(inputs, Mapping) or not isinstance(inputs.get(logical_name), Mapping):
        raise HCPManifestError(f"HCP configuration is missing logical input '{logical_name}'")
    patterns = inputs[logical_name].get("patterns")
    if (
        not isinstance(patterns, list)
        or not patterns
        or not all(isinstance(item, str) for item in patterns)
    ):
        raise HCPManifestError(f"logical input '{logical_name}' has invalid patterns")
    root = metadata_root.resolve()
    candidates = {
        path.resolve()
        for pattern in patterns
        for path in root.glob(pattern)
        if path.is_file() and path.resolve().is_relative_to(root)
    }
    candidates = {
        path
        for path in candidates
        if not any(
            part.casefold() in {"archive", "archived", "legacy"}
            for part in path.relative_to(root).parts
        )
    }
    if not candidates:
        raise HCPManifestError(f"logical input '{logical_name}' is missing")
    definition = inputs[logical_name]
    selection = definition.get("selection", "exact")
    ordered = sorted(candidates, key=lambda path: path.relative_to(root).as_posix())
    if selection == "latest":
        return sorted(ordered, key=lambda path: (path.name, path.as_posix()))[-1]
    if selection in (None, "exact") and len(ordered) == 1:
        return ordered[0]
    raise HCPManifestError(f"logical input '{logical_name}' is ambiguous")


def main(argv: list[str] | None = None) -> int:
    """Run the manifest builder with console output containing no subject-level data."""
    parser = argparse.ArgumentParser(description="Build a provisional HCP metadata manifest.")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--metadata-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        result = build_hcp_manifest(arguments.config, arguments.metadata_root)
        if not arguments.dry_run:
            _write_outputs(result, arguments.output_dir)
        action = "validated" if arguments.dry_run else "written"
        print(f"HCP manifest {action}: {len(result.manifest)} candidates")
    except HCPManifestError as error:
        print(f"HCP manifest failed: {error}", file=__import__("sys").stderr)
        return 2
    except OSError:
        print("HCP manifest failed: HCP output cannot be written", file=__import__("sys").stderr)
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
