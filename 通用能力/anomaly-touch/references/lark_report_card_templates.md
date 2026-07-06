# lark_report_card_templates — 飞书报告卡片模板

本文沉淀人审监控结果推送到飞书时的统一卡片形态。目标是让不同业务模块产出的报告在飞书里保持一致：先看关键指标，再看 TopN 明细，完整数据跳转到飞书电子表格。

## 模板：low_efficiency_dimension_report

适用场景：

- 低效 reason 维度拆解报告；
- `机审一级标签 × reason` 打标率低效结果；
- 任何 `dimensions × reason` 的 TopN 数据报告。

模板文件：

- [`../templates/low_efficiency_dimension_report.card_template.json`](../templates/low_efficiency_dimension_report.card_template.json)

渲染脚本：

```bash
python3 通用能力/anomaly-touch/scripts/render_lark_report_card.py \
  --summary dist/analysis_results/<run>/summary.json \
  --detail-csv dist/analysis_results/<run>/sheet1_mach_label_reason_detail.csv \
  --dimension-summary-csv dist/analysis_results/<run>/sheet2_mach_label_summary.csv \
  --sheet-url "https://bytedance.larkoffice.com/sheets/<token>" \
  --output dist/analysis_results/<run>/lark_report_card.json \
  --meta-output dist/analysis_results/<run>/lark_report_card.with_meta.json
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
