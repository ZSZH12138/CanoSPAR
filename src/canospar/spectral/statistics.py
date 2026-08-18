"""Deterministic graph and spectral statistics for M2."""

from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np
import torch

from canospar.contracts.base import NodeFeatureMatrix, ScienceContext
from canospar.contracts.errors import ContractViolation, NumericalValidationError
from canospar.contracts.spectral import (
    LaplacianArtifact,
    M2Spec,
    SpectralStatistics,
    SpectrumArtifact,
)

from .lineage import (
    canonical_json_hash,
    dirichlet_epsilon,
    make_meta,
    numerics_profile,
    tensor_content_hash,
    tie_tolerance,
    zero_tolerance,
)

FIXED_STATISTIC_KEYS = (
    "num_nodes",
    "num_edges",
    "density",
    "mean_degree",
    "connected_components",
    "algebraic_connectivity",
    "zero_eigenvalue_count",
    "distinct_eigenvalue_count",
    "eigenvalue_q05",
    "eigenvalue_q25",
    "eigenvalue_q50",
    "eigenvalue_q75",
    "eigenvalue_q95",
    "spectral_entropy",
    "dirichlet_energy",
)


def _component_count(adjacency: torch.Tensor) -> int:
    n = adjacency.size(0)
    seen = [False] * n
    count = 0
    for start in range(n):
        if seen[start]:
            continue
        count += 1
        stack = [start]
        seen[start] = True
        while stack:
            node = stack.pop()
            neighbors = torch.nonzero(adjacency[node], as_tuple=False).flatten().tolist()
            for neighbor in neighbors:
                if not seen[int(neighbor)]:
                    seen[int(neighbor)] = True
                    stack.append(int(neighbor))
    return count


def _validate_topology(topology: torch.Tensor, num_nodes: int) -> torch.Tensor:
    if not isinstance(topology, torch.Tensor):
        raise ContractViolation("topology must be a torch.Tensor")
    if topology.dim() != 2 or topology.size(0) != num_nodes or topology.size(1) != num_nodes:
        raise ContractViolation("topology shape must match the Laplacian")
    topology = topology.detach().cpu().to(torch.float64)
    if not bool(torch.isfinite(topology).all()):
        raise ContractViolation("topology must be finite")
    if not torch.equal(topology, topology.T):
        raise ContractViolation("topology must be symmetric")
    if bool((topology < 0).any()) or bool(torch.diag(topology).ne(0).any()):
        raise ContractViolation("topology must be non-negative and self-loop-free")
    if not bool(((topology == 0) | (topology == 1)).all()):
        raise ContractViolation("topology must be binary")
    return topology


def _quantiles(values: np.ndarray) -> tuple[float, float, float, float, float]:
    quantiles = np.quantile(values, [0.05, 0.25, 0.50, 0.75, 0.95], method="linear")
    return tuple(float(value) for value in quantiles.tolist())  # type: ignore[return-value]


def _heat_trace(values: torch.Tensor, times: object) -> Mapping[str, float]:
    if isinstance(times, str | bytes) or not isinstance(times, list | tuple):
        raise ContractViolation("diffusion_times must be a sequence of positive finite numbers")
    result: dict[str, float] = {}
    for time in times:
        if isinstance(time, bool) or not isinstance(time, int | float) or not math.isfinite(time):
            raise ContractViolation("diffusion_times must contain finite numbers")
        if time <= 0:
            raise ContractViolation("diffusion_times must contain positive numbers")
        result[f"heat_trace_t{float(time):g}"] = float(torch.exp(-float(time) * values).mean())
    return result


