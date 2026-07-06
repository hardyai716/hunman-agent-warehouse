# 配置可运行性验证、迁移验收与回滚方案

本文覆盖 Task 6、Task 7、Task 8 的设计交付。范围限定为机制、验收样例和 runbook，不包含代码实现。

## 1. 验证目标与门禁

配置验证分两级：

- `lint`：只校验配置完整性、注册关系、枚举值、SOP 可达性、等级字典、模板和 Skill 可达性。不访问真实业务数据，不生成触达。
- `dry-run`：在 lint 通过后执行无副作用探测，包括数据就绪、SQL 渲染、`LIMIT 1` 探测、产物生成、卡片渲染和路由模拟。dry-run 不写事件主表，不发送正式群聊或私聊。

自动运行前必须满足：

- 无 `blocker` 或 `error` 级问题。
- 所有启用 SOP 的 process skill、report type、模板、owner source 均已注册。
- 所有触达相关 dry-run 只允许生成预览产物和校验摘要，不能真实触达。
- 对于 shadow/canary 之外的新 SOP，必须先生成 validation report 并由运营按表名、字段名完成修复闭环。

## 2. lint / dry-run 矩阵

### 2.1 配置 lint 矩阵

| 检查域 | 检查项 | 主要输入 | 校验规则 | 失败级别 | 修复提示粒度 |
|---|---|---|---|---|---|
| 必填字段 | SOP 根配置完整 | SOP 注册表 | `sop_id`、`sop_name`、`business_domain`、`process_skill`、`domain_reference`、`run_frequency`、`run_mode`、`default_report_type` 必填 | error | 表名、记录 ID、字段名 |
| 必填字段 | 观测对象完整 | SOP 指标/观测对象表 | `sop_id`、`metric_id`、`data_source_id`、`period_policy`、`canonical_metric`、`enabled` 必填 | error | 表名、metric_id、字段名 |
| 关联关系 | SOP 到指标、规则、等级可关联 | SOP 注册表、指标表、规则组表、等级字典 | 启用 SOP 至少有一个启用观测对象、一个启用规则组、一个启用等级 | error | 缺失的关联表与关联键 |
| 关联关系 | 数据源可关联 | 数据源表、指标表 | `data_source_id` 存在且状态为 enabled，字段映射包含 process skill 所需输入字段 | error | 数据源表字段映射 |
| 枚举值 | 运行模式合法 | SOP 注册表 | `run_mode` 只能取 `manual`、`scheduled`、`report_only`、`touch_enabled`、`shadow`、`canary`、`active`、`rollback` | error | 字段可选值 |
| 枚举值 | 数据源类型合法 | 数据源表 | `source_type` 必须为已支持类型，例如 `aeolus_dataset`、`hive_table`、`clickhouse_table`、`lark_base_table` | error | 字段可选值 |
| Skill 可达性 | process skill 注册 | Process Skill 注册表、`tools/agent_skill_manifest.json` | `process_skill` 必须在注册表中；当前可上传包包含 `review-monitoring-shared`、`warehouse-skill`、`owner-routing`、`monitoring-orchestrator`、`anomaly-touch`、`low-efficiency-strategy-analysis`；新增 skill 必须补注册和 manifest | error | `process_skill` 字段 |
| Skill 可达性 | validation command 存在 | Process Skill 注册表 | 每个 process skill 必须声明 `validation_command` 或等价 smoke check | warning | 注册表命令字段 |
| report type 注册 | 发布类型合法 | Process Skill 注册表、Report Template 注册表、`anomaly-touch` report registry | `default_report_type` 必须属于 process skill 的 `supported_report_types`，且在发布层注册。当前已注册 `low_efficiency_dimension_breakdown`、`low_efficiency_grading`、`low_efficiency_level_detail` | error | report type 字段 |
| 模板注册 | 卡片模板合法 | 触达模板表、Report Template 注册表 | `template_id` 或 `local_template_name` 必须注册；必填变量集合必须与 report type 输出契约匹配 | error | 模板表字段 |
| SQL 模板注册 | `sql_key` 合法 | SOP 规则组表、process skill SQL registry | 启用规则只能引用已注册 `sql_key`。低效策略当前包含 `rule_low_label_rate_notice`、`rule_low_label_rate_p1`、`rule_low_label_rate_p2`、`rule_low_label_rate_p0` | error | 规则组 `sql_key` |
| SQL 参数 | 参数类型合法 | SOP 规则组表、SQL 模板参数定义 | `sql_params` 必须满足模板参数类型，逻辑字段必须在 `field_map` 中 | error | 参数名和可选逻辑字段 |
| 安全红线 | 禁止原始凭证 | 所有配置表 | 不允许出现 access token、app secret、个人 open_id 临时粘贴、未登记 chat_id | blocker | 具体字段与脱敏建议 |

