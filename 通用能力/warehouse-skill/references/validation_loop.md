# warehouse-skill Validation 闭环落地方案

本文档用于把 Claude 文章中的 Validation 机制落到人审数据仓库场景。目标不是证明 Agent 永远正确，而是持续发现并修复三类问题：

1. **概念 <> 实体歧义**：问题映射到了错误指标、字段、表或 segment；
2. **数据 / 文档过期**：语义层、reference doc、dashboard、表结构漂移；
3. **检索失败**：正确资料存在，但 Agent 没找到或没正确使用。

## 总体闭环

```text
业务问题 / dashboard / 用户纠错
  → 离线 eval 样本
  → 固化 ground truth
  → 每次 Skill / reference / 数据模型变更触发评测
  → 记录评测结果与 ablation
  → 线上查询带 provenance + 质量校验
  → 线上纠错自动回收
  → PR 更新 reference doc / skill / eval
```

## 一、离线 Eval 流程

### 1. Eval 分类

| 类型 | 来源 | 目的 | 例子 |
|---|---|---|---|
| Dashboard-based eval | 已被业务认可的核心 dashboard | 覆盖高频、核心 KPI | “近7天 P1 低效策略数量是多少？” |
| Long-tail eval | roadmaps、业务文档、表说明、历史分析需求 | 覆盖边缘问题和真实长尾 | “某业务线机审标签为空的低效 reason 占比？” |
| Regression eval | 用户纠错、事故复盘、曾经答错的问题 | 防止同类问题复发 | “打标率分母不能用进审量” |
| Safety eval | PII、权限、未就绪、无口径场景 | 验证应停止而不是回答 | “导出审核员明细手机号” |
| Freshness eval | 分区延迟、字段废弃、表迁移 | 验证 stale source 会被拦截 | “昨天数据没到时是否仍输出结论？” |

### 2. Eval 样本结构

建议建一个 `warehouse_eval_cases` 表，可放在飞书多维表格或数据仓库。

| 字段 | 类型 | 说明 |
|---|---|---|
| eval_id | text | 唯一 ID，如 `efficiency_label_rate_001` |
| domain | single_select | 效率 / 质量 / 成本 / 通用 |
| question | text | 用户自然语言问题 |
| expected_behavior | single_select | answer / clarify / stop / escalate |
| ground_truth_type | single_select | fixed_answer / sql_assertion / query_shape / behavior_only |
| snapshot_date | date | 固化数据日期，避免 live data 漂移 |
| required_source_tier | single_select | semantic_layer / governed_dataset / curated_raw_sql |
| required_metrics | multi_select | 必须使用的指标 |
| forbidden_sources | multi_select | 禁止使用的表、字段、旧口径 |
| assertions_json | json | 数字、SQL、行为、provenance 断言 |
| owner | person | 业务域 owner |
| severity | single_select | P0 / P1 / P2 / normal |
| status | single_select | active / deprecated / draft |
| created_from | text | dashboard / user_correction / incident / generated |

### 3. Ground Truth 固化方式

优先级从高到低：

1. **固定快照答案**：对稳定 fact table 或 dashboard snapshot 固化数值。
2. **SQL 断言**：不固定数值，只断言 SQL 使用了正确 source、metric、filter、grain。
3. **行为断言**：验证 Agent 应该澄清、停止或升级。
4. **Provenance 断言**：验证回答是否标注 source tier、freshness、owner、review 状态。

示例 `assertions_json`：

```json
{
  "must_use_source_tier": "semantic_layer",
  "must_include_metrics": ["label_rate", "review_done_cnt"],
  "must_not_use_fields": ["打标量_reviewid"],
  "must_include_filters": ["standard_review_scope"],
  "expected_behavior": "answer",
  "numeric_tolerance": {
    "label_rate": 0.0001
  },
  "provenance_required": ["Source", "Confidence", "Freshness", "Owner", "Reviewed"]
}
```

