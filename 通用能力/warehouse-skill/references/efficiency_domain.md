# efficiency_domain — 人审效率域数据仓库参考

> 本文是人审效率域的 knowledge reference。`low-efficiency-strategy-analysis` 只负责低效 reason 分析流程；字段映射、指标口径、数据源、gotchas、fallback 判断统一从本文读取。

## Quick Reference

### Business Context

- **业务域**：人审效率。
- **核心问题**：识别「高完审低打标」的低效送审策略，定位无效占用人审产能的 reason。
- **主要使用者**：人审运营、策略、产运、管理复盘。
- **典型决策**：低效策略告警、周报复盘、策略调优、送审规则收敛、人审产能治理。
- **不负责的问题**：责任人匹配走 `owner-routing`；触达发送走 `anomaly-touch`；事件状态推进走编排层。

### Entity Grain

- **主实体**：`reason`（送审原因 / 送审策略）。
- **模式 A 默认粒度**：`p_date × reason`，最终按 reason 分级。
- **模式 B 默认粒度**：`p_date × 机审一级标签 × reason`。
- **最小可信粒度**：日粒度；跨天必须用动态天数重算日均。
- **去重键**：分级输出按 reason 去重；等级 sheet 不跨级去重，综合 sheet 取最高等级。
- **跨表 join 前提**：必须先确认 join 后不会一对多放大 reason 指标；默认不做外部 join。

### Standard Hygiene Filter

默认样本池圈定「社区人工审核」有效样本，来自 `low-efficiency-strategy-analysis/scripts/sql_templates.py` 的 `_DEFAULT_BASE_FILTER_LOW_LABEL`：

- **A 标题黑名单**：排除虚假、标注、封面、自动处置、演绎、模型、run、质检、QA、测试、大模型、离线等非常规审核项目。
- **B 场景白名单**：`scene IN (community_audit_safe, community_audit_style, community_audit_moderate)`。
- **C reason 排除**：`reason NOT IN (recall_skip_L6, fatal_output)`。
- **D 机审一级标签白名单**：`IS NULL OR IN (...)`，空标签必须显式保留。

自定义样本池只能通过结构化 `ctx.base_filter` 或明确 SQL 片段覆盖，并在 provenance 中说明。

## Semantic Layer Routing

Semantic Layer 是效率域查询默认入口。低效分级规则本身较复杂，当前允许 fallback 到 `low-efficiency-strategy-analysis/scripts/sql_templates.py`，但必须先完成语义层发现并记录 fallback reason。

### Required Semantic Checks

1. 搜索 canonical metrics：打标率、进审量、完审量、打标量、日均进审量、日均完审量、日均打标量。
2. 搜索 dimensions：`reason`、`p_date`、`scene`、`project_title`、`机审一级标签`。
3. 搜索 segments：社区人工审核标准样本池、测试/质检/离线项目排除、机审标签白名单。
4. 检查 metric grain 是否支持 `day × reason` 或 `day × 机审一级标签 × reason`。
5. 若语义层无法表达 notice/P2/P1/P0 多条件分级，fallback 到 curated SQL template，并记录 `fallback_reason=complex_grading_rule_not_covered_by_semantic_layer`。

### Canonical Metrics

| 业务概念 | canonical metric | 分子 | 分母 | 默认 grain | 标准 segment | 状态 |
|---|---|---|---|---|---|---|
| 打标率 | `label_rate` | 打标量 | 完审量 | `day × reason` | `standard_review_scope` | active |
| 进审量 | `review_in_cnt` | - | - | `day × reason` | `standard_review_scope` | active |
| 完审量 | `review_done_cnt` | - | - | `day × reason` | `standard_review_scope` | active |
| 打标量 | `label_cnt` | - | - | `day × reason` | `standard_review_scope` | active |
| 日均进审量 | `avg_daily_review_in_cnt` | `SUM(进审量)` | `COUNT(DISTINCT p_date)` | reason | `standard_review_scope` | derived |
| 日均完审量 | `avg_daily_review_done_cnt` | `SUM(完审量)` | `COUNT(DISTINCT p_date)` | reason | `standard_review_scope` | derived |
| 日均打标量 | `avg_daily_label_cnt` | `SUM(打标量)` | `COUNT(DISTINCT p_date)` | reason | `standard_review_scope` | derived |

