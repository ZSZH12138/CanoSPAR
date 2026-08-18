from __future__ import annotations

import torch

from canospar.api.m2 import fit_qc_transform, run_m2
from canospar.contracts.base import ArtifactMeta, MultiGraphArtifact, ScienceContext
from canospar.contracts.execution import cache_is_eligible
from canospar.contracts.spectral import M2Spec
from canospar.data.contracts import BrainMultiGraphSample, GraphData
from canospar.spectral.lineage import multigraph_content_hash
from canospar.spectral.qc import fitted_qc_state_hash


def _meta(content_sha256: str = "synthetic-multigraph-content") -> ArtifactMeta:
    return ArtifactMeta(
        schema_version="1.0.0",
        artifact_type="MultiGraphArtifact",
        artifact_id="synthetic-multigraph",
        producer_module="M1",
        module_contract_version="1.1.0",
        science_contract_version="1.1.0",
        input_artifact_ids=("m1-input",),
        input_content_hashes=("m1-input-content",),
        science_config_hash="m2-synthetic-config",
        dataset_manifest_hash="synthetic-manifest",
        split_id="synthetic-outer-0",
        random_seed=13,
        content_sha256=content_sha256,
        implementation_hash="m1-synthetic-implementation",
        numerics_profile_hash="m1-synthetic-numerics",
        created_at_utc="2026-08-18T00:00:00Z",
    )


def _graph(modality: str, relation: str, offset: float) -> GraphData:
    edges = torch.tensor([[0, 1, 1, 2, 2, 3], [1, 0, 2, 1, 3, 2]], dtype=torch.long)
    return GraphData(
        x=torch.arange(4, dtype=torch.float64).reshape(4, 1) + offset,
        edge_index=edges,
        edge_weight=torch.ones(6, dtype=torch.float64),
        num_nodes=4,
        modality=modality,
        relation=relation,
        graph_qc={"synthetic": 1.0},
        construction_hash=f"{modality}-{relation}-construction",
    )


def _artifact() -> MultiGraphArtifact:
    sample = BrainMultiGraphSample(
        subject_id="synthetic-subject",
        visit_id="baseline",
        group_id="synthetic-subject",
        site_id="synthetic-site",
        graphs={
            "fmri": {
                "positive_functional_connectivity": _graph(
                    "fmri", "positive_functional_connectivity", 2.0
                )
            },
            "smri": {"morphology_similarity": _graph("smri", "morphology_similarity", 0.0)},
            "dmri": {"structural_connectivity": _graph("dmri", "structural_connectivity", 1.0)},
        },
        modality_available={"smri": True, "dmri": True, "fmri": True},
        qc_vector={"motion": 0.2, "snr": 1.5},
        target=0.0,
        covariates={"age": 30.0},
        cohort_metadata={
            "cohort_source": "synthetic",
            "unrelated_list_version": "not_applicable",
            "kinship_control_method": "synthetic",
        },
    )
    atlas_id = "synthetic-atlas"
    atlas_hash = "synthetic-atlas-hash"
    roi_table_hash = "synthetic-roi-hash"
    node_order_hash = "synthetic-node-order"
    content_hash = multigraph_content_hash(
        sample,
        atlas_id,
        atlas_hash,
        roi_table_hash,
        node_order_hash,
    )
    return MultiGraphArtifact(
        meta=_meta(content_hash),
        sample=sample,
        atlas_id=atlas_id,
        atlas_hash=atlas_hash,
        roi_table_hash=roi_table_hash,
        node_order_hash=node_order_hash,
    )


def _spec() -> M2Spec:
    return M2Spec(
        backend="numpy",
        parameters={
            "qc_features": ["motion", "snr"],
            "winsor_lower_quantile": 0.25,
            "winsor_upper_quantile": 0.75,
            "robust_scale_epsilon": 1e-6,
        },
    )


def _context() -> ScienceContext:
    return ScienceContext(
        science_contract_version="1.1.0",
        science_config_hash="m2-synthetic-config",
        dataset_manifest_hash="synthetic-manifest",
        split_id="synthetic-outer-0",
        random_seed=13,
    )


def test_three_synthetic_modalities_run_in_stable_graph_order() -> None:
    multigraph = _artifact()
    context = ScienceContext(
        science_contract_version="1.1.0",
        science_config_hash="m2-synthetic-config",
        dataset_manifest_hash="synthetic-manifest",
        split_id="synthetic-outer-0",
        random_seed=13,
    )
    train_state = fit_qc_transform(
        [{"motion": 0.1, "snr": 1.0}, {"motion": 0.3, "snr": 2.0}], _spec()
    )
    bundle = run_m2(multigraph, _spec(), context, qc_state=train_state)

    assert len(bundle.laplacians) == len(bundle.spectra) == len(bundle.statistics) == 3
    assert [item.graph_key.modality for item in bundle.laplacians] == ["dmri", "fmri", "smri"]
    assert bundle.normalized_qc is not None
    assert bundle.science_key
    assert bundle.reproduction_key
    assert bundle.receipt is not None
    assert bundle.evidence["verification_scope"] == "SYNTHETIC_ANALYTIC_ONLY"
    assert all(torch.isfinite(item.payload).all() for item in bundle.laplacians)
    assert all(torch.isfinite(item.eigenvalues).all() for item in bundle.spectra)
    assert fitted_qc_state_hash(train_state) in bundle.meta.input_content_hashes


