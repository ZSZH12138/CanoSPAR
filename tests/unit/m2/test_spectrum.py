from __future__ import annotations

import torch

from canospar.api.m2 import build_normalized_laplacian, compute_spectrum
from canospar.contracts.base import ArtifactMeta, ScienceContext
from canospar.contracts.spectral import M2Spec
from canospar.data.contracts import GraphData


def _meta() -> ArtifactMeta:
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


def _graph() -> GraphData:
    return GraphData(
        x=torch.ones((4, 1), dtype=torch.float64),
        edge_index=torch.tensor([[0, 1, 1, 2, 2, 3], [1, 0, 2, 1, 3, 2]], dtype=torch.long),
        edge_weight=torch.ones(6, dtype=torch.float64),
        num_nodes=4,
        modality="smri",
        relation="morphology",
        graph_qc={"synthetic": 1.0},
        construction_hash="construction-a",
    )


def test_exact_spectrum_is_sorted_finite_and_bounded() -> None:
    context = ScienceContext(science_config_hash="config-a")
    spec = M2Spec(backend="numpy", parameters={"solver_tolerance": 1e-8})
    laplacian = build_normalized_laplacian(_graph(), spec, context, parent_meta=_meta())
    spectrum = compute_spectrum(laplacian, spec, context)

    assert spectrum.eigenvalues.shape == (4,)
    assert spectrum.eigenvalues.dtype == torch.float64
    assert torch.isfinite(spectrum.eigenvalues).all()
    assert torch.all(spectrum.eigenvalues[:-1] <= spectrum.eigenvalues[1:])
    assert float(spectrum.eigenvalues.min()) >= -1e-8
    assert float(spectrum.eigenvalues.max()) <= 2.0 + 1e-8
    assert spectrum.graph_key == laplacian.graph_key


def test_path_graph_has_expected_analytic_eigenvalues() -> None:
    context = ScienceContext(science_config_hash="config-a")
    spec = M2Spec(backend="numpy")
    spectrum = compute_spectrum(
        build_normalized_laplacian(_graph(), spec, context, parent_meta=_meta()),
        spec,
        context,
    )

    expected = torch.tensor([0.0, 0.5, 1.5, 2.0], dtype=torch.float64)
    assert torch.allclose(spectrum.eigenvalues, expected, atol=1e-8, rtol=1e-8)