### 2.2 SOP lint 矩阵

| 检查域 | 检查项 | 主要输入 | 校验规则 | 失败级别 | 修复提示粒度 |
|---|---|---|---|---|---|
| SOP 启停 | SOP 是否启用 | SOP 注册表 | `enabled=true` 才能进入自动运行；`enabled=false` 只能允许手动 lint 和 dry-run | error | `enabled` 字段 |
| 节点顺序 | 节点拓扑合法 | SOP 节点表 | 合法顺序为感知/数据就绪、判断、路由、报告发布、触达、跟进、复盘；触达不能早于路由，事件写入不能早于判断 | error | 节点表 `node_order` |
| 节点启停 | 依赖节点完整 | SOP 节点表 | 启用 `event_touch` 时必须启用或显式跳过 `owner_routing`；启用 `report_publish` 时必须有 report type 和模板 | error | 节点启停字段 |
| 规则组完整 | 规则组字段完整 | SOP 规则组表 | 每个启用规则组必须有 `rule_group_id`、`sop_level_id`、`condition_logic`、`window_policy`、`metric_refs`、`rule_key/sql_key` 或结构化规则描述、`audience_policy` | error | 规则组字段 |
| 规则组完整 | 条件引用存在 | SOP 规则组表、指标表、阈值表 | `condition_logic` 中引用的条件 ID、指标 ID、阈值 ID 必须存在 | error | 规则组表达式 |
| 角色别名 | 角色可解析 | SOP 角色目录表、等级字典、触达策略 | `audience_policy` 中的角色别名必须在 SOP 角色目录中解析到用户、群或升级角色 | error | 角色别名字段 |
| owner source | 来源已注册 | Owner Source 注册表、责任路由表 | 每个 `owner_source_id` 必须声明 `source_type`、`source_ref`、`key_field`、`owner_fields`、`fallback_policy`、`freshness_policy` | error | owner source 记录 |
| route grain | 路由粒度可输出 | Process Skill 注册表、输出契约、规则组表 | `route_grain` 必须存在于 process skill 输出字段中，例如低效策略输出 `reason` 或 `strategy`，审核延时输出 `queue_id`、`queue_name`、`group_id` 或 `scene` | error | `route_grain` 与输出字段 |
| 触达策略 | 自动触达边界 | SOP 注册表、触达配置 | `auto_send=true` 只允许在 canary/active 下启用；shadow 下必须强制 false | blocker | `auto_send` 和 `run_mode` |
| 状态策略 | 状态回写目标合法 | 状态策略表、事件表 | shadow 不写事件主表，只写 shadow run summary；canary 只能写 scoped SOP/run_id | error | 状态策略字段 |

### 2.3 等级 lint 矩阵

| 检查域 | 检查项 | 主要输入 | 校验规则 | 失败级别 | 修复提示粒度 |
|---|---|---|---|---|---|
| 等级引用 | `sop_level_id` 存在 | SOP 规则组表、SOP 等级字典表 | 规则组引用的 `sop_level_id` 必须属于同一 `sop_id`，不能跨 SOP 复用 | error | 规则组 `sop_level_id` |
| 等级作用域 | 标签不全局化 | SOP 等级字典表 | `P0/P1/P2/notice` 只作为当前 SOP 的 `level_label`，系统不能按全局枚举解释 SLA 或受众 | error | 等级字典 `sop_id` |
| 优先级 | 优先级完整 | SOP 等级字典表 | `priority_order` 必填且同一 SOP 内唯一，数值越小优先级越高 | error | `priority_order` |
| SLA | SLA 完整 | SOP 等级字典表 | `sla_minutes` 和 `sla_text` 必填；若无 SLA 需显式配置 `sla_minutes=null` 和解释 | error | SLA 字段 |
| 人工确认 | 确认策略完整 | SOP 等级字典表 | `requires_human_confirm` 必填；P0/P1 或高 normalized severity 不允许为空 | error | 人工确认字段 |
| 默认受众 | 默认受众策略完整 | SOP 等级字典表、角色目录表 | `default_audience_policy` 必填，且角色别名可解析 | error | 受众策略字段 |
| 升级策略 | 升级规则完整 | SOP 等级字典表 | 高等级必须配置 `escalation_policy`，包含升级角色和升级时限 | warning/error | 升级策略字段 |
| 启停一致 | 等级启用状态 | SOP 等级字典表、规则组表 | 规则组不能引用 `enabled=false` 的等级 | error | 等级启停字段 |

