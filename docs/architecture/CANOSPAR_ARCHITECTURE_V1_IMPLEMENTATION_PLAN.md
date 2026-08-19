# CanoSPAR Architecture Contract v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Build and verify the CanoSPAR Architecture Contract v1 skeleton while preserving existing Week 1, M0, Week 5-7, and MRIQC v2 behavior.

**Architecture:** Add immutable contracts around existing data objects, expose P0/M0-M9 through Protocol-based APIs, and keep execution/runtime state separate. Unfinished scientific modules expose contract shape and validators only.

**Tech Stack:** Python 3.11, stdlib dataclasses/typing/hashlib/json, existing hashing helpers, PyTorch/PyG wrappers, PyYAML, pytest, Ruff, mypy.

## Global Constraints

- Preserve GraphData, BrainMultiGraphSample, M0 semantics, Week5-7 lifecycle, and MRIQC v2 runtime.
- Do not execute real data, MRI tools, servers, SSH, Bita, GPU jobs, training, or formal M2/M3 experiments.
- Mark M4-M9 CONTRACT_ONLY.
- Keep L0-L3 stable and keep runtime values in L4.
- Use synthetic fixtures only and no real IDs or absolute user paths.
- Use frozen dataclasses and defensive copies.
- Verify with D:\software\MyAnaconda\envs\canospar-mriqc-v2-dev.

---

### Task 1: Documentation and registry

**Files:** architecture docs, ADR 0002, configs/architecture/contracts_v1.yaml.

**Interfaces:** consumes existing project documentation; produces the layer/module/source-of-truth registry used by every later task.

- [ ] Write the documents and registry with exact module states.
- [ ] Parse the registry with the configured Python environment.
- [ ] Run git diff --check.
- [ ] Commit with message: docs: define CanoSPAR architecture contract v1.

### Task 2: Core immutable artifacts

**Files:** src/canospar/contracts/base.py, governance.py, graph.py, imaging.py, errors.py, init; tests/contracts/test_core_artifacts.py and test_graph_compatibility.py.

**Interfaces:** consumes existing GraphData, BrainMultiGraphSample, hashing helpers; produces ArtifactMeta, ScienceContext, GraphKey, BandKey, TokenKey, MultiGraphArtifact, ImagingInputBundle, ROIAlignedSample, build_science_key, and build_reproduction_key.

- [ ] Write failing tests for deterministic keys, defensive copies, runtime exclusion, and old imports.
- [ ] Run the focused tests and confirm they fail because the package is absent.
- [ ] Implement frozen dataclasses and canonical length-delimited SHA-256 identity functions.
- [ ] Run focused tests and Ruff.
- [ ] Commit with message: feat: add CanoSPAR core artifact contracts.

### Task 3: Module APIs and artifact families

**Files:** contracts/spectral.py, bands.py, tokens.py, roles.py, routing.py, prediction.py, evaluation.py; api/p0.py, api/m0.py, api/m1.py through api/m9.py; API tests.

**Interfaces:** consumes Task 2; produces Protocol APIs for prepare_imaging_sample, build_multigraph_sample, run_m2, run_m3, filter_bands, tokenize_bands, infer_roles, route_tokens, predict_sample, and read-only M9 evaluators.

- [ ] Write tests for imports, required protocol names, and no fabricated return values.
- [ ] Run the focused API test and observe the expected missing-import failure.
- [ ] Implement frozen artifact-family metadata and Protocol signatures. Contract-only callables raise module-specific NotImplementedError.
- [ ] Add M0 read-only reference wrappers; do not regenerate manifests.
- [ ] Run tests, Ruff, and mypy.
- [ ] Commit with message: feat: add CanoSPAR module API contracts.

### Task 4: Validation and execution contracts

**Files:** validators/base.py, validators/contracts.py, validators/init; contracts/execution.py; runtime/profile.py, runtime/invalidation.py, runtime/init; execution and invalidation tests.

**Interfaces:** consumes artifact metadata and the registry; produces ValidationIssue, ValidationReport, ModuleRunResult, CompletionReceipt, RuntimeProfile, compute_invalidated_modules, and cache eligibility.

- [ ] Write failing tests for schema/hash mismatch, receipt validity, runtime separation, and M3-only downstream invalidation.
- [ ] Run focused tests and verify expected failures.
- [ ] Implement immutable validation/execution objects with canonical/native status separation.
- [ ] Implement the fixed DAG and fail-closed cache predicate.
- [ ] Run focused tests, Ruff, and mypy.
- [ ] Commit with message: feat: add architecture execution and lineage contracts.

### Task 5: Verifier, CI, and result placement

**Files:** scripts/verify_architecture_contract.py, tests/contracts/test_architecture_registry.py, .github/workflows/ci.yml, placement map, and locally generated verification output.

**Interfaces:** consumes registry, imports, validators, source-of-truth map, and contract tests; produces G01-G15 results with overall_status and PASS/FAIL/SKIP counts.

- [ ] Write failing registry/verifier tests.
- [ ] Implement required-file, YAML, import, version, DAG, source-of-truth, contract-test, and runtime-separation checks.
- [ ] Add one minimal CI contract step without replacing existing checks.
- [ ] Run the verifier and inspect its JSON.
- [ ] Commit with message: test: verify CanoSPAR architecture contract.

### Task 6: Final report and release verification

**Files:** local verification output and the project protocol/architecture documents; stage reports are not repository deliverables.

**Interfaces:** consumes all implementation evidence; produces an evidence-backed PASS/PARTIAL/BLOCKED report.

- [ ] Run contract tests, import-mode regression, Ruff, format check, mypy, diff check, and architecture verifier.
- [ ] Record inherited failures as PREEXISTING or SKIP_ENVIRONMENT.
- [ ] Write the fixed report sections: final status, Git/workspace, preservation, layers, module/artifact/API matrices, source-of-truth, versioning, lineage/cache, invalidation, runtime, tests, files, reality, conflicts, manual verification, recommendation.
- [ ] Review for paths, credentials, real IDs, fake science, and runtime/science coupling.
- [ ] Commit with message: docs: report architecture contract v1 implementation.
