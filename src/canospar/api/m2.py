"""M2 Laplacian, spectrum, and graph-quality API boundary."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Protocol

import torch

from canospar.contracts.base import (
    MODULE_PROTOCOL_SPEC_VERSION,
    ArtifactMeta,
    FittedQCState,
    GraphKey,
    MultiGraphArtifact,
    NodeFeatureMatrix,
    QCVector,
    ScienceContext,
)
from canospar.contracts.errors import ContractViolation
from canospar.contracts.execution import CanonicalStatus, CompletionReceipt
from canospar.contracts.spectral import (
    LaplacianArtifact,
    M2Spec,
    NormalizedQCArtifact,
    SpectralBundle,
    SpectralStatistics,
    SpectrumArtifact,
)
from canospar.data.contracts import GraphData
from canospar.spectral.laplacian import (
    build_laplacian_artifact,
    build_unweighted_topology,
)
from canospar.spectral.lineage import (
    canonical_json_hash,
    graph_key_sort_key,
    make_meta,
    multigraph_content_hash,
    numerics_profile,
    science_spec_content_hash,
    spec_content_hash,
)
from canospar.spectral.qc import (
    _qc_parameters,
    build_normalized_qc_artifact,
    fit_qc_state,
    fitted_qc_state_hash,
)
from canospar.spectral.spectrum import build_spectrum_artifact
from canospar.spectral.statistics import build_statistics_artifact
from canospar.validators.m2 import validate_m2_bundle


class M2Backend(Protocol):
    def run_m2(
        self,
        multigraph: MultiGraphArtifact,
        spec: M2Spec,
        context: ScienceContext,
        *,
        qc_state: FittedQCState | None = None,
    ) -> SpectralBundle: ...


def build_normalized_laplacian(
    graph: GraphData,
    spec: M2Spec,
    context: ScienceContext,
    *,
    parent_meta: ArtifactMeta,
) -> LaplacianArtifact:
    return build_laplacian_artifact(graph, spec, context, parent_meta=parent_meta)


def compute_spectrum(
    laplacian: LaplacianArtifact,
    spec: M2Spec,
    context: ScienceContext,
) -> SpectrumArtifact:
    spectrum, _ = build_spectrum_artifact(laplacian, spec, context)
    return spectrum


def compute_spectral_statistics(
    laplacian: LaplacianArtifact,
    spectrum: SpectrumArtifact,
    node_features: NodeFeatureMatrix,
    context: ScienceContext,
    *,
    topology: torch.Tensor | None = None,
) -> SpectralStatistics:
    if topology is None:
        raise ContractViolation("explicit M1 topology is required for spectral statistics")
    return build_statistics_artifact(
        laplacian,
        spectrum,
        node_features,
        context,
        topology=topology,
    )


def fit_qc_transform(train_qc: Sequence[QCVector], spec: M2Spec) -> FittedQCState:
    return fit_qc_state(train_qc, spec)


def transform_qc(
    qc: QCVector,
    state: FittedQCState,
    context: ScienceContext,
    *,
    source_artifact_id: str,
    source_content_hash: str,
) -> NormalizedQCArtifact:
    return build_normalized_qc_artifact(
        qc,
        state,
        context,
        source_artifact_id=source_artifact_id,
        source_content_hash=source_content_hash,
    )


def run_m2(
    multigraph: MultiGraphArtifact,
    spec: M2Spec,
    context: ScienceContext,
    *,
    qc_state: FittedQCState | None = None,
) -> SpectralBundle:
    if not isinstance(multigraph, MultiGraphArtifact):
        raise ContractViolation("multigraph must be MultiGraphArtifact")
    if not isinstance(spec, M2Spec):
        raise ContractViolation("spec must be M2Spec")
    if not isinstance(context, ScienceContext):
        raise ContractViolation("context must be ScienceContext")
    parent_meta = multigraph.meta
    _validate_upstream_multigraph(multigraph, context)

    spec_hash = spec_content_hash(spec)
    if qc_state is not None:
        features, _, _, _ = _qc_parameters(spec)
        state_hash = fitted_qc_state_hash(qc_state)
        if tuple(sorted(qc_state)) != tuple(sorted(features)):
            raise ContractViolation("QC state features must exactly match M2Spec.qc_features")
    else:
        state_hash = None

    graph_items: list[tuple[GraphKey, GraphData]] = []
    for modality, relations in multigraph.sample.graphs.items():
        for relation, graph in relations.items():
            key = GraphKey(
                multigraph.sample.subject_id,
                multigraph.sample.visit_id,
                modality,
                relation,
            )
            graph_items.append((key, graph))
    graph_items.sort(key=lambda item: graph_key_sort_key(item[0]))

    laplacians: list[LaplacianArtifact] = []
    spectra: list[SpectrumArtifact] = []
    statistics: list[SpectralStatistics] = []
    for key, graph in graph_items:
        if not isinstance(graph, GraphData):
            raise ContractViolation("upstream graph mapping must contain GraphData")
        laplacian = build_laplacian_artifact(
            graph,
            spec,
            context,
            parent_meta=parent_meta,
            graph_key=key,
        )
        spectrum, _ = build_spectrum_artifact(laplacian, spec, context)
        stats = build_statistics_artifact(
            laplacian,
            spectrum,
            graph.x,
            context,
            spec,
            topology=build_unweighted_topology(graph),
        )
        laplacians.append(laplacian)
        spectra.append(spectrum)
        statistics.append(stats)

    numerics_hash = numerics_profile(spec).numerics_profile_hash
    normalized_qc = None
    if qc_state is not None:
        normalized_qc = build_normalized_qc_artifact(
            multigraph.sample.qc_vector,
            qc_state,
            context,
            source_artifact_id=parent_meta.artifact_id,
            source_content_hash=parent_meta.content_sha256,
            numerics_profile_hash=numerics_hash,
        )

    science_spec_hash = science_spec_content_hash(spec)
    input_ids = [
        parent_meta.artifact_id,
        f"spec:{spec_hash}",
        f"science-spec:{science_spec_hash}",
    ]
    input_hashes = [parent_meta.content_sha256, spec_hash, science_spec_hash]
    for laplacian, spectrum, stats in zip(laplacians, spectra, statistics, strict=True):
        input_ids.extend(
            (laplacian.meta.artifact_id, spectrum.meta.artifact_id, stats.meta.artifact_id)
        )
        input_hashes.extend(
            (laplacian.meta.content_sha256, spectrum.meta.content_sha256, stats.meta.content_sha256)
        )
    if normalized_qc is not None and state_hash is not None:
        input_ids.append(f"qc-state:{state_hash}")
        input_hashes.append(state_hash)
    bundle_content_hash = canonical_json_hash(
        {
            "laplacians": [artifact.meta.content_sha256 for artifact in laplacians],
            "spectra": [artifact.meta.content_sha256 for artifact in spectra],
            "statistics": [artifact.meta.content_sha256 for artifact in statistics],
            "normalized_qc": normalized_qc.meta.content_sha256 if normalized_qc else None,
        }
    )
    bundle_meta = make_meta(
        artifact_type="SpectralBundle",
        context=context,
        content_sha256=bundle_content_hash,
        input_artifact_ids=input_ids,
        input_content_hashes=input_hashes,
        numerics_profile_hash=numerics_hash,
        created_at_utc=parent_meta.created_at_utc,
    )
    bundle = SpectralBundle(
        meta=bundle_meta,
        laplacians=tuple(laplacians),
        spectra=tuple(spectra),
        statistics=tuple(statistics),
        normalized_qc=normalized_qc,
    )
    validation = validate_m2_bundle(bundle, spec, multigraph, qc_state=qc_state)
    if not validation.is_valid:
        issue_codes = ", ".join(issue.code for issue in validation.issues)
        raise ContractViolation(f"M2 output validation failed: {issue_codes}")
    receipt = CompletionReceipt(
        module_id="M2",
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
    return replace(
        bundle,
        _validated_receipt=receipt,
        _validated_fingerprint=bundle._validation_fingerprint(),
    )


def _validate_upstream_multigraph(
    multigraph: MultiGraphArtifact,
    context: ScienceContext,
) -> None:
    parent_meta = multigraph.meta
    if parent_meta.artifact_type.upper() in {"NOT_READY", "INVALIDATED"}:
        raise ContractViolation("upstream artifact is not ready or has been invalidated")
    if parent_meta.schema_version != "1.0.0":
        raise ContractViolation("upstream artifact schema version is invalid")
    if parent_meta.artifact_type != "MultiGraphArtifact":
        raise ContractViolation("upstream artifact type must be MultiGraphArtifact")
    if parent_meta.producer_module != "M1":
        raise ContractViolation("upstream artifact must be produced by M1")
    if parent_meta.module_contract_version != MODULE_PROTOCOL_SPEC_VERSION:
        raise ContractViolation("upstream artifact uses an incompatible module protocol version")
    if parent_meta.science_contract_version != context.science_contract_version:
        raise ContractViolation("science contract version does not match upstream artifact")
    if parent_meta.science_config_hash != context.science_config_hash:
        raise ContractViolation("science config lineage does not match upstream artifact")
    if parent_meta.dataset_manifest_hash != context.dataset_manifest_hash:
        raise ContractViolation("dataset manifest lineage does not match upstream artifact")
    if parent_meta.split_id != context.split_id:
        raise ContractViolation("split lineage does not match upstream artifact")
    if parent_meta.random_seed != context.random_seed:
        raise ContractViolation("random seed lineage does not match upstream artifact")
    multigraph.sample.validate()
    if not multigraph.sample.graphs:
        raise ContractViolation("M2 requires at least one upstream graph")
    expected_content_hash = multigraph_content_hash(
        multigraph.sample,
        multigraph.atlas_id,
        multigraph.atlas_hash,
        multigraph.roi_table_hash,
        multigraph.node_order_hash,
    )
    if parent_meta.content_sha256 != expected_content_hash:
        raise ContractViolation("upstream artifact content hash does not match its content")