### 2.4 dry-run 矩阵

| 阶段 | 检查项 | 输入 | dry-run 行为 | 通过标准 | 失败停止规则 |
|---|---|---|---|---|---|
| 数据就绪 | 分区、行数、权限、字段映射 | 数据源表、语义指标绑定、warehouse 输出 | 只读探测目标分区、行数、权限和字段存在性，记录 freshness 与 provenance | 分区满足延迟策略，核心字段存在，行数高于最小样本量 | 停止在数据 gate，不渲染报告 |
| SQL 渲染 | 模板与参数 | 规则组 `sql_key/sql_params`、process skill registry | 调用已注册模板渲染 SQL，不执行运营手写 SQL | SQL 只来自注册模板，逻辑字段均在 `field_map` 内 | 停止该规则组 |
| `LIMIT 1` 探测 | 查询可执行性 | 渲染 SQL、数据源权限 | 在安全上下文中做 `LIMIT 1` 或等价小样本探测 | 查询语法和权限通过，返回列包含输出契约字段 | 停止该 SOP 自动运行 |
| 产物生成 | process skill 输出契约 | dry-run run dir | 生成标准产物预览：`summary.json`、明细 CSV、汇总 CSV、workbook、provenance | 下游需要的文件存在，字段完整，行数和 hash 写入摘要 | 不进入发布层 |
| 路由模拟 | owner source、route grain | 命中行、责任映射、角色目录 | 解析 `route_result`，但不触达、不建群、不写真实 touch record | 每条命中行有 owner 或显式 `missing_object_owner=true` | auto-touch 禁止；报告仍可标注缺 owner |
| 卡片渲染 | report type、模板变量 | run dir、sheet URL 占位符、route_result | 使用发布层 dry-run 生成带 `_meta` 的卡片和发送版卡片 | 发送版卡片无内部 `_meta`，表格列宽不小于 80px，变量无缺失 | 不允许发送 |
| 卡片安全 | 等级、chat_id、数据 hash | 卡片 `_meta`、route_result、命中行 | 校验等级匹配、chat_id 匹配、数据 hash 匹配 | `level`、`route_chat_id`、`_data_hash` 全部匹配 | 阻断触达 |
| 发布 dry-run | sheet 与 publish summary | workbook、report type、目标对象 | 只生成 `card_json`、带 meta 卡片和 publish summary，不导入或发送 | `sent=false`，产物路径可读取，idempotency key 安全化 | 不进入真实发布 |

## 3. validation report 输出格式

validation report 必须让运营能按表名、记录、字段修复。建议输出 JSON，同时可渲染成表格视图。

