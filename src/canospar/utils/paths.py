"""Project-root discovery and safe output-directory creation."""

from __future__ import annotations

from pathlib import Path

_PROJECT_MARKER = "pyproject.toml"
_RESTRICTED_DIRECTORY_NAMES = frozenset({"data", "raw", "derivatives", "bids", "hcp", "ppmi"})


def find_project_root(start: Path | None = None) -> Path:
    """Find the nearest ancestor containing ``pyproject.toml``.

    ``start`` may name either a directory or an existing file. The returned
    root is absolute and has symlinks resolved.
    """
    candidate = (start if start is not None else Path.cwd()).resolve()
    if candidate.is_file():
        candidate = candidate.parent

    for directory in (candidate, *candidate.parents):
        if (directory / _PROJECT_MARKER).is_file():
            return directory
    raise FileNotFoundError(f"Could not find {_PROJECT_MARKER} above {candidate}")


def _contains_restricted_directory(path: Path, boundary: Path) -> bool:
    relative_parts = path.relative_to(boundary).parts
    return any(part.casefold() in _RESTRICTED_DIRECTORY_NAMES for part in relative_parts)


def ensure_safe_output_dir(
    path: Path,
    *,
    project_root: Path,
    allowed_external_root: Path | None = None,
) -> Path:
    """Create and return an approved output directory.

    Project-local outputs must be descendants of ``project_root / 'artifacts'``.
    A caller may opt into a separate root with ``allowed_external_root``. Paths
    using lexical parent traversal, unapproved roots, and dataset/source
    directories are rejected before anything is created.
    """
    raw_path = Path(path)
    if ".." in raw_path.parts:
        raise ValueError("Output path must not use parent traversal")

    root = Path(project_root).resolve()
    candidate = (raw_path if raw_path.is_absolute() else root / raw_path).resolve()
    artifacts_root = (root / "artifacts").resolve()
    external_root = Path(allowed_external_root).resolve() if allowed_external_root else None
    if external_root is not None and external_root.name.casefold() in _RESTRICTED_DIRECTORY_NAMES:
        raise ValueError("Output path targets a restricted project directory")

    if candidate.is_relative_to(root):
        if _contains_restricted_directory(candidate, root):
            raise ValueError("Output path targets a restricted project directory")
        if not candidate.is_relative_to(artifacts_root):
            raise ValueError("Project output paths must be inside the artifacts directory")
    elif external_root is not None and candidate.is_relative_to(external_root):
        if _contains_restricted_directory(candidate, external_root):
            raise ValueError("Output path targets a restricted project directory")
    else:
        raise ValueError("Output path is outside the approved output roots")

    candidate.mkdir(parents=True, exist_ok=True)
    return candidate