def test_identical_run_is_reproducible_and_cache_eligible() -> None:
    multigraph = _artifact()
    context = ScienceContext(
        science_contract_version="1.1.0",
        science_config_hash="m2-synthetic-config",
        dataset_manifest_hash="synthetic-manifest",
        split_id="synthetic-outer-0",
        random_seed=13,
    )
    first = run_m2(multigraph, _spec(), context)
    second = run_m2(multigraph, _spec(), context)

    assert first.meta.artifact_id == second.meta.artifact_id
    assert first.meta.content_sha256 == second.meta.content_sha256
    assert first.science_key == second.science_key
    assert first.reproduction_key == second.reproduction_key
    assert first.receipt is not None
    assert cache_is_eligible(
        expected_science_key=first.science_key,
        expected_reproduction_key=first.reproduction_key,
        artifact_hash=first.meta.content_sha256,
        receipt=first.receipt,  # type: ignore[arg-type]
        validator_status="PASS",
    )


def test_run_m2_without_qc_state_does_not_fit_current_sample() -> None:
    artifact = _artifact()
    context = ScienceContext(
        science_contract_version="1.1.0",
        science_config_hash="m2-synthetic-config",
        dataset_manifest_hash="synthetic-manifest",
        split_id="synthetic-outer-0",
        random_seed=13,
    )
    bundle = run_m2(artifact, _spec(), context)
    assert bundle.normalized_qc is None
    assert all("qc-state:" not in value for value in bundle.meta.input_artifact_ids)


def test_different_frozen_qc_state_changes_science_identity() -> None:
    source = _artifact()
    context = _context()
    state_a = fit_qc_transform([{"motion": 0.1, "snr": 1.0}, {"motion": 0.3, "snr": 2.0}], _spec())
    state_b = fit_qc_transform([{"motion": 0.2, "snr": 1.0}, {"motion": 0.4, "snr": 2.0}], _spec())
    first = run_m2(source, _spec(), context, qc_state=state_a)
    second = run_m2(source, _spec(), context, qc_state=state_b)

    assert fitted_qc_state_hash(state_a) != fitted_qc_state_hash(state_b)
    assert first.science_key != second.science_key


def test_non_degenerate_unit_qc_scale_is_not_reported_as_constant() -> None:
    state = {
        "motion": (2.5, 1.0, 4.0, 1.0),
        "snr": (2.5, 1.0, 4.0, 1.0),
    }
    bundle = run_m2(_artifact(), _spec(), _context(), qc_state=state)

    assert bundle.receipt is not None
    assert "QC_CONSTANT_FEATURE" not in bundle.receipt.validation_issue_codes


def test_constant_qc_feature_is_recorded_in_receipt() -> None:
    state = fit_qc_transform(
        [{"motion": 1.0, "snr": 2.0}, {"motion": 1.0, "snr": 2.0}],
        _spec(),
    )
    bundle = run_m2(_artifact(), _spec(), _context(), qc_state=state)

    assert bundle.receipt is not None
    assert "QC_CONSTANT_FEATURE" in bundle.receipt.validation_issue_codes


def test_winsorized_constant_qc_feature_is_recorded_in_receipt() -> None:
    spec = M2Spec(
        backend="numpy",
        parameters={
            "qc_features": ["motion", "snr"],
            "winsor_lower_quantile": 0.0,
            "winsor_upper_quantile": 1.0,
            "robust_scale_epsilon": 1e-6,
        },
    )
    state = fit_qc_transform(
        [
            {"motion": 0.0, "snr": 1.0},
            {"motion": 1.0, "snr": 2.0},
            {"motion": 1.0, "snr": 3.0},
            {"motion": 1.0, "snr": 4.0},
            {"motion": 100.0, "snr": 5.0},
        ],
        spec,
    )
    bundle = run_m2(_artifact(), spec, _context(), qc_state=state)

    assert bundle.receipt is not None
    assert "QC_CONSTANT_FEATURE" in bundle.receipt.validation_issue_codes


def test_canonical_run_m2_emits_only_explicit_diffusion_statistics() -> None:
    spec = M2Spec(
        backend="numpy",
        parameters={
            "diffusion_times": [0.5, 2.0],
            "qc_features": ["motion", "snr"],
            "winsor_lower_quantile": 0.25,
            "winsor_upper_quantile": 0.75,
            "robust_scale_epsilon": 1e-6,
        },
    )

    bundle = run_m2(_artifact(), spec, _context())

    assert all("heat_trace_t0.5" in item.values for item in bundle.statistics)
    assert all("heat_trace_t2" in item.values for item in bundle.statistics)
