from __future__ import annotations

from pathlib import Path

import pytest

from canospar.utils.paths import ensure_safe_output_dir, find_project_root


def _make_project_root(tmp_path: Path) -> Path:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text("[project]\nname = 'example'\n", encoding="utf-8")
    return project_root


def test_find_project_root_searches_ancestor_directories(tmp_path: Path) -> None:
    project_root = _make_project_root(tmp_path)
    nested = project_root / "src" / "canospar" / "utils"
    nested.mkdir(parents=True)

    assert find_project_root(nested) == project_root.resolve()


def test_find_project_root_accepts_an_existing_file(tmp_path: Path) -> None:
    project_root = _make_project_root(tmp_path)
    source = project_root / "src" / "module.py"
    source.parent.mkdir()
    source.touch()

    assert find_project_root(source) == project_root.resolve()


def test_find_project_root_rejects_a_location_without_project_marker(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        find_project_root(tmp_path)


def test_ensure_safe_output_dir_creates_artifact_subdirectory(tmp_path: Path) -> None:
    project_root = _make_project_root(tmp_path)
    destination = project_root / "artifacts" / "smoke" / "run-001"

    result = ensure_safe_output_dir(destination, project_root=project_root)

    assert result == destination.resolve()
    assert result.is_dir()


def test_ensure_safe_output_dir_anchors_relative_paths_to_project_root(tmp_path: Path) -> None:
    project_root = _make_project_root(tmp_path)

    result = ensure_safe_output_dir(Path("artifacts") / "smoke", project_root=project_root)

    assert result == (project_root / "artifacts" / "smoke").resolve()


def test_ensure_safe_output_dir_rejects_parent_traversal(tmp_path: Path) -> None:
    project_root = _make_project_root(tmp_path)

    with pytest.raises(ValueError, match="traversal"):
        ensure_safe_output_dir(
            project_root / "artifacts" / ".." / "escaped", project_root=project_root
        )


def test_ensure_safe_output_dir_rejects_artifacts_prefix_trap(tmp_path: Path) -> None:
    project_root = _make_project_root(tmp_path)
    unsafe = project_root / "artifacts_evil" / "run"

    with pytest.raises(ValueError, match="artifacts"):
        ensure_safe_output_dir(unsafe, project_root=project_root)


@pytest.mark.parametrize("restricted_name", ["data", "raw", "derivatives", "bids", "hcp", "ppmi"])
def test_ensure_safe_output_dir_rejects_restricted_project_directories(
    tmp_path: Path, restricted_name: str
) -> None:
    project_root = _make_project_root(tmp_path)

    with pytest.raises(ValueError, match="restricted"):
        ensure_safe_output_dir(
            project_root / restricted_name / "new-output", project_root=project_root
        )


def test_ensure_safe_output_dir_rejects_non_artifact_project_directory(tmp_path: Path) -> None:
    project_root = _make_project_root(tmp_path)
    destination = project_root / "reports" / "generated"

    with pytest.raises(ValueError, match="artifacts"):
        ensure_safe_output_dir(destination, project_root=project_root)

    assert not destination.exists()


def test_ensure_safe_output_dir_allows_explicit_external_root(tmp_path: Path) -> None:
    project_root = _make_project_root(tmp_path)
    external_root = tmp_path / "approved-external"
    destination = external_root / "run"

    result = ensure_safe_output_dir(
        destination,
        project_root=project_root,
        allowed_external_root=external_root,
    )

    assert result == destination.resolve()
    assert result.is_dir()


def test_ensure_safe_output_dir_rejects_unapproved_external_root(tmp_path: Path) -> None:
    project_root = _make_project_root(tmp_path)

    with pytest.raises(ValueError, match="outside"):
        ensure_safe_output_dir(tmp_path / "other" / "run", project_root=project_root)


def test_ensure_safe_output_dir_rejects_external_root_prefix_trap(tmp_path: Path) -> None:
    project_root = _make_project_root(tmp_path)
    allowed_external_root = tmp_path / "approved"
    unsafe = tmp_path / "approved-evil" / "run"

    with pytest.raises(ValueError, match="outside"):
        ensure_safe_output_dir(
            unsafe,
            project_root=project_root,
            allowed_external_root=allowed_external_root,
        )


@pytest.mark.parametrize("restricted_name", ["data", "raw", "derivatives", "bids", "hcp", "ppmi"])
def test_ensure_safe_output_dir_rejects_restricted_external_root_without_creating_it(
    tmp_path: Path, restricted_name: str
) -> None:
    project_root = _make_project_root(tmp_path)
    external_root = tmp_path / restricted_name
    destination = external_root / "run"

    with pytest.raises(ValueError, match="restricted"):
        ensure_safe_output_dir(
            destination,
            project_root=project_root,
            allowed_external_root=external_root,
        )

    assert not external_root.exists()
