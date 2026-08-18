from __future__ import annotations

import pytest
import torch

from canospar.api.m2 import build_normalized_laplacian
from canospar.contracts.base import ArtifactMeta, ScienceContext
from canospar.contracts.errors import ContractViolation
from canospar.contracts.spectral import M2Spec
from canospar.data.contracts import GraphData


def make_meta() -> ArtifactMeta:
    return ArtifactMeta(
        schema_version="1.0.0",
        artifact_type="MultiGraphArtifact",
        artifact_id="parent-a",
        producer_module="M1",
        module_contract_version="1.1.0",
        science_contract_version="1.1.0",
        input_artifact_ids=(),
        input_content_hashes=(),
        science_config_hash="config-a",
        dataset_manifest_hash="manifest-a",
        split_id="outer-0",
        random_seed=7,
        content_sha256="parent-content-a",
        implementation_hash="m1-impl-a",
        numerics_profile_hash="numerics-a",
        created_at_utc="2026-08-18T00:00:00Z",
    )


def make_graph(
    *,
    edge_index: torch.Tensor | None = None,
    edge_weight: torch.Tensor | None = None,
    num_nodes: int = 3,
) -> GraphData:
    if edge_index is None:
        edge_index = torch.tensor([[0, 1], [1, 0]], dtype=torch.long)
    if edge_weight is None:
        edge_weight = torch.ones(edge_index.size(1), dtype=torch.float64)
    return GraphData(
        x=torch.arange(num_nodes, dtype=torch.float64).reshape(num_nodes, 1),
        edge_index=edge_index,
        edge_weight=edge_weight,
        num_nodes=num_nodes,
        modality="smri",
        relation="morphology",
        graph_qc={"synthetic": 1.0},
        construction_hash="construction-a",
    )


def make_laplacian(graph: GraphData):
    return build_normalized_laplacian(
        graph,
        M2Spec(backend="numpy"),
        ScienceContext(science_config_hash="config-a"),
        parent_meta=make_meta(),
    )


def test_normalized_laplacian_is_symmetric_and_preserves_shape_and_graph_key() -> None:
    graph = make_graph()
    artifact = make_laplacian(graph)

    assert artifact.payload.shape == (3, 3)
    assert artifact.graph_key.modality == "smri"
    assert artifact.graph_key.relation == "morphology"
    assert torch.allclose(artifact.payload, artifact.payload.T)
    assert torch.isfinite(artifact.payload).all()
    expected = torch.tensor(
        [[1.0, -1.0, 0.0], [-1.0, 1.0, 0.0], [0.0, 0.0, 0.0]],
        dtype=torch.float64,
    )
    assert torch.allclose(artifact.payload, expected)


def test_isolated_node_is_retained_with_zero_normalized_identity_diagonal() -> None:
    artifact = make_laplacian(make_graph())
    assert artifact.payload.size(0) == 3
    assert artifact.payload[2, 2].item() == pytest.approx(0.0)


@pytest.mark.parametrize(
    ("edge_index", "edge_weight", "message"),
    [
        (
            torch.tensor([[0, 1], [1, 0]], dtype=torch.long),
            torch.tensor([-1.0, -1.0]),
            "negative",
        ),
        (
            torch.tensor([[0], [1]], dtype=torch.long),
            torch.tensor([1.0]),
            "symmetric",
        ),
        (
            torch.tensor([[0], [0]], dtype=torch.long),
            torch.tensor([1.0]),
            "self-loop",
        ),
        (
            torch.tensor([[0, 1], [1, 0]], dtype=torch.long),
            torch.tensor([1.0, float("nan")]),
            "finite",
        ),
    ],
)
def test_invalid_graph_policies_fail_closed(
    edge_index: torch.Tensor,
    edge_weight: torch.Tensor,
    message: str,
) -> None:
    with pytest.raises((ValueError, ContractViolation), match=message):
        make_laplacian(make_graph(edge_index=edge_index, edge_weight=edge_weight))


def test_laplacian_does_not_mutate_graph_tensors() -> None:
    graph = make_graph()
    edge_index_before = graph.edge_index.clone()
    edge_weight_before = graph.edge_weight.clone()
    x_before = graph.x.clone()

    make_laplacian(graph)

    assert torch.equal(graph.edge_index, edge_index_before)
    assert torch.equal(graph.edge_weight, edge_weight_before)
    assert torch.equal(graph.x, x_before)
