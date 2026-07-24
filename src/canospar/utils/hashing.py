"""Deterministic, content-based hashing helpers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TypeAlias, cast

import yaml
from omegaconf import OmegaConf

JsonPrimitive: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]


def sha256_bytes(data: bytes) -> str:
    """Return the SHA-256 digest of *data* as lowercase hexadecimal."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a file's contents."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json_bytes(value: JsonValue) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def hash_json(value: JsonValue) -> str:
    """Hash JSON-compatible data with a canonical key order and encoding."""
    return sha256_bytes(_canonical_json_bytes(value))


def hash_yaml_config(config: Any) -> str:
    """Hash a JSON-compatible configuration in canonical YAML form.

    Canonical JSON validation occurs before YAML serialization so NaN and
    infinity are rejected instead of being represented by YAML-specific values.
    """
    plain_config = (
        OmegaConf.to_container(config, resolve=True, throw_on_missing=True)
        if OmegaConf.is_config(config)
        else config
    )
    normalized = json.loads(_canonical_json_bytes(cast(JsonValue, plain_config)))
    serialized = yaml.safe_dump(
        normalized,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=True,
    )
    return sha256_bytes(serialized.encode("utf-8"))


def hash_files(paths: Sequence[Path]) -> str:
    """Hash file contents in caller-supplied sequence order.

    Absolute paths are deliberately excluded so the digest can be reproduced
    after relocating a dataset. Each position is encoded separately, making
    the order of ``paths`` part of the hash contract.
    """
    digest = hashlib.sha256()
    for index, path in enumerate(paths):
        digest.update(index.to_bytes(8, byteorder="big", signed=False))
        digest.update(bytes.fromhex(sha256_file(path)))
    return digest.hexdigest()
