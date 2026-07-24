# CanoSPAR 第一周实施报告

报告日期：2026-07-24
报告范围：第一周基础设施，不含模型实现或科学结果

## 1. 最终状态

**PASS**

用户仅豁免了 6 GiB 可用内存检查；原始硬件结论继续保留为
`gate_passed: false`，授权后的有效结论为 `effective_gate_passed: true`。除这项
有记录、有限定范围的偏差外，环境、依赖、中央处理器约束、静态质量、测试、覆盖率、
smoke、provenance、Git 忽略、路径扫描、Snakemake、统一验收和构建均以退出码 0
完成。机器可读矩阵记录 17 项 `PASS`、0 项 `FAIL`、0 项
`SKIP_WITH_REASON`，因此第一周基础设施最终状态为 `PASS`。

本报告的最终验收快照是在首次发布前、实验契约 `1.0.0` 下生成的；快照生成时
版本控制状态为 `UNCOMMITTED_WORKTREE`：

- 当时分支为 `master`；
- 仓库尚无首个提交，因而没有可报告的提交哈希；
- 未配置远程仓库；
- 第一周文件均保留在未提交工作树中，符合“不自动提交”的约束。

以上内容是可复现的发布前历史证据，不用于描述此后仓库的实时状态。首次提交和推送
完成后，应以 Git 历史及 GitHub Actions 的远程运行结果作为发布状态的事实来源。

## 2. 算力结论

原始硬件门禁必须原样保留为 `gate_passed: false`。四次可用内存测量为
1.95、1.11、0.96 和 0.88 GiB，最后一次 0.88 GiB 低于强制的 6 GiB
门槛。用户仅豁免了 `available_ram_gib` 这一项，因此独立记录
`effective_gate_passed: true`；该豁免没有改写原始测量，也没有把原始门禁伪装成通过。

| 项目 | 实测或结论 |
| --- | --- |
| 处理器 | 6 个物理核心、12 个逻辑核心 |
| 总内存 | 15.75 GiB |
| 最后一次可用内存 | 0.88 GiB |
| 可用磁盘空间 | 183.74 GiB |
| 图形处理器 | 检测到物理设备，但第一周完全不使用 |
| CUDA | 不可用，`cuda_available: false` |
| Docker | 可用，但第一周不构建容器 |
| Apptainer | 不可用，且第一周不要求 |
| 外部算力 | 不租用服务器，不启动云端或付费算力 |

项目环境为 Python 3.11.15、PyTorch 2.12.1+cpu 和 PyTorch Geometric
2.8.0.post1。`environment.lock.yml` 来自实际的 `canospar-week1` 环境，
是明确的 win-64 平台锁；它不宣称可跨平台复用，也不包含本机 Conda 前缀。
Anaconda 安装位置在所有说明中统一写作 `<ANACONDA_ROOT>`。

## 3. 大概实现了什么功能

第一周实现的是一条可复现、仅使用中央处理器、无真实数据的基础设施闭环：

1. 组合并验证 Hydra 配置，强制 `device=cpu`。
2. 以稳定的 SHA-256 规则哈希字节、文件、JSON、YAML 配置和文件序列。
3. 将输出限制在 `artifacts/`，拒绝父目录穿越、个人绝对路径和受限数据目录。
4. 以冻结字段和防御性复制约束单图与多模态多图样本，验证过程不隐式修改输入，
   并可转换为真实的 PyG `Data`。
5. 用固定随机种子生成三张很小的随机图，并通过真实 PyG `DataLoader` 完成批处理。
6. 保存完整解析配置、隐私安全的 provenance 和 smoke 报告，并用同一配置哈希关联三者。
7. 提供单元测试、子进程集成测试、预提交检查、最小权限持续集成、Snakemake
   dry-run 和统一验收脚本。

这些功能只验证工程基础设施。尚未实现 CanoSPAR 模型、M1 及后续模块、MRI
工具、数据下载、真实预处理、训练、调参或科学评估。

## 4. 具体实施了什么

