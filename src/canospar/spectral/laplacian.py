"""Normalized Laplacian construction for validated M1 graphs."""

from __future__ import annotations

from dataclasses import dataclass

import torch

from canospar.contracts.base import ArtifactMeta, GraphKey, ScienceContext
from canospar.contracts.errors import ContractViolation, NumericalValidationError
from canospar.contracts.spectral import LaplacianArtifact, M2Spec
from canospar.data.contracts import GraphData

from .lineage import (
    fixed_graph_key,
    make_meta,
    numerics_profile,
    tensor_content_hash,
)


@dataclass(frozen=True)
class LaplacianComputation:
    payload: torch.Tensor
    adjacency: torch.Tensor


def _build_adjacency(graph: GraphData) -> torch.Tensor:
    graph.validate()
    edge_index = graph.edge_index.detach().cpu()
    edge_weight = graph.edge_weight.detach().cpu().to(torch.float64)
    if not bool(torch.isfinite(edge_weight).all()):
        raise ContractViolation("edge weights must be finite")
    if bool((edge_weight < 0).any()):
        raise ContractViolation("negative edge weights are rejected")
    if bool((edge_index[0] == edge_index[1]).any()):
        raise ContractViolation("self-loop edges are rejected")

    adjacency = torch.zeros((graph.num_nodes, graph.num_nodes), dtype=torch.float64)
    if edge_index.numel():
        adjacency.index_put_((edge_index[0], edge_index[1]), edge_weight, accumulate=True)
    if not bool(torch.isfinite(adjacency).all()):
        raise ContractViolation("adjacency must be finite")
    if not torch.equal(adjacency, adjacency.T):
        raise ContractViolation("adjacency must be symmetric")
    if bool((torch.diag(adjacency) != 0).any()):
        raise ContractViolation("adjacency must be self-loop-free")
    return adjacency


def build_unweighted_topology(graph: GraphData) -> torch.Tensor:
    """Return M1's undirected edge support without thresholding edge weights."""
    _build_adjacency(graph)
    edge_index = graph.edge_index.detach().cpu()
    topology = torch.zeros((graph.num_nodes, graph.num_nodes), dtype=torch.float64)
    if edge_index.numel():
        topology[edge_index[0], edge_index[1]] = 1.0
    topology.fill_diagonal_(0.0)
    if not torch.equal(topology, topology.T):
        raise ContractViolation("graph topology must be symmetric")
    return topology


def compute_normalized_laplacian(graph: GraphData) -> LaplacianComputation:
    adjacency = _build_adjacency(graph)
    degree = adjacency.sum(dim=1)
    if bool((degree < 0).any()) or not bool(torch.isfinite(degree).all()):
        raise NumericalValidationError("degree must be finite and non-negative")
    inverse_sqrt = torch.zeros_like(degree)
    non_isolated = degree > 0
    inverse_sqrt[non_isolated] = degree[non_isolated].rsqrt()
    normalized_adjacency = inverse_sqrt[:, None] * adjacency * inverse_sqrt[None, :]
    identity = torch.diag(non_isolated.to(torch.float64))
    laplacian = identity - normalized_adjacency
    if not bool(torch.isfinite(laplacian).all()):
        raise NumericalValidationError("normalized Laplacian must be finite")
    if not torch.equal(laplacian, laplacian.T):
        raise NumericalValidationError("normalized Laplacian must be symmetric")
    return LaplacianComputation(payload=laplacian, adjacency=adjacency)


def build_laplacian_artifact(
    graph: GraphData,
    spec: M2Spec,
    context: ScienceContext,
    *,
    parent_meta: ArtifactMeta,
    graph_key: GraphKey | None = None,
) -> LaplacianArtifact:
    if not isinstance(parent_meta, ArtifactMeta):
        raise ContractViolation("parent_meta must be ArtifactMeta")
    computation = compute_normalized_laplacian(graph)
    key = graph_key or fixed_graph_key(graph.modality, graph.relation)
    numerics_hash = numerics_profile(spec).numerics_profile_hash
    content_hash = tensor_content_hash(computation.payload)
    meta = make_meta(
        artifact_type="LaplacianArtifact",
        context=context,
        content_sha256=content_hash,
        input_artifact_ids=(parent_meta.artifact_id, f"graph:{graph.construction_hash}"),
        input_content_hashes=(parent_meta.content_sha256, graph.construction_hash),
        numerics_profile_hash=numerics_hash,
        graph_key=key,
        created_at_utc=parent_meta.created_at_utc,
    )
    return LaplacianArtifact(meta=meta, graph_key=key, payload=computation.payload)
