# 编排与业务 Process Skill 契约

本文交付 Task 3 与 Task 4 的设计结论，只定义 `monitoring-orchestrator` 与业务 process skill 的职责、运行契约和产物格式，不包含代码实现。

## 1. 设计原则

1. 以 SOP 为一级业务对象。编排层读取启用 SOP、SOP 节点、SOP 规则组、SOP 等级字典和 process skill registry，不再以单个指标作为全链路根对象。
2. `monitoring-orchestrator` 是流程与状态权威，只决定“按什么顺序调用哪些能力、在哪里停、如何审计”。业务指标口径、等级判断、SQL 模板、阈值不写入 orchestrator。
3. 业务 process skill 只负责确定性分析过程：解析输入、完成数据查询或计算、输出命中清单和证据。它不做责任路由、不发飞书、不推进事件状态。
4. 等级标签属于当前 SOP。`P0/P1/P2/notice` 只能作为某个 SOP 的配置值出现，系统不得把它们当全局枚举。
5. 所有下游动作必须消费标准产物目录：`summary.json`、明细 CSV、汇总 CSV、workbook、provenance。报告发布、路由、触达和状态推进都不得临时解析非契约文件。

## 2. `monitoring-orchestrator` Skill 契约

### 2.1 定位

`monitoring-orchestrator` 是人审运营监控体系的横向编排层，目标 `SKILL.md` 应定义为：

| 项 | 契约 |
|---|---|
| Skill 名称 | `monitoring-orchestrator` |
| 所属层 | Horizontal Skill / Flow Authority |
| 核心职责 | 读取 SOP 配置，编译本轮执行计划，调用 process skill、owner-routing、anomaly-touch 或报告发布能力，统一推进运行实例与事件状态，记录审计日志 |
| 直接依赖 | `review-monitoring-shared`、`owner-routing`、`anomaly-touch`、注册过的业务 process skill |
| 可选依赖 | `warehouse-skill`、`lark-base`、`lark-sheets`、`lark-im`、`lark-contact`，由具体节点和运行模式决定 |
| 状态权威 | 运行实例状态与事件“当前状态”的推进只能由 orchestrator 执行 |
| 配置来源 | SOP 注册表、SOP 节点表、SOP 规则组表、SOP 等级字典表、Process Skill 注册表、Report Template 注册表、责任路由/Owner Source/触达策略配置 |

### 2.2 输入

标准输入应支持以下字段：

| 字段 | 必填 | 说明 |
|---|---:|---|
| `run_mode` | 是 | `manual`、`scheduled`、`report_only`、`touch_execute` 四选一 |
| `sop_id` | 条件必填 | 指定 SOP；未传时只允许在 `manual` 或 `scheduled` 中读取全部启用 SOP |
| `metric_id` | 否 | 兼容旧入口；必须能解析到唯一 SOP 观测对象 |
| `period` | 否 | 如“近7天”；显式 `period_start/period_end` 优先 |
| `period_start` / `period_end` | 否 | 明确分析窗口 |
| `run_date` | 否 | 基准日期，默认当前运行日 |
| `data_lag_days` | 否 | 数据延迟天数，默认来自 SOP 或数据源配置 |
| `config_version` | 否 | 指定配置快照；为空时读取当前生效版本 |
| `report_type` | 否 | 覆盖默认报告类型；必须在 registry 中注册 |
| `dry_run` | 否 | 只读验证，不写事件、不发消息、不建群、不回写触达记录 |
| `resume_from` | 否 | `touch_execute` 或重试时使用，例如 `run_id`、`artifact_hash`、`event_ids` |
| `operator` | 否 | 手动运行发起人，用于审计 |

### 2.3 输出

标准输出是一份运行摘要，不承载大结果集：

| 字段 | 说明 |
|---|---|
| `run_id` | 本轮运行唯一 ID |
| `sop_id` | 当前 SOP |
| `run_mode` | 实际运行模式 |
| `run_status` | `completed`、`no_hits`、`blocked`、`failed`、`partial_success`、`waiting_confirm`、`skipped` |
| `process_run_dir` | process skill 标准产物目录 |
| `summary_path` | `summary.json` 路径 |
| `event_ids` | 已创建或更新的事件 ID；report-only/dry-run 可为空或为 preview ID |
| `publish_result` | 报告发布结果，如 sheet URL、message_id、report_hash |
| `route_result_refs` | 路由结果引用，按事件或业务对象分组 |
| `touch_result` | 触达发送结果；report-only 不产生 |
| `audit_log_path` | 本轮审计日志路径 |
| `stop_reason` | 被阻断或失败时的停止原因 |

### 2.4 职责边界

`monitoring-orchestrator` 必须做：

- 读取并缓存本轮配置快照，记录 `config_version` 和配置哈希。
- 校验 SOP 是否启用、节点顺序是否合法、process skill/report type 是否注册、等级字典是否完整。
- 按 `run_mode` 与 SOP 节点表编译执行计划。
- 调用数据就绪 gate，未就绪时停止或等待重试，不产出“无命中”。
- 调用已注册 process skill，并校验其标准输出目录。
- 按当前 SOP 等级字典解析 process skill 输出的 `sop_level_id` 或 `level_label`。
- 根据节点配置调用报告发布、owner-routing、anomaly-touch。
- 统一推进运行状态和事件状态。
- 记录节点输入引用、输出引用、失败原因、fallback reason、side effect 和产物哈希。

`monitoring-orchestrator` 禁止做：

