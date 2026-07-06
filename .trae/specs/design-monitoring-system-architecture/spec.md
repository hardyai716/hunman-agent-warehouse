# 人审运营 AI 监控自动化体系理想架构 Spec

## Why
旧版 `human-review-monitoring` 是从“低效打标策略”这一条运营 SOP 出发设计的，将感知、判断、路由、触达、状态推进和配置读取全部镶嵌在一个 Skill 中，导致复杂度高、耦合重、复用难。后续还会接入审核延时、自动处置准确率等不同 SOP，因此系统需要从“指标监控”升级为“多 SOP 配置化编排”，并基于当前项目架构和 Claude data-agent 架构定义理想态。

## What Changes
- 定义 Claude data-agent 风格三层架构在人审监控体系中的落地形态：通用数据仓库层、业务域知识层、纵向过程 Skill。
- 定义横向监控能力层：`monitoring-orchestrator`、`owner-routing`、`anomaly-touch`、`review-monitoring-shared`。
- 定义飞书多维表格作为配置中心时的配置分层、字段职责、可配置边界和不可配置边界。
- 定义配置如何驱动 Agent 串联：从 SOP 注册、监控对象注册、数据就绪、规则选择、过程 Skill 路由、责任路由、触达模板到状态推进。
- 评估现有 9 张配置表对多 SOP 的适配性，指出需保留、改造、废弃或新增的表。
- 将“审核延时 SOP”作为架构验证样例，覆盖多数据源、多条件组合、多时间窗口、分级升级、多角色触达。
- 定义版本回滚和基线保护方案，避免大规模架构改造损坏当前已跑通的低效策略查询、飞书表格发布和卡片推送链路。
- 定义从旧 `human-review-monitoring` 单体 Skill 向多 Skill 系统迁移的目标方案、验证方式和风险控制。
- 明确已跑通能力的复用路径，包括低效策略分析、维度拆解、飞书电子表格发布和报告卡片推送。

## Impact
- Affected specs: 人审监控系统架构、配置中心、编排层、横向触达、责任路由、数据仓库 Skill、业务域 process skill。
- Affected code: `通用能力/warehouse-skill/`、`通用能力/review-monitoring-shared/`、`通用能力/owner-routing/`、`通用能力/anomaly-touch/`、`通用能力/monitoring-orchestrator/`、`效率模块/low-efficiency-strategy-analysis/`、未来 `效率模块/review-latency-analysis/`、未来 `质量模块/` 和 `成本模块/` 纵向 Skill，以及 `tools/package_agent_skills.py` 和上传包发布流程。

## ADDED Requirements

### Requirement: 系统采用分层 Skill 架构
The system SHALL separate human review monitoring into distinct layers:

- Universal Warehouse Skill：负责数据源发现、语义层优先、取数、freshness、provenance、fallback reason。
- Domain Knowledge References：负责业务域 canonical metrics、dimensions、segments、governed tables、gotchas。
- Process Skills：负责单一业务流程的确定性执行，例如低效策略分级、维度拆解、审核延时分析、自动处置准确率分析。
- Horizontal Skills：负责跨业务复用能力，包括责任路由、触达、报告发布、状态编排。
- Shared Foundation：负责配置中心 schema、公共脚本、红线、踩坑清单和运行契约。

#### Scenario: 新增一个质量域监控
- **WHEN** 用户新增“自动处置准确率”监控能力
- **THEN** 系统 SHALL 新增质量域 reference 和质量域 process skill
- **AND** 系统 SHALL 复用已有 `warehouse-skill`、`owner-routing`、`anomaly-touch` 和 `monitoring-orchestrator`
- **AND** 系统 SHALL NOT 复制低效策略 Skill 中的触达、路由或状态机逻辑

### Requirement: 多维表格配置中心只配置可变决策
The system SHALL use 飞书多维表格 to configure business-variable decisions, not executable implementation logic.

可配置内容 SHALL include:

