from __future__ import annotations

from dataclasses import replace

import pytest
import torch

from canospar.api.m2 import run_m2
from canospar.contracts.base import GraphKey
from canospar.contracts.errors import ContractViolation
from canospar.contracts.spectral import NormalizedQCArtifact, SpectralStatistics
from canospar.spectral.lineage import canonical_json_hash
from canospar.spectral.qc import fit_qc_state
from canospar.validators.m2 import validate_m2_bundle
from tests.integration.test_m2_synthetic_multigraph import _artifact, _context, _spec


def test_spectrum_artifact_rejects_eigenvalues_outside_normalized_bounds() -> None:
    bundle = run_m2(_artifact(), _spec(), _context())
    spectrum = bundle.spectra[0]

    candidate = replace(
        bundle,
        spectra=(
            replace(
                spectrum,
                eigenvalues=torch.tensor(
                    [-0.1, 0.5, 1.5, 2.0],
                    dtype=torch.float64,
                ),
            ),
            *bundle.spectra[1:],
        ),
    )

    report = validate_m2_bundle(candidate, _spec(), _artifact())
    assert report.status == "FAIL"
    assert any(issue.code == "SPECTRUM_BOUNDS" for issue in report.issues)


def test_spectral_statistics_require_all_fixed_protocol_keys() -> None:
    bundle = run_m2(_artifact(), _spec(), _context())
    statistics = bundle.statistics[0]

    candidate = replace(
        bundle,
        statistics=(
            SpectralStatistics(
                meta=statistics.meta,
                graph_key=statistics.graph_key,
                values={"num_nodes": 4.0},
            ),
            *bundle.statistics[1:],
        ),
    )

    report = validate_m2_bundle(candidate, _spec(), _artifact())
    assert report.status == "FAIL"
    assert any(issue.code == "STATISTICS_KEYS" for issue in report.issues)


def test_tampered_bundle_does_not_expose_a_pass_receipt() -> None:
    source = _artifact()
    spec = _spec()
    bundle = run_m2(source, spec, _context())
    candidate = replace(bundle, meta=replace(bundle.meta, content_sha256="tampered"))

    assert candidate.receipt is None


def test_validator_rejects_forged_implementation_identity() -> None:
    source = _artifact()
    spec = _spec()
    bundle = run_m2(source, spec, _context())
    candidate = replace(
        bundle,
        meta=replace(bundle.meta, implementation_hash="forged-implementation"),
    )

    report = validate_m2_bundle(candidate, spec, source)

    assert report.status == "FAIL"
    assert any(issue.code == "IMPLEMENTATION_IDENTITY" for issue in report.issues)
    assert candidate.receipt is None


def test_validator_rejects_forged_artifact_ids() -> None:
    source = _artifact()
    spec = _spec()
    bundle = run_m2(source, spec, _context())
    laplacians = tuple(
        replace(item, meta=replace(item.meta, artifact_id=f"forged-laplacian-{index}"))
        for index, item in enumerate(bundle.laplacians)
    )
    spectra = tuple(
        replace(
            item,
            meta=replace(
                item.meta,
                artifact_id=f"forged-spectrum-{index}",
                input_artifact_ids=(f"forged-laplacian-{index}",),
            ),
        )
        for index, item in enumerate(bundle.spectra)
    )
    statistics = tuple(
        replace(
            item,
            meta=replace(
                item.meta,
                artifact_id=f"forged-statistics-{index}",
                input_artifact_ids=(
                    f"forged-laplacian-{index}",
                    f"forged-spectrum-{index}",
                    item.meta.input_artifact_ids[2],
                ),
            ),
        )
        for index, item in enumerate(bundle.statistics)
    )
    child_ids = tuple(
        artifact_id
        for index in range(len(laplacians))
        for artifact_id in (
            f"forged-laplacian-{index}",
            f"forged-spectrum-{index}",
            f"forged-statistics-{index}",
        )
    )
    candidate = replace(
        bundle,
        meta=replace(
            bundle.meta,
            artifact_id="forged-bundle",
            input_artifact_ids=bundle.meta.input_artifact_ids[:3] + child_ids,
        ),
        laplacians=laplacians,
        spectra=spectra,
        statistics=statistics,
        _validated_receipt=None,
        _validated_fingerprint=None,
    )

    report = validate_m2_bundle(candidate, spec, source)

    assert report.status == "FAIL"
    assert any(issue.code == "ARTIFACT_ID" for issue in report.issues)


def test_validator_rejects_forged_science_spec_lineage() -> None:
    source = _artifact()
    spec = _spec()
    bundle = run_m2(source, spec, _context())
    input_ids = list(bundle.meta.input_artifact_ids)
    input_hashes = list(bundle.meta.input_content_hashes)
    science_index = next(
        index for index, value in enumerate(input_ids) if value.startswith("science-spec:")
    )
    input_ids[science_index] = "science-spec:forged"
    input_hashes[science_index] = "forged"
    candidate = replace(
        bundle,
        meta=replace(
            bundle.meta,
            input_artifact_ids=tuple(input_ids),
            input_content_hashes=tuple(input_hashes),
        ),
    )

    report = validate_m2_bundle(candidate, spec, source)

    assert report.status == "FAIL"
    assert any(issue.code == "SCIENCE_SPEC_LINEAGE" for issue in report.issues)