- 写业务阈值、业务规则、指标口径或 SQL 模板。
- 把 `P0/P1/P2/notice` 当作全局等级枚举。
- 直接拼接业务 SQL 或执行运营配置中的任意 SQL/Python 片段。
- 绕过 `owner-routing` 解析责任人。
- 绕过 `anomaly-touch` 的人工确认、哈希校验、chat_id 校验和发送前剥离内部字段。
- 在 dry-run/report-only 模式下写事件主表、建群、发送正式消息或写触达记录。

## 3. 四类运行模式

| 运行模式 | 触发来源 | 默认节点范围 | 写副作用 | 典型用途 |
|---|---|---|---|---|
| `manual` 手动运行 | 人工或 Agent 单次触发 | 配置读取、lint、数据就绪、process 分析、事件预览/创建、报告发布、可选路由触达 | 由 `dry_run` 与 SOP 节点决定 | 验证新 SOP、手动补跑、排障复现 |
| `scheduled` 定时运行 | 调度器按 SOP `run_frequency` 触发 | 启用 SOP 全链路，严格执行 lint 和数据就绪 gate | 可写运行实例、事件、报告、触达记录 | 稳定上线后的自动巡检 |
| `report_only` 报告-only | 人工、定时或 shadow run | 配置读取、数据就绪、process 分析、报告发布、审计 | 只允许写运行实例和报告发布记录；不得写触达记录或发正式事件触达 | 双跑对比、周报/日报、只看结果不打扰 POC |
| `touch_execute` 触达执行 | 基于已有 run/event/artifact 触发 | 读取既有产物、校验 artifact hash、路由、触达生成、人工确认、发送、状态推进 | 可写触达记录、事件触达摘要和状态 | 人工确认后发送、发送失败重试、从 report-only 升级到正式触达 |

运行模式对节点的覆盖规则：

1. `manual` 与 `scheduled` 可以执行完整节点，但仍受 SOP 节点启停控制。
2. `report_only` 强制关闭 `owner_routing`、`touch_render`、`human_confirm`、`touch_send` 和触达记录写入；即使 SOP 配置中这些节点启用，也只记录为 `skipped_by_run_mode`。
3. `touch_execute` 不重新执行 process analysis，除非显式要求 `rerun_analysis=true` 且 SOP 允许；默认从已存在的 `summary.json`、CSV、workbook 和 provenance 恢复。
4. `dry_run=true` 是所有模式的安全覆盖层：允许真实读配置、读数据和渲染卡片，但任何写副作用都必须短路为预览。

## 4. SOP 节点驱动的执行图

### 4.1 节点类型

SOP 节点表至少应支持以下 `node_type`：

| `node_type` | 职责 | 可被关闭 | 关闭影响 |
|---|---|---:|---|
| `config_load` | 读取 SOP、节点、等级、registry、规则和模板配置 | 否 | 关闭则 SOP 不可运行 |
| `config_lint` | 检查必填字段、关联关系、枚举值、Skill 可达性 | 否 | 失败则停止 |
| `data_ready_gate` | 检查分区、权限、行数、字段映射和 freshness | 条件可关 | 自动运行不允许关闭；手动调试关闭时必须标记低置信 |
| `process_analysis` | 调用业务 process skill 生成标准产物目录 | 否 | 关闭则无分析结果，后续节点不可运行 |
| `event_build` | 将命中行转成事件或事件预览 | 是 | report-only 可跳过；正式触达前必须有事件或可追溯 preview |
| `report_publish` | 调用报告发布入口导入表格、渲染报告卡片 | 是 | 关闭则不生成报告链接 |
| `owner_routing` | 调用 owner-routing 解析 owner、协作方、升级人和 SLA | 是 | 关闭后不能执行正式触达 |
| `touch_render` | 调用 anomaly-touch 生成触达卡片并计算哈希 | 是 | 关闭后不能发送 |
| `human_confirm` | 根据当前 SOP 等级字典执行人工确认门禁 | 条件可关 | 若等级要求确认，则不能通过配置关闭 |
| `touch_send` | 通过 anomaly-touch 发送消息、建群或回写触达记录 | 是 | 关闭则停在报告或待触达状态 |
| `state_update` | 推进运行实例和事件状态 | 否 | 只有 dry-run 可短路为状态预览 |
| `audit_finalize` | 写本轮节点审计摘要和最终运行摘要 | 否 | 失败时仍需保留已产生的节点日志 |

### 4.2 节点执行图

默认完整执行图：

```text
config_load
  -> config_lint
  -> data_ready_gate
  -> process_analysis
  -> event_build
  -> report_publish
  -> owner_routing
  -> touch_render
  -> human_confirm
  -> touch_send
  -> state_update
  -> audit_finalize
```

分支规则：

- `process_analysis` 返回 `no_hits`：跳过 `event_build`、`owner_routing`、`touch_render`、`touch_send`，进入 `audit_finalize`，运行状态为 `no_hits`。
- `report_only`：执行到 `report_publish` 后进入 `audit_finalize`。
- `touch_execute`：从 `config_load`、`config_lint`、artifact 校验开始，跳过 `data_ready_gate` 和 `process_analysis`，从 `event_build` 或 `owner_routing` 继续。
- 任一节点返回 `blocked`：停止后续依赖节点，进入 `audit_finalize`；已完成且安全的副作用保留，不做自动回滚。
- 同等级多业务对象命中：全部生成事件或事件预览；触达阶段按 `chat_strategy` 分组，不能只处理最高一条。

