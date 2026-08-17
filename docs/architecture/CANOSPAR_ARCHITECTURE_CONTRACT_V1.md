# CanoSPAR Architecture Contract v1

Status: implementation target accepted by the project owner on 2026-08-17.

## Scope

This contract freezes stable cross-module interfaces, artifact semantics, lineage, cache identity, invalidation, and runtime boundaries over the existing Week 1, Week 2-4, Week 5-7, and MRIQC v2 work. It does not freeze scientific backends, hardware, schedulers, containers, or server providers.

This task does not run real HCP/PPMI data, MRIQC, fMRIPrep, QSIPrep, FreeSurfer, servers, SSH, Bita, GPU jobs, model training, or formal M2/M3 experiments. M4-M9 remain CONTRACT_ONLY.

## Five layers

| Layer | Responsibility |
| --- | --- |
| L0 Scientific Contract | cohort, task, split, leakage, QC, scientific definitions |
| L1 Artifact Contract | typed cross-module objects, hashes, and stable keys |
| L2 Module API Contract | P0 and M0-M9 public inputs and outputs |
| L3 Execution Contract | validation, receipts, lineage, cache, invalidation |
| L4 Runtime Profile | CPU/GPU, workers, containers, schedulers, transport, server lifecycle |

L0-L3 are stable versioned contracts. L4 is replaceable and must never be embedded in scientific APIs or `science_key`.

## Module graph

~~~text
M0 cohort/task/split
  -> P0 imaging/QC/ROI alignment
  -> M1 graph topology
  -> M2 Laplacian/spectrum/QC
  -> M3 canonical spectral coordinate/bands
  -> M4 band signals
  -> M5 tokens
  -> M6 roles/reliability
  -> M7 routes
  -> M8 prediction/objective
  -> M9 evaluation/interpretation
~~~

Source-of-truth ownership is strict: M0 owns cohort/task/split; P0 owns ROI alignment/QC; M1 owns graph topology; M2 owns Laplacian/spectrum; M3 owns canonical coordinate/bands; M4 owns band signals; M5 owns tokens; M6 owns roles; M7 owns routes; M8 owns prediction/objective; M9 owns evaluation. Downstream modules cannot silently recompute an upstream artifact.

| Module | Input | Output | State |
| --- | --- | --- | --- |
| M0 | existing metadata sources | DatasetManifestArtifact, SplitRegistryArtifact, TaskDefinitionArtifact | EXISTING + adapter |
| P0 | ImagingInputBundle | ROIAlignedSample | PARTIAL |
| M1 | ROIAlignedSample, GraphConstructionSpec, ScienceContext | MultiGraphArtifact | PARTIAL/contract boundary |
| M2 | MultiGraphArtifact, M2Spec, ScienceContext | SpectralBundle | CONTRACT_ONLY |
| M3 | SpectralBundle, coordinate/band specs | CanonicalSpectrumBundle | CONTRACT_ONLY |
| M4 | graph/spectral/canonical bundles | BandSignalBundle | CONTRACT_ONLY |
| M5 | BandSignalBundle | TokenBundle | CONTRACT_ONLY |
| M6 | TokenBundle, QC, availability | RoleBundle | CONTRACT_ONLY |
| M7 | TokenBundle, RoleBundle | RoutingBundle | CONTRACT_ONLY |
| M8 | token/role/route/QC artifacts | embedding/prediction/loss bundles | CONTRACT_ONLY |
| M9 | scientific artifacts and experiment registry | EvaluationBundle | CONTRACT_ONLY |

## Compatibility and identity

GraphData and BrainMultiGraphSample remain the existing data objects and imports remain valid. MultiGraphArtifact wraps BrainMultiGraphSample with ArtifactMeta, atlas identity, ROI table hash, and node-order hash. M0 uses read-only references to existing manifests/reports.

ArtifactMeta, ScienceContext, and NumericsProfile are immutable. `science_key` uses module contract version, input content hashes, science config hash, dataset manifest hash, split, and seed only. `reproduction_key` additionally uses implementation hash and canonical `numerics_profile_hash`. CPU/GPU/server/Bita/SSH/worker values never enter these keys unless a numerical backend change is explicitly represented in NumericsProfile.

A formal run needs CompletionReceipt. Cache reuse is fail-closed: science key, reproduction key, artifact hash, receipt status, and validator status must agree. A change at M3 invalidates M3-M9 while keeping M0, P0, M1, and M2 valid. Runtime-only changes do not invalidate scientific artifacts when scientific and reproduction identities are unchanged.

## Runtime placement and version policy

Week 5-7 archive/extraction/DICOM/BIDS/atlas/QC is P0 plus L3 evidence. MRIQC v2 scheduling, monitoring, handoff, native Linux support, Bita, SSH, and WebTerminal are L3/L4 runtime evidence, not M2-M9 implementations.

The namespaces `architecture_contract_version`, `science_contract_version`, `module_contract_version`, `schema_version`, `runtime_profile_version`, and `numerics_profile_schema_version` remain distinct. PATCH preserves semantics; MINOR adds backward-compatible metadata/backends; MAJOR requires an ADR, migration adapter, compatibility tests, and invalidation analysis.
