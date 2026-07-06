# lark_report_card_templates — 飞书报告卡片模板

本文沉淀人审监控结果推送到飞书时的统一卡片形态。目标是让不同业务模块产出的报告在飞书里保持一致：先看关键指标，再看 TopN 明细，完整数据跳转到飞书电子表格。

## 统一发布入口

所有报告推送优先走统一入口，不再为单个报告临时写脚本：

```bash
python3 通用能力/anomaly-touch/scripts/publish_lark_report.py \
  --run-dir dist/analysis_results/<run> \
  --report-type low_efficiency_dimension_breakdown \
  --target-user ou_xxx \
  --identity bot
```

支持的 `report_type`：

| report_type | 用途 | 必要产物 |
|---|---|---|
| `low_efficiency_dimension_breakdown` | 维度 × reason 低效拆解 | `summary.json`、`sheet1_mach_label_reason_detail.csv`、`sheet2_mach_label_summary.csv`、xlsx |
| `low_efficiency_grading` | 单 reason 全等级汇总 | `summary.json`、`综合.csv`、xlsx |
| `low_efficiency_level_detail` | 单独发送 P0/P1/P2/notice 某一等级 | `summary.json`、`<level>.csv`、xlsx；同时传 `--level P0` |

默认行为：

- 若未传 `--sheet-url`，自动导入 xlsx 为飞书电子表格；
- 若传 `--sheet-url`，复用已有电子表格；
- 发送版卡片会剥离 `_meta` 内部字段；
- 审计版卡片保留 `_meta._data_hash`，用于发送前校验；
- 发送命令统一带 idempotency key，key 仅保留字母、数字、短横线，长度控制在 50 字符以内；
- 用户身份缺少 `im:message.send_as_user` 时，可回退 bot 身份发送。

## 模板：low_efficiency_dimension_report

适用场景：

- 低效 reason 维度拆解报告；
- `机审一级标签 × reason` 打标率低效结果；
- 任何 `dimensions × reason` 的 TopN 数据报告。

模板文件：

- [`../templates/low_efficiency_dimension_report.card_template.json`](../templates/low_efficiency_dimension_report.card_template.json)

兼容渲染脚本：

```bash
python3 通用能力/anomaly-touch/scripts/render_lark_report_card.py \
  --summary dist/analysis_results/<run>/summary.json \
  --detail-csv dist/analysis_results/<run>/sheet1_mach_label_reason_detail.csv \
  --dimension-summary-csv dist/analysis_results/<run>/sheet2_mach_label_summary.csv \
  --sheet-url "https://bytedance.larkoffice.com/sheets/<token>" \
  --output dist/analysis_results/<run>/lark_report_card.json \
  --meta-output dist/analysis_results/<run>/lark_report_card.with_meta.json
```

> 新流程优先使用 `publish_lark_report.py`；该脚本保留为维度拆解报告的兼容入口。

## 模板：low_efficiency_grading_report

适用场景：

- 单 reason 全等级结果；
- 展示 P0/P1/P2/notice 数量和综合 TopN；
- 一张卡片总览本轮低效 reason 等级分布。

模板文件：

- [`../templates/low_efficiency_grading_report.card_template.json`](../templates/low_efficiency_grading_report.card_template.json)

示例：

```bash
python3 通用能力/anomaly-touch/scripts/publish_lark_report.py \
  --run-dir dist/analysis_results/low_efficiency_20260706_145041 \
  --report-type low_efficiency_grading \
  --sheet-url "https://bytedance.larkoffice.com/sheets/<token>" \
  --target-user ou_xxx \
  --identity bot
```

## 模板：low_efficiency_level_detail

适用场景：

- 单独发送 P0/P1/P2/notice 某一等级；
- 面向责任人做等级专项排查；
- 同一个完整飞书电子表格下派发多个等级卡片。

模板文件：

- [`../templates/low_efficiency_level_detail.card_template.json`](../templates/low_efficiency_level_detail.card_template.json)

示例：

```bash
python3 通用能力/anomaly-touch/scripts/publish_lark_report.py \
  --run-dir dist/analysis_results/low_efficiency_20260706_145041 \
  --report-type low_efficiency_level_detail \
  --level P0 \
  --sheet-url "https://bytedance.larkoffice.com/sheets/<token>" \
  --target-user ou_xxx \
  --identity bot
```

## 飞书卡片搭建工具版本

飞书卡片搭建工具地址：

```text
https://open.feishu.cn/cardkit
```

推荐搭建结构：

1. Header：标题、周期、阈值标签；
2. 指标区：4 个指标卡；
3. 图表区：维度汇总 TopN 横向条形图；
4. TopN 明细区：
   - 搭建工具内优先使用「循环容器」绑定 `top_items`；
   - 每个循环项展示 `rank / dimension / reason / avg_in / label_rate_pct`；
5. 操作区：按钮跳转 `sheet_url`；
6. 口径区：默认折叠，展示数据集、窗口、计算口径和 fallback reason。

变量契约见模板文件中的 `template_variables`。发布为卡片模板后，发送时通过 `template_variable` 传入实际数据。

## 手写 Card 2.0 发送版本

当前 `lark-cli im +messages-send --msg-type interactive` 直接发送 JSON 时，不能使用卡片搭建工具专属的「循环容器」。因此手写发送版本使用 Card 2.0 的 `table` 组件替代循环容器：

- `column_set`：核心指标；
- `chart`：维度汇总 TopN；
- `table`：TopN 明细；
- `button(open_url)`：跳转完整飞书电子表格；
- `collapsible_panel`：口径与溯源。

发送前应使用 `--meta-output` 的审计版卡片做哈希校验，通过后发送 `--output` 的发送版 JSON。发送版 JSON 会剥离 `_meta` 等内部字段，避免内部审计字段进入飞书客户端。

## 设计规则

- 卡片只展示 TopN，不展示全量明细；
- 完整数据必须落到飞书电子表格，用按钮跳转；
- 打标率口径必须显式写明：`SUM(打标量) / SUM(完审量)`；
- 表格内 reason 可能很长，卡片仅承载定位和优先级，深挖在电子表格里完成；
- 数据报告使用蓝色主色；告警升级版本才使用红色主色，避免同卡多主色导致噪声。
- Card 2.0 `table.columns[].width` 不得小于 `80px`，否则飞书服务端会报卡片创建失败。
- `lark-cli im +messages-send --idempotency-key` 过长或含不稳定字符时，飞书可能只返回 `field validation failed`；发布层必须先做 key 安全化。