### 4. Eval 执行时机

| 触发点 | 执行范围 | 是否阻断 |
|---|---|---|
| 修改 `warehouse-skill/SKILL.md` | 全量核心 eval + 相关域 eval | 阻断 |
| 修改 `references/*_domain.md` | 对应 domain eval | 阻断 |
| 修改语义层 metric / segment | 依赖该 metric 的 eval | 阻断 |
| 修改 dashboard / 数据模型 | dashboard-based eval | 阻断或人工确认 |
| 每日定时 | P0/P1 核心 KPI eval | 告警，不直接阻断 |
| 用户纠错入库 | 新增 regression eval 后重跑 | 不阻断，进入修复队列 |

### 5. Eval 判定维度

每个 eval 不只判答案数字，还要判过程：

| 维度 | 通过条件 |
|---|---|
| Source Routing | 优先语义层；fallback 有充分理由 |
| Entity Mapping | 指标、字段、表、segment 命中 canonical 定义 |
| Query Correctness | grain、join、filter、分母、去重逻辑正确 |
| Data Freshness | 查询前检查 `MAX(p_date)` 或等价 freshness |
| Behavior | 不清楚时澄清；无权限/未就绪时停止 |
| Output Quality | 区分观察和解释；带限制说明 |
| Provenance | footer 完整且与实际查询路径一致 |

### 6. 结果记录表

建议建 `warehouse_eval_runs` 表。

| 字段 | 类型 | 说明 |
|---|---|---|
| run_id | text | 一次评测运行 ID |
| eval_id | text | 关联 eval case |
| skill_version | text | `warehouse-skill` 版本 |
| git_sha | text | 仓库 commit |
| model_id | text | 使用的模型 |
| source_tier_used | single_select | 实际使用 source tier |
| passed | checkbox | 总体是否通过 |
| failed_assertions | text | 失败断言摘要 |
| latency_ms | number | 耗时 |
| token_count | number | token 消耗 |
| query_hash | text | SQL / semantic spec hash |
| answer_hash | text | 答案 hash |
| created_at | datetime | 运行时间 |

### 7. PR 级 Ablation

每个有意义的 Skill / reference doc 改动，都要做 before / after：

1. 固定同一批 eval；
2. 只改变一个组件：主 skill、某个 domain doc、semantic routing、review 提示等；
3. 记录通过率、失败样本、token、耗时；
4. 在 PR 描述中写明 delta；
5. 负向结果也要记录，避免重复试错。

PR 描述模板：

```markdown
## Validation

- Eval slice: [efficiency_core, regression_low_label_rate]
- Baseline pass rate: 42/45
- New pass rate: 44/45
- Delta: +2 pass, 0 regression
- Latency/token delta: +8% latency, +3% tokens
- Failed cases:
  - eval_id: ...
  - reason: ...
- Negative findings:
  - [哪些尝试无效或变差]
```

## 二、线上校验流程

### 1. 查询前校验

每次线上回答前执行最小 gate：

| Gate | 检查 | 失败动作 |
|---|---|---|
| Scope Gate | 是否属于数据仓库查询 | 不属于则不调用本 skill |
| Permission Gate | 是否有权限查询目标数据 | 停止，返回授权路径 |
| Semantic Gate | 是否已查语义层 | 未查则返回语义层发现步骤 |
| Freshness Gate | 目标分区是否就绪 | 停止，不给结论 |
| PII Gate | 是否涉及敏感明细 | 返回 SQL 或转人工，不直接出明细 |
| High-stakes Gate | 是否用于领导汇报 / 处罚 / 资源调整 | 要求人审或二次校验 |

### 2. 查询后校验

每次查询后至少检查：

- 结果行数是否异常为 0；
- 关键指标是否 NULL / NaN / INF；
- 比率是否超出合理范围；
- join 前后行数是否膨胀；
- 聚合前后口径是否一致；
- 与 blessed dashboard 的核心 KPI 是否偏离阈值；
- provenance footer 是否和实际 source tier 一致。