### 4.3 节点顺序编译规则

orchestrator 每轮启动时将 SOP 节点表编译成执行计划：

1. 只读取 `sop_id` 对应且 `enabled=true` 的节点。
2. 按 `node_order` 从小到大排序；同序号节点必须显式声明互不依赖，否则 lint 失败。
3. 检查依赖关系：例如 `touch_send` 依赖 `touch_render` 与 `owner_routing`；`owner_routing` 依赖 process 输出中存在 `route_grain` 对应字段。
4. 将 `run_mode` 覆盖层应用到节点计划，例如 report-only 强制跳过触达相关节点。
5. 将节点计划写入审计日志，后续节点只能按该快照执行，不允许运行中重新读取配置改变顺序。

## 5. 当前 SOP 等级字典读取规则

orchestrator 处理等级时必须遵循以下规则：

1. 在 `config_load` 阶段按 `sop_id` 读取 SOP 等级字典，生成本轮 `level_map`。
2. `level_map` 同时支持按 `sop_level_id` 和 `level_label` 查找，但优先使用 `sop_level_id`。
3. process skill 输出的每一条命中必须能解析到当前 SOP 的一个等级；无法解析时，该命中行标记为 `invalid_level`，正式运行停止，dry-run/report-only 可输出 validation report。
4. `priority_order` 只来自当前 SOP 等级字典，用于同一 SOP 内排序和同一业务对象多规则命中取最高等级。
5. `normalized_severity` 仅用于跨 SOP 看板排序、颜色和汇总，不得替代当前 SOP 的 `level_label`、SLA、受众和人工确认策略。
6. owner-routing、anomaly-touch 和报告模板接收完整 `level_config`，包括 `sop_level_id`、`level_label`、`priority_order`、`sla_minutes`、`requires_human_confirm`、`default_audience_policy`。

示例：低效 SOP 可以配置 `notice/P2/P1/P0`；审核延时 SOP 可以配置 `黄灯/橙灯/红灯` 或 `P2/P1/P0`。两个 SOP 即使标签同名，也必须按各自 `sop_id` 读取不同 SLA、受众和门禁。

## 6. 状态机契约

### 6.1 运行实例状态

运行实例状态用于描述一轮 orchestrator 的执行进度：

| 状态 | 含义 | 进入条件 |
|---|---|---|
| `created` | 运行实例已创建 | 接收输入并生成 `run_id` |
| `plan_ready` | 节点计划已编译 | 配置读取和 lint 通过 |
| `waiting_data` | 等待数据就绪 | 数据未就绪，允许重试 |
| `analysis_running` | process skill 执行中 | 数据 gate 通过 |
| `analysis_ready` | 标准产物目录已生成并通过校验 | process skill 成功 |
| `no_hits` | 本轮无命中 | process skill 明确返回无命中 |
| `report_published` | 报告已发布 | report_publish 成功 |
| `waiting_touch` | 等待路由或触达 | 有事件/命中，触达节点未完成 |
| `waiting_confirm` | 等待人工确认 | 当前等级字典要求确认 |
| `touch_sent` | 正式触达已发送 | anomaly-touch 返回 sent |
| `completed` | 本轮正常结束 | 所有应执行节点完成 |
| `partial_success` | 部分对象成功，部分对象 blocked/failed | 分组触达或多事件处理中出现局部失败 |
| `blocked` | 安全门禁或配置问题阻断 | 缺配置、缺路由、哈希不匹配、未确认等 |
| `failed` | 系统错误失败 | 权限、查询、发布、发送等异常且不可降级 |

### 6.2 事件状态推进

默认完整事件流转关系：

```text
待判断 -> 待归因 -> 待触达 -> 处理中 -> 待验证 -> 待关闭 -> 已解决
                 ↘ 误报
                 ↘ 已升级
                 ↘ 失败转人工
```

MVP 或 report-only 可以使用子集：

- MVP 手动链路：`待判断 -> 待触达 -> 处理中`。
- report-only：不写正式事件状态，只写运行实例状态和事件预览。
- touch_execute：从 `待触达` 或已确认的事件预览进入 `处理中`。

推进规则：

1. process skill 只输出命中行，不写事件状态。
2. `event_build` 负责创建事件或事件预览，初始状态为 `待判断` 或 SOP state policy 指定的等价状态。
3. 判断完成且非误报后，由 orchestrator 推进到 `待触达`；如果 SOP 启用了归因节点，则先推进到 `待归因`。
4. 触达发送成功后，由 orchestrator 推进到 `处理中`。
5. `requires_human_confirm=true` 的等级在确认前不得推进到 `处理中`。
6. 同一业务对象命中多条规则时，按当前 SOP `priority_order` 取最高等级合并为一个事件；不同业务对象全部保留。
7. 状态枚举值的落库名称以 shared/base schema 或 SOP state policy 注册值为准，本文只定义逻辑流转。

### 6.3 停止规则

以下情况必须停止当前 SOP 或当前事件分组：

