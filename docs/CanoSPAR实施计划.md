
> 设计依据：以 `CanoSPAR_异构多模态多图学习.md` 为主计划，MRI 主链优先；本轮不提前扩展电商、社交、文本—图像等通用多模态图。
>
> 目标：先在 HCP 上完成机制清晰、可复现的主实验，再在 PPMI 上完成临床和多中心外部验证。最终交付代码、数据清单、模型、消融、鲁棒性、统计检验和解释稳定性结果，不包含论文正文写作。
>
> 标准单人实施周期：约 46 周。若已取得数据、可直接使用 HCP 官方衍生数据且服务器资源稳定，可压缩至约 32–36 周。

---

## 0. 执行纪律

以下规则从第一天开始执行，后续不得临时改变。

1. **严格顺序执行**：当前阶段未通过验收，不进入下一阶段；不允许先写完整 CanoSPAR，再回头补数据和基线。
2. **HCP 先行，PPMI 后置**：HCP 用于跑通三模态链路和验证机制；PPMI 在 HCP 主实验稳定后用于临床、纵向、多中心和缺失模态验证。
3. **先精确、后近似**：ROI 图节点规模通常不大，先用精确特征分解得到谱滤波真值，再实现 Chebyshev；SLQ 只用于后期的大图扩展和效率实验。
4. **先简单模型、后复杂模型**：非图模型 → 单模态图模型 → 普通多模态融合 → 规范频带 → Token → 角色路由 → 稀疏通信。
5. **测试集永久封存**：测试集标签只允许在最终阶段读取；归一化、特征筛选、阈值、ComBat、超参数和早停均只能使用训练/验证数据。
6. **每个结论必须有独立实验支撑**：性能、谱对齐、噪声抑制、稀疏性、效率和解释稳定性分别验证，不能只用最终 AUC/MAE 代替全部证据。
7. **不得把近邻方法写成自己的创新**：SMGFM 已包含频带 token、Chebyshev 滤波和可靠性路由；DiP 已包含稀疏动态跨模态路径。本项目必须始终突出“多个独立拉普拉斯之间的规范谱质量坐标及其验证”。参见 [R18]、[R19]。

---

# 第 1 周：建立仓库、环境和不可变实验契约

## 1.1 本周目标

只建立项目基础设施，不处理全量数据，不实现模型。

## 1.2 建立仓库结构

```text
canospar/
├── README.md
├── LICENSE
├── pyproject.toml
├── environment.lock.yml
├── .pre-commit-config.yaml
├── containers/
│   ├── model.def
│   └── versions.md
├── configs/
│   ├── data/
│   ├── graph/
│   ├── model/
│   ├── experiment/
│   └── paths/
├── workflow/
│   ├── Snakefile
│   └── rules/
├── src/canospar/
│   ├── data/
│   ├── graph/
│   ├── spectral/
│   ├── models/
│   ├── training/
│   ├── evaluation/
│   └── utils/
├── scripts/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── regression/
├── reports/
│   ├── data_qc/
│   ├── graph_qc/
│   ├── experiments/
│   └── final/
└── artifacts/                 # 不提交 Git
```

## 1.3 固定技术栈

模型部分：

- Python 3.11；
- PyTorch；
- PyTorch Geometric，用于图数据结构、消息传递和 ChebConv 参考实现 [R10]；
- SciPy / NumPy，用于稀疏矩阵和精确特征分解；
- scikit-learn，用于拆分、传统基线和指标；
- `entmax`，用于稀疏 assignment [R12]；
- Hydra 或等价配置系统；
- MLflow 本地模式或 TensorBoard；
- pytest、ruff、mypy、pre-commit。

影像部分：

- BIDS Validator [R5]；
- MRIQC [R6]；
- fMRIPrep [R7]；
- QSIPrep/QSIRecon 或 QSIPrep+MRtrix3 [R8][R9]；
- FreeSurfer；
- Nilearn；
- Docker 或 Apptainer/Singularity。

## 1.4 建立最小持续集成

至少执行：

```bash
ruff check src tests
mypy src/canospar
pytest -q tests/unit
```

每次提交必须记录：

```text
commit_hash
config_hash
dataset_manifest_hash
container_digest
random_seed
```

## 1.5 建立全局数据对象契约

```python
BrainMultiGraphSample = {
    "subject_id": str,
    "visit_id": str,
    "group_id": str,      # HCP 官方 unrelated cohort 与 PPMI 均使用 subject_id；若另获 Restricted Access，可选用 Family_ID
    "site_id": str,
    "graphs": {
        "smri": {relation_name: GraphData},
        "dmri": {relation_name: GraphData},
        "fmri": {relation_name: GraphData},
    },
    "modality_available": dict[str, bool],
    "qc_vector": dict[str, float],
    "target": float | int,
    "covariates": dict[str, float | str],
    "cohort_metadata": dict[str, str],  # cohort_source / unrelated_list_version / kinship_control_method
}
```

```python
GraphData = {
    "x": "FloatTensor[N, F]",
    "edge_index": "LongTensor[2, E]",
    "edge_weight": "FloatTensor[E]",
    "num_nodes": int,
    "modality": str,
    "relation": str,
    "graph_qc": dict,
    "construction_hash": str,
}
```

## 1.6 通过标准

- 新环境从零安装后能运行 `pytest`；
- `python -m canospar.utils.smoke_test` 能构造 3 张随机图并完成一次 DataLoader 批处理；
- 所有配置均可保存为 YAML；
- 不存在写死的本机绝对路径；
- `artifacts/`、原始影像和受限数据不进入 Git。

---

# 第 2–4 周：申请数据、冻结科学问题并建立数据清单

## 2.1 同时申请 HCP 与 PPMI 访问

此时只申请和盘点，不处理 PPMI 模型。

- HCP 主数据使用 HCP-Young Adult 2025 Open Access 影像；正式监督实验采用 HCP 官方公开的 unrelated 受试者名单作为候选白名单，并与 2025 版三模态可用性、目标完整性和 QC 结果取交集 [R1][R2]。`Family_ID` 不再作为必需字段；完整 Open Access 队列只能用于管线调试，不能直接随机拆分后作为主结果 [R21][R22]。
- PPMI 是纵向、多中心的 PD 自然史研究，具有健康对照、PD、前驱期人群及多次随访；当前 MRI 手册包含 T1、rs-fMRI 和 DTI 流程 [R3][R4]。
- HCP-YA 2025 影像必须从当前官方平台获取，不得与 2017 S1200 处理影像混用；旧 DataLad HCP1200 仓库仅作为下载工程参考，不作为本项目主数据源 [R1][R23]。

建立：

```text
legal/
├── hcp_access_status.md
├── ppmi_access_status.md
├── data_use_restrictions.md
└── permitted_outputs.md
```

不得公开任何受限个体级数据。

## 2.2 冻结 HCP 主任务

