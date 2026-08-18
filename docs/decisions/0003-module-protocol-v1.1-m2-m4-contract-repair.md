# ADR 0003: Module Protocol v1.1.0 M2-M4 Contract Repair

- Status: accepted for local implementation
- Date: 2026-08-18

## Decision

Adopt module protocol specification `1.1.0` as the canonical cross-module interface for CanoSPAR. The architecture, science, schema, runtime, and numerics namespaces remain unchanged at their existing contract versions.

The migration closes the following boundaries without implementing scientific algorithms:

1. M2 exposes explicit `FittedQCState` semantics, frozen-state QC transformation, context/lineage inputs, and the keyword-only `qc_state` on `run_m2`.
2. M3 exposes context-aware canonical mass coordinates, tie-aware band contracts, and `ValidationReport`/sequence types.
3. M4 retains its exact-filter, Chebyshev-filter, and canonical-band-filter inputs and remains fail-closed.
4. M0 gains the required split/task loaders and imaging-input builder signatures; all remain read-only contract-only adapters.
5. Artifact annotations close previously unbounded `object`/`Any` fields to existing aliases, tensors, keys, tuples, or JSON mappings.

## Cache and invalidation

For M2-M9, the module protocol version is part of cache eligibility. A v1.0.0 M2-M9 canonical cache or completion receipt cannot be reused by v1.1.0. This is a cache-eligibility boundary, not a scientific recomputation claim. M0/P0/M1 are not automatically invalidated by the protocol upgrade and retain their prior receipt eligibility. Runtime profile changes remain outside `science_key`; numerics profile changes remain part of `reproduction_key`.

## Non-goals

This ADR does not implement MRI ingestion, graph construction outside the M1 boundary, canonical coordinates, filtering, tokenization, role inference, routing, prediction, evaluation, GPU execution, server execution, or scientific results. M2 is implemented by the follow-up protocol-compliant Laplacian, exact spectrum, spectral statistics and QC path; M3-M9 remain `CONTRACT_ONLY`.
