# grading_rules — notice/P2/P1/P0 四级低效分级规则拆解

> 本文是四级分级规则的**完整条件权威**。每级绑定一条 SQL 模板（`scripts/sql_templates.py`），**SQL 结果非空即命中，每一行是一条低效策略**。等级只决定优先级，不影响 SQL 逻辑本身。

## 分级总览

| 等级 | 优先级 | sql_key | 形态 | 时间窗口 |
|---|---|---|---|---|
| **P0** | 0（最高） | `rule_low_label_rate_p0` | 四条件 UNION | 4 周窗口（w1-w4，共28天） |
| **P1** | 1 | `rule_low_label_rate_p1` | 三条件 UNION | 双周期（近1周+前1周） |
| **P2** | 2 | `rule_low_label_rate_p2` | 双条件 UNION | 双周期（近1周+前1周） |
| **notice** | 3（最低） | `rule_low_label_rate_notice` | 单周期比率阈值 | 单周期（近1周） |

> **多级命中取最高等级**：同一 `reason` 若同时命中 P0 和 P1，只算 P0。优先级数字越小越高。
>
> 阈值方向记忆：**打标率越低越低效**（`打标率 < X%`）、**进审量越高越占产能**（`进审量 > N`）、**环比越高越爆量**（`环比 > Y%`）。等级越高，进审量门槛越高、持续时间要求越长。

---

## notice — 观察级单周期低效

**逻辑**：单周期（近7天）内，`打标率 < 10%` 且 `进审量 > 0`。

**默认参数**（`default_params`）：

| 参数 | 默认值 | 含义 |
|---|---|---|
| `ratio_threshold` | 0.1 | 打标率阈值（< 10%） |
| `ratio_op` | `<` | 比较算子 |
| `guard_threshold` | 0 | 进审量守卫（> 0，即有进审即算） |
| `guard_op` | `>` | 守卫算子 |
| `order_field` | `wan_shen` | 按日均完审量降序 |

用途：最宽松的观察网，捞出所有打标率偏低的策略供观察。

---

## P2 — 双条件 UNION（单策略低效 OR 低效环比增长）

**条件一 · 单策略低效**（逻辑 A AND B）：
- A：近7天累计进审量 > 14000（即日均 > 2000）
- B：近7天打标率 < 3%

**条件二 · 低效策略环比增长**（逻辑 A AND B AND C，前置打标率<10%）：
- 前置：本周期打标率 < 10%（低效策略）
- A：上周期日均进审量 > 0（守卫）
- B：环比增长率 > 20%
- C：日均增量 > 2000

**默认参数**：

| 参数 | 默认值 | 对应条件 |
|---|---|---|
| `c1_jinshen_threshold` | 14000 | 条件一 累计进审 > 14000 |
| `c1_ratio_threshold` | 0.03 | 条件一 打标率 < 3% |
| `c2_ratio_threshold` | 0.1 | 条件二前置 打标率 < 10% |
| `prev_daily_guard` | 0 | 条件二 上周期日均 > 0 |
| `growth_rate_threshold` | 0.2 | 条件二 环比 > 20% |
| `daily_delta_threshold` | 2000 | 条件二 日均增量 > 2000 |

条件一 UNION ALL 条件二，外层按 `reason` 去重（`groupUniqArray(hit_condition)` 合并命中条件文案）。**注意：外层只合并命中条件，当前周期指标必须只取一次，不能对 UNION 命中行再次 `SUM`，否则同一 reason 同时命中两个条件时日均量会翻倍。**

---

## P1 — 三条件 UNION（持续低效 OR 高量低效 OR 低效爆量）

**条件一 · 双周持续低效**（近7天+前7天双周期均满足）：
- 双周期日均进审 > 2000（本期 `c1_cur_daily_jinshen`、上期 `c1_prev_daily_jinshen`）
- 双周期打标率 < 3%（`c1_ratio_threshold`）

**条件二 · 单周高量低效**：
- 近7天日均进审 > 5000（`c2_daily_jinshen`）
- 近7天打标率 < 3%（`c2_ratio_threshold`）

**条件三 · 低效策略爆量**：
- 本期打标率 < 10%（`c3_ratio_threshold`）且 上期打标率 < 10%（`c3_prev_ratio_threshold`）
- 上期日均进审 > 0（`c3_prev_daily_guard`）
- 环比增长率 > 30%（`c3_growth_rate_threshold`）
- 日均增量 > 5000（`c3_daily_delta_threshold`）

**默认参数**：