```json
{
  "schema_version": "validation_report.v1",
  "run_id": "validation_20260706_180000",
  "config_version": "sop_config_20260706_01",
  "mode": "shadow",
  "scope": {
    "sop_id": "review_latency",
    "business_domain": "efficiency",
    "process_skill": "review-latency-analysis"
  },
  "summary": {
    "status": "failed",
    "blocker_count": 1,
    "error_count": 3,
    "warning_count": 2,
    "dry_run_executed": false
  },
  "findings": [
    {
      "severity": "error",
      "category": "sop_lint",
      "check_id": "SOP_ROUTE_GRAIN_OUTPUT_FIELD",
      "table_name": "SOP规则组表",
      "view_name": "启用规则",
      "record_key": "review_latency_p1_delay_or_forecast",
      "field_name": "route_grain",
      "field_label": "路由粒度",
      "current_value": "queue",
      "expected_value": "queue_id | queue_name | group_id | scene",
      "message": "route_grain 不在 review-latency-analysis 输出契约中。",
      "fix_hint": "将 route_grain 改为输出字段 queue_id，或在 process skill 输出契约中注册 queue。",
      "owner_role": "人审运营",
      "can_auto_fix": false
    },
    {
      "severity": "blocker",
      "category": "touch_safety",
      "check_id": "TOUCH_SHADOW_AUTO_SEND",
      "table_name": "触达配置表",
      "view_name": "SOP触达策略",
      "record_key": "review_latency_p0_touch",
      "field_name": "auto_send",
      "field_label": "是否自动触达",
      "current_value": true,
      "expected_value": false,
      "message": "shadow 模式禁止真实触达。",
      "fix_hint": "将 auto_send 改为 false，或等 canary 审批后再打开。",
      "owner_role": "人审运营",
      "can_auto_fix": false
    }
  ],
  "dry_run": {
    "status": "skipped",
    "skipped_reason": "lint_has_blocker",
    "planned_checks": [
      "data_readiness",
      "sql_render",
      "limit_1_probe",
      "artifact_generation",
      "card_render"
    ],
    "artifacts": []
  },
  "operator_repair_view": {
    "group_by": ["table_name", "field_name"],
    "primary_columns": [
      "severity",
      "table_name",
      "record_key",
      "field_name",
      "current_value",
      "expected_value",
      "fix_hint"
    ]
  }
}
```

输出约定：

- `severity=blocker`：存在安全红线或模式冲突，必须停止。
- `severity=error`：配置不可运行，不能进入自动分析或触达。
- `severity=warning`：可进入人工 dry-run，但不能进入 active。
- `table_name`、`record_key`、`field_name` 是运营修复的最小定位信息。
- `expected_value` 必须给出枚举、关联键或字段集合，避免只写“配置错误”。
- dry-run 产物只记录路径、hash、行数和预览 URL，不写真实事件主表。

## 4. 从旧单体 Skill 到多 Skill 的迁移阶段

| 阶段 | 目标 | 运行方式 | 写入与触达边界 | 退出条件 |
|---|---|---|---|---|
| baseline | 保护当前已跑通路径 | 继续使用旧 `human-review-monitoring` 参考逻辑和当前低效策略 process skill 直跑路径 | 可写当前产物，可按已验证流程发布报告和卡片 | 基线命令、产物、发布链路可复现 |
| mapping | 把旧能力映射到新层 | 不执行新链路，只完成 warehouse、domain reference、process skill、owner-routing、anomaly-touch、orchestrator 的职责映射 | 不写事件，不触达 | 旧能力都有目标层归属 |
| shadow | 新多 Skill 链路只读双跑 | 新 orchestrator 读取 SOP-first 配置并运行 dry-run，产物与 baseline 对比 | 不写事件主表，不真实触达，只生成 shadow summary | 差异可解释，lint/dry-run 连续通过 |
| canary | 小范围真实发布 | 选择一个 SOP 或一个等级打开新链路发布，例如低效策略 P2 | 只允许 scoped SOP/run_id 写状态和发布，其他仍走 baseline | smoke test 通过，无误触达 |
| active | 新架构成为默认入口 | 多 SOP 默认走 orchestrator，旧单体仅保留参考 | 按 SOP 策略写事件、发布、触达 | 连续周期稳定，回滚包和配置快照完整 |
| rollback | 恢复上一稳定版本 | 切回 baseline 或上一稳定入口、配置版本、Skill 包 | 停止新链路写入和触达 | 基线 smoke test 全部通过 |

迁移原则：

- 旧 `human-review-monitoring` 只作为参考实现，不复制成新的单体 Skill。
- 每迁移一个行为，先明确目标层：数据取数归 `warehouse-skill`，业务判断归 process skill，路由归 `owner-routing`，报告和触达归 `anomaly-touch`，配置和公共校验归 `review-monitoring-shared`，流程权威归 `monitoring-orchestrator`。
- baseline 到 shadow 必须双跑同一 period，并输出差异报告。
- shadow 到 canary 必须先通过 lint、dry-run、report publishing dry-run 和人工验收。

## 5. 四个端到端验收用例

