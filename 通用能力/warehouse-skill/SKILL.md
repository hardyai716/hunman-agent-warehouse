---
name: warehouse-skill
description: 人审运营监控体系·数据仓库查询横向能力。Invoke when business analysis needs governed metrics, semantic-layer lookup, warehouse SQL, data provenance, or query validation.
metadata:
  version: "0.1.0"
  author: 李中涛
  status: draft
  tags: [人审运营, 横向能力, 数据仓库, Semantic Layer, 指标口径, 数据校验, provenance]
  requires:
    bins: ["bytedcli"]
    siblings: []
  requires_optional:
    - "bytedance-aeolus：平台内置风神/Aeolus 查询能力，用于治理数据集、报表和 SQL 执行"
    - "sqless-data-analysis：内部业务数据自然语言取数/跨源分析兜底能力，仅作为平台内置能力调用"
    - "lark-base / lark-sheets：当需要读取指标配置、eval 结果或线上校验看板时使用"
    - "review-monitoring-shared：当分析结果要进入事件、路由、触达链路时复用配置中心与审计字段"
  requires_note: "本 skill 是数据查询横向能力；默认强制先走 Semantic Layer，raw SQL 仅作为有记录的 fallback。"
---

# warehouse-skill — 数据仓库查询横向能力

## 定位

面向人审运营监控体系的数据仓库入口：把业务问题稳定映射到**被治理的指标、维度、数据集和查询路径**，并输出可追溯、可复核的分析结果。

本 skill 是**横向能力层**，供效率、质量、成本等纵向业务模块复用。它只负责：

1. 识别业务问题对应的数据域、指标和口径；
2. 优先通过 Semantic Layer 查询；
3. 在语义层不覆盖时，按业务域参考文档回退到受控 raw SQL；
4. 执行查询前后的数据质量与 SQL 审查；
5. 输出带 provenance footer 的结果。

## 触发场景

当用户或上游 skill 需要：

- 查询人审运营、效率、质量、成本等业务指标；
- 判断某个业务概念对应哪个 canonical metric / table / field；
- 基于数据仓库做趋势、分群、漏斗、环比、归因、异常解释；
- 生成可复核 SQL、查询结果、分析报告；
- 校验已有分析口径是否符合统一指标定义；

使用本 skill。

## 不适用场景

- 不负责异常分级、事件状态推进、责任路由、触达发送；
- 不替业务 owner 下产品、策略、运营决策，只提供数据事实、方法和限制；
- 不处理飞书 open_id/chat_id 解析；
- 不绕过权限读取敏感数据；
- 不在数据未就绪、口径不明确、权限不足时编造结论。

## 输入（标准形态）

```json
{
  "question": "近7天低效策略的打标率和完审量趋势如何？",
  "business_domain": "效率模块",
  "time_window": {
    "type": "trailing_days",
    "days": 7,
    "as_of_date": "2026-07-06",
    "data_lag_days": 1
  },
  "segments": {
    "business_line": "人审",
    "review_scene": "可选"
  },
  "output_level": "analysis",
  "risk_level": "normal"
}
```

最小输入可以只有自然语言问题；缺少时间窗口、业务域、分群或决策背景时，先澄清再查询。

## 输出（标准形态）

```json
{
  "status": "answered",
  "answer_summary": "近7天低效策略共命中 N 条，其中 P1 X 条，P2 Y 条。",
  "methodology": {
    "metric_source": "semantic_layer",
    "metrics": ["打标率", "完审量", "进审量"],
    "filters": ["p_date between ...", "标准人审过滤条件"],
    "grain": "reason × day"
  },
  "query": {
    "engine": "ClickHouse",
    "semantic_spec_or_sql": "..."
  },
  "limitations": ["目标分区 T-1 已就绪；不包含未入仓实时数据"],
  "provenance": {
    "source_tier": "semantic_layer",
    "confidence": "high",
    "freshness": "max(p_date)=2026-07-05",
    "owner": "待填：数据域 owner",
    "reviewed": "sql_review_passed"
  }
}
```

## 查询路径优先级

1. **Semantic Layer（强制默认路径）**：指标、维度、segment、grain、join、标准过滤条件由治理层提供。
2. **Governed Dataset / Aeolus Dataset**：当语义层无覆盖，但存在被治理的数据集、风神逻辑数据集或 canonical dashboard。
3. **Curated Raw SQL**：仅在业务域参考文档明确列出表、grain、join key、必需过滤条件时使用。
4. **Untrusted Raw Exploration**：仅用于字段探测或可行性验证，不能直接作为最终结论来源。
5. **不可查询**：无权限、无口径、无 owner、数据未就绪时停止，要求补充信息或转人工。

## Semantic Layer（REQUIRED first step）

Semantic Layer 是每个数据问题的**强制第一步**，原因是它内置了统一指标口径、标准 segment、join 关系、grain 和过滤条件。raw SQL 只能作为 fallback，且必须记录 fallback 原因。

### 必须执行的工作流

1. **Load**：加载当前 runtime 可用的语义层入口。
   - 首选：公司内部 Semantic Layer / 风神语义数据集 / 已注册指标查询接口；
   - 次选：`bytedcli` 或 `bytedance-aeolus` 可查询的数据集元信息；
   - 不可用：记录 `semantic_layer_unavailable`，进入受控 fallback。
