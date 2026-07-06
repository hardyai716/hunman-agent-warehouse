# [业务域名称] 数据仓库参考文档模板

> 复制本模板为 `references/[domain]_domain.md` 后再填写。本文档面向 LLM 检索和执行，不是给人看的长篇说明书；每个条目都要能帮助 Agent 做出路由、口径、字段、fallback 或停止判断。

## Quick Reference

### Business Context

- **业务域**：[效率 / 质量 / 成本 / 产能 / 体验 / 其他]
- **业务问题**：[该域主要回答什么问题，例如低效策略识别、质检通过率、审核成本趋势]
- **主要使用者**：[运营 / 产运 / 策略 / 管理层 / 数据同学]
- **典型决策**：[用于告警、周报、复盘、策略下线、资源调度等]
- **不负责的问题**：[相邻但不属于本域的问题，路由到哪个 domain]

### Entity Grain

- **主实体**：[reason / review_id / task_id / operator / queue / business_line / label / policy_id]
- **默认分析粒度**：[day × reason / day × team / task × reviewer]
- **最小可信粒度**：[低于该粒度会重复计数或口径失真]
- **去重键**：[review_id / task_id / item_id / reason + p_date]
- **跨表 join 前提**：[join key、时间对齐、是否一对多]

### Standard Hygiene Filter

每次查询默认应用，除非用户明确要求或本域 owner 允许排除：

```sql
-- 示例，占位后替换
p_date BETWEEN '${start_date}' AND '${end_date}'
AND [业务线字段] IN (...)
AND [是否测试数据] = 0
AND [是否作弊/无效样本] = 0
```

- **必须过滤**：[测试数据、无效状态、灰度实验、低置信样本等]
- **可选过滤**：[业务线、审核场景、地域、策略类型]
- **禁止过滤**：[会改变 canonical 口径的字段]

## Semantic Layer Routing

Semantic Layer 是本业务域的默认入口。只有本节明确无覆盖时，才允许进入 `Governed Tables` 或 raw SQL。

### Required Semantic Checks

1. 搜索本域 metric：中文名、英文名、历史别名、缩写。
2. 搜索本域 dimension：业务线、场景、reason、标签、队列、人员等。
3. 搜索本域 segment：标准人群、标准过滤条件、排除规则。
4. 检查 metric 的 grain、owner、freshness、deprecated 状态。
5. 编译 semantic spec；失败时记录错误，不直接改写成 raw SQL。

### Canonical Metrics

| 业务概念 | canonical metric | 语义层 ID / 数据集 | 分子 | 分母 | 默认 grain | 标准 segment | owner | 状态 |
|---|---|---|---|---|---|---|---|---|
| [打标率] | [label_rate] | [metric_id] | [打标量] | [完审量] | [day × reason] | [standard_review_scope] | [owner] | active |
| [完审量] | [review_done_cnt] | [metric_id] | - | - | [day × reason] | [standard_review_scope] | [owner] | active |

### Canonical Dimensions

| 业务维度 | semantic dimension | 字段/ID | 粒度影响 | 常见别名 | 注意事项 |
|---|---|---|---|---|---|
| [送审原因] | [reason] | [dim_reason] | reason 粒度 | reason / 策略 / 规则 | 注意历史名称映射 |
| [机审一级标签] | [mach_root_label] | [dim_label] | label × reason | 机审根标签名 | 空值需显式保留 |

### Canonical Segments

| segment | 定义 | 适用场景 | 禁止手写原因 |
|---|---|---|---|
| [standard_review_scope] | [标准人审样本] | 默认所有人审指标 | 过滤条件多且会随业务变化 |
| [exclude_test_data] | [排除测试/演练样本] | 默认所有查询 | 防止报表和临时查询不一致 |

### Semantic Fallback Decision

