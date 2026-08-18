"""Fail-closed validation for M2 spectral artifacts."""

from __future__ import annotations

import math
from collections.abc import Iterable

import torch

from canospar.contracts.base import (
    MODULE_PROTOCOL_SPEC_VERSION,
    ArtifactMeta,
    FittedQCState,
    GraphKey,
    MultiGraphArtifact,
)
from canospar.contracts.errors import ContractViolation
from canospar.contracts.spectral import (
    M2Spec,
    NormalizedQCArtifact,
    SpectralBundle,
)
from canospar.spectral.lineage import (
    M2_IMPLEMENTATION_HASH,
    _artifact_id,
    canonical_json_hash,
    graph_key_sort_key,
    numerics_profile,
    science_spec_content_hash,
    solver_tolerance,
    spec_content_hash,
    tensor_content_hash,
)
from canospar.spectral.qc import qc_features, qc_issue_codes
from canospar.spectral.statistics import FIXED_STATISTIC_KEYS

from .base import ValidationIssue, ValidationReport


def _issue(code: str, field: str, message: str) -> ValidationIssue:
    return ValidationIssue(code=code, severity="ERROR", field=field, message=message)


def _warning(code: str, field: str, message: str) -> ValidationIssue:
    return ValidationIssue(code=code, severity="WARNING", field=field, message=message)


def _check_artifact_id(
    meta: ArtifactMeta,
    expected_type: str,
    graph_key: GraphKey | None,
    input_artifact_ids: tuple[str, ...],
    issues: list[ValidationIssue],
    field_prefix: str,
) -> None:
    expected_id = _artifact_id(
        expected_type,
        meta.content_sha256,
        graph_key,
        input_artifact_ids,
    )
    if meta.artifact_id != expected_id:
        issues.append(
            _issue(
                "ARTIFACT_ID",
                f"{field_prefix}.artifact_id",
                "does not match the deterministic artifact identity",
            )
        )


def _expected_heat_trace_keys(spec: M2Spec, issues: list[ValidationIssue]) -> set[str]:
    times = spec.parameters.get("diffusion_times")
    if times is None:
        return set()
    if isinstance(times, str | bytes) or not isinstance(times, Iterable):
        issues.append(
            _issue("DIFFUSION_CONFIG", "diffusion_times", "must be a finite positive sequence")
        )
        return set()
    keys: set[str] = set()
    for time in times:
        if isinstance(time, bool) or not isinstance(time, int | float) or not math.isfinite(time):
            issues.append(
                _issue("DIFFUSION_CONFIG", "diffusion_times", "must contain finite numbers")
            )
            continue
        if time <= 0:
            issues.append(
                _issue("DIFFUSION_CONFIG", "diffusion_times", "must contain positive numbers")
            )
            continue
        keys.add(f"heat_trace_t{float(time):g}")
    return keys


def _check_meta(
    meta: ArtifactMeta,
    expected_type: str,
    parent_meta: ArtifactMeta,
    expected_numerics_hash: str,
    issues: list[ValidationIssue],
    field_prefix: str,
) -> None:
    if meta.schema_version != "1.0.0":
        issues.append(_issue("SCHEMA_VERSION", f"{field_prefix}.schema_version", "must be 1.0.0"))
    if meta.artifact_type != expected_type:
        issues.append(
            _issue("ARTIFACT_TYPE", f"{field_prefix}.artifact_type", f"must be {expected_type}")
        )
    if meta.producer_module != "M2":
        issues.append(_issue("PRODUCER_MODULE", f"{field_prefix}.producer_module", "must be M2"))
    if meta.implementation_hash != M2_IMPLEMENTATION_HASH:
        issues.append(
            _issue(
                "IMPLEMENTATION_IDENTITY",
                f"{field_prefix}.implementation_hash",
                "must match the active M2 implementation identity",
            )
        )
    if meta.numerics_profile_hash != expected_numerics_hash:
        issues.append(
            _issue(
                "NUMERICS_IDENTITY",
                f"{field_prefix}.numerics_profile_hash",
                "must match the active M2 numerics profile",
            )
        )
    if meta.module_contract_version != MODULE_PROTOCOL_SPEC_VERSION:
        issues.append(
            _issue(
                "MODULE_PROTOCOL_VERSION",
                f"{field_prefix}.module_contract_version",
                "must match the active module protocol",
            )
        )
    for field_name in (
        "science_contract_version",
        "science_config_hash",
        "dataset_manifest_hash",
        "split_id",
        "random_seed",
    ):
        if getattr(meta, field_name) != getattr(parent_meta, field_name):
            issues.append(
                _issue(
                    "LINEAGE_MISMATCH",
                    f"{field_prefix}.{field_name}",
                    "must match the upstream artifact",
                )
            )