先下载数据字典并核验变量，然后从下列候选中冻结一个主任务：

- 认知总复合分数回归；
- 流体认知复合分数回归；
- 流体智力测验得分回归。

执行规则：

1. 主终点只能选择一个；
2. 第二、第三个目标只能作为次要任务；
3. 不允许看完模型结果后更换主终点；
4. 记录年龄、性别、教育等协变量，但主模型是否使用协变量必须提前固定；
5. 推荐同时提供“仅影像”和“影像+基本协变量”两条结果，防止模型只是复制人口学信息。

## 2.3 冻结 PPMI 任务选择门槛

PPMI 任务现在不直接确定，先写成数据驱动但事前固定的决策树：

```text
若基线三模态 + 24 月 MDS-UPDRS 目标的独立受试者 N ≥ 180：
    主任务 = 基线 MRI 预测 24 月 MDS-UPDRS 变化（回归）
若 120 ≤ N < 180：
    主任务 = 基线 MRI 预测较短时间窗变化；PD/HC 分类为次要任务
若 N < 120：
    PPMI 不承担主性能结论，只承担多中心、缺失模态和质量路由压力测试
```

阈值是工程决策门槛，不是统计功效证明；最终仍需报告样本量、标签方差和置信区间。

## 2.4 建立 manifest 生成程序

实现：

```text
src/canospar/data/build_hcp_manifest.py
src/canospar/data/build_ppmi_manifest.py
src/canospar/data/validate_manifest.py
```

每行至少包含：

```text
subject_id, visit_id, family_id, site_id, scanner,
cohort_source, unrelated_list_version, kinship_control_method,
age, sex, diagnosis, target, target_date,
t1_path, dwi_path, fmri_path,
t1_available, dwi_available, fmri_available,
raw_qc_status, exclusion_reason
```

其中 HCP 的 `family_id` 在不使用 Restricted Access 时允许为空，但必须设置：

```text
cohort_source = hcp_official_unrelated
unrelated_list_version = <文件名或发布日期>
kinship_control_method = official_unrelated_cohort
```

## 2.5 初始样本审计

输出：

- 每个模态可用人数；
- 三模态交集人数；
- HCP 官方 unrelated 名单原始人数、与 HCP-YA 2025 可用受试者的交集人数、三模态完整人数及目标完整人数；
- PPMI 站点、扫描仪、诊断和访视分布；
- 目标缺失率；
- 模态缺失模式；
- 受试者重复访视情况；
- 影像日期与临床日期间隔。

## 2.6 通过标准

- `dataset_manifest.csv` 可由脚本重复生成且哈希一致；
- HCP 正式样本全部属于冻结的官方 unrelated 名单，受试者 ID 唯一，且名单来源、版本与 SHA256 哈希可追踪；
- 同一 PPMI 受试者的所有访视可被识别；
- 数据缺失原因区分为“未采集、下载失败、预处理失败、QC 失败”；
- HCP 主任务已冻结并写入 `configs/data/hcp.yaml`；
- PPMI 任务决策树已冻结，但尚未使用测试结果选择任务。

---

# 第 5–7 周：建立小规模影像试运行集

## 3.1 选择试运行样本

从 HCP 选择约 24 名受试者：

- 覆盖男性/女性；
- 覆盖目标分数的低、中、高区间；
- 全部来自冻结的官方 unrelated 候选名单，且受试者 ID 不重复；
- 三种 MRI 均完整；
- 不追求统计代表性，只用于管线调试。

PPMI 选择约 12–20 个样本，仅测试下载、BIDS 转换和工具兼容性，不训练模型。

## 3.2 HCP 数据路线

主路线优先使用 HCP 官方最小预处理结果，避免在全量 1200 人上重复昂贵预处理。保留少量原始数据用于验证本地流程与官方衍生结果的一致性。

试运行需完成：

1. T1/FreeSurfer 表面和分区读取；
2. 静息态 fMRI 时序提取；
3. dMRI 预处理输出读取或本地 QSIPrep 测试；
4. 同一 atlas 在三种模态空间中的映射；
5. QC 文件读取。

## 3.3 PPMI BIDS 转换试运行

对 PPMI DICOM 建立匿名化、序列映射和 BIDS 转换规则。

```bash
bids-validator-deno /path/to/ppmi_bids
```

禁止在转换后手工修改单个受试者而不记录规则。所有例外写入：

```text
configs/data/ppmi_heuristic.py
reports/data_qc/ppmi_conversion_exceptions.csv
```

## 3.4 MRIQC 和预处理试运行

示意命令：

```bash
mriqc /bids /derivatives/mriqc participant \
  --participant-label sub-001 \
  --no-sub

fmriprep /bids /derivatives/fmriprep participant \
  --participant-label sub-001 \
  --fs-license-file /licenses/license.txt \
  --output-spaces MNI152NLin2009cAsym:res-2 T1w

qsiprep /bids /derivatives/qsiprep participant \
  --participant-label sub-001 \
  --output-resolution 2.0 \
  --fs-license-file /licenses/license.txt
```

实际执行时必须锁定容器 digest，不允许只写 `latest`。

## 3.5 人工 QC 表

每个试运行样本必须人工检查：

- T1 脑提取；
- 皮层分割；
- BOLD 到 T1 配准；
- T1 到模板配准；
- dMRI 畸变和运动校正；
- atlas 到 BOLD/dMRI 空间的 ROI 对齐；
- ROI 是否落在脑外；
- 时序是否存在大量尖峰；
- tractography 是否出现异常全脑纤维束。

输出：

```text
reports/data_qc/pilot_manual_qc.csv
reports/data_qc/pilot_failure_gallery/
```

## 3.6 通过标准

- HCP 试运行样本三模态均能输出 ROI 级数据；
- PPMI BIDS Validator 无 error；warning 有逐条说明；
- 预处理失败能够自动记录，而不是静默跳过；
- 任意输出均可回溯到原始输入、容器版本和配置；
- atlas 在三模态上的节点编号完全一致。

---

# 第 8–12 周：完成 HCP 正式 unrelated cohort 数据整理和质量控制

## 4.1 固定 atlas

为兼顾 HCP 和 PPMI，主实验不使用只适合 HCP 高分辨率数据的超细粒度分区。

建议：

- 主 atlas：约 200 个皮层 ROI，加固定的皮层下 ROI；
- 敏感性 atlas：Desikan–Killiany 级别的较粗分区；
- atlas 为外部固定资源，不从标签学习；
- 三模态必须使用完全一致的节点编号表。

生成：

```text
assets/atlas/roi_table.tsv
assets/atlas/roi_adjacency.npy
assets/atlas/roi_centroids.npy
```

## 4.2 sMRI 特征

每个 ROI 提取：

- cortical thickness；
- surface area；
- gray matter volume；
- mean curvature；
- 皮层下体积或相应形态指标。