### 3. Adversarial Review

高风险查询必须加对抗审查。触发条件：

- P0/P1 事件判断；
- 领导汇报或正式周报；
- 涉及成本、绩效、处罚、资源调度；
- fallback 到 raw SQL；
- 查询结果与 dashboard 不一致；
- 用户追问“为什么”和“归因”。

审查清单：

```markdown
## SQL / Semantic Review

- 是否使用 Semantic Layer？若没有，fallback 理由是否成立？
- 指标分子 / 分母是否正确？
- grain 是否与问题一致？
- join 是否会一对多放大？
- 时间窗口是否是用户想要的窗口？
- 标准过滤和 segment 是否完整？
- 是否把数据未就绪误判为无结果？
- 是否使用了 deprecated table / field？
- 输出是否区分事实、解释、建议？
- provenance 是否完整？
```

### 4. Provenance Footer

线上所有回答必须带 footer：

```markdown
> **Source:** semantic_layer | governed_dataset | curated_raw_sql | raw_exploration  
> **Confidence:** high | medium | low  
> **Freshness:** max_partition=YYYY-MM-DD / checked_at=YYYY-MM-DD HH:mm  
> **Owner:** [数据域 owner]  
> **Reviewed:** semantic_compile_passed | sql_review_passed | adversarial_review_passed | needs_human_review
```

置信度建议：

| Confidence | 条件 |
|---|---|
| high | 语义层命中 + 数据就绪 + eval 覆盖 + 无审查问题 |
| medium | governed table fallback + 有 reference doc + SQL 审查通过 |
| low | raw exploration / 文档缺失 / owner 未确认 / freshness 异常 |

### 5. 线上遥测表

建议建 `warehouse_online_queries` 表。

| 字段 | 类型 | 说明 |
|---|---|---|
| query_id | text | 单次查询 ID |
| user_question | text | 脱敏后的问题 |
| domain | single_select | 业务域 |
| source_tier | single_select | 实际 source tier |
| semantic_hit | checkbox | 是否命中语义层 |
| fallback_reason | text | fallback 原因 |
| freshness | text | max partition / 更新时间 |
| confidence | single_select | high / medium / low |
| reviewed | single_select | none / sql / adversarial / human |
| correction_detected | checkbox | 是否被用户纠错 |
| correction_text | text | 纠错摘要 |
| latency_ms | number | 耗时 |
| token_count | number | token 消耗 |
| created_at | datetime | 查询时间 |

核心线上指标：

- 语义层命中率；
- raw SQL fallback 占比；
- low confidence 回答占比；
- 用户纠错率；
- 数据未就绪拦截次数；
- deprecated source 命中次数；
- 高风险查询人审覆盖率。

## 三、纠错回收机制

### 1. 纠错来源

- 用户明确指出：“表错了 / 字段错了 / 口径错了 / 少了过滤 / 数字不对”；
- 线上查询与 blessed dashboard 偏离；
- domain owner 在周会或飞书线程中修正口径；
- eval 失败；
- 数据模型变更导致 reference doc 不再准确。

### 2. 纠错记录表

建议建 `warehouse_corrections` 表。

| 字段 | 类型 | 说明 |
|---|---|---|
| correction_id | text | 唯一 ID |
| query_id | text | 关联线上查询 |
| domain | single_select | 业务域 |
| correction_type | single_select | metric / table / field / filter / freshness / permission / output |
| original_answer | text | 原答案摘要 |
| correction_text | text | 用户或 owner 纠错内容 |
| root_cause | single_select | ambiguity / stale_doc / retrieval_failure / query_bug / data_issue |
| proposed_fix | text | 建议修改 |
| target_file | text | 需要改的 skill / reference / eval |
| owner | person | 处理人 |
| status | single_select | new / triaged / pr_opened / fixed / wont_fix |
| new_eval_required | checkbox | 是否需要新增 regression eval |