| 停止原因 | 停止位置 | 后续动作 |
|---|---|---|
| SOP 未启用或 process skill 未注册 | `config_lint` | 不进入分析，输出 validation report |
| SOP 等级字典缺失或规则引用未注册等级 | `config_lint` | 不运行该规则组 |
| 数据未就绪、权限不足、字段缺失 | `data_ready_gate` | 标记 `waiting_data` 或 `failed`，不得解释为无命中 |
| process 输出目录缺少必需文件 | `process_analysis` 后 | 标记 `blocked`，不得触达 |
| 命中行等级无法解析到当前 SOP | `event_build` | 标记 `invalid_level`，停止正式执行 |
| `missing_route=true` 或 owner source 未注册 | `owner_routing` | 转人工补配置，不发给兜底 POC，除非配置了显式 fallback |
| 模板必填变量缺失 | `touch_render` | 标记 `missing_variables`，不发送残缺消息 |
| 卡片哈希、等级、chat_id 校验失败 | `touch_send` 前 | 标记 `blocked`，不调用发送接口 |
| 高风险等级未人工确认 | `human_confirm` | 停在 `waiting_confirm` |
| dry-run/report-only | 任意写节点 | 写操作短路为预览 |

### 6.4 重试与降级规则

1. 重试必须以节点为单位记录 `attempt`，不得整轮静默重跑覆盖原审计。
2. 只有节点 `retry_policy.enabled=true` 且错误属于 `retryable_error` 时才能自动重试。
3. 数据未就绪优先等待下一调度或人工重跑；不得在同一轮内无限轮询。
4. 查询失败可按注册 fallback 降级：semantic layer -> governed dataset -> curated raw SQL。是否允许 SQLess 兜底必须由 process skill registry 或数据源配置声明。
5. 报告发布失败不影响 process 产物保留；可通过同一 `run_id` 重试 `report_publish`。
6. 触达发送失败应优先使用 `touch_execute` 从已校验产物恢复，不默认重跑分析。
7. 降级到 report-only、manual_fallback 或转人工必须写入 `fallback_reason`，且不得推进到触达成功状态。
8. P0 或当前 SOP 标记为高风险的等级不得自动关闭、不得自动执行不可逆动作。

## 7. 审计日志格式

每轮运行必须生成节点级审计日志，推荐 `run_audit.jsonl`，一行一条节点记录。字段契约如下：

| 字段 | 说明 |
|---|---|
| `audit_version` | 审计格式版本，例如 `orchestrator-audit-v1` |
| `run_id` | 运行实例 ID |
| `attempt` | 节点尝试次数 |
| `sop_id` | SOP ID |
| `run_mode` | 运行模式 |
| `config_version` | 配置快照版本 |
| `node_type` | 当前节点类型 |
| `node_order` | 本轮计划中的节点顺序 |
| `node_status` | `success`、`skipped`、`blocked`、`failed`、`retrying` |
| `started_at` / `finished_at` | 节点开始和结束时间 |
| `input_ref` | 输入对象引用，避免写入大数据或敏感数据 |
| `input_hash` | 输入哈希 |
| `output_ref` | 输出文件、事件、消息或报告引用 |
| `output_hash` | 输出哈希 |
| `process_skill` | 当前调用的 process skill；非分析节点可为空 |
| `report_type` | 当前报告类型 |
| `level_dictionary_ref` | 当前 SOP 等级字典版本和哈希 |
| `data_freshness` | 数据分区、检查时间和 freshness 结果 |
| `fallback_reason` | fallback 或降级原因 |
| `side_effects` | 本节点产生的写副作用摘要，如 `event_write`、`sheet_publish`、`message_send` |
| `dry_run` | 是否 dry-run |
| `stop_reason` | blocked/failed 时必填 |
| `error_class` / `error_message` | 系统错误摘要，不记录 token、secret、完整 open_id |
| `correlation_ids` | 关联的 event_id、message_id、sheet_url、touch_record_id |

示例记录：

```json
{
  "audit_version": "orchestrator-audit-v1",
  "run_id": "run_20260706_low_efficiency_001",
  "attempt": 1,
  "sop_id": "low_efficiency_strategy",
  "run_mode": "report_only",
  "config_version": "cfg_20260706_1200",
  "node_type": "process_analysis",
  "node_order": 40,
  "node_status": "success",
  "started_at": "2026-07-06T12:10:00+08:00",
  "finished_at": "2026-07-06T12:18:30+08:00",
  "input_ref": "inputs/run_20260706_low_efficiency_001.json",
  "input_hash": "sha256:...",
  "output_ref": "runs/low_efficiency_strategy/run_20260706_low_efficiency_001/",
  "output_hash": "sha256:...",
  "process_skill": "low-efficiency-strategy-analysis",
  "report_type": "low_efficiency_grading",
  "level_dictionary_ref": "sop_level_dict:low_efficiency_strategy:cfg_20260706_1200",
  "data_freshness": {"max_partition": "2026-07-05", "status": "ready"},
  "fallback_reason": "dimension_reason_breakdown_requires_curated_sql",
  "side_effects": [],
  "dry_run": false,
  "stop_reason": null,
  "correlation_ids": {"event_ids": [], "message_ids": [], "sheet_urls": []}
}
```

## 8. Process Skill Registry 契约

Process Skill 注册表限制 orchestrator 可调用的业务分析能力。运营只能选择已注册 skill 和 report type，不能输入任意 Skill 名称或任意执行命令。

### 8.1 字段与允许值

