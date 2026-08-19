"""M3 canonical spectral-mass coordinate API."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Protocol

import torch

from canospar.contracts.bands import (
    BandDefinition,
    BandSpec,
    CanonicalSpectrumArtifact,
    CanonicalSpectrumBundle,
)
from canospar.contracts.base import MODULE_PROTOCOL_SPEC_VERSION, ScienceContext
from canospar.contracts.errors import ContractViolation
from canospar.contracts.execution import CanonicalStatus, CompletionReceipt
from canospar.contracts.spectral import CanonicalCoordinateSpec, SpectralBundle, SpectrumArtifact
from canospar.spectral.lineage import graph_key_sort_key, tensor_content_hash
from canospar.spectral.m3_lineage import (
    band_spec_content_hash,
    canonical_bundle_content_hash,
    canonical_spectrum_content_hash,
    coordinate_spec_content_hash,
    empirical_mid_rank_coordinate,
    make_m3_meta,
    validate_band_spec,
    validate_coordinate_spec,
)
from canospar.validators.base import ValidationReport
from canospar.validators.m3 import validate_m3_bundle


class M3Backend(Protocol):
    def run_m3(
        self,
        spectral_bundle: SpectralBundle,
        coordinate_spec: CanonicalCoordinateSpec,
        band_spec: BandSpec,
        context: ScienceContext,
    ) -> CanonicalSpectrumBundle: ...


def canonical_mass_coordinate(
    spectrum: SpectrumArtifact,
    coordinate_spec: CanonicalCoordinateSpec,
    context: ScienceContext,
) -> CanonicalSpectrumArtifact:
    if not isinstance(spectrum, SpectrumArtifact):
        raise ContractViolation("spectrum must be SpectrumArtifact")
    if not isinstance(context, ScienceContext):
        raise ContractViolation("context must be ScienceContext")
    tie_atol, tie_rtol, _ = validate_coordinate_spec(coordinate_spec)
    meta = spectrum.meta
    if meta.artifact_type.upper() in {"NOT_READY", "INVALIDATED"}:
        raise ContractViolation("upstream spectrum is not ready or has been invalidated")
    if meta.schema_version != "1.0.0" or meta.artifact_type != "SpectrumArtifact":
        raise ContractViolation("spectrum must use the supported SpectrumArtifact schema")
    if meta.producer_module != "M2" or meta.module_contract_version != MODULE_PROTOCOL_SPEC_VERSION:
        raise ContractViolation("spectrum must be produced by M2 under the current protocol")
    if (
        meta.science_contract_version != context.science_contract_version
        or meta.science_config_hash != context.science_config_hash
        or meta.dataset_manifest_hash != context.dataset_manifest_hash
        or meta.split_id != context.split_id
        or meta.random_seed != context.random_seed
    ):
        raise ContractViolation("spectrum science lineage does not match context")
    if meta.content_sha256 != tensor_content_hash(spectrum.eigenvalues):
        raise ContractViolation("spectrum content hash does not match eigenvalues")
    u_coordinate = empirical_mid_rank_coordinate(spectrum.eigenvalues, tie_atol, tie_rtol)
    lambda_coordinate = spectrum.eigenvalues.detach().clone()
    content_hash = canonical_spectrum_content_hash(u_coordinate, lambda_coordinate)
    coordinate_hash = coordinate_spec_content_hash(coordinate_spec)
    output_meta = make_m3_meta(
        artifact_type="CanonicalSpectrumArtifact",
        context=context,
        content_sha256=content_hash,
        input_artifact_ids=(meta.artifact_id, f"coordinate-spec:{coordinate_hash}"),
        input_content_hashes=(meta.content_sha256, coordinate_hash),
        numerics_profile_hash=meta.numerics_profile_hash,
        graph_key=spectrum.graph_key,
        created_at_utc=meta.created_at_utc,
    )
    return CanonicalSpectrumArtifact(
        meta=output_meta,
        graph_key=spectrum.graph_key,
        spectrum_artifact_id=meta.artifact_id,
        u_coordinate=u_coordinate,
        lambda_coordinate=lambda_coordinate,
    )


def build_canonical_bands(
    spectral_bundle: SpectralBundle,
    coordinate_spec: CanonicalCoordinateSpec,
    band_spec: BandSpec,
) -> tuple[BandDefinition, ...]:
    if not isinstance(spectral_bundle, SpectralBundle):
        raise ContractViolation("spectral_bundle must be SpectralBundle")
    validate_coordinate_spec(coordinate_spec)
    validate_band_spec(band_spec)
    if not spectral_bundle.spectra:
        raise ContractViolation("M3 requires at least one upstream spectrum")
    width = 1.0 / band_spec.band_count
    return tuple(
        BandDefinition(
            band_id=f"band_{index}",
            lower_mass=index * width,
            upper_mass=1.0 if index == band_spec.band_count - 1 else (index + 1) * width,
            lower_lambda=None,
            upper_lambda=None,
        )
        for index in range(band_spec.band_count)
    )


def validate_canonical_bands(bands: Sequence[BandDefinition]) -> ValidationReport:
    from canospar.validators.m3 import validate_canonical_bands as _validate

    return _validate(bands)


def run_m3(
    spectral_bundle: SpectralBundle,
    coordinate_spec: CanonicalCoordinateSpec,
    band_spec: BandSpec,
    context: ScienceContext,
) -> CanonicalSpectrumBundle:
    if not isinstance(spectral_bundle, SpectralBundle):
        raise ContractViolation("spectral_bundle must be SpectralBundle")
    if not isinstance(context, ScienceContext):
        raise ContractViolation("context must be ScienceContext")
    validate_coordinate_spec(coordinate_spec)
    validate_band_spec(band_spec)
    if spectral_bundle.receipt is None:
        raise ContractViolation("M3 requires a valid M2 PASS completion receipt")
    source_snapshot = tuple(
        (item.meta.artifact_id, item.meta.content_sha256, item.eigenvalues.detach().clone())
        for item in spectral_bundle.spectra
    )
    ordered_spectra = tuple(
        sorted(spectral_bundle.spectra, key=lambda item: graph_key_sort_key(item.graph_key))
    )
    canonical_spectra = tuple(
        canonical_mass_coordinate(item, coordinate_spec, context) for item in ordered_spectra
    )
    for (artifact_id, content_hash, values), source in zip(
        source_snapshot, spectral_bundle.spectra, strict=True
    ):
        if (
            source.meta.artifact_id != artifact_id
            or source.meta.content_sha256 != content_hash
            or not torch.equal(source.eigenvalues, values)
        ):
            raise ContractViolation("M3 mutated an upstream M2 spectrum")
    bands = build_canonical_bands(spectral_bundle, coordinate_spec, band_spec)
    coordinate_hash = coordinate_spec_content_hash(coordinate_spec)
    band_hash = band_spec_content_hash(band_spec)
    input_ids = (
        spectral_bundle.meta.artifact_id,
        f"coordinate-spec:{coordinate_hash}",
        f"band-spec:{band_hash}",
        *(item.meta.artifact_id for item in canonical_spectra),
    )
    input_hashes = (
        spectral_bundle.meta.content_sha256,
        coordinate_hash,
        band_hash,
        *(item.meta.content_sha256 for item in canonical_spectra),
    )
    bundle_meta = make_m3_meta(
        artifact_type="CanonicalSpectrumBundle",
        context=context,
        content_sha256=canonical_bundle_content_hash(canonical_spectra, bands),
        input_artifact_ids=input_ids,
        input_content_hashes=input_hashes,
        numerics_profile_hash=ordered_spectra[0].meta.numerics_profile_hash,
        created_at_utc=spectral_bundle.meta.created_at_utc,
    )
    bundle = CanonicalSpectrumBundle(
        meta=bundle_meta,
        spectra=canonical_spectra,
        bands=bands,
    )
    validation = validate_m3_bundle(
        bundle,
        spectral_bundle,
        coordinate_spec,
        band_spec,
        context,
    )
    if not validation.is_valid:
        issue_codes = ", ".join(issue.code for issue in validation.issues)
        raise ContractViolation(f"M3 output validation failed: {issue_codes}")
    receipt = CompletionReceipt(
        module_id="M3",
        module_contract_version=MODULE_PROTOCOL_SPEC_VERSION,
        science_contract_version=bundle.meta.science_contract_version,
        canonical_status=CanonicalStatus.PASS,
        native_status="SYNTHETIC_ANALYTIC_ONLY",
        input_artifact_ids=bundle.meta.input_artifact_ids,
        input_hashes=bundle.meta.input_content_hashes,
        science_key=bundle.science_key,
        reproduction_key=bundle.reproduction_key,
        runtime_profile_id="local-cpu",
        output_artifact_ids=(bundle.meta.artifact_id,),
        output_hashes=(bundle.meta.content_sha256,),
        validator_status="PASS",
        validation_issue_codes=tuple(dict.fromkeys(issue.code for issue in validation.issues)),
        started_at_utc=bundle.meta.created_at_utc,
        finished_at_utc=bundle.meta.created_at_utc,
    )
    validated_bundle = replace(bundle, _validation_issues=validation.issues)
    return replace(
        validated_bundle,
        _validated_receipt=receipt,
        _validated_fingerprint=validated_bundle._validation_fingerprint(),
    )
