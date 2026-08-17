# ADR 0002: CanoSPAR Architecture Contract v1

- Status: accepted for implementation
- Date: 2026-08-17

## Decision

Freeze cross-module artifact and API semantics without freezing scientific backends or runtime infrastructure. Preserve existing Week 1, M0, Week 5-7, and MRIQC v2 through wrappers, adapters, and documentation rather than destructive relocation.

## Rationale

The project contains both scientific data contracts and operational execution work. A formal boundary prevents runtime changes from invalidating scientific artifacts and prevents contracts from being mistaken for completed algorithms.

## Consequences

L0-L3 are stable and versioned. L4 is replaceable. `RuntimeProfile` and `NumericsProfile` remain separate: runtime placement is operational evidence, while numerical semantics participate in `reproduction_key`. M4-M9 remain CONTRACT_ONLY until real implementations and validation evidence exist. Breaking changes require a version bump, migration adapter, compatibility tests, and invalidation analysis.
