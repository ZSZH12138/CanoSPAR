# CanoSPAR Week 2–4 implementation report

## 1. 最终状态

`PASS`

真实 HCP/PPMI 元数据流程、统一 schema、验证、审计和确定性复跑均已完成。HCP 与 PPMI 科学目标已按用户确认写入配置、生产加载器、聚合审计与 task gate；当前没有未决的 Week 2–4 科学配置。

## 2. 实施范围

已实现第 2–4 周的元数据治理、输入发现与列映射、统一 manifest schema、HCP/PPMI deterministic builders、sequence/scanner batch、候选目标审计、24 月任务门控、validator/audit、fixture workflow、自动验收和汇总报告。

明确未实现第 5 周及以后内容：MRI 下载或预处理、图构建、CanoSPAR 模型、训练、超参数搜索、科学性能评估、站点级实验和容器发布。

## 3. 数据治理结果

- `data/metadata`：由 `data/**` ignore 规则覆盖。
- tracked/staged/history private metadata：`0 / 0 / 0`。
- 凭据指标：未发现。
- 原始 CSV/PDF/JSON：构建前后 1,135 个文件、43,717,086 bytes；按 `sha256(sorted(relative_path|byte_length|file_sha256\n))` 计算的 composite SHA-256 均为 `f94a3b4d1ddc339ce445cf4c5120a032b4086ac1b3f2975a9dc7766067033c62`，逐文件比较零变更。
- 私有 access record：已记录 HCP Open Access approved、Restricted Access not approved；该文件保持 ignored，未暂存。
- 所有 tracked 报告只含聚合统计，不含 participant 标识、行摘录、私有 basename 或机器绝对路径。

## 4. 输入文件复核

完整逻辑源清单见：

- `hcp_source_inventory.json`：9 个 HCP 逻辑输入，逐项记录了脱敏相对位置、大小、SHA-256、快照日期、current/archive 状态和选择依据。
- `ppmi_source_inventory.json`：17 个 PPMI 逻辑输入，逐项记录了同样字段。

HCP 选择依据是受控 download/access record、当前 subject export、official unrelated whitelist、当前 dictionary 与 2025 appendix。历史 completion inventory 只作 aggregate archive evidence；它不能证明 2025 processed package availability，因此 cohort 保持 `provisional`。

PPMI 选择依据是 source manifest、path map 和 current guidance。Archived MRI 仅按 record key 左连接 enrichment，archived-only 记录不追加；旧 dictionary 仅作 archive provenance。

已知缺失/歧义：HCP processed-package inventory 不可用；PPMI site metadata 不可用；PPMI 临床日期仅有 month-year 精度，无法计算精确 imaging-clinical interval days。

## 5. 实现功能

- metadata discovery：配置驱动、hash 校验、current/archive 分离、错误脱敏。
- column mapping：HCP/PPMI 独立映射，PPMI visit 与 sequence aliases 配置化。
- schema：contract `1.1.0` 的 exact canonical manifest。
- HCP builder：official-unrelated 交集、completion-based provisional availability，并写出已确认的 primary/secondary target、regression 与 MAE。
- HCP target audit：三个 Open Access cognition targets 的覆盖、缺失、分布、QC 聚合。
- PPMI builder：current-primary/archive-left-join、subject+visit matching、enrollment cohort。
- sequence classifier：保守分类并排除污染描述。
- scanner batch：vendor/protocol 规范化并生成非站点 scanner batch；`site_id` 保持 `unknown`。
- MDS-UPDRS target audit：dictionary/config 驱动的 candidate A/B、12/24/48 月与三种 Part III policy。
- task gate：按 24 月独立 subject 数执行 120/180 阈值；明确标记 candidate A / `prefer_off` 为主分支，同时保留 candidate B 与两种 sensitivity policy。
- validator/audit：schema、唯一性、日期、状态转换、privacy、provenance、dataset evidence 和 Git governance。
- workflow/tests/docs：fixture Snakemake DAG、Week 2–4 acceptance runner、单元/集成测试和本报告集。

## 6. 生成产物

私有、ignored、可重建产物位于 `artifacts/manifests/week02_04/private/`，包括：

