from __future__ import annotations

import pytest
import torch

from canospar.contracts.base import ArtifactMeta, GraphKey, ScienceContext
from canospar.contracts.spectral import CanonicalCoordinateSpec, SpectrumArtifact
from canospar.spectral.lineage import tensor_content_hash


@pytest.fixture
def context() -> ScienceContext:
    return ScienceContext(
        science_contract_version="1.1.0",
        science_config_hash="m3-unit-config",
        dataset_manifest_hash="m3-unit-manifest",
        split_id="m3-unit-split",
        random_seed=17,
    )


@pytest.fixture
def m2_context() -> ScienceContext:
    return ScienceContext(
        science_contract_version="1.1.0",
        science_config_hash="m2-synthetic-config",
        dataset_manifest_hash="synthetic-manifest",
        split_id="synthetic-outer-0",
        random_seed=13,
    )


@pytest.fixture
def coordinate_spec() -> CanonicalCoordinateSpec:
    return CanonicalCoordinateSpec(
        method="empirical_mid_cdf",
        parameters={
            "tie_atol": 0.0,
            "tie_rtol": 0.0,
            "empty_band_policy": "fail",
        },
    )


def make_spectrum(values: list[float], modality: str = "fmri") -> SpectrumArtifact:
    eigenvalues = torch.tensor(values, dtype=torch.float64)
    graph_key = GraphKey(
        subject="m3-subject",
        visit="baseline",
        modality=modality,
        relation="synthetic",
    )
    content_hash = tensor_content_hash(eigenvalues)
    meta = ArtifactMeta(
        schema_version="1.0.0",
        artifact_type="SpectrumArtifact",
        artifact_id=f"m2-spectrum-{modality}",
        producer_module="M2",
        module_contract_version="1.1.0",
        science_contract_version="1.1.0",
        input_artifact_ids=("m2-bundle",),
        input_content_hashes=("m2-bundle-content",),
        science_config_hash="m3-unit-config",
        dataset_manifest_hash="m3-unit-manifest",
        split_id="m3-unit-split",
        random_seed=17,
        content_sha256=content_hash,
        implementation_hash="m2-unit-implementation",
        numerics_profile_hash="m2-unit-numerics",
        created_at_utc="2026-08-19T00:00:00Z",
    )
    return SpectrumArtifact(meta=meta, graph_key=graph_key, eigenvalues=eigenvalues)


@pytest.fixture
def m2_bundle():
    from canospar.api.m2 import run_m2
    from tests.integration.test_m2_synthetic_multigraph import _artifact, _context, _spec

    return run_m2(_artifact(), _spec(), _context())
