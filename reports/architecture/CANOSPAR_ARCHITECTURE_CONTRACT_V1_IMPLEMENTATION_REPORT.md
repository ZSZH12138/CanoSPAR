# CanoSPAR Architecture Contract v1 Implementation Report

## 1. 最终结论

**ARCHITECTURE_V1_FINALIZED**

Architecture Contract v1 的核心契约门禁 G01-G12 已通过，新增 NumericsProfile 语义门禁 G16 也已通过；公共骨架、Artifact metadata、Module API、lineage/cache/invalidation、Runtime separation 和机器 verifier 已建立。

之所以不是全仓 PASS，是因为当前基线仍有与本次架构变更无关的环境和既有回归问题：

- 全仓回归：2063 passed, 4 failed, 17 skipped, 8 warnings；相对上一轮只增加本轮 9 个契约测试，失败数和失败类型未增加；
- 2 个失败来自当前环境缺少 Snakemake；
- 2 个失败来自未修改的 MRIQC v2 controller 集成生命周期测试；
- mypy 保留 2 个既有 pilot_atlas.py 错误；
- Week1/Week2-4 acceptance verifier 未能在当前环境完整闭环。

因此，本次结果可以作为 M2/M3 的正式接口基础，但不能解释为 M2/M3 算法已经实现，也不能解释为全仓科学运行环境已经合格。

## 2. Git / Workspace

| 项目 | 结果 |
| --- | --- |
| worktree | .worktrees/architecture-contract-v1 |
| branch | codex/architecture-contract-v1 |
| base commit | 73b0ec9 |
| architecture docs commit | efabdc5 |
| core artifact commit | 8db9323 |
| module API commit | eacdd6c |
| execution/lineage commit | 2af5f09 |
| verifier/CI commit | db39505 |
| main 是否修改 | 否 |
| 是否 push | 否 |
| 是否使用多智能体 | 否 |
| 修改前 dirty 状态 | architecture worktree clean；Week5-7 原工作树存在用户未提交修改，未触碰 |
| 运行环境 | canospar-mriqc-v2-dev from D:\software\MyAnaconda |

## 3. Existing System Preservation

### Week 1

现有 CPU-only 环境、smoke workflow、配置、provenance、hardware gate 和 GraphData/BrainMultiGraphSample 保留。架构层仅增加 wrapper、validator 和 API boundary。

### Week 2-4

现有 HCP unrelated cohort、PPMI subject/visit boundary、任务门禁、manifest、split 和 test-set seal 未重写。M0 通过只读 artifact reference 表达，不重新生成 manifest。

### Week 5-7

现有 archive inventory、safe extraction、DICOM-to-BIDS、BIDS validator、atlas/QC、路径和私有数据边界未移动或删除。它们在成果归位索引中被标记为 P0 与 L3 execution evidence。

### MRIQC v2

scheduler、ledger、monitor、handoff、native runtime 和 server lifecycle 未被重写；它们被明确放入 L3/L4。没有启动服务器、Bita、SSH 或真实 MRIQC。

### 兼容性

GraphData 和 BrainMultiGraphSample 的原始 import 仍由 canospar.data.contracts 提供。canospar.contracts.graph 只做兼容性 re-export 和 MultiGraphArtifact wrapper。

## 4. Architecture Layers

| Layer | Responsibility | 本次状态 |
| --- | --- | --- |
| L0 Scientific Contract | cohort/task/split/QC/leakage/scientific semantics | 复用现有 contract |
| L1 Artifact Contract | immutable metadata、keys、artifact families | 已建立 |
| L2 Module API Contract | P0、M0-M9 Protocol/function boundaries | 已建立 |
| L3 Execution Contract | validator、receipt、lineage、cache、invalidation | 已建立 |
| L4 Runtime Profile | runtime/server/scheduler/container/transport | 已隔离，复用已有 runtime |

## 5. Module Matrix

