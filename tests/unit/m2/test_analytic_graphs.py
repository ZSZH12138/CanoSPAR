from __future__ import annotations

import pytest
import torch

from canospar.api.m2 import build_normalized_laplacian, compute_spectrum
from canospar.contracts.base import ArtifactMeta, ScienceContext
from canospar.contracts.spectral import M2Spec
from canospar.data.contracts import GraphData


def _meta() -> ArtifactMeta:
    return ArtifactMeta(
        schema_version="1.0.0",
        artifact_type="MultiGraphArtifact",
        artifact_id="parent-analytic",
        producer_module="M1",
        module_contract_version="1.1.0",
        science_contract_version="1.1.0",
        input_artifact_ids=(),
        input_content_hashes=(),
        science_config_hash="analytic-config",
        dataset_manifest_hash="synthetic-manifest",
        split_id="synthetic",
        random_seed=1,
        content_sha256="analytic-parent-content",
        implementation_hash="m1-analytic",
        numerics_profile_hash="analytic-numerics",
        created_at_utc="2026-08-18T00:00:00Z",
    )


def _graph(num_nodes: int, edges: list[tuple[int, int]], name: str) -> GraphData:
    edge_index = (
        torch.tensor(edges, dtype=torch.long).T.contiguous()
        if edges
        else torch.empty((2, 0), dtype=torch.long)
    )
    return GraphData(
        x=torch.ones((num_nodes, 1), dtype=torch.float64),
        edge_index=edge_index,
        edge_weight=torch.ones(edge_index.size(1), dtype=torch.float64),
        num_nodes=num_nodes,
        modality="smri",
        relation=name,
        graph_qc={"synthetic": 1.0},
        construction_hash=f"construction-{name}",
    )


def _spectrum(graph: GraphData):
    context = ScienceContext(science_config_hash="analytic-config")
    spec = M2Spec(backend="numpy")
    return compute_spectrum(
        build_normalized_laplacian(graph, spec, context, parent_meta=_meta()), spec, context
    ).eigenvalues


@pytest.mark.parametrize(
    ("name", "num_nodes", "edges", "expected"),
    [
        (
            "complete",
            4,
            [
                (0, 1),
                (1, 0),
                (0, 2),
                (2, 0),
                (0, 3),
                (3, 0),
                (1, 2),
                (2, 1),
                (1, 3),
                (3, 1),
                (2, 3),
                (3, 2),
            ],
            [0.0, 4 / 3, 4 / 3, 4 / 3],
        ),
        (
            "path",
            4,
            [(0, 1), (1, 0), (1, 2), (2, 1), (2, 3), (3, 2)],
            [0.0, 0.5, 1.5, 2.0],
        ),
        (
            "cycle",
            4,
            [(0, 1), (1, 0), (1, 2), (2, 1), (2, 3), (3, 2), (3, 0), (0, 3)],
            [0.0, 1.0, 1.0, 2.0],
        ),
        (
            "disconnected",
            4,
            [(0, 1), (1, 0), (2, 3), (3, 2)],
            [0.0, 0.0, 2.0, 2.0],
        ),
        (
            "isolated",
            4,
            [(0, 1), (1, 0)],
            [0.0, 0.0, 0.0, 2.0],
        ),
    ],
)
def test_analytic_graph_eigenvalues(
    name: str,
    num_nodes: int,
    edges: list[tuple[int, int]],
    expected: list[float],
) -> None:
    actual = _spectrum(_graph(num_nodes, edges, name))
    assert torch.allclose(actual, torch.tensor(expected, dtype=torch.float64), atol=1e-8, rtol=1e-8)