def _contains_pair(meta: ArtifactMeta, artifact_id: str, content_hash: str) -> bool:
    return any(
        current_id == artifact_id and current_hash == content_hash
        for current_id, current_hash in zip(
            meta.input_artifact_ids,
            meta.input_content_hashes,
            strict=True,
        )
    )


def _pairs(meta: ArtifactMeta) -> tuple[tuple[str, str], ...]:
    return tuple(zip(meta.input_artifact_ids, meta.input_content_hashes, strict=True))


def _expected_graph_keys(parent: MultiGraphArtifact) -> tuple[GraphKey, ...]:
    keys = [
        GraphKey(parent.sample.subject_id, parent.sample.visit_id, modality, relation)
        for modality, relations in parent.sample.graphs.items()
        for relation in relations
    ]
    return tuple(sorted(keys, key=graph_key_sort_key))


def validate_m2_bundle(
    bundle: SpectralBundle,
    spec: M2Spec,
    parent: MultiGraphArtifact,
    *,
    qc_state: FittedQCState | None = None,
) -> ValidationReport:
    """Validate M2 outputs before a canonical PASS receipt can be exposed."""
    if not isinstance(bundle, SpectralBundle):
        raise ContractViolation("bundle must be SpectralBundle")
    if not isinstance(spec, M2Spec):
        raise ContractViolation("spec must be M2Spec")
    if not isinstance(parent, MultiGraphArtifact):
        raise ContractViolation("parent must be MultiGraphArtifact")
    parent_meta = parent.meta
    parent.sample.validate()

    issues: list[ValidationIssue] = []
    checked = [
        "bundle_metadata",
        "child_metadata",
        "graph_key_alignment",
        "laplacian_finiteness_and_symmetry",
        "spectrum_length_order_and_bounds",
        "fixed_statistics_keys",
        "content_hash_lineage",
        "implementation_and_numerics_identity",
        "m1_graph_key_provenance",
        "qc_diagnostic_codes",
    ]
    expected_numerics_hash = numerics_profile(spec).numerics_profile_hash
    _check_meta(
        bundle.meta,
        "SpectralBundle",
        parent_meta,
        expected_numerics_hash,
        issues,
        "bundle.meta",
    )
    if not bundle.laplacians:
        issues.append(_issue("EMPTY_BUNDLE", "bundle", "must contain at least one graph"))
    if not _contains_pair(bundle.meta, parent_meta.artifact_id, parent_meta.content_sha256):
        issues.append(
            _issue("PARENT_LINEAGE", "bundle.meta", "must contain the parent id/hash pair")
        )

    expected_keys = _expected_graph_keys(parent)
    graph_by_key = {
        GraphKey(parent.sample.subject_id, parent.sample.visit_id, modality, relation): graph
        for modality, relations in parent.sample.graphs.items()
        for relation, graph in relations.items()
    }
    if tuple(item.graph_key for item in bundle.laplacians) != expected_keys:
        issues.append(
            _issue(
                "GRAPH_KEY_PROVENANCE",
                "bundle.laplacians.graph_key",
                "child GraphKeys must be the sorted GraphKeys present in M1",
            )
        )
    if len(bundle.laplacians) != len(expected_keys):
        issues.append(
            _issue(
                "GRAPH_KEY_PROVENANCE",
                "bundle.laplacians",
                "child graph count must match the M1 graph count",
            )
        )

    science_spec_hash = science_spec_content_hash(spec)
    science_spec_pair = (f"science-spec:{science_spec_hash}", science_spec_hash)
    spec_hash = spec_content_hash(spec)
    spec_pair = (f"spec:{spec_hash}", spec_hash)
    expected_bundle_pairs: list[tuple[str, str]] = [
        (parent_meta.artifact_id, parent_meta.content_sha256),
        spec_pair,
        science_spec_pair,
    ]
    if science_spec_pair not in _pairs(bundle.meta):
        issues.append(
            _issue(
                "SCIENCE_SPEC_LINEAGE",
                "bundle.meta.input_artifact_ids",
                "must contain the exact science-spec id/hash pair for M2Spec",
            )
        )

    tolerance = solver_tolerance(spec)
    for index, (laplacian, spectrum, statistics) in enumerate(
        zip(bundle.laplacians, bundle.spectra, bundle.statistics, strict=True)
    ):
        prefix = f"graphs[{index}]"
        _check_meta(
            laplacian.meta,
            "LaplacianArtifact",
            parent_meta,
            expected_numerics_hash,
            issues,
            f"{prefix}.laplacian.meta",
        )
        _check_meta(
            spectrum.meta,
            "SpectrumArtifact",
            parent_meta,
            expected_numerics_hash,
            issues,
            f"{prefix}.spectrum.meta",
        )
        _check_meta(
            statistics.meta,
            "SpectralStatistics",
            parent_meta,
            expected_numerics_hash,
            issues,
            f"{prefix}.statistics.meta",
        )
        if not (laplacian.graph_key == spectrum.graph_key == statistics.graph_key):
            issues.append(_issue("GRAPH_KEY_ALIGNMENT", prefix, "child GraphKeys must match"))
        if not _contains_pair(
            laplacian.meta,
            parent_meta.artifact_id,
            parent_meta.content_sha256,
        ):
            issues.append(
                _issue("PARENT_LINEAGE", f"{prefix}.laplacian.meta", "parent id/hash missing")
            )
        if not _contains_pair(
            spectrum.meta,
            laplacian.meta.artifact_id,
            laplacian.meta.content_sha256,
        ):
            issues.append(
                _issue("CHILD_LINEAGE", f"{prefix}.spectrum.meta", "laplacian id/hash missing")
            )
        if not _contains_pair(
            statistics.meta,
            laplacian.meta.artifact_id,
            laplacian.meta.content_sha256,
        ) or not _contains_pair(
            statistics.meta,
            spectrum.meta.artifact_id,
            spectrum.meta.content_sha256,
        ):
            issues.append(
                _issue("CHILD_LINEAGE", f"{prefix}.statistics.meta", "upstream id/hash missing")
            )

        graph_key = expected_keys[index] if index < len(expected_keys) else laplacian.graph_key
        graph = graph_by_key.get(graph_key)
        if graph is None:
            continue
        expected_laplacian_input_ids = (
            (parent_meta.artifact_id, parent_meta.content_sha256),
            (f"graph:{graph.construction_hash}", graph.construction_hash),
        )
        expected_laplacian_id = _artifact_id(
            "LaplacianArtifact",
            laplacian.meta.content_sha256,
            graph_key,
            tuple(artifact_id for artifact_id, _ in expected_laplacian_input_ids),
        )
        expected_spectrum_input_ids = (expected_laplacian_id,)
        expected_spectrum_id = _artifact_id(
            "SpectrumArtifact",
            spectrum.meta.content_sha256,
            graph_key,
            expected_spectrum_input_ids,
        )
        node_features_hash = tensor_content_hash(graph.x)
        expected_statistics_input_ids = (
            expected_laplacian_id,
            expected_spectrum_id,
            f"node-features:{node_features_hash}",
        )
        expected_statistics_id = _artifact_id(
            "SpectralStatistics",
            statistics.meta.content_sha256,
            graph_key,
            expected_statistics_input_ids,
        )
        expected_statistics_pairs = (
            (expected_laplacian_id, laplacian.meta.content_sha256),
            (expected_spectrum_id, spectrum.meta.content_sha256),
            (f"node-features:{node_features_hash}", node_features_hash),
        )
        if _pairs(laplacian.meta) != expected_laplacian_input_ids:
            issues.append(
                _issue(
                    "CHILD_LINEAGE",
                    f"{prefix}.laplacian.meta.input_artifact_ids",
                    "must exactly identify the M1 graph construction",
                )
            )
        if _pairs(spectrum.meta) != ((expected_laplacian_id, laplacian.meta.content_sha256),):
            issues.append(
                _issue(
                    "CHILD_LINEAGE",
                    f"{prefix}.spectrum.meta.input_artifact_ids",
                    "must exactly identify the Laplacian artifact",
                )
            )
        if _pairs(statistics.meta) != expected_statistics_pairs:
            issues.append(
                _issue(
                    "CHILD_LINEAGE",
                    f"{prefix}.statistics.meta.input_artifact_ids",
                    "must exactly identify Laplacian, spectrum, and node features",
                )
            )
        _check_artifact_id(
            laplacian.meta,
            "LaplacianArtifact",
            graph_key,
            tuple(artifact_id for artifact_id, _ in expected_laplacian_input_ids),
            issues,
            f"{prefix}.laplacian.meta",
        )
        _check_artifact_id(
            spectrum.meta,
            "SpectrumArtifact",
            graph_key,
            expected_spectrum_input_ids,
            issues,
            f"{prefix}.spectrum.meta",
        )
        _check_artifact_id(
            statistics.meta,
            "SpectralStatistics",
            graph_key,
            expected_statistics_input_ids,
            issues,
            f"{prefix}.statistics.meta",
        )
        expected_bundle_pairs.extend(
            (
                (expected_laplacian_id, laplacian.meta.content_sha256),
                (expected_spectrum_id, spectrum.meta.content_sha256),
                (expected_statistics_id, statistics.meta.content_sha256),
            )
        )

        payload = laplacian.payload.detach().cpu().to(torch.float64)
        if payload.dim() != 2 or payload.size(0) != payload.size(1):
            issues.append(
                _issue("LAPLACIAN_SHAPE", f"{prefix}.laplacian.payload", "must be square")
            )
        elif not torch.allclose(payload, payload.T, atol=tolerance, rtol=tolerance):
            issues.append(
                _issue("LAPLACIAN_SYMMETRY", f"{prefix}.laplacian.payload", "must be symmetric")
            )
        if laplacian.meta.content_sha256 != tensor_content_hash(laplacian.payload):
            issues.append(
                _issue(
                    "ARTIFACT_HASH",
                    f"{prefix}.laplacian.meta.content_sha256",
                    "does not match payload",
                )
            )

        values = spectrum.eigenvalues.detach().cpu().to(torch.float64)
        if values.numel() != payload.size(0):
            issues.append(
                _issue("SPECTRUM_LENGTH", f"{prefix}.spectrum.eigenvalues", "must match node count")
            )
        if not bool(torch.isfinite(values).all()):
            issues.append(
                _issue("SPECTRUM_FINITE", f"{prefix}.spectrum.eigenvalues", "must be finite")
            )
        if values.numel() > 1 and bool((values[:-1] > values[1:]).any()):
            issues.append(
                _issue("SPECTRUM_ORDER", f"{prefix}.spectrum.eigenvalues", "must be ascending")
            )
        if values.numel() and (
            float(values.min()) < -tolerance or float(values.max()) > 2.0 + tolerance
        ):
            issues.append(
                _issue("SPECTRUM_BOUNDS", f"{prefix}.spectrum.eigenvalues", "must lie in [0, 2]")
            )
        if spectrum.meta.content_sha256 != tensor_content_hash(spectrum.eigenvalues):
            issues.append(
                _issue(
                    "ARTIFACT_HASH",
                    f"{prefix}.spectrum.meta.content_sha256",
                    "does not match payload",
                )
            )

        expected_statistic_keys = set(FIXED_STATISTIC_KEYS) | _expected_heat_trace_keys(
            spec, issues
        )
        if set(statistics.values) != expected_statistic_keys:
            issues.append(
                _issue(
                    "STATISTICS_KEYS", f"{prefix}.statistics.values", "must use fixed protocol keys"
                )
            )
        if statistics.meta.content_sha256 != canonical_json_hash(dict(statistics.values)):
            issues.append(
                _issue(
                    "ARTIFACT_HASH",
                    f"{prefix}.statistics.meta.content_sha256",
                    "does not match values",
                )
            )

    if bundle.normalized_qc is not None:
        normalized_qc = bundle.normalized_qc
        _check_meta(
            normalized_qc.meta,
            "NormalizedQCArtifact",
            parent_meta,
            expected_numerics_hash,
            issues,
            "normalized_qc.meta",
        )
        if not _contains_pair(
            normalized_qc.meta,
            parent_meta.artifact_id,
            parent_meta.content_sha256,
        ):
            issues.append(_issue("QC_LINEAGE", "normalized_qc.meta", "parent id/hash missing"))
        if not any(
            value.startswith("qc-state:") for value in normalized_qc.meta.input_artifact_ids
        ):
            issues.append(_issue("QC_STATE_LINEAGE", "normalized_qc.meta", "state hash missing"))
        state_pairs = [
            (artifact_id, content_hash)
            for artifact_id, content_hash in zip(
                normalized_qc.meta.input_artifact_ids,
                normalized_qc.meta.input_content_hashes,
                strict=True,
            )
            if artifact_id.startswith("qc-state:")
        ]
        if len(state_pairs) != 1 or state_pairs[0][0] != f"qc-state:{state_pairs[0][1]}":
            issues.append(
                _issue(
                    "QC_STATE_LINEAGE",
                    "normalized_qc.meta",
                    "state id and hash must agree",
                )
            )
        if len(state_pairs) == 1:
            expected_state_pair = (f"qc-state:{state_pairs[0][1]}", state_pairs[0][1])
            expected_qc_pairs = (
                (parent_meta.artifact_id, parent_meta.content_sha256),
                expected_state_pair,
            )
            if _pairs(normalized_qc.meta) != expected_qc_pairs:
                issues.append(
                    _issue(
                        "QC_LINEAGE",
                        "normalized_qc.meta.input_artifact_ids",
                        "must exactly identify the parent and fitted QC state",
                    )
                )
            _check_artifact_id(
                normalized_qc.meta,
                "NormalizedQCArtifact",
                None,
                tuple(artifact_id for artifact_id, _ in expected_qc_pairs),
                issues,
                "normalized_qc.meta",
            )
            expected_bundle_pairs.append(expected_state_pair)
        if set(normalized_qc.values) != set(qc_features(spec)):
            issues.append(
                _issue(
                    "QC_KEYS",
                    "normalized_qc.values",
                    "must match M2Spec.qc_features",
                )
            )
        if normalized_qc.meta.content_sha256 != canonical_json_hash(dict(normalized_qc.values)):
            issues.append(
                _issue(
                    "ARTIFACT_HASH", "normalized_qc.meta.content_sha256", "does not match values"
                )
            )

    if _pairs(bundle.meta) != tuple(expected_bundle_pairs):
        issues.append(
            _issue(
                "BUNDLE_LINEAGE",
                "bundle.meta.input_artifact_ids",
                "must exactly identify the parent, spec, child artifacts, and QC state",
            )
        )
    _check_artifact_id(
        bundle.meta,
        "SpectralBundle",
        None,
        tuple(artifact_id for artifact_id, _ in expected_bundle_pairs),
        issues,
        "bundle.meta",
    )
    if qc_state is not None:
        for code in qc_issue_codes(qc_state, spec):
            issues.append(_warning(code, "qc_state", "fitted QC state contains a constant feature"))

    expected_bundle_hash = canonical_json_hash(
        {
            "laplacians": [item.meta.content_sha256 for item in bundle.laplacians],
            "spectra": [item.meta.content_sha256 for item in bundle.spectra],
            "statistics": [item.meta.content_sha256 for item in bundle.statistics],
            "normalized_qc": (
                bundle.normalized_qc.meta.content_sha256
                if isinstance(bundle.normalized_qc, NormalizedQCArtifact)
                else None
            ),
        }
    )
    if bundle.meta.content_sha256 != expected_bundle_hash:
        issues.append(
            _issue("ARTIFACT_HASH", "bundle.meta.content_sha256", "does not match child hashes")
        )

    return ValidationReport(
        status="FAIL" if any(issue.severity == "ERROR" for issue in issues) else "PASS",
        checked_invariants=tuple(checked),
        issues=tuple(issues),
    )
