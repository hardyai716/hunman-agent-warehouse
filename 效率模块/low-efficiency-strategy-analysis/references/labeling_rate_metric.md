# labeling_rate_metric — 打标率与效率指标口径

> 本文保留低效策略打标率口径的细节说明。当前 Claude 三层架构下，效率域 canonical source of truth 是 [`../../../通用能力/warehouse-skill/references/efficiency_domain.md`](../../../通用能力/warehouse-skill/references/efficiency_domain.md)；如本文与 `efficiency_domain.md` 冲突，以 `efficiency_domain.md` 和 `scripts/sql_templates.py` 的执行默认值为准。

## 什么是「低效策略」

人审场景里，每个 `reason`（送审策略/送审原因）会把一批内容送进人工审核。理想情况下，送审的内容应当**大概率需要打标处置**（命中违规、需要打标签）。如果某个 `reason`：

- **完审量高**（审了大量内容），但
- **打标率低**（几乎不需要打标处置），

说明这个策略在**无效占用人审产能**——审了很多，却几乎没审出问题。这就是「**高完审低打标**」的**低效策略**。本 Skill 的目标就是把这类策略按严重程度分级揪出来。

## 核心指标：打标率

```
打标率 = 打标量 / 完审量
```

**SQL 实现（v2.1 重算口径，唯一正确写法）：**

```sql
if(SUM(完审量) = 0, 0, SUM(打标量) / SUM(完审量))
```

三条不可违背的口径约定：

1. **分母是完审量，不是进审量**。进审量（送进来的）≥ 完审量（审完的）≥ 打标量（打了标的）。用进审量当分母会让打标率虚低、误判低效。
2. **基于内层 SUM 重算**，不直接引用数据集预聚合的 `打标率__reviewid` 字段——预聚合值在多分区聚合时口径可能与动态日均不一致。
3. **打标率越低 = 越低效**。所有规则的触发方向都是 `打标率 < 阈值`。

## 辅助指标（都用动态天数）

| 指标 | SQL 表达 | 为什么这样算 |
|---|---|---|
| 日均进审量 | `SUM(进审量) / COUNT(DISTINCT p_date)` | 用**实际有数据的天数**（动态天数），不写死 `/7`。若某天数据未就绪，写死 `/7` 会让日均被低估，导致漏判。 |
| 日均完审量 | `SUM(完审量) / COUNT(DISTINCT p_date)` | 同上 |
| 日均打标量 | `SUM(打标量) / COUNT(DISTINCT p_date)` | 同上 |
| 环比增长率 | `(本期日均进审 - 上期日均进审) / 上期日均进审` | **日均比**，不是总量比。两周期天数不一致（如上期少一天数据）时，总量比会失真。 |
| 日均增量 | `本期日均进审 - 上期日均进审` | 判断「爆量」用；配合环比增长率一起看。 |

> 环比防除零：`/ NULLIF(上期日均, 0)`，并额外用 `上期日均 > prev_daily_guard` 守卫，避免极小基数放大环比。

## 字段映射（逻辑名 → 真实字段名）

模板内部用逻辑字段名，渲染时经 `ctx.field_map` 映射到数据集真实字段名。执行权威为 `scripts/sql_templates.py` 的 `_DEFAULT_FIELD_MAP`，效率域汇总说明见 `efficiency_domain.md`：

| 概念 | 逻辑字段名 | 真实字段名（Name 列） | 下划线 | 类型 |
|---|---|---|---|---|
| 送审策略/原因 | `reason` | `reason` | — | 维度 |
| 项目标题 | `project_title` | `project_title` | — | 维度 |
| 审核场景 | `scene` | `scene` | — | 维度 |
| 机审一级标签 | `mach_root_label_name` | `机审一级标签` | — | 维度 |
| 日期分区 | `date` | `p_date` | — | 分区字段 |
| 进审量 | `jin_shen` | `进审量_reviewid` | 单下划线 | 聚合字段（不二次 SUM） |
| 完审量 | `wan_shen` | `完审量_reviewid` | 单下划线 | 聚合字段 |
| 打标量 | `da_biao` | `打标量__reviewid` | 双下划线 | 聚合字段 |
| 打标率 | `ratio` | `打标率__reviewid` | 双下划线 | 聚合字段（但模板中重算，不直接用） |

> 旧逻辑数据集入口可能需要把 `reason` 覆盖为中文显示名「送审原因」，这属于 runtime `ctx.field_map` 覆盖，不是默认执行口径。

> 注意 `打标量__reviewid` 与 `打标率__reviewid` 是**双下划线**，`进审量_reviewid`/`完审量_reviewid` 是**单下划线**。抄错会报字段不存在。

## 字段引用风格（ClickHouse 物理表）

- 物理表：`olap_content_security_community.dws_sft_tcs_review_task_detail_di`（ClickHouse）。
- **FROM 用物理表 `db.table` 裸写**（含点，不加反引号）；不用逻辑数据集名（逻辑名常报「未知表/字段权限」）。
- **字段用 `` `[Name]` ``**（反引号包方括号）语义占位符：物理表 FROM 下风神服务端会把 `` `[完审量_reviewid]` `` 自动展开成底层 ClickHouse 聚合表达式（`uniqExact(if(...))`），口径由数据集定义保证，无需手抄聚合表达式。
- 禁止裸 `[Name]`（ClickHouse 报 `Unrecognized token '['`）或纯反引号 `` `Name` ``（逻辑集报未知表）。三者只有 `` `[Name]` `` 可跑通。

## 模板输出列别名（报告格式化用）

| 别名 | 含义 | 默认格式 |
|---|---|---|
| `reason` | 送审策略 | 原始文本 |
| `avg_jinshen` | 日均进审量 | 整数 + 千分位 |
| `avg_wanshen` | 日均完审量 | 整数 + 千分位 |
| `avg_dabiao` | 日均打标量 | 整数 + 千分位 |
| `ratio_val` | 打标率 | 百分比保留 2 位小数（×100） |
| `hit_condition` | 命中条件 | 自动拼接文本（多条件用「；」分隔） |

## 基础过滤（样本池）

默认 `base_filter`（`use_default_base_filter=true` 时启用）圈定「社区人工审核」有效样本：

- **A** 标题黑名单：`project_title NOT LIKE` 虚假/标注/封面/自动处置/演绎/模型/run/质检/QA/测试/大模型/离线 等（排除非常规审核项目）。
- **B** 场景白名单：`scene IN (community_audit_safe, community_audit_style, community_audit_moderate)`。
- **C** reason 排除：`reason NOT IN (recall_skip_L6, fatal_output)`。
- **D** 机审一级标签：`IS NULL OR IN (...)` 白名单（不良行为、侵犯未成年、危险行为、国家安全 等）。

完整过滤条件见 `scripts/sql_templates.py` 的 `_DEFAULT_BASE_FILTER_LOW_LABEL`。需自定义样本池时传 `ctx.base_filter`（结构化 list 或 SQL 片段）覆盖。