### Metric Formulas

```sql
打标率 = if(SUM(完审量) = 0, 0, SUM(打标量) / SUM(完审量))
日均进审量 = SUM(进审量) / COUNT(DISTINCT p_date)
日均完审量 = SUM(完审量) / COUNT(DISTINCT p_date)
日均打标量 = SUM(打标量) / COUNT(DISTINCT p_date)
环比增长率 = (本期日均进审量 - 上期日均进审量) / NULLIF(上期日均进审量, 0)
日均增量 = 本期日均进审量 - 上期日均进审量
```

硬约束：

- 打标率分母是**完审量**，不是进审量。
- 比率跨分区、跨 reason、跨标签聚合时必须用分子/分母重算，不直接 `SUM(rate)`。
- 所有日均都用 `COUNT(DISTINCT p_date)` 动态天数，不硬编码 `/7`。

### Canonical Dimensions

| 业务维度 | semantic dimension | 粒度影响 | 常见别名 | 注意事项 |
|---|---|---|---|---|
| 送审原因 | `reason` | reason 粒度 | 送审原因 / 策略 / 规则 | 当前 SQL 模板默认 Name 是 `reason`；逻辑数据集入口可能需覆盖为中文显示名 |
| 日期分区 | `p_date` | day 粒度 | date / 日期 / dt | 分区日期，不一定是事件发生时间 |
| 机审一级标签 | `mach_root_label_name` | label × reason | 机审根标签名 | 空值必须保留；模式 B 使用 |
| 场景 | `scene` | scene 粒度 | 审核场景 | 默认只保留社区审核三类场景 |
| 项目标题 | `project_title` | project 粒度 | 项目名 | 用于排除测试、质检、离线等项目 |

### Semantic Fallback Decision

| 场景 | 允许 fallback 吗 | fallback 到哪里 | 必须记录 |
|---|---|---|---|
| 只查打标率/完审量/趋势 | 否，优先语义层 | semantic layer | metric、segment、freshness |
| 查 notice/P2/P1/P0 低效分级 | 是 | `sql_templates.py` | `complex_grading_rule_not_covered_by_semantic_layer` |
| 查维度 × reason 明细 | 是 | `dimension_breakdown.md` + `analyze_mach_label.py --dimensions ...` | 维度缺口或模式 B 说明 |
| 语义层权限失败 | 否 | 要求授权 / 转人工 | 权限错误原文 |
| 字段探测 / LIMIT 1 | 是 | raw exploration | 仅用于探测，不可直接出结论 |

## Field Mapping

模板内部使用逻辑字段名，执行时由 `ctx.field_map` 映射到数据集真实 Name。执行权威是 `low-efficiency-strategy-analysis/scripts/sql_templates.py` 的 `_DEFAULT_FIELD_MAP`。

| 概念 | 逻辑字段名 | 默认 Name | 类型 | 说明 |
|---|---|---|---|---|
| 送审策略/原因 | `reason` | `reason` | 维度 | 旧文档可能写“送审原因”；逻辑数据集/显示名入口需通过字段探测确认 |
| 日期分区 | `date` | `p_date` | 分区字段 | 用于 WHERE 和动态天数 |
| 项目标题 | `project_title` | `project_title` | 维度 | 默认过滤黑名单依赖 |
| 审核场景 | `scene` | `scene` | 维度 | 默认场景白名单依赖 |
| 机审一级标签 | `mach_root_label_name` | `机审一级标签` | 维度 | Name 真值是中文；description/UI 可能显示“机审根标签名” |
| 进审量 | `jin_shen` | `进审量_reviewid` | 聚合字段 | 单下划线 |
| 完审量 | `wan_shen` | `完审量_reviewid` | 聚合字段 | 单下划线 |
| 打标量 | `da_biao` | `打标量__reviewid` | 聚合字段 | 双下划线 |
| 打标率 | `ratio` | `打标率__reviewid` | 聚合字段 | 双下划线；低效规则不直接聚合使用 |