2. **Discover**：按用户问题搜索 metric、dimension、segment。
   - 必须同时搜索中文名、英文名、历史别名、业务简称；
   - 必须检查 segment，不能手写语义层已有的人群过滤；
   - 如概念多义，先澄清，不猜。
3. **Compile + Run**：构造 semantic spec，编译为 SQL 或直接执行指标查询。
   - 记录指标 ID / 数据集 ID / 维度 / 时间窗口 / segment；
   - 编译失败时保存错误原因。
4. **Fallback**：只有以下情况才允许 raw SQL：
   - 语义层找不到对应 metric；
   - metric 覆盖但缺少必要维度；
   - 编译失败且错误不可由参数修正；
   - 业务域参考文档明确要求某类问题使用 governed table。

### 禁止过早 fallback

以下理由不能作为跳过 Semantic Layer 的依据：

- “需要自定义时间窗口”：先确认语义层是否支持 time dimension / as-of date；
- “需要 join”：语义层可能已封装 join，不得自行拼接；
- “需要分群过滤”：先查 segment，不手写 canonical population；
- “想看 SQL”：可以编译 semantic spec，不代表必须 raw SQL；
- “历史上用过某张表”：历史 SQL 不是 source of truth，只能作为参考。

### 时间窗口与时区

- “近 N 天”：默认使用最新已就绪分区往前 N 天，不含未就绪自然日。
- “上周 / 上月”：默认解释为**完整自然周 / 完整自然月**，不是 trailing 7/30 days。
- “截至昨天”：先用数据就绪探测确认 `MAX(p_date)`，不要硬编码昨天。
- 默认时区：除业务域参考文档另有说明，使用公司统一报表时区。
- T+N 数据：优先锚定 `MAX(p_date)`，并在 provenance 中写明 freshness。

## Quick Start Workflow

1. **检查红线**：权限、PII、敏感字段、领导汇报、高风险结论。
2. **澄清问题**：业务域、时间窗口、分群、指标定义、使用场景。
3. **语义层发现**：搜索 metric / dimension / segment / dashboard。
4. **识别数据源**：按 `references/domain_reference_template.md` 的结构定位 reference doc。
5. **数据就绪校验**：确认目标分区、行数、关键字段非空率、异常波动。
6. **执行查询**：先 semantic spec；必要时受控 raw SQL。
7. **审查结果**：SQL 口径、join grain、分母、过滤条件、重复计数、样本偏差。
8. **输出结论**：区分数据事实、解释判断和业务建议；附 provenance footer。

## 数据完整性硬约束

- **NEVER** 编造表、字段、指标、数值、open_id、chat_id。
- **NEVER** 把查询失败、权限失败、数据未就绪解释为“无异常 / 无命中”。
- **NEVER** 在没有 owner 或 canonical 定义时宣称某口径是唯一正确口径。
- **ALWAYS** 使用安全除法，明确分母、样本范围、时间窗口和过滤条件。
- **ALWAYS** 记录 source tier：semantic layer / governed dataset / curated raw SQL / raw exploration。
- **ALWAYS** 在多规则命中同一 reason 聚合时用 `MAX` 而不是 `SUM`，避免指标翻倍。
- **ALWAYS** 在 ClickHouse 语义字段中使用反引号包方括号，例如 `` `[Name]` ``。

## 业务域参考

新增业务域时，不直接把大量表说明塞进本文件。按模板创建独立参考文档：

- 模板：[references/domain_reference_template.md](references/domain_reference_template.md)
- Validation 闭环：[references/validation_loop.md](references/validation_loop.md)

建议目录：

```text
通用能力/warehouse-skill/references/
  domain_reference_template.md
  validation_loop.md
  efficiency_domain.md
  quality_domain.md
  cost_domain.md
```

## 故障处理入口

遇到以下情况，先查业务域参考文档的 `Troubleshooting Guide`：

- 语义层找不到指标；
- 字段名相似或 v1/v2 并存；
- 表粒度不匹配；
- 分区未就绪；
- 权限不足；
- dashboard 数字与查询结果不一致；
- 查询为空但业务上不合理；
- 历史 SQL 与 reference doc 冲突。

## 输出格式要求

所有最终分析回答必须包含：

1. **结论摘要**：用业务语言说明结果；
2. **口径方法**：指标、分母、分子、过滤条件、grain；
3. **数据证据**：核心数字、趋势、分群；
4. **限制说明**：数据新鲜度、缺失、样本偏差、未覆盖范围；
5. **Provenance Footer**：

```markdown
> **Source:** semantic_layer | governed_dataset | curated_raw_sql | raw_exploration  
> **Confidence:** high | medium | low  
> **Freshness:** max_partition=YYYY-MM-DD / checked_at=YYYY-MM-DD HH:mm  
> **Owner:** [数据域 owner]  
> **Reviewed:** semantic_compile_passed | sql_review_passed | needs_human_review
```

## 能力边界

本 skill 只解决“如何正确查询和解释数据”。后续链路由其他 skill 负责：

- 异常事件生成与监控配置：由纵向业务分析 skill 或 orchestrator 负责；
- 责任人匹配：由 `owner-routing` 负责；
- 飞书触达、建群、确认门禁：由 `anomaly-touch` 负责；
- 配置表结构：由 `review-monitoring-shared` 维护。