| 模块 | 具体实施 | 当前边界 |
| --- | --- | --- |
| 仓库结构 | 建立 `src` 包布局、配置、测试、脚本、工作流、报告、产物和容器占位目录；用 `.gitkeep` 保留空目录边界。 | 最终验收快照生成时尚无首个提交；该状态作为发布前历史证据保留。 |
| 环境与依赖 | 要求 Python `>=3.11,<3.12`；`environment.yml` 安装中央处理器版 PyTorch 及开发、研究和工作流依赖；`environment.lock.yml` 保存实际 win-64 解析版本。 | 不修改 `base`，不安装 CUDA wheel；win-64 锁不冒充跨平台锁。 |
| 数据对象契约 | `GraphData` 与 `BrainMultiGraphSample` 使用冻结字段；构造时防御性复制张量和嵌套映射；验证张量、边、模态、可用性、质控、目标和协变量，且验证不隐式修改输入。 | 这里只定义输入边界和 PyG 转换，不实现模型语义或训练逻辑。 |
| 配置系统 | `compose_config` 使用真实 Hydra 组合五个配置组；验证中央处理器、契约版本、随机种子、图规模和规范相对输出路径；`save_resolved_config` 保存解析 YAML 与配置哈希。 | `device=cuda`、绝对输出路径、父目录穿越和非 `artifacts/` 输出均被拒绝。 |
| 哈希和 provenance | 使用规范 JSON/YAML 与 SHA-256 实现内容哈希；provenance 记录 UTC、契约、Git、配置、清单、容器、随机种子、版本、设备和脱敏命令；硬件门禁保留原始与豁免后结论。 | 缺失提交、清单或容器时写 `null`、状态和原因；不伪造值，不写个人或机器敏感信息。 |
| smoke test | 固定种子生成 sMRI、dMRI、fMRI 三张小图，使用真实 PyG `DataLoader` 批处理，输出解析配置、provenance 和 smoke 报告。 | 默认 3 张图、12 个节点、18 条边、3 维特征；不联网、不下载、不训练。 |
| 测试 | 单元测试覆盖配置、契约、硬件、哈希、路径、provenance、smoke 和验收器；集成测试以真实子进程检查成功、确定性复跑与 CUDA 拒绝。 | 147 个单元测试和 3 个集成测试通过；全量 150 个测试通过，覆盖率 89.59%。 |
| 代码质量 | Ruff 执行规则检查和格式检查，mypy 对 `src/canospar` 使用严格模式，pytest 分支覆盖率门槛为 80%，另有硬编码路径扫描器。 | 本报告不以局部历史输出替代最终全量验收。 |
| pre-commit | 固定正式版本的通用检查与 Ruff 钩子，并复用项目环境执行 mypy、单元测试和路径扫描。 | 启用大文件、私钥、冲突、JSON、TOML、YAML、尾随空白等检查。 |
| GitHub Actions | Ubuntu 与 Python 3.11 作业先安装官方中央处理器版 PyTorch，再安装项目依赖，依次执行质量、测试、smoke、预提交、Snakemake、总验收和构建。 | 权限仅为 `contents: read`；发布前快照没有远程运行证据，首次推送后的状态应在 GitHub Actions 中核对。 |
| Snakemake | `rule all` 只聚合三个 smoke 文件，`rule smoke_test` 只调用中央处理器 smoke 命令。 | dry-run 不包含下载、MRI、模型或训练规则。 |
| 容器占位 | `containers/model.def` 和 `containers/versions.md` 记录 Python 与中央处理器 PyTorch 声明，并明确其仅为占位。 | 未构建、拉取、发布或运行容器；没有可报告的容器摘要。 |
| 文档和安全规则 | README 说明安装与边界；实验契约规定测试集封存、分组、训练集拟合、无标签构图、provenance 和受限数据规则；Git 忽略数据、影像、模型权重与产物；许可证声明保持待定。 | 未实现 MRI、M1 及后续模块、模型、训练或科学评估；正式许可证由用户决定。 |

## 5. 创建和修改的文件

仓库没有基线提交，Git 无法可靠区分传统意义上的“新建”与“修改”。因此，第一周核心
文件统一如实标为“新建/增量建立（无基线提交）”；用户原有的两份研究 Markdown 只标为
“保留（原有）”。这不构成对修改历史的推断。

