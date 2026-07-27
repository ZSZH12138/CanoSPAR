"""Configuration-led discovery that exposes only sanitized logical inputs."""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path, PureWindowsPath

import yaml

from canospar.data.metadata_io import csv_columns, sha256_file

_ARCHIVE_PARTS = frozenset({"archive", "archived", "legacy"})
_ALLOWED_SUFFIXES = frozenset({".csv", ".tsv", ".json", ".yaml", ".yml", ".txt", ".md", ".pdf"})
_IDENTIFIER_COMPONENT = re.compile(
    r"(?:sub(?:ject)?|patno|participant)[_-]?\d+|\d{6,}", re.IGNORECASE
)


class DiscoveryError(ValueError):
    """An input cannot be safely and uniquely resolved."""


@dataclass(frozen=True)
class DiscoveredInput:
    """Safe discovery result: no table rows or absolute source paths."""

    logical_name: str
    relative_path: str | None
    sha256: str | None
    legacy: dict[str, object] | None = None
    _canonical_path: Path | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class PathMapResolution:
    """Root-confined sources resolved from a path map and source manifest."""

    sources: dict[str, DiscoveredInput]
    snapshot_date: str


def _safe_root(metadata_root: Path) -> Path:
    root = metadata_root.resolve()
    if not root.is_dir():
        raise DiscoveryError("metadata root is unavailable")
    return root


def _is_archived(path: Path, root: Path) -> bool:
    return any(part.casefold() in _ARCHIVE_PARTS for part in path.relative_to(root).parts)


def _sanitized_relative_path(path: Path, root: Path) -> str:
    """Keep useful directory context while never persisting a source basename."""
    relative = path.relative_to(root)
    directories = [
        "<redacted-dir>" if _IDENTIFIER_COMPONENT.search(part) else part
        for part in relative.parts[:-1]
    ]
    filename = f"<file>{path.suffix.casefold()}"
    return "/".join([*directories, filename])


def _matches(root: Path, patterns: object, *, include_archives: bool) -> list[Path]:
    if not isinstance(patterns, list):
        raise DiscoveryError("logical source patterns must be a non-empty list of strings")
    if not patterns or not all(isinstance(item, str) for item in patterns):
        raise DiscoveryError("logical source patterns must be a non-empty list of strings")
    string_patterns = [str(item) for item in patterns]
    matches = {
        candidate.resolve()
        for pattern in string_patterns
        for candidate in root.glob(pattern)
        if candidate.is_file()
    }
    safe_matches = [
        candidate
        for candidate in matches
        if candidate.is_relative_to(root)
        and candidate.suffix.casefold() in _ALLOWED_SUFFIXES
        and (include_archives or not _is_archived(candidate, root))
    ]
    return sorted(safe_matches, key=lambda item: item.relative_to(root).as_posix())


def _select(logical_name: str, matches: list[Path], selection: object) -> Path:
    if not matches:
        raise DiscoveryError(f"logical source '{logical_name}' is missing")
    if selection == "latest":
        ordered = sorted(matches, key=lambda item: (item.name, item.as_posix()))
        return ordered[-1]
    if selection not in (None, "exact"):
        raise DiscoveryError(f"logical source '{logical_name}' has unsupported selection")
    if len(matches) != 1:
        raise DiscoveryError(f"logical source '{logical_name}' is ambiguous")
    return matches[0]


def _verify_columns(logical_name: str, path: Path, required_columns: object) -> None:
    if required_columns is None:
        return
    if path.suffix.casefold() not in {".csv", ".tsv"}:
        raise DiscoveryError(f"logical source '{logical_name}' cannot validate required columns")
    columns = set(csv_columns(path))
    if not isinstance(required_columns, list):
        raise DiscoveryError(f"logical source '{logical_name}' has invalid required columns")
    if not all(isinstance(column, str) for column in required_columns):
        raise DiscoveryError(f"logical source '{logical_name}' has invalid required columns")
    expected_columns = [str(column) for column in required_columns]
    missing = [column for column in expected_columns if column not in columns]
    if missing:
        raise DiscoveryError(f"logical source '{logical_name}' is missing columns")


