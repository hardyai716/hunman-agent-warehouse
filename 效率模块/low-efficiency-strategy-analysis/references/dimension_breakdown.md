# dimension_breakdown — 通用维度拆解模式

本文是模式 B `dimension_breakdown` 的执行说明，与四级分级模式 [`grading_rules.md`](grading_rules.md) 并列。它用于把低效 reason 按一个或多个维度拆开，产出 `dimensions × reason` 明细和 `dimensions` 汇总。

字段映射、指标口径、样本池和 ClickHouse 注意事项以 [`../../../通用能力/warehouse-skill/references/efficiency_domain.md`](../../../通用能力/warehouse-skill/references/efficiency_domain.md) 为准，本文只描述维度拆解流程。

## 何时使用

| 用户诉求 | 使用模式 |
|---|---|
| 要 notice/P2/P1/P0 分级 | 模式 A：grading |
| 要按机审一级标签、场景、项目或多个维度组合看低效 reason | 模式 B：dimension_breakdown |
| 只说“低效 reason 列表”，未要求维度或分级 | 默认模式 A；用户补充维度后切模式 B |

## 维度参数

脚本通过 `--dimensions` 接收一个或多个 CSV 维度列名：

```bash
python3 analyze_mach_label.py \
  --input output/reason_dimension_daily.csv \
  --dimensions mach_label scene \
  --threshold 0.1
```

也支持逗号分隔：

```bash
python3 analyze_mach_label.py --input input.csv --dimensions mach_label,scene
```

兼容说明：

- `mach_label` 是历史脚本使用的 CSV 列名，继续支持；
- `mach_root_label_name` 是效率域逻辑字段名，等价于机审一级标签；
- 当输入 CSV 仍使用旧列 `mach_label` 时，`--dimensions mach_root_label_name` 会自动兼容到该列；
- 概念上本模式是通用 `dimension_breakdown`，不是机审标签专用模式。

## 日粒度取数

模式 B 先拉 `day × dimensions × reason` 日粒度明细，再交给 Python 聚合。SQL 结构如下，`{dimension_select}` 与 `{dimension_group_by}` 由选择的维度生成：

```sql
SELECT `[p_date]`            AS dt,
       {dimension_select}
       `[reason]`            AS reason,
       `[进审量_reviewid]`    AS review_in,
       `[完审量_reviewid]`    AS review_done,
       `[打标量__reviewid]`   AS labeled
FROM olap_content_security_community.dws_sft_tcs_review_task_detail_di
WHERE `[p_date]` >= '{start_date}' AND `[p_date]` <= '{end_date}'
  {base_filter}
GROUP BY `[p_date]`, {dimension_group_by}, `[reason]`
HAVING `[进审量_reviewid]` > 0
```

要求：

- 维度列必须来自效率域已允许字段或已完成字段探测的治理字段；
- 输出 CSV 必须包含 `dt, reason, review_in, review_done, labeled` 和所有 `--dimensions` 指定列；
- `review_in > 0` 属于聚合后的有效性过滤，放在 `HAVING`；
- `mach_root_label_name` 对应数据集 Name `机审一级标签`，SQL 中可 alias 为 `mach_label` 以兼容历史脚本；
- NULL 维度值不丢弃，聚合输出填充为 `（空/<维度名>）`。

示例：按机审一级标签拆解时，维度片段为：

```sql
`[机审一级标签]` AS mach_label,
```

示例：按机审一级标签 + 场景组合拆解时，维度片段为：

```sql
`[机审一级标签]` AS mach_label,
`[scene]` AS scene,
```

## Python 聚合

输入 CSV 交给兼容脚本：

```bash
cd scripts && python3 analyze_mach_label.py \
  --input output/reason_dimension_daily.csv \
  --dimensions mach_label \
  --threshold 0.1 \
  --sheet1 output/sheet1_dimension_reason_detail.csv \
  --sheet2 output/sheet2_dimension_summary.csv
```

聚合逻辑：

- `dimensions × reason` 分组跨日 SUM；
- `dimensions` 分组跨日 SUM；
- 打标率基于 `SUM(labeled) / SUM(review_done)` 重算；
- 日均量使用该组合实际有数据天数；
- 低效明细筛选 `label_rate < threshold`；
- 汇总表保留全量维度组合，不只保留低效项。

输出表：

| 表 | 粒度 | 说明 |
|---|---|---|
| Sheet1 / CSV1 | `dimensions × reason` | 低效明细，按日均进审量降序 |
| Sheet2 / CSV2 | `dimensions` | 全量维度汇总，含覆盖 reason 数和整体打标率 |

## 复用 base_filter

默认样本池过滤由 `scripts/sql_templates.py` 的 `_DEFAULT_BASE_FILTER_LOW_LABEL` 维护。模式 B 只复用 A-D 样本池过滤，`review_in > 0` 单独放 `HAVING`：

```bash
cd scripts && python3 -c "
import sql_templates as t
frag = t._build_base_filter(t._DEFAULT_BASE_FILTER_LOW_LABEL, dict(t._DEFAULT_FIELD_MAP), 'bracket')
print(frag)
"
```

## 失败处理

| 触发条件 | 处理 |
|---|---|
| 指定维度列不在 CSV 中 | 停止并提示补齐日粒度取数字段 |
| `mach_root_label_name` 输入但 CSV 只有 `mach_label` | 自动兼容到 `mach_label` |
| NULL 维度行消失 | 检查 SQL 是否误用了 `IN (NULL, ...)`，必须显式 `IS NULL` |
| 打标率异常 | 核对分母是否为完审量 `review_done` |
| 明细行数过大 | 缩短周期、增加维度过滤或分批拉取后合并 |