| 文件路径 | 文件用途 | 新建或修改 |
| --- | --- | --- |
| `.gitignore` | 忽略受限数据、医学影像、模型权重、运行产物、环境和缓存。 | 新建/增量建立（无基线提交） |
| `.pre-commit-config.yaml` | 固定预提交质量、安全、测试和路径扫描钩子。 | 新建/增量建立（无基线提交） |
| `.github/workflows/ci.yml` | 定义最小权限的中央处理器持续集成流程。 | 新建/增量建立（无基线提交） |
| `LICENSE` | 声明正式许可证尚未选择及当前再分发限制。 | 新建/增量建立（无基线提交） |
| `README.md` | 说明阶段、安装、验证、配置、安全、provenance 和许可证。 | 新建/增量建立（无基线提交） |
| `pyproject.toml` | 定义包元数据、Python 边界、依赖和 pytest、覆盖率、Ruff、mypy 配置。 | 新建/增量建立（无基线提交） |
| `environment.yml` | 定义 Python 3.11 隔离环境和中央处理器依赖安装。 | 新建/增量建立（无基线提交） |
| `environment.lock.yml` | 保存实际 win-64 环境的解析版本，不含本地前缀。 | 新建/增量建立（无基线提交） |
| `configs/config.yaml` | 定义 Hydra 默认组合、中央处理器、契约、种子和日志。 | 新建/增量建立（无基线提交） |
| `configs/data/toy.yaml` | 定义生成式玩具数据配置。 | 新建/增量建立（无基线提交） |
| `configs/graph/toy.yaml` | 定义 smoke 图节点数和特征维数。 | 新建/增量建立（无基线提交） |
| `configs/model/smoke.yaml` | 定义仅用于 smoke 的模型占位配置组。 | 新建/增量建立（无基线提交） |
| `configs/experiment/smoke.yaml` | 定义确定性 smoke 实验配置。 | 新建/增量建立（无基线提交） |
| `configs/paths/local.example.yaml` | 定义可移植的相对产物目录示例。 | 新建/增量建立（无基线提交） |
| `containers/model.def` | 保存未构建的容器定义占位。 | 新建/增量建立（无基线提交） |
| `containers/versions.md` | 记录容器占位版本与未构建边界。 | 新建/增量建立（无基线提交） |
| `workflow/Snakefile` | 定义仅聚合 smoke 三文件的 `all` 规则。 | 新建/增量建立（无基线提交） |
| `workflow/rules/smoke.smk` | 定义唯一可执行的 `smoke_test` 规则。 | 新建/增量建立（无基线提交） |
| `src/canospar/__init__.py` | 建立顶层 Python 包。 | 新建/增量建立（无基线提交） |
| `src/canospar/data/__init__.py` | 建立数据子包边界。 | 新建/增量建立（无基线提交） |
| `src/canospar/data/contracts.py` | 实现冻结字段、防御性复制、输入验证和 PyG 转换。 | 新建/增量建立（无基线提交） |
| `src/canospar/graph/__init__.py` | 保留后续图模块包边界，不含实现。 | 新建/增量建立（无基线提交） |
| `src/canospar/spectral/__init__.py` | 保留后续谱模块包边界，不含实现。 | 新建/增量建立（无基线提交） |
| `src/canospar/models/__init__.py` | 保留后续模型包边界，不含模型实现。 | 新建/增量建立（无基线提交） |
| `src/canospar/training/__init__.py` | 保留后续训练包边界，不含训练实现。 | 新建/增量建立（无基线提交） |
| `src/canospar/evaluation/__init__.py` | 保留后续评估包边界，不含科学评估。 | 新建/增量建立（无基线提交） |
| `src/canospar/utils/__init__.py` | 建立工具子包边界。 | 新建/增量建立（无基线提交） |
| `src/canospar/utils/config.py` | 实现 Hydra 组合、验证和解析配置保存。 | 新建/增量建立（无基线提交） |
| `src/canospar/utils/hardware_gate.py` | 实现隐私安全的硬件采集及原始/有效门禁评估。 | 新建/增量建立（无基线提交） |
| `src/canospar/utils/hashing.py` | 实现确定性 SHA-256 哈希工具。 | 新建/增量建立（无基线提交） |
| `src/canospar/utils/paths.py` | 实现项目根定位和安全输出目录约束。 | 新建/增量建立（无基线提交） |
| `src/canospar/utils/provenance.py` | 实现隐私安全的运行来源记录与写入。 | 新建/增量建立（无基线提交） |
| `src/canospar/utils/smoke_test.py` | 实现三图生成、真实 PyG 批处理、报告和命令入口。 | 新建/增量建立（无基线提交） |
| `scripts/bootstrap.ps1` | 在 Windows PowerShell 中创建隔离环境并验证中央处理器 PyTorch。 | 新建/增量建立（无基线提交） |
| `scripts/bootstrap.sh` | 在 Linux 或 macOS shell 中创建隔离环境并验证中央处理器 PyTorch。 | 新建/增量建立（无基线提交） |
| `scripts/check_no_hardcoded_paths.py` | 扫描用户特定绝对路径并以非零码报告违规。 | 新建/增量建立（无基线提交） |
| `scripts/verify_week1.py` | 顺序执行 17 项验收（含全量测试覆盖率硬门槛）并生成机器可读矩阵。 | 新建/增量建立（无基线提交） |
| `tests/unit/test_config.py` | 测试配置组合、覆盖、验证、路径和保存。 | 新建/增量建立（无基线提交） |
| `tests/unit/test_contracts.py` | 测试图与多图样本契约及无隐式修改。 | 新建/增量建立（无基线提交） |
| `tests/unit/test_hardware_gate.py` | 测试硬件采集、Windows 内存分支和豁免结论。 | 新建/增量建立（无基线提交） |
| `tests/unit/test_hashing.py` | 测试稳定哈希、非有限值拒绝和路径无关性。 | 新建/增量建立（无基线提交） |
| `tests/unit/test_no_hardcoded_paths.py` | 测试个人绝对路径扫描规则。 | 新建/增量建立（无基线提交） |
| `tests/unit/test_paths.py` | 测试项目根定位和安全输出目录边界。 | 新建/增量建立（无基线提交） |
| `tests/unit/test_provenance.py` | 测试来源字段、Git 无首个提交、脱敏和写入。 | 新建/增量建立（无基线提交） |
| `tests/unit/test_smoke_components.py` | 测试三图、确定性和真实 PyG 批处理。 | 新建/增量建立（无基线提交） |
| `tests/unit/test_verify_week1.py` | 测试验收顺序、退出码、继续执行和诊断脱敏。 | 新建/增量建立（无基线提交） |
| `tests/integration/test_smoke_cli.py` | 以真实子进程验证 smoke 成功、复跑和 CUDA 拒绝。 | 新建/增量建立（无基线提交） |
| `tests/fixtures/` | 保留测试夹具目录边界。 | 新建/增量建立（无基线提交） |
| `tests/unit/` | 保留单元测试目录边界。 | 新建/增量建立（无基线提交） |
| `tests/integration/` | 保留集成测试目录边界。 | 新建/增量建立（无基线提交） |
| `tests/regression/` | 保留后续回归测试目录边界。 | 新建/增量建立（无基线提交） |
| `docs/CanoSPAR_异构多模态多图学习.md` | 用户原有研究设计说明，作为需求来源保留。 | 保留原有内容；pre-commit 仅规范 EOF/尾空白 |
| `docs/CanoSPAR实施计划.md` | 用户原有实施计划，作为需求来源保留。 | 保留原有内容；pre-commit 仅规范 EOF/尾空白 |
| `docs/experiment_contract.md` | 规定测试集封存、分组、训练集拟合、无标签构图和来源记录规则。 | 新建/增量建立（无基线提交） |
| `docs/decisions/README.md` | 规定后续架构决策记录格式和隐私边界。 | 新建/增量建立（无基线提交） |
| `reports/week1/hardware_gate.json` | 保存原始硬件测量、原始门禁及限定豁免。 | 新建/增量建立（无基线提交） |
| `reports/week1/BLOCKER_REPORT.md` | 解释历史阻断、测量保留和授权恢复。 | 新建/增量建立（无基线提交） |
| `reports/week1/WEEK1_IMPLEMENTATION_REPORT.md` | 保存本中文实施报告及最终验收结果。 | 新建/增量建立（无基线提交） |
| `reports/week1/verification_results.json` | 保存最终总验收生成的 17 项机器可读结果。 | 已生成（最终验收） |
| `reports/data_qc/` | 保留后续数据质控报告目录边界。 | 新建/增量建立（无基线提交） |
| `reports/graph_qc/` | 保留后续图质控报告目录边界。 | 新建/增量建立（无基线提交） |
| `reports/experiments/` | 保留后续实验报告目录边界。 | 新建/增量建立（无基线提交） |
| `reports/final/` | 保留后续最终报告目录边界。 | 新建/增量建立（无基线提交） |
| `reports/week1/` | 限定第一周硬件、阻断、实施和验收结果目录。 | 新建/增量建立（无基线提交） |
| `artifacts/` | 保存被 Git 忽略的 smoke 与后续运行产物。 | 新建/增量建立（无基线提交） |