| 场景 | 允许 fallback 吗 | fallback 到哪里 | 必须记录 |
|---|---|---|---|
| metric 不存在 | 是 | Governed Table | searched keywords、无覆盖结论 |
| metric 存在但缺维度 | 是 | Governed Table 或补充维表 | 缺失维度、owner |
| compile 权限失败 | 否 | 要求授权 / 转人工 | 权限错误原文 |
| compile 方言失败 | 是 | 先修 semantic spec；仍失败再 SQL | compile error、修复尝试 |
| 用户要求看明细 | 视情况 | 明细 governed table | 是否涉及 PII |

### Do Not Bypass Semantic Layer

- 不因“历史 SQL 这么写”跳过；
- 不因“需要 join”跳过；
- 不因“需要自定义时间窗口”跳过；
- 不因“用户只问一个简单数字”跳过；
- 不因“raw SQL 更快”跳过。

## Dimensions

说明同一业务概念在不同表、语义层、报表中的命名差异。

| 概念 | 推荐名称 | 历史别名 | 表字段 | 语义层字段 | 口径说明 |
|---|---|---|---|---|---|
| [送审原因] | reason | 策略 / 规则 / 审核原因 | `[送审原因]` | reason | 以数据域 owner 定义为准 |
| [日期] | p_date | dt / date / 日期 | `p_date` | date | 分区日期，不一定是事件发生时间 |

## Governed Tables

只有 Semantic Layer 无覆盖或明确不适用时才读本节。

### [db.table_or_dataset]

- **Owner**：[团队 / 人]
- **Tier**：canonical / governed / deprecated / exploration
- **Grain**：[一行代表什么]
- **Freshness**：[T+1 / T+2 / 小时级 / 手动刷新]
- **Partition**：[p_date / date]
- **Scope/exclusions**：[覆盖范围、排除范围]
- **Use for**：[适用问题]
- **Do NOT use for**：[不适用问题]
- **Join keys**：[key + 一对一/一对多说明]
- **Required filters**：

```sql
-- 必填过滤条件
```

- **Known caveats**：
  - [例如：字段 A 是预聚合值，跨 reason 汇总要重算]
  - [例如：某字段含历史别名，需要映射]

### [db.table_or_dataset_2]

- **Owner**：
- **Tier**：
- **Grain**：
- **Freshness**：
- **Partition**：
- **Scope/exclusions**：
- **Use for**：
- **Do NOT use for**：
- **Join keys**：
- **Required filters**：
- **Known caveats**：

## Gotchas

记录 senior analyst 会提前提醒的错误模式。每条都要明确“错法”和“正法”。

| 错误模式 | 为什么错 | 正确做法 |
|---|---|---|
| 直接 SUM 已聚合率值 | 比率不可跨粒度直接相加 | 用分子、分母重新计算 |
| 多规则命中同一 reason 后 SUM 指标 | 同一 reason 被重复计数，指标翻倍 | 同 reason 多规则聚合用 `MAX` |
| 使用未就绪的昨天分区 | T+1 数据可能未落完 | 先查 `MAX(p_date)` 和分区行数 |
| 空标签用 `IN (NULL, ...)` | ClickHouse 无法命中 NULL | 显式 `field IS NULL OR field IN (...)` |
| 字段写成裸 `[Name]` | ClickHouse 语义字段语法错误 | 使用 `` `[Name]` `` |

## Best Practices / Common Query Patterns

### 趋势分析

- 默认粒度：[day]
- 默认比较：[本期 vs 上期同长度窗口]
- 必须输出：[本期值、上期值、绝对变化、相对变化、数据新鲜度]

### 分群分析

- 默认维度：[业务线 / reason / 标签 / 队列]
- 防重复要求：[join 前确认 grain，join 后检查行数膨胀]
- 小样本要求：[低于阈值只展示，不做强结论]

### 漏斗 / 转化分析

- 每一层必须写清分母；
- 同一用户 / 任务跨层去重规则必须一致；
- 不同时间窗的漏斗不能直接比较。