保留原始值和标准化值。标准化器只在训练折拟合。

## 4.3 rs-fMRI 时序

对每个 run：

1. 读取 fMRIPrep/HCP confounds；
2. 移除非稳态体积；
3. 回归运动参数、导数和平方项；
4. 回归 aCompCor/WM/CSF；
5. 加入高通或带通；
6. 对高运动帧进行 censor/scrub；
7. 提取 ROI 时序；
8. 多 run 结果先分别构图，再求稳健平均；
9. 主分析不使用全局信号回归，GSR 作为敏感性实验。

所有策略写入 `configs/data/confounds.yaml`。

## 4.4 dMRI 结构连接

推荐主流程：

1. QSIPrep 完成去噪、运动、涡流、磁敏感畸变和 T1 配准 [R8]；
2. QSIRecon 或 MRtrix3 完成响应函数/FOD、ACT tractography；
3. SIFT2 生成定量纤维权重；
4. `tck2connectome` 映射到 atlas [R9]；
5. 同时保存 streamline count、SIFT2 weight、mean FA 等矩阵；
6. 主关系使用 SIFT2 权重，其他矩阵作为敏感性关系。

## 4.5 QC 向量

建立两级 QC：

### 硬失败

用于剔除明显不可用数据：

- 预处理程序失败；
- 大面积脑区缺失；
- atlas 严重错位；
- ROI 时序长度不足；
- dMRI 无法生成有效 connectome；
- 数值含 NaN/Inf。

### 软质量指标

保留并输入模型：

- sMRI：Euler number、分割异常、区域厚度离群率；
- fMRI：mean FD、最大 FD、DVARS、tSNR、被删帧比例、有效帧数；
- dMRI：平均运动、outlier slice 比例、eddy QC、连接成功率；
- 图级：密度、连通分量、平均度、权重分布、谱熵。

软 QC 不得先按结果标签调阈值。

## 4.6 批量运行和失败恢复

使用 Snakemake：

```bash
snakemake --use-apptainer --cores 32 --rerun-incomplete --keep-going
```

每个 rule 输出 `.done.json`：

```json
{
  "subject_id": "...",
  "input_hash": "...",
  "output_hash": "...",
  "software": "...",
  "container_digest": "...",
  "status": "success"
}
```

## 4.7 通过标准

- HCP 最终纳入人数、排除人数和原因明确；
- 三模态节点映射一致；
- 100% 样本具有可追踪 QC；
- 10% 随机样本完成人工复核；
- 重跑任一受试者可生成相同 ROI 数据和 connectome 哈希；
- 数据阶段尚未使用目标标签做构图或 QC 选择。

---

# 第 13–15 周：实现 M1——多模态多关系图构建

## 5.1 先实现最小图集合

第一版每个模态只使用一个主关系，避免一开始产生大量关系图：

```text
sMRI: individual_morphological_similarity
 dMRI: sift2_structural_connectivity
 fMRI: positive_pearson_connectivity
```

运行稳定后再增加：

```text
sMRI: atlas_spatial_adjacency
 dMRI: fa_weighted_connectivity
 fMRI: negative_pearson_connectivity
 fMRI: partial_correlation
```

## 5.2 sMRI 个体形态相似图

对每个 ROI 的形态特征向量：

$$
x_i=[\text{thickness},\text{area},\text{volume},\text{curvature}],
$$

先在训练折内做稳健标准化，再计算 RBF 或余弦相似度：

$$
A_{ij}=\exp\left(-\frac{\|x_i-x_j\|_2^2}{2\sigma^2}\right).
$$

实施细节：

- `sigma` 只由训练集决定；
- 每个节点保留 top-
  \(k\) 邻居，随后对称化；
- 记录孤立节点；
- atlas 空间邻接作为独立关系，不能与形态相似边直接相加。

## 5.3 dMRI 图

主边权：

$$
A_{ij}=\log(1+\text{SIFT2Weight}_{ij}).
$$

可选归一化：ROI 体积、总权重或对称归一化。主协议只能选一种，其他作为敏感性实验。

节点特征第一版采用：

- 结构连接 profile；
- 节点 strength；
- mean FA/MD（若稳定可用）；
- 不允许把标签或全队列统计写入节点特征。

## 5.4 fMRI 图

1. 对 ROI 时序计算 Pearson 相关；
2. Fisher-z 变换；
3. 正边和负边必须拆成不同关系；
4. 负边关系使用绝对值作为非负权重，并保留 `sign=-1` 元数据；
5. 主协议采用固定 top-
   \(k\) 或固定密度；
6. 节点特征采用连接 profile 和时序统计。

## 5.5 图密度协议

主设置固定后，额外测试 3 个密度：

```text
低密度 / 主密度 / 高密度
```

不要根据测试性能挑选密度。密度只在内层训练验证中确定。

## 5.6 图缓存格式

每个样本保存：

```text
artifacts/graphs/{dataset}/{subject}/{visit}/{modality}_{relation}.pt
artifacts/graphs/{dataset}/{subject}/{visit}/metadata.json
```

`metadata.json` 至少包含：

```text
num_nodes, num_edges, density, components,
weight_min, weight_max, weight_mean,
construction_config_hash, atlas_hash,
input_feature_hash, qc_summary
```

## 5.7 单元测试

- 邻接矩阵对称；
- 无 NaN/Inf；
- 边权非负；
- 对角线处理一致；
- 节点数与 atlas 一致；
- 置换节点后，图统计一致；
- fMRI 正负边不会重复；
- 训练外样本不参与标准化器拟合。

## 5.8 通过标准

- 所有纳入 HCP 样本可构建最小三图集合；
- 每条边可追溯到具体构图规则；
- 图密度、连通分量和边权分布有可视化报告；
- 无标签泄漏；
- 在相同输入和配置下图缓存哈希稳定。

---

# 第 16–18 周：先建立无 CanoSPAR 的可运行基线

## 6.1 固定数据拆分

HCP 正式监督实验只使用冻结的官方 unrelated cohort；`group_id=subject_id`。官方 S900 unrelated 名单仅是候选白名单，最终 cohort 必须与 HCP-YA 2025 三模态可用性、目标完整性和 QC 结果取交集，并保存名单来源、版本与哈希。亲缘或重复受试者跨折会削弱独立性，因此不得以完整 Open Access 队列的普通随机拆分替代该协议 [R21]。

推荐最终协议：

- 外层 5 折受试者级 KFold，回归任务可在训练数据内按目标分位箱做近似分层；
- 内层 3 折选择超参数；
- 任一受试者只存在于一个外层折；
- 主结果使用固定的 5 个随机种子；
- 开发阶段仅使用第 1 外层折，减少计算；
- 最终测试前锁定全部候选超参数；
- 若未来另获 Restricted Access，可在更大 HCP 队列上增加 `Family_ID` group split 作为扩展实验，但不替换当前预注册主协议。