缓存、临时 `.snakemake/` 内容和生成的 `artifacts/smoke/` 文件不计入源码清单。
两份原有研究 Markdown 中描述的后续模块仍只是需求来源，未被本报告宣称为已实现。

## 6. 关键设计决策

1. **中央处理器优先。** 使用官方预编译中央处理器 wheel；不安装 CUDA wheel，
   不依赖可选 PyG C++/CUDA 扩展。
2. **配置即证据。** Hydra 负责组合，解析配置和稳定哈希随每次 smoke 一同保存。
3. **不可变边界。** 冻结数据类加防御性复制，验证函数不修改调用方张量或映射。
4. **内容寻址。** 哈希只依赖规范化内容，不依赖 Python 内建 `hash()`、个人路径或映射顺序。
5. **输出最小权限（第一周快照）。** 第一周的可重复生成运行产物统一落在
   `artifacts/`；真实数据目录和常见医学影像、模型权重、运行目录均被 Git 忽略。
   后续阶段有意纳入版本控制的非敏感说明文档和汇总报告可进入 `docs/` 或 `reports/`。
6. **缺失值必须诚实。** 提交、清单或容器证据不存在时使用显式 `null`、状态和原因，
   不以占位哈希冒充。
7. **原始门禁与豁免分离。** `gate_passed` 保留历史测量，`effective_gate_passed`
   单独表达用户只豁免 6 GiB 可用内存检查后的授权结论。