- SOP 注册：SOP ID、SOP 名称、业务域、启停、运行频率、运行模式、所属 process skill、domain reference、默认 report type。
- SOP 节点/阶段：感知、判断、路由、报告发布、触达、跟进、复盘等节点是否启用及顺序。
- 监控对象注册：指标 ID、业务域、模块、启停、频率、统计粒度、所属 SOP。
- 数据源配置：数据源类型、数据集/表标识、数据地址、日期字段、数据延迟天数、字段映射、数据源状态。
- 语义指标绑定：canonical metric、semantic dimension、segment、默认 grain、freshness 约束。
- 规则配置：SOP ID、规则 ID、等级、规则状态、规则描述、`rule_key/sql_key`、`rule_params/sql_params`、条件组合、连续窗口、最小样本量、输出字段约定。
- 编排路由配置：SOP ID、监控类型、process skill 名称、report type、运行模式、是否自动触达。
- 责任路由配置：SOP ID、路由粒度、业务对象字段、owner 来源、等级、角色别名、负责人、协作方、升级人、触达渠道、chat_id。
- 触达配置：SOP ID、模板场景、适用等级、接收对象、卡片模板 ID 或本地模板名、必填变量。
- 角色目录配置：治理 BP、审核 VOC POC、人审运营、交付调度负责人、VOC 负责人、群组负责人、CQC 负责人等业务角色别名到人员/群的映射。
- SOP 等级字典：SOP 内等级标签、标准化严重度、优先级、SLA、是否需要人工确认、升级策略。

不可配置内容 SHALL include:

- Python/SQL 模板骨架的任意代码片段。
- 未注册 Skill 名称或未验证 report type。
- 绕过数据就绪 gate、人工确认门禁、卡片哈希校验、chat_id 校验的开关。
- 任意原始 access token、app secret、个人 open_id 或临时 chat_id。
- 状态机跳转代码和安全红线。

### Requirement: 系统以 SOP 为一级业务对象，而不是以单个指标为一级业务对象
The system SHALL model each operational workflow as an SOP. An SOP MAY contain multiple metrics, multiple data sources, multiple rule groups, multiple touch audiences, and multiple state transitions.

SOP configuration SHALL include:

- `sop_id`
- `sop_name`
- `business_domain`
- `owner_team`
- `process_skill`
- `domain_reference`
- `run_frequency`
- `run_mode`
- `enabled_nodes`
- `default_report_type`
- `default_touch_policy`

The existing 指标注册表 SHALL be re-scoped as “SOP 指标/观测对象表” or linked under an SOP. It SHALL NOT remain the only root table for the whole monitoring system.

#### Scenario: 审核延时 SOP
- **WHEN** 运营配置“审核延时 SOP”
- **THEN** 系统 SHALL create or read `sop_id=review_latency`
- **AND** this SOP SHALL contain metrics such as 进审增幅、机审增幅、实时延时、预计全天进审、目标值达成率
- **AND** orchestrator SHALL call `review-latency-analysis` instead of low-efficiency-specific logic
- **AND** routing and touch SHALL be selected by SOP + level + role audience, not by metric alone

### Requirement: 现有 9 张表需要分层改造，而不是全部沿用
The system SHALL evaluate current tables by their fitness for multi-SOP orchestration.

Recommended table decisions:

| 当前表 | 决策 | 理由 |
|---|---|---|
| 数据源表 | 保留并增强 | 数据源对所有 SOP 通用，需增加 semantic field mapping、freshness policy、source tier |
| 指标注册表 | 改造 | 从系统根表降级为 SOP 下的“观测对象/指标表”，增加 `sop_id`、canonical metric、process skill binding |
| 撞线规则表 | 改造或重命名为 SOP 规则表 | 规则应挂 SOP，支持多条件组合、连续窗口、预测目标、规则组 |
| 等级字典表 | 改造为 SOP 等级字典表 | 等级标签与 SOP 强绑定，不同 SOP 可使用完全不同标签；系统只保留可选的标准化严重度用于横向排序 |
| 责任路由表 | 保留但重构语义 | 当前“指标+等级+范围”不能覆盖真实 owner 关系；需升级为“SOP+路由粒度+业务对象+等级+角色别名”，或拆成对象 owner 映射表与触达角色表 |
| 触达模板表 | 保留并增强 | 增加 SOP、report type、CardKit template id、本地模板名 |
| 事件表 | 保留并增强 | 增加 `sop_id`、`run_id`、`node_trace`、命中规则组、配置版本 |
| 触达记录表 | 保留 | 继续作为审计表，需关联 SOP/run_id/message_id |
| 案例沉淀表 | 保留但不进入 MVP 主链路 | 用于后续规则沉淀和 SOP 复盘 |

