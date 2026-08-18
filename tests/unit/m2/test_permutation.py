from __future__ import annotations

import pytest
import torch

from canospar.api.m2 import (
    build_normalized_laplacian,
    compute_spectral_statistics,
    compute_spectrum,
)
from canospar.contracts.base import ArtifactMeta, ScienceContext
from canospar.contracts.spectral import M2Spec
from canospar.data.contracts import GraphData
from canospar.spectral.laplacian import build_unweighted_topology


def _meta(name: str) -> ArtifactMeta:
    return ArtifactMeta(
        schema_version="1.0.0",
        artifact_type="MultiGraphArtifact",
        artifact_id=f"parent-{name}",
        producer_module="M1",
        module_contract_version="1.1.0",
        science_contract_version="1.1.0",
        input_artifact_ids=(),
        input_content_hashes=(),
        science_config_hash="perm-config",
        dataset_manifest_hash="perm-manifest",
        split_id="perm",
        random_seed=1,
        content_sha256=f"content-{name}",
        implementation_hash="perm-m1",
        numerics_profile_hash="perm-num",
        created_at_utc="2026-08-18T00:00:00Z",
    )


def _graph(permutation: torch.Tensor | None = None) -> GraphData:
    edges = torch.tensor([[0, 1, 1, 2, 2, 3], [1, 0, 2, 1, 3, 2]], dtype=torch.long)
    x = torch.tensor([[1.0], [2.0], [4.0], [8.0]], dtype=torch.float64)
    if permutation is not None:
        inverse = torch.argsort(permutation)
        edges = permutation[edges]
        x = x[inverse]
    return GraphData(
        x=x,
        edge_index=edges,
        edge_weight=torch.ones(6, dtype=torch.float64),
        num_nodes=4,
        modality="smri",
        relation="morphology",
        graph_qc={"synthetic": 1.0},
        construction_hash="perm-graph",
    )


def test_graph_permutation_preserves_spectrum_statistics_and_energy() -> None:
    context = ScienceContext(
        science_config_hash="perm-config",
        dataset_manifest_hash="perm-manifest",
        split_id="perm",
        random_seed=1,
    )
    spec = M2Spec(backend="numpy")
    original = _graph()
    permuted = _graph(torch.tensor([2, 0, 3, 1], dtype=torch.long))
    laplacian_a = build_normalized_laplacian(original, spec, context, parent_meta=_meta("a"))
    laplacian_b = build_normalized_laplacian(permuted, spec, context, parent_meta=_meta("b"))
    spectrum_a = compute_spectrum(laplacian_a, spec, context)
    spectrum_b = compute_spectrum(laplacian_b, spec, context)
    stats_a = compute_spectral_statistics(
        laplacian_a,
        spectrum_a,
        original.x,
        context,
        topology=build_unweighted_topology(original),
    )
    stats_b = compute_spectral_statistics(
        laplacian_b,
        spectrum_b,
        permuted.x,
        context,
        topology=build_unweighted_topology(permuted),
    )

    permutation = torch.zeros((4, 4), dtype=torch.float64)
    order = torch.tensor([2, 0, 3, 1])
    permutation[order, torch.arange(4)] = 1.0
    assert torch.allclose(laplacian_b.payload, permutation @ laplacian_a.payload @ permutation.T)
    assert torch.allclose(spectrum_a.eigenvalues, spectrum_b.eigenvalues)
    for key in stats_a.values:
        assert stats_a.values[key] == pytest.approx(stats_b.values[key], abs=1e-12)
