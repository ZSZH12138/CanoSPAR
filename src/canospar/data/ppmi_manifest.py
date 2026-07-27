"""Build deterministic, subject-visit PPMI imaging metadata manifests."""

from __future__ import annotations

import argparse
import hashlib
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import yaml

from canospar.data.manifest_schema import validate_manifest_row
from canospar.data.metadata_discovery import (
    DiscoveryError,
    discover_logical_inputs,
    load_logical_inputs,
)
from canospar.data.metadata_io import canonical_json_bytes, parse_iso_date, read_csv_table
from canospar.data.ppmi_sequences import (
    SequenceClassification,
    classify_sequence,
    scanner_metadata,
)
from canospar.data.provenance import manifest_provenance


class PPMIManifestError(ValueError):
    """A PPMI metadata source cannot safely produce a manifest."""


@dataclass(frozen=True)
class PPMIManifestResult:
    """In-memory PPMI outputs; audits contain aggregates, not subject lists."""

    manifest: tuple[dict[str, object], ...]
    exclusions: dict[str, object]
    audit: dict[str, object]
    provenance: dict[str, object]


_REQUIRED_MAP_FIELDS = ("subject_id", "visit", "record_id")
_OPTIONAL_MAP_FIELDS = (
    "sequence_description",
    "scan_date",
    "form_date",
    "participant_status",
    "cohort",
    "cohort_definition",
    "protocol",
    "manufacturer",
    "scanner_model",
)
_INVENTORY_MAP_FIELDS = (
    "inventory_subject_id",
    "inventory_visit",
    "inventory_description",
    "inventory_study_date",
    "inventory_protocol",
)


def _load_mapping(path: Path, name: str) -> Mapping[str, object]:
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise PPMIManifestError(f"PPMI {name} cannot be read") from error
    if not isinstance(loaded, Mapping):
        raise PPMIManifestError(f"PPMI {name} is invalid")
    return loaded


def _relative_config_path(config_path: Path, config: Mapping[str, object], key: str) -> Path:
    value = config.get(key)
    if not isinstance(value, str) or not value.strip() or Path(value).is_absolute():
        raise PPMIManifestError(f"PPMI configuration has invalid {key}")
    directory = config_path.parent.resolve()
    candidate = (directory / value).resolve()
    if not candidate.is_relative_to(directory):
        raise PPMIManifestError(f"PPMI configuration has invalid {key}")
    return candidate


def _column_map(config_path: Path, config: Mapping[str, object]) -> dict[str, str]:
    loaded = _load_mapping(_relative_config_path(config_path, config, "column_map"), "column map")
    result: dict[str, str] = {}
    for field in (*_REQUIRED_MAP_FIELDS, *_OPTIONAL_MAP_FIELDS, *_INVENTORY_MAP_FIELDS):
        value = loaded.get(field)
        if value is None and field in (*_OPTIONAL_MAP_FIELDS, *_INVENTORY_MAP_FIELDS):
            continue
        if not isinstance(value, str) or not value.strip():
            raise PPMIManifestError(f"PPMI column map is missing {field}")
        result[field] = value
    return result


def _aliases(config_path: Path, config: Mapping[str, object]) -> Mapping[str, Sequence[str]]:
    loaded = _load_mapping(_relative_config_path(config_path, config, "aliases_file"), "aliases")
    result: dict[str, Sequence[str]] = {}
    for name in (
        "smri",
        "fmri",
        "dwi",
        "exclude",
        "smri_exclude",
        "fmri_exclude",
        "dwi_exclude",
    ):
        value = loaded.get(name)
        if name.endswith("_exclude") and value is None:
            result[name] = []
            continue
        if (
            not isinstance(value, list)
            or not value
            or not all(isinstance(item, str) for item in value)
        ):
            raise PPMIManifestError(f"PPMI aliases are missing {name}")
        result[name] = value
    reverse_phase_rules = loaded.get("reverse_phase_short_rules")
    if reverse_phase_rules is not None:
        if not isinstance(reverse_phase_rules, list) or not all(
            isinstance(item, str) for item in reverse_phase_rules
        ):
            raise PPMIManifestError("PPMI aliases have invalid reverse_phase_short_rules")
        result["reverse_phase_short_rules"] = reverse_phase_rules
    return result


