# M2_VALUES_CANDIDATE_V2.2｜第 6 项唯一 canonical 绑定

## 结论与边界

本文件是 `M2_VALUES_CANDIDATE_V2.2` 唯一 canonical 第 6 项绑定。它只绑定已批准的 Truth 等价控制引用，不重做或修改独立 QA 评论 `50cb743c-2919-4115-b78b-1bcd2dc7d546` 已 ACCEPT 的第 1—5、7—8 项，不复制或披露 Truth，不修改 G1-A/G1-B、正式评测数据或标准答案。

当前状态：`PREPARATION_ONLY / NOT_RUN_FORMAL / PENDING_SCOPED_INDEPENDENT_QA`。QA 明确 ACCEPT 且 Owner 完成登记前，M2-PREP-VALUES 未冻结，禁止登记 `M2_VALUES_FROZEN`，禁止启动 M2-FORMAL。

基线固定为仓库 `main`、提交 `c4f0b5bab63572dd0b9722be7aa12293fc3fb2b8`、VALUES V2 评论 `3761887d-22bf-4cb3-895d-40a2af55fa9b`、V2 manifest 附件 `019ffff8-22ec-7476-9546-986d0ef5afc4` / SHA-256 `216e3ceaa655b86c84a9e3957bcdb553b263809b8fa486f451c6b4c6c33ba303`。该 manifest 的 18 个成员哈希原样继承。

## V2.1 失败证据与 supersession 登记

下列两套证据均保留，禁止覆盖或删除；自本文件提交起，两套均为 `SUPERSEDED / NOT_ELIGIBLE_FOR_FREEZE`，不得作为 canonical 输入，也不得单独或组合登记冻结：

| 被取代评论 | 附件 ID | 文件 | SHA-256 | 状态 |
|---|---|---|---|---|
| `d7c218cd-bd6b-4e74-b068-775b5a70a09b` | `01a00000-b6e3-7883-b7a5-0acdda9df4e1` | `m2-values-candidate-v2.1-truth-binding.md` | `b0f0e2c42c83d7b3b4b9ec34e40f6603316ae21c1e8c5c490eb3718865554ffa` | `SUPERSEDED / NOT_ELIGIBLE_FOR_FREEZE` |
| `d7c218cd-bd6b-4e74-b068-775b5a70a09b` | `01a00000-b7d8-7392-93e8-d0fd49ee7209` | `m2-values-snapshot-manifest-v2.1.sha256` | `2d042838f25498196de87b49654a65829ba8c228d68958dfb7c2f68043b088c8` | `SUPERSEDED / NOT_ELIGIBLE_FOR_FREEZE` |
| `c1d0fff2-c03d-413e-81b1-0c7b1ce97624` | `01a00001-42c6-7350-995d-bb7270bcdafb` | `m2-values-candidate-v2.1-item6-truth-binding.md` | `1800d08eca9d6854ae3f466c54ac1a59c1674d7974c11c7ad8b46fe86b64a604` | `SUPERSEDED / NOT_ELIGIBLE_FOR_FREEZE` |
| `c1d0fff2-c03d-413e-81b1-0c7b1ce97624` | `01a00001-43f7-7955-a48c-cec2235f64f2` | `m2-values-candidate-v2.1-binding-manifest.sha256` | `0e069fc10ce47bdcf8a1816846b7c67626947f9b094e221b75527b527b97eb90` | `SUPERSEDED / NOT_ELIGIBLE_FOR_FREEZE` |

退回证据为独立 QA `ee32fecd-f506-4b42-948a-c6ccb4c48154` 及结论回执 `f04cb785-c702-4662-a279-a71055a0fa78`；Owner RETURN 为 `fc6d77c7-648b-4573-b0d6-286947bedd4e`。

## 第 6 项固定绑定

控制来源为 CARB-18 / `f71e163d-d782-4267-9918-08452129992f` 的 `M2_TRUTH_CONTROLS_V1`。交付评论 `9ae980a1-ab2e-45c0-9e0f-b85302dcfa36`；独立安全审计 `7fa69bf1-220f-4ef8-b167-eefa69e0adc2` = `ACCEPT`；Owner 批准 `7779f9ec-aa89-4db0-8eed-9656175896a3`，依据 `DEC-20260814-02`，边界为 `PREPARATION_ONLY_COMPLETE / VIRTUAL_EQUIVALENT_CONTROL / NOT_RUN_FORMAL`。

