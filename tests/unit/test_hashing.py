from __future__ import annotations

import hashlib
import math
from pathlib import Path

import pytest
from omegaconf import OmegaConf
from omegaconf.errors import InterpolationKeyError

from canospar.utils.hashing import (
    hash_files,
    hash_json,
    hash_yaml_config,
    sha256_bytes,
    sha256_file,
)


def test_sha256_bytes_matches_known_vector() -> None:
    assert (
        sha256_bytes(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_sha256_file_hashes_file_contents(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_bytes(b"abc")

    assert sha256_file(source) == sha256_bytes(b"abc")


def test_sha256_file_changes_when_contents_change(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("first", encoding="utf-8")
    first_hash = sha256_file(source)
    source.write_text("second", encoding="utf-8")

    assert sha256_file(source) != first_hash


def test_hash_json_ignores_mapping_order() -> None:
    assert hash_json({"a": 1, "b": 2}) == hash_json({"b": 2, "a": 1})


def test_hash_json_uses_compact_canonical_json() -> None:
    expected = hashlib.sha256(b'{"a":1,"b":2}').hexdigest()

    assert hash_json({"b": 2, "a": 1}) == expected


def test_hash_json_stabilizes_nested_mappings() -> None:
    first = {"outer": {"z": [3, {"b": True, "a": None}], "a": "value"}}
    second = {"outer": {"a": "value", "z": [3, {"a": None, "b": True}]}}

    assert hash_json(first) == hash_json(second)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_hash_json_rejects_non_finite_floats(value: float) -> None:
    with pytest.raises(ValueError):
        hash_json({"value": value})


def test_hash_yaml_config_ignores_mapping_order() -> None:
    assert hash_yaml_config({"model": {"width": 4}, "seed": 3}) == hash_yaml_config(
        {"seed": 3, "model": {"width": 4}}
    )


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_hash_yaml_config_rejects_non_finite_floats(value: float) -> None:
    with pytest.raises(ValueError):
        hash_yaml_config({"learning_rate": value})


def test_hash_yaml_config_accepts_omegaconf_config() -> None:
    config = OmegaConf.create({"model": {"width": 4}, "seed": 3})

    assert hash_yaml_config(config) == hash_yaml_config({"seed": 3, "model": {"width": 4}})


def test_hash_yaml_config_resolves_omegaconf_interpolation() -> None:
    config = OmegaConf.create({"seed": 3, "run": {"seed": "${seed}"}})

    assert hash_yaml_config(config) == hash_yaml_config({"seed": 3, "run": {"seed": 3}})


def test_hash_yaml_config_rejects_missing_omegaconf_interpolation() -> None:
    config = OmegaConf.create({"run": {"seed": "${missing_seed}"}})

    with pytest.raises(InterpolationKeyError):
        hash_yaml_config(config)


def test_hash_files_is_deterministic_and_order_sensitive(tmp_path: Path) -> None:
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")

    ordered_hash = hash_files([first, second])

    assert ordered_hash == hash_files([first, second])
    assert ordered_hash != hash_files([second, first])


def test_hash_files_does_not_depend_on_absolute_paths(tmp_path: Path) -> None:
    original = tmp_path / "private-root-a" / "input.txt"
    relocated = tmp_path / "private-root-b" / "input.txt"
    original.parent.mkdir()
    relocated.parent.mkdir()
    original.write_text("same content", encoding="utf-8")
    relocated.write_text("same content", encoding="utf-8")

    assert hash_files([original]) == hash_files([relocated])
