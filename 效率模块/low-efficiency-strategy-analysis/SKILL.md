---
name: low-efficiency-strategy-analysis
description: 人审效率模块·低效 reason 分析流程。Invoke when user asks for high-volume low-label-rate reason detection, P0/P1/P2/notice grading, or dimension × reason efficiency breakdown.
metadata:
  version: "1.4.0"
  author: 李中涛
  status: beta
  tags: [人审效率, 低效策略, 打标率, 高完审低打标, 分级分析, 维度拆解]
  requires:
    bins: ["bytedcli", "python3"]
    siblings: ["warehouse-skill"]
  requires_optional:
    - "bytedance-aeolus / aeolus-query / aeolus_sql_query 等平台内置风神查数技能：当 runtime 无 bytedcli aeolus sibling（如 IDA）时的同源替代"
    - "sqless-data-analysis：仅当数据源不在风神（RDS/API/跨源）时的自然语言取数兜底"
  requires_note: "本 Skill 是效率域 process skill；字段映射、指标口径、gotchas、样本池以 ../../通用能力/warehouse-skill/references/efficiency_domain.md 为 source of truth。"
---

# 人审低效策略分析

本 Skill 只负责编排低效策略分析流程：选择模式、解析周期、执行确定性脚本、汇总输出。字段映射、指标口径、样本池、ClickHouse gotchas 不在本文重复维护，统一引用效率域 source of truth。

## 必读引用

- 效率域口径与字段映射：[`../../通用能力/warehouse-skill/references/efficiency_domain.md`](../../通用能力/warehouse-skill/references/efficiency_domain.md)
- 仓库通用查询规则：[`../../通用能力/warehouse-skill/SKILL.md`](../../通用能力/warehouse-skill/SKILL.md)
- 模式 A 分级规则：[`references/grading_rules.md`](references/grading_rules.md)
- 模式 B 维度拆解：[`references/dimension_breakdown.md`](references/dimension_breakdown.md)
- 报告输出契约：[`references/analysis_output.md`](references/analysis_output.md)

## 触发场景

当用户询问以下内容时使用本 Skill：

- 近 N 天或指定周期内有哪些高完审、低打标 reason；
- 低效策略分级，或是否有 P0/P1/P2/notice；
- 某些 reason 是否打标率低且占用大量人审；
- 按某个维度或多个维度拆解低效 reason，例如机审一级标签、场景、项目等。

若用户只问普通完审量、打标率、趋势，不要求低效分级或维度拆解，优先按 `warehouse-skill` 的 Semantic Layer first 查询。

## 模式选择

| 模式 | 何时使用 | 主要产出 | 入口 |
|---|---|---|---|
| A · grading（默认） | 用户要 notice/P2/P1/P0 分级、低效策略清单、近 N 天低效 reason | 四级命中 sheet + 综合去重 sheet | `scripts/sql_templates.py` + `references/grading_rules.md` |
| B · dimension_breakdown | 用户要按一个或多个维度拆解低效 reason，或明确提到标签/场景/项目维度 | `dimensions × reason` 低效明细 + `dimensions` 汇总 | `references/dimension_breakdown.md` + `scripts/analyze_mach_label.py --dimensions ...` |

两种模式共用效率域口径：打标率 = 打标量 / 完审量，日均 = SUM(metric) / 实际有数据天数。模式 A 用 SQL 模板判定等级；模式 B 先拉日粒度明细，再在 Python 中跨日聚合并重算指标。

## 通用执行步骤

### 0. Semantic Layer 发现与 fallback 判定

先按 `warehouse-skill` 规则发现 canonical metrics、dimensions、segment 与 freshness。仅当语义层无法覆盖以下复杂逻辑时 fallback 到本 Skill：

- `complex_grading_rule_not_covered_by_semantic_layer`
- `dimension_reason_breakdown_requires_curated_sql`
- `semantic_dimension_missing_but_governed_table_available`

必须在报告中记录 fallback reason。

### 1. 解析周期窗口

输入支持：

- `period`：如「近7天」「近14天」；
- `period_start` / `period_end`：显式周期；
- `run_date`：基准日，默认当前日期；
- `data_lag_days`：数据延迟天数，默认 1；
- `levels`：模式 A 等级子集，默认全跑 `notice/P2/P1/P0`；
- `dimensions`：模式 B 维度列，默认兼容 `mach_label`。

近 N 天默认以 `run_date - data_lag_days` 为最新可取分区。显式周期优先，不再按 lag 推算。

### 2. 数据就绪 gate

探测目标分区及规则所需历史窗口是否存在且可查询。若数据未就绪、权限不足或查询失败，停止本轮，不输出“无低效策略”或任何分级结论。

### 3. 按模式执行

#### 模式 A：grading

1. 读取 [`references/grading_rules.md`](references/grading_rules.md) 确认等级条件。
2. 对每个等级调用 `scripts/sql_templates.py`：
   - `validate_params(sql_key, params, ctx)`
   - `render_sql(sql_key, params, ctx)`
3. 预校验 SQL 后执行取数。
4. 四个等级 sheet 保留各自完整命中结果，不跨级去重。
5. 综合 sheet 按 `P0 > P1 > P2 > notice` 对同一 reason 取最高等级。
6. 按 [`references/analysis_output.md`](references/analysis_output.md) 输出同一个工作簿的五个 sheet。

默认必须全跑 `notice/P2/P1/P0`。只有用户明确说“只看 P0”“只跑 notice”等，才执行子集。

#### 模式 B：dimension_breakdown

1. 按 [`references/dimension_breakdown.md`](references/dimension_breakdown.md) 构造日粒度 SQL，粒度为 `day × dimensions × reason`。
2. 指标列保持为 `review_in,review_done,labeled`，维度列按 `--dimensions` 指定。
3. 执行 `scripts/analyze_mach_label.py` 跨日 SUM、重算打标率、计算动态日均。
4. 输出两张 CSV 或工作簿 sheet：
   - `dimensions × reason` 低效明细；
   - `dimensions` 全量汇总。

`mach_label` 单维度为兼容入口；新需求应优先使用通用 `--dimensions` 参数。

## 脚本入口

| 脚本 | 职责 |
|---|---|
| [`scripts/sql_templates.py`](scripts/sql_templates.py) | 模式 A 四级分级 SQL 模板、参数校验和渲染。 |
| [`scripts/analyze_mach_label.py`](scripts/analyze_mach_label.py) | 模式 B 通用维度拆解聚合脚本。保留旧文件名，CLI 支持 `--dimensions`。 |

## 输出与停止规则

- 每条结论必须带真实 evidence：日均进审、日均完审、日均打标、打标率、命中条件或维度上下文。
- 查询失败、权限失败、数据未就绪时停止，不把失败解释成 0 命中。
- 模式 A 的最终报告遵循一个文件五个 sheet：`notice` / `P2` / `P1` / `P0` / `综合`。
- 模式 B 的最终报告遵循两张表：`dimensions × reason` 明细 + `dimensions` 汇总。
- 分析结果交付到分级/汇总清单为止，后续运营流转、触达、工单不属于本 Skill。