| 字段 | 必填 | 允许值/格式 | 说明 |
|---|---:|---|---|
| `process_skill_id` | 是 | 稳定 ID，如 `low-efficiency-strategy-analysis` | registry 主键 |
| `process_skill_name` | 是 | 展示名 | 给运营看的名称 |
| `skill_path` | 是 | 仓库内已存在路径或发布包路径 | 只允许注册路径 |
| `registry_status` | 是 | `draft`、`active`、`canary`、`deprecated`、`disabled` | 只有 `active/canary` 可被自动运行调用 |
| `business_domain` | 是 | `efficiency`、`quality`、`cost`、`review_operation` 或已注册 domain id | 业务域 |
| `supported_sop_types` | 是 | SOP type id 列表 | 如 `low_efficiency_strategy`、`review_latency` |
| `supported_run_modes` | 是 | `manual`、`scheduled`、`report_only`、`touch_execute` 子集 | process 本身通常不支持 `touch_execute`，由 orchestrator 恢复产物 |
| `supported_process_modes` | 是 | skill 内部模式，如 `grading`、`level_detail`、`dimension_breakdown` | 必须是注册枚举 |
| `input_contract_version` | 是 | 如 `process-input-v1` | 输入契约版本 |
| `output_contract_version` | 是 | 如 `process-output-v1` | 输出目录契约版本 |
| `required_domain_reference` | 是 | 已注册 reference 路径 | 如 `warehouse-skill/references/efficiency_domain.md` |
| `required_siblings` | 否 | 项目内已注册 sibling skill 列表；只允许填写随本项目上传包 manifest 打包的 skill | 如 `warehouse-skill` |
| `runtime_tool_dependencies` | 否 | 运行时工具、平台 Skill 或平台 CLI 能力引用；不进入项目上传包 sibling manifest | 如 `bytedcli`、`sqless-data-analysis`、`bytedance-aeolus`、`lark-*` |
| `data_source_tiers` | 是 | `semantic_layer`、`governed_dataset`、`curated_raw_sql`、`raw_exploration` 子集 | 允许的数据来源层级 |
| `fallback_policy` | 是 | `none`、`semantic_to_governed`、`semantic_to_curated_sql`、`registered_sqless_fallback` | 不允许临时 fallback |
| `supported_report_types` | 是 | Report Template 注册表中的 report type | 不允许自由文本 |
| `default_report_type` | 是 | 上述列表之一 | SOP 未指定时使用 |
| `route_grains` | 是 | `reason`、`strategy`、`queue_id`、`queue_name`、`group_id`、`scene`、`project`、`none`、已注册 custom grain | 输出可供路由使用的业务对象粒度 |
| `business_object_fields` | 是 | 字段名列表 | 如 `reason`、`queue_id`、`scene` |
| `level_binding` | 是 | `sop_level_id_required`、`level_label_allowed_with_validation`、`report_only_no_level` | 等级输出方式 |
| `validation_entry` | 是 | 已注册验证入口名称 | 不是任意 shell 命令；由工程侧维护 |
| `timeout_seconds` | 否 | 正整数 | 单次分析超时 |
| `max_retry` | 否 | `0` 到 `3` | 节点自动重试次数 |
| `side_effect_policy` | 是 | `read_only_analysis` | process skill 不允许写事件、发消息、建群 |
| `owner_team` | 是 | 团队或角色别名 | 产物维护方 |
| `provenance_required` | 是 | `true` | MVP 后强制为 true |

### 8.2 调用前校验

orchestrator 调用 process skill 前必须校验：

1. `process_skill_id` 存在且 `registry_status` 对当前运行模式可用。
2. SOP 的 `sop_type` 在 `supported_sop_types` 内。
3. SOP 的 `domain_reference` 与 registry 的 `required_domain_reference` 一致或兼容。
4. `report_type` 在 `supported_report_types` 内。
5. SOP 配置的 `route_grain` 在 `route_grains` 内。
6. process 输出等级方式与当前 SOP 等级字典兼容。
7. `validation_entry` 已通过最近一次包验证或 dry-run 验证。

### 8.3 上传包 sibling 边界

上传包 manifest 中的 sibling 只表达本项目随 zip 一起打包、由打包脚本解析和校验的项目内 Skill 依赖。它不是运行环境能力清单，也不是外部平台 Skill 或 CLI 工具清单。

边界规则：

1. 项目内 sibling 只包含本项目目录内、需要随当前 manifest 一起打包发布的 Skill，例如当前项目自有的 `warehouse-skill`、`review-monitoring-shared`、`owner-routing`、`anomaly-touch`、`monitoring-orchestrator` 或业务 process skill。
2. `lark-*`、`sqless-data-analysis`、`bytedcli`、`bytedance-aeolus` 等能力属于外部平台能力、运行时 bin/CLI 或可选平台 Skill；它们可以作为 `runtime_tool_dependencies`、节点可选依赖、fallback policy 或运行前环境检查项引用，但不得要求随项目 zip 上传，也不得写入项目上传包 manifest 的 `required_siblings`。
3. `required_siblings` 中出现外部平台能力时，包验证或配置 lint 应提示将其迁移到 `runtime_tool_dependencies` 或对应节点的可选平台依赖；不得因为运行时会用到飞书、SQLess、Aeolus 或 bytedcli 就扩大上传包 sibling 范围。
4. `registered_sqless_fallback` 只表示运行时允许调用已注册的 SQLess 兜底能力，不表示上传包必须携带 `sqless-data-analysis` Skill。
5. 报告发布、IM 发送、表格导入、联系人解析等 Lark 能力由运行环境和授权状态提供；orchestrator 可以在节点执行前检查可用性，但 manifest 只校验项目内 sibling 是否齐全。

#### Scenario: 项目内 warehouse sibling
- **WHEN** process skill registry declares `required_siblings=warehouse-skill`
- **THEN** packaging validation MAY require the current project upload package to include `warehouse-skill`
- **AND** runtime validation SHALL verify the sibling is present before process analysis