回归任务的分位分层只能用于保持目标分布，所有预处理和分箱边界必须在训练折内确定。

## 6.2 非图基线

实现：

1. Ridge/Elastic Net；
2. XGBoost 或 HistGradientBoosting；
3. MLP；
4. 单模态和三模态拼接两种输入。

输入为：

- sMRI ROI 特征；
- dMRI 上三角连接；
- fMRI 上三角连接；
- PCA 只在训练折拟合。

## 6.3 单模态图基线

至少实现：

- GCN；
- GAT；
- ChebNet/ChebNetII 参考；
- BrainGNN [R16]；
- Brain Network Transformer [R17]。

不要求第一轮全部达到论文最优值，但必须统一数据、拆分、参数预算和早停规则。

## 6.4 普通多模态基线

按顺序实现：

1. 三个单模态模型预测平均；
2. 三个图级 embedding 拼接；
3. 模态门控融合；
4. dense cross-attention；
5. IBrainGNN/MaskGNN 类三模态模型 [R15]。

## 6.5 统一训练器

```text
src/canospar/training/trainer.py
src/canospar/training/callbacks.py
src/canospar/evaluation/metrics.py
```

必须支持：

- 同一拆分；
- 同一早停；
- 梯度裁剪；
- 混合精度；
- checkpoint；
- seed；
- 每个样本预测保存；
- 参数量、时间和显存统计。

## 6.6 指标

HCP 回归主指标：MAE。

同时报告：

- RMSE；
- Pearson \(r\)；
- Spearman \(\rho\)；
- \(R^2\)；
- 预测校准斜率；
- 按性别和目标区间的误差。

## 6.7 通过标准

- 非图基线和至少两个图基线可完成完整训练；
- 数据拆分检查 0 泄漏；
- 同一 seed 重跑预测误差在允许数值范围内；
- 模型能明显过拟合 16–32 个样本的小数据集，证明训练代码有效；
- 全标签随机打乱后，性能回到随机/均值基线附近；
- 形成第一张正式基线表。

---

# 第 19–20 周：实现 M2——拉普拉斯、谱统计和图质量向量

## 7.1 归一化拉普拉斯

对非负对称图：

$$
L=I-D^{-1/2}AD^{-1/2}.
$$

实现：

```text
src/canospar/spectral/laplacian.py
src/canospar/spectral/statistics.py
```

孤立节点处理必须固定：

- 优先通过构图协议减少孤立节点；
- 若存在孤立节点，令相应 \(D^{-1/2}=0\)；
- 记录孤立节点数；
- 不静默删除节点。

## 7.2 精确谱分解

ROI 图规模不大，先执行：

```python
lambda_, U = scipy.linalg.eigh(L)
```

保存：

- 全部特征值；
- 小图调试用特征向量；
- 谱范围；
- 特征值重数；
- 零特征值数量。

## 7.3 谱统计

每张图计算：

- density；
- mean degree；
- components；
- algebraic connectivity；
- spectral entropy；
- eigenvalue quantiles；
- Dirichlet energy：
  \(\operatorname{tr}(X^TLX)/\|X\|_F^2\)；
- 简单扩散统计。

## 7.4 质量向量标准化

QC 向量只在训练折进行：

- 缺失值填补；
- winsorization；
- robust scaling；
- 保存变换器供验证/测试使用。

## 7.5 数值测试

- \(L=L^T\)；
- 特征值在数值容差内位于 \([0,2]\)；
- \(LU=U\Lambda\) 残差小；
- 节点置换前后特征值一致；
- 完全断开图、完全图、路径图和环图结果与解析性质一致。

## 7.6 通过标准

- HCP 每张主关系图均能得到可靠谱；
- 特征分解残差和正交残差满足数值容差；
- 不同模态的谱分布确实存在可视化差异；
- 质量向量没有使用测试折统计量。

---

# 第 21–22 周：实现 M3——规范谱质量坐标，并先做机制实验

## 8.1 精确规范坐标

给定排序特征值：

$$
\lambda_1\le \cdots \le \lambda_N,
$$

定义离散坐标：

$$
u_i=\frac{i-0.5}{N}.
$$

使用中点秩而不是直接 \(i/N\)，减少端点处理歧义。

频带边界：

```text
B = 4
[0, 0.25), [0.25, 0.5), [0.5, 0.75), [0.75, 1]
```

实现：

```text
src/canospar/spectral/canonical_coordinate.py
```

必须明确：在精确谱下，等质量频带本质上是按特征值秩分组；真正需要证明的是这种图特异阈值是否比固定原始 \(\lambda\) 区间更稳定地承载相对频率角色，而不是宣称秩本身天然具有语义。

## 8.2 建立三个对照

- `raw_lambda_fixed`：所有图使用相同原始特征值边界；
- `eigen_rank_equal_mass`：每张图按谱秩等分；
- `learned_raw_lambda`：在训练集学习全局边界，但所有图共用。

CanoSPAR 必须优于至少一个强对照，而不是只与明显不合理的固定区间比较。

## 8.3 合成图机制实验

在实现后续神经模块前完成。

### 合成族 A：相同社区语义，不同谱密度

1. 生成具有相同节点和社区标签的 SBM；
2. 改变边密度、度异质性和边权尺度；
3. 构造社区平滑信号作为 shared；
4. 构造局部高频信号作为 private；
5. 加入可控白噪声。

### 合成族 B：拓扑扰动

- 随机删边；
- 随机加边；
- degree-preserving rewiring；
- 局部社区破坏。

### 负对照

生成语义和拓扑均无关的图。规范坐标不应强行产生高对齐；后续路由应依赖表示相似性而拒绝通信。

## 8.4 机制指标

- 正确 shared 频带召回率；
- fixed-\(\lambda\) 与 equal-mass 的 band assignment agreement；
- 过滤后 shared 信号相关性；
- 不同扰动强度下的稳定性曲线；
- unrelated graph 的错误对齐率；
- 频带边界对谱分布变化的敏感性。

## 8.5 HCP 无监督谱检验

不使用标签，计算：

- 同一受试者不同模态的频带能量分布；
- 不同受试者同一模态的边界稳定性；
- raw-\(\lambda\) 与 equal-mass 对图密度的相关性；
- 图密度变化后频带样本数是否失衡。

## 8.6 通过标准

- 合成族 A 中 equal-mass 对共享相对频率角色的恢复优于 fixed-\(\lambda\)；
- 负对照中不会仅因分位相同产生虚假高相似；
- 结果在多种图扰动和随机种子下稳定；
- 若机制实验失败，停止后续 CanoSPAR，实现并修改规范坐标定义。

---

# 第 23–24 周：实现 M4——精确频带滤波与 Chebyshev 近似

## 9.1 先实现精确滤波真值

对平滑窗口 \(g_b(\lambda)\)：

$$
Z_b^{\text{exact}}=U g_b(\Lambda)U^T X.
$$