8. **真实最小闭环。** smoke 使用真实 PyG `DataLoader` 和真实子进程，不联网、
   不下载数据、不训练模型。
9. **平台事实分层。** `environment.lock.yml` 只代表实际 win-64 环境；
   `environment.yml` 和项目元数据承担可移植安装说明。
10. **许可不擅自决定。** 正式许可证由用户后续选择；当前文件明确禁止把“待定”误写为
    已授予开源许可。

## 7. 实际运行的命令

以下结果来自最终环境中的实际运行。所有列出的命令退出码均为 0。

| 命令 | 退出码 | 结果或计数 |
| --- | ---: | --- |
| `python -m pip install -e ".[dev,research,workflow]"` | 0 | 可编辑安装成功。 |
| `python -m pip check` | 0 | 未发现依赖冲突。 |
| `python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())"` | 0 | `2.12.1+cpu None False`。 |
| `python -c "import torch_geometric; print(torch_geometric.__version__)"` | 0 | `2.8.0.post1`。 |
| `ruff check src tests` | 0 | 规则检查通过。 |
| `ruff format --check src tests` | 0 | 25 个文件已格式化。 |
| `mypy src/canospar` | 0 | 15 个源文件未发现问题。 |
| `pytest -q tests/unit` | 0 | 147 通过、0 失败、0 跳过；另有 2 条第三方弃用警告。 |
| `pytest -q tests/integration` | 0 | 3 通过、0 失败、0 跳过。 |
| `python -m canospar.utils.smoke_test` | 0 | `success`、中央处理器、3 张图、12 个节点、18 条边、3 维特征；配置哈希为 `09613f9612367cd29e209b389443b7c50f355967958ff9a287743d8052d94e44`。 |
| `pre-commit install` | 0 | 钩子安装成功。 |
| `pre-commit run --all-files`（第二次） | 0 | 全部钩子通过。第一次运行真实发现并修复 2 处 `UP038`，同时规范文档 EOF 和尾空白；该修复过程未隐藏。 |
| `snakemake -n -s workflow/Snakefile` | 0 | 仅包含 `all` 与 `smoke_test`；现有产物已是最新。 |
| `snakemake --cores 1 -s workflow/Snakefile` | 0 | 实际工作流执行成功。 |
| `python scripts/verify_week1.py` | 0 | 17 `PASS`、0 `FAIL`、0 `SKIP_WITH_REASON`；其中覆盖率检查强制 `--cov-fail-under=80`。 |
| `python -m pytest -q --cov=canospar --cov-report=term-missing --cov-fail-under=80 tests` | 0 | 150 个测试通过；总覆盖率 89.59%，达到 80% 门槛。 |
| `python -m build` | 0 | 成功生成源码分发包和 wheel，且无警告。 |
| `conda env create --dry-run --prefix "<TEMP_ENV_PREFIX>" --file environment.lock.yml` | 0 | win-64 锁文件 dry-run 成功。 |
| `git check-ignore` 分别检查 `artifacts/`、受限数据、`.env` 和 `.snakemake/` | 0 | 四类路径均被正确忽略。 |
| `python scripts/check_no_hardcoded_paths.py` | 0 | 未发现用户特定绝对路径。 |
| `git diff --check` | 0 | 未发现未暂存差异中的空白错误。 |
| `git diff --cached --check` | 0 | 未发现暂存内容中的空白错误。 |
| `git status --short` | 0 | 最终验收快照生成时，第一周文件均为已加入索引但未提交的 `A` 状态。 |