#### Scenario: 外部 Lark 能力用于报告发布
- **WHEN** report publishing needs `lark-sheets`、`lark-im` or `lark-contact`
- **THEN** the registry SHALL declare them as `runtime_tool_dependencies` or node optional platform dependencies
- **AND** the upload package manifest SHALL NOT require these `lark-*` capabilities as project siblings

#### Scenario: SQLess 或 bytedcli 作为运行时兜底
- **WHEN** fallback policy uses `registered_sqless_fallback` or a data node invokes `bytedcli` / `bytedance-aeolus`
- **THEN** the run SHALL check runtime availability, authorization and registered fallback policy
- **AND** the upload package manifest SHALL NOT include `sqless-data-analysis`、`bytedcli` or `bytedance-aeolus` as project siblings

## 9. Process Skill 标准输出目录契约

### 9.1 目录结构

每次 process skill 执行必须输出一个独立 `run_dir`：

```text
<run_dir>/
  summary.json
  detail.csv
  aggregate.csv
  result.xlsx
  detail/
    <可选的多视图明细 CSV>
  aggregate/
    <可选的多视图汇总 CSV>
  provenance/
    manifest.json
    data_sources.json
    query_manifest.json
    config_snapshot.json
    quality_checks.json
```

必需文件：

- `summary.json`：运行摘要、契约版本、输入输出索引、状态和计数。
- `detail.csv`：下游路由和事件生成使用的标准明细表；无命中时保留表头并在 summary 中声明 `hit_count=0`。
- `aggregate.csv`：报告和看板使用的标准汇总表；没有汇总维度时至少包含全局汇总行。
- `result.xlsx`：报告发布默认使用的 workbook；若运行环境暂不支持 xlsx，必须在 summary 中写明替代 workbook 引用和限制。
- `provenance/`：可复核来源，不记录 token、secret、个人敏感标识。

可选目录：

- `detail/`：用于多等级、多 sheet 或多维下钻的扩展明细，如 `P2.csv`、`dimension_reason_detail.csv`。
- `aggregate/`：用于多视图汇总，如 `level_summary.csv`、`dimension_summary.csv`。

### 9.2 `summary.json` 必填内容

| 字段 | 说明 |
|---|---|
| `contract_version` | 固定为当前输出契约版本，如 `process-output-v1` |
| `run_id` / `sop_id` / `sop_type` | 运行与 SOP 标识 |
| `process_skill` / `process_mode` | 业务 skill 与内部模式 |
| `report_type` | 推荐或实际 report type |
| `status` | `success`、`no_hits`、`blocked`、`failed` |
| `period` | `period_start`、`period_end`、`run_date`、`data_lag_days`、`latest_partition` |
| `level_dictionary_ref` | 使用的当前 SOP 等级字典引用；report-only 无等级时可为空并说明 |
| `counts` | 总命中数、事件候选数、按等级计数、按业务对象计数 |
| `route_contract` | `route_grain`、`route_key_fields`、`business_object_fields` |
| `outputs` | `detail.csv`、`aggregate.csv`、`result.xlsx`、扩展视图路径及哈希 |
| `provenance_summary` | source tier、freshness、fallback reason、confidence |
| `quality_checks` | 行数、空值、分母为 0、样本不足等检查摘要 |
| `stop_reason` | blocked/failed 时必填 |

### 9.3 `detail.csv` 字段契约

标准明细表至少包含：

| 字段 | 说明 |
|---|---|
| `run_id` | 运行 ID |
| `sop_id` | SOP ID |
| `business_object` | 业务对象展示值 |
| `route_grain` | 路由粒度，如 `reason`、`queue_id` |
| `route_key` | 供 owner-routing 查找 owner 的稳定 key |
| `sop_level_id` | 当前 SOP 等级 ID；report-only 无等级时可为空 |
| `level_label` | 当前 SOP 等级展示标签 |
| `normalized_severity` | 可选横向严重度 |
| `priority_order` | 当前 SOP 内排序 |
| `metric_id` | 观测对象或指标 ID |
| `rule_group_id` | 命中的规则组 |
| `hit_condition` | 命中条件说明 |
| `evidence_json` | 证据字段摘要，使用结构化 JSON 字符串 |
| `period_start` / `period_end` | 分析窗口 |
| `source_row_hash` | 行级哈希，供卡片哈希和追溯使用 |

业务指标列可追加在上述标准列之后，例如 `avg_jinshen`、`label_rate`、`realtime_latency_minutes`。

### 9.4 `aggregate.csv` 字段契约

标准汇总表至少包含：

| 字段 | 说明 |
|---|---|
| `run_id` / `sop_id` | 运行与 SOP 标识 |
| `group_type` | `level`、`dimension`、`route_grain`、`overall` |
| `group_key` | 汇总 key |
| `level_label` | 按等级汇总时必填 |
| `hit_count` | 命中数 |
| `event_candidate_count` | 事件候选数 |
| `primary_metric_name` / `primary_metric_value` | 该汇总最核心指标 |
| `period_start` / `period_end` | 分析窗口 |

### 9.5 workbook 契约

- `result.xlsx` 的 sheet 必须能映射到 `detail.csv`、`aggregate.csv` 或扩展 CSV，不允许 workbook 内存在无法复核的孤立数据。
- sheet 名称由 report type 注册表定义，例如低效分级固定为 `notice/P2/P1/P0/综合`。
- workbook 发布到飞书后，发布层回写 sheet URL 和 workbook hash；process skill 本身不负责发送。

