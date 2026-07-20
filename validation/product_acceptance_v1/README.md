# 产品验收数据集 V1

这组文件只用于本地产品验收，全部来自固定种子的合成工厂场景，不代表真实客户、法定核查或监管申报。

## 数据来源

- `01_complete_electricity_bill.csv`：由 `syn_candidate_1001_complete` 的装置、期间和外购电真值合并为产品可上传格式。
- `02_missing_electricity_quantity.csv`：同一结构中故意删除用电量，用来验证正式写入失败关闭。
- `03_production_report.csv`：由 `syn_candidate_1001_complete` 的产量真值整理，用来验证生产报表不会误写入电费 ActivityData。
- `04_user_walkthrough_electricity_bill.csv`：由 `syn_candidate_1006_complete` 真值整理，保留给用户亲自走一遍流程；自动验收不上传此文件。

## 预期结果

| 文件 | 文档识别 | 用户动作 | 预期系统结果 |
|---|---|---|---|
| 01 | electricity_bill | 确认写入 | 精确保留 3,529,181 kWh；无已批准因子时停在 `pending_factor` |
| 02 | electricity_bill | 尝试确认 | 400：缺少可写入的用电量字段 |
| 03 | production_report | 尝试确认 | 400：不得写入电费活动账本，应进入护照产量步骤 |
| 04 | electricity_bill | 用户手工确认 | 精确保留 2,176,841.7 kWh；显示人工确认来源 |

百分比字段目前表示“识别字段覆盖度”，不代表事实正确率。所有候选数据必须经过人工核对后才能进入正式账本。