def _visit_map(config_path: Path, config: Mapping[str, object]) -> dict[str, frozenset[str]]:
    loaded = _load_mapping(_relative_config_path(config_path, config, "visit_map"), "visit map")
    result: dict[str, frozenset[str]] = {}
    for source, event_id in loaded.items():
        if source in {"visit_policy", "unknown_visit", "date_validation", "aliases"}:
            continue
        if (
            not isinstance(source, str)
            or not isinstance(event_id, str)
            or not source.strip()
            or not event_id.strip()
        ):
            raise PPMIManifestError("PPMI visit map is invalid")
        result[source.casefold().strip()] = frozenset({event_id.strip()})
    aliases = loaded.get("aliases", {})
    if not isinstance(aliases, Mapping):
        raise PPMIManifestError("PPMI visit map aliases are invalid")
    for source, codes in aliases.items():
        if (
            not isinstance(source, str)
            or not isinstance(codes, list)
            or not all(isinstance(code, str) and code.strip() for code in codes)
        ):
            raise PPMIManifestError("PPMI visit map aliases are invalid")
        result[source.casefold().strip()] = frozenset(code.strip() for code in codes)
    return result


def _normalize_visit_label(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _code_list_candidates(rows: Sequence[Mapping[str, str]]) -> dict[str, frozenset[str]]:
    candidates: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row.get("ITM_NAME", "").strip() != "EVENT_ID":
            continue
        code = row.get("CODE", "").strip()
        decode = row.get("DECODE", "").strip()
        if not code or not decode:
            continue
        candidates[_normalize_visit_label(decode)].add(code)
        candidates[_normalize_visit_label(code)].add(code)
    return {label: frozenset(codes) for label, codes in candidates.items()}


def _visit_candidates(
    value: str, code_list: Mapping[str, frozenset[str]], visit_map: Mapping[str, frozenset[str]]
) -> frozenset[str]:
    normalized = _normalize_visit_label(value)
    candidates = set(code_list.get(normalized, frozenset()))
    candidates.update(visit_map.get(value.casefold().strip(), frozenset()))
    return frozenset(candidates)


def _parse_audit_date(value: str, *, logical_name: str) -> date | None:
    """Validate an approved date representation; month-only dates have no day."""
    if re.fullmatch(r"(?:0[1-9]|1[0-2])/\d{4}", value):
        return None
    try:
        return parse_iso_date(value)
    except ValueError:
        try:
            return datetime.strptime(value, "%m/%d/%Y").date()
        except ValueError as error:
            raise PPMIManifestError(f"PPMI {logical_name} has invalid date") from error


def _validate_date(value: str, *, logical_name: str) -> bool:
    if not value:
        return False
    _parse_audit_date(value, logical_name=logical_name)
    return True


def _snapshot_date(config: Mapping[str, object], discovered: Mapping[str, object]) -> str:
    configured = config.get("availability_snapshot_date")
    if isinstance(configured, str):
        try:
            return parse_iso_date(configured).isoformat()
        except ValueError as error:
            raise PPMIManifestError(
                "PPMI configuration has invalid availability_snapshot_date"
            ) from error
    source_manifest = discovered.get("source_manifest")
    legacy = getattr(source_manifest, "legacy", None)
    value = legacy.get("snapshot_date") if isinstance(legacy, Mapping) else None
    if not isinstance(value, str):
        raise PPMIManifestError("PPMI configuration lacks availability_snapshot_date")
    try:
        return parse_iso_date(value).isoformat()
    except ValueError as error:
        raise PPMIManifestError("PPMI source manifest has invalid snapshot date") from error


def _inventory_record(record: Mapping[str, str], column_map: Mapping[str, str]) -> dict[str, str]:
    """Project an imaging inventory row into completion-table logical columns."""
    projected = dict(record)
    for canonical, inventory_name in (
        ("subject_id", "inventory_subject_id"),
        ("visit", "inventory_visit"),
        ("sequence_description", "inventory_description"),
        ("scan_date", "inventory_study_date"),
        ("protocol", "inventory_protocol"),
    ):
        target = column_map.get(canonical)
        source = column_map.get(inventory_name)
        if target is not None and source is not None:
            projected[target] = record.get(source, "")
    return projected


def _participant_cohorts(
    rows: Sequence[Mapping[str, str]], column_map: Mapping[str, str]
) -> dict[str, str]:
    cohorts: dict[str, str] = {}
    for row in rows:
        subject = _value(row, column_map, "subject_id")
        if not subject:
            raise PPMIManifestError("participant status has invalid subject identifiers")
        cohort = _value(row, column_map, "cohort_definition") or _value(row, column_map, "cohort")
        if subject in cohorts:
            raise PPMIManifestError("participant status has duplicate subject identifiers")
        cohorts[subject] = cohort
    return cohorts


def _value(row: Mapping[str, str], column_map: Mapping[str, str], field: str) -> str:
    column = column_map.get(field)
    return row.get(column, "").strip() if column is not None else ""


def _archive_left_join(
    current: list[dict[str, str]], archived: list[dict[str, str]], column_map: Mapping[str, str]
) -> tuple[list[dict[str, str]], dict[str, object]]:
    record_column = column_map["record_id"]
    current_counts = Counter(record.get(record_column, "").strip() for record in current)
    duplicate_current = sum(
        count for record_id, count in current_counts.items() if record_id and count > 1
    )
    if duplicate_current:
        raise PPMIManifestError("current MRI has duplicate record identifiers")
    archive_index: dict[str, dict[str, str]] = {}
    archive_counts: Counter[str] = Counter()
    for record in archived:
        record_id = record.get(record_column, "").strip()
        if not record_id:
            continue
        archive_counts[record_id] += 1
        archive_index.setdefault(record_id, record)
    duplicate_ids = {record_id for record_id, count in archive_counts.items() if count > 1}
    for record_id in duplicate_ids:
        del archive_index[record_id]
    current_ids = {record.get(record_column, "").strip() for record in current}
    enriched = 0
    conflicts: Counter[str] = Counter()
    joined: list[dict[str, str]] = []
    fields = tuple(column_map)
    for record in current:
        archive = archive_index.get(record.get(record_column, "").strip())
        effective = dict(record)
        if archive is not None:
            for field in fields:
                column = column_map[field]
                current_value = effective.get(column, "").strip()
                archived_value = archive.get(column, "").strip()
                if not current_value and archived_value:
                    effective[column] = archived_value
                    enriched += 1
                elif current_value and archived_value and current_value != archived_value:
                    conflicts[field] += 1
        joined.append(effective)
    return joined, {
        "method": "left_join_on_record_id",
        "enriched_records": enriched,
        "conflicting_fields": dict(sorted(conflicts.items())),
        "duplicate_groups": len(duplicate_ids),
        "duplicate_rows": sum(archive_counts[record_id] for record_id in duplicate_ids),
        "archived_only_record_count": len(set(archive_index).difference(current_ids)),
        "matched_record_count": len(set(archive_index).intersection(current_ids)),
    }


def _mapped_visit(value: str, visit_map: Mapping[str, str]) -> str | None:
    return visit_map.get(value.casefold().strip())


def _unknown_visit_id(subject: str, raw_visit: str, unknown_count: int) -> str:
    if unknown_count == 1:
        return "unknown"
    digest = hashlib.sha256(f"{subject}|{raw_visit}".encode()).hexdigest()[:12]
    return f"unknown_{digest}"


def _scan_dates(records: Sequence[Mapping[str, str]], column_map: Mapping[str, str]) -> str | None:
    dates = []
    for record in records:
        value = _value(record, column_map, "scan_date")
        if value:
            parsed = _parse_audit_date(value, logical_name="inventory")
            if parsed is not None:
                dates.append(parsed.isoformat())
    return min(dates) if dates else None


def _build_row(
    subject: str,
    visit_id: str,
    records: Sequence[Mapping[str, str]],
    classifications: Sequence[SequenceClassification],
    column_map: Mapping[str, str],
    source_hash: str,
    config: Mapping[str, object],
    enrollment_cohort: str | None,
) -> dict[str, object]:
    modalities = {classification.modality for classification in classifications}
    protocols = sorted(
        value
        for value in (
            _value(record, column_map, "protocol")
            or _value(record, column_map, "sequence_description")
            for record in records
        )
        if value
    )
    manufacturers = sorted(_value(record, column_map, "manufacturer") for record in records)
    models = sorted(_value(record, column_map, "scanner_model") for record in records)
    scanner = scanner_metadata(
        " | ".join(protocols),
        manufacturer=" | ".join(manufacturers),
        model=models[0] if models else "",
    )
    all_available = {"t1", "fmri", "dwi"}.issubset(modalities)
    reasons = {classification.reason for classification in classifications}
    exclusion = (
        "missing_visit_mapping"
        if visit_id.startswith("unknown")
        else "none"
        if all_available
        else "ambiguous_sequence"
        if reasons.intersection({"ambiguous", "contaminated"})
        else "not_in_source_inventory"
    )
    row = {
        "contract_version": "1.1.0",
        "dataset": "ppmi",
        "source_release": str(config.get("source_release", "ppmi-current")),
        "subject_id": subject,
        "visit_id": visit_id,
        "group_id": subject,
        "family_id": None,
        "site_id": "unknown",
        "site_available": False,
        "site_source": "unavailable_in_current_ppmi_export",
        "scanner_vendor": scanner.vendor,
        "scanner_model": scanner.model,
        "field_strength": scanner.field_strength,
        "normalized_protocol": scanner.normalized_protocol,
        "scanner_batch_id": scanner.batch_id,
        "age": None,
        "sex": None,
        "diagnosis": enrollment_cohort,
        "diagnosis_source": (
            "participant_status_enrollment_cohort" if enrollment_cohort is not None else None
        ),
        "target": None,
        "target_name": None,
        "target_date": None,
        "imaging_date": _scan_dates(records, column_map),
        "imaging_clinical_interval_days": None,
        "t1_available": "t1" in modalities,
        "t1_downloaded": False,
        "t1_preprocessed": False,
        "t1_qc_pass": None,
        "t1_path": "",
        "fmri_available": "fmri" in modalities,
        "fmri_downloaded": False,
        "fmri_preprocessed": False,
        "fmri_qc_pass": None,
        "fmri_path": "",
        "dwi_available": "dwi" in modalities,
        "dwi_downloaded": False,
        "dwi_preprocessed": False,
        "dwi_qc_pass": None,
        "dwi_path": "",
        "raw_qc_status": None,
        "exclusion_reason": exclusion,
        "availability_basis": "source_inventory",
        "availability_snapshot_date": str(config["availability_snapshot_date"]),
        "cohort_status": "provisional",
        "row_status": "included" if all_available and exclusion == "none" else "excluded",
        "source_manifest_hash": source_hash,
        "cohort_source": "not_applicable",
        "unrelated_list_version": "not_applicable",
        "kinship_control_method": "not_applicable",
    }
    return validate_manifest_row(row)


def build_ppmi_manifest(config_path: Path, metadata_root: Path) -> PPMIManifestResult:
    """Build an imaging-only manifest from current MRI completion plus archived supplements."""
    config = _load_mapping(config_path, "configuration")
    if config.get("contract_version") != "1.1.0" or config.get("cohort") != "ppmi":
        raise PPMIManifestError("PPMI configuration has an unsupported contract")
    column_map = _column_map(config_path, config)
    if "sequence_description" not in column_map and "inventory_description" in column_map:
        column_map["sequence_description"] = column_map["inventory_description"]
    if "scan_date" not in column_map and "inventory_study_date" in column_map:
        column_map["scan_date"] = column_map["inventory_study_date"]
    if "protocol" not in column_map and "inventory_protocol" in column_map:
        column_map["protocol"] = column_map["inventory_protocol"]
    if "sequence_description" not in column_map:
        raise PPMIManifestError(
            "PPMI column map lacks sequence_description or inventory_description"
        )
    aliases = _aliases(config_path, config)
    visit_map = _visit_map(config_path, config)
    try:
        discovered = discover_logical_inputs(metadata_root, load_logical_inputs(config_path))
    except (DiscoveryError, OSError, yaml.YAMLError) as error:
        raise PPMIManifestError("PPMI logical inputs cannot be resolved") from error
    resolved_config = dict(config) | {
        "availability_snapshot_date": _snapshot_date(config, discovered)
    }
    current_source = discovered.get("mri_completion")
    if current_source is None or current_source._canonical_path is None:
        raise PPMIManifestError("PPMI current MRI completion is unavailable")
    try:
        current = read_csv_table(current_source._canonical_path)
        archive_source = discovered.get("archived_mri")
        archived = (
            read_csv_table(archive_source._canonical_path)
            if archive_source is not None and archive_source._canonical_path is not None
            else []
        )
        code_list_source = discovered.get("code_list")
        code_list_rows = (
            read_csv_table(code_list_source._canonical_path)
            if code_list_source is not None and code_list_source._canonical_path is not None
            else []
        )
        participant_source = discovered.get("participant_status")
        participant_rows = (
            read_csv_table(participant_source._canonical_path)
            if participant_source is not None and participant_source._canonical_path is not None
            else []
        )
    except (OSError, ValueError) as error:
        raise PPMIManifestError("PPMI MRI input cannot be read") from error
    records, archive_audit = _archive_left_join(current, archived, column_map)
    code_list = _code_list_candidates(code_list_rows)
    participant_cohorts = _participant_cohorts(participant_rows, column_map)
    provenance = manifest_provenance(discovered)
    source_hash = str(provenance["input_manifest_hash"])
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    raw_unknowns: dict[str, set[str]] = defaultdict(set)
    current_events: dict[str, set[str]] = defaultdict(set)
    for record in records:
        subject = _value(record, column_map, "subject_id")
        if not subject:
            raise PPMIManifestError("current MRI has invalid subject identifiers")
        raw_visit = _value(record, column_map, "visit")
        candidates = _visit_candidates(raw_visit, code_list, visit_map)
        mapped = next(iter(candidates)) if len(candidates) == 1 else None
        group_visit = mapped if mapped is not None else f"<unknown>|{raw_visit}"
        if mapped is None:
            raw_unknowns[subject].add(raw_visit)
        else:
            current_events[subject].add(mapped)
        _validate_date(_value(record, column_map, "form_date"), logical_name="current MRI")
        grouped[(subject, group_visit)].append(record)
    orphan_inventory_records = 0
    inventory_record_count = 0
    visit_resolution: Counter[str] = Counter()
    for logical_name in ("t1_inventory", "rsfmri_inventory", "dti_inventory"):
        inventory_source = discovered.get(logical_name)
        if inventory_source is None or inventory_source._canonical_path is None:
            continue
        try:
            inventory = read_csv_table(inventory_source._canonical_path)
        except (OSError, ValueError) as error:
            raise PPMIManifestError("PPMI imaging inventory cannot be read") from error
        inventory_record_count += len(inventory)
        for raw_record in inventory:
            record = _inventory_record(raw_record, column_map)
            subject = _value(record, column_map, "subject_id")
            raw_visit = _value(record, column_map, "visit")
            if not subject:
                raise PPMIManifestError("PPMI imaging inventory has invalid subject identifiers")
            if _validate_date(_value(record, column_map, "scan_date"), logical_name="inventory"):
                visit_resolution["date_validated"] += 1
            candidates = _visit_candidates(raw_visit, code_list, visit_map)
            if candidates:
                visit_resolution["code_list_candidates"] += 1
            subject_candidates = candidates.intersection(current_events[subject])
            if len(subject_candidates) == 1:
                mapped = next(iter(subject_candidates))
                visit_resolution["subject_event_matched"] += 1
            elif len(subject_candidates) > 1:
                mapped = None
                visit_resolution["ambiguous"] += 1
            else:
                mapped = None
                visit_resolution["unmapped"] += 1
            group_visit = mapped if mapped is not None else f"<unknown>|{raw_visit}"
            target = (subject, group_visit)
            if mapped is None or target not in grouped:
                orphan_inventory_records += 1
                continue
            record[column_map["visit"]] = mapped
            grouped[target].append(record)
    sequence_reasons: Counter[str] = Counter()
    sequence_modalities: Counter[str] = Counter()
    rows: list[dict[str, object]] = []
    enrollment_status: Counter[str] = Counter()
    for (subject, group_visit), grouped_records in sorted(grouped.items()):
        if group_visit.startswith("<unknown>|"):
            visit_id = _unknown_visit_id(
                subject, group_visit.split("|", 1)[1], len(raw_unknowns[subject])
            )
        else:
            visit_id = group_visit
        classifications = []
        for record in grouped_records:
            sequence_text = " ".join(
                value
                for value in (
                    _value(record, column_map, "sequence_description"),
                    _value(record, column_map, "protocol"),
                )
                if value
            )
            classification = classify_sequence(sequence_text, aliases)
            classifications.append(classification)
            sequence_reasons[classification.reason] += 1
            if classification.modality is not None:
                sequence_modalities[classification.modality] += 1
        for record in grouped_records:
            cohort = _value(record, column_map, "participant_status")
            if cohort:
                enrollment_status[cohort] += 1
        rows.append(
            _build_row(
                subject,
                visit_id,
                grouped_records,
                classifications,
                column_map,
                source_hash,
                resolved_config,
                participant_cohorts.get(subject) or None,
            )
        )
    manifest = tuple(sorted(rows, key=lambda row: (str(row["subject_id"]), str(row["visit_id"]))))
    exclusions = Counter(str(row["exclusion_reason"]) for row in manifest)
    audit = {
        "status": "PARTIAL",
        "current_mri_completion_records": len(current),
        "archived_mri_records": len(archived),
        "imaging_inventory_records": inventory_record_count,
        "orphan_inventory_records": orphan_inventory_records,
        "inventory_visit_resolution": {
            name: visit_resolution[name]
            for name in (
                "code_list_candidates",
                "subject_event_matched",
                "date_validated",
                "ambiguous",
                "unmapped",
            )
        },
        "manifest_subject_visit_count": len(manifest),
        "distinct_subject_count": len({row["subject_id"] for row in manifest}),
        "trimodal_subject_visit_count": sum(
            bool(row["t1_available"] and row["fmri_available"] and row["dwi_available"])
            for row in manifest
        ),
        "archive_join": archive_audit,
        "visit_mapping": {
            "mapped": sum(not str(row["visit_id"]).startswith("unknown") for row in manifest),
            "unknown": sum(str(row["visit_id"]).startswith("unknown") for row in manifest),
        },
        "sequence_classification": {
            "modalities": dict(sorted(sequence_modalities.items())),
            "reasons": dict(sorted(sequence_reasons.items())),
        },
        "enrollment_cohort_distribution": dict(
            sorted(
                Counter(
                    str(row["diagnosis"]) for row in manifest if row["diagnosis"] is not None
                ).items()
            )
        ),
        "enrollment_status_distribution": dict(sorted(enrollment_status.items())),
        "participant_status": {
            "matched_subject_visits": sum(row["diagnosis"] is not None for row in manifest),
            "missing_subject_visits": sum(row["diagnosis"] is None for row in manifest),
        },
        "site_status": "unavailable_in_current_ppmi_export",
    }
    provenance = provenance | {
        "availability_basis": "source_inventory",
        "cohort_status": "provisional",
    }
    return PPMIManifestResult(
        manifest, {"counts": dict(sorted(exclusions.items()))}, audit, provenance
    )


def _write_json(path: Path, payload: Mapping[str, object] | Sequence[Mapping[str, object]]) -> str:
    content = canonical_json_bytes(payload) + b"\n"
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a PPMI manifest without exposing subject rows."
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--metadata-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        result = build_ppmi_manifest(arguments.config, arguments.metadata_root)
        if arguments.dry_run:
            print(f"PPMI manifest dry-run: subject-visits={len(result.manifest)}")
            return 0
        arguments.output_dir.mkdir(parents=True, exist_ok=True)
        hashes = {
            "manifest": _write_json(arguments.output_dir / "ppmi_manifest.json", result.manifest),
            "exclusions": _write_json(
                arguments.output_dir / "ppmi_exclusions.json", result.exclusions
            ),
            "sequence_audit": _write_json(
                arguments.output_dir / "ppmi_sequence_audit.json", result.audit
            ),
            "provenance": _write_json(
                arguments.output_dir / "ppmi_provenance.json", result.provenance
            ),
        }
        print(f"PPMI manifest: subject-visits={len(result.manifest)} sha256={hashes['manifest']}")
    except PPMIManifestError as error:
        print(f"PPMI manifest failed: {error}", file=__import__("sys").stderr)
        return 2
    except (OSError, ValueError):
        print("PPMI manifest failed: PPMI output cannot be written", file=__import__("sys").stderr)
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