### 异常解释

- 先拆贡献：整体变化 = 主要分群变化贡献；
- 再看口径：确认不是分区、过滤、join、重复计数导致；
- 最后才给业务解释，并标注“数据支持”与“推测”。

## Troubleshooting Guide

### When Information Is Missing

| 问题 | 一线处理 | 仍失败时 |
|---|---|---|
| 找不到 metric | 搜中文、英文、别名、dashboard 名；查 deprecated metric | 记录 searched keywords，转 domain owner |
| 找不到 table | 查 lineage、dashboard SQL、reference doc cross-reference | 不猜表名，转人工 |
| 缺少字段说明 | 查字段 profile、样例值、上游模型注释 | 只做探索，不输出最终结论 |
| 权限不足 | 返回权限申请对象、数据集 ID、用途说明 | 不让用户粘贴敏感数据绕过 |
| 用户口径不清 | 澄清分子、分母、时间窗、范围 | 提供候选口径让用户选择 |

### Semantic Layer Failures

| 错误 | 可能原因 | 修复 |
|---|---|---|
| metric not found | 关键词不匹配 / 未注册 | 查别名；确认是否应补 metric |
| dimension not found | 语义层未暴露该维度 | 查 governed table；记录缺口 |
| segment not found | 标准过滤未注册 | 禁止手写复杂 segment，先找 owner |
| compile failed | 参数、时间窗、方言错误 | 修 spec；保留错误信息 |
| result mismatch dashboard | dashboard 使用旧口径或缓存 | 比对 metric ID、时间窗、segment、刷新时间 |

### Field Naming Gotchas

| 禁用字段/写法 | 推荐字段/写法 | 说明 |
|---|---|---|
| `[Name]` | `` `[Name]` `` | ClickHouse 语义字段必须反引号包方括号 |
| `[field_x]` | `[field_x_v2]` | v1 已废弃 |
| `打标量_reviewid` | `打标量__reviewid` | 示例：双下划线字段 |
| `SUM(rate)` | `SUM(numerator) / SUM(denominator)` | 比率跨粒度重算 |

### Data Freshness / Completeness

每次查询前做最小数据健康检查：

```sql
SELECT
  max(p_date) AS max_partition,
  count() AS row_cnt,
  countIf([关键字段] IS NULL) AS null_cnt
FROM [table]
WHERE p_date BETWEEN '${start_date}' AND '${end_date}'
```

停止条件：

- 目标分区不存在；
- 目标分区行数为 0；
- 关键字段空值率异常；
- 与过去 7/14/28 天均值相比突变且无业务解释；
- owner 标记数据源 deprecated。

### Empty Result

空结果不能直接解释为“没有问题”。按顺序检查：

1. 时间窗是否正确；
2. 分区是否就绪；
3. 标准过滤条件是否过严；
4. segment 是否选错；
5. join 是否把样本过滤掉；
6. 阈值是否过高；
7. 是否查询了 deprecated source。

只有以上检查通过后，才允许输出“本口径下未命中”。

## Cross-References

| 相邻业务域 | 文档 | 何时跳转 |
|---|---|---|
| [效率域] | `references/efficiency_domain.md` | 打标率、完审量、低效策略 |
| [质量域] | `references/quality_domain.md` | 准确率、误伤、漏审、质检 |
| [成本域] | `references/cost_domain.md` | 人力成本、单量成本、产能 |

## Maintenance Checklist

当数据模型、语义层或 dashboard 变更时，同步检查：

- [ ] canonical metric 是否新增、废弃或改口径；
- [ ] segment 是否变化；
- [ ] governed table grain 是否变化；
- [ ] 字段名、枚举值、owner 是否变化；
- [ ] dashboard 数字是否仍能由本参考文档复现；
- [ ] offline eval 是否需要新增或更新；
- [ ] provenance footer 的 owner / freshness 是否仍准确。