禁止直接使用硬矩形窗口作为最终方案。先实现：

- raised-cosine；
- sigmoid difference；
- 可配置 transition width。

## 9.2 图特异的 \(\lambda\) 边界

对每张图通过经验分位数得到：

$$
q_b=F_L^{-1}(\tau_b).
$$

平滑窗口在 \(q_b\) 附近过渡。若特征值大量重复，边界必须记录 tie 处理。

## 9.3 Chebyshev 近似

缩放：

$$
\widetilde L=\frac{2L}{\lambda_{\max}}-I.
$$

递推：

$$
T_0X=X,\qquad T_1X=\widetilde LX,
$$

$$
T_kX=2\widetilde L T_{k-1}X-T_{k-2}X.
$$

实现：

```text
src/canospar/spectral/filter_exact.py
src/canospar/spectral/filter_chebyshev.py
src/canospar/spectral/window.py
```

参考 ChebNet/ChebNetII 和 PyG ChebConv [R10][R11]，但本项目的系数由图特异分位边界生成。

## 9.4 阶数选择

候选：

```text
K ∈ {5, 10, 20, 30, 50}
```

只在试运行和训练折选择。记录：

- 相对 Frobenius 误差；
- 频率响应误差；
- 频带泄漏；
- 时间；
- 内存。

## 9.5 验收阈值

工程目标：

```text
平均相对误差 ≤ 5%
95 分位相对误差 ≤ 10%
频带能量总和能近似重构原信号
```

若无法达到，优先增大 transition width 或阶数，不先改神经网络。

## 9.6 SLQ 暂不进入主训练

实现接口占位：

```text
src/canospar/spectral/cdf_slq.py
```

但 HCP/PPMI 主实验继续使用精确谱。SLQ 仅在最后扩展到大节点合成图时使用；其经验谱近似可参考 [R13][R14]。

## 9.7 通过标准

- Chebyshev 输出与精确滤波在试运行图上匹配；
- 滤波器频率响应有自动绘图；
- 节点置换后滤波结果按相同置换变化；
- 四频带能量和不出现系统性爆炸或消失；
- K 和过渡宽度均由验证集确定。

---

# 第 25–26 周：实现 M5——频带 Token 化

## 10.1 统一隐空间

每个模态/关系先通过独立输入投影：

$$
\bar Z^{(m,r,b)}=\operatorname{MLP}_{m,r}(Z^{(m,r,b)})\in\mathbb R^{N\times d}.
$$

第一版建议：

```text
d = 64
B = 4
p = 4 tokens per band
```

## 10.2 稀疏 assignment

```python
logits = assignment_mlp(z)          # [N, p]
S = entmax15(logits, dim=-1)        # 每个节点对 token 稀疏分配
H = (S.T @ z) / (S.sum(0)[:, None] + eps)
```

输出：

```text
H: [p, d]
S: [N, p]
```

## 10.3 防退化损失

### 使用率

防止 token 永远为空。

### 覆盖率

防止所有节点集中在一个 token。

### 去相关

降低多个 token 学到相同表示：

$$
\mathcal L_{token\_div}=\|\operatorname{offdiag}(\hat H\hat H^T)\|_F^2.
$$

### 轻度熵控制

促进稀疏，但不强迫 one-hot。

## 10.4 Token 元数据

每个 token 附带：

```text
subject_id
modality
relation
band_id
band_center_u
band_lambda_low
band_lambda_high
graph_qc
modality_qc
token_mass
assignment_entropy
```

## 10.5 单元测试

- 节点置换后 token 输出不变；
- `S` 行和为 1；
- 无空 token 时分母稳定；
- 全相同节点特征不导致 NaN；
- batch 内不同节点数可处理；
- 梯度可反向传播到 assignment MLP 和频带编码器。

## 10.6 通过标准

- 活跃 token 比例大于 80%；
- 单个 token 长期占据超过 70% 节点时触发告警；
- 多 token 表示不是完全重复；
- Token 模型在 HCP 主任务上至少不显著劣于对应的频带 pooling 模型；
- 仍未加入角色或跨图路由。

---

# 第 27–28 周：实现 M6——shared/private/noisy 角色与可靠性

## 11.1 分两步训练角色

### 第一步：shared/private

先证明角色分离不会破坏任务性能。

### 第二步：增加 noisy

使用可控污染和真实 QC 建立弱监督，不直接假定所有高频都是 noisy。

## 11.2 路由器输入

$$
r_i=[H_i,u_i,\Delta u_i,e_i,q_i,a_i],
$$

包括：

- token 表示；
- 频带中心和宽度；
- 图谱统计；
- 模态和图 QC；
- 模态可用性；
- token assignment 熵。

```python
role_prob = softmax(role_mlp(r_i) / temperature)
```

第一版使用 softmax，稳定后比较 entmax。不要一开始使用硬离散角色。

## 11.3 污染增强

每个 batch 随机选择一个模态或关系，施加不同强度：

- 节点特征 Gaussian noise；
- 随机 masking；
- 边删除/添加；
- degree-preserving rewiring；
- fMRI 连接 profile 打乱；
- dMRI 弱连接删除；
- 整模态缺失。

记录真实 corruption mask 和 severity。

## 11.4 角色损失

### 任务损失

保持下游可用性。

### noisy 排序损失

污染后 noisy mass 应高于干净版本：

$$
\mathcal L_{noise-rank}=\max(0,m+p_{noisy}^{clean}-p_{noisy}^{corrupt}).
$$

### QC 单调性

质量更低时 shared/outgoing 倾向应降低，但仅作为软约束。

### shared 一致性

同一受试者、兼容频带的 shared 表示应比不同受试者更接近。

### shared/private 去相关

减少重复编码，不要求完全独立。

### 防塌缩

对 batch 角色使用率设置宽松上下界，避免全部 shared 或全部 private。

## 11.5 角色诊断

输出：

- 每模态、关系、频带角色比例；
- noisy mass 与 corruption severity 的曲线；
- shared mass 与 QC 的关系；
- clean/corrupt 成对变化；
- 不同 seed 的角色稳定性。

## 11.6 通过标准

- 污染强度与 noisy mass 呈稳定正相关；
- 污染后 shared mass 或后续出边倾向下降；
- 三角色均未塌缩；
- 干净数据任务性能不比无角色模型显著下降；
- 真实 QC 与路由行为的关系在控制模态和频带后仍可观察。

若 noisy 角色无法被污染实验验证，不能保留“噪声识别”强表述，只能改称 reliability/down-weighting。

---

# 第 29–30 周：实现 M7——角色条件稀疏跨图路由

## 12.1 候选通信范围

只允许跨不同 `(modality, relation)` 的 token 通信。第一版禁止同一图内部路由，避免与图内编码混淆。

## 12.2 打分