### 5.1 低效策略 P2

| 验收环节 | 标准 |
|---|---|
| 配置读取 | 读取 `sop_id=low_efficiency_labeling`，process skill 为 `low-efficiency-strategy-analysis`，等级字典中存在当前 SOP 的 P2，规则组引用 `rule_low_label_rate_p2` |
| 取数 | warehouse 或 process skill 使用注册数据源和字段映射，分区满足 freshness，`LIMIT 1` 探测通过 |
| 判断 | P2 规则按已注册模板渲染，输出 P2 命中行，包含 `reason`、打标率、进审量、完审量、`hit_condition` |
| 报告发布 | 产物包含 `summary.json`、`P2.csv` 或综合明细、workbook；发布层支持 `low_efficiency_level_detail` 且 `level=P2`，dry-run 生成卡片和 publish summary |
| 路由/触达 | 可选；如开启，按 `route_grain=reason` 或 `strategy` 解析 owner，缺 owner 行不得发给任意指标负责人 |
| 状态记录 | shadow 只写 shadow summary；canary 可写 scoped run state，必须记录 `config_version`、`rule_group_id`、`route_result` |

通过标准：P2 查询结果与 baseline 在同一 period 下主要行数和 Top 命中原因可解释一致，报告卡片通过等级、chat_id、hash 校验。

### 5.2 机审标签维度拆解

| 验收环节 | 标准 |
|---|---|
| 配置读取 | 读取低效策略 SOP 下的维度拆解运行模式，report type 为 `low_efficiency_dimension_breakdown`，维度包含机审一级标签和 `reason` |
| 取数 | 数据源字段映射包含 `mach_root_label_name`、`reason`、进审、完审、打标、日期字段 |
| 判断 | 不做等级升级，仅按阈值识别低打标率组合，输出标签维度汇总和明细 |
| 报告发布 | 产物包含 `summary.json`、标签 reason 明细 CSV、标签汇总 CSV、workbook；dry-run 卡片表格列宽不小于 80px |
| 路由/触达 | 默认报告-only；如后续触达，必须先定义标签或 reason owner source |
| 状态记录 | 记录分析 period、维度组合、阈值、产物路径、fallback reason |

通过标准：能复现“机审一级标签 × reason”的维度拆解结果，报告可预览，不要求自动触达。

### 5.3 审核延时 SOP

| 验收环节 | 标准 |
|---|---|
| 配置读取 | 读取 `sop_id=review_latency`，process skill 为未来 `review-latency-analysis`，该 skill 必须先进入 Process Skill 注册表和上传 manifest 后才能 canary |
| 取数 | 数据源覆盖进审增幅、机审增幅、实时延时、预计全天进审、目标值；支持 `10min`、连续窗口、日预测窗口 |
| 判断 | 根据 SOP 内 P2/P1/P0 规则组判断，不依赖全局 P0/P1/P2 枚举 |
| 报告发布 | report type 需注册，例如 `review_latency_summary`；模板变量包含队列、群组、场景、指标值、命中规则、SLA、受众 |
| 路由/触达 | 可选；按 `queue_id`、`queue_name`、`group_id` 或 `scene` 解析对象 owner，再扩展等级受众 |
| 状态记录 | 写入 run summary、命中规则组、等级、route_result、人工确认状态、SLA 截止时间 |

通过标准：P2/P1/P0 三类规则都能被配置表达，shadow 下只产报告和路由预览，canary 前通过卡片安全校验。

### 5.4 未来质量域自动处置准确率

| 验收环节 | 标准 |
|---|---|
| 配置读取 | 读取未来 `sop_id=auto_disposal_accuracy`，business domain 为质量域，process skill 和 domain reference 必须先注册 |
| 取数 | warehouse 解析自动处置结果、人工复核结果、误处置/漏处置样本、模型或策略维度 |
| 判断 | process skill 输出准确率、召回、误处置率、样本量守卫和命中等级，规则只引用注册模板或结构化条件 |
| 报告发布 | report type 需注册，例如 `quality_auto_disposal_accuracy`；模板展示指标、样本、趋势、置信度和 fallback reason |
| 路由/触达 | 可选；按模型、策略、项目或场景解析质量 owner，缺 owner 只进入报告和待补 owner 队列 |
| 状态记录 | 记录质量域 config version、指标口径、样本窗口、route_result、是否人工确认 |