The system SHALL add new tables or logical views for SOP-first orchestration:

- SOP 注册表
- SOP 节点表
- SOP 规则组表
- SOP 等级字典表
- SOP 角色目录表
- 业务对象责任映射表
- Owner Source 注册表
- SOP 运行实例表
- Process Skill 注册表
- Report Template 注册表

#### Scenario: 现有指标注册表无法表达审核延时 SOP
- **WHEN** 一个 SOP 需要同时读取进审增幅、机审增幅、实时延时、预计全天进审和目标值
- **THEN** 系统 SHALL NOT force these into one metric row
- **AND** it SHALL represent them as multiple SOP metrics under one SOP
- **AND** SOP 规则组 SHALL combine those metrics into P2/P1/P0 conditions

### Requirement: 责任路由按业务对象粒度解析，而不是只按指标和等级匹配
The system SHALL support object-level owner resolution. Responsibility routing SHALL be able to resolve owners from the specific business object that triggered the SOP, such as `reason`, `strategy`, `queue`, `scene`, `project`, `group`, or another configured routing key.

The routing model SHALL separate three decisions:

1. 结果归属解析：将每一条命中结果关联到业务 POC、owner、协作方或负责团队。
2. 触达受众扩展：根据 SOP、等级、角色目录和升级策略，补充治理 BP、VOC POC、人审运营、CQC 负责人等角色。
3. 触达通道决策：决定发到已有群、SOP 通用群、对象专属群、私聊，还是为紧急场景单独建群。

The routing model SHALL support:

- 触达角色：某个等级下需要通知哪些角色，例如治理 BP、VOC POC、人审运营、CQC 负责人。
- 对象 owner：某个业务对象本身归谁负责，例如低效打标的 `reason/策略 -> owner`。
- 触达渠道：群聊、私聊、已有对象群、SOP 通用群、临时专项群或自动建群。
- owner 来源：多维表格映射、查询逻辑、外部系统、process skill 输出字段。
- 路由置信度：明确 owner 来源、匹配方式、是否命中兜底。

The current “指标 + 等级 + 适用范围” routing SHALL be treated as a fallback policy only. It SHALL NOT be the only supported responsibility model.

The output of owner-routing SHALL include a structured `route_result`:

```json
{
  "business_object": "reason_xxx",
  "route_grain": "reason",
  "owner_source": "reason_owner_mapping",
  "owners": [{"role": "业务POC", "id": "ou_xxx", "name": "负责人"}],
  "collaborators": [{"role": "人审运营", "id": "ou_xxx", "name": "协作人"}],
  "escalation": [{"role": "治理负责人", "id": "ou_xxx", "name": "升级人"}],
  "delivery_policy": {
    "primary_channel": "group",
    "chat_strategy": "reuse_object_group",
    "chat_id": "oc_xxx",
    "mention_targets": ["ou_xxx"],
    "fallback_channel": "dm"
  },
  "route_confidence": "high",
  "missing_object_owner": false
}
```

#### Scenario: 低效打标策略按 reason 找 owner
- **WHEN** low-efficiency process skill outputs hit rows with `reason`
- **THEN** owner-routing SHALL use `route_grain=reason` or `strategy`
- **AND** it SHALL resolve owner from a configured owner source such as a `reason_owner_mapping` table or registered query logic
- **AND** two different reasons MAY resolve to different owners even when metric and level are identical
- **AND** if a reason has no owner mapping, routing SHALL return `missing_object_owner=true` and SHALL NOT fallback to an arbitrary metric owner unless an explicit fallback policy exists
- **AND** anomaly-touch SHALL be able to mention the resolved POC in a group card or message
- **AND** the full result row SHALL keep `route_result` so operators can see why a result was routed to that POC

#### Scenario: 审核延时 SOP 按队列或群组找 owner
- **WHEN** review-latency process skill outputs hit rows with queue, group, or scene
- **THEN** owner-routing SHALL use the SOP configured routing grain, such as `queue_id`, `queue_name`, `group_id`, or `scene`
- **AND** it SHALL combine object owner with level-specific audience roles
- **AND** it SHALL route P2/P1/P0 to different escalation roles according to SOP role policy

