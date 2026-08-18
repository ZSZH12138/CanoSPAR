# CanoSPAR M2 Implementation Report

## 1. Status and boundary

- `module_protocol_spec_version`: `1.1.0`
- `science_contract_version`: `1.1.0`
- `architecture_contract_version`: `1.0.0`
- `implementation_status`: `IMPLEMENTED`
- `scientific_verification_status`: `NOT_VERIFIED`
- Evidence scope: synthetic graphs, analytic graph truth, CPU numerical checks, contract checks only.

Real MRI data, real HCP/PPMI imaging, MRI preprocessing tools, servers, Bita, SSH, WebTerminal, GPU/CUDA, model training, M3 and M4 were not used.

## 2. Git and versions

- Starting branch: `codex/m2-implementation-v1.1`
- Starting HEAD for this compliance follow-up: `c1d0538d751f14730a6fd119b2e3dbedd07ccb5f`
- Final branch for the validated implementation: `codex/m2-implementation-v1.1`
- Prior implementation commits remain in branch history; this follow-up closes the remaining protocol-compliance and regression gaps.
- Pushed: `false`
- Main modified: `false`

## 3. Implemented public functions

- `build_normalized_laplacian`: validates M1 graph policy and builds the normalized Laplacian.
- `compute_spectrum`: computes the exact CPU symmetric spectrum and validates bounds/residuals.
- `compute_spectral_statistics`: produces the fixed topology/spectral statistics set and requires explicit M1 topology; it fails closed when topology is omitted.
- `fit_qc_transform`: fits train-only median, winsor bounds and robust scale.
- `transform_qc`: consumes an immutable fitted state without refitting.
- `run_m2`: canonical stable-order M1→M2 orchestration with optional frozen QC state; consumes upstream `GraphData` topology directly and performs upstream metadata/content-hash preflight.

Supporting modules are split into `src/canospar/spectral/laplacian.py`, `spectrum.py`, `statistics.py`, `qc.py` and `lineage.py`; no new cross-module artifact class was added.

The repair adds `src/canospar/validators/m2.py`, which validates M2 bundle metadata, exact parent/child lineage, M1 GraphKey provenance, implementation/numerics identity, science-spec and QC-state bindings, Laplacian/spectrum/statistics invariants, exact normalized-QC feature coverage and content hashes before a canonical PASS receipt is exposed. Empty bundles and non-binary formal topology are rejected. `SpectralBundle` keeps a private validator attestation and fingerprint; only a canonical `run_m2` result carries a PASS receipt, while hand-reconstructed or tampered bundles fail closed.

## 4. Functional behavior

### Laplacian

Uses `L = I_nonisolated - D^-1/2 A D^-1/2` in float64 CPU form. Non-finite, negative, asymmetric and self-loop graphs fail closed. Isolated nodes remain in the matrix with zero degree inverse square root and zero normalized-identity diagonal. Input tensors, node count, node order semantics, modality, relation and GraphKey are preserved.

### Spectrum and numerical profile

Uses `numpy.linalg.eigh` on a symmetric float64 CPU matrix. Eigenvalues are one-dimensional, finite, ascending and validated against `[0, 2]` with the configured tolerance. Eigenvectors are transient only and are not stored in `SpectrumArtifact`.

Numerical evidence on the path fixture:

- Laplacian symmetry error: `0.0`
- Eigenvalue residual max: `4.440892098500626e-16`
- Eigenvector orthogonality residual max: `4.440892098500626e-16`
- Eigenvalue range: `[3.137412501463416e-17, 2.0]`

### Spectral statistics

The fixed keys are node/edge count, density, mean degree, connected components, algebraic connectivity, zero and distinct eigenvalue counts, q05/q25/q50/q75/q95, spectral entropy and Dirichlet energy. Quantiles use linear interpolation. Heat-trace statistics are emitted only when `diffusion_times` is explicit. Canonical `run_m2` derives unweighted topology from the upstream graph edge list, so legal zero-weight edges are still counted and connected components are not inferred from the weighted Laplacian. The path fixture produced `num_nodes=4`, `num_edges=3`, `density=0.5`, `mean_degree=1.5`, `connected_components=1`, `algebraic_connectivity=0.5`, `zero_eigenvalue_count=1`, `spectral_entropy=0.8868595071429147`, and `dirichlet_energy=0.042893218813452594`.

### QC fit and transform

The feature set, winsor quantiles and robust-scale epsilon must be explicit in `M2Spec`. Fitting consumes only the supplied training sequence; missing keys are median-imputed, while `None`, NaN, Inf and all-missing features fail closed. Constant features use scale `1.0` and emit `QC_CONSTANT_FEATURE`; the fit-time diagnostic is carried on the immutable four-value state tuple so winsorized constant features are not confused with non-degenerate unit-scale features. Transform never updates the state and outputs all frozen features in stable order. State serialization is canonical SHA-256.

