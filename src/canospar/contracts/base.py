"""Immutable artifact metadata, scientific context, and stable identity keys."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from types import MappingProxyType
from typing import TypeVar, cast

from canospar.data.contracts import BrainMultiGraphSample

from .errors import ContractViolation
from .governance import SCIENCE_CONTRACT_VERSION

_MappingValue = TypeVar("_MappingValue")


def require_non_empty_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractViolation(f"{field_name} must be a non-empty string")
    return value


def _freeze_mapping(
    value: Mapping[str, _MappingValue],
    field_name: str,
) -> Mapping[str, _MappingValue]:
    if not isinstance(value, Mapping):
        raise ContractViolation(f"{field_name} must be a mapping")
    if any(not isinstance(key, str) for key in value):
        raise ContractViolation(f"{field_name} keys must be strings")
    return cast(
        Mapping[str, _MappingValue],
        MappingProxyType(deepcopy(dict(value))),
    )


def _freeze_string_tuple(
    values: Sequence[str],
    field_name: str,
) -> tuple[str, ...]:
    if isinstance(values, str):
        raise ContractViolation(f"{field_name} must be a sequence, not a string")
    frozen = tuple(values)
    for index, value in enumerate(frozen):
        require_non_empty_text(value, f"{field_name}[{index}]")
    return frozen


def _digest_parts(parts: Sequence[object]) -> str:
    digest_input = bytearray()
    for part in parts:
        encoded = json.dumps(
            part,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        digest_input.extend(len(encoded).to_bytes(8, "big"))
        digest_input.extend(encoded)
    return hashlib.sha256(bytes(digest_input)).hexdigest()


@dataclass(frozen=True)
class ScienceContext:
    science_contract_version: str = SCIENCE_CONTRACT_VERSION
    science_config_hash: str = ""
    dataset_manifest_hash: str | None = None
    split_id: str | None = None
    random_seed: int | None = None

    def __post_init__(self) -> None:
        require_non_empty_text(self.science_contract_version, "science_contract_version")
        require_non_empty_text(self.science_config_hash, "science_config_hash")
        if self.dataset_manifest_hash is not None:
            require_non_empty_text(self.dataset_manifest_hash, "dataset_manifest_hash")
        if self.split_id is not None:
            require_non_empty_text(self.split_id, "split_id")
        if isinstance(self.random_seed, bool) or (
            self.random_seed is not None and not isinstance(self.random_seed, int)
        ):
            raise ContractViolation("random_seed must be an integer or None")


@dataclass(frozen=True)
class ArtifactMeta:
    schema_version: str
    artifact_type: str
    artifact_id: str
    producer_module: str
    module_contract_version: str
    science_contract_version: str
    input_artifact_ids: tuple[str, ...]
    input_content_hashes: tuple[str, ...]
    science_config_hash: str
    dataset_manifest_hash: str | None
    split_id: str | None
    random_seed: int | None
    content_sha256: str
    implementation_hash: str
    numerics_profile_hash: str
    created_at_utc: str

    def __post_init__(self) -> None:
        for field_name in (
            "schema_version",
            "artifact_type",
            "artifact_id",
            "producer_module",
            "module_contract_version",
            "science_contract_version",
            "science_config_hash",
            "content_sha256",
            "implementation_hash",
            "numerics_profile_hash",
            "created_at_utc",
        ):
            require_non_empty_text(getattr(self, field_name), field_name)

        object.__setattr__(
            self,
            "input_artifact_ids",
            _freeze_string_tuple(self.input_artifact_ids, "input_artifact_ids"),
        )
        object.__setattr__(
            self,
            "input_content_hashes",
            _freeze_string_tuple(self.input_content_hashes, "input_content_hashes"),
        )
        if len(self.input_artifact_ids) != len(self.input_content_hashes):
            raise ContractViolation(
                "input_artifact_ids and input_content_hashes must have equal lengths"
            )
        if self.dataset_manifest_hash is not None:
            require_non_empty_text(self.dataset_manifest_hash, "dataset_manifest_hash")
        if self.split_id is not None:
            require_non_empty_text(self.split_id, "split_id")
        if isinstance(self.random_seed, bool) or (
            self.random_seed is not None and not isinstance(self.random_seed, int)
        ):
            raise ContractViolation("random_seed must be an integer or None")


@dataclass(frozen=True)
class GraphKey:
    subject: str
    visit: str
    modality: str
    relation: str

    def __post_init__(self) -> None:
        for field_name in ("subject", "visit", "modality", "relation"):
            require_non_empty_text(getattr(self, field_name), field_name)


@dataclass(frozen=True)
class BandKey:
    graph_key: GraphKey
    band_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.graph_key, GraphKey):
            raise ContractViolation("graph_key must be a GraphKey")
        require_non_empty_text(self.band_id, "band_id")


@dataclass(frozen=True)
class TokenKey:
    band_key: BandKey
    token_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.band_key, BandKey):
            raise ContractViolation("band_key must be a BandKey")
        require_non_empty_text(self.token_id, "token_id")


@dataclass(frozen=True)
class MultiGraphArtifact:
    meta: ArtifactMeta
    sample: BrainMultiGraphSample
    atlas_id: str
    atlas_hash: str
    roi_table_hash: str
    node_order_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.meta, ArtifactMeta):
            raise ContractViolation("meta must be ArtifactMeta")
        if not isinstance(self.sample, BrainMultiGraphSample):
            raise ContractViolation("sample must be BrainMultiGraphSample")
        for field_name in ("atlas_id", "atlas_hash", "roi_table_hash", "node_order_hash"):
            require_non_empty_text(getattr(self, field_name), field_name)


@dataclass(frozen=True)
class _IdentityInput:
    module_contract_version: str
    input_content_hashes: tuple[str, ...]
    science_contract_version: str
    science_config_hash: str
    dataset_manifest_hash: str | None
    split_id: str | None
    random_seed: int | None


def build_science_key(
    context: ScienceContext,
    input_content_hashes: Sequence[str],
    module_contract_version: str,
    *,
    runtime_profile_id: str | None = None,
) -> str:
    """Build a deterministic scientific identity; runtime_profile_id is ignored."""
    del runtime_profile_id
    if not isinstance(context, ScienceContext):
        raise ContractViolation("context must be ScienceContext")
    identity = _IdentityInput(
        module_contract_version=require_non_empty_text(
            module_contract_version,
            "module_contract_version",
        ),
        input_content_hashes=_freeze_string_tuple(
            input_content_hashes,
            "input_content_hashes",
        ),
        science_contract_version=context.science_contract_version,
        science_config_hash=context.science_config_hash,
        dataset_manifest_hash=context.dataset_manifest_hash,
        split_id=context.split_id,
        random_seed=context.random_seed,
    )
    return _digest_parts(
        (
            identity.module_contract_version,
            identity.input_content_hashes,
            identity.science_contract_version,
            identity.science_config_hash,
            identity.dataset_manifest_hash,
            identity.split_id,
            identity.random_seed,
        )
    )


def build_reproduction_key(
    science_key: str,
    implementation_hash: str,
    numerics_profile_hash: str,
) -> str:
    """Build a deterministic reproducibility identity."""
    return _digest_parts(
        (
            require_non_empty_text(science_key, "science_key"),
            require_non_empty_text(implementation_hash, "implementation_hash"),
            require_non_empty_text(numerics_profile_hash, "numerics_profile_hash"),
        )
    )