def compute_statistics_values(
    laplacian: LaplacianArtifact,
    spectrum: SpectrumArtifact,
    node_features: NodeFeatureMatrix,
    spec: M2Spec | None = None,
    *,
    topology: torch.Tensor | None = None,
) -> dict[str, float]:
    if laplacian.graph_key != spectrum.graph_key:
        raise ContractViolation("laplacian and spectrum GraphKey must match")
    payload = laplacian.payload.detach().cpu().to(torch.float64)
    values = spectrum.eigenvalues.detach().cpu().to(torch.float64)
    if payload.dim() != 2 or payload.size(0) != payload.size(1):
        raise ContractViolation("laplacian must be square")
    n = int(payload.size(0))
    if n < 2:
        raise ContractViolation("spectral statistics require at least two nodes")
    if values.numel() != n or not bool(torch.isfinite(values).all()):
        raise NumericalValidationError("spectrum length and finiteness must match laplacian")
    if not isinstance(node_features, torch.Tensor) or node_features.dim() != 2:
        raise ContractViolation("node_features must be a two-dimensional tensor")
    features = node_features.detach().cpu().to(torch.float64)
    if features.size(0) != n:
        raise ContractViolation("node_features row count must match the graph")
    if not bool(torch.isfinite(features).all()):
        raise ContractViolation("node_features must be finite")

    if topology is None:
        raise ContractViolation("explicit M1 topology is required for spectral statistics")
    adjacency = _validate_topology(topology, n)
    num_edges = int(torch.triu(adjacency, diagonal=1).sum().item())
    degrees = adjacency.sum(dim=1)
    spectrum_np = values.numpy()
    quantile_values = _quantiles(spectrum_np)
    zero_tol = zero_tolerance(spec) if spec is not None else 1e-7
    tie_tol = tie_tolerance(spec) if spec is not None else 1e-7
    positive = spectrum_np[spectrum_np > zero_tol]
    if len(positive) <= 1:
        entropy = 0.0
    else:
        probabilities = positive / positive.sum()
        entropy = float(-(probabilities * np.log(probabilities)).sum() / np.log(len(positive)))
    denominator = float(torch.sum(features * features).item())
    epsilon = dirichlet_epsilon(spec) if spec is not None else 1e-12
    if denominator < epsilon:
        raise NumericalValidationError("node feature Frobenius norm is too small")
    dirichlet = float(torch.trace(features.T @ payload @ features).item() / denominator)
    distinct_count = 1 + int(torch.sum(torch.diff(values).abs() > tie_tol).item())
    result = {
        "num_nodes": float(n),
        "num_edges": float(num_edges),
        "density": float(2 * num_edges / (n * (n - 1))),
        "mean_degree": float(degrees.mean().item()),
        "connected_components": float(_component_count(adjacency)),
        "algebraic_connectivity": float(values[1].item()),
        "zero_eigenvalue_count": float(torch.sum(values.abs() <= zero_tol).item()),
        "distinct_eigenvalue_count": float(distinct_count),
        "eigenvalue_q05": quantile_values[0],
        "eigenvalue_q25": quantile_values[1],
        "eigenvalue_q50": quantile_values[2],
        "eigenvalue_q75": quantile_values[3],
        "eigenvalue_q95": quantile_values[4],
        "spectral_entropy": entropy,
        "dirichlet_energy": dirichlet,
    }
    if spec is not None and "diffusion_times" in spec.parameters:
        result.update(_heat_trace(values, spec.parameters["diffusion_times"]))
    if any(not math.isfinite(value) for value in result.values()):
        raise NumericalValidationError("spectral statistics must be finite")
    return result


def build_statistics_artifact(
    laplacian: LaplacianArtifact,
    spectrum: SpectrumArtifact,
    node_features: NodeFeatureMatrix,
    context: ScienceContext,
    spec: M2Spec | None = None,
    *,
    topology: torch.Tensor | None = None,
) -> SpectralStatistics:
    values = compute_statistics_values(
        laplacian,
        spectrum,
        node_features,
        spec,
        topology=topology,
    )
    content_hash = canonical_json_hash(values)
    meta = make_meta(
        artifact_type="SpectralStatistics",
        context=context,
        content_sha256=content_hash,
        input_artifact_ids=(
            laplacian.meta.artifact_id,
            spectrum.meta.artifact_id,
            f"node-features:{tensor_content_hash(node_features)}",
        ),
        input_content_hashes=(
            laplacian.meta.content_sha256,
            spectrum.meta.content_sha256,
            tensor_content_hash(node_features),
        ),
        numerics_profile_hash=numerics_profile(
            spec or M2Spec(backend="numpy")
        ).numerics_profile_hash,
        graph_key=laplacian.graph_key,
        created_at_utc=laplacian.meta.created_at_utc,
    )
    return SpectralStatistics(meta=meta, graph_key=laplacian.graph_key, values=values)