### 9.6 provenance 契约

`provenance/manifest.json` 记录：

- 数据源层级：`semantic_layer`、`governed_dataset`、`curated_raw_sql` 等。
- 数据新鲜度：最大分区、检查时间、数据延迟策略。
- 查询来源：semantic spec ID、dataset ID、registered sql_key、参数哈希。
- 配置来源：SOP 配置版本、规则组版本、等级字典版本、process registry 版本。
- fallback reason：语义层不可用、维度缺失、模板不覆盖等。
- 质量检查：行数、空值、重复 key、安全除法、样本不足。

## 10. 样例契约：`low-efficiency-strategy-analysis`

### 10.1 Registry 样例

| 字段 | 值 |
|---|---|
| `process_skill_id` | `low-efficiency-strategy-analysis` |
| `business_domain` | `efficiency` |
| `supported_sop_types` | `low_efficiency_strategy` |
| `supported_process_modes` | `grading`、`level_detail`、`dimension_breakdown` |
| `required_domain_reference` | `通用能力/warehouse-skill/references/efficiency_domain.md` |
| `required_siblings` | `warehouse-skill` |
| `data_source_tiers` | `semantic_layer`、`governed_dataset`、`curated_raw_sql` |
| `fallback_policy` | `semantic_to_curated_sql`，fallback reason 必填 |
| `supported_report_types` | `low_efficiency_grading`、`low_efficiency_level_detail`、`low_efficiency_dimension_breakdown` |
| `default_report_type` | `low_efficiency_grading` |
| `route_grains` | `reason`、`strategy` |
| `business_object_fields` | `reason` |
| `level_binding` | `level_label_allowed_with_validation`；当前低效 SOP 字典可配置 `notice/P2/P1/P0` |
| `side_effect_policy` | `read_only_analysis` |

### 10.2 输入样例

| 字段 | 说明 |
|---|---|
| `sop_id` | `low_efficiency_strategy` |
| `process_mode` | `grading`、`level_detail` 或 `dimension_breakdown` |
| `period` / `period_start` / `period_end` | 分析周期 |
| `run_date` / `data_lag_days` | 分区锚点 |
| `levels` | `level_detail` 或分级子集使用；必须能解析到当前 SOP 等级字典 |
| `dimensions` | `dimension_breakdown` 使用，如 `mach_label`、`scene` |
| `rule_set` | SOP 规则组引用，不传任意 SQL |
| `report_type` | 三个低效 report type 之一 |

### 10.3 输出覆盖已跑通能力

| 已跑通能力 | 标准产物映射 | 说明 |
|---|---|---|
| grading 全等级分级 | `summary.json` + `detail.csv` + `aggregate.csv` + `detail/notice.csv`、`detail/P2.csv`、`detail/P1.csv`、`detail/P0.csv`、`detail/综合.csv` + `result.xlsx` | 四个等级 sheet 保留完整命中，不跨级去重；`综合` 跨级按当前 SOP `priority_order` 取最高等级 |
| level detail 单等级明细 | `detail.csv` 为指定等级完整命中；`aggregate.csv` 为该等级汇总；`result.xlsx` 至少包含该等级 sheet 和摘要 sheet | 例如只看 P2 时，`P2` 必须是原等级完整命中，不使用综合去重替代 |
| dimension breakdown 维度拆解 | `detail.csv` 或 `detail/dimension_reason_detail.csv` 为 `dimensions × reason` 低效明细；`aggregate.csv` 或 `aggregate/dimension_summary.csv` 为维度汇总；`result.xlsx` 两个 sheet | report-only 默认不需要等级；若纳入异常事件，必须由 SOP 规则组绑定当前 SOP 等级 |

### 10.4 低效明细关键字段

低效 grading/detail 的 `detail.csv` 应包含：

- 标准字段：`run_id`、`sop_id`、`business_object`、`route_grain=reason`、`route_key=reason`、`level_label`、`priority_order`、`rule_group_id`、`hit_condition`、`evidence_json`。
- 业务字段：`reason`、`avg_jinshen`、`avg_wanshen`、`avg_dabiao`、`ratio_val`、`period_start`、`period_end`。
- provenance 字段：`source_tier`、`sql_key`、`fallback_reason`、`source_row_hash`。

维度拆解的 `detail.csv` 应包含：

- 标准字段：`run_id`、`sop_id`、`business_object=reason`、`route_grain=reason`、`route_key=reason`。
- 维度字段：所有 `dimensions`，例如 `mach_label`、`scene`。
- 业务字段：`reason`、`review_in`、`review_done`、`labeled`、`label_rate`、`avg_review_in`。

## 11. 样例契约：`review-latency-analysis`

### 11.1 Registry 样例

| 字段 | 值 |
|---|---|
| `process_skill_id` | `review-latency-analysis` |
| `business_domain` | `review_operation` |
| `supported_sop_types` | `review_latency` |
| `supported_process_modes` | `grading`、`level_detail`、`realtime_snapshot`、`forecast_vs_target` |
| `required_domain_reference` | 未来 `warehouse-skill/references/review_latency_domain.md` 或等价注册 reference |
| `required_siblings` | `warehouse-skill` |
| `data_source_tiers` | `semantic_layer`、`governed_dataset`、`curated_raw_sql` |
| `fallback_policy` | `semantic_to_governed` 或 `semantic_to_curated_sql`，以 domain reference 为准 |
| `supported_report_types` | `review_latency_grading`、`review_latency_level_detail`、`review_latency_realtime_snapshot`、`review_latency_forecast_vs_target` |
| `default_report_type` | `review_latency_grading` |
| `route_grains` | `queue_id`、`queue_name`、`group_id`、`scene` |
| `business_object_fields` | `queue_id`、`queue_name`、`group_id`、`scene` |
| `level_binding` | `sop_level_id_required`；如只输出标签，必须经当前 SOP 字典校验 |
| `side_effect_policy` | `read_only_analysis` |