## 8. 测试结果

| 项目 | 最终结果 | 退出码 | 计数或覆盖率 |
| --- | --- | ---: | --- |
| 单元测试 | 通过 | 0 | 147 通过、0 失败、0 跳过；2 条第三方 `DeprecationWarning`。 |
| 集成测试 | 通过 | 0 | 3 通过、0 失败、0 跳过。 |
| 全量覆盖率 | 通过 | 0 | 150 通过；89.59%，高于 80% 门槛。 |
| 17 项统一验收矩阵 | 通过 | 0 | 17 `PASS`、0 `FAIL`、0 `SKIP_WITH_REASON`；覆盖率属于必需检查。 |
| smoke 产物一致性 | 通过 | 0 | 解析配置、provenance 与 smoke 报告共享配置哈希 `09613f9612367cd29e209b389443b7c50f355967958ff9a287743d8052d94e44`。 |
| Snakemake dry-run | 通过 | 0 | 仅 `all` 与 `smoke_test`，当前产物已是最新。 |
| Snakemake 单核执行 | 通过 | 0 | `--cores 1` 执行成功。 |
| 构建 | 通过 | 0 | 源码分发包与 wheel 均生成，无警告。 |

测试输出中的 2 条弃用警告来自第三方 PyTorch JIT 组件，不是项目测试失败；本项目未在
第一周引入对应弃用接口。

## 9. 已知问题和偏差

未发现已知阻断问题。以下项目是已授权偏差、诚实缺失值、平台边界或后续范围，不影响
第一周 `PASS`：

1. 原始可用内存门禁失败：最后一次仅 0.88 GiB。用户只豁免该项，因此
   `effective_gate_passed: true`，但原始 `gate_passed: false` 永久保留。
2. 最终验收快照生成时，工作树没有首个提交且没有远程仓库，无法给出不可变提交哈希；
   provenance 以 `null`、状态、原因和真实 `git_dirty: true` 表达。该记录是历史事实，
   不会因后续首次提交而被回填或伪造。
3. 第一周没有数据清单，也没有已构建容器；相应清单哈希和容器摘要明确为 `null`，
   并附状态与原因。