def test_validator_rejects_bundle_qc_state_pair_mismatch() -> None:
    source = _artifact()
    spec = _spec()
    state = fit_qc_state(
        [{"motion": 0.1, "snr": 1.0}, {"motion": 0.3, "snr": 2.0}],
        spec,
    )
    bundle = run_m2(source, spec, _context(), qc_state=state)
    assert bundle.normalized_qc is not None
    input_ids = tuple(
        "qc-state:forged" if value.startswith("qc-state:") else value
        for value in bundle.meta.input_artifact_ids
    )
    input_hashes = tuple(
        "forged" if artifact_id.startswith("qc-state:") else content_hash
        for artifact_id, content_hash in zip(
            bundle.meta.input_artifact_ids,
            bundle.meta.input_content_hashes,
            strict=True,
        )
    )
    candidate = replace(
        bundle,
        meta=replace(
            bundle.meta,
            input_artifact_ids=input_ids,
            input_content_hashes=input_hashes,
        ),
    )

    report = validate_m2_bundle(candidate, spec, source)

    assert report.status == "FAIL"
    assert any(issue.code == "BUNDLE_LINEAGE" for issue in report.issues)


def test_validator_rejects_graph_keys_not_present_in_m1() -> None:
    source = _artifact()
    spec = _spec()
    bundle = run_m2(source, spec, _context())
    forged_key = GraphKey("forged-subject", "forged-visit", "fmri", "forged-relation")
    candidate = replace(
        bundle,
        laplacians=(replace(bundle.laplacians[0], graph_key=forged_key), *bundle.laplacians[1:]),
        spectra=(replace(bundle.spectra[0], graph_key=forged_key), *bundle.spectra[1:]),
        statistics=(replace(bundle.statistics[0], graph_key=forged_key), *bundle.statistics[1:]),
    )

    report = validate_m2_bundle(candidate, spec, source)

    assert report.status == "FAIL"
    assert any(issue.code == "GRAPH_KEY_PROVENANCE" for issue in report.issues)


def test_spectral_bundle_rejects_empty_graph_payloads() -> None:
    bundle = run_m2(_artifact(), _spec(), _context())

    with pytest.raises(ContractViolation, match="at least one graph"):
        replace(bundle, laplacians=(), spectra=(), statistics=())


def test_normalized_qc_requires_exact_spec_feature_keys() -> None:
    source = _artifact()
    spec = _spec()
    state = fit_qc_state(
        [{"motion": 0.1, "snr": 1.0}, {"motion": 0.3, "snr": 2.0}],
        spec,
    )
    bundle = run_m2(source, spec, _context(), qc_state=state)
    assert bundle.normalized_qc is not None
    values = {"motion": 0.0}
    normalized_qc = NormalizedQCArtifact(
        meta=replace(
            bundle.normalized_qc.meta,
            content_sha256=canonical_json_hash(values),
        ),
        values=values,
    )
    bundle_hash = canonical_json_hash(
        {
            "laplacians": [item.meta.content_sha256 for item in bundle.laplacians],
            "spectra": [item.meta.content_sha256 for item in bundle.spectra],
            "statistics": [item.meta.content_sha256 for item in bundle.statistics],
            "normalized_qc": normalized_qc.meta.content_sha256,
        }
    )
    candidate = replace(
        bundle,
        meta=replace(bundle.meta, content_sha256=bundle_hash),
        normalized_qc=normalized_qc,
    )

    report = validate_m2_bundle(candidate, spec, source)

    assert report.status == "FAIL"
    assert any(issue.code == "QC_KEYS" for issue in report.issues)


def test_normalized_qc_requires_matching_state_hash_pair() -> None:
    source = _artifact()
    spec = _spec()
    state = fit_qc_state(
        [{"motion": 0.1, "snr": 1.0}, {"motion": 0.3, "snr": 2.0}],
        spec,
    )
    bundle = run_m2(source, spec, _context(), qc_state=state)
    assert bundle.normalized_qc is not None
    normalized_meta = replace(
        bundle.normalized_qc.meta,
        input_artifact_ids=(source.meta.artifact_id, "qc-state:forged"),
        input_content_hashes=(source.meta.content_sha256, "different-state-hash"),
    )
    normalized_qc = replace(bundle.normalized_qc, meta=normalized_meta)
    candidate = replace(bundle, normalized_qc=normalized_qc)

    report = validate_m2_bundle(candidate, spec, source)

    assert report.status == "FAIL"
    assert any(issue.code == "QC_STATE_LINEAGE" for issue in report.issues)