#### Scenario: 默认群聊触达
- **WHEN** route_result contains a reusable object group or SOP group
- **THEN** anomaly-touch SHALL send one grouped notification to that chat
- **AND** it SHALL mention the resolved POC and required escalation roles
- **AND** it SHALL NOT create a new group unless chat strategy explicitly requires it

#### Scenario: 紧急或持续未处理时个人/临时群触达
- **WHEN** level is high severity or an event remains unresolved beyond configured SLA
- **THEN** delivery policy MAY switch to `dm` or `create_incident_group`
- **AND** the new group SHALL include object owner, level escalation roles, and necessary operations roles
- **AND** group creation SHALL write back chat_id only if the policy says the group should be reused

#### Scenario: 多条结果对应不同 POC
- **WHEN** one report contains hit rows mapped to different owners
- **THEN** report publishing MAY show all rows in one report
- **AND** event touch SHALL split or group notifications by `chat_strategy`
- **AND** a row SHALL NOT be sent to an unrelated POC merely because it shares the same metric or level

### Requirement: Owner Source 可配置但必须注册
The system SHALL allow owner resolution to come from multiple registered sources, but every source SHALL be declared before use.

Owner Source configuration SHALL include:

- `owner_source_id`
- `sop_id`
- `route_grain`
- `source_type` such as `lark_base_table`, `query_template`, `process_output`, `manual_fallback`
- `source_ref` such as base table token, query key, or output field path
- `key_field`
- `owner_fields`
- `fallback_policy`
- `freshness_policy`

Recommended owner mapping fields for a multi-dimensional table:

- `sop_id`
- `route_grain`
- `route_key`
- `route_key_alias`
- `owner_role`
- `owner_user`
- `collaborators`
- `escalation_users`
- `default_chat_id`
- `default_chat_name`
- `effective_start`
- `effective_end`
- `enabled`
- `priority`
- `notes`

#### Scenario: owner 来源是多维表格
- **WHEN** owner source is `lark_base_table`
- **THEN** owner-routing SHALL lookup the hit row route key in the mapping table
- **AND** it SHALL return owner, collaborators, escalation, optional chat_id, and route_source

#### Scenario: owner 来源是查询逻辑
- **WHEN** owner source is `query_template`
- **THEN** owner-routing SHALL invoke a registered query template only
- **AND** it SHALL NOT execute arbitrary SQL written directly by operators

### Requirement: SOP 规则支持多条件、多窗口、预测目标和升级角色
The system SHALL support rule groups that combine multiple conditions with AND/OR logic while keeping executable logic in registered process skills or SQL templates.

Rule group configuration SHALL support:

- `sop_id`
- `rule_group_id`
- `sop_level_id`
- `condition_logic` such as `A AND B`, `A OR B`
- `window_policy` such as `10min`, `2 consecutive windows`, `daily forecast`
- `metric_refs`
- `threshold_refs`
- `target_value_refs`
- `rule_key/sql_key`
- `rule_params/sql_params`
- `audience_policy`

### Requirement: 等级定义必须与 SOP 强绑定
The system SHALL treat level labels as SOP-scoped configuration. Labels such as `P0`, `P1`, `P2`, `notice` SHALL NOT be assumed as global system enums.

SOP Level configuration SHALL include:

- `sop_id`
- `sop_level_id`
- `level_label`
- `level_name`
- `normalized_severity`
- `priority_order`
- `sla_minutes`
- `sla_text`
- `requires_human_confirm`
- `escalation_policy`
- `default_audience_policy`
- `enabled`

`normalized_severity` MAY be used for cross-SOP sorting, dashboard colors and generic escalation comparison. It SHALL NOT replace the SOP’s own `level_label`.

#### Scenario: 低效打标 SOP 使用 P0/P1/P2/notice
- **WHEN** low-efficiency SOP emits `level_label=P2`
- **THEN** downstream routing and touch SHALL resolve level config by `(sop_id, sop_level_id or level_label)`
- **AND** it SHALL NOT assume another SOP’s `P2` has the same SLA, audience or confirmation policy

