from __future__ import annotations

from dataclasses import replace

import pytest
import torch

from canospar.api.m2 import run_m2
from canospar.contracts.base import ArtifactMeta, ScienceContext
from canospar.contracts.errors import ContractViolation
from canospar.contracts.spectral import M2Spec
from canospar.data.contracts import GraphData
from tests.integration.test_m2_synthetic_multigraph import _artifact, _spec


def _context() -> ScienceContext:
    return ScienceContext(
        science_contract_version="1.1.0",
        science_config_hash="m2-synthetic-config",
        dataset_manifest_hash="synthetic-manifest",
        split_id="synthetic-outer-0",
        random_seed=13,
    )


def test_bad_dataset_split_and_science_lineage_fail_closed() -> None:
    artifact = _artifact()
    with pytest.raises(ContractViolation, match="dataset manifest"):
        run_m2(
            artifact,
            _spec(),
            replace(_context(), dataset_manifest_hash="other-manifest"),
        )
    with pytest.raises(ContractViolation, match="split"):
        run_m2(artifact, _spec(), replace(_context(), split_id="other-split"))
    with pytest.raises(ContractViolation, match="science contract"):
        run_m2(artifact, _spec(), replace(_context(), science_contract_version="other"))


def test_incompatible_upstream_protocol_and_invalidated_artifacts_fail_closed() -> None:
    artifact = _artifact()
    with pytest.raises(ContractViolation, match="protocol"):
        run_m2(
            replace(
                artifact,
                meta=replace(artifact.meta, module_contract_version="1.0.0"),
            ),
            _spec(),
            _context(),
        )


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("schema_version", "9.9.9"),
        ("artifact_type", "WrongArtifact"),
        ("producer_module", "M9"),
        ("content_sha256", "tampered-content"),
    ],
)
def test_bad_upstream_schema_type_producer_or_hash_fails_closed(
    field_name: str, bad_value: str
) -> None:
    artifact = _artifact()
    bad_meta = replace(artifact.meta, **{field_name: bad_value})

    with pytest.raises(ContractViolation):
        run_m2(replace(artifact, meta=bad_meta), _spec(), _context())
    with pytest.raises(ContractViolation, match="not ready"):
        run_m2(
            replace(
                artifact,
                meta=replace(artifact.meta, artifact_type="NOT_READY"),
            ),
            _spec(),
            _context(),
        )


def test_invalid_graph_node_features_and_qc_state_fail_closed() -> None:
    artifact = _artifact()
    bad_graph = replace(
        artifact.sample.graphs["smri"]["morphology_similarity"],
        x=torch.full((4, 1), float("nan"), dtype=torch.float64),
    )
    bad_sample = replace(
        artifact.sample,
        graphs={
            **artifact.sample.graphs,
            "smri": {"morphology_similarity": bad_graph},
        },
    )
    with pytest.raises(ValueError, match="finite"):
        run_m2(replace(artifact, sample=bad_sample), _spec(), _context())
    with pytest.raises(ContractViolation, match="qc_"):
        run_m2(
            artifact, M2Spec(backend="numpy"), _context(), qc_state={"motion": (0.0, 0.0, 1.0, 1.0)}
        )


def test_invalid_qc_state_values_fail_closed() -> None:
    with pytest.raises(ContractViolation):
        run_m2(
            _artifact(),
            _spec(),
            _context(),
            qc_state={"motion": (0.0, 0.0, 1.0, float("nan")), "snr": (0.0, 0.0, 1.0, 1.0)},
        )


def test_direct_graph_contract_rejects_negative_nonfinite_and_asymmetric_inputs() -> None:
    from canospar.api.m2 import build_normalized_laplacian

    meta = ArtifactMeta(
        schema_version="1.0.0",
        artifact_type="MultiGraphArtifact",
        artifact_id="parent",
        producer_module="M1",
        module_contract_version="1.1.0",
        science_contract_version="1.1.0",
        input_artifact_ids=(),
        input_content_hashes=(),
        science_config_hash="config",
        dataset_manifest_hash=None,
        split_id=None,
        random_seed=None,
        content_sha256="content",
        implementation_hash="impl",
        numerics_profile_hash="num",
        created_at_utc="2026-08-18T00:00:00Z",
    )
    for weights, edges in (
        (
            torch.tensor([-1.0, -1.0]),
            torch.tensor([[0, 1], [1, 0]], dtype=torch.long),
        ),
        (
            torch.tensor([float("inf"), 1.0]),
            torch.tensor([[0, 1], [1, 0]], dtype=torch.long),
        ),
        (
            torch.tensor([1.0]),
            torch.tensor([[0], [1]], dtype=torch.long),
        ),
    ):
        graph = GraphData(
            x=torch.ones((2, 1), dtype=torch.float64),
            edge_index=edges,
            edge_weight=weights,
            num_nodes=2,
            modality="smri",
            relation="bad",
            graph_qc={"synthetic": 1.0},
            construction_hash="bad-graph",
        )
        with pytest.raises((ValueError, ContractViolation)):
            build_normalized_laplacian(
                graph,
                M2Spec(backend="numpy"),
                _context(),
                parent_meta=meta,
            )
