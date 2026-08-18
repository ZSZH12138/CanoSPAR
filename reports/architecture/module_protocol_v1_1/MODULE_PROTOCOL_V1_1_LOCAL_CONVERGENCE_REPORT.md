# CanoSPAR Module Protocol v1.1.0 本地收敛报告

## 1. 结论

**最终状态：PASS**。

本报告记录 CanoSPAR 模块协议 v1.1.0 的本地迁移、接口收敛、缓存兼容边界、验证器同步、回归测试和文档记录。这里的 PASS 表示该协议迁移阶段验收通过；随后 M2 已通过独立实现任务完成 Laplacian、精确谱、谱统计和 QC 路径，M3-M9 仍未实现，也不表示产生了 MRI 科学结果。

- 工作树：当前隔离工作树（portable report，不写入用户绝对路径）
- 分支：`codex/module-protocol-v1.1-local-repair`
- 新协议 SHA-256：`51475FAC300E46CAC42FE185FED28D223F3ED778B1FD8E0BEDEB92F94FBDF6FB`
- 协议状态：`FROZEN FOR IMPLEMENTATION`
- 本地提交：在最终验收通过后创建；不 push，不修改 main/master。

## 2. 协议文件迁移

用户提供的 `D:\CANOSPAR_MODULE_PROTOCOL_SPEC_V1_1_REPAIRED.md` 已剪切到当前 canonical source-of-truth：

`docs/architecture/CANOSPAR_MODULE_PROTOCOL_SPEC_V1.md`

原 v1.0.0 文件已保留为历史归档：

`docs/architecture/archive/CANOSPAR_MODULE_PROTOCOL_SPEC_V1_0_0.md`

源盘上的临时协议文件不再保留。新协议只改变 `module_protocol_spec_version` 到 `1.1.0`；architecture/science/schema/runtime/numerics 版本继续保持 `1.0.0/1.1.0/1.0.0/1.0.0/1.0.0`。

## 3. 按功能层说明的执行流程

1. **版本与注册表层**：把 v1.1.0 写入治理常量、架构 YAML registry 和每个模块的协议版本字段；保留原 DAG `M0 -> P0 -> M1 -> M2 -> M3 -> M4 -> M5 -> M6 -> M7 -> M8 -> M9`。
2. **输入适配层 M0/P0**：补齐 split registry、task definition 的只读 loader，以及 imaging input bundle builder 的公共签名；因为仓库没有新增序列化定义，这些入口继续 fail-closed，不伪造 artifact。
3. **图与谱层 M1/M2**：把图、tensor、QC vector、fitted QC state 和 lineage 元数据闭合为既有类型；M2 的 `run_m2` 只接受显式冻结的 `qc_state`，未提供时返回语义仍是 `normalized_qc=None`，不隐式拟合。
4. **canonical 频谱层 M3**：采用 tie-aware mass coordinate 的接口约束，band 默认策略固定为 `keep_ties_intact`，band 校验返回 `ValidationReport`；M3 仍是 contract-only。
5. **滤波层 M4**：保留 exact/Chebyshev/canonical-band 三个入口的完整输入边界；不实现滤波、重算谱或发布第二份 canonical spectrum，继续 fail-closed。
6. **下游骨架层 M5-M9**：把 token、role、route、prediction、evaluation 的宽泛 `object`/`Any` 字段收敛到既有 key、tensor、tuple 和 JSON mapping；这些模块继续 `CONTRACT_ONLY`。
7. **身份与缓存层**：M2-M9 的 v1.0.0 receipt/cache 在 v1.1.0 下不可命中；M0/P0/M1 不因本协议升级自动失效；RuntimeProfile 不改变 `science_key`，NumericsProfile 仍改变 `reproduction_key`。
8. **验证层**：先跑协议 targeted tests，再跑 contract、架构 verifier、Week 1、Week 2-4 fixture 回归、静态检查、覆盖率、Snakemake dry-run 和 package build，最后生成本报告和 JSON 证据。

## 4. 核心变更审计矩阵

| 区域 | 本次完成内容 | 实现状态 |
|---|---|---|
| Version namespace | 新增 `MODULE_PROTOCOL_SPEC_VERSION=1.1.0`，其他版本不变 | 完成 |
| M0 | `load_split_registry`、`load_task_definition`、`build_imaging_input_bundle` | 只读 / fail-closed |
| M2 QC | `QCFeatureState` 四元组、`FittedQCState` mapping、显式 `qc_state` | 契约闭合 |
| M2 lineage | helper 接收 `ScienceContext`、`parent_meta` 或 source artifact id/hash | 契约闭合 |
| M3 coordinate | context-aware canonical coordinate、mass-space band、tie policy | 契约闭合 |
| M4 | exact/Chebyshev/band filter 输入闭合 | CONTRACT_ONLY |
| M5-M9 | artifact 字段去除无界 `object`/`Any` | CONTRACT_ONLY |
| Registry | 全 DAG 模块协议版本同步为 1.1.0；M2 为 IMPLEMENTED，M3-M9 保持 CONTRACT_ONLY | 完成 |
| Cache | 仅 M2-M9 强制当前协议版本；M0/P0/M1 保留兼容 | 完成 |
| Invalidation | 保留固定 DAG；协议升级不伪装成 M0/P0/M1 失效 | 完成 |
| Docs | canonical 协议、历史归档、ADR、执行/缓存规则 | 完成 |

## 5. 验收证据

- 协议 targeted test：`10 passed`；与 execution compatibility 合计 `14 passed`。
- contract tests：`62 passed`。
- 全量 tests：`392 passed, 2 warnings`。
- 架构 verifier：`16 PASS, 0 FAIL, 1 SKIP`；SKIP 是原 verifier 对“完整回归另行记录”的保留性 gate，不是失败。
- Week 1 acceptance：`17/17 PASS`。
- Week 2-4 acceptance：`12/12 PASS`，coverage `85.0%`。
- Ruff check：PASS。
- Ruff format check：PASS。
- mypy：`Success: no issues found in 61 source files`。
- Snakemake dry-run：PASS。
- package build：PASS。

## 6. 数据、硬件和实现边界

本次没有读取真实 MRI、DICOM、BIDS、HCP/PPMI 私有数据，没有启动服务器，没有使用 GPU，没有联网，没有调用远程 agent，也没有生成科学结果。Week 1/Week 2-4 验收只使用 CPU 和仓库内 synthetic/fixture 数据；Week 2-4 机器证据明确记录 `fixture_only=true`、`network_access=false`、`private_metadata_read=false`、`gpu_used=false`、`server_required=false`。

M3-M9 当前仍是协议骨架。M2 的后续实现仅覆盖 synthetic/analytic 与 CPU 数值证据，科学验证仍为 `NOT_VERIFIED`；下一阶段只有在用户明确授权并提供相应数据/任务定义后，才能按冻结协议继续实现 M3-M9 算法，并分别补充真实数据、数值验证、泄漏检查和科学结果证据。