#### Scenario: 审核延时 SOP 使用不同等级标签
- **WHEN** review-latency SOP uses labels such as `红灯`, `橙灯`, `黄灯` or `L1/L2/L3`
- **THEN** the system SHALL support those labels without code changes
- **AND** it SHALL map them to optional normalized severity only for cross-SOP comparison
- **AND** touch templates SHALL render the SOP-specific label, not a forced P0/P1/P2 label

#### Scenario: 配置表出现未注册等级
- **WHEN** a rule group references a `sop_level_id` not present in the SOP level dictionary
- **THEN** configuration lint SHALL fail
- **AND** orchestrator SHALL NOT run that rule group

#### Scenario: 审核延时 SOP P2
- **WHEN** rule group is P2
- **THEN** condition SHALL support “进审增幅 >= 30% AND 预计全天进审 > 目标值”
- **AND** audience SHALL resolve to 治理 BP、审核 VOC POC、人审运营、交付调度负责人

#### Scenario: 审核延时 SOP P1
- **WHEN** rule group is P1
- **THEN** condition SHALL support “机审增加 >= 30% AND 实时延时 >= 1h” OR “预计全天进审 > 目标值 * 1.2”
- **AND** audience SHALL resolve to 治理 BP+1、VOC 负责人、人审运营负责人、群组负责人

#### Scenario: 审核延时 SOP P0
- **WHEN** rule group is P0
- **THEN** condition SHALL support “连续 2 个 10min 窗口进审超 100%” OR “预计全天进审 > 目标值 * 1.5”
- **AND** audience SHALL resolve to 治理负责人、CQC 负责人

### Requirement: Process Skill Registry 限制配置可调用范围
The system SHALL maintain a registry of allowed process skills and report types.

The registry SHALL include:

- `process_skill`
- `business_domain`
- `supported_sop_types`
- `input_contract`
- `output_contract`
- `supported_report_types`
- `required_domain_reference`
- `validation_command`

#### Scenario: 运营误填未注册 Skill
- **WHEN** SOP 注册表 contains `process_skill=unknown-skill`
- **THEN** configuration lint SHALL fail
- **AND** orchestrator SHALL NOT execute that SOP
- **AND** validation report SHALL indicate the invalid table and field

#### Scenario: 运营配置一个新规则
- **WHEN** 运营在撞线规则表新增一条生效规则
- **THEN** 该规则 SHALL 只能选择已注册 `sql_key` 或填写结构化规则描述
- **AND** `sql_params` SHALL 由 Agent 或规则录入流程校验后回填
- **AND** 如果 `sql_key` 未注册或参数校验失败，系统 SHALL 转人工而不是执行未验证 SQL

### Requirement: 配置必须足以驱动 Agent 串联
The system SHALL define a minimum viable configuration set that allows Agent to decide which Skill to call and how to pass outputs downstream.

一条可执行监控配置 SHALL 至少 resolve to:

- `sop_id`
- `sop_type`
- `metric_id`
- `business_domain`
- `process_skill`
- `domain_reference`
- `data_source_id`
- `period_policy`
- `rule_set`
- `output_contract`
- `report_type`
- `route_policy`
- `owner_source`
- `route_grain`
- `touch_policy`
- `state_policy`

#### Scenario: Agent 运行单轮监控
- **WHEN** `monitoring-orchestrator` receives `{metric_id, period}`
- **THEN** it SHALL read configuration and resolve the target process skill
- **AND** it SHALL call the process skill only after warehouse freshness passes
- **AND** it SHALL pass structured hits to routing and touch stages
- **AND** it SHALL write event state transitions according to state policy

### Requirement: monitoring-orchestrator 作为流程权威
The system SHALL introduce `monitoring-orchestrator` as the flow authority for manual and scheduled runs.

`monitoring-orchestrator` SHALL:

- 读取启用 SOP 配置，而不是只读取启用指标。
- 读取当前 SOP 的等级字典，而不是依赖全局 P0/P1/P2/notice 枚举。
- 解析 period 和运行模式。
- 调用数据就绪 gate。
- 调用业务 process skill。
- 调用 owner-routing，并把 process skill 输出的业务对象字段传入路由解析。
- 调用 anomaly-touch 或 report publishing。
- 统一推进事件状态。
- 记录每个节点的输入、输出、失败原因和 fallback reason。

