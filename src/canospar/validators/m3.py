"""Fail-closed validators for the M3 canonical mass coordinate boundary."""

from __future__ import annotations

import math
from collections.abc import Sequence

import torch

from canospar.contracts.bands import (
    BandDefinition,
    BandSpec,
    CanonicalSpectrumArtifact,
    CanonicalSpectrumBundle,
)
from canospar.contracts.base import (
    MODULE_PROTOCOL_SPEC_VERSION,
    GraphKey,
    ScienceContext,
)
from canospar.contracts.errors import ContractViolation
from canospar.contracts.spectral import CanonicalCoordinateSpec, SpectralBundle
from canospar.spectral.lineage import graph_key_sort_key, graph_key_value, tensor_content_hash
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

from .base import ValidationIssue, ValidationReport


def _issue(code: str, severity: str, field: str, message: str) -> ValidationIssue:
    return ValidationIssue(code=code, severity=severity, field=field, message=message)


def _graph_key_field(graph_key: GraphKey, suffix: str) -> str:
    subject, visit, modality, relation = graph_key_value(graph_key)
    return f"subject={subject}|visit={visit}|modality={modality}|relation={relation}:{suffix}"


def _report(checked: Sequence[str], issues: Sequence[ValidationIssue]) -> ValidationReport:
    frozen = tuple(issues)
    status = "FAIL" if any(issue.severity == "ERROR" for issue in frozen) else "PASS"
    return ValidationReport(status=status, checked_invariants=tuple(checked), issues=frozen)


def validate_canonical_bands(bands: Sequence[BandDefinition]) -> ValidationReport:
    checked = (
        "band_mass_boundaries",
        "band_order_and_contiguity",
        "band_ids_unique",
        "m3_does_not_materialize_lambda_boundaries",
    )
    issues: list[ValidationIssue] = []
    try:
        values = tuple(bands)
    except TypeError:
        return _report(
            checked, (_issue("M3_BANDS_TYPE", "ERROR", "bands", "bands must be a sequence"),)
        )
    if not values:
        issues.append(_issue("M3_BANDS_EMPTY", "ERROR", "bands", "at least one band is required"))
        return _report(checked, issues)
    identifiers: set[str] = set()
    previous_upper: float | None = None
    for index, band in enumerate(values):
        field = f"bands[{index}]"
        if not isinstance(band, BandDefinition):
            issues.append(_issue("M3_BAND_TYPE", "ERROR", field, "band must be BandDefinition"))
            continue
        if band.band_id in identifiers:
            issues.append(_issue("M3_BAND_ID_DUPLICATE", "ERROR", field, "band IDs must be unique"))
        identifiers.add(band.band_id)
        if (
            not all(math.isfinite(float(value)) for value in (band.lower_mass, band.upper_mass))
            or not 0.0 <= band.lower_mass < band.upper_mass <= 1.0
        ):
            issues.append(
                _issue(
                    "M3_BAND_BOUNDARY",
                    "ERROR",
                    field,
                    "mass boundaries must satisfy 0 <= lower < upper <= 1",
                )
            )
        if previous_upper is not None and not math.isclose(
            band.lower_mass, previous_upper, rel_tol=0.0, abs_tol=1e-12
        ):
            code = "M3_BAND_GAP" if band.lower_mass > previous_upper else "M3_BAND_OVERLAP"
            issues.append(_issue(code, "ERROR", field, "mass bands must be contiguous and ordered"))
        if band.lower_lambda is not None or band.upper_lambda is not None:
            issues.append(
                _issue(
                    "M3_BAND_LAMBDA_BOUNDARY",
                    "ERROR",
                    field,
                    "M3 must leave lambda boundaries unset for M4",
                )
            )
        previous_upper = band.upper_mass
    if values and not math.isclose(values[0].lower_mass, 0.0, rel_tol=0.0, abs_tol=1e-12):
        issues.append(
            _issue("M3_BAND_START", "ERROR", "bands[0]", "first band must start at mass 0")
        )
    if values and not math.isclose(values[-1].upper_mass, 1.0, rel_tol=0.0, abs_tol=1e-12):
        issues.append(_issue("M3_BAND_END", "ERROR", "bands[-1]", "last band must end at mass 1"))
    return _report(checked, issues)


