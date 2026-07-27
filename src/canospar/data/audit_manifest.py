"""Aggregate-only HCP and PPMI manifest audits."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeAlias

from canospar.data.metadata_discovery import (
    discover_logical_inputs,
    load_logical_inputs,
    load_ppmi_target_config,
)
from canospar.data.metadata_io import canonical_json_bytes, read_csv_table
from canospar.data.ppmi_targets import audit_ppmi_targets
from canospar.data.validate_manifest import ValidationCheck, validate_manifest_file

AuditStatus: TypeAlias = Literal["PASS", "PARTIAL", "FAIL"]


@dataclass(frozen=True)
class ManifestAuditResult:
    """Serializable audit containing aggregate values only."""

    status: AuditStatus
    dataset: str
    manifest_sha256: str
    checks: tuple[ValidationCheck, ...]
    summary: Mapping[str, object]

    def as_record(self) -> dict[str, object]:
        return {
            "status": self.status,
            "dataset": self.dataset,
            "manifest_sha256": self.manifest_sha256,
            "checks": [check.as_record() for check in self.checks],
            "summary": dict(self.summary),
        }


def _load_rows(path: Path) -> list[Mapping[str, object]]:
    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    if not isinstance(decoded, list):
        return []
    return [row for row in decoded if isinstance(row, Mapping)]


def _counter(rows: Sequence[Mapping[str, object]], field: str) -> dict[str, int]:
    values = Counter("null" if row.get(field) is None else str(row.get(field)) for row in rows)
    return dict(sorted(values.items()))


def _interval_summary(rows: Sequence[Mapping[str, object]]) -> dict[str, float | int | None]:
    values = [
        float(value)
        for row in rows
        if isinstance(value := row.get("imaging_clinical_interval_days"), int | float)
        and not isinstance(value, bool)
        and math.isfinite(value)
    ]
    if not values:
        return {"count": 0, "min": None, "median": None, "max": None}
    return {
        "count": len(values),
        "min": min(values),
        "median": statistics.median(values),
        "max": max(values),
    }


def _base_summary(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    keys = [(row.get("subject_id"), row.get("visit_id")) for row in rows]
    modality_counts = {
        modality: sum(row.get(f"{modality}_available") is True for row in rows)
        for modality in ("dwi", "fmri", "t1")
    }
    return {
        "row_count": len(rows),
        "distinct_subject_count": len({row.get("subject_id") for row in rows}),
        "distinct_visit_count": len({row.get("visit_id") for row in rows}),
        "duplicate_subject_visit_count": len(keys) - len(set(keys)),
        "trimodal_subject_visit_count": sum(
            all(row.get(f"{modality}_available") is True for modality in ("t1", "fmri", "dwi"))
            for row in rows
        ),
        "modality_available_counts": modality_counts,
        "row_status_distribution": _counter(rows, "row_status"),
        "exclusion_reason_distribution": _counter(rows, "exclusion_reason"),
        "availability_basis_distribution": _counter(rows, "availability_basis"),
        "source_manifest_hash_count": len({row.get("source_manifest_hash") for row in rows}),
        "imaging_clinical_interval_days": _interval_summary(rows),
    }


def _hcp_summary(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    return {
        "provisional_subject_count": sum(row.get("cohort_status") == "provisional" for row in rows),
        "qc_issue_count": sum(bool(row.get("raw_qc_status")) for row in rows),
        "target_non_missing_count": sum(row.get("target") is not None for row in rows),
        "family_id_non_missing_count": sum(row.get("family_id") is not None for row in rows),
        "unrelated_source_distribution": _counter(rows, "cohort_source"),
    }


def _ppmi_summary(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    return {
        "visit_distribution": _counter(rows, "visit_id"),
        "enrollment_cohort_distribution": _counter(rows, "diagnosis"),
        "scanner_vendor_distribution": _counter(rows, "scanner_vendor"),
        "field_strength_distribution": _counter(rows, "field_strength"),
        "normalized_protocol_distribution": _counter(rows, "normalized_protocol"),
        "scanner_batch_distribution": _counter(rows, "scanner_batch_id"),
        "site_id_distribution": _counter(rows, "site_id"),
        "site_metadata_status": (
            "unavailable_in_current_ppmi_export"
            if all(
                row.get("site_id") == "unknown" and row.get("site_available") is False
                for row in rows
            )
            else "invalid"
        ),
    }


def audit_manifest_file(manifest_path: Path, dataset: str) -> ManifestAuditResult:
    """Audit one manifest while retaining no row identifiers."""
    validation = validate_manifest_file(manifest_path)
    rows = _load_rows(manifest_path)
    dataset_mismatch = sum(row.get("dataset") != dataset for row in rows)
    checks = validation.checks + (
        ValidationCheck(
            "requested_dataset",
            "FAIL" if dataset_mismatch or dataset not in {"hcp", "ppmi"} else "PASS",
            dataset_mismatch,
            "manifest rows match the requested dataset",
        ),
    )
    summary = _base_summary(rows)
    summary.update(_hcp_summary(rows) if dataset == "hcp" else _ppmi_summary(rows))
    if any(check.status == "FAIL" for check in checks):
        status: AuditStatus = "FAIL"
    elif any(check.status == "WARN" for check in checks):
        status = "PARTIAL"
    else:
        status = "PASS"
    digest = (
        hashlib.sha256(manifest_path.read_bytes()).hexdigest() if manifest_path.exists() else ""
    )
    return ManifestAuditResult(status, dataset, digest, checks, summary)


def _write_audit(result: ManifestAuditResult, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{result.dataset}_initial_audit.json"
    path.write_bytes(canonical_json_bytes(result.as_record()) + b"\n")
    return path


def audit_ppmi_target_sources(
    manifest_path: Path,
    config_path: Path,
    metadata_root: Path,
) -> dict[str, object]:
    """Run the config-driven PPMI target audit using read-only logical sources."""
    target_config = load_ppmi_target_config(config_path)
    discovered = discover_logical_inputs(metadata_root, load_logical_inputs(config_path))

    def rows(logical_name: str) -> list[dict[str, str]]:
        source = discovered.get(logical_name)
        if source is None or source._canonical_path is None:
            raise ValueError(f"logical input '{logical_name}' is unavailable")
        return read_csv_table(source._canonical_path)

    clinical = {
        logical_name: rows(logical_name)
        for logical_name in (
            "mds_updrs_part_i_clinician",
            "mds_updrs_part_i_patient",
            "mds_updrs_part_ii_patient",
            "mds_updrs_part_iii_motor",
        )
    }
    result = audit_ppmi_targets(
        clinical,
        rows("data_dictionary"),
        target_config,
        _load_rows(manifest_path),
        rows("code_list"),
    )
    return {"audit": result.audit, "branches": result.branches}


def _write_ppmi_target_audit(payload: Mapping[str, object], output_dir: Path) -> None:
    branches = payload.get("branches")
    audit = payload.get("audit")
    if not isinstance(branches, Mapping) or not isinstance(audit, Mapping):
        raise ValueError("PPMI target audit payload is invalid")
    gates: dict[str, dict[str, object]] = {}
    for candidate, policies in branches.items():
        if not isinstance(candidate, str) or not isinstance(policies, Mapping):
            raise ValueError("PPMI target audit branches are invalid")
        gates[candidate] = {}
        for policy, horizons in policies.items():
            if not isinstance(policy, str) or not isinstance(horizons, Mapping):
                raise ValueError("PPMI target audit branches are invalid")
            month24 = horizons.get("24")
            if not isinstance(month24, Mapping) or not isinstance(
                task_gate := month24.get("task_gate"), Mapping
            ):
                raise ValueError("PPMI target audit has no 24-month task gate")
            gates[candidate][policy] = dict(task_gate)
    target_path = output_dir / "ppmi_target_candidate_audit.json"
    gate_path = output_dir / "ppmi_task_gate.json"
    target_path.write_bytes(canonical_json_bytes(payload) + b"\n")
    gate_path.write_bytes(
        canonical_json_bytes(
            {
                "status": audit.get("status"),
                "basis_horizon": "24",
                "primary_target": audit.get("primary_target"),
                "target_definition": audit.get("target_definition"),
                "primary_policy": audit.get("primary_policy"),
                "secondary_targets": audit.get("secondary_targets"),
                "sensitivity_policies": audit.get("sensitivity_policies"),
                "branches": gates,
            }
        )
        + b"\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create an aggregate manifest audit.")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--dataset", required=True, choices=("hcp", "ppmi"))
    parser.add_argument("--output-dir", type=Path, default=Path("reports/data_qc/week02_04"))
    parser.add_argument("--config", type=Path)
    parser.add_argument("--metadata-root", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        target_requested = arguments.config is not None or arguments.metadata_root is not None
        if target_requested and (
            arguments.dataset != "ppmi"
            or arguments.config is None
            or arguments.metadata_root is None
        ):
            raise ValueError("PPMI target audit requires config and metadata root")
        result = audit_manifest_file(arguments.manifest, arguments.dataset)
        target_payload = (
            audit_ppmi_target_sources(arguments.manifest, arguments.config, arguments.metadata_root)
            if target_requested
            and arguments.config is not None
            and arguments.metadata_root is not None
            else None
        )
        if arguments.dry_run:
            print(
                f"{arguments.dataset.upper()} audit dry-run {result.status}: "
                f"rows={result.summary['row_count']}"
            )
        else:
            output = _write_audit(result, arguments.output_dir)
            if target_payload is not None:
                _write_ppmi_target_audit(target_payload, arguments.output_dir)
            print(
                f"{arguments.dataset.upper()} audit {result.status}: "
                f"output={output.name} sha256={result.manifest_sha256}"
            )
    except Exception as error:  # defensive CLI boundary
        print(f"Manifest audit failed: {type(error).__name__}", file=sys.stderr)
        return 2
    return int(result.status == "FAIL")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