### Lineage, identity and cache

Every M2 artifact has `ArtifactMeta` with protocol version, parent artifact/content hashes, GraphKey, implementation hash and numerics profile hash. The repaired M2 implementation identity is `9da8befdb4dc2140cf979a55152860666b4f8dc2896f90e7a01018bb33823491` (v1.1.3 literal), bumped from the previous implementation. Artifact IDs are recomputed from type, content hash, GraphKey and expected input IDs during validation. `FittedQCState` hash is included in normalized-QC and bundle input content hashes, receipt lineage and `science_key`. Runtime profile changes are excluded from `science_key`; every active M2 numerical tolerance changes `reproduction_key`. v1.0 M2 receipts are rejected by cache eligibility.

## 5. Verification evidence

### Analytic graphs

| Fixture | Eigenvalues | Result |
| --- | --- | --- |
| complete(4) | `[-2.220446049250314e-16, 1.3333333333333333, 1.3333333333333335, 1.3333333333333335]` | PASS |
| path(4) | `[3.137412501463416e-17, 0.49999999999999994, 1.4999999999999998, 2.0]` | PASS |
| cycle(4) | `[2.174405912551658e-16, 1.0, 1.0, 2.0]` | PASS |
| disconnected(4) | `[0.0, 0.0, 2.0, 2.0]` | PASS |
| isolated(4) | `[0.0, 0.0, 0.0, 2.0]` | PASS |

### Permutation and synthetic integration

- Graph permutation preserved `L' = P L P^T`, eigenvalues, statistics and Dirichlet energy within `1e-12`: PASS.
- Three legal synthetic graph modalities ran in stable order: `dmri/structural_connectivity`, `fmri/positive_functional_connectivity`, `smri/morphology_similarity`: PASS.
- Synthetic bundle graph count: `3`; all Laplacians, spectra and statistics were finite.

### QC leakage controls

- Train-only fit: `true`
- Validation/test modifies state: `false`
- Extreme test value changes state: `false`
- State hash stable: `true`
- Different fitted state changes science key: `true`

The synthetic state hash used in the evidence run was `837ccafa334e134be36bb4bd03ca2c2318429d56c89d704e521983c20599081c`.

### Identity evidence

- Same input/spec/context rerun produced the same bundle content hash: `a7a5d5ee9bb462ebcd48d6176ec481c66abc652860e9d5bcb31c72c4d05aef8b`.
- Runtime-only changes kept science identity stable.
- Solver tolerance change kept science identity stable and changed reproduction identity.
- A current PASS receipt with matching artifact/science/reproduction/validator fields was cache eligible; protocol, status, validator and identity mismatches were not.

## 6. Tests and quality gates

- M2 unit: `63 passed`
- M2 integration: `8 passed`
- M2 protocol contract: `10 passed`
- Focused M2 + API/protocol suite: `81 passed, 5 warnings`
- Architecture verifier: `16 PASS / 0 FAIL / 1 SKIP`
- Architecture/contracts: `63 passed`
- Week1 regression: `17/17 PASS`
- Week2-4 regression: `12/12 PASS`
- Full suite: `464 passed, 5 warnings`
- Coverage: `NOT RUN` in the approved environment because `coverage`/`pytest-cov` is not installed; required threshold remains `80%`.
- Ruff: `PASS`
- Ruff format: `PASS` (`117 files already formatted` at final check)
- mypy: `BLOCKED BY BASELINE ENVIRONMENT` — full check reports 6 missing `yaml` stubs and 2 historical redundant casts; the focused check for all 6 changed M2 source files passes with no issues.
- Hard-coded user path scan: `PASS`

The architecture verifier's single SKIP is its pre-existing informational `G13_EXISTING_REGRESSION_ACCEPTABLE` gate; no test failures were observed and no new failure was introduced. The local pre-commit hook could not find system `python`; Ruff and the full pytest suite were run successfully with the project-approved Anaconda environment. This follow-up has not been pushed or merged.

## 7. Boundary flags and remaining issues

- real MRI accessed: `false`
- HCP imaging accessed: `false`
- PPMI imaging accessed: `false`
- MRI tools run: `false`
- GPU used: `false`
- server connected: `false`
- Bita used: `false`
- M3 executed: `false`
- M4 executed: `false`

Known environment follow-ups: install `coverage`/`pytest-cov` and `types-PyYAML`, then address the two pre-existing redundant casts if a clean all-source mypy gate is required. These do not block the M2 functional, protocol, architecture or regression gates demonstrated here. Scientific verification remains `NOT_VERIFIED` because the real MRI/P0/M1 chain and real cohort evidence were intentionally outside this task. The system must not be upgraded to `VERIFIED` on the basis of these synthetic/analytic results.