def _same_context(meta: object, context: ScienceContext) -> bool:
    return (
        getattr(meta, "science_contract_version", None) == context.science_contract_version
        and getattr(meta, "science_config_hash", None) == context.science_config_hash
        and getattr(meta, "dataset_manifest_hash", None) == context.dataset_manifest_hash
        and getattr(meta, "split_id", None) == context.split_id
        and getattr(meta, "random_seed", None) == context.random_seed
    )


def _band_index(u_value: float, bands: Sequence[BandDefinition]) -> int | None:
    for index, band in enumerate(bands):
        if band.lower_mass <= u_value < band.upper_mass:
            return index
        if index == len(bands) - 1 and math.isclose(u_value, band.upper_mass):
            return index
    return None


def _validate_empty_bands(
    artifact: CanonicalSpectrumArtifact,
    bands: Sequence[BandDefinition],
    empty_policy: str,
    issues: list[ValidationIssue],
) -> None:
    assigned = [_band_index(float(value), bands) for value in artifact.u_coordinate.tolist()]
    for index, band in enumerate(bands):
        if index not in assigned:
            realized_mass = (
                sum(value == index for value in assigned) / artifact.u_coordinate.numel()
            )
            severity = "ERROR" if empty_policy == "fail" else "WARNING"
            issues.append(
                _issue(
                    "M3_EMPTY_BAND",
                    severity,
                    _graph_key_field(artifact.graph_key, band.band_id),
                    f"band is empty for graph; realized_mass={realized_mass:.17g}",
                )
            )


def _validate_tie_boundaries(
    artifact: CanonicalSpectrumArtifact,
    bands: Sequence[BandDefinition],
    tie_atol: float,
    tie_rtol: float,
    issues: list[ValidationIssue],
) -> None:
    values = artifact.lambda_coordinate
    start = 0
    while start < values.numel():
        end = start
        while end + 1 < values.numel() and bool(
            torch.isclose(values[end], values[end + 1], atol=tie_atol, rtol=tie_rtol)
        ):
            end += 1
        assigned = {
            _band_index(float(value), bands)
            for value in artifact.u_coordinate[start : end + 1].tolist()
        }
        if len(assigned) != 1:
            issues.append(
                _issue(
                    "M3_TIE_SPLIT",
                    "ERROR",
                    _graph_key_field(artifact.graph_key, f"u_coordinate[{start}:{end + 1}]"),
                    "one spectral tie block was assigned to multiple mass bands",
                )
            )
        start = end + 1