$$
a_{ij}=\frac{q(H_i)^Tk(H_j)}{\sqrt d}
-\lambda_u|u_i-u_j|
-\lambda_qd_{QC}(i,j)
+e_{relation(i,j)}.
$$

再乘或加上 shared 概率。

## 12.3 Top-k

候选：

```text
k ∈ {2, 4, 8}
```

```python
idx = torch.topk(score, k=k, dim=-1).indices
alpha = masked_softmax(score, idx)
```

更新：

$$
\widetilde H_i=H_i+
\pi_i^{shared}
\sum_{j\in TopK(i)}
\alpha_{ij}\pi_j^{shared}W_vH_j.
$$

## 12.4 真实复杂度声明

必须区分：

1. **dense score + sparse aggregation**：仍需计算全部 token pair 分数，只减少消息和路由边；
2. **sparse candidate generation**：先按频带桶、模态兼容表和质量阈值生成候选，再计算分数，才能接近 \(O(Tkd)\)。

主实现先完成第 1 种；稳定后再完成第 2 种。论文结果不得把第 1 种误写为全流程线性复杂度。

## 12.5 private 与 noisy 通道

- private 不参与跨图发送，直接保留到读出；
- noisy 在主任务中降权，可进入遮蔽重建；
- 模态完全缺失时生成 availability mask，不构造虚假 token。

## 12.6 单元测试

- 路由边数量不超过 \(T\times k\)；
- 不存在非法同图边；
- 每个 source 的 alpha 和为 1；
- shared=0 时无跨图消息；
- 缺失模态时不引用不存在 token；
- 节点置换不改变 token 路由；
- route log 可序列化。

## 12.7 通过标准

- dense 和 sparse 路由都能训练；
- sparse 路由边数显著少于 dense；
- 污染模态的 outgoing route mass 下降；
- private 通道保留后，单模态特有信息没有被强制抹平；
- 多 seed 的高权重路由具有可接受重合率。

---

# 第 31–33 周：实现 M8——完整 CanoSPAR、训练阶段和损失

## 13.1 完整前向路径

```text
Graph input
→ modality/relation encoder
→ canonical band filtering
→ token assignment
→ role router
→ sparse cross-graph routing
→ shared/private readout
→ task head
```

## 13.2 读出

$$
h_{shared}=Pool(\{\widetilde H_i\}),
$$

$$
h_{private}=Pool(\{\pi_i^{private}H_i\}),
$$

$$
h=[h_{shared};h_{private};h_{QC}].
$$

任务头第一版采用两层 MLP，不使用过深结构。

## 13.3 总损失

$$
\mathcal L=
\mathcal L_{task}
+\lambda_{token}\mathcal L_{token}
+\lambda_{role}\mathcal L_{role}
+\lambda_{decor}\mathcal L_{decor}
+\lambda_{mask}\mathcal L_{mask}.
$$

损失权重仅在内层验证选择。

## 13.4 分阶段训练

### Stage A：单图编码与任务头预热

不启用角色和跨图通信。

### Stage B：启用频带 Token

保持路由关闭，检查 token 是否退化。

### Stage C：启用 shared/private/noisy

加入污染增强。

### Stage D：启用 sparse routing

先冻结部分底层编码器，再端到端微调。

这种顺序用于定位塌缩和负迁移来源。

## 13.5 主超参数搜索范围

```text
hidden_dim: [32, 64, 128]
num_bands: [3, 4, 6]
cheb_order: [10, 20, 30]
tokens_per_band: [2, 4, 8]
top_k: [2, 4, 8]
dropout: [0.1, 0.3, 0.5]
lr: [1e-4, 3e-4, 1e-3]
weight_decay: [1e-5, 1e-4, 1e-3]
```

禁止一次性笛卡尔穷举。先用开发折做粗筛，再冻结小候选集进入嵌套验证。

## 13.6 通过标准

- 完整模型可在小样本上过拟合；
- 每个阶段均有独立 checkpoint；
- 角色和 token 不塌缩；
- 梯度无持续 NaN/Inf；
- 与无路由模型相比，训练稳定性可接受；
- 所有预测和路由均可保存到样本级文件。

---

# 第 34–37 周：完成 HCP 主实验、消融和鲁棒性

所有实验使用相同外层拆分。先冻结实验清单，后批量运行。

## 14.1 E0：数据和泄漏负控

- 标签打乱；
- 完整 Open Access 队列的受试者级随机拆分仅作为非正式敏感性分析，不进入主表；由于其与 unrelated cohort 在样本规模和组成上同时不同，不得把二者差异直接解释为纯家庭泄漏效应；
- 使用仅人口学协变量模型；
- 检查模型是否主要依赖年龄/性别。

## 14.2 E1：性能主表

比较：

1. Ridge/Elastic Net；
2. XGBoost/MLP；
3. GCN/GAT/ChebNet；
4. BrainGNN；
5. Brain Network Transformer；
6. 单模态最佳模型；
7. late fusion；
8. dense cross-attention；
9. IBrainGNN 类三模态模型；
10. CanoSPAR。

若 SMGFM/DiP 官方代码可用，按原论文接口纳入；若不可用，只能标记为 `paper-based reimplementation`，不能声称完全复现 [R18][R19]。

## 14.3 E2：规范谱坐标消融

```text
A. fixed raw lambda bands
B. learned global lambda bands
C. equal-width lambda bands per graph
D. canonical equal-mass bands
E. no spectral bands
```

同时报告：

- 下游 MAE/相关；
- 频带能量稳定性；
- 图扰动稳定性；
- 频带跨图对应指标。

## 14.4 E3：Token 消融

```text
mean pooling
attention pooling
softmax assignment
sparsemax
entmax15
p = 2/4/8
```

报告 token 使用率、冗余、性能和计算量。

## 14.5 E4：角色消融

```text
no roles
shared/private
shared/noisy
shared/private/noisy
remove QC input
remove corruption supervision
```

## 14.6 E5：路由消融

```text
no cross-modal communication
dense attention
top-k only
top-k + canonical band penalty
top-k + QC penalty
full CanoSPAR
```

## 14.7 E6：模态污染

对每种模态分别增加 4–5 个强度：

- 节点噪声；
- 边噪声；
- 局部连接删除；
- 整图重连。

指标：

- 性能下降曲线；
- noisy mass；
- shared mass；
- outgoing route mass；
- 与无 QC 路由模型比较。

## 14.8 E7：缺失模态

```text
missing sMRI
missing dMRI
missing fMRI
missing any two modalities
random modality dropout
```

不得只在训练时 dropout、测试时报告一次；需要固定缺失模式逐一评估。

## 14.9 E8：拓扑扰动

- edge deletion；
- edge addition；
- degree-preserving rewiring；
- graph density sensitivity；
- atlas 粒度敏感性。

## 14.10 E9：效率

报告：