- HCP/PPMI manifest；
- canonical manifest SHA-256；
- provenance；
- audit；
- exclusion ledger；
- manifest validation JSON；
- PPMI target candidate audit 和 task gate；
- 两次独立 builder 输出，用于 byte/hash determinism 比较。

Tracked、聚合-only 产物位于 `reports/data_qc/week02_04/`：preflight、source inventories、HCP/PPMI audits、sequence/target CSV、task gate、validation summary、manual checklist、remaining decisions 和 authoritative acceptance JSON。

## 7. 数据审计结果

### HCP

- input subject：1,206；official-unrelated / manifest subject：339。
- 三模态 provisional：339。
- target coverage：Fluid 1,188（unrelated/trimodal 337）；Total 1,187（337）；Matrix 1,197（338）。
- `QC_Issue` soft-marker：39。
- exclusion：867 个输入不在 official unrelated whitelist；manifest 内 exclusion `none=339`。
- cohort：`provisional`；processed-package inventory `not_available`。

### PPMI

- 独立 subject：6,101；subject-visit：12,419；distinct visit code：22。
- 同访视可用：T1 1,830；fMRI 862；DWI 1,777；三模态交集 366。
- visit distribution：BL 5,042；SC 1,936；V04 1,980；V06 2,228；V10 745；其余 18 个 visit code 合计 488。
- enrollment cohort：Healthy Control 522；Parkinson's Disease 4,104；Prodromal 7,668；SWEDD 125。
- scanner vendor：GE 488；Philips 351；Siemens 1,760；unknown 9,820。field strength 可用数 0。protocol/scanner batch 非空 2,627，182 个聚合类别，最大类别 308。
- target coverage（基线三模态 + 完整目标独立 subject）：
  - candidate A：baseline `343/348/352`，12 月 `232/269/285`，24 月 `179/151/154`，48 月 `45/82/85`，顺序为 `unique_only/prefer_off/prefer_on`；
  - candidate B：baseline `339/344/348`，12 月 `226/263/279`，24 月 `177/149/153`，48 月 `45/81/84`。
- Part III duplicate subject-visit groups：6,819；preference ambiguous groups：9（prefer_off 8，prefer_on 1）。
- 24 月 task gate：六个分支均为 149–179，全部建议 shorter window；主分支 candidate A / `prefer_off` 为 151，配置状态为 `READY_FOR_USER_SELECTED_TASK`，`final_task_selected=true`。
- site metadata：`unavailable_in_current_ppmi_export`；12,419 行均为 `site_id=unknown`。
- 日期限制：146,509 个临床日期值全部为 month-year；exact imaging-clinical day interval 为 unavailable。

## 8. 测试证据

真实元数据命令：

| command | exit_code | passed | failed | skipped | coverage |
|---|---:|---:|---:|---:|---:|
| HCP discovery dry/full | 0 / 0 | 2 steps | 0 | 0 | n/a |
| PPMI discovery dry/full | 0 / 0 | 2 steps | 0 | 0 | n/a |
| HCP builder dry/full | 0 / 0 | 2 steps | 0 | 0 | n/a |
| PPMI builder dry/full | 0 / 0 | 2 steps | 0 | 0 | n/a |
| HCP validator + audit | 0 / 0 | 2 steps | 0 | 0 | n/a |
| PPMI validator + audit/target gate | 0 / 0 | 2 steps | 0 | 0 | n/a |
| HCP/PPMI builder deterministic rerun | 0 / 0 | 2 byte-identical manifests | 0 | 0 | n/a |

完整工程验收（最终 release authoritative run；以当前
`verification_results.json` 为准）：