| Module | Responsibility | Input | Output | Important APIs | Version | State |
| --- | --- | --- | --- | --- | --- | --- |
| M0 | cohort/task/split metadata | existing references | manifest/split/task artifacts | load_dataset_manifest | 1.0.0 | EXISTING + adapter |
| P0 | imaging/QC/ROI alignment | ImagingInputBundle | ROIAlignedSample | prepare_imaging_sample | 1.0.0 | PARTIAL |
| M1 | graph topology | ROIAlignedSample/spec/context | MultiGraphArtifact | build_multigraph_sample | 1.0.0 | PARTIAL/contract boundary |
| M2 | Laplacian/spectrum/QC | MultiGraphArtifact/M2Spec/context | SpectralBundle | run_m2 | 1.0.0 | CONTRACT_ONLY |
| M3 | canonical spectral coordinate | SpectralBundle/coordinate/bands/context | CanonicalSpectrumBundle | run_m3 | 1.0.0 | CONTRACT_ONLY |
| M4 | spectral filtering | graph/spectral/canonical/filter/context | BandSignalBundle | filter_bands | 1.0.0 | CONTRACT_ONLY |
| M5 | band tokenization | BandSignalBundle/spec/context | TokenBundle | tokenize_bands | 1.0.0 | CONTRACT_ONLY |
| M6 | roles/reliability | TokenBundle/QC/availability/spec/context | RoleBundle | infer_roles | 1.0.0 | CONTRACT_ONLY |
| M7 | sparse routing | TokenBundle/RoleBundle/spec/context | RoutingBundle | route_tokens | 1.0.0 | CONTRACT_ONLY |
| M8 | readout/prediction/objective | token/role/route/QC/spec/context | embedding/prediction/loss | predict_sample | 1.0.0 | CONTRACT_ONLY |
| M9 | evaluation/interpretation | prediction/route/role/spectral artifacts | EvaluationBundle | evaluate_predictions | 1.0.0 | CONTRACT_ONLY |

## 6. Artifact Matrix

| Artifact | Owner | Identity/provenance |
| --- | --- | --- |
| DatasetManifestArtifact | M0 | manifest reference/content hash |
| SplitRegistryArtifact | M0 | split reference/content hash |
| TaskDefinitionArtifact | M0 | task reference/content hash |
| ImagingInputBundle | P0 | subject/visit/dataset/source hashes |
| ROIAlignedSample | P0 | atlas/ROI/node-order/QC/source IDs |
| MultiGraphArtifact | M1 | ArtifactMeta + existing BrainMultiGraphSample + atlas identity |
| SpectralBundle | M2 | Laplacian/spectrum/statistics/QC artifacts |
| CanonicalSpectrumBundle | M3 | spectrum artifact ID, mass coordinate, bands |
| BandSignalBundle | M4 | graph/band parent identity |
| TokenBundle | M5 | token IDs, metadata, assignment |
| RoleBundle | M6 | token IDs, shared/private/noisy/reliability |
| RoutingBundle | M7 | candidate/score/route/routed-token artifacts |
| PredictionBundle | M8 | prediction and embedding identity |
| EvaluationBundle | M9 | read-only evaluation reports |

## 7. Public API Matrix

Public API modules are in src/canospar/api. Contract-only functions fail closed with NotImplementedError and never return fabricated artifacts.

- P0: prepare_imaging_sample
- M0: load_dataset_manifest
- M1: build_multigraph_sample, validate_graph
- M2: build_normalized_laplacian, compute_spectrum, compute_spectral_statistics, run_m2
- M3: canonical_mass_coordinate, build_canonical_bands, validate_canonical_bands, run_m3
- M4: filter_exact, filter_chebyshev, filter_bands
- M5: tokenize_bands, validate_token_bundle
- M6: infer_roles, validate_role_bundle
- M7: build_route_candidates, score_routes, route_tokens
- M8: readout_sample, predict_sample, compute_objective
- M9: evaluate_predictions, evaluate_spectral_mechanism, evaluate_robustness, evaluate_route_stability, run_statistical_tests

## 8. Source-of-Truth Rules

- M0 is the cohort/task/split source of truth.
- P0 is the ROI alignment/QC source of truth.
- M1 is the graph topology source of truth.
- M2 is the Laplacian/spectrum source of truth.
- M3 is the canonical coordinate/band source of truth.
- M4 is the band signal source of truth.
- M5 is the token source of truth.
- M6 is the role source of truth.
- M7 is the route source of truth.
- M8 is the prediction/objective source of truth.
- M9 is the evaluation source of truth.

The contract tests enforce legacy graph imports, parent identity preservation, and M3's spectral-bundle boundary. No M4-M9 algorithm recomputes upstream scientific objects in this change.

## 9. Versioning

The following namespaces are separate:

- architecture_contract_version: 1.0.0
- science_contract_version: 1.1.0
- module_contract_version: 1.0.0
- schema_version: 1.0.0
- runtime_profile_version: 1.0.0
- numerics_profile_schema_version: 1.0.0

No existing scientific protocol was changed. This is additive, so there is no breaking change.

## 10. Lineage / Cache