通过标准：无需改低效策略代码即可新增质量域 SOP；未注册 process skill 或 report type 时 lint 必须失败。

## 6. 审核延时 SOP 规则组样例

以下 P2/P1/P0 只属于 `sop_id=review_latency`。它们不是全局等级枚举，不能自动套用低效策略 SOP 的 SLA、受众或人工确认策略。

### 6.1 等级字典样例

| sop_id | sop_level_id | level_label | normalized_severity | priority_order | sla_minutes | requires_human_confirm | default_audience_policy | enabled |
|---|---|---|---|---:|---:|---|---|---|
| review_latency | review_latency_p2 | P2 | medium | 3 | 60 | false | 治理 BP、审核 VOC POC、人审运营、交付调度负责人 | true |
| review_latency | review_latency_p1 | P1 | high | 2 | 30 | true | 治理 BP+1、VOC 负责人、人审运营负责人、群组负责人 | true |
| review_latency | review_latency_p0 | P0 | critical | 1 | 10 | true | 治理负责人、CQC 负责人 | true |

### 6.2 规则组表达样例

| rule_group_id | sop_level_id | condition_logic | window_policy | metric_refs | threshold_refs | route_grain | audience_policy |
|---|---|---|---|---|---|---|---|
| review_latency_p2_growth_forecast | review_latency_p2 | `ingress_growth_rate >= 0.30 AND forecast_full_day_ingress > target_ingress` | 单个当前窗口 + 当日预测 | 进审增幅、预计全天进审、目标值 | 增幅 30%、目标值 100% | `queue_id` 或 `scene` | 治理 BP、审核 VOC POC、人审运营、交付调度负责人 |
| review_latency_p1_delay_or_forecast | review_latency_p1 | `(machine_audit_growth_rate >= 0.30 AND realtime_latency_minutes >= 60) OR forecast_full_day_ingress > target_ingress * 1.20` | 当前窗口 + 当日预测 | 机审增幅、实时延时、预计全天进审、目标值 | 增幅 30%、延时 60 分钟、目标值 120% | `queue_id` 或 `group_id` | 治理 BP+1、VOC 负责人、人审运营负责人、群组负责人 |
| review_latency_p0_continuous_or_forecast | review_latency_p0 | `ingress_growth_rate >= 1.00 FOR 2 consecutive 10min windows OR forecast_full_day_ingress > target_ingress * 1.50` | 连续 2 个 10min 窗口 + 当日预测 | 进审增幅、预计全天进审、目标值 | 增幅 100%、目标值 150% | `queue_id` 或 `group_id` | 治理负责人、CQC 负责人 |

配置约束：

- 规则组必须引用同一 SOP 下的 `sop_level_id`。
- `route_grain` 必须在 `review-latency-analysis` 输出契约中存在。
- P1/P0 触达前必须有人工确认策略，除非事故应急模式有单独审批记录。
- 受众角色必须在 `review_latency` 的角色目录中解析，不能复用低效策略 SOP 的角色含义。

## 7. 低效策略 owner mapping 样例

### 7.1 Owner Source 注册样例

| owner_source_id | sop_id | route_grain | source_type | source_ref | key_field | owner_fields | fallback_policy | freshness_policy |
|---|---|---|---|---|---|---|---|---|
| reason_owner_mapping | low_efficiency_labeling | reason | lark_base_table | 低效策略 reason owner 映射表 | route_key | owner_user、collaborators、escalation_users、default_chat_id | missing_owner_only | 7 天内更新或人工确认 |
| strategy_owner_mapping | low_efficiency_labeling | strategy | lark_base_table | 低效策略 strategy owner 映射表 | route_key | owner_user、collaborators、escalation_users、default_chat_id | missing_owner_only | 7 天内更新或人工确认 |

### 7.2 映射记录样例