### Quote Style

- 默认 `quote_style="bracket"`：字段渲染为 `` `[Name]` ``，即反引号包方括号。
- 物理表 FROM 下，风神服务端会把 `` `[完审量_reviewid]` `` 展开成底层 ClickHouse 聚合表达式。
- 禁止裸 `[Name]`，ClickHouse 会报 `Unrecognized token '['`。
- 禁止纯反引号 `` `Name` `` 误用到逻辑数据集入口，容易报未知表/字段权限。

## Governed Tables

### `olap_content_security_community.dws_sft_tcs_review_task_detail_di`

- **Owner**：待补充效率域数据 owner。
- **Tier**：governed / curated raw SQL fallback。
- **Engine**：ClickHouse。
- **Grain**：经语义字段聚合后支持 `p_date × reason`；模式 B 支持 `p_date × 机审一级标签 × reason`。
- **Freshness**：默认 T+1；每次查询前以 `MAX(p_date)` 和分区行数确认。
- **Partition**：`p_date`。
- **Use for**：低效 reason 分级、打标率趋势、机审一级标签 × reason 维度汇总。
- **Do NOT use for**：人员明细、责任人匹配、触达对象解析、跨应用 open_id/chat_id。
- **Required filters**：默认 `_DEFAULT_BASE_FILTER_LOW_LABEL`；自定义过滤必须写入 methodology 和 provenance。
- **Known caveats**：
  - 语义字段必须用 `` `[Name]` ``；
  - 聚合字段是数据集语义指标，不要二次包 `SUM(`[Name]`)`；
  - 打标率必须用打标量 / 完审量重算；
  - 空机审标签要显式保留。

## Gotchas

| 错误模式 | 为什么错 | 正确做法 |
|---|---|---|
| 取数失败/数据未就绪时判为“无低效策略” | 把系统失败伪装成业务结论 | 停止并报告失败原因，不给分级结论 |
| 数据未就绪/进审量过低仍定 P0/P1 | 极小基数或缺分区会误报 | 就绪 gate 未过直接停；使用进审量守卫 |
| 未预校验就跑全量 SQL | 方言/字段错会浪费资源并污染结果 | 入口 A 用 `query parse`，入口 B 用 `LIMIT 1` 探测 |
| 打标率分母写成进审量 | 会虚低打标率，误判低效 | 分母固定为完审量 |
| 日均硬编码 `/7` | 缺分区时日均被低估 | 用 `COUNT(DISTINCT p_date)` |
| 直接引用或聚合 `打标率__reviewid` | 多分区聚合口径不稳 | 用 `SUM(打标量)/SUM(完审量)` 重算 |
| 同一 reason 多条件命中后再次 SUM 指标 | UNION 命中行重复，指标翻倍 | 条件内指标只取一次；综合层取最高等级 |
| 手改 `sql_templates.py` SQL 骨架凑结果 | 破坏确定性和单测背书 | 只改 `sql_params`；改骨架必须跑单测 |
| 裸 `[Name]` 或纯反引号 `` `Name` `` | ClickHouse / 逻辑集入口会报字段错 | 物理表入口用 `` `[Name]` `` |
| 用逻辑数据集名直接 FROM | 容易未知表/权限错误 | 物理表用 `db.table` 裸写 |
| 打标量字段写成单下划线 | 正确字段是双下划线 | `打标量__reviewid`，不是 `打标量_reviewid` |
| 模式 B 用 `IN (NULL, ...)` 匹配空标签 | SQL 不会命中 NULL | 显式 `(f IS NULL OR f IN (...))` |
| 模式 B 把 `进审量>0` 放 WHERE | 语义聚合字段不能在 WHERE 过滤 | 放 HAVING；日粒度必须 GROUP BY |
| 等级 sheet 跨级去重 | 会丢失每级完整命中结果 | 只有综合 sheet 跨级去重取最高等级 |