4. 实际锁文件仅适用于 win-64，不能当作 Linux 或 macOS 的跨平台锁。
5. 正式许可证仍待用户决定，当前不得宣称已开源或允许再分发。
6. 单元测试出现 2 条第三方 PyTorch JIT `DeprecationWarning`；测试仍全部通过，
   且项目代码未引入该弃用接口。
7. MRI 工具、M1 及后续模块、CanoSPAR 模型、训练、数据下载和科学评估仍属于后续范围，
   本阶段没有提前实现或宣称完成。

## 10. 我应该如何人工核对

以下 A–J 必须从仓库根目录执行，不要把个人安装路径写入仓库文件。

### A. 检查文件结构

```text
git status --short
```

确认核心文件存在，工作树保持未提交，且没有意外数据、密钥、模型权重或缓存文件进入
待跟踪清单。

### B. 从新环境安装

在 Windows PowerShell 中，将占位符替换为本机 Anaconda 根目录，但不要提交替换后的
路径：

```powershell
Set-Location "<REPOSITORY_ROOT>"
$AnacondaRoot = "<ANACONDA_ROOT>"
$env:CONDA_EXE = Join-Path $AnacondaRoot "Scripts\conda.exe"
.\scripts\bootstrap.ps1 -EnvironmentName "canospar-week1-audit"
& $env:CONDA_EXE run --name canospar-week1-audit python -m pip check
```

### C. 检查 CPU-only

```text
python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())"
```

预期 PyTorch 版本带 `+cpu`，`torch.version.cuda` 为 `None`，
`torch.cuda.is_available()` 为 `False`。

### D. 检查静态质量

```text
ruff check src tests
ruff format --check src tests
mypy src/canospar
```

三条命令都应以退出码 0 结束。

### E. 检查测试

```text
pytest -q tests/unit
pytest -q tests/integration
```

记录实际通过数、失败数和退出码，不以旧输出替代。

### F. 检查 smoke test

```text
python -m canospar.utils.smoke_test
```

预期命令成功，输出 `status: success`、`num_graphs: 3`、`device: cpu`，并在
`artifacts/smoke/` 中生成 `resolved_config.yaml`、`provenance.json` 和
`smoke_report.json`。人工确认三者的 `config_hash` 一致。

### G. 检查 Git 忽略

```text
git check-ignore artifacts/example.txt
git check-ignore data/example.nii.gz
```

两条命令都应以退出码 0 结束，证明产物与受限数据边界已被忽略。

### H. 检查是否存在硬编码路径

```text
python scripts/check_no_hardcoded_paths.py
```

预期退出码为 0，且报告未发现用户特定绝对路径。

### I. 检查 Snakemake

```text
snakemake -n -s workflow/Snakefile
```

只应出现 `all` 和 `smoke_test`，不得触发下载、MRI、模型或训练规则。

### J. 执行总验收

```text
python scripts/verify_week1.py
```

预期退出码为 0，17 项必需检查全部为 `PASS`，并生成
`reports/week1/verification_results.json`。如任一必需项为 `FAIL`，不得把本报告状态
改为最终通过。

## 11. 下一阶段边界

第一周结束前只允许修复验收缺陷和回填真实证据，不扩展研究功能。最终矩阵通过后，
下一阶段仍需单独授权和计划，至少包括：

- 由用户决定正式开源许可证；当前公开源码发布不构成开源许可授权，在正式许可证确定前
  不得宣称项目已开源，第三方也不得擅自再分发；
- 建立真实但不含受限个体信息的数据清单，并记录不可变清单哈希；
- 如决定使用容器，先固定基础镜像摘要，再构建并记录不可变容器摘要；
- 在任何数据处理前落实家庭或受试者分组、永久测试集封存和训练集拟合边界；
- 另行评审 MRI 工具链、数据访问合规和资源门禁，不沿用本周内存豁免自动扩大范围；
- 分阶段设计 M1 及后续模块、CanoSPAR 模型、训练和评估，每个阶段重新执行测试驱动、
  安全和可复现性验收。

当前不租服务器、不使用图形处理器、不运行 MRI、不实现模型、不训练，也不把 smoke
输出解释为科学结论。