### 3. 修复闭环

1. 纠错入库；
2. 标记 root cause；
3. 判断修复对象：
   - 概念歧义 → 更新 domain reference / Semantic Layer alias；
   - 文档过期 → 更新 reference doc；
   - 检索失败 → 更新 knowledge navigation / trigger；
   - SQL bug → 更新模板或执行流程；
   - 数据问题 → 转数据 owner，不在 skill 内硬修；
4. 新增或更新 regression eval；
5. 跑对应 eval slice；
6. 合并后同步到所有使用面；
7. 线上看板确认同类纠错下降。

## 四、上线阶段规划

### Phase 0：准备 canonical 资产

- 列出效率、质量、成本三个首批业务域；
- 每域确认 5-10 个核心 metric；
- 每域确认 1-3 张 governed table；
- 每个 metric 指定 owner、grain、freshness、dashboard 对照。

### Phase 1：最小离线 Eval

- 每域 20-30 条 eval；
- 至少包含：
  - 10 条 dashboard-based；
  - 5 条 long-tail；
  - 5 条 regression / safety；
- 通过率目标：核心域上线前 >= 90%，P0/P1 KPI eval 接近 100%。

### Phase 2：线上 Provenance + 遥测

- 所有回答强制 provenance footer；
- 记录 `warehouse_online_queries`；
- 每周看语义层命中率、纠错率、low confidence 占比。

### Phase 3：纠错自动回收

- 每日扫描纠错语言；
- 自动生成 proposed_fix；
- domain owner 审核后开 PR；
- 合并前必须新增 regression eval。

### Phase 4：PR 阻断与 CI

- 修改 skill / reference / semantic layer 时自动跑 eval slice；
- 失败阻断合并；
- PR 描述必须带 before / after ablation。

## 五、本地模拟脚本

在接入真实 LLM 和数据仓库前，先用本地脚本验证 `warehouse_eval_cases` 样本表逻辑是否成立：

```bash
python3 通用能力/warehouse-skill/scripts/simulate_offline_eval.py \
  --cases 通用能力/warehouse-skill/examples/warehouse_eval_cases.sample.json \
  --out 通用能力/warehouse-skill/examples/warehouse_eval_runs.mock.json
```

脚本职责：

- 校验 `warehouse_eval_cases` 必填字段、枚举值、`eval_id` 唯一性；
- 校验 `assertions_json` 是否为合法 JSON object；
- 校验顶层字段与断言是否一致，例如 `expected_behavior`、`required_source_tier`；
- 校验 `fixed_answer` / `sql_assertion` / `query_shape` / `behavior_only` 的必要约束；
- 生成模拟版 `warehouse_eval_runs`，用于检查结果表字段是否可承载评测结果。

生成内置样本：

```bash
python3 通用能力/warehouse-skill/scripts/simulate_offline_eval.py \
  --write-sample 通用能力/warehouse-skill/examples/warehouse_eval_cases.sample.json
```

> 当前脚本只验证“样本表和断言设计是否自洽”，不调用真实模型、不查询数据仓库。接入真实评测时，将 `mock_agent_output` 替换为实际 Agent 调用即可。

## 六、初始落地清单

- [x] 建本地模拟版 `warehouse_eval_cases` 样例；
- [x] 建本地模拟版 `warehouse_eval_runs` 输出；
- [ ] 建 `warehouse_online_queries`；
- [ ] 建 `warehouse_corrections`；
- [x] 为效率域补第一版 `efficiency_domain.md`；
- [ ] 从低效策略 dashboard 抽 20 条 eval；
- [ ] 把“打标率分母=完审量”“多规则同 reason 用 MAX”加入 regression eval；
- [ ] 在所有分析输出中强制 provenance footer；
- [ ] 每周复盘语义层命中率和用户纠错。