## Best Practices / Common Query Patterns

### 低效 reason 分级

- 默认执行 notice / P2 / P1 / P0 四级，不得省级。
- 四个等级 sheet 独立保留完整命中结果。
- 综合 sheet 按 P0 > P1 > P2 > notice 去重取最高等级。
- 每条结果必须带 evidence：日均进审、日均完审、日均打标、打标率、命中条件。

### 趋势分析

- 默认比较本期 vs 上期同长度窗口。
- 优先输出日均量，不直接比较不同长度周期总量。
- 环比用日均比，并加上期日均守卫防除零。

### 机审一级标签维度汇总

- 先按 `p_date × 机审一级标签 × reason` 拉日粒度明细。
- 进审量过滤放 HAVING。
- 空标签统一填“（空/无机审一级标签）”。
- Python 聚合时跨日 SUM 后重算打标率和动态日均。

## Troubleshooting Guide

### When Information Is Missing

| 问题 | 一线处理 | 仍失败时 |
|---|---|---|
| 找不到打标率 metric | 查 `label_rate`、打标率、`打标率__reviewid`、dashboard 字段 | 使用 SQL 模板重算，并记录语义层缺口 |
| 找不到 reason 字段 | 先用默认 Name `reason`；逻辑集入口再试中文显示名 | 用数据集字段探测确认 Name / description |
| 找不到机审标签 | 查 `机审一级标签` 与“机审根标签名” | 模式 B 转人工确认字段 |
| 分区未就绪 | 查 `MAX(p_date)`、分区行数、数据延迟 | 停止，不输出分级结论 |
| 权限不足 | 透出表名、数据集、用途说明 | 转人工授权，不要求用户贴敏感数据 |

### Field Naming Gotchas

| 禁用字段/写法 | 推荐字段/写法 | 说明 |
|---|---|---|
| `打标量_reviewid` | `打标量__reviewid` | 打标量是双下划线 |
| `打标率_reviewid` | `打标率__reviewid` | 打标率是双下划线，但规则中仍应重算 |
| `[Name]` | `` `[Name]` `` | ClickHouse 物理表入口语义字段写法 |
| `SUM(rate)` | `SUM(label_cnt) / SUM(review_done_cnt)` | 比率跨粒度重算 |
| `IN (NULL, ...)` | `field IS NULL OR field IN (...)` | NULL 不能被 IN 命中 |

### Empty Result

空结果只代表“本口径下未命中”，前提是以下检查都通过：

1. 目标分区已就绪；
2. SQL 预校验通过；
3. 标准过滤条件无误；
4. 阈值符合预期；
5. 字段映射与入口一致；
6. 查询不是权限失败或执行失败；
7. 结果与近期 dashboard / 历史趋势没有明显矛盾。

## Cross-References

| 文档 | 何时读取 |
|---|---|
| `../../../效率模块/low-efficiency-strategy-analysis/references/grading_rules.md` | 需要四级分级条件细节 |
| `../../../效率模块/low-efficiency-strategy-analysis/references/dimension_breakdown.md` | 需要模式 B 通用维度拆解 |
| `../../../效率模块/low-efficiency-strategy-analysis/references/analysis_output.md` | 需要五 sheet 输出格式 |

## Maintenance Checklist

- [ ] `sql_templates.py` 默认字段映射变化时，同步更新本文 Field Mapping。
- [ ] 默认样本池 `_DEFAULT_BASE_FILTER_LOW_LABEL` 变化时，同步更新 Standard Hygiene Filter。
- [ ] 新增/废弃指标时，同步更新 Canonical Metrics。
- [ ] 修复线上错例时，补充 Gotchas 与 offline eval。
- [ ] 每次修改分级 SQL 骨架后，必须运行源侧 SQL 模板回归。
