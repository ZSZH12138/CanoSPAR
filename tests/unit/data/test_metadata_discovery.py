"""Synthetic tests for privacy-preserving metadata discovery."""

from __future__ import annotations

import csv
import json
from hashlib import sha256
from pathlib import Path

import pytest
import yaml

from canospar.data.metadata_discovery import (
    DiscoveredInput,
    DiscoveryError,
    discover_logical_inputs,
    load_logical_inputs,
    load_ppmi_target_config,
    main,
    resolve_path_map_sources,
    resolve_recorded_sources,
)
from canospar.data.provenance import manifest_provenance


def _write_csv(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def test_discovers_current_file_and_preserves_string_identifiers(tmp_path: Path) -> None:
    root = tmp_path / "metadata"
    _write_csv(root / "current" / "subjects.csv", ["Subject", "Date"], [["0007", "2026-01-03"]])

    found = discover_logical_inputs(
        root,
        {
            "subject_export": {
                "patterns": ["current/*.csv"],
                "required_columns": ["Subject", "Date"],
            }
        },
    )

    assert found["subject_export"].relative_path == "current/<file>.csv"
    assert found["subject_export"].sha256


def test_selects_latest_non_archive_file_deterministically(tmp_path: Path) -> None:
    root = tmp_path / "metadata"
    _write_csv(root / "exports" / "table_2025.csv", ["id"], [["001"]])
    _write_csv(root / "exports" / "table_2026.csv", ["id"], [["002"]])
    _write_csv(root / "archive" / "table_2099.csv", ["id"], [["003"]])

    found = discover_logical_inputs(
        root,
        {
            "inventory": {
                "patterns": ["**/table_*.csv"],
                "selection": "latest",
                "required_columns": ["id"],
            }
        },
    )

    assert found["inventory"].relative_path == "exports/<file>.csv"


def test_rejects_incomplete_inventory_and_ambiguous_current_input(tmp_path: Path) -> None:
    root = tmp_path / "metadata"
    _write_csv(root / "one.csv", ["wrong"], [["x"]])
    _write_csv(root / "two.csv", ["id"], [["x"]])

    with pytest.raises(DiscoveryError, match="logical source 'required_export'.*missing columns"):
        discover_logical_inputs(
            root, {"required_export": {"patterns": ["one.csv"], "required_columns": ["id"]}}
        )
    with pytest.raises(DiscoveryError, match="logical source 'ambiguous_export'.*ambiguous"):
        discover_logical_inputs(root, {"ambiguous_export": {"patterns": ["*.csv"]}})


def test_rejects_hash_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "metadata"
    _write_csv(root / "current" / "download.csv", ["id"], [["001"]])

    with pytest.raises(DiscoveryError, match="logical source 'download'.*SHA-256"):
        discover_logical_inputs(
            root, {"download": {"patterns": ["current/download.csv"], "sha256": "0" * 64}}
        )


def test_resolves_historical_manifest_path_under_root_and_verifies_recorded_hash(
    tmp_path: Path,
) -> None:
    root = tmp_path / "metadata"
    payload = root / "current" / "payload.csv"
    _write_csv(payload, ["id"], [["001"]])
    digest = sha256(payload.read_bytes()).hexdigest()
    manifest = root / "records" / "download_manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            {
                "files": [
                    {
                        "logical_name": "subject_export",
                        "local_path": "C:/stale/payload.csv",
                        "sha256": digest,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    found = resolve_recorded_sources(
        root,
        manifest,
        {
            "records_key": "files",
            "logical_name_key": "logical_name",
            "stale_path_key": "local_path",
            "sha256_key": "sha256",
        },
    )

    assert found["subject_export"].relative_path == "current/<file>.csv"
    assert found["subject_export"].sha256 == digest


def test_resolves_root_confined_path_map_sources_against_source_manifest(
    tmp_path: Path,
) -> None:
    root = tmp_path / "metadata"
    table = root / "tables" / "current.csv"
    _write_csv(table, ["PATNO", "EVENT_ID"], [["001", "BL"]])
    digest = sha256(table.read_bytes()).hexdigest()
    path_map = root / "records" / "path_map.json"
    source_manifest = root / "records" / "source_manifest.json"
    path_map.parent.mkdir(parents=True)
    path_map.write_text(
        json.dumps(
            {
                "participant_status": "tables/current.csv",
                "ppmi_metadata_root_env": "C:/stale",
            }
        ),
        encoding="utf-8",
    )
    source_manifest.write_text(
        json.dumps(
            {
                "snapshot_date": "2026-07-26",
                "files": [
                    {
                        "canonical_relative_path": "tables/current.csv",
                        "sha256": digest,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    resolution = resolve_path_map_sources(
        root,
        path_map,
        source_manifest,
        {
            "path_map_keys": {"participant_status": "participant_status"},
            "records_key": "files",
            "canonical_path_key": "canonical_relative_path",
            "sha256_key": "sha256",
            "snapshot_date_key": "snapshot_date",
            "allowed_metadata_keys": ["ppmi_metadata_root_env"],
        },
    )

    assert resolution.snapshot_date == "2026-07-26"
    assert resolution.sources["participant_status"].relative_path == "tables/<file>.csv"
    assert resolution.sources["participant_status"].sha256 == digest


def test_rejects_unknown_path_map_source_manifest_record_without_disclosing_path(
    tmp_path: Path,
) -> None:
    root = tmp_path / "metadata"
    root.mkdir()
    path_map = root / "path_map.json"
    source_manifest = root / "source_manifest.json"
    path_map.write_text(json.dumps({"participant_status": "tables/current.csv"}), encoding="utf-8")
    source_manifest.write_text(
        json.dumps(
            {
                "snapshot_date": "2026-07-26",
                "files": [
                    {"canonical_relative_path": "tables/not_disclosed.csv", "sha256": "0" * 64}
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        DiscoveryError, match="source manifest has unknown path-map record"
    ) as error:
        resolve_path_map_sources(
            root,
            path_map,
            source_manifest,
            {
                "path_map_keys": {"participant_status": "participant_status"},
                "records_key": "files",
                "canonical_path_key": "canonical_relative_path",
                "sha256_key": "sha256",
                "snapshot_date_key": "snapshot_date",
            },
        )
    assert "not_disclosed.csv" not in str(error.value)


def test_resolves_declared_archive_only_dictionary_as_aggregate_provenance(
    tmp_path: Path,
) -> None:
    root = tmp_path / "metadata"
    current = root / "clinical" / "status.csv"
    archive = root / "guidance" / "archive" / "ppmi_data_dictionary_2024.csv"
    _write_csv(current, ["PATNO"], [["001"]])
    _write_csv(archive, ["field"], [["synthetic"]])
    current_digest = sha256(current.read_bytes()).hexdigest()
    archive_digest = sha256(archive.read_bytes()).hexdigest()
    path_map = root / "records" / "path_map.json"
    source_manifest = root / "records" / "source_manifest.json"
    path_map.parent.mkdir(parents=True)
    path_map.write_text(json.dumps({"participant_status": "clinical/status.csv"}), encoding="utf-8")
    source_manifest.write_text(
        json.dumps(
            {
                "snapshot_date": "2026-07-26",
                "files": [
                    {"canonical_relative_path": "clinical/status.csv", "sha256": current_digest},
                    {
                        "canonical_relative_path": "guidance/archive/ppmi_data_dictionary_2024.csv",
                        "sha256": archive_digest,
                        "role": "Historical dictionary retained only for compatibility comparison",
                        "status": "archive_only",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    resolution = resolve_path_map_sources(
        root,
        path_map,
        source_manifest,
        {
            "path_map_keys": {"participant_status": "participant_status"},
            "records_key": "files",
            "canonical_path_key": "canonical_relative_path",
            "sha256_key": "sha256",
            "snapshot_date_key": "snapshot_date",
            "allowed_unmapped_records": [
                {
                    "logical_name": "archived_data_dictionary",
                    "canonical_pattern": "guidance/archive/ppmi_data_dictionary_*.csv",
                    "required_status": "archive_only",
                    "required_role": (
                        "Historical dictionary retained only for compatibility comparison"
                    ),
                }
            ],
        },
    )

    archive_record = resolution.sources["archived_data_dictionary"]
    assert archive_record.relative_path is None
    assert archive_record.sha256 is None
    assert archive_record._canonical_path is None
    assert archive_record.legacy == {
        "status": "archive_only",
        "count": 1,
        "content_hash": archive_digest,
    }


@pytest.mark.parametrize("failure", ["non_archive", "status", "hash", "multiple"])
def test_rejects_invalid_declared_archive_only_dictionary_without_disclosing_path(
    tmp_path: Path, failure: str
) -> None:
    root = tmp_path / "metadata"
    current = root / "clinical" / "status.csv"
    _write_csv(current, ["PATNO"], [["001"]])
    current_digest = sha256(current.read_bytes()).hexdigest()
    archive_paths = [root / "guidance" / "archive" / "ppmi_data_dictionary_2024.csv"]
    if failure == "multiple":
        archive_paths.append(root / "guidance" / "archive" / "ppmi_data_dictionary_2025.csv")
    if failure == "non_archive":
        archive_paths = [root / "guidance" / "ppmi_data_dictionary_2024.csv"]
    for archive_path in archive_paths:
        _write_csv(archive_path, ["field"], [["synthetic"]])
    path_map = root / "records" / "path_map.json"
    source_manifest = root / "records" / "source_manifest.json"
    path_map.parent.mkdir(parents=True)
    path_map.write_text(json.dumps({"participant_status": "clinical/status.csv"}), encoding="utf-8")
    records: list[dict[str, str]] = [
        {"canonical_relative_path": "clinical/status.csv", "sha256": current_digest}
    ]
    for archive_path in archive_paths:
        canonical = archive_path.relative_to(root).as_posix()
        records.append(
            {
                "canonical_relative_path": canonical,
                "sha256": "0" * 64
                if failure == "hash"
                else sha256(archive_path.read_bytes()).hexdigest(),
                "role": "Historical dictionary retained only for compatibility comparison",
                "status": "current" if failure == "status" else "archive_only",
            }
        )
    source_manifest.write_text(
        json.dumps({"snapshot_date": "2026-07-26", "files": records}), encoding="utf-8"
    )
    specification = {
        "path_map_keys": {"participant_status": "participant_status"},
        "records_key": "files",
        "canonical_path_key": "canonical_relative_path",
        "sha256_key": "sha256",
        "snapshot_date_key": "snapshot_date",
        "allowed_unmapped_records": [
            {
                "logical_name": "archived_data_dictionary",
                "canonical_pattern": "guidance/archive/ppmi_data_dictionary_*.csv",
                "required_status": "archive_only",
                "required_role": "Historical dictionary retained only for compatibility comparison",
            }
        ],
    }

    with pytest.raises(DiscoveryError) as error:
        resolve_path_map_sources(root, path_map, source_manifest, specification)
    assert "ppmi_data_dictionary" not in str(error.value)


def test_discovers_deferred_path_map_logical_inputs_with_declared_columns(tmp_path: Path) -> None:
    root = tmp_path / "metadata"
    base = root / "ppmi_metadata"
    table = base / "tables" / "status.csv"
    archive = base / "guidance" / "archive" / "ppmi_data_dictionary_2024.csv"
    _write_csv(table, ["PATNO", "COHORT"], [["001", "PD"]])
    _write_csv(archive, ["field"], [["synthetic"]])
    digest = sha256(table.read_bytes()).hexdigest()
    archive_digest = sha256(archive.read_bytes()).hexdigest()
    path_map = base / "records" / "path_map.json"
    source_manifest = base / "records" / "source_manifest.json"
    path_map.parent.mkdir(parents=True)
    path_map.write_text(
        json.dumps(
            {
                "participant_status": "tables/status.csv",
                "ppmi_metadata_root_env": "C:/untrusted-historical-root",
            }
        ),
        encoding="utf-8",
    )
    source_manifest.write_text(
        json.dumps(
            {
                "root": "C:/untrusted-historical-root",
                "snapshot_date": "2026-07-26",
                "files": [
                    {"canonical_relative_path": "tables/status.csv", "sha256": digest},
                    {
                        "canonical_relative_path": "guidance/archive/ppmi_data_dictionary_2024.csv",
                        "sha256": archive_digest,
                        "role": "Historical dictionary retained only for compatibility comparison",
                        "status": "archive_only",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    found = discover_logical_inputs(
        root,
        {
            "path_map": {
                "patterns": ["ppmi_metadata/records/path_map.json"],
                "path_map_resolution": {
                    "base_directory": "ppmi_metadata",
                    "source_manifest_logical_name": "source_manifest",
                    "path_map_keys": {"participant_status": "participant_status"},
                    "records_key": "files",
                    "canonical_path_key": "canonical_relative_path",
                    "sha256_key": "sha256",
                    "snapshot_date_key": "snapshot_date",
                    "allowed_metadata_keys": ["ppmi_metadata_root_env"],
                    "allowed_unmapped_records": [
                        {
                            "logical_name": "archived_data_dictionary",
                            "canonical_pattern": "guidance/archive/ppmi_data_dictionary_*.csv",
                            "required_status": "archive_only",
                            "required_role": (
                                "Historical dictionary retained only for compatibility comparison"
                            ),
                        }
                    ],
                },
            },
            "source_manifest": {"patterns": ["ppmi_metadata/records/source_manifest.json"]},
            "participant_status": {"required_columns": ["PATNO", "COHORT"]},
            "archived_data_dictionary": {"archive_only": True},
        },
    )

    assert found["participant_status"].relative_path == "ppmi_metadata/tables/<file>.csv"
    assert found["participant_status"].sha256 == digest
    assert found["source_manifest"].legacy == {
        "status": "source_manifest",
        "snapshot_date": "2026-07-26",
    }
    assert found["archived_data_dictionary"].legacy == {
        "status": "archive_only",
        "count": 1,
        "content_hash": archive_digest,
    }


def test_rejects_path_map_value_that_escapes_configured_base_directory(tmp_path: Path) -> None:
    root = tmp_path / "metadata"
    base = root / "ppmi_metadata"
    table = root / "outside.csv"
    _write_csv(table, ["PATNO"], [["001"]])
    digest = sha256(table.read_bytes()).hexdigest()
    path_map = base / "records" / "path_map.json"
    source_manifest = base / "records" / "source_manifest.json"
    path_map.parent.mkdir(parents=True)
    escaped_path = "clinical/../../outside.csv"
    path_map.write_text(json.dumps({"participant_status": escaped_path}), encoding="utf-8")
    source_manifest.write_text(
        json.dumps(
            {
                "snapshot_date": "2026-07-26",
                "files": [{"canonical_relative_path": escaped_path, "sha256": digest}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(DiscoveryError, match="path map has invalid relative path"):
        resolve_path_map_sources(
            root,
            path_map,
            source_manifest,
            {
                "base_directory": "ppmi_metadata",
                "path_map_keys": {"participant_status": "participant_status"},
                "records_key": "files",
                "canonical_path_key": "canonical_relative_path",
                "sha256_key": "sha256",
                "snapshot_date_key": "snapshot_date",
            },
        )


def test_rejects_unapproved_path_map_metadata_key_without_disclosing_it(tmp_path: Path) -> None:
    root = tmp_path / "metadata"
    table = root / "tables" / "status.csv"
    _write_csv(table, ["PATNO"], [["001"]])
    digest = sha256(table.read_bytes()).hexdigest()
    path_map = root / "records" / "path_map.json"
    source_manifest = root / "records" / "source_manifest.json"
    path_map.parent.mkdir(parents=True)
    path_map.write_text(
        json.dumps(
            {
                "participant_status": "tables/status.csv",
                "not_approved": "C:/untrusted-historical-root",
            }
        ),
        encoding="utf-8",
    )
    source_manifest.write_text(
        json.dumps(
            {
                "snapshot_date": "2026-07-26",
                "files": [{"canonical_relative_path": "tables/status.csv", "sha256": digest}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(DiscoveryError, match="path map has unapproved key") as error:
        resolve_path_map_sources(
            root,
            path_map,
            source_manifest,
            {
                "path_map_keys": {"participant_status": "participant_status"},
                "allowed_metadata_keys": ["ppmi_metadata_root_env"],
                "records_key": "files",
                "canonical_path_key": "canonical_relative_path",
                "sha256_key": "sha256",
                "snapshot_date_key": "snapshot_date",
            },
        )
    assert "not_approved" not in str(error.value)


def test_rejects_ppmi_subdirectory_as_metadata_root(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[3]
    logical_inputs = load_logical_inputs(project_root / "configs" / "data" / "ppmi.yaml")
    ppmi_subdirectory = tmp_path / "ppmi_metadata"
    ppmi_subdirectory.mkdir()

    with pytest.raises(DiscoveryError, match="logical source 'path_map' is missing"):
        discover_logical_inputs(ppmi_subdirectory, logical_inputs)


def test_rejects_path_map_logical_name_missing_from_configuration(tmp_path: Path) -> None:
    with pytest.raises(DiscoveryError, match="path-map source configuration is invalid"):
        discover_logical_inputs(
            tmp_path,
            {
                "path_map": {
                    "patterns": ["records/path_map.json"],
                    "path_map_resolution": {"path_map_keys": {"not_configured": "not_configured"}},
                }
            },
        )


@pytest.mark.parametrize("failure", ["duplicate", "missing", "mismatch"])
def test_rejects_invalid_path_map_manifest_join_without_disclosing_paths(
    tmp_path: Path, failure: str
) -> None:
    root = tmp_path / "metadata"
    table = root / "tables" / "not_disclosed.csv"
    _write_csv(table, ["PATNO"], [["001"]])
    digest = sha256(table.read_bytes()).hexdigest()
    path_map = root / "records" / "path_map.json"
    source_manifest = root / "records" / "source_manifest.json"
    path_map.parent.mkdir(parents=True)
    path_map.write_text(
        json.dumps({"participant_status": "tables/not_disclosed.csv"}), encoding="utf-8"
    )
    record = {"canonical_relative_path": "tables/not_disclosed.csv", "sha256": digest}
    records = {
        "duplicate": [record, record],
        "missing": [],
        "mismatch": [record | {"sha256": "0" * 64}],
    }[failure]
    source_manifest.write_text(
        json.dumps({"snapshot_date": "2026-07-26", "files": records}), encoding="utf-8"
    )
    expected_message = {
        "duplicate": "duplicate",
        "missing": "missing path-map",
        "mismatch": "SHA-256",
    }[failure]

    with pytest.raises(DiscoveryError, match=expected_message) as error:
        resolve_path_map_sources(
            root,
            path_map,
            source_manifest,
            {
                "path_map_keys": {"participant_status": "participant_status"},
                "records_key": "files",
                "canonical_path_key": "canonical_relative_path",
                "sha256_key": "sha256",
                "snapshot_date_key": "snapshot_date",
            },
        )
    assert "not_disclosed.csv" not in str(error.value)


def test_rejects_recorded_source_ambiguity_and_hash_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "metadata"
    _write_csv(root / "a" / "payload.csv", ["id"], [["001"]])
    _write_csv(root / "b" / "payload.csv", ["id"], [["002"]])
    manifest = root / "path_map.json"
    manifest.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "logical_name": "inventory",
                        "stale_local_path": "D:/old/payload.csv",
                        "sha256": "0" * 64,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(DiscoveryError, match="logical source 'inventory'.*ambiguous"):
        resolve_recorded_sources(root, manifest, {"records_key": "records"})


def test_resolves_top_level_array_manifest_with_approved_pattern_map(tmp_path: Path) -> None:
    root = tmp_path / "metadata"
    payload = root / "current" / "inventory.csv"
    _write_csv(payload, ["id"], [["001"]])
    digest = sha256(payload.read_bytes()).hexdigest()
    manifest = root / "records" / "download_manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            [
                {
                    "name": "inventory.csv",
                    "local_path": "C:/stale/inventory.csv",
                    "sha256": digest,
                }
            ]
        ),
        encoding="utf-8-sig",
    )

    found = resolve_recorded_sources(
        root,
        manifest,
        {
            "top_level": "array",
            "filename_key": "name",
            "stale_path_key": "local_path",
            "sha256_key": "sha256",
            "record_name_patterns": {"inventory": ["*inventory.csv"]},
        },
    )

    assert found["inventory"].relative_path == "current/<file>.csv"
    assert found["inventory"].sha256 == digest


def test_rejects_unknown_top_level_array_mapping(tmp_path: Path) -> None:
    root = tmp_path / "metadata"
    manifest = root / "download_manifest.json"
    root.mkdir()
    manifest.write_text(
        json.dumps(
            [
                {
                    "name": "not_disclosed_unknown.csv",
                    "local_path": "C:/old/not_disclosed_unknown.csv",
                    "sha256": "0" * 64,
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(DiscoveryError, match="unrecognized") as error:
        resolve_recorded_sources(
            root,
            manifest,
            {
                "top_level": "array",
                "filename_key": "name",
                "stale_path_key": "local_path",
                "sha256_key": "sha256",
                "record_name_patterns": {"inventory": ["*inventory.csv"]},
            },
        )
    assert "not_disclosed_unknown.csv" not in str(error.value)


def test_rejects_duplicate_top_level_array_mapping(tmp_path: Path) -> None:
    root = tmp_path / "metadata"
    first = root / "not_disclosed_one.csv"
    second = root / "not_disclosed_two.csv"
    _write_csv(first, ["id"], [["001"]])
    _write_csv(second, ["id"], [["002"]])
    manifest = root / "download_manifest.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "name": "not_disclosed_one.csv",
                    "local_path": "C:/old/not_disclosed_one.csv",
                    "sha256": sha256(first.read_bytes()).hexdigest(),
                },
                {
                    "name": "not_disclosed_two.csv",
                    "local_path": "C:/old/not_disclosed_two.csv",
                    "sha256": sha256(second.read_bytes()).hexdigest(),
                },
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(DiscoveryError, match="ambiguous") as error:
        resolve_recorded_sources(
            root,
            manifest,
            {
                "top_level": "array",
                "filename_key": "name",
                "stale_path_key": "local_path",
                "sha256_key": "sha256",
                "record_name_patterns": {"inventory": ["*.csv"]},
            },
        )
    assert "not_disclosed_one.csv" not in str(error.value)
    assert "not_disclosed_two.csv" not in str(error.value)


def test_rejects_top_level_array_hash_mismatch_without_disclosing_record_name(
    tmp_path: Path,
) -> None:
    root = tmp_path / "metadata"
    payload = root / "not_disclosed_inventory.csv"
    _write_csv(payload, ["id"], [["001"]])
    manifest = root / "download_manifest.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "name": "not_disclosed_inventory.csv",
                    "local_path": "C:/old/not_disclosed_inventory.csv",
                    "sha256": "0" * 64,
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(DiscoveryError, match="SHA-256") as error:
        resolve_recorded_sources(
            root,
            manifest,
            {
                "top_level": "array",
                "filename_key": "name",
                "stale_path_key": "local_path",
                "sha256_key": "sha256",
                "record_name_patterns": {"inventory": ["*inventory.csv"]},
            },
        )
    assert "not_disclosed_inventory.csv" not in str(error.value)


def test_uses_known_hashes_to_disambiguate_manifest_records_and_record_historical_zip(
    tmp_path: Path,
) -> None:
    root = tmp_path / "metadata"
    dictionary = root / "current" / "YA_subjects_dictionary.csv"
    subject_export = root / "current" / "YA_subjects_2026.csv"
    _write_csv(dictionary, ["field"], [["value"]])
    _write_csv(subject_export, ["Subject"], [["001"]])
    manifest = root / "download_manifest.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "name": "YA_subjects_dictionary.csv",
                    "local_path": "C:/old/YA_subjects_dictionary.csv",
                    "sha256": sha256(dictionary.read_bytes()).hexdigest(),
                },
                {
                    "name": "YA_subjects_2026.csv",
                    "local_path": "C:/old/YA_subjects_2026.csv",
                    "sha256": sha256(subject_export.read_bytes()).hexdigest(),
                },
                {
                    "name": "sessionSummaryCSV_1200Release.zip",
                    "local_path": "C:/old/sessionSummaryCSV_1200Release.zip",
                    "sha256": "0" * 64,
                },
            ]
        ),
        encoding="utf-8",
    )
    known_sources = {
        "data_dictionary": DiscoveredInput(
            "data_dictionary",
            "current/<file>.csv",
            sha256(dictionary.read_bytes()).hexdigest(),
        ),
        "subject_export": DiscoveredInput(
            "subject_export",
            "current/<file>.csv",
            sha256(subject_export.read_bytes()).hexdigest(),
        ),
    }

    found = resolve_recorded_sources(
        root,
        manifest,
        {
            "top_level": "array",
            "filename_key": "name",
            "stale_path_key": "local_path",
            "sha256_key": "sha256",
            "historical_record_patterns": ["sessionSummaryCSV_1200Release.zip"],
            "record_name_patterns": {
                "data_dictionary": ["*dictionary*.csv"],
                "subject_export": ["*YA_subjects_*.csv"],
            },
        },
        known_sources=known_sources,
    )

    assert set(found) == {
        "data_dictionary",
        "subject_export",
        "historical_manifest_record",
    }
    historical = found["historical_manifest_record"]
    assert historical.relative_path is None
    assert historical.sha256 is None
    assert historical.legacy == {
        "status": "historical_manifest_record",
        "count": 1,
        "content_hash": None,
    }
    assert "sessionSummaryCSV_1200Release.zip" not in str(manifest_provenance(found))


def test_rejects_undeclared_zip_record_without_disclosing_its_name(tmp_path: Path) -> None:
    root = tmp_path / "metadata"
    root.mkdir()
    manifest = root / "download_manifest.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "name": "sessionSummaryCSV_extra_1200Release.zip",
                    "local_path": "C:/old/sessionSummaryCSV_extra_1200Release.zip",
                    "sha256": "0" * 64,
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(DiscoveryError, match="unrecognized") as error:
        resolve_recorded_sources(
            root,
            manifest,
            {
                "top_level": "array",
                "filename_key": "name",
                "stale_path_key": "local_path",
                "sha256_key": "sha256",
                "historical_record_patterns": ["sessionSummaryCSV_1200Release.zip"],
                "record_name_patterns": {"inventory": ["*inventory.csv"]},
            },
        )
    assert "sessionSummaryCSV_extra_1200Release.zip" not in str(error.value)


def test_aggregates_historical_manifest_records_across_source_manifests(tmp_path: Path) -> None:
    root = tmp_path / "metadata"
    root.mkdir()
    first = root / "first_manifest.json"
    second = root / "second_manifest.json"
    historical_record = {
        "name": "sessionSummaryCSV_1200Release.zip",
        "local_path": "C:/old/sessionSummaryCSV_1200Release.zip",
        "sha256": "0" * 64,
    }
    first.write_text(json.dumps([historical_record]), encoding="utf-8")
    second.write_text(json.dumps([historical_record]), encoding="utf-8")
    source_manifest = {
        "top_level": "array",
        "filename_key": "name",
        "stale_path_key": "local_path",
        "sha256_key": "sha256",
        "historical_record_patterns": ["sessionSummaryCSV_1200Release.zip"],
        "record_name_patterns": {"inventory": ["*inventory.csv"]},
    }

    found = discover_logical_inputs(
        root,
        {
            "first_manifest": {
                "patterns": ["first_manifest.json"],
                "source_manifest": source_manifest,
            },
            "second_manifest": {
                "patterns": ["second_manifest.json"],
                "source_manifest": source_manifest,
            },
        },
    )

    assert found["historical_manifest_record"].legacy == {
        "status": "historical_manifest_record",
        "count": 2,
        "content_hash": None,
    }


def test_reconciles_manifest_verified_input_or_rejects_inconsistent_input(
    tmp_path: Path,
) -> None:
    root = tmp_path / "metadata"
    manifest = root / "records" / "download_manifest.json"
    verified = root / "current" / "verified_inventory.csv"
    _write_csv(verified, ["id"], [["001"]])
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            [
                {
                    "name": "verified_inventory.csv",
                    "local_path": "C:/old/verified_inventory.csv",
                    "sha256": sha256(verified.read_bytes()).hexdigest(),
                }
            ]
        ),
        encoding="utf-8",
    )
    source_manifest = {
        "top_level": "array",
        "filename_key": "name",
        "stale_path_key": "local_path",
        "sha256_key": "sha256",
        "record_name_patterns": {"inventory": ["*inventory.csv"]},
    }

    found = discover_logical_inputs(
        root,
        {
            "a_manifest": {
                "patterns": ["records/download_manifest.json"],
                "source_manifest": source_manifest,
            },
            "inventory": {"patterns": ["current/verified_inventory.csv"]},
        },
    )

    assert found["inventory"].sha256 == sha256(verified.read_bytes()).hexdigest()


def test_rejects_inconsistent_manifest_verified_input_without_disclosing_filenames(
    tmp_path: Path,
) -> None:
    root = tmp_path / "metadata"
    manifest = root / "records" / "download_manifest.json"
    direct = root / "current" / "not_disclosed_direct_inventory.csv"
    recorded = root / "current" / "not_disclosed_recorded_inventory.csv"
    _write_csv(direct, ["id"], [["001"]])
    _write_csv(recorded, ["id"], [["002"]])
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            [
                {
                    "name": "not_disclosed_recorded_inventory.csv",
                    "local_path": "C:/old/not_disclosed_recorded_inventory.csv",
                    "sha256": sha256(recorded.read_bytes()).hexdigest(),
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(DiscoveryError, match="logical source 'inventory' is inconsistent") as error:
        discover_logical_inputs(
            root,
            {
                "a_manifest": {
                    "patterns": ["records/download_manifest.json"],
                    "source_manifest": {
                        "top_level": "array",
                        "filename_key": "name",
                        "stale_path_key": "local_path",
                        "sha256_key": "sha256",
                        "record_name_patterns": {"inventory": ["*inventory.csv"]},
                    },
                },
                "inventory": {"patterns": ["current/not_disclosed_direct_inventory.csv"]},
            },
        )
    assert "not_disclosed_direct_inventory.csv" not in str(error.value)
    assert "not_disclosed_recorded_inventory.csv" not in str(error.value)


def test_rejects_same_hash_manifest_input_at_a_different_path_without_disclosing_names(
    tmp_path: Path,
) -> None:
    root = tmp_path / "metadata"
    manifest = root / "records" / "download_manifest.json"
    recorded = root / "current" / "not_disclosed_recorded_inventory.csv"
    direct = root / "current" / "not_disclosed_direct_inventory.csv"
    _write_csv(recorded, ["id"], [["001"]])
    _write_csv(direct, ["id"], [["001"]])
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            [
                {
                    "name": "not_disclosed_recorded_inventory.csv",
                    "local_path": "C:/old/not_disclosed_recorded_inventory.csv",
                    "sha256": sha256(recorded.read_bytes()).hexdigest(),
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(DiscoveryError, match="logical source 'inventory' is inconsistent") as error:
        discover_logical_inputs(
            root,
            {
                "a_manifest": {
                    "patterns": ["records/download_manifest.json"],
                    "source_manifest": {
                        "top_level": "array",
                        "filename_key": "name",
                        "stale_path_key": "local_path",
                        "sha256_key": "sha256",
                        "record_name_patterns": {"inventory": ["*inventory.csv"]},
                    },
                },
                "inventory": {"patterns": ["current/not_disclosed_direct_inventory.csv"]},
            },
        )
    assert "not_disclosed_direct_inventory.csv" not in str(error.value)
    assert "not_disclosed_recorded_inventory.csv" not in str(error.value)


def test_rejects_duplicate_manifest_records_during_discovery_without_disclosing_names(
    tmp_path: Path,
) -> None:
    root = tmp_path / "metadata"
    manifest = root / "records" / "download_manifest.json"
    first = root / "current" / "not_disclosed_first_inventory.csv"
    second = root / "current" / "not_disclosed_second_inventory.csv"
    _write_csv(first, ["id"], [["001"]])
    _write_csv(second, ["id"], [["002"]])
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            [
                {
                    "name": "not_disclosed_first_inventory.csv",
                    "local_path": "C:/old/not_disclosed_first_inventory.csv",
                    "sha256": sha256(first.read_bytes()).hexdigest(),
                },
                {
                    "name": "not_disclosed_second_inventory.csv",
                    "local_path": "C:/old/not_disclosed_second_inventory.csv",
                    "sha256": sha256(second.read_bytes()).hexdigest(),
                },
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(DiscoveryError, match="logical source 'inventory' is ambiguous") as error:
        discover_logical_inputs(
            root,
            {
                "a_manifest": {
                    "patterns": ["records/download_manifest.json"],
                    "source_manifest": {
                        "top_level": "array",
                        "filename_key": "name",
                        "stale_path_key": "local_path",
                        "sha256_key": "sha256",
                        "record_name_patterns": {"inventory": ["*inventory.csv"]},
                    },
                }
            },
        )
    assert "not_disclosed_first_inventory.csv" not in str(error.value)
    assert "not_disclosed_second_inventory.csv" not in str(error.value)


def test_load_logical_inputs_consumes_column_signature_and_alias_config(tmp_path: Path) -> None:
    column_map = tmp_path / "columns.yaml"
    column_map.write_text("subject_id: Subject\nvisit: Visit\n", encoding="utf-8")
    aliases = tmp_path / "aliases.yaml"
    aliases.write_text("smri: [t1]\nfmri: [rest]\n", encoding="utf-8")
    config = tmp_path / "cohort.yaml"
    config.write_text(
        "column_map: columns.yaml\n"
        "aliases_file: aliases.yaml\n"
        "required_alias_groups: [smri, fmri]\n"
        "logical_inputs:\n"
        "  inventory:\n"
        "    patterns: ['*.csv']\n"
        "    column_signature: [subject_id, visit]\n",
        encoding="utf-8",
    )

    loaded = load_logical_inputs(config)

    assert loaded["inventory"]["required_columns"] == ["Subject", "Visit"]


def test_legacy_inventory_is_redacted_to_aggregate_metadata(tmp_path: Path) -> None:
    root = tmp_path / "metadata"
    (root / "legacy").mkdir(parents=True)
    (root / "legacy" / "subject-0007-session.txt").write_text("synthetic", encoding="utf-8")

    found = discover_logical_inputs(root, {"legacy_inventory": {"legacy_directory": "legacy"}})

    record = found["legacy_inventory"]
    assert record.legacy is not None
    assert record.legacy["count"] == 1
    assert "subject-0007" not in str(record.legacy)


def test_discovers_tsv_columns_and_redacts_normal_source_filename(tmp_path: Path) -> None:
    root = tmp_path / "metadata"
    source = root / "current" / "subject-0007-private.tsv"
    source.parent.mkdir(parents=True)
    source.write_text("Subject\tDate\n0007\t2026-01-03\n", encoding="utf-8")

    found = discover_logical_inputs(
        root,
        {
            "subject_export": {
                "patterns": ["current/*.tsv"],
                "required_columns": ["Subject", "Date"],
            }
        },
    )

    assert found["subject_export"].relative_path == "current/<file>.tsv"
    assert "subject-0007" not in str(manifest_provenance(found))


def test_discovers_hcp_non_subject_records_by_safe_file_type(tmp_path: Path) -> None:
    root = tmp_path / "metadata"
    (root / "records").mkdir(parents=True)
    (root / "records" / "appendix_2025.pdf").write_bytes(b"synthetic")
    (root / "records" / "access_record.md").write_text("synthetic", encoding="utf-8")

    found = discover_logical_inputs(
        root,
        {
            "appendix_2025": {"patterns": ["records/*appendix*.pdf"]},
            "access_record": {"patterns": ["records/*access*record*.md"]},
        },
    )

    assert found["appendix_2025"].relative_path == "records/<file>.pdf"
    assert found["access_record"].relative_path == "records/<file>.md"


def test_hcp_config_declares_complete_metadata_contract() -> None:
    project_root = Path(__file__).resolve().parents[3]
    config_path = project_root / "configs" / "data" / "hcp.yaml"
    raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    column_map = yaml.safe_load(
        (config_path.parent / raw_config["column_map"]).read_text(encoding="utf-8")
    )
    logical_inputs = load_logical_inputs(config_path)

    assert raw_config["access"] == {"open_access": "approved", "restricted_access": "not_approved"}
    assert set(logical_inputs).issuperset(
        {
            "data_dictionary",
            "unrelated_list",
            "subject_export",
            "appendix_2025",
            "access_record",
            "download_record",
            "download_manifest",
            "legacy_inventory",
        }
    )
    assert set(logical_inputs["subject_export"]["required_columns"]).issuperset(
        {
            "CogFluidComp_Unadj",
            "CogTotalComp_Unadj",
            "PMAT24_A_CR",
            "QC_Issue",
            "3T_Full_MR_Compl",
        }
    )
    assert "age" not in raw_config["logical_inputs"]["subject_export"]["column_signature"]
    assert logical_inputs["download_manifest"]["source_manifest"]["sha256_key"] == "sha256"
    assert logical_inputs["download_manifest"]["source_manifest"]["record_name_patterns"][
        "subject_export"
    ] == ["*YA_subjects_*.csv"]
    assert logical_inputs["subject_export"]["patterns"] == ["hcp_metadata/raw/*YA_subjects_*.csv"]
    assert logical_inputs["download_manifest"]["source_manifest"]["historical_record_patterns"] == [
        "sessionSummaryCSV_1200Release.zip"
    ]
    assert column_map["dictionary_field"] == "columnHeader"
    assert column_map["dictionary_definition"] == "description"
    assert "dictionary_type" not in column_map


def test_hcp_manifest_mapping_distinguishes_subject_export_from_unrelated_subjects(
    tmp_path: Path,
) -> None:
    project_root = Path(__file__).resolve().parents[3]
    logical_inputs = load_logical_inputs(project_root / "configs" / "data" / "hcp.yaml")
    root = tmp_path / "metadata"
    unrelated = root / "hcp_metadata" / "raw" / "HCP_YA_unrelated_subjects.csv"
    subject_export = root / "hcp_metadata" / "raw" / "HCP_YA_subjects_2026.csv"
    _write_csv(unrelated, ["Subject"], [["001"]])
    _write_csv(subject_export, ["Subject"], [["002"]])
    manifest = root / "hcp_metadata" / "records" / "download_manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            [
                {
                    "name": "HCP_YA_unrelated_subjects.csv",
                    "local_path": "C:/old/HCP_YA_unrelated_subjects.csv",
                    "sha256": sha256(unrelated.read_bytes()).hexdigest(),
                },
                {
                    "name": "HCP_YA_subjects_2026.csv",
                    "local_path": "C:/old/HCP_YA_subjects_2026.csv",
                    "sha256": sha256(subject_export.read_bytes()).hexdigest(),
                },
            ]
        ),
        encoding="utf-8",
    )

    found = resolve_recorded_sources(
        root,
        manifest,
        logical_inputs["download_manifest"]["source_manifest"],
    )

    assert set(found) == {"unrelated_list", "subject_export"}


def test_hcp_direct_discovery_distinguishes_subject_export_from_unrelated_subjects(
    tmp_path: Path,
) -> None:
    project_root = Path(__file__).resolve().parents[3]
    logical_inputs = load_logical_inputs(project_root / "configs" / "data" / "hcp.yaml")
    subject_specification = logical_inputs["subject_export"]
    root = tmp_path / "metadata"
    unrelated = root / "hcp_metadata" / "raw" / "HCP_YA_unrelated_subjects.csv"
    subject_export = root / "hcp_metadata" / "raw" / "HCP_YA_subjects_2026.csv"
    required_columns = subject_specification["required_columns"]
    assert isinstance(required_columns, list)
    _write_csv(unrelated, required_columns, [["unrelated", *["" for _ in required_columns[1:]]]])
    _write_csv(subject_export, required_columns, [["" for _ in required_columns]])

    found = discover_logical_inputs(root, {"subject_export": subject_specification})

    assert found["subject_export"].relative_path == "hcp_metadata/raw/<file>.csv"
    assert found["subject_export"].sha256 == sha256(subject_export.read_bytes()).hexdigest()


def test_hcp_config_reuses_combined_download_record_for_access_and_download(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[3]
    config_path = project_root / "configs" / "data" / "hcp.yaml"
    logical_inputs = load_logical_inputs(config_path)
    root = tmp_path / "metadata"
    record = root / "hcp_metadata" / "records" / "hcp_download_record.md"
    record.parent.mkdir(parents=True)
    record.write_text("Open Access approved; Restricted Access not approved.\n", encoding="utf-8")

    found = discover_logical_inputs(
        root,
        {
            "access_record": logical_inputs["access_record"],
            "download_record": logical_inputs["download_record"],
        },
    )

    assert found["access_record"].relative_path == found["download_record"].relative_path
    assert found["access_record"].sha256 == found["download_record"].sha256


def test_ppmi_config_uses_path_map_join_and_real_form_inventory_headers() -> None:
    project_root = Path(__file__).resolve().parents[3]
    config_path = project_root / "configs" / "data" / "ppmi.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    column_map = yaml.safe_load(
        (config_path.parent / config["column_map"]).read_text(encoding="utf-8")
    )
    visit_map = yaml.safe_load(
        (config_path.parent / config["visit_map"]).read_text(encoding="utf-8")
    )
    aliases = yaml.safe_load(
        (config_path.parent / config["aliases_file"]).read_text(encoding="utf-8")
    )

    resolution = config["logical_inputs"]["path_map"]["path_map_resolution"]
    assert config["visit_map"] == "ppmi_visit_map.yaml"
    assert config["logical_inputs"]["path_map"]["patterns"] == [
        "ppmi_metadata/records/ppmi_path_map.json"
    ]
    assert config["logical_inputs"]["source_manifest"]["patterns"] == [
        "ppmi_metadata/records/ppmi_source_manifest.json"
    ]
    assert resolution["base_directory"] == "ppmi_metadata"
    assert resolution["allowed_metadata_keys"] == ["ppmi_metadata_root_env"]
    assert resolution["allowed_unmapped_records"] == [
        {
            "logical_name": "archived_data_dictionary",
            "canonical_pattern": "guidance/archive/ppmi_data_dictionary_*.csv",
            "required_status": "archive_only",
            "required_role": "Historical dictionary retained only for compatibility comparison",
        }
    ]
    assert config["logical_inputs"]["archived_data_dictionary"] == {"archive_only": True}
    assert resolution["source_manifest_logical_name"] == "source_manifest"
    assert resolution["records_key"] == "files"
    assert resolution["canonical_path_key"] == "canonical_relative_path"
    assert resolution["snapshot_date_key"] == "snapshot_date"
    assert resolution["path_map_keys"] == {
        "data_dictionary": "current_data_dictionary",
        "code_list": "current_code_list",
        "participant_status": "participant_status",
        "demographics": "demographics",
        "mds_updrs_part_i_patient": "mds_updrs_part_i_patient",
        "mds_updrs_part_i_clinician": "mds_updrs_part_i_clinician",
        "mds_updrs_part_ii_patient": "mds_updrs_part_ii_patient",
        "mds_updrs_part_iii_motor": "mds_updrs_part_iii_motor",
        "mri_completion": "mri_completion_current",
        "archived_mri": "mri_completion_archived",
        "xing_mri_acquisition": "xing_mri_acquisition",
        "t1_inventory": "t1_inventory",
        "rsfmri_inventory": "rsfmri_inventory",
        "dti_inventory": "dti_inventory",
    }
    assert column_map["current_page_name"] == "PAG_NAME"
    assert column_map["participant_status"] == "ENROLL_STATUS"
    assert column_map["acquisition_protocol"] == "PROTOCOL"
    assert column_map["inventory_description"] == "Description"
    assert "sequence_description" not in column_map
    assert visit_map == {
        "visit_policy": "code_list_subject_event",
        "date_validation": "audit_only",
        "unknown_visit": "unknown",
    }
    assert {"3d t1", "mprage", "mp-rage", "ir-fspgr", "spgr", "t1"}.issubset(aliases["smri"])
    assert {
        "rsfmri_rl",
        "rsfmri_lr",
        "rsfmri_pa",
        "rsfmri_ap",
        "ep2d_resting_state",
        "ep2d_bold_rest",
        "resting state",
    }.issubset(aliases["fmri"])
    assert not {"rest", "bold", "ep2d", "rl", "lr", "pa", "ap"}.intersection(aliases["fmri"])
    assert {"reverse phase", "short", "revpe", "spin echo"}.issubset(
        aliases["reverse_phase_short_rules"]
    )
    assert not {"rl", "lr", "pa", "ap"}.intersection(aliases["reverse_phase_short_rules"])
    assert {"survey", "t2", "flair", "field map"}.issubset(aliases["smri_exclude"])
    assert {"nm-mt", "gre_mt", "dti", "dwi", "diffusion", "field map"}.issubset(
        aliases["fmri_exclude"]
    )
    assert {"dti_rl", "dti_lr", "b700", "b1000", "b2000", "revb0"}.issubset(aliases["dwi"])
    assert {"t1", "t2", "flair", "rest", "fmri", "phantom", "field map"}.issubset(
        aliases["dwi_exclude"]
    )


def test_loads_validated_ppmi_target_config_from_confined_companion() -> None:
    project_root = Path(__file__).resolve().parents[3]
    target_config = load_ppmi_target_config(project_root / "configs" / "data" / "ppmi.yaml")

    assert target_config["change_direction"] == "followup_total - baseline_total"
    assert target_config["candidates"] == {
        "candidate_A": {"parts": ["part_iii"]},
        "candidate_B": {"parts": ["part_i_clinician", "part_i_patient", "part_ii", "part_iii"]},
    }
    assert target_config["tables"]["part_iii"]["dictionary_selector"] == {
        "modules": ["NUPDRS3TRT"],
        "pages": ["NUPDRDOSE3"],
        "item_name_regex": "^NP3[A-Z]+$",
        "official_total_column": "NP3TOT",
        "expected_item_count": 33,
    }
    assert target_config["part_iii_state"]["policies"] == {
        "unique_only": {"enabled": True},
        "prefer_off": {"enabled": True},
        "prefer_on": {"enabled": True},
    }
    assert target_config["selection"] == {
        "primary_target": "candidate_A",
        "target_definition": "MDS-UPDRS Part III follow-up score minus baseline score",
        "primary_policy": "prefer_off",
        "secondary_targets": ["candidate_B"],
        "sensitivity_policies": ["unique_only", "prefer_on"],
    }
    assert target_config["part_iii_state"]["confirmed"] is True
    assert target_config["target_confirmed"] is True


def test_rejects_target_config_companion_outside_config_directory(tmp_path: Path) -> None:
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (tmp_path / "targets.yaml").write_text("target_confirmed: false\n", encoding="utf-8")
    config_path = config_dir / "ppmi.yaml"
    config_path.write_text("target_config: ../targets.yaml\n", encoding="utf-8")

    with pytest.raises(DiscoveryError, match="target_config must be beneath config directory"):
        load_ppmi_target_config(config_path)


def test_rejects_ppmi_target_config_with_invalid_policy_or_selector(tmp_path: Path) -> None:
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    config_path = config_dir / "ppmi.yaml"
    target_path = config_dir / "targets.yaml"
    config_path.write_text("target_config: targets.yaml\n", encoding="utf-8")
    target_path.write_text(
        yaml.safe_dump(
            {
                "subject_id_column": "PATNO",
                "visit_column": "EVENT_ID",
                "date_column": "INFODT",
                "change_direction": "followup_total - baseline_total",
                "month_horizons": {},
                "tables": {},
                "candidates": {},
                "part_iii_state": {"policies": {"unique_only": {"enabled": True}}},
                "target_confirmed": False,
                "task_thresholds": {"stress_test": 120, "ready": 180},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(DiscoveryError, match="target configuration is invalid"):
        load_ppmi_target_config(config_path)


@pytest.mark.parametrize("extra_location", ["top_level", "part_iii_state"])
def test_rejects_ppmi_target_config_extra_keys(tmp_path: Path, extra_location: str) -> None:
    project_root = Path(__file__).resolve().parents[3]
    target_config = dict(load_ppmi_target_config(project_root / "configs" / "data" / "ppmi.yaml"))
    if extra_location == "top_level":
        target_config["not_approved"] = True
    else:
        target_config["part_iii_state"] = dict(target_config["part_iii_state"]) | {
            "not_approved": True
        }
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    config_path = config_dir / "ppmi.yaml"
    target_path = config_dir / "targets.yaml"
    config_path.write_text("target_config: targets.yaml\n", encoding="utf-8")
    target_path.write_text(yaml.safe_dump(target_config), encoding="utf-8")

    with pytest.raises(DiscoveryError, match="target configuration is invalid"):
        load_ppmi_target_config(config_path)


def test_normalizes_missing_target_config_companion_without_disclosing_filename(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "ppmi.yaml"
    config_path.write_text("target_config: not_disclosed.yaml\n", encoding="utf-8")

    with pytest.raises(DiscoveryError, match="target configuration cannot be read") as error:
        load_ppmi_target_config(config_path)
    assert "not_disclosed.yaml" not in str(error.value)


def test_cli_normalizes_missing_config_without_disclosing_absolute_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing_config = tmp_path / "private-config-sentinel.yaml"

    exit_code = main(
        [
            "--config",
            str(missing_config),
            "--metadata-root",
            str(tmp_path),
            "--output-dir",
            str(tmp_path / "output"),
            "--dry-run",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 2
    assert output == "discovery failed: configuration or metadata input cannot be read\n"
    assert str(missing_config) not in output
    assert missing_config.name not in output


def test_rejects_invalid_ppmi_target_item_name_regex(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[3]
    target_config = dict(load_ppmi_target_config(project_root / "configs" / "data" / "ppmi.yaml"))
    tables = dict(target_config["tables"])
    part_iii = dict(tables["part_iii"])
    part_iii["dictionary_selector"] = dict(part_iii["dictionary_selector"]) | {
        "item_name_regex": "["
    }
    target_config["tables"] = tables | {"part_iii": part_iii}
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    config_path = config_dir / "ppmi.yaml"
    target_path = config_dir / "targets.yaml"
    config_path.write_text("target_config: targets.yaml\n", encoding="utf-8")
    target_path.write_text(yaml.safe_dump(target_config), encoding="utf-8")

    with pytest.raises(DiscoveryError, match="target configuration is invalid"):
        load_ppmi_target_config(config_path)


@pytest.mark.parametrize(
    ("companion_key", "expected_message"),
    [
        ("column_map", "column map must be beneath config directory"),
        ("aliases_file", "aliases_file must be beneath config directory"),
    ],
)
def test_rejects_configuration_companion_path_outside_config_directory(
    tmp_path: Path, companion_key: str, expected_message: str
) -> None:
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (tmp_path / "outside.yaml").write_text("field: value\n", encoding="utf-8")
    config_path = config_dir / "cohort.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                companion_key: "../outside.yaml",
                "logical_inputs": {"input": {"patterns": ["*.csv"]}},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(DiscoveryError, match=expected_message):
        load_logical_inputs(config_path)