| 附件 ID | 固定件 | SHA-256 |
|---|---|---|
| `019ffff4-fccc-7ae3-b9d8-6111e1c11aea` | 实施包 | `6efc585d0f0e9941bf4626eb86530616e4183fde0c0bb77b0312c7cfad2a69df` |
| `019ffff4-fdd0-7c6c-847b-f417bbecbcc3` | freeze 记录 | `e737abb5fe437589a07cdf2529a7335b25e8bffbdbd7e6e474a9da0c3084837a` |
| `019ffff4-ff15-7a45-9a0c-6325c1fa470b` | manifest | `e4c25a94a569c35dda10e5f15635cb30c702c453483b0a067893e52acc5e661f` |
| `019ffff5-001b-77cc-9dfb-f03cb5a2f332` | 封包后复验 | `f9028684b30e88fa13fd4445244d6f95fb622be1533667a3153def48f02adbf6` |
| `019ffff5-0143-7552-8d12-ac0346f8a16c` | 命令与退出码 | `f2b37b6a0ba708b57bf19c721a66d2a6b62eeba207e27c3bf01b4e9385d382ce` |
| `019ffff5-025e-763e-a4d8-545f77588f92` | 实施报告 | `9cfed1417178fb76c5bcb21c406d46aeae30211c02c53478a82877f8ef571db5` |
| `019ffff5-0362-7633-ab37-f5725fabdeba` | 哈希表 | `f5c3e5ab024674d40592cbfdc646d55bbca14bcae4a7f4c97164669eae8650c4` |

内部锚点：input-only manifest `7555930b61e6abe01e12da7d34d79e2fb90f9d40c4441132bb44d1508e530ab7`；包级哈希 `60fd37c3eeb5968255751693d31c42af39d88fe5344386e3b25093d99dafde84`；11 事件链头 `891a3006f3ae29be03dcdd6452858766ce4d9b896378a8606fd1c8331d239c36`。这里只登记 opaque 引用、哈希和净化控制结果，不含 Truth 内容。

## 唯一成员闭包、失效、退出码与回滚

V2.2 canonical 闭包严格等于配套 `m2-values-canonical-manifest-v2.2.sha256` 的 19 行：V2 已接受的 18 个成员逐字继承，加本文件 1 个成员。配套 manifest 自身不作为被校验成员。不得加入任一 V2.1 文件、第二份 V2.2 绑定、额外附件或同名不同哈希文件。

以下任一情况自动失效并回到 `WAITING_CANONICAL_BINDING`：19 个成员缺失、增加、重命名或哈希不符；出现第二套 V2.2；任一上述 opaque 引用/附件/哈希/规则/审批链变化或不可回读；审计 ACCEPT 或 Owner 批准撤销；Truth 非零泄露、正式写入、开发侧可读或审计未 fail-closed；范围被外推为真实 IAM/WORM、正式评测或模型准入。

退出码固定为：`0=19/19 完整且审批链一致`；`12=V2/V2.2 manifest 或成员哈希不一致`；`13=权限、角色或路径边界失败`；`14=Truth 交付、审计、Owner 批准或绑定缺失/失效`；`21=输入完整性篡改`；`23=审计链篡改`。任一非零均 fail-closed，禁止读取 Truth、登记冻结或启动 M2-FORMAL。

回滚仅撤销 V2.2 工作副本和任务专用临时校验副本，恢复到未冻结的 V2 基线；必须保留本文件、配套 manifest、两套 V2.1 失败证据及评论历史供审计。禁止删除、覆盖、改写或重新上传 V2/V2.1 与 CARB-18 固定附件。

## 8 项状态与下一步审批请求

| 项 | 状态 | 证据 | 是否阻断 |
|---:|---|---|---|
| 1—5 | `ACCEPT / UNCHANGED` | QA `50cb743c-2919-4115-b78b-1bcd2dc7d546` | 否 |
| 6 | `BOUND_IN_V2.2 / PENDING_SCOPED_INDEPENDENT_QA` | 本文件、配套 manifest、上述 Truth 审计与批准链 | 是 |
| 7—8 | `ACCEPT / UNCHANGED`（第 7 项 `NOT_RUN_ENV` 不是 PASS） | QA `50cb743c-2919-4115-b78b-1bcd2dc7d546` | 否 |

下一步只请求原独立 QA 对 V2.2 的唯一 19 成员闭包、两套 V2.1 supersession、失效条件、退出码和回滚边界作限定复核，并明确 `ACCEPT / RETURN / BLOCKED`。本文件不替代 QA 放行或 Owner 登记，也不授权正式评测、模型准入或护照发布。