| command/check | exit_code | passed | failed | skipped | coverage |
|---|---:|---:|---:|---:|---:|
| fixture pipeline | 0 | 0 | 0 | 0 | n/a |
| fixture determinism | 0 | 5 | 0 | 0 | n/a |
| dataset contract tests | 0 | 66 | 0 | 0 | n/a |
| unit tests | 0 | 321 | 0 | 0 | n/a |
| integration tests | 0 | 8 | 0 | 0 | n/a |
| all tests + coverage | 0 | 329 | 0 | 0 | 85.0% |
| ruff check | 0 | 0 | 0 | 0 | n/a |
| ruff format check | 0 | 0 | 0 | 0 | n/a |
| mypy | 0 | 0 | 0 | 0 | n/a |
| Week 1 acceptance | 0 | 0 | 0 | 0 | n/a |
| Snakemake dry-run | 0 | 0 | 0 | 0 | n/a |
| build | 0 | 0 | 0 | 0 | n/a |

`verification_results.json` 总结：12 PASS、0 FAIL、0 skipped，overall `PASS`。

第一次 finalization 验收曾出现 4 个 FAIL，根因是 synthetic fixture 的
PPMI target YAML 仍保留旧 `confirmed:false` 契约；同步 HCP/PPMI fixture
YAML 并增加端到端选择断言后，fixture integration `5 passed`，随后上述
authoritative run 全部通过。该失败只属于 historical intermediate run，
已被当前 PASS 结果取代。

## 9. 算力判断

```text
本阶段是否可在日常电脑完成：是（用户已豁免低可用内存阻断）
是否使用 GPU：否
是否需要服务器：否
输入总量：43,719,269 bytes（全部 metadata 文档）；其中完整性快照 CSV/PDF/JSON 为 43,717,086 bytes
峰值内存：未仪器化测量
最长单步耗时：255.723 秒（Week 1 acceptance）
```

## 10. 修改文件

Create：本次科学配置收尾没有新增 tracked 顶层产物；继续使用既有
`reports/data_qc/week02_04/` 报告集。

Modify：HCP/PPMI 生产与 synthetic YAML、目标审计/加载/导出代码、单元与
integration 测试、fixture 聚合产物、README、Task 3–6 ledger、最终实施与
verification reports。

Delete：无；未删除或改写 Week 1 tracked 文件。

科学配置收尾的提交分为：

```text
498ee90 feat: confirm week2-4 scientific targets
<final report-only commit> docs/fixtures/reports and authoritative verification
```

私有 artifacts 和 ignored access record 不进入该 diff。

## 11. 人工核对步骤

18 项可复制核对命令、路径、预期结果和失败含义见 `MANUAL_VERIFICATION_CHECKLIST.md`。

## 12. 科学配置与非阻断限制

- HCP：`CogFluidComp_Unadj` primary；`CogTotalComp_Unadj` 与
  `PMAT24_A_CR` secondary；task 为 regression；primary metric 为 MAE。
- PPMI：candidate A primary，定义为 MDS-UPDRS Part III follow-up minus
  baseline；candidate B secondary/sensitivity；`prefer_off` primary；
  `unique_only` 与 `prefer_on` sensitivity。

没有未决的 Week 2–4 科学选择。HCP Restricted Access 未获批且未使用；PPMI
主分支 24 月样本为 151，仍建议 shorter window；临床日期仅 month-year。
这些是科学/数据限制，不是工程 WARN 或 FAIL。详见 `NEEDS_USER_ACTION.md`。

## 13. Commit 清单

| Commit | Message | 职责 |
|---|---|---|
| `3a77114` | feat: add metadata governance foundations | governance/preflight |
| `99a6cb7` | fix: harden metadata governance discovery | governance hardening |
| `03017a0`–`f53792c` | HCP config/discovery/schema fixes | HCP input contract |
| `cbdf639`–`7cb9007` | HCP builder and audit implementation/fixes | HCP M0 |
| `fe19d7d`–`24abb4f` | PPMI imaging builder and audit implementation/fixes | PPMI imaging M0 |
| `cf22ce6`–`d145da4` | PPMI discovery/current/archive/visit contract | PPMI input contract |
| `0644388`–`ff31fbb` | PPMI target candidates and task gate | PPMI targets |
| `9aee385`–`6e60707` | validators, audits, fixture workflow and acceptance hardening | integration/acceptance |
| `498ee90` | feat: confirm week2-4 scientific targets | confirmed targets, production contracts and tests |

The final report-only commit is intentionally not self-referential; use
`git log --oneline` for its final hash.
