from __future__ import annotations

from dataclasses import replace

import pytest
import torch

from canospar.api.m2 import (
    build_normalized_laplacian,
    compute_spectral_statistics,
    compute_spectrum,
)
from canospar.contracts.base import ArtifactMeta, ScienceContext
from canospar.contracts.errors import ContractViolation
from canospar.contracts.spectral import M2Spec
from canospar.data.contracts import GraphData
from canospar.spectral.laplacian import build_unweighted_topology
from canospar.spectral.lineage import multigraph_content_hash
from tests.integration.test_m2_synthetic_multigraph import _artifact, _context, _spec


def _meta() -> ArtifactMeta:
    return ArtifactMeta(
        schema_version="1.0.0",
        artifact_type="MultiGraphArtifact",
        artifact_id="parent-stats",
        producer_module="M1",
        module_contract_version="1.1.0",
        science_contract_version="1.1.0",
        input_artifact_ids=(),
        input_content_hashes=(),
        science_config_hash="stats-config",
        dataset_manifest_hash="stats-manifest",
        split_id="synthetic",
        random_seed=1,
        content_sha256="stats-parent-content",
        implementation_hash="m1-stats",
        numerics_profile_hash="stats-numerics",
        created_at_utc="2026-08-18T00:00:00Z",
    )


def _graph(num_nodes: int = 4) -> GraphData:
    return GraphData(
        x=torch.arange(num_nodes, dtype=torch.float64).reshape(num_nodes, 1),
        edge_index=torch.tensor([[0, 1, 1, 2, 2, 3], [1, 0, 2, 1, 3, 2]], dtype=torch.long),
        edge_weight=torch.ones(6, dtype=torch.float64),
        num_nodes=num_nodes,
        modality="smri",
        relation="morphology",
        graph_qc={"synthetic": 1.0},
        construction_hash="stats-graph",
    )


def _artifacts(graph: GraphData | None = None):
    if graph is None:
        graph = _graph()
    context = ScienceContext(science_config_hash="stats-config")
    spec = M2Spec(backend="numpy")
    laplacian = build_normalized_laplacian(graph, spec, context, parent_meta=_meta())
    spectrum = compute_spectrum(laplacian, spec, context)
    return laplacian, spectrum, context


def test_statistics_have_fixed_keys_and_frozen_topology_values() -> None:
    laplacian, spectrum, context = _artifacts()
    result = compute_spectral_statistics(
        laplacian,
        spectrum,
        _graph().x,
        context,
        topology=build_unweighted_topology(_graph()),
    )

    expected_keys = {
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
    }
    assert set(result.values) == expected_keys
    assert result.values["num_nodes"] == 4.0
    assert result.values["num_edges"] == 3.0
    assert result.values["density"] == pytest.approx(0.5)
    assert result.values["mean_degree"] == pytest.approx(1.5)
    assert result.values["connected_components"] == 1.0
    assert result.values["algebraic_connectivity"] == pytest.approx(0.5)
    assert result.values["zero_eigenvalue_count"] == 1.0
    assert result.values["distinct_eigenvalue_count"] == 4.0
    assert result.values["spectral_entropy"] == pytest.approx(0.8868595071)
    assert torch.isfinite(torch.tensor(list(result.values.values()))).all()


def test_public_statistics_fail_closed_without_explicit_m1_topology() -> None:
    laplacian, spectrum, context = _artifacts()

    with pytest.raises(ContractViolation, match="explicit M1 topology"):
        compute_spectral_statistics(laplacian, spectrum, _graph().x, context)


def test_statistics_fail_closed_for_one_node_or_zero_norm_features() -> None:
    context = ScienceContext(science_config_hash="stats-config")
    spec = M2Spec(backend="numpy")
    one_node = GraphData(
        x=torch.ones((1, 1), dtype=torch.float64),
        edge_index=torch.empty((2, 0), dtype=torch.long),
        edge_weight=torch.empty((0,), dtype=torch.float64),
        num_nodes=1,
        modality="smri",
        relation="one",
        graph_qc={"synthetic": 1.0},
        construction_hash="one-node",
    )
    laplacian = build_normalized_laplacian(one_node, spec, context, parent_meta=_meta())
    spectrum = compute_spectrum(laplacian, spec, context)
    with pytest.raises(ValueError, match="at least two"):
        compute_spectral_statistics(
            laplacian,
            spectrum,
            one_node.x,
            context,
            topology=build_unweighted_topology(one_node),
        )

    laplacian, spectrum, context = _artifacts()
    with pytest.raises(ValueError, match="Frobenius"):
        compute_spectral_statistics(
            laplacian,
            spectrum,
            torch.zeros_like(_graph().x),
            context,
            topology=build_unweighted_topology(_graph()),
        )


def test_explicit_diffusion_times_are_the_only_source_of_heat_trace_values() -> None:
    laplacian, spectrum, context = _artifacts()
    spec = M2Spec(backend="numpy", parameters={"diffusion_times": [0.5, 2.0]})
    from canospar.spectral.statistics import build_statistics_artifact

    result = build_statistics_artifact(
        laplacian,
        spectrum,
        _graph().x,
        context,
        spec,
        topology=build_unweighted_topology(_graph()),
    )
    assert result.values["heat_trace_t0.5"] > 0
    assert result.values["heat_trace_t2"] > 0


def test_canonical_run_m2_counts_zero_weight_edges_from_upstream_topology() -> None:
    source = _artifact()
    original = source.sample.graphs["smri"]["morphology_similarity"]
    zero_weight_graph = replace(
        original,
        edge_weight=torch.tensor([0.0, 0.0, 1.0, 1.0, 1.0, 1.0], dtype=torch.float64),
    )
    sample = replace(
        source.sample,
        graphs={
            **source.sample.graphs,
            "smri": {"morphology_similarity": zero_weight_graph},
        },
    )

    from canospar.api.m2 import run_m2

    updated_meta = replace(
        source.meta,
        content_sha256=multigraph_content_hash(
            sample,
            source.atlas_id,
            source.atlas_hash,
            source.roi_table_hash,
            source.node_order_hash,
        ),
    )
    bundle = run_m2(replace(source, meta=updated_meta, sample=sample), _spec(), _context())
    smri_statistics = next(item for item in bundle.statistics if item.graph_key.modality == "smri")

    assert smri_statistics.values["num_edges"] == 3.0
    assert smri_statistics.values["connected_components"] == 1.0


def test_public_statistics_use_explicit_m1_topology_for_zero_weight_edges() -> None:
    graph = replace(
        _graph(),
        edge_weight=torch.tensor([0.0, 0.0, 1.0, 1.0, 1.0, 1.0], dtype=torch.float64),
    )
    context = ScienceContext(science_config_hash="stats-config")
    spec = M2Spec(backend="numpy")
    laplacian = build_normalized_laplacian(graph, spec, context, parent_meta=_meta())
    spectrum = compute_spectrum(laplacian, spec, context)

    result = compute_spectral_statistics(
        laplacian,
        spectrum,
        graph.x,
        context,
        topology=build_unweighted_topology(graph),
    )

    assert result.values["num_edges"] == 3.0
    assert result.values["connected_components"] == 1.0


def test_public_statistics_reject_non_binary_topology() -> None:
    laplacian, spectrum, context = _artifacts()

    with pytest.raises(ContractViolation, match="binary"):
        compute_spectral_statistics(
            laplacian,
            spectrum,
            _graph().x,
            context,
            topology=build_unweighted_topology(_graph()) * 2.0,
        )