`monitoring-orchestrator` SHALL NOT:

- 写业务指标口径。
- 写 P0/P1/P2/notice 具体判断阈值。
- 直接拼接业务 SQL。
- 绕过横向能力的安全校验。

#### Scenario: 只需要报告不需要触达
- **WHEN** 监控配置的 `touch_policy.auto_send=false`
- **THEN** orchestrator SHALL run analysis and report publishing only
- **AND** it SHALL NOT create group chat or write touch records

#### Scenario: SOP 中部分节点关闭
- **WHEN** SOP 节点表配置 `report_publish=true` and `event_touch=false`
- **THEN** orchestrator SHALL publish reports but SHALL NOT write touch records
- **AND** it SHALL still write a run summary for audit

### Requirement: 结果发布能力统一复用
The system SHALL treat Lark report publishing as a reusable horizontal capability under `anomaly-touch`.

The system SHALL use one publishing entry point for standard analysis output directories:

```bash
python3 scripts/publish_lark_report.py --run-dir <run_dir> --report-type <type>
```

Supported report types SHALL include:

- `low_efficiency_dimension_breakdown`
- `low_efficiency_grading`
- `low_efficiency_level_detail`

#### Scenario: 推送已跑通的 P2 低效策略结果
- **WHEN** process skill outputs `summary.json`, `P2.csv`, and workbook
- **THEN** publishing SHALL import or reuse a Lark spreadsheet
- **AND** publishing SHALL render a Card 2.0 payload from a registered template
- **AND** publishing SHALL send by bot or user according to configuration
- **AND** publishing SHALL write a publish summary containing message_id, chat_id and sheet_url

### Requirement: 配置变更必须可验证
The system SHALL provide validation gates before a configured monitor can run automatically.

Validation SHALL cover:

- 配置完整性：必填字段、关联表、启停状态。
- 数据可用性：目标分区、行数、权限、字段映射。
- Skill 可达性：process skill 名称、report type、模板名称是否注册。
- SOP 可达性：SOP 是否启用、SOP 节点顺序是否合法、SOP 所需角色是否可解析。
- 等级可达性：规则组引用的 `sop_level_id` 是否存在、优先级/SLA/人工确认策略是否完整。
- SQL 安全性：`sql_key` 是否存在，`sql_params` 是否通过校验。
- 触达安全性：责任路由、chat_id、人工确认策略、模板必填变量。
- 输出契约：是否产出下游需要的 `summary.json`、CSV、workbook 或 events。

#### Scenario: 自动运行前配置不完整
- **WHEN** required configuration is missing
- **THEN** system SHALL stop before analysis or touch
- **AND** system SHALL produce a validation report that tells operators which table and field to fix

### Requirement: 大规模改造必须具备版本回滚与基线保护
The system SHALL provide a rollback plan before introducing SOP-first architecture changes that affect existing working flows.

The rollback design SHALL cover five layers:

- 代码版本：Git commit、tag、branch、PR 粒度的回滚。
- Skill 上传包：`dist/agent_upload/zips/*.zip` 的可回滚基线版本。
- 配置中心：飞书多维表格 schema、记录数据、视图和关键配置的备份与版本号。
- 运行入口：旧入口、新入口、灰度入口和手动 fallback 命令。
- 验证基线：低效策略 P2 查询、全等级查询、机审标签维度拆解、飞书表格发布、卡片推送的 smoke tests。

The system SHALL NOT remove or overwrite the currently working path until the new path passes baseline validation.

#### Scenario: 新 orchestrator 改造失败
- **WHEN** `monitoring-orchestrator` fails during SOP-first rollout
- **THEN** operators SHALL be able to run the existing direct process skill path
- **AND** low-efficiency P2 query and Lark report publishing SHALL remain available through the previously working commands
- **AND** failed orchestrator state SHALL NOT corrupt existing result artifacts or touch records

#### Scenario: 新配置表 schema 不兼容
- **WHEN** SOP-first table migration produces invalid or incomplete configuration
- **THEN** the system SHALL keep the previous 9-table configuration snapshot available
- **AND** lint/dry-run SHALL stop before writing events or sending touches
- **AND** rollback SHALL restore the previous schema/data snapshot or switch runtime to the previous config version