def _recorded_filename(value: object, *, logical_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DiscoveryError(f"logical source '{logical_name}' has no recorded filename")
    filename = PureWindowsPath(value).name
    if filename in {"", ".", ".."}:
        raise DiscoveryError(f"logical source '{logical_name}' has no recorded filename")
    return filename


def _read_json_mapping(path: Path, *, description: str) -> Mapping[str, object]:
    try:
        decoded = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise DiscoveryError(f"{description} cannot be read") from error
    if not isinstance(decoded, Mapping):
        raise DiscoveryError(f"{description} must be a mapping")
    return decoded


def _confined_relative_path(root: Path, value: object) -> Path:
    if not isinstance(value, str) or not value.strip() or PureWindowsPath(value).is_absolute():
        raise DiscoveryError("path map has invalid relative path")
    path = Path(value)
    if path.is_absolute():
        raise DiscoveryError("path map has invalid relative path")
    candidate = (root / path).resolve()
    if not candidate.is_relative_to(root):
        raise DiscoveryError("path map has invalid relative path")
    return candidate


def resolve_path_map_sources(
    metadata_root: Path,
    path_map_path: Path,
    source_manifest_path: Path,
    source_specification: Mapping[str, object],
) -> PathMapResolution:
    """Join approved path-map entries with manifest hashes without exposing file names."""
    root = _safe_root(metadata_root)
    base_directory = source_specification.get("base_directory", ".")
    base_root = _confined_relative_path(root, base_directory)
    path_map_control = path_map_path.resolve()
    source_manifest_control = source_manifest_path.resolve()
    if (
        not base_root.is_dir()
        or not path_map_control.is_relative_to(base_root)
        or not source_manifest_control.is_relative_to(base_root)
    ):
        raise DiscoveryError("path-map control files must be beneath base directory")
    path_map = _read_json_mapping(path_map_control, description="path map")
    source_manifest = _read_json_mapping(source_manifest_control, description="source manifest")
    path_map_keys = source_specification.get("path_map_keys")
    records_key = source_specification.get("records_key", "files")
    canonical_path_key = source_specification.get("canonical_path_key", "canonical_relative_path")
    sha256_key = source_specification.get("sha256_key", "sha256")
    snapshot_date_key = source_specification.get("snapshot_date_key", "snapshot_date")
    allowed_unmapped_paths = source_specification.get("allowed_unmapped_canonical_paths", [])
    allowed_metadata_keys = source_specification.get("allowed_metadata_keys", [])
    allowed_unmapped_records = source_specification.get("allowed_unmapped_records", [])
    valid_path_map_keys = isinstance(path_map_keys, Mapping) and all(
        isinstance(name, str) and isinstance(key, str) for name, key in path_map_keys.items()
    )
    valid_manifest_keys = all(
        isinstance(key, str)
        for key in (records_key, canonical_path_key, sha256_key, snapshot_date_key)
    )
    valid_allowed_paths = isinstance(allowed_unmapped_paths, list) and all(
        isinstance(path, str) for path in allowed_unmapped_paths
    )
    valid_metadata_keys = isinstance(allowed_metadata_keys, list) and all(
        isinstance(key, str) for key in allowed_metadata_keys
    )
    valid_archive_records = isinstance(allowed_unmapped_records, list) and all(
        isinstance(record, Mapping)
        and all(
            isinstance(record.get(key), str)
            for key in ("logical_name", "canonical_pattern", "required_status", "required_role")
        )
        for record in allowed_unmapped_records
    )
    if (
        not valid_path_map_keys
        or not valid_manifest_keys
        or not valid_allowed_paths
        or not valid_metadata_keys
        or not valid_archive_records
    ):
        raise DiscoveryError("path-map source configuration is invalid")
    assert isinstance(path_map_keys, Mapping)
    assert isinstance(records_key, str)
    assert isinstance(canonical_path_key, str)
    assert isinstance(sha256_key, str)
    assert isinstance(snapshot_date_key, str)
    assert isinstance(allowed_unmapped_paths, list)
    assert isinstance(allowed_metadata_keys, list)
    assert isinstance(allowed_unmapped_records, list)
    configured_keys = {str(name): str(key) for name, key in path_map_keys.items()}
    allowed_paths = {str(path) for path in allowed_unmapped_paths}
    allowed_metadata = {str(key) for key in allowed_metadata_keys}
    archive_specifications = [dict(record) for record in allowed_unmapped_records]
    archive_logical_names = [str(record["logical_name"]) for record in archive_specifications]
    if (
        len(archive_logical_names) != len(set(archive_logical_names))
        or any(not re.fullmatch(r"[a-z][a-z0-9_]*", name) for name in archive_logical_names)
        or any(
            PureWindowsPath(str(record["canonical_pattern"])).is_absolute()
            or Path(str(record["canonical_pattern"])).is_absolute()
            or ".." in Path(str(record["canonical_pattern"])).parts
            for record in archive_specifications
        )
    ):
        raise DiscoveryError("path-map source configuration is invalid")
    for allowed_path in allowed_paths:
        _confined_relative_path(base_root, allowed_path)
    if not all(isinstance(value, str) for value in path_map.values()):
        raise DiscoveryError("path map must contain only string values")
    typed_path_map = {key: str(value) for key, value in path_map.items()}
    if set(typed_path_map).difference(set(configured_keys.values()), allowed_metadata):
        raise DiscoveryError("path map has unapproved key")
    snapshot_date = source_manifest.get(snapshot_date_key)
    if not isinstance(snapshot_date, str):
        raise DiscoveryError("source manifest has invalid snapshot date")
    try:
        date.fromisoformat(snapshot_date)
    except ValueError as error:
        raise DiscoveryError("source manifest has invalid snapshot date") from error
    records = source_manifest.get(records_key)
    if not isinstance(records, list):
        raise DiscoveryError("source manifest has no record collection")
    manifest_hashes: dict[str, str] = {}
    manifest_records: dict[str, Mapping[str, object]] = {}
    for record in records:
        if not isinstance(record, Mapping):
            raise DiscoveryError("source manifest has invalid record")
        relative_path = record.get(canonical_path_key)
        digest = record.get(sha256_key)
        if not isinstance(relative_path, str) or not isinstance(digest, str):
            raise DiscoveryError("source manifest has invalid record")
        _confined_relative_path(base_root, relative_path)
        if relative_path in manifest_hashes:
            raise DiscoveryError("source manifest has duplicate path-map record")
        manifest_hashes[relative_path] = digest
        manifest_records[relative_path] = record
    selected_paths = {
        typed_path_map[key] for key in configured_keys.values() if key in typed_path_map
    }
    if len(selected_paths) != len(configured_keys):
        raise DiscoveryError("path map is missing approved logical input")
    unresolved_paths = set(manifest_hashes).difference(selected_paths, allowed_paths)
    sources: dict[str, DiscoveredInput] = {}
    for archive_specification in archive_specifications:
        pattern = str(archive_specification["canonical_pattern"])
        matches = sorted(path for path in unresolved_paths if fnmatch.fnmatchcase(path, pattern))
        if len(matches) != 1:
            raise DiscoveryError("source manifest has invalid archive-only record")
        archive_path = matches[0]
        archive_record = manifest_records[archive_path]
        if (
            archive_record.get("status") != archive_specification["required_status"]
            or archive_record.get("role") != archive_specification["required_role"]
        ):
            raise DiscoveryError("source manifest has invalid archive-only record")
        canonical_archive_path = _confined_relative_path(base_root, archive_path)
        if not canonical_archive_path.is_file():
            raise DiscoveryError("source manifest has invalid archive-only record")
        archive_digest = sha256_file(canonical_archive_path)
        if archive_digest != manifest_hashes[archive_path]:
            raise DiscoveryError("source manifest archive-only record failed SHA-256 validation")
        sources[str(archive_specification["logical_name"])] = DiscoveredInput(
            logical_name=str(archive_specification["logical_name"]),
            relative_path=None,
            sha256=None,
            legacy={
                "status": "archive_only",
                "count": 1,
                "content_hash": archive_digest,
            },
        )
        unresolved_paths.remove(archive_path)
    if unresolved_paths:
        raise DiscoveryError("source manifest has unknown path-map record")
    if selected_paths.difference(manifest_hashes):
        raise DiscoveryError("source manifest is missing path-map record")
    for logical_name, path_map_key in configured_keys.items():
        relative_path = typed_path_map[path_map_key]
        path = _confined_relative_path(base_root, relative_path)
        if not path.is_file():
            raise DiscoveryError(f"logical source '{logical_name}' is missing")
        digest = sha256_file(path)
        if manifest_hashes[relative_path] != digest:
            raise DiscoveryError(f"logical source '{logical_name}' failed SHA-256 validation")
        sources[logical_name] = DiscoveredInput(
            logical_name=logical_name,
            relative_path=_sanitized_relative_path(path, root),
            sha256=digest,
            _canonical_path=path,
        )
    return PathMapResolution(sources=sources, snapshot_date=snapshot_date)


def _same_discovered_input(left: DiscoveredInput, right: DiscoveredInput) -> bool:
    return left.sha256 == right.sha256 and left._canonical_path == right._canonical_path


def _historical_manifest_count(item: DiscoveredInput) -> int | None:
    if item.legacy is None or item.legacy.get("status") != "historical_manifest_record":
        return None
    count = item.legacy.get("count")
    return count if isinstance(count, int) and count > 0 else None


def _historical_manifest_record(count: int) -> DiscoveredInput:
    return DiscoveredInput(
        logical_name="historical_manifest_record",
        relative_path=None,
        sha256=None,
        legacy={
            "status": "historical_manifest_record",
            "count": count,
            "content_hash": None,
        },
    )


def resolve_recorded_sources(
    metadata_root: Path,
    source_manifest_path: Path,
    source_specification: Mapping[str, object],
    *,
    known_sources: Mapping[str, DiscoveredInput] | None = None,
) -> dict[str, DiscoveredInput]:
    """Resolve manifest/path-map records under the root, never at historical absolute paths."""
    root = _safe_root(metadata_root)
    manifest = source_manifest_path.resolve()
    if not manifest.is_relative_to(root) or manifest.suffix.casefold() != ".json":
        raise DiscoveryError("source manifest must be a JSON file beneath metadata root")
    try:
        decoded = json.loads(manifest.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise DiscoveryError("source manifest cannot be read") from error
    top_level = source_specification.get("top_level", "mapping")
    records_key = source_specification.get("records_key", "records")
    record_name_patterns = source_specification.get("record_name_patterns")
    historical_record_patterns = source_specification.get("historical_record_patterns", [])
    records: list[object]
    if top_level == "array":
        if not isinstance(decoded, list) or not isinstance(record_name_patterns, Mapping):
            raise DiscoveryError("source manifest has invalid record configuration")
        records = decoded
    elif top_level == "mapping":
        if not isinstance(records_key, str) or not isinstance(decoded, Mapping):
            raise DiscoveryError("source manifest has invalid record configuration")
        mapped_records = decoded.get(records_key)
        if not isinstance(mapped_records, list):
            raise DiscoveryError("source manifest has no record collection")
        records = list(mapped_records)
    else:
        raise DiscoveryError("source manifest has invalid record configuration")
    logical_name_key = source_specification.get("logical_name_key", "logical_name")
    stale_path_key = source_specification.get("stale_path_key", "stale_local_path")
    filename_key = source_specification.get("filename_key", "filename")
    hash_key = source_specification.get("sha256_key", "sha256")
    keys = (logical_name_key, stale_path_key, filename_key, hash_key)
    if not all(isinstance(key, str) for key in keys):
        raise DiscoveryError("source manifest has invalid key configuration")
    if not isinstance(historical_record_patterns, list) or not all(
        isinstance(pattern, str) for pattern in historical_record_patterns
    ):
        raise DiscoveryError("source manifest has invalid historical record patterns")
    resolved: dict[str, DiscoveredInput] = {}
    historical_record_count = 0
    for record in records:
        if not isinstance(record, Mapping):
            raise DiscoveryError("source manifest has invalid record")
        reference = record.get(filename_key) or record.get(stale_path_key)
        filename = _recorded_filename(reference, logical_name="record")
        if top_level == "array":
            if any(
                fnmatch.fnmatchcase(filename.casefold(), pattern.casefold())
                for pattern in historical_record_patterns
            ):
                historical_record_count += 1
                continue
            assert isinstance(record_name_patterns, Mapping)
            matches = [
                name
                for name, patterns in record_name_patterns.items()
                if isinstance(name, str)
                and re.fullmatch(r"[a-z][a-z0-9_]*", name)
                and isinstance(patterns, list)
                and any(
                    isinstance(pattern, str)
                    and fnmatch.fnmatchcase(filename.casefold(), pattern.casefold())
                    for pattern in patterns
                )
            ]
            if not matches:
                raise DiscoveryError("source manifest has unrecognized record")
            if len(matches) != 1:
                expected_hash = record.get(hash_key)
                verified_matches = [
                    name
                    for name in matches
                    if known_sources is not None
                    and known_sources.get(name) is not None
                    and known_sources[name].sha256 == expected_hash
                ]
                if len(verified_matches) != 1:
                    raise DiscoveryError("source manifest has ambiguous record mapping")
                logical_name = verified_matches[0]
            else:
                logical_name = matches[0]
        else:
            candidate_logical_name = record.get(logical_name_key)
            if not isinstance(candidate_logical_name, str) or not re.fullmatch(
                r"[a-z][a-z0-9_]*", candidate_logical_name
            ):
                raise DiscoveryError("source manifest has invalid logical name")
            logical_name = candidate_logical_name
        candidates = [
            candidate
            for candidate in root.rglob(filename)
            if candidate.is_file()
            and candidate.is_relative_to(root)
            and not _is_archived(candidate, root)
        ]
        path = _select(
            logical_name, sorted(candidates), source_specification.get("selection", "exact")
        )
        digest = sha256_file(path)
        expected_hash = record.get(hash_key)
        if not isinstance(expected_hash, str) or expected_hash != digest:
            raise DiscoveryError(f"logical source '{logical_name}' failed SHA-256 validation")
        if logical_name in resolved:
            raise DiscoveryError(f"logical source '{logical_name}' is ambiguous")
        resolved[logical_name] = DiscoveredInput(
            logical_name=logical_name,
            relative_path=_sanitized_relative_path(path, root),
            sha256=digest,
            _canonical_path=path,
        )
    if historical_record_count:
        resolved["historical_manifest_record"] = _historical_manifest_record(
            historical_record_count
        )
    return resolved


def _legacy_summary(root: Path, relative_directory: object, *, required: bool) -> dict[str, object]:
    if not isinstance(relative_directory, str):
        raise DiscoveryError("legacy directory must be a relative string")
    directory = (root / relative_directory).resolve()
    if not directory.is_relative_to(root):
        raise DiscoveryError("legacy inventory is missing")
    if not directory.is_dir():
        if not required:
            return {"status": "not_available", "count": 0, "content_hash": None}
        raise DiscoveryError("legacy inventory is missing")
    digest_material = "\n".join(
        sha256_file(path) for path in sorted(directory.rglob("*")) if path.is_file()
    ).encode("ascii")
    import hashlib

    return {
        "status": "aggregate_only",
        "count": sum(1 for path in directory.rglob("*") if path.is_file()),
        "content_hash": hashlib.sha256(digest_material).hexdigest(),
    }


def discover_logical_inputs(
    metadata_root: Path,
    logical_inputs: Mapping[str, Mapping[str, object]],
) -> dict[str, DiscoveredInput]:
    """Resolve configured metadata beneath ``metadata_root`` and verify hashes."""
    root = _safe_root(metadata_root)
    discovered: dict[str, DiscoveredInput] = {}
    pending_source_manifests: list[tuple[Path, Mapping[str, object]]] = []
    path_map_resolutions: list[tuple[str, Mapping[str, object]]] = []
    deferred_path_map_names: set[str] = set()
    deferred_archive_names: set[str] = set()
    for name, specification in logical_inputs.items():
        if not isinstance(specification, Mapping):
            continue
        resolution = specification.get("path_map_resolution")
        if resolution is None:
            continue
        if not isinstance(resolution, Mapping) or not isinstance(
            resolution.get("path_map_keys"), Mapping
        ):
            raise DiscoveryError("path-map source configuration is invalid")
        names = resolution["path_map_keys"]
        if not all(isinstance(logical_name, str) for logical_name in names):
            raise DiscoveryError("path-map source configuration is invalid")
        if any(logical_name not in logical_inputs for logical_name in names):
            raise DiscoveryError("path-map source configuration is invalid")
        if deferred_path_map_names.intersection(names):
            raise DiscoveryError("path-map source configuration is invalid")
        deferred_path_map_names.update(names)
        archive_records = resolution.get("allowed_unmapped_records", [])
        if not isinstance(archive_records, list) or not all(
            isinstance(record, Mapping) and isinstance(record.get("logical_name"), str)
            for record in archive_records
        ):
            raise DiscoveryError("path-map source configuration is invalid")
        archive_names = {str(record["logical_name"]) for record in archive_records}
        if (
            len(archive_names) != len(archive_records)
            or any(name not in logical_inputs for name in archive_names)
            or deferred_path_map_names.intersection(archive_names)
            or deferred_archive_names.intersection(archive_names)
        ):
            raise DiscoveryError("path-map source configuration is invalid")
        deferred_archive_names.update(archive_names)
        path_map_resolutions.append((name, resolution))
    for logical_name, specification in sorted(logical_inputs.items()):
        valid_definition = re.fullmatch(r"[a-z][a-z0-9_]*", logical_name) and isinstance(
            specification, Mapping
        )
        if not valid_definition:
            raise DiscoveryError("logical input definitions must use safe logical names")
        if logical_name in deferred_path_map_names or logical_name in deferred_archive_names:
            continue
        if "legacy_directory" in specification:
            discovered[logical_name] = DiscoveredInput(
                logical_name=logical_name,
                relative_path=None,
                sha256=None,
                legacy=_legacy_summary(
                    root,
                    specification["legacy_directory"],
                    required=bool(specification.get("required", True)),
                ),
            )
            continue
        matches = _matches(
            root,
            specification.get("patterns"),
            include_archives=bool(specification.get("include_archives")),
        )
        if not matches and not bool(specification.get("required", True)):
            discovered[logical_name] = DiscoveredInput(logical_name, None, None)
            continue
        path = _select(logical_name, matches, specification.get("selection", "exact"))
        _verify_columns(logical_name, path, specification.get("required_columns"))
        digest = sha256_file(path)
        expected_hash = specification.get("sha256")
        if expected_hash is not None and expected_hash != digest:
            raise DiscoveryError(f"logical source '{logical_name}' failed SHA-256 validation")
        current = DiscoveredInput(
            logical_name=logical_name,
            relative_path=_sanitized_relative_path(path, root),
            sha256=digest,
            _canonical_path=path,
        )
        existing = discovered.get(logical_name)
        if existing is not None:
            if not _same_discovered_input(existing, current):
                raise DiscoveryError(f"logical source '{logical_name}' is inconsistent")
            continue
        discovered[logical_name] = current
        source_manifest = specification.get("source_manifest")
        if source_manifest is not None:
            if not isinstance(source_manifest, Mapping):
                raise DiscoveryError(
                    f"logical source '{logical_name}' has invalid source manifest config"
                )
            pending_source_manifests.append((path, source_manifest))
    for path, source_manifest in pending_source_manifests:
        for record_name, record in resolve_recorded_sources(
            root, path, source_manifest, known_sources=discovered
        ).items():
            if record_name in discovered:
                existing = discovered[record_name]
                existing_historical_count = _historical_manifest_count(existing)
                record_historical_count = _historical_manifest_count(record)
                if existing_historical_count is not None and record_historical_count is not None:
                    discovered[record_name] = _historical_manifest_record(
                        existing_historical_count + record_historical_count
                    )
                    continue
                if not _same_discovered_input(existing, record):
                    raise DiscoveryError(f"logical source '{record_name}' is inconsistent")
                continue
            discovered[record_name] = record
    for path_map_name, resolution in path_map_resolutions:
        source_manifest_name = resolution.get("source_manifest_logical_name")
        if not isinstance(source_manifest_name, str):
            raise DiscoveryError("path-map source configuration is invalid")
        path_map_input = discovered.get(path_map_name)
        source_manifest_input = discovered.get(source_manifest_name)
        if (
            path_map_input is None
            or source_manifest_input is None
            or path_map_input._canonical_path is None
            or source_manifest_input._canonical_path is None
        ):
            raise DiscoveryError("path-map source configuration is incomplete")
        resolution_result = resolve_path_map_sources(
            root,
            path_map_input._canonical_path,
            source_manifest_input._canonical_path,
            resolution,
        )
        discovered[source_manifest_name] = DiscoveredInput(
            logical_name=source_manifest_input.logical_name,
            relative_path=source_manifest_input.relative_path,
            sha256=source_manifest_input.sha256,
            legacy={
                "status": "source_manifest",
                "snapshot_date": resolution_result.snapshot_date,
            },
            _canonical_path=source_manifest_input._canonical_path,
        )
        for logical_name, record in resolution_result.sources.items():
            specification = logical_inputs[logical_name]
            if not isinstance(specification, Mapping):
                raise DiscoveryError("path-map source configuration is invalid")
            if record.legacy is not None:
                if logical_name in discovered:
                    raise DiscoveryError(f"logical source '{logical_name}' is inconsistent")
                discovered[logical_name] = record
                continue
            if record._canonical_path is None:
                raise DiscoveryError("path-map source configuration is invalid")
            _verify_columns(
                logical_name, record._canonical_path, specification.get("required_columns")
            )
            if logical_name in discovered and not _same_discovered_input(
                discovered[logical_name], record
            ):
                raise DiscoveryError(f"logical source '{logical_name}' is inconsistent")
            discovered[logical_name] = record
    return discovered


def _config_companion_path(config_path: Path, value: str, description: str) -> Path:
    config_directory = config_path.parent.resolve()
    candidate = (config_directory / value).resolve()
    if Path(value).is_absolute() or not candidate.is_relative_to(config_directory):
        raise DiscoveryError(f"{description} must be beneath config directory")
    return candidate


def _is_string_list(value: object, expected: list[str]) -> bool:
    return (
        isinstance(value, list)
        and value == expected
        and all(isinstance(item, str) for item in value)
    )


def _validate_ppmi_target_config(target_config: Mapping[str, object]) -> None:
    required_top_level_keys = {
        "subject_id_column",
        "visit_column",
        "date_column",
        "change_direction",
        "selection",
        "month_horizons",
        "tables",
        "candidates",
        "part_iii_state",
        "task_thresholds",
        "target_confirmed",
    }
    required_text = ("subject_id_column", "visit_column", "date_column")
    if (
        set(target_config) != required_top_level_keys
        or any(
            not isinstance(target_config.get(name), str) or not target_config[name]
            for name in required_text
        )
        or target_config.get("change_direction") != "followup_total - baseline_total"
        or target_config.get("target_confirmed") is not True
    ):
        raise DiscoveryError("target configuration is invalid")
    if target_config.get("selection") != {
        "primary_target": "candidate_A",
        "target_definition": "MDS-UPDRS Part III follow-up score minus baseline score",
        "primary_policy": "prefer_off",
        "secondary_targets": ["candidate_B"],
        "sensitivity_policies": ["unique_only", "prefer_on"],
    }:
        raise DiscoveryError("target configuration is invalid")
    thresholds = target_config.get("task_thresholds")
    if thresholds != {"stress_test": 120, "ready": 180}:
        raise DiscoveryError("target configuration is invalid")
    horizons = target_config.get("month_horizons")
    expected_horizons: dict[str, Mapping[str, object]] = {
        "baseline": {"selector": "code_list_event_id", "event_id": "BL"},
        "month12": {"selector": "code_list_month", "month": 12, "event_id_prefix": "V"},
        "month24": {"selector": "code_list_month", "month": 24, "event_id_prefix": "V"},
        "month48": {"selector": "code_list_month", "month": 48, "event_id_prefix": "V"},
    }
    if not isinstance(horizons, Mapping) or dict(horizons) != expected_horizons:
        raise DiscoveryError("target configuration is invalid")
    expected_parts = {
        "part_i_clinician": (
            "mds_updrs_part_i_clinician",
            "NUPDRS1",
            "NUPDRS1",
            "^NP1[A-Z]+$",
            "NP1RTOT",
            6,
        ),
        "part_i_patient": (
            "mds_updrs_part_i_patient",
            "NUPDRS1P",
            "NUPDRS1P2P",
            "^NP1[A-Z]+$",
            "NP1PTOT",
            7,
        ),
        "part_ii": (
            "mds_updrs_part_ii_patient",
            "NUPDRS2P",
            "NUPDRS1P2P",
            "^NP2[A-Z]+$",
            "NP2PTOT",
            13,
        ),
        "part_iii": (
            "mds_updrs_part_iii_motor",
            "NUPDRS3TRT",
            "NUPDRDOSE3",
            "^NP3[A-Z]+$",
            "NP3TOT",
            33,
        ),
    }
    tables = target_config.get("tables")
    if not isinstance(tables, Mapping) or set(tables) != set(expected_parts):
        raise DiscoveryError("target configuration is invalid")
    for part, (source, module, page, item_name_regex, total, item_count) in expected_parts.items():
        table = tables.get(part)
        if (
            not isinstance(table, Mapping)
            or set(table) != {"source", "dictionary_selector"}
            or table.get("source") != source
        ):
            raise DiscoveryError("target configuration is invalid")
        selector = table.get("dictionary_selector")
        configured_regex = (
            selector.get("item_name_regex") if isinstance(selector, Mapping) else None
        )
        if (
            not isinstance(configured_regex, str)
            or not configured_regex
            or not configured_regex.startswith("^")
            or not configured_regex.endswith("$")
        ):
            raise DiscoveryError("target configuration is invalid")
        try:
            re.compile(configured_regex)
        except re.error as error:
            raise DiscoveryError("target configuration is invalid") from error
        if not isinstance(selector, Mapping) or dict(selector) != {
            "modules": [module],
            "pages": [page],
            "item_name_regex": item_name_regex,
            "official_total_column": total,
            "expected_item_count": item_count,
        }:
            raise DiscoveryError("target configuration is invalid")
    candidates = target_config.get("candidates")
    if candidates != {
        "candidate_A": {"parts": ["part_iii"]},
        "candidate_B": {"parts": ["part_i_clinician", "part_i_patient", "part_ii", "part_iii"]},
    }:
        raise DiscoveryError("target configuration is invalid")
    state = target_config.get("part_iii_state")
    expected_fields = {
        "PDSTATE": {"off_values": ["OFF"], "on_values": ["ON"]},
        "OFFEXAM": {"off_values": ["1"], "on_values": []},
        "ONEXAM": {"off_values": [], "on_values": ["1"]},
    }
    expected_policies = {
        "unique_only": {"enabled": True},
        "prefer_off": {"enabled": True},
        "prefer_on": {"enabled": True},
    }
    if (
        not isinstance(state, Mapping)
        or set(state)
        != {
            "primary_field",
            "fields",
            "audit_only_fields",
            "policies",
            "confirmed",
        }
        or state.get("primary_field") != "PDSTATE"
        or state.get("fields") != expected_fields
        or not _is_string_list(
            state.get("audit_only_fields"),
            ["PDMEDYN", "HRPOSTMED", "DBSYN", "HRDBSON", "HRDBSOFF", "ONOFFORDER"],
        )
        or state.get("policies") != expected_policies
        or state.get("confirmed") is not True
    ):
        raise DiscoveryError("target configuration is invalid")


def load_ppmi_target_config(config_path: Path) -> Mapping[str, object]:
    """Load the strict, config-directory-confined PPMI target contract."""
    cohort_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(cohort_config, Mapping):
        raise DiscoveryError("target configuration is invalid")
    target_config_name = cohort_config.get("target_config")
    if not isinstance(target_config_name, str):
        raise DiscoveryError("target_config must be a relative filename")
    try:
        target_config = yaml.safe_load(
            _config_companion_path(config_path, target_config_name, "target_config").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, yaml.YAMLError) as error:
        raise DiscoveryError("target configuration cannot be read") from error
    if not isinstance(target_config, Mapping):
        raise DiscoveryError("target configuration is invalid")
    _validate_ppmi_target_config(target_config)
    return target_config


def load_logical_inputs(config_path: Path) -> Mapping[str, Mapping[str, object]]:
    """Load only the logical-input portion of a YAML cohort configuration."""
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping) or not isinstance(data.get("logical_inputs"), Mapping):
        raise DiscoveryError("configuration must define logical_inputs")
    logical_inputs = data["logical_inputs"]
    column_map_path = data.get("column_map")
    if column_map_path is None:
        column_map: Mapping[str, object] = {}
    elif isinstance(column_map_path, str):
        loaded_column_map = yaml.safe_load(
            _config_companion_path(config_path, column_map_path, "column map").read_text(
                encoding="utf-8"
            )
        )
        if not isinstance(loaded_column_map, Mapping):
            raise DiscoveryError("column map must be a mapping")
        column_map = loaded_column_map
    else:
        raise DiscoveryError("column_map must be a relative filename")
    aliases_file = data.get("aliases_file")
    if aliases_file is not None:
        if not isinstance(aliases_file, str):
            raise DiscoveryError("aliases_file must be a relative filename")
        aliases = yaml.safe_load(
            _config_companion_path(config_path, aliases_file, "aliases_file").read_text(
                encoding="utf-8"
            )
        )
        groups = data.get("required_alias_groups", [])
        if (
            not isinstance(aliases, Mapping)
            or not isinstance(groups, list)
            or any(not isinstance(group, str) or group not in aliases for group in groups)
        ):
            raise DiscoveryError("aliases configuration is incomplete")
    resolved_inputs: dict[str, Mapping[str, object]] = {}
    for name, definition in logical_inputs.items():
        if not isinstance(name, str) or not isinstance(definition, Mapping):
            raise DiscoveryError("logical_inputs must map names to definitions")
        resolved_definition = dict(definition)
        signature = resolved_definition.pop("column_signature", None)
        if signature is not None:
            if not isinstance(signature, list) or not all(
                isinstance(field, str) for field in signature
            ):
                raise DiscoveryError("column_signature must be a list of column-map fields")
            columns = [column_map.get(field) for field in signature]
            if not all(isinstance(column, str) and column for column in columns):
                raise DiscoveryError("column_signature references an unknown column-map field")
            resolved_definition["required_columns"] = columns
        resolved_inputs[name] = resolved_definition
    return resolved_inputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Discover metadata without printing records.")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--metadata-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        logical_inputs = load_logical_inputs(arguments.config)
        results = discover_logical_inputs(arguments.metadata_root, logical_inputs)
        output = arguments.output_dir / "metadata_discovery.json"
        payload = [
            {
                "logical_name": result.logical_name,
                "relative_path": result.relative_path,
                "sha256": result.sha256,
                "legacy": result.legacy,
            }
            for result in results.values()
        ]
        if not arguments.dry_run:
            arguments.output_dir.mkdir(parents=True, exist_ok=True)
            serialized = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
            output.write_text(serialized, encoding="utf-8")
        for result in results.values():
            digest = result.sha256
            if digest is None and result.legacy is not None:
                digest = str(result.legacy["content_hash"] or "not_available")
            print(
                f"{result.logical_name}\t{result.relative_path or 'aggregate-only'}"
                f"\t{output.name}\t{digest}"
            )
    except DiscoveryError as error:
        print(f"discovery failed: {error}")
        return 2
    except (OSError, yaml.YAMLError):
        print("discovery failed: configuration or metadata input cannot be read")
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