def validate_m3_bundle(
    bundle: CanonicalSpectrumBundle,
    spectral_bundle: SpectralBundle,
    coordinate_spec: CanonicalCoordinateSpec,
    band_spec: BandSpec,
    context: ScienceContext,
) -> ValidationReport:
    checked = (
        "upstream_m2_identity_and_receipt",
        "science_lineage_and_content_hashes",
        "canonical_empirical_mid_cdf",
        "tie_blocks_are_intact",
        "mass_band_assignment",
        "m3_lambda_boundaries_are_unset",
        "stable_graph_key_order",
        "upstream_artifacts_are_not_mutated",
    )
    issues: list[ValidationIssue] = []
    if not isinstance(bundle, CanonicalSpectrumBundle):
        return _report(
            checked, (_issue("M3_OUTPUT_TYPE", "ERROR", "bundle", "invalid M3 output type"),)
        )
    try:
        tie_atol, tie_rtol, empty_policy = validate_coordinate_spec(coordinate_spec)
        validate_band_spec(band_spec)
    except ContractViolation as error:
        issues.append(_issue("M3_SPEC_INVALID", "ERROR", "spec", str(error)))
        return _report(checked, issues)
    band_report = validate_canonical_bands(bundle.bands)
    issues.extend(band_report.issues)
    if len(bundle.bands) != band_spec.band_count:
        issues.append(
            _issue("M3_BAND_COUNT", "ERROR", "bands", "band count does not match BandSpec")
        )
    if not isinstance(spectral_bundle, SpectralBundle):
        issues.append(
            _issue("M3_UPSTREAM_TYPE", "ERROR", "spectral_bundle", "invalid upstream type")
        )
        return _report(checked, issues)
    upstream_meta = spectral_bundle.meta
    if upstream_meta.artifact_type.upper() in {"NOT_READY", "INVALIDATED"}:
        issues.append(
            _issue(
                "M3_UPSTREAM_NOT_READY",
                "ERROR",
                "spectral_bundle.meta",
                "upstream is not consumable",
            )
        )
    if upstream_meta.artifact_type != "SpectralBundle":
        issues.append(
            _issue(
                "M3_UPSTREAM_TYPE",
                "ERROR",
                "spectral_bundle.meta.artifact_type",
                "upstream must be SpectralBundle",
            )
        )
    if upstream_meta.producer_module != "M2":
        issues.append(
            _issue(
                "M3_UPSTREAM_PRODUCER",
                "ERROR",
                "spectral_bundle.meta.producer_module",
                "upstream must be produced by M2",
            )
        )
    if upstream_meta.module_contract_version != MODULE_PROTOCOL_SPEC_VERSION:
        issues.append(
            _issue(
                "M3_UPSTREAM_PROTOCOL",
                "ERROR",
                "spectral_bundle.meta.module_contract_version",
                "upstream protocol version is incompatible",
            )
        )
    if not _same_context(upstream_meta, context):
        issues.append(
            _issue(
                "M3_LINEAGE",
                "ERROR",
                "spectral_bundle.meta",
                "science lineage does not match context",
            )
        )
    receipt = spectral_bundle.receipt
    if receipt is None or receipt.module_id != "M2" or receipt.canonical_status.value != "PASS":
        issues.append(
            _issue(
                "M3_UPSTREAM_RECEIPT",
                "ERROR",
                "spectral_bundle.receipt",
                "M2 PASS receipt is required",
            )
        )
    coordinate_hash = coordinate_spec_content_hash(coordinate_spec)
    band_hash = band_spec_content_hash(band_spec)
    expected_graph_order = tuple(
        sorted(spectral_bundle.spectra, key=lambda item: graph_key_sort_key(item.graph_key))
    )
    if tuple(item.graph_key for item in bundle.spectra) != tuple(
        item.graph_key for item in expected_graph_order
    ):
        issues.append(
            _issue("M3_GRAPH_ORDER", "ERROR", "spectra", "spectra must use stable GraphKey order")
        )
    if len(bundle.spectra) != len(expected_graph_order):
        issues.append(
            _issue(
                "M3_SPECTRUM_COUNT",
                "ERROR",
                "spectra",
                "one canonical spectrum per M2 spectrum is required",
            )
        )
    if len(bundle.spectra) == len(expected_graph_order):
        for canonical, source in zip(bundle.spectra, expected_graph_order, strict=True):
            field = f"spectra[{source.graph_key.modality}]"
            if (
                source.meta.artifact_type != "SpectrumArtifact"
                or source.meta.producer_module != "M2"
            ):
                issues.append(
                    _issue(
                        "M3_SOURCE_SPECTRUM_LINEAGE",
                        "ERROR",
                        field,
                        "source spectrum must be an M2 SpectrumArtifact",
                    )
                )
            if (
                source.meta.module_contract_version != MODULE_PROTOCOL_SPEC_VERSION
                or not _same_context(source.meta, context)
            ):
                issues.append(
                    _issue(
                        "M3_SOURCE_SPECTRUM_LINEAGE",
                        "ERROR",
                        field,
                        "source spectrum lineage is incompatible",
                    )
                )
            if source.meta.content_sha256 != tensor_content_hash(source.eigenvalues):
                issues.append(
                    _issue(
                        "M3_SOURCE_HASH",
                        "ERROR",
                        field,
                        "source spectrum content hash is inconsistent",
                    )
                )
            try:
                expected_u = empirical_mid_rank_coordinate(source.eigenvalues, tie_atol, tie_rtol)
            except ContractViolation as error:
                issues.append(_issue("M3_SOURCE_SPECTRUM_INVALID", "ERROR", field, str(error)))
                continue
            if not isinstance(canonical, CanonicalSpectrumArtifact):
                issues.append(
                    _issue(
                        "M3_CANONICAL_TYPE", "ERROR", field, "canonical spectrum has invalid type"
                    )
                )
                continue
            if canonical.spectrum_artifact_id != source.meta.artifact_id:
                issues.append(
                    _issue(
                        "M3_SPECTRUM_ARTIFACT_ID",
                        "ERROR",
                        _graph_key_field(source.graph_key, "spectrum_artifact_id"),
                        "canonical spectrum must reference its M2 source artifact",
                    )
                )
            if canonical.graph_key != source.graph_key:
                issues.append(
                    _issue("M3_GRAPH_KEY", "ERROR", field, "canonical GraphKey differs from M2")
                )
            if not torch.equal(canonical.lambda_coordinate, source.eigenvalues):
                issues.append(
                    _issue(
                        "M3_LAMBDA_COPY",
                        "ERROR",
                        field,
                        "lambda coordinate must copy M2 eigenvalues",
                    )
                )
            if not torch.equal(canonical.u_coordinate, expected_u):
                issues.append(
                    _issue(
                        "M3_COORDINATE_VALUE",
                        "ERROR",
                        field,
                        "u coordinate is not the empirical mid-CDF",
                    )
                )
            if canonical.u_coordinate.numel() and (
                not bool(torch.isfinite(canonical.u_coordinate).all())
                or not bool((canonical.u_coordinate > 0.0).all())
                or not bool((canonical.u_coordinate < 1.0).all())
                or (
                    canonical.u_coordinate.numel() > 1
                    and not bool((canonical.u_coordinate[:-1] <= canonical.u_coordinate[1:]).all())
                )
            ):
                issues.append(
                    _issue(
                        "M3_COORDINATE_RANGE",
                        "ERROR",
                        field,
                        "u coordinate must be finite, ordered, and in (0,1)",
                    )
                )
            canonical_content_hash = canonical_spectrum_content_hash(
                canonical.u_coordinate, canonical.lambda_coordinate
            )
            expected_meta = make_m3_meta(
                artifact_type="CanonicalSpectrumArtifact",
                context=context,
                content_sha256=canonical_content_hash,
                input_artifact_ids=(source.meta.artifact_id, f"coordinate-spec:{coordinate_hash}"),
                input_content_hashes=(source.meta.content_sha256, coordinate_hash),
                numerics_profile_hash=source.meta.numerics_profile_hash,
                graph_key=source.graph_key,
                created_at_utc=source.meta.created_at_utc,
            )
            if canonical.meta != expected_meta:
                issues.append(
                    _issue(
                        "M3_CANONICAL_LINEAGE",
                        "ERROR",
                        field,
                        "canonical spectrum metadata does not match its inputs",
                    )
                )
            _validate_empty_bands(canonical, bundle.bands, empty_policy, issues)
            _validate_tie_boundaries(canonical, bundle.bands, tie_atol, tie_rtol, issues)
    expected_input_ids = (
        upstream_meta.artifact_id,
        f"coordinate-spec:{coordinate_hash}",
        f"band-spec:{band_hash}",
        *(item.meta.artifact_id for item in bundle.spectra),
    )
    expected_input_hashes = (
        upstream_meta.content_sha256,
        coordinate_hash,
        band_hash,
        *(item.meta.content_sha256 for item in bundle.spectra),
    )
    expected_bundle_hash = canonical_bundle_content_hash(bundle.spectra, bundle.bands)
    expected_bundle_meta = make_m3_meta(
        artifact_type="CanonicalSpectrumBundle",
        context=context,
        content_sha256=expected_bundle_hash,
        input_artifact_ids=expected_input_ids,
        input_content_hashes=expected_input_hashes,
        numerics_profile_hash=(
            expected_graph_order[0].meta.numerics_profile_hash
            if expected_graph_order
            else "m3-none"
        ),
        created_at_utc=upstream_meta.created_at_utc,
    )
    if bundle.meta != expected_bundle_meta:
        issues.append(
            _issue(
                "M3_BUNDLE_LINEAGE",
                "ERROR",
                "bundle.meta",
                "bundle metadata does not match its inputs",
            )
        )
    return _report(checked, issues)