ArtifactMeta is frozen and records schema, artifact, producer module, module version, science version, input IDs/hashes, science configuration, dataset manifest, split, seed, content hash, implementation hash, numerics profile hash, and UTC creation time. NumericsProfile is a separate frozen value object whose canonical hash binds numerical library identity, dtype/precision, deterministic settings, eigensolver/backend choice, and solver tolerance. RuntimeProfile remains execution provenance and is excluded from both scientific and numerical identity.

ScienceContext is the single scientific identity input. science_key is deterministic and excludes runtime profile. reproduction_key changes with implementation or the canonical NumericsProfile hash. Runtime-only changes such as worker count, GPU count, server, Bita, SSH, WebTerminal, or scheduler concurrency do not change reproduction identity when numerical identity is unchanged.

Cache reuse requires matching science key, reproduction key, artifact hash, PASS/READY receipt, and PASS validator status.

## 11. Invalidation

The DAG is:

~~~text
M0 -> P0 -> M1 -> M2 -> M3 -> M4 -> M5 -> M6 -> M7 -> M8 -> M9
~~~

A change at M3 invalidates M3-M9 only. M0, P0, M1, and M2 remain valid. Runtime profile changes do not invalidate scientific artifacts when science and reproduction identities are unchanged.

## 12. Runtime Separation

RuntimeProfile contains CPU, RAM, GPU, CUDA, workers, threads, container, scheduler, transport, and server class. These are not scientific module inputs. NumericsProfile separately records the numerical semantics that affect reproduction identity.

The following existing work is placed under L3/L4:

- Week5-7 lifecycle, package, monitor, Bita handoff, and server evidence;
- MRIQC v2 scheduler, ledger, monitor, checkpoint/recovery, and native Linux support;
- SSH, WebTerminal, server type, and runtime feasibility results.

No runtime-only value enters science_key or reproduction_key. Numerical backend identity enters only through NumericsProfile.

## 13. Contract Tests

The dedicated contract suite passed:

~~~text
53 passed, 3 warnings
~~~

It covers:

- old GraphData and BrainMultiGraphSample imports;
- immutable ArtifactMeta and ScienceContext;
- deterministic science_key/reproduction_key;
- runtime identity exclusion;
- immutable NumericsProfile and numerical identity changes for dtype, eigensolver backend, and solver tolerance;
- artifact key hierarchy;
- imaging and graph wrappers;
- M0 read-only references;
- P0/M0-M9 public API symbols;
- contract-only fail-closed behavior;
- receipt/cache validation;
- schema/hash validation;
- invalidation DAG;
- registry and verifier gates.

## 14. Regression Tests

The full importlib-mode regression result was:

~~~text
2063 passed, 4 failed, 17 skipped, 8 warnings
~~~

The 4 failures are not caused by this architecture closure:

1. Two Week2-4 Snakemake integration tests fail because Snakemake is not installed in the selected environment.
2. Two MRIQC v2 controller tests fail in unchanged server lifecycle code with heartbeat/owned-lane startup behavior on this Windows host.

Fresh Week1/Week2-4 verifier attempts are recorded as `PREEXISTING_ENVIRONMENT_BLOCK`: the selected environment lacks entmax/Snakemake, and the inherited default collection/path/mypy checks remain outside this architecture closure.

Ruff check and Ruff format check both passed. The mypy result remains:

~~~text
2 existing errors in src/canospar/data/pilot_atlas.py
~~~

The default pytest baseline also has the existing duplicate test module name collection mismatch. The importlib-mode run was used for the full regression to avoid that collection artifact.

## 15. Files Created / Modified

Created:

- AGENTS.md
- docs/architecture/*, including the implementation plan and result-placement map;
- docs/decisions/0002-canospar-architecture-contract-v1.md;
- configs/architecture/contracts_v1.yaml;
- src/canospar/contracts/*;
- src/canospar/api/*;
- src/canospar/validators/*;
- src/canospar/runtime/*;
- src/canospar/runtime/numerics.py;
- tests/contracts/*;
- scripts/verify_architecture_contract.py;
- reports/architecture/verification_results.json;
- reports/architecture/ARCHITECTURE_V1_BASELINE.json;
- this report.

Modified:

- .github/workflows/ci.yml, with one architecture verifier step.

No existing scientific module implementation, real data, private artifact, server script, or MRIQC scientific result was moved or deleted.

## 16. Current Implementation Reality

### 已经真正实现

- Architecture Contract v1 documentation and machine registry;
- immutable ArtifactMeta, ScienceContext, GraphKey, BandKey, TokenKey;
- science_key and reproduction_key;
- MultiGraphArtifact compatibility wrapper;
- P0 imaging input/output contract objects;
- M0 read-only reference artifact types;
- typed P0/M0-M9 API boundaries;
- validation reports and contract errors;
- CompletionReceipt and ModuleRunResult;
- RuntimeProfile and NumericsProfile with explicit runtime/numerics separation;
- fail-closed cache eligibility;
- invalidation DAG;
- contract tests;
- architecture verifier and CI hook;
- existing-result placement map.

### 只有 Contract

- M2 Laplacian/spectrum computation;
- M3 canonical spectral-mass computation;
- M4 filtering;
- M5 tokenization;
- M6 shared/private/noisy role model;
- M7 sparse routing;
- M8 full readout/training objective;
- M9 scientific evaluation and interpretation.

No algorithm, model, scientific result, or real HCP/PPMI output was fabricated.

## 17. Breaking Changes

**NONE.**

The change is additive. Existing GraphData, BrainMultiGraphSample, M0 modules, Week5-7 runtime code, and MRIQC v2 runtime code retain their existing locations and imports.

## 18. Existing Conflicts

No unresolved scientific contract conflict was introduced.

Known inherited/environment conflicts:

- Snakemake is absent in the selected environment, so Snakemake-dependent acceptance tests cannot pass there.
- The selected environment lacks entmax, which blocks the Week1 dependency import check.
- Existing repository documents contain three placeholder path tokens rejected by the inherited hard-coded-path verifier.
- Existing default pytest collection has duplicate test module names; importlib mode avoids this.
- Existing MRIQC v2 controller lifecycle tests are not stable on this Windows host.

These are recorded rather than silently changed.

## 19. Manual Verification

The following commands were used or are the recommended handoff checks:

~~~powershell
git status --short
git branch --show-current
git rev-parse HEAD
git log --oneline -15
git diff --check
python scripts/verify_architecture_contract.py
python -m pytest -q tests/contracts
python -m pytest -q --import-mode=importlib
ruff check src tests scripts
ruff format --check src tests scripts
python -m mypy src/canospar
python scripts/verify_week1.py
python scripts/verify_week2_4.py
Get-Content docs/architecture/CANOSPAR_ARCHITECTURE_CONTRACT_V1.md
Get-Content configs/architecture/contracts_v1.yaml
~~~

The Python commands must use the configured Anaconda environment and the repository source path.

## 20. Recommendation

Architecture Contract v1 is now the frozen interface baseline for a subsequent M2/M3 implementation branch. This closure does not implement M2/M3 and does not run scientific data or experiments.

进入条件已经满足：

- M2/M3 的输入、输出和 source-of-truth 已冻结；
- M3 被强制绑定到 M2 的 SpectrumArtifact；
- cache、lineage、version 和 invalidation 语义已定义；
- contract suite 和 G01-G16 verifier 门禁通过。

进入 M2/M3 后仍必须继续使用 TDD、toy/synthetic tests、exact-before-approximate 验证，并保持真实 HCP/PPMI 全量运行、服务器、GPU 和正式科学实验关闭，直到另行授权。

## 21. Architecture v1 Release Closure

| Item | Final evidence | Status |
| --- | --- | --- |
| final branch | `codex/architecture-contract-v1` | recorded in final handoff |
| final HEAD | `fa947b625ff961c0a71b7dee6d93e1035bdddf28` architecture baseline commit; receipt-only closeout descendants are reported in the final handoff | FROZEN |
| baseline SHA | `fa947b625ff961c0a71b7dee6d93e1035bdddf28` | FROZEN |
| architecture verifier | G01-G15 PASS/SKIP as defined; G16 NumericsProfile semantics PASS | PASS |
| contract tests | final fresh `tests/contracts`: `53 passed, 3 warnings` | PASS |
| full regression delta | previous `2054 passed, 4 failed, 17 skipped` → final `2063 passed, 4 failed, 17 skipped, 8 warnings`; +9 passes from NumericsProfile tests, no new failures | INHERITED_BASELINE |
| NumericsProfile | immutable; runtime-only identity excluded; numerical semantic changes alter reproduction identity | FROZEN |
| worktree clean | verified after final commit | recorded in final handoff |
| main modified | no | NO |
| push performed | no | NO |
| architecture baseline | `FROZEN` | FINALIZED |
| M2+M3 implementation authorized | YES, from this SHA or an explicit descendant; implementation is not started in this task | YES |

`ARCHITECTURE_CONTRACT_V1_BASELINE_SHA=fa947b625ff961c0a71b7dee6d93e1035bdddf28`

Subsequent M2/M3 branches must start from this SHA or an explicit descendant and must not silently modify Architecture Contract v1.
