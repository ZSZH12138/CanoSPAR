from __future__ import annotations

from canospar.api.m2 import fit_qc_transform, run_m2
from canospar.contracts.spectral import SpectralBundle
from canospar.spectral.qc import fitted_qc_state_hash
from tests.integration.test_m2_synthetic_multigraph import _artifact, _context, _spec


def test_m2_artifacts_preserve_graph_keys_and_parent_lineage() -> None:
    source = _artifact()
    bundle = run_m2(source, _spec(), _context())

    assert bundle.meta.module_contract_version == "1.1.0"
    assert bundle.meta.input_artifact_ids[0] == source.meta.artifact_id
    assert bundle.meta.input_content_hashes[0] == source.meta.content_sha256
    for laplacian, spectrum, statistics in zip(
        bundle.laplacians, bundle.spectra, bundle.statistics, strict=True
    ):
        assert laplacian.graph_key == spectrum.graph_key == statistics.graph_key
        assert source.meta.artifact_id in laplacian.meta.input_artifact_ids
        assert laplacian.meta.artifact_id in spectrum.meta.input_artifact_ids
        assert spectrum.meta.artifact_id in statistics.meta.input_artifact_ids
        assert laplacian.meta.content_sha256 in spectrum.meta.input_content_hashes


def test_qc_state_hash_is_in_normalized_qc_and_bundle_lineage() -> None:
    state = fit_qc_transform([{"motion": 0.1, "snr": 1.0}, {"motion": 0.3, "snr": 2.0}], _spec())
    bundle = run_m2(_artifact(), _spec(), _context(), qc_state=state)
    state_hash = fitted_qc_state_hash(state)

    assert bundle.normalized_qc is not None
    assert state_hash in bundle.normalized_qc.meta.input_content_hashes
    assert state_hash in bundle.meta.input_content_hashes
    assert state_hash in bundle.receipt.input_hashes  # type: ignore[union-attr]


def test_formal_bundle_reconstruction_preserves_identity_and_evidence() -> None:
    bundle = run_m2(_artifact(), _spec(), _context())
    reconstructed = SpectralBundle(
        bundle.meta,
        bundle.laplacians,
        bundle.spectra,
        bundle.statistics,
        bundle.normalized_qc,
    )

    assert reconstructed.science_key == bundle.science_key
    assert reconstructed.reproduction_key == bundle.reproduction_key
    assert reconstructed.receipt is None
    assert reconstructed.evidence == bundle.evidence