### 11.2 输入契约

审核延时 process skill 的输入应覆盖：

| 字段 | 说明 |
|---|---|
| `sop_id` | `review_latency` |
| `process_mode` | `grading`、`level_detail`、`realtime_snapshot`、`forecast_vs_target` |
| `run_date` | 运行日期 |
| `window_policy` | 实时窗口，如 `10min`；连续窗口由规则组配置 |
| `comparison_policy` | 环比或基线窗口，用于计算进审增幅、机审增幅 |
| `forecast_policy` | 预计全天进审计算方式引用 |
| `target_value_ref` | 目标值来源，例如目标表、配置字段或注册查询 |
| `route_grain` | `queue_id`、`queue_name`、`group_id` 或 `scene` |
| `metric_refs` | 进审量、机审量、实时延时、预计全天进审、目标值的 canonical metric 引用 |
| `rule_groups` | SOP 规则组引用，不传任意 SQL |
| `report_type` | 已注册审核延时 report type |

### 11.3 指标与字段

`review-latency-analysis` 必须在 `detail.csv` 输出以下核心业务字段：

| 字段 | 含义 |
|---|---|
| `review_in_current` | 当前窗口或当前日进审量 |
| `review_in_baseline` | 对比窗口进审量 |
| `review_in_growth_rate` | 进审增幅 |
| `machine_audit_current` | 当前机审量或机审进审量 |
| `machine_audit_baseline` | 对比窗口机审量 |
| `machine_audit_growth_rate` | 机审增幅 |
| `realtime_latency_minutes` | 实时延时分钟数 |
| `forecast_full_day_review_in` | 预计全天进审 |
| `target_review_in` | 目标值 |
| `target_exceed_ratio` | 预计全天进审 / 目标值 |
| `consecutive_window_count` | 连续命中窗口数 |
| `window_start` / `window_end` | 当前窗口 |

### 11.4 等级规则样例

以下仅是 `review_latency` SOP 的样例等级配置，不是系统全局枚举：

| 当前 SOP 等级 | 样例条件 | 样例受众策略引用 |
|---|---|---|
| `P2` 或 `黄灯` | `进审增幅 >= 30% AND 预计全天进审 > 目标值` | 治理 BP、审核 VOC POC、人审运营、交付调度负责人 |
| `P1` 或 `橙灯` | `机审增幅 >= 30% AND 实时延时 >= 1h` OR `预计全天进审 > 目标值 * 1.2` | 治理 BP+1、VOC 负责人、人审运营负责人、群组负责人 |
| `P0` 或 `红灯` | `连续 2 个 10min 窗口进审超 100%` OR `预计全天进审 > 目标值 * 1.5` | 治理负责人、CQC 负责人 |

process skill 只输出命中等级、证据和业务对象；受众解析由 owner-routing 基于当前 SOP 等级字典和角色目录完成。

### 11.5 输出目录样例

`review-latency-analysis` 的标准产物：

- `summary.json`：记录窗口、目标值来源、命中等级计数、最高等级、最新实时窗口和数据 freshness。
- `detail.csv`：每个 `route_grain` 业务对象一行或多行，包含等级、规则组、进审增幅、机审增幅、实时延时、预计全天进审、目标值、证据。
- `aggregate.csv`：按等级、队列/群组/场景汇总命中数、最大延时、总进审、目标超额比例。
- `result.xlsx`：建议 sheet 为 `level_summary`、`hit_detail`、`forecast_vs_target`、`window_trend`。
- `provenance/`：记录实时数据源、目标值来源、forecast 方法、窗口策略、规则组版本和数据质量检查。

### 11.6 下游路由兼容

每条审核延时命中行必须携带：

- `route_grain`：来自 SOP 配置，例如 `queue_id`。
- `route_key`：稳定业务 key，例如具体 queue_id。
- `business_object`：人可读名称，例如队列名或场景名。
- `owner_hint`：可选，若 process 输出能提供 owner 线索，只作为 owner-routing 的一个注册 owner source，不直接作为最终触达人。

当某队列无 owner 映射时，owner-routing 返回 `missing_object_owner=true`；orchestrator 停止该对象正式触达，不能退化为任意指标 owner。

## 12. Task 3/4 覆盖矩阵

| 任务 | 覆盖章节 |
|---|---|
| 3.1 orchestrator 职责、输入、输出、边界和依赖 | 第 2 章 |
| 3.2 四类运行模式 | 第 3 章 |
| 3.3 SOP 节点启停和顺序驱动编排 | 第 4 章 |
| 3.4 当前 SOP 等级字典读取 | 第 5 章 |
| 3.5 状态机、停止、重试/降级、审计日志 | 第 6、7 章 |
| 4.1 process skill registry 字段和允许值 | 第 8 章 |
| 4.2 标准输出目录契约 | 第 9 章 |
| 4.3 low-efficiency 契约验证 | 第 10 章 |
| 4.4 review-latency 契约设计 | 第 11 章 |
