from dataclasses import FrozenInstanceError

import pytest

from canospar.contracts.base import (
    ArtifactMeta,
    BandKey,
    GraphKey,
    ScienceContext,
    TokenKey,
    build_reproduction_key,
    build_science_key,
)


def make_context(*, config_hash: str = "config-a") -> ScienceContext:
    return ScienceContext(
        science_contract_version="1.1.0",
        science_config_hash=config_hash,
        dataset_manifest_hash="manifest-a",
        split_id="outer-0",
        random_seed=7,
    )


def make_meta() -> ArtifactMeta:
    return ArtifactMeta(
        schema_version="1.0.0",
        artifact_type="SyntheticArtifact",
        artifact_id="artifact-a",
        producer_module="M1",
        module_contract_version="1.0.0",
        science_contract_version="1.1.0",
        input_artifact_ids=("input-a",),
        input_content_hashes=("hash-a",),
        science_config_hash="config-a",
        dataset_manifest_hash="manifest-a",
        split_id="outer-0",
        random_seed=7,
        content_sha256="content-a",
        implementation_hash="impl-a",
        numerics_profile_hash="numerics-a",
        created_at_utc="2026-08-17T00:00:00Z",
    )


def test_artifact_meta_is_frozen_and_preserves_input_tuples() -> None:
    meta = make_meta()

    assert meta.input_artifact_ids == ("input-a",)
    assert meta.input_content_hashes == ("hash-a",)
    with pytest.raises(FrozenInstanceError):
        meta.artifact_id = "changed"  # type: ignore[misc]


def test_science_key_is_deterministic_and_excludes_runtime_values() -> None:
    context = make_context()

    first = build_science_key(context, ("hash-a", "hash-b"), "M1", runtime_profile_id="cpu-a")
    second = build_science_key(context, ("hash-a", "hash-b"), "M1", runtime_profile_id="gpu-b")

    assert first == second
    assert len(first) == 64


def test_science_config_changes_science_key() -> None:
    first = build_science_key(make_context(config_hash="config-a"), ("hash-a",), "M1")
    second = build_science_key(make_context(config_hash="config-b"), ("hash-a",), "M1")

    assert first != second


def test_reproduction_key_tracks_implementation_and_numerics() -> None:
    science_key = "a" * 64

    first = build_reproduction_key(science_key, "impl-a", "numerics-a")
    changed_implementation = build_reproduction_key(science_key, "impl-b", "numerics-a")
    changed_numerics = build_reproduction_key(science_key, "impl-a", "numerics-b")

    assert first != changed_implementation
    assert first != changed_numerics
    assert len(first) == 64


def test_artifact_key_hierarchy_is_immutable() -> None:
    graph_key = GraphKey("subject-a", "visit-a", "smri", "morphology")
    band_key = BandKey(graph_key, "band-0")
    token_key = TokenKey(band_key, "token-0")

    assert token_key.band_key.graph_key == graph_key
    assert token_key.band_key.band_id == "band-0"