- 参数量；
- 单 epoch 时间；
- 推理时间；
- 峰值显存；
- token 数；
- 候选路由数；
- 实际保留路由数；
- dense score 与 sparse candidate 两种实现的差异。

## 14.11 E10：解释稳定性

每条路由记录：

```text
source_modality, source_relation, source_band,
target_modality, target_relation, target_band,
source_shared_prob, target_shared_prob,
attention_weight, band_penalty, qc_penalty
```

稳定性指标：

- top route Jaccard；
- rank correlation；
- 跨 seed 重合率；
- 跨外层折重合率；
- 图扰动前后重合率；
- bootstrap 置信区间。

解释只在稳定时报告；单次 seed 的注意力图不能作为生物学结论。

## 14.12 统计协议

- 主比较：CanoSPAR vs 最强非 CanoSPAR 基线；
- 使用外层测试预测做 subject-level paired bootstrap；
- MAE 比较使用配对误差差值；
- 相关系数使用 Fisher-z 或 bootstrap；
- 主要消融使用配对置换或 bootstrap；
- 多重比较使用 Holm 校正；
- 报告效应量和 95% CI，不只报告 p 值；
- 主表至少 5 seeds；大规模辅助消融可用 3 seeds，但必须注明。

## 14.13 HCP 阶段通过标准

至少同时满足：

1. 完整模型在预注册主指标上优于最强基线，且 95% CI 不跨越无效方向；
2. 规范谱坐标不仅提升任务性能，也改善机制稳定性；
3. 污染增强时 noisy/route 行为符合预期；
4. 缺失模态下性能下降小于 dense fusion；
5. 稀疏路由显著减少通信边；
6. 解释路径在多 seed/折下不是随机的；
7. 所有结论均能通过独立脚本重现。

如果只满足性能提升、其余机制失败，则论文只能定位为普通融合模型，不能保留完整 CanoSPAR 叙事。

---

# 第 38–42 周：按既定决策树完成 PPMI 外部验证

## 15.1 重新生成 PPMI 数据审计

访问获批后，使用真实下载数据重新统计：

- T1、rs-fMRI、DTI 可用性；
- 基线三模态交集；
- 12/24/48 月标签可用性；
- 站点和扫描仪；
- PD、前驱期和 HC；
- MRI 与临床评估间隔；
- 多次访视。

随后严格按照第 2 周冻结的决策树选主任务。

## 15.2 PPMI 预处理

使用与 HCP 相同 atlas 和图合同，但允许原始预处理工具不同：

- BIDS Validator；
- MRIQC；
- fMRIPrep；
- QSIPrep/QSIRecon；
- FreeSurfer；
- 相同的 ROI 定义；
- 相同的图构建公式；
- 记录站点和扫描仪信息。

PPMI 官方 MRI 手册强调纵向、多中心质量一致性，并包含多次 MRI 评估 [R3][R4]。

## 15.3 严格时间和受试者拆分

若预测未来变化：

- 输入只使用基线及其之前信息；
- 标签使用未来固定时间窗；
- 同一受试者不得跨折；
- 同一受试者多个未来访视不能变成多个独立测试样本而忽略相关性；
- 影像和临床日期间隔纳入审计。

## 15.4 多中心处理

主分析优先不在全数据上预先 harmonize。比较：

1. 仅在模型输入中加入 site/scanner embedding；
2. 在训练折拟合 neuroHarmonize/ComBat，再应用到验证/测试 [R20]；
3. 不做 harmonization 的敏感性结果。

任何 harmonization 参数都不得使用外层测试折。

## 15.5 PPMI 实验

### P1：PPMI 从头训练

使用与 HCP 相同的基线和最优 CanoSPAR 配置，小范围重新调参。

### P2：HCP 自监督预训练

仅迁移：

- 图编码器；
- 频带滤波器设置；
- masked modality/token reconstruction 模块。

不迁移 HCP 认知任务头。

比较：

```text
from scratch
HCP pretrained + frozen encoder
HCP pretrained + fine-tuning
```

### P3：缺失模态和质量路由

PPMI 的真实模态缺失和站点差异用于验证：

- availability mask；
- QC-conditioned routing；
- 单模态/双模态/三模态子集；
- 模态质量与 route mass 的关系。

### P4：站点外推

仅当站点样本量足够时做 leave-one-site-out。小站点不得单独作为外部测试并过度解释。

## 15.6 PPMI 指标

回归：

- MAE、RMSE、Pearson/Spearman、\(R^2\)；
- 预测变化与基线严重程度的关系；
- 站点分层误差。

分类：

- AUROC；
- AUPRC；
- balanced accuracy；
- sensitivity/specificity；
- calibration/Brier score；
- 置信区间。

## 15.7 PPMI 通过标准

PPMI 不要求一定显著超过 HCP 上的相对提升幅度，但至少需要：

- 在真实多中心/缺失条件下不出现灾难性失效；
- QC 路由行为与 HCP 污染实验方向一致；
- HCP 预训练或规范谱设置具有可迁移价值，或明确证明不迁移；
- 所有结果按站点、诊断和模态完整性分层报告；
- 若样本量不足，明确降级为压力测试，不硬写临床预测结论。

---

# 第 43–44 周：完成大图近似、复杂度和理论性质验证

## 16.1 实现 SLQ/CDF 近似

对节点数扩展到：

```text
N = 500, 1,000, 5,000, 10,000
```

的稀疏合成图测试：

- 精确谱可计算的小图作为真值；
- SLQ 估计经验谱 CDF；
- 比较 Wasserstein/KS 距离；
- 比较分位边界误差；
- 比较滤波输出误差；
- 记录矩阵—向量乘次数、时间和内存。

参考 SLQ 频谱近似理论与实现 [R13][R14]。

## 16.2 形式化可证明性质

至少写成技术报告并用数值验证：

1. 经验 CDF 映射的单调性；
2. 对严格单调谱重参数化的秩不变性；
3. 等质量频带包含近似相等数量谱模态；
4. Chebyshev 近似误差随阶数和窗口平滑度变化；
5. 节点置换下拉普拉斯滤波的等变性；
6. sparse routing 的通信边上界；
7. 区分 dense scoring 与 sparse candidate 的复杂度。

不得把经验观察写成已证明定理。

## 16.3 通过标准

- SLQ 在可控大图上能近似 CDF 和分位边界；
- 误差—时间曲线完整；
- 主 MRI 结果仍以精确谱为准，避免近似误差混入主结论；
- 复杂度表述与实际实现一致。

---

# 第 45–46 周：最终复现、结果冻结和发布包

## 17.1 从空目录复现

在新的计算环境执行：

```bash
git clone <repo>
make environment
make download-manifests
make preprocess-pilot
make graphs
make baselines
make canospar
make evaluate
```

受限数据无法公开时，提供：

- 数据申请说明；
- manifest schema；
- 样本筛选脚本；
- 文件哈希生成脚本；
- toy/synthetic data；
- 不含个体信息的汇总结果。