| sop_id | route_grain | route_key | route_key_alias | owner_role | owner_user | collaborators | escalation_users | default_chat_id | enabled | priority |
|---|---|---|---|---|---|---|---|---|---|---:|
| low_efficiency_labeling | reason | N1_chuxing_model_llm_pe_review | 出行模型 LLM PE 审核 | 业务 POC | ou_owner_a | ou_ops_a | ou_manager_a | oc_reason_a | true | 10 |
| low_efficiency_labeling | reason | political_figure_risk_review | 领导人风险审核 | 业务 POC | ou_owner_b | ou_ops_a | ou_manager_b | oc_reason_b | true | 20 |
| low_efficiency_labeling | strategy | strategy_low_label_rate_safe_v1 | 低打标率安全策略 v1 | 策略 owner | ou_strategy_a | ou_ops_b | ou_strategy_manager | oc_strategy_a | true | 10 |

### 7.3 missing owner 处理

- 如果命中行的 `reason` 或 `strategy` 没有映射，`owner-routing` 必须返回 `missing_object_owner=true`、`route_confidence=low`，并保留原始 route key。
- 不允许回退到任意“指标负责人”，除非 Owner Source 注册表显式配置了 `manual_fallback` 且角色目录可解析。
- 报告发布仍可继续，但必须展示 `missing_owner_count` 和缺失 owner 明细。
- 自动触达必须阻断缺 owner 行；可以只把缺 owner 汇总发给 SOP 运营群或进入待补 owner 队列。
- 状态记录应标记为 `route_pending_owner`，补齐 owner 后才能进入触达确认。

## 8. baseline 与 rollback runbook

### 8.1 当前已跑通 baseline

baseline 由以下能力组成，任何新架构改造不得删除或覆盖：

| 基线项 | 已验证能力 | 保护要求 |
|---|---|---|
| 低效策略 P2 查询 | `rule_low_label_rate_p2` 模板渲染、参数校验、动态天数、P2 命中结果 | 保留模板、测试和历史样例产物 |
| 低效策略全等级查询 | P0/P1/P2/notice 模板均已注册并有测试覆盖 | 新等级模型不得破坏低效策略 SOP 内等级 |
| 机审标签维度拆解 | 机审一级标签 × reason 维度拆解、汇总和明细导出 | 保留 report type 和产物字段 |
| 飞书表格发布 | workbook 导入或复用 sheet URL | 发布 dry-run 必须先通过 |
| 飞书卡片推送 | Card 2.0 渲染、发送版剥离 `_meta`、列宽不小于 80px、idempotency key 安全化、bot fallback | 正式发送前校验等级、chat_id、数据 hash |

baseline 产物建议保存在只读位置，并记录：

- Git commit 或 tag。
- `tools/agent_skill_manifest.json` 版本。
- `dist/agent_upload/zips/*.zip` 的文件名、生成时间、hash。
- 低效策略同一 period 的 `summary.json`、CSV、workbook、publish summary。
- 飞书配置中心 schema 和数据快照版本。

不要把唯一可回滚上传包只放在会被清理的 `dist/agent_upload` 下。生成后的稳定 zip 需要同步到 release 附件、云盘或其它只读归档。

### 8.2 代码回滚策略

- 每次进入 shadow、canary、active 前创建 Git tag，例如 `baseline-low-efficiency-publish-YYYYMMDD`、`sop-shadow-YYYYMMDD`。
- 主干保留稳定分支，实验性 orchestrator 或新 SOP 走独立分支和 PR。
- 回滚优先使用 revert commit，避免破坏其他人的未提交变更。
- PR 合并门禁至少包含：低效策略 SQL 模板测试、卡片校验测试、报告发布 dry-run 测试、打包脚本验证。
- active 切换前必须确认新旧入口都能独立运行，且 baseline 命令未被删除。

### 8.3 Skill 上传包回滚策略

- 保留上一稳定的单 Skill zip：`review-monitoring-shared.zip`、`warehouse-skill.zip`、`owner-routing.zip`、`anomaly-touch.zip`、`low-efficiency-strategy-analysis.zip`。
- 上传平台当前要求单 Skill zip 根目录直接包含 `SKILL.md`；如果总包报 `Missing file: SKILL.md`，只上传 `dist/agent_upload/zips/<skill-name>.zip`。
- `tools/agent_skill_manifest.json` 是上传范围权威，新增 skill 必须先进入 manifest、通过 frontmatter name 校验、路径改写和排除规则校验。
- 每个 zip 需要记录 manifest 版本、构建时间、Git commit、hash、上传人和平台 active 版本。
- 新包 smoke test 失败时，停止继续上传后续包，重新上传上一稳定 zip，并把平台 active version 切回上一稳定记录。