| 参数 | 默认值 | 对应条件 |
|---|---|---|
| `c1_ratio_threshold` | 0.03 | 条件一 双周期打标率 < 3% |
| `c1_cur_daily_jinshen` | 2000 | 条件一 本期日均进审 > 2000 |
| `c1_prev_daily_jinshen` | 2000 | 条件一 上期日均进审 > 2000 |
| `c2_daily_jinshen` | 5000 | 条件二 近7天日均进审 > 5000 |
| `c2_ratio_threshold` | 0.03 | 条件二 打标率 < 3% |
| `c3_ratio_threshold` | 0.1 | 条件三 本期打标率 < 10% |
| `c3_prev_ratio_threshold` | 0.1 | 条件三 上期打标率 < 10% |
| `c3_prev_daily_guard` | 0 | 条件三 上期日均 > 0 |
| `c3_growth_rate_threshold` | 0.3 | 条件三 环比 > 30% |
| `c3_daily_delta_threshold` | 5000 | 条件三 日均增量 > 5000 |

三条件 UNION ALL（`sql.count("UNION ALL") == 2`），外层按 `reason` 去重。**注意：外层只合并命中条件，当前周期指标必须只取一次，不能对 UNION 命中行再次 `SUM`，否则同一 reason 同时命中多个条件时日均量会重复累加。**

---

## P0 — 四条件 UNION（按周拆分，最严重）

P0 用 **4 个周窗口**（w1=近1周、w2=前1周、w3=前前1周、w4=前前前1周，共28天）。展示口径为近1周（w1）日均量。

**条件A · 持续四周低效（严重）**：
- 近1周日均进审 > 2000（`c1_weekly_daily_jinshen`，**仅 w1 校验进审量**）
- 近1、2、3、4周打标率均 < 3%（`c1_ratio_threshold`），4 周全部命中（w1 JOIN w2 JOIN w3 JOIN w4，w2/w3/w4 只校验打标率）

**条件B · 持续两周高量**：
- 近1周日均进审 > 5000（`c2_daily_jinshen`）
- 近1、2周打标率 < 3%（`c2_ratio_threshold`）

**条件C · 单周超高量**：
- 近1周日均进审 > 10000（`c3_daily_jinshen`）
- 近1周打标率 < 3%（`c3_ratio_threshold`）

**条件D · 进审量异常爆量**：
- 近1周日均进审 > 上1周日均 × 1.5（`c4_growth_rate`=0.5，即增长50%）
- 日均增量 > 10000（`c4_daily_delta`）
- 近1周打标率 < 10%（`c4_ratio_threshold`）
- 上1周仅作环比基线（`c4_prev_daily_guard` 防除零），**不设打标率门槛**

**默认参数**：

| 参数 | 默认值 | 对应条件 |
|---|---|---|
| `c1_weekly_daily_jinshen` | 2000 | 条件A 近1周日均进审 > 2000 |
| `c1_ratio_threshold` | 0.03 | 条件A 近1~4周每周打标率 < 3% |
| `c2_daily_jinshen` | 5000 | 条件B 近1周日均进审 > 5000 |
| `c2_ratio_threshold` | 0.03 | 条件B 近1、2周打标率 < 3% |
| `c3_daily_jinshen` | 10000 | 条件C 近1周日均进审 > 10000 |
| `c3_ratio_threshold` | 0.03 | 条件C 近1周打标率 < 3% |
| `c4_prev_daily_guard` | 0 | 条件D 上1周日均 > 0（防除零基线） |
| `c4_growth_rate` | 0.5 | 条件D 近1周 > 上1周 ×1.5 |
| `c4_daily_delta` | 10000 | 条件D 日均增量 > 10000 |
| `c4_ratio_threshold` | 0.10 | 条件D 近1周打标率 < 10% |

四条件 UNION ALL（`sql.count("UNION ALL") == 3`），外层按 `reason` 去重。

---

## 阈值来源与覆盖

- 默认阈值内嵌在 `scripts/sql_templates.py` 各 `sql_key` 的 `default_params`，本文表格与之一一对应。
- 运行时可通过 `sql_params`（扁平 JSON）覆盖任意阈值，例如 `{"c2_daily_jinshen": 8000}`。
- **参数命名约定**：`c1/c2/c3/c4` 对应 UNION 内第 N 个条件；`ratio_threshold`=打标率阈值（小数）；`jinshen_threshold`/`daily_jinshen`=进审量阈值；`growth_rate*`=环比阈值（小数）；`daily_delta*`=日均增量阈值；`prev_daily_guard`=上周期日均守卫（防除零/极小基数）。
- 阈值单位统一用**小数**（`3%` → `0.03`），不写百分号。渲染前 `validate_params` 会校验为数值，非数值直接转人工。
- **进审量守卫**：`guard_threshold`（notice）/ `prev_daily_guard`（双周期规则）过滤极小基数策略，避免低量偶发被误判高等级。