## 17.2 冻结结果

```text
reports/final/
├── table_main_hcp.csv
├── table_ablation.csv
├── table_robustness.csv
├── table_efficiency.csv
├── table_ppmi.csv
├── figure_spectral_alignment/
├── figure_corruption_routes/
├── figure_missing_modalities/
├── figure_route_stability/
├── predictions_outer_folds/
├── statistical_tests.json
└── model_cards/
```

## 17.3 最终审计

逐项检查：

- 测试折是否参与任何拟合；
- HCP 正式样本是否全部属于冻结的官方 unrelated 名单，且是否存在受试者跨折或重复记录；
- PPMI 受试者是否跨折；
- harmonization 是否在训练折内；
- 图阈值是否使用测试标签；
- 是否存在最佳 seed 选择；
- 是否只报告有利结果；
- 是否把复现实现误称官方实现；
- 是否把 attention/routing 直接解释成因果机制；
- 是否公开了所有失败和排除原因。

## 17.4 CCF-B 级最终验收清单

### 数据证据

- [ ] HCP 主数据完成官方 unrelated cohort 下的严格受试者级验证，名单来源、版本、哈希和交集筛选过程完整可追踪；
- [ ] PPMI 完成独立受试者、多中心或纵向验证；
- [ ] 两个数据集均有完整 QC 和排除流程。

### 方法证据

- [ ] 规范谱坐标有合成机制实验；
- [ ] 精确谱与 Chebyshev 近似完成验证；
- [ ] Token 不塌缩；
- [ ] shared/private/noisy 行为可被污染实验检验；
- [ ] sparse routing 的实际稀疏性和复杂度准确报告。

### 实验证据

- [ ] 与非图、单模态、普通融合和脑图强基线比较；
- [ ] 与 SMGFM/DiP 等近邻思想进行明确区别和尽可能公平的比较；
- [ ] 主模块均有消融；
- [ ] 有缺失模态、图扰动、模态污染、atlas 和图密度敏感性；
- [ ] 有多 seed、置信区间、效应量和校正后的统计检验。

### 可复现性

- [ ] 容器和依赖锁定；
- [ ] 拆分索引公开或可再生；
- [ ] 配置、日志、预测和路由均保存；
- [ ] 受限原始数据之外的代码和合成数据可运行；
- [ ] 从空目录完成一次独立复现。

只有上述四类证据均基本闭合，项目才达到较可信的 CCF-B 投稿准备度。若只完成 HCP 单数据集的性能提升，应按 CCF-C/应用型工作重新定位，不能用复杂模型结构弥补证据链缺失。

---

# 最终推荐的实验优先级

当算力或时间不足时，按以下顺序保留，后面的可删：

1. HCP 官方 unrelated cohort 数据协议；
2. 非图、单模态和普通多模态强基线；
3. 规范谱坐标的合成机制验证；
4. 精确滤波与 Chebyshev 对照；
5. CanoSPAR 完整模型；
6. 规范坐标、角色、QC 和稀疏路由核心消融；
7. 模态污染与缺失模态；
8. PPMI 外部验证；
9. 解释稳定性；
10. SLQ 大图扩展。

不能删除第 1–8 项后仍声称达到 CCF-B 标准。

---

# 参考论文、官方资料与代码仓库

## 数据与影像处理

- **[R1] HCP-Young Adult 2025 release**
  https://www.humanconnectome.org/study/hcp-young-adult/document/hcp-young-adult-2025-release
- **[R2] HCP S900 Unrelated Subjects CSV**
  https://wiki.humanconnectome.org/docs/S900%20Unrelated%20Subjects%20CSV.html
- **[R3] PPMI MRI Procedure Manual, Final v1.0, 2025**
  https://www.ppmi-info.org/sites/default/files/docs/PPMI_002_MRI_Imaging_Manual_Final_v1.0_20250122_Executed-1.pdf
- **[R4] PPMI data access**
  https://www.ppmi-info.org/access-data-specimens/download-data
- **[R5] BIDS Validator**
  https://github.com/bids-standard/bids-validator
- **[R6] MRIQC**
  https://github.com/nipreps/mriqc
- **[R7] fMRIPrep**
  https://github.com/nipreps/fmriprep
- **[R8] QSIPrep**
  https://github.com/PennLINC/qsiprep
- **[R9] MRtrix3 structural connectome documentation**
  https://github.com/MRtrix3/mrtrix3/blob/master/docs/quantitative_structural_connectivity/structural_connectome.rst

## 图谱、频带与稀疏映射

- **[R10] PyTorch Geometric**
  https://github.com/pyg-team/pytorch_geometric
- **[R11] ChebNetII**
  https://arxiv.org/abs/2202.03580
  https://github.com/ivam-he/ChebNetII
- **[R12] entmax / sparsemax**
  https://github.com/deep-spin/entmax
- **[R13] Analysis of Stochastic Lanczos Quadrature for Spectrum Approximation**
  https://arxiv.org/abs/2105.06595
- **[R14] SLQ reference implementation**
  https://github.com/Shashankaubaru/SLQ

## 脑图基线

- **[R15] IBrainGNN: fMRI + DTI + sMRI**
  https://arxiv.org/abs/2408.14254
  https://github.com/GQ93/IBrainGNN_fMRI_DTI_sMRI
- **[R16] BrainGNN**
  https://github.com/xxlya/BrainGNN_Pytorch
- **[R17] Brain Network Transformer**
  https://arxiv.org/abs/2210.06681
  https://github.com/Wayfear/BrainNetworkTransformer
- **BrainGB benchmark**
  https://arxiv.org/abs/2204.07054
  https://github.com/HennyJie/BrainGB

## 必须正面对比的近邻多模态图方法

- **[R18] SMGFM: Spectral Multimodal Graph Pretraining for Multimodal-Attributed Graphs, 2026**
  https://arxiv.org/abs/2606.12867
- **[R19] DiP: Multimodal Graph Representation Learning with Dynamic Information Pathways, AAAI 2026**
  https://ojs.aaai.org/index.php/AAAI/article/view/38503

## 多中心 harmonization

- **[R20] neuroHarmonize / neuroCombat**
  https://github.com/rpomponio/neuroHarmonize
  https://github.com/Jfortin1/neuroCombat

## HCP 队列、访问与泄漏控制

- **[R21] Rosenblatt et al. Data leakage inflates prediction performance in connectome-based machine learning models. Nature Communications, 2024**
  https://doi.org/10.1038/s41467-024-46150-w
- **[R22] HCP Quick Reference: Open Access vs Restricted Data**
  https://www.humanconnectome.org/study/hcp-young-adult/document/quick-reference-open-access-vs-restricted-data
- **[R23] DataLad HCP Open Access repository（旧 HCP1200/S1200；仅作工程参考）**
  https://github.com/datalad-datasets/human-connectome-project-openaccess