### 8.4 飞书多维表格配置回滚策略

- 配置中心必须有 `config_version`、`effective_start`、`effective_end`、`enabled`、`updated_by`、`updated_at`。
- schema 变更前导出 schema 快照，包括表、字段、视图、字段类型、选项值、关联关系。
- 数据变更前导出数据快照，包括 SOP 注册、节点、规则组、等级字典、角色目录、owner source、责任映射、模板注册。
- 旧 9 表配置在 active 前保持只读保护，不被新 SOP-first 表覆盖。
- 新 schema 不兼容时，运行入口切回上一 `config_version`；lint/dry-run 在恢复前必须停止写事件和触达。

### 8.5 运行入口回滚策略

| 模式 | 默认入口 | 写事件 | 真实触达 | 使用场景 |
|---|---|---|---|---|
| baseline | 旧直跑路径或当前已验证 process skill 路径 | 只写既有路径允许的产物 | 只走已验证发布链路 | 当前稳定生产 |
| shadow | 新 `monitoring-orchestrator` | 不写主事件，只写 shadow summary | 禁止 | 双跑对比 |
| canary | 新 orchestrator 的指定 SOP/等级 | 只写 scoped run state | 只触达 scoped 对象 | 小范围验证 |
| active | 新 orchestrator | 按 SOP 状态策略写入 | 按 SOP 触达策略执行 | 默认新链路 |
| rollback | baseline 或上一稳定 orchestrator | 停止新链路写入 | 停止新链路触达 | 故障恢复 |

入口切换必须是配置化的，至少支持按 `sop_id`、`sop_level_id`、`run_mode`、`config_version` 选择。切换到 rollback 后，新链路未完成 run 必须标记为 `aborted_by_rollback`。

### 8.6 smoke test 基线

| smoke test | 通过标准 |
|---|---|
| P2 查询 | P2 SQL 模板渲染通过，`LIMIT 1` 探测通过，输出字段包含 `reason`、指标值、`hit_condition` |
| 全等级查询 | P0/P1/P2/notice 四类模板均可渲染，测试覆盖未知 `sql_key`、非法参数、非法逻辑字段 |
| 维度拆解 | 机审一级标签 × reason 明细和汇总可生成，`summary.json` 记录 period、阈值、行数、fallback reason |
| report publishing dry-run | `publish_lark_report.py` dry-run 生成发送版 card、带 meta card、publish summary，且 `sent=false` |
| 真实私聊卡片发送 | 仅在人工确认后向测试 open_id 或测试 chat 发送，idempotency key 合法，失败可 fallback bot 身份 |
| 卡片安全校验 | 发送前等级匹配、chat_id 匹配、数据 hash 匹配，发送版卡片不含内部 `_meta` |
| 打包验证 | `tools/package_agent_skills.py` 只清理 `dist/agent_upload`，输出单 Skill zip 和 build summary |

### 8.7 失败停止规则

遇到以下任一情况必须停止新链路：

- lint 出现 `blocker` 或 `error`。
- dry-run 数据就绪、SQL 渲染、`LIMIT 1` 探测、产物生成、卡片渲染任一失败。
- process skill 未注册、report type 未注册、模板未注册、owner source 未注册。
- `route_grain` 不在 process skill 输出中。
- 规则组引用不存在或跨 SOP 的 `sop_level_id`。
- 触达目标 chat_id 与责任路由结果不一致。
- 卡片 hash 与当前命中数据不一致。
- missing owner 行尝试自动触达。
- shadow 模式配置了真实触达或主事件写入。
- 新 Skill 上传包 smoke test 失败。
- 新链路结果与 baseline 同 period 差异无法解释，且影响核心指标或 Top 命中对象。

停止后的保护动作：

- 不写事件主表，只写失败 validation report 和 run summary。
- 不覆盖 baseline 产物目录，所有新产物写入带 `run_id` 和 `config_version` 的独立目录。
- 不触达无关 POC，不创建临时群，不回写 chat_id。
- 不修改旧 9 表只读快照。
- 进入 rollback 时恢复上一稳定入口、上一稳定配置版本和上一稳定 Skill zip。