#### Scenario: 新 Skill 上传包不可用
- **WHEN** a newly uploaded Skill package fails validation or runtime smoke test
- **THEN** operators SHALL re-upload the previous known-good zip package
- **AND** the manifest SHALL keep enough metadata to identify which package version is active

### Requirement: 新架构必须支持灰度与双跑
The system SHALL support gradual rollout by running the old and new paths side by side before replacing the current working flow.

The rollout model SHALL include:

- `baseline`：当前已跑通路径，只读保护。
- `shadow`：新架构只产报告和对比结果，不触达、不写事件主表。
- `canary`：少量 SOP 或单等级打开真实发布。
- `active`：新架构成为默认路径。
- `rollback`：恢复到 baseline 或上一稳定版本。

#### Scenario: shadow run 对比
- **WHEN** new SOP-first flow runs in shadow mode
- **THEN** it SHALL compare its outputs with baseline artifacts for the same period
- **AND** differences SHALL be reported before enabling touch or event writeback

#### Scenario: canary 发布
- **WHEN** canary mode is enabled for one SOP or one level
- **THEN** only that scoped configuration SHALL use the new flow
- **AND** all other SOPs SHALL continue using baseline behavior

### Requirement: 旧单体 Skill 作为迁移参考而非运行目标
The system SHALL keep `/human-review-monitoring` as a reference implementation while migrating logic into modular skills.

#### Scenario: 迁移旧流程
- **WHEN** a behavior exists only in old `human-review-monitoring`
- **THEN** migration SHALL map it to a target layer first
- **AND** it SHALL NOT copy the entire old flow into a new monolithic Skill

## MODIFIED Requirements

### Requirement: review-monitoring-shared 作为配置与公共契约底座
`review-monitoring-shared` SHALL remain the shared foundation for base schema, public validation scripts, red-line rules and runtime pitfalls. It SHALL document SOP-first configuration schema, including SOP-scoped level dictionary. It SHALL NOT own business thresholds, process routing or touch execution.

### Requirement: anomaly-touch 作为触达与报告发布横向能力
`anomaly-touch` SHALL own message/card rendering, report publishing, human confirmation gate, pre-send validation and touch record writeback. It SHALL NOT own business detection or responsibility matching.

### Requirement: owner-routing 作为责任匹配横向能力
`owner-routing` SHALL own object-level owner resolution, role audience expansion, collaborator/escalation matching and SLA calculation. It SHALL resolve SLA from the current SOP’s level dictionary. It SHALL support configured route grains such as reason, strategy, queue, scene or group. It SHALL NOT own anomaly judgement, event creation or message sending.

### Requirement: low-efficiency-strategy-analysis 作为效率域 process skill
`low-efficiency-strategy-analysis` SHALL remain a process skill for low-efficiency reason analysis. It SHALL output structured run artifacts and SHALL NOT own routing, touching, or orchestration.

### Requirement: review-latency-analysis 作为审核延时 SOP 的 process skill
`review-latency-analysis` SHALL be designed as a process skill for 审核延时 SOP. It SHALL read SOP config and domain reference, compute queue ingress growth, machine-audit growth, realtime latency, full-day forecast, and target exceedance. It SHALL output structured hits by level and SHALL NOT own routing, touching, or orchestration.

## REMOVED Requirements

### Requirement: 单体 human-review-monitoring 继续承载全流程新增能力
**Reason**: 单体 Skill 同时承载感知、判断、触达、路由、状态和配置，导致新业务接入时复用困难且风险扩大。
**Migration**: 保留旧 Skill 作为参考实现，将能力逐步迁移到 `warehouse-skill`、domain references、process skills、`owner-routing`、`anomaly-touch` 和 `monitoring-orchestrator`。

### Requirement: 运营通过配置表直接修改执行逻辑
**Reason**: 让运营配置 SQL/Python 执行逻辑会破坏可测试性、安全门禁和模板校验。
**Migration**: 运营只配置已注册模板的参数和启停策略；新增模板或 process skill 必须通过代码评审、测试和打包验证。
