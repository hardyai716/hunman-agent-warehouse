# 人审监控体系配置模型设计

本文覆盖 Task 1 与 Task 2：先盘点旧 `human-review-monitoring` 单体 Skill 能力并映射到新分层架构，再定义以 SOP 为一级对象的多维表格配置中心目标模型。

## 1. 旧单体能力盘点与目标层映射

旧 `human-review-monitoring` 将感知、判断、路由、触达、状态、配置全部放在一个 Skill 内。新架构不复制旧单体，而是把旧能力拆到以下目标层：

- `warehouse`：通用数据发现、语义层优先、取数、freshness、provenance、fallback reason。
- `domain reference`：业务域指标口径、维度、字段映射、治理表、gotchas。
- `process skill`：单一 SOP 或业务流程的确定性分析，例如低效策略分级、维度拆解、审核延时分析。
- `owner-routing`：业务对象粒度的负责人解析、角色扩展、SLA 计算、通道策略。
- `anomaly-touch`：报告发布、卡片渲染、人工确认、发送校验、触达记录写入。
- `orchestrator`：SOP 节点编排、状态推进、失败仲裁、run 审计。
- `shared`：配置 schema、公共红线、通用校验脚本、dry-run gate、运行契约。

### 1.1 旧 reference 与脚本盘点

| 旧能力域 | 旧资产 | 旧职责 | 目标层 | 当前项目落地状态 |
|---|---|---|---|---|
| 配置中心 schema | `SKILL.md`、`references/base_schema.md` | 定义 9 张多维表格、base token、字段结构、红线 | `shared` | 已迁移到 `通用能力/review-monitoring-shared/references/base_schema.md`，但仍是旧 9 表形态，未 SOP-first |
| 手动编排 | `references/flow_manual_run.md` | 预加载 6 张配置表，串联感知、判断、路由、触达，定义 dry-run 边界 | `orchestrator` + `shared` | 未落地独立 `monitoring-orchestrator`；dry-run 坑和红线部分已进入 shared |
| 全量状态编排 | `references/flow_orchestration.md` | 状态机权威、节点顺序、结果仲裁、失败降级 | `orchestrator` | 缺失。当前项目没有 `通用能力/monitoring-orchestrator/` |
| 数据感知 | `references/data_sensing.md` | 数据源就绪 gate、目标分区、取数前置检查，不建事件 | `warehouse` + `orchestrator` | `warehouse-skill` 已有语义层优先和 freshness 思路；SOP 级 freshness gate 尚未配置化 |
| 取数细节 | `references/metric_data_fetcher.md` | 风神/Aeolus 取数、物理表解析、字段引用、fallback | `warehouse` + `domain reference` | `warehouse-skill` 与 `efficiency_domain.md` 已承接低效策略相关口径和 gotchas |
| 撞线判断 | `references/anomaly_judgement.md` | `sql_key` 优先、`sql_params` 校验、SQL 结果非空即命中、事件创建 | `process skill` + `orchestrator` | 低效策略判断已落在 `效率模块/low-efficiency-strategy-analysis/scripts/sql_templates.py` 与 `grading_rules.md`；事件创建/状态推进仍缺 orchestrator |
| 规则录入 | `references/rule_intake.md` | 自然语言规则转五章节描述，生成 `sql_key/sql_params`，写规则表 | `shared` + `process skill` registry | 低效策略模板已迁移；通用 SOP 规则组、模板注册和 lint 未落地 |
| 责任路由 | `references/owner_routing.md` | 按指标、等级、适用范围匹配负责人、协作方、升级人和 SLA | `owner-routing` | 已有 `通用能力/owner-routing/`，但仍是旧的“指标+等级+范围”匹配；对象级 owner source、route_result 未落地 |
| 触达内容 | `references/touch_message_writer.md` | 选模板、填变量、生成卡片、批量表格消息 | `anomaly-touch` | 已有 `通用能力/anomaly-touch/` 和报告卡片模板；事件触达模板注册仍未 SOP-first |
| 触达发送 | `references/touch_sender.md` | 人工确认、三重校验、建群、发送、触达记录写入 | `anomaly-touch` + `shared` | `anomaly-touch` 保留触达发送文档；`card_validator.py` 已进入 shared；SOP/route_result 驱动的触达还缺 |
| 卡片校验脚本 | `scripts/card_validator.py`、`scripts/test_card_validator.py` | 命中数据哈希、等级一致、chat_id 一致校验 | `shared` | 已落地到 `review-monitoring-shared/scripts/card_validator.py` |
| SQL 模板脚本 | `scripts/sql_templates.py`、`scripts/test_sql_templates.py` | 低效策略 notice/P2/P1/P0 SQL 模板、参数校验、渲染 | `process skill` | 已落地到 `low-efficiency-strategy-analysis/scripts/sql_templates.py` |
| 跑批踩坑 | `references/dry_run_pitfalls.md` | 工具、风神、字段、输出解析、dry-run gate | `shared` | 已迁移到 `review-monitoring-shared/references/dry_run_pitfalls.md` |
| 根因/解决/跟进 | `references/root_cause_analysis.md`、`resolution_action.md`、`resolution_tracking.md` | 事件归因、处置、复查、关闭 | 未来 process skill + `orchestrator` | 暂未进入当前拆分 MVP 主链路 |
| 案例沉淀 | `references/case_to_rule.md`、案例沉淀表 | 已关闭事件转案例和规则草稿 | `shared` + 未来规则治理流程 | 案例沉淀表保留，MVP 不进入主链路 |

### 1.2 目标层能力映射与缺口

| 目标层 | 承接的旧能力 | 当前已落地 | 仍缺失 |
|---|---|---|---|
| `warehouse` | 数据源发现、取数、数据就绪、字段引用规范、fallback reason | `通用能力/warehouse-skill/`；`efficiency_domain.md`；低效策略字段/口径/gotchas | SOP 配置驱动的数据源解析、freshness policy 表达、运行实例级 provenance 写回 |
| `domain reference` | 低效策略指标口径、字段映射、样本池、维度 gotchas | `warehouse-skill/references/efficiency_domain.md` | 审核延时、质量、成本等 domain reference；业务域 reference 注册表 |
| `process skill` | SQL 撞线、低效分级、维度拆解、输出清单 | `low-efficiency-strategy-analysis`；`grading_rules.md`；`dimension_breakdown.md`；`analysis_output.md` | `review-latency-analysis`；质量域 process skill；统一 process skill registry |
| `owner-routing` | 负责人匹配、协作方、升级人、SLA | `通用能力/owner-routing/` 基础版 | 对象级路由粒度、Owner Source 注册、角色目录、`route_result` 标准输出、missing owner 停止策略 |
| `anomaly-touch` | 触达模板、卡片渲染、人工确认、建群、发送、触达记录 | `通用能力/anomaly-touch/`；`publish_lark_report.py`；三类低效报告模板 | SOP/等级/角色驱动模板选择；正式事件触达与报告发布的边界配置；多 POC 拆分/合并触达策略 |
| `orchestrator` | 手动/定时运行、节点顺序、状态推进、失败仲裁、dry-run 副作用控制 | 仅旧文档中定义，当前项目未建目录 | `monitoring-orchestrator` Skill、SOP 运行实例表、节点 trace、状态策略、自动运行 gate |
| `shared` | 9 表 schema、红线、card_validator、dry-run pitfall | `review-monitoring-shared` 已包含 base schema、card validator、dry-run pitfall | SOP-first schema、配置 lint 规则、失败报告格式、注册表契约 |

### 1.3 当前落地判定

已落地能力：

- 旧 9 表 schema 已在 `review-monitoring-shared` 中沉淀，真实 token 已脱敏。
- 通用卡片哈希和发送前三重校验脚本已迁移到 shared。
- 低效策略分级 SQL 模板、四级规则、维度拆解脚本和报告输出契约已进入 `low-efficiency-strategy-analysis`。
- 效率域字段映射、canonical metric、样本池、ClickHouse gotchas 已进入 `warehouse-skill/references/efficiency_domain.md`。
- 报告发布入口 `anomaly-touch/scripts/publish_lark_report.py` 已支持 `low_efficiency_dimension_breakdown`、`low_efficiency_grading`、`low_efficiency_level_detail`。
- 基础版 `owner-routing` 已支持旧的“指标 + 等级 + 适用范围”匹配和 SLA 计算。

仍缺失能力：

- `monitoring-orchestrator` 未建，状态机和节点 trace 尚无独立运行权威。
- 配置中心仍以“指标”为主根，尚未升级到 SOP-first。
- 当前等级字典是全局 P0/P1/P2/notice，不支持 SOP-scoped level。
- Owner Source 未注册化，无法按 `reason/strategy/queue/group/scene` 等业务对象粒度解析 owner。
- `route_result`、角色目录、触达策略、建群策略尚未标准化为可串联契约。
- Process Skill Registry、Report Template Registry、SOP 运行实例表未落地。
- 审核延时 SOP、质量域自动处置准确率等新 process skill 和 domain reference 未落地。
- 配置 lint、dry-run validation report、自动运行前 gate 尚未形成可执行配置规范。

## 2. 配置中心设计原则

配置中心以飞书多维表格承载“业务可变决策”，不承载代码实现。一级业务对象必须是 SOP，而不是单个指标。一个 SOP 可以包含多个指标、多个数据源、多个规则组、多个责任路由、多个触达受众和多个状态节点。

可配置：

- SOP 注册、启停、运行频率、运行模式、process skill、domain reference、默认报告类型。
- SOP 节点顺序与启停。
- SOP 观测对象/指标、数据源、语义指标绑定、统计粒度和 freshness 约束。
- SOP 规则组、规则参数、等级、窗口策略、最小样本量、输出字段契约。
- 责任路由策略、Owner Source、对象 owner 映射、角色目录、触达通道和触达模板。
- SOP 等级字典中的标签、优先级、SLA、人工确认、默认受众策略。

不可配置：

- Python 代码、SQL 模板骨架、任意可执行脚本片段。
- 未注册 process skill、未注册 report type、未注册 card template。
- 绕过数据就绪 gate、人工确认门禁、卡片哈希校验、chat_id 校验的开关。
- access token、app secret、tenant token、个人 open_id、临时 chat_id 等敏感或易错标识。
- 状态机跳转代码、安全红线、权限绕过策略。
- 运营直接手写任意 SQL；只能选择已注册 `sql_key` 或填写规则描述，由 Agent 校验并回填结构化参数。

## 3. 字段职责分类

### 3.1 四类职责边界

| 职责类别 | 定义 | 典型字段 | 写入方 | 校验要求 |
|---|---|---|---|---|
| 运营可配 | 业务侧可变决策，允许运营在表内维护 | `sop_id`、`sop_name`、`business_domain`、启停、运行频率、数据源类型、数据延迟天数、规则描述、最小样本量、等级标签、SLA、角色别名、触达模板变量 | 运营或 Agent 辅助录入后人工确认 | 必填、枚举、关联关系、注册表、字段格式 |
| Agent 回写 | 运行过程中产生的审计、状态、探测、发送结果 | 数据就绪状态、最近就绪校验时间、命中事件、事件状态、责任方、SLA 截止时间、触达记录、消息 ID、confirmed_by、run_id、node_trace、publish_summary | Agent / orchestrator / 横向 skill | 只允许运行态写入，不得作为业务配置源 |
| 系统派生 | 由配置和运行上下文计算得出，不允许人工直接改 | 目标分区、period_start/end、config_version_hash、route_confidence、fallback_reason、computed_sla_deadline、idempotency_key、card_hash | 系统计算 | 可落库审计，但人工修改无效 |
| 禁止配置 | 配置中心不得出现或不得由运营填写 | SQL/Python 骨架、未注册 skill 名、密钥、临时 open_id/chat_id、绕过 gate 的开关、状态机跳转代码 | 不允许 | lint 必须阻断运行 |

### 3.2 旧 9 表字段职责归类

| 旧表 | 运营可配 | Agent 回写 | 系统派生 | 禁止配置/限制 |
|---|---|---|---|---|
| 数据源表 | 数据源名称、类型、ID、数据集/表标识、数据地址、日期字段、维度字段、指标字段、数据延迟天数、更新频率 | 数据就绪状态、最近就绪校验时间 | 目标分区、freshness、source tier | 不配置 token、region/appId 可由 URL 或平台解析，不写死 |
| 指标注册表 | 指标 ID、名称、模块、启停、监控频率、统计粒度、指标口径、基础过滤条件、目标阈值/方向/单位、数据源 | 无，除非迁移时写关联 | canonical metric 绑定、默认 period policy | 不作为系统根表；基础过滤条件必须结构化或受控 SQL 片段 |
| 撞线规则表 | 规则 ID、关联指标、规则状态、等级、规则描述、最小样本量 | 命中事件、`sql_key/sql_params` 可由 Agent 校验后回填为只读机器字段 | 规则组展开、窗口日期、渲染 SQL | 运营不直接填任意 SQL；`sql_key` 必须注册 |
| 等级字典表 | 等级标签、优先级、默认响应时长/分钟、是否需要人工确认 | 无 | SLA 截止时间由运行时计算 | 不再作为全局等级权威；必须绑定 SOP |
| 责任路由表 | 路由 ID、关联指标、等级、适用范围、主负责人、协作方、升级人、触达渠道、群聊/接收方、是否启用 | 自动建群后的群聊 ID、群聊名回写 | route_confidence、missing_object_owner | 不允许人工随意填临时 chat_id；chat_id 需校验 `oc_` 并与策略匹配 |
| 触达模板表 | 模板 ID、场景、等级、接收对象、标题模板、正文模板、必填变量、启停 | 无 | 模板变量解析结果 | 不配置人工确认开关，人工确认只看等级字典或 SOP level |
| 事件表 | 少量人工治理字段，如预计治理完成时间、关闭原因、复盘摘要 | 事件状态、等级、业务对象、当前值、目标值、影响说明、责任方、SLA、触达记录、最近触达时间、命中规则 | event_id、route_result、state_trace | 不作为配置表；禁止人工跳过状态机写终态 |
| 触达记录表 | 无，属于审计表 | 触达标题、内容、对象、渠道、群聊 ID、消息 ID、状态、触达时间、关联事件/路由/模板、确认人和确认时间 | idempotency_key、card_hash | 不作为触达策略配置源 |
| 案例沉淀表 | 案例标题、最终原因、有效/无效动作、适用范围、是否转规则、是否需更新 Skill | 关联事件、关联规则、创建时间 | 案例可转规则建议 | 转规则只能建议或草稿，不能绕过规则校验直接生效 |

## 4. 现有 9 表去留评估

| 当前表 | 决策 | 目标名称/关系 | 迁移理由 | 关键改造 |
|---|---|---|---|---|
| 数据源表 | 保留并增强 | 数据源注册表 | 所有 SOP 共用数据源配置 | 增加 `semantic_field_mapping`、`freshness_policy`、`source_tier`、`owner`、`status`、`config_version` |
| 指标注册表 | 改造/重命名 | SOP 指标/观测对象表 | 不再作为根表，挂到 SOP 下 | 增加 `sop_id`、`canonical_metric`、`metric_role`、`process_skill_binding`、`period_policy`、`output_alias` |
| 撞线规则表 | 改造/重命名 | SOP 规则表 + SOP 规则组表 | 规则应挂 SOP，支持多条件、多窗口、预测目标 | 增加 `sop_id`、`rule_group_id`、`sop_level_id`、`condition_logic`、`window_policy`、`metric_refs`、`audience_policy` |
| 等级字典表 | 改造/重命名 | SOP 等级字典表 | 等级标签和 SLA 与 SOP 强绑定 | 增加 `sop_id`、`sop_level_id`、`level_label`、`normalized_severity`、`default_audience_policy`，不假设全局 P0/P1/P2 |
| 责任路由表 | 保留但重构语义 | SOP 路由策略表 + 业务对象责任映射表 + Owner Source 注册表 | 旧“指标+等级+范围”无法覆盖对象级 owner | 改为 `sop_id + route_grain + business_object + sop_level_id + role_alias`，旧表作为 fallback |
| 触达模板表 | 保留并增强 | Report Template 注册表 + Touch Template 表 | 触达模板和报告模板都需注册 | 增加 `sop_id`、`report_type`、`cardkit_template_id`、`local_template_name`、`required_artifacts`、`required_variables` |
| 事件表 | 保留并增强 | SOP 事件表 | 仍是异常状态和审计主表 | 增加 `sop_id`、`run_id`、`node_trace`、`rule_group_id`、`config_version`、`route_result` |
| 触达记录表 | 保留并增强 | SOP 触达记录表 | 仍是发送审计表 | 增加 `sop_id`、`run_id`、`message_id`、`card_hash`、`route_result_id`、`idempotency_key` |
| 案例沉淀表 | 保留但不进 MVP 主链路 | SOP 复盘/案例表 | 用于后续规则沉淀和 SOP 复盘 | 增加 `sop_id`、`related_rule_group_id`、`case_status`、`promoted_rule_id`，默认不驱动运行 |

## 5. SOP-first 新表设计

以下表可以是新表，也可以先用逻辑视图或现有表增强字段表达。MVP 迁移建议先逻辑定义，待 orchestrator 和 lint 就绪后再物理建表。

### 5.1 SOP 注册表

| 字段 | 职责 | 说明 |
|---|---|---|
| `sop_id` | 运营可配 | SOP 唯一 ID，例如 `low_efficiency_labeling`、`review_latency` |
| `sop_name` | 运营可配 | SOP 展示名称 |
| `sop_type` | 运营可配 | SOP 类型，例如 `anomaly_detection`、`reporting`、`review_followup` |
| `business_domain` | 运营可配 | 效率、质量、成本等业务域 |
| `owner_team` | 运营可配 | SOP 归属团队 |
| `enabled` | 运营可配 | SOP 是否启用 |
| `run_frequency` | 运营可配 | 日度、周度、10min、手动等 |
| `run_mode` | 运营可配 | `baseline`、`shadow`、`canary`、`active`、`rollback` |
| `process_skill` | 运营可配 | 必须命中 Process Skill 注册表 |
| `domain_reference` | 运营可配 | 必须命中已存在 reference |
| `default_report_type` | 运营可配 | 必须命中 Report Template 注册表 |
| `default_touch_policy` | 运营可配 | 触达默认策略 ID |
| `state_policy` | 运营可配 | 状态策略 ID，决定可走节点和终止规则 |
| `config_version` | 系统派生/运营确认 | 配置版本，用于 run 审计和回滚 |

### 5.2 SOP 节点表

| 字段 | 职责 | 说明 |
|---|---|---|
| `sop_node_id` | 运营可配 | 节点唯一 ID |
| `sop_id` | 运营可配 | 关联 SOP |
| `node_type` | 运营可配 | `freshness_check`、`analysis`、`route`、`report_publish`、`event_touch`、`followup`、`review` |
| `node_order` | 运营可配 | 节点顺序，必须单调且无环 |
| `enabled` | 运营可配 | 节点是否启用 |
| `required_inputs` | 运营可配 | 上游必须产出的字段或文件 |
| `output_contract` | 运营可配 | 下游可消费的结构 |
| `fail_policy` | 运营可配 | `stop`、`skip_touch`、`manual_review`、`retry` |
| `dry_run_behavior` | 运营可配 | dry-run 下是否只读、是否短路写入 |
| `node_trace` | Agent 回写 | 运行实例中记录，不作为配置字段回写本表 |

### 5.3 SOP 指标/观测对象表

| 字段 | 职责 | 说明 |
|---|---|---|
| `metric_id` | 运营可配 | 旧指标 ID 可沿用 |
| `sop_id` | 运营可配 | 必填，指标挂 SOP |
| `metric_name` | 运营可配 | 指标名称 |
| `metric_role` | 运营可配 | `primary`、`guard`、`forecast`、`target`、`context` |
| `canonical_metric` | 运营可配 | 对应业务域 canonical metric |
| `business_domain` | 系统派生/校验 | 应与 SOP 注册表一致 |
| `data_source_id` | 运营可配 | 关联数据源表 |
| `grain` | 运营可配 | 统计粒度 |
| `period_policy` | 运营可配 | 周期窗口策略 |
| `base_filter` | 运营可配 | 样本池或基础过滤，必须受控 |
| `enabled` | 运营可配 | 是否启用 |

### 5.4 SOP 规则组表

| 字段 | 职责 | 说明 |
|---|---|---|
| `rule_group_id` | 运营可配 | 规则组唯一 ID |
| `sop_id` | 运营可配 | 关联 SOP |
| `sop_level_id` | 运营可配 | 关联 SOP 等级字典 |
| `rule_status` | 运营可配 | 草稿、生效、停用 |
| `condition_logic` | 运营可配 | 例如 `A AND B`、`A OR B`、`condition_1 OR condition_2` |
| `window_policy` | 运营可配 | 例如 `10min`、`2 consecutive windows`、`daily forecast` |
| `metric_refs` | 运营可配 | 参与判断的 metric_id 列表 |
| `threshold_refs` | 运营可配 | 阈值参数或目标引用 |
| `target_value_refs` | 运营可配 | 目标值来源，如预算、目标表、预测值 |
| `rule_key/sql_key` | 运营可配/Agent 回写 | 必须注册；运营可选择，Agent 可由规则录入回填 |
| `rule_params/sql_params` | Agent 回写/人工确认 | Agent 校验后写入，运营不手写 JSON |
| `min_sample_size` | 运营可配 | 样本量守卫 |
| `audience_policy` | 运营可配 | 命中该等级默认受众策略 |
| `output_fields` | 运营可配 | process skill 输出字段约定 |

### 5.5 SOP 等级字典表

等级定义必须与 SOP 强绑定。系统不得假设全局 `P0/P1/P2/notice`。

| 字段 | 职责 | 说明 |
|---|---|---|
| `sop_level_id` | 运营可配 | SOP 内等级唯一 ID，例如 `review_latency_red` |
| `sop_id` | 运营可配 | 关联 SOP |
| `level_label` | 运营可配 | SOP 展示标签，例如 `P1`、`红灯`、`L2` |
| `level_name` | 运营可配 | 等级名称 |
| `normalized_severity` | 运营可配 | 跨 SOP 排序/展示用，例如 `critical`、`high`、`medium`、`low` |
| `priority_order` | 运营可配 | 数字越小优先级越高 |
| `sla_minutes` | 运营可配 | SLA 分钟数 |
| `sla_text` | 运营可配 | SLA 文案 |
| `requires_human_confirm` | 运营可配 | 是否需要人工确认 |
| `default_audience_policy` | 运营可配 | 默认受众策略 |
| `escalation_policy` | 运营可配 | 超时或高等级升级策略 |
| `enabled` | 运营可配 | 是否启用 |

Task 2.5 要求的最小字段为：`sop_level_id`、`level_label`、`normalized_severity`、`priority_order`、`sla_minutes`、`requires_human_confirm`、`default_audience_policy`。实际建表建议同时保留 `sop_id`，否则无法保证等级与 SOP 强绑定。

### 5.6 SOP 角色目录表

| 字段 | 职责 | 说明 |
|---|---|---|
| `role_alias_id` | 运营可配 | 角色别名唯一 ID |
| `sop_id` | 运营可配 | 为空可表示全局角色，非空表示 SOP 专属 |
| `role_alias` | 运营可配 | 例如 治理 BP、审核 VOC POC、人审运营、CQC 负责人 |
| `role_name` | 运营可配 | 展示名称 |
| `default_user` | 运营可配 | 默认人员，需通过通讯录解析 |
| `default_chat_id` | Agent 回写/受控配置 | 复用群聊时使用，必须校验 |
| `required` | 运营可配 | 是否为必达角色 |
| `escalation_order` | 运营可配 | 升级顺序 |
| `enabled` | 运营可配 | 是否启用 |

### 5.7 业务对象责任映射表

| 字段 | 职责 | 说明 |
|---|---|---|
| `mapping_id` | 运营可配 | 映射唯一 ID |
| `sop_id` | 运营可配 | 关联 SOP |
| `route_grain` | 运营可配 | `reason`、`strategy`、`queue`、`group`、`scene`、`project` |
| `route_key` | 运营可配 | 业务对象主键 |
| `route_key_alias` | 运营可配 | 可读别名 |
| `owner_role` | 运营可配 | 业务 POC、策略 owner、群组负责人等 |
| `owner_user` | 运营可配 | 负责人 |
| `collaborators` | 运营可配 | 协作方 |
| `escalation_users` | 运营可配 | 升级人 |
| `default_chat_id` | Agent 回写/受控配置 | 对象专属群，可为空 |
| `default_chat_name` | 运营可配/Agent 回写 | 对象专属群名 |
| `effective_start` | 运营可配 | 生效开始时间 |
| `effective_end` | 运营可配 | 生效结束时间 |
| `enabled` | 运营可配 | 是否启用 |
| `priority` | 运营可配 | 多条映射命中时排序 |
| `notes` | 运营可配 | 说明 |

### 5.8 Owner Source 注册表

| 字段 | 职责 | 说明 |
|---|---|---|
| `owner_source_id` | 运营可配 | owner 来源唯一 ID |
| `sop_id` | 运营可配 | 关联 SOP |
| `route_grain` | 运营可配 | owner 解析粒度 |
| `source_type` | 运营可配 | `lark_base_table`、`query_template`、`process_output`、`manual_fallback` |
| `source_ref` | 运营可配 | 表 token、query key、输出字段路径等 |
| `key_field` | 运营可配 | 与 hit row 匹配的 key 字段 |
| `owner_fields` | 运营可配 | owner/collaborator/escalation 字段映射 |
| `fallback_policy` | 运营可配 | missing owner 时是否停止、是否人工兜底 |
| `freshness_policy` | 运营可配 | 来源新鲜度要求 |
| `enabled` | 运营可配 | 是否启用 |

### 5.9 SOP 运行实例表

| 字段 | 职责 | 说明 |
|---|---|---|
| `run_id` | 系统派生 | 单次运行唯一 ID |
| `sop_id` | 系统派生 | 运行的 SOP |
| `run_mode` | 系统派生 | 本次运行模式 |
| `trigger_type` | 系统派生 | 手动、定时、回放、shadow |
| `triggered_by` | Agent 回写 | 触发人或系统 |
| `config_version` | 系统派生 | 本次读取的配置版本 |
| `period_start` / `period_end` | 系统派生 | 本次周期 |
| `node_trace` | Agent 回写 | 每个节点输入、输出、状态、耗时、失败原因 |
| `run_status` | Agent 回写 | `success`、`failed`、`blocked`、`partial` |
| `artifact_refs` | Agent 回写 | summary、CSV、workbook、sheet、card 等产物路径 |
| `error_code` / `error_message` | Agent 回写 | 失败原因 |
| `started_at` / `finished_at` | 系统派生/Agent 回写 | 运行时间 |

### 5.10 Process Skill 注册表

| 字段 | 职责 | 说明 |
|---|---|---|
| `process_skill` | 运营可配/平台维护 | Skill 名称，必须与包内名称一致 |
| `business_domain` | 运营可配 | 支持的业务域 |
| `supported_sop_types` | 运营可配 | 支持的 SOP 类型 |
| `input_contract` | 平台维护 | 标准输入字段 |
| `output_contract` | 平台维护 | 标准输出目录和字段 |
| `supported_report_types` | 平台维护 | 可发布的 report type |
| `required_domain_reference` | 平台维护 | 必读 reference |
| `validation_command` | 平台维护 | 验证命令或 smoke test |
| `status` | 平台维护 | draft、beta、active、deprecated |

### 5.11 Report Template 注册表

| 字段 | 职责 | 说明 |
|---|---|---|
| `report_type` | 运营可配/平台维护 | 例如 `low_efficiency_grading` |
| `template_id` | 平台维护 | CardKit 模板 ID，可为空 |
| `local_template_name` | 平台维护 | 本地模板文件名 |
| `supported_sop_types` | 平台维护 | 支持的 SOP |
| `required_artifacts` | 平台维护 | 需要的 summary、CSV、workbook |
| `required_variables` | 平台维护 | 卡片必填变量 |
| `renderer` | 平台维护 | 渲染入口 |
| `channel` | 运营可配 | 群、私聊、报告-only |
| `identity_policy` | 运营可配 | bot/user/fallback |
| `idempotency_policy` | 平台维护 | 幂等 key 生成规则 |
| `enabled` | 运营可配 | 是否启用 |

## 6. 最小可执行配置集

一条配置要能驱动 Agent 串联，至少必须能解析出下表字段。缺任一核心字段时，orchestrator 必须停止在配置校验阶段，不进入分析或触达。

| 字段 | 来源表 | 用途 | 校验 |
|---|---|---|---|
| `sop_id` | SOP 注册表 | 运行根对象 | 必填、唯一、启用 |
| `sop_type` | SOP 注册表 | 选择节点模板和 process skill 类型 | 枚举合法 |
| `metric_id` | SOP 指标/观测对象表 | 指定观测对象 | 必须挂当前 `sop_id` |
| `business_domain` | SOP 注册表 / 指标表 | 定位 domain reference 和 warehouse reference | 两处一致 |
| `process_skill` | SOP 注册表 | 决定调用哪个过程 Skill | 必须在 Process Skill 注册表启用 |
| `domain_reference` | SOP 注册表 / Process Skill 注册表 | 决定指标口径、字段、gotchas | 文件或 registry 必须存在 |
| `data_source_id` | SOP 指标/观测对象表 / 数据源表 | 决定 freshness 和取数底座 | 数据源启用，字段映射完整 |
| `rule_set` | SOP 规则组表 | 决定判断条件和等级 | 至少一个生效规则组，等级存在 |
| `report_type` | SOP 注册表 / Report Template 注册表 | 决定报告发布模板 | 必须注册且支持 process skill 输出 |
| `route_policy` | SOP 路由策略 / Owner Source 注册表 | 决定 owner 解析粒度和兜底 | owner source 存在，route grain 在输出中存在 |
| `touch_policy` | 触达策略 / Report Template 注册表 | 决定是否触达、发哪里、是否人工确认 | 模板、角色、chat 策略合法 |
| `state_policy` | SOP 注册表 / SOP 节点表 | 决定状态推进和停止规则 | 节点顺序合法，fail policy 完整 |

推荐同时解析但不列为 Task 2.4 最小字段的运行辅助字段：

- `period_policy`：将“近 7 天”“10min 窗口”“预计全天”转成可执行窗口。
- `output_contract`：校验 process skill 是否产出 `summary.json`、CSV、workbook、events。
- `owner_source` 与 `route_grain`：对象级路由必需。
- `config_version`：run 审计和回滚必需。

## 7. 配置驱动链路

一次 SOP 运行的配置解析顺序：

1. 用 `sop_id` 读取 SOP 注册表，确认启用、运行模式、process skill、domain reference、默认 report type。
2. 读取 SOP 节点表，确认本次需要执行 freshness、analysis、report、route、touch、state 哪些节点。
3. 读取 SOP 指标/观测对象表与数据源表，解析 metric、data source、字段映射、period policy、freshness policy。
4. 读取 SOP 规则组表与 SOP 等级字典表，解析 `rule_set`、等级、优先级、SLA、人工确认和默认受众。
5. 调用 process skill，校验输出契约。
6. 用 `route_policy` 读取 Owner Source 注册表和业务对象责任映射表，得到每条 hit 的 `route_result`。
7. 用 `touch_policy` 和 Report Template 注册表选择报告模板、卡片模板、发送对象、人工确认策略。
8. 由 orchestrator 写 SOP 运行实例和事件状态；横向 skill 只写自身审计结果，不擅自推进状态机。

## 8. 配置校验规则

### 8.1 基础完整性校验

- SOP 注册表：`sop_id`、`sop_type`、`business_domain`、`process_skill`、`domain_reference`、`run_mode` 必填。
- SOP 节点表：启用节点必须有 `node_order`、`required_inputs`、`output_contract`、`fail_policy`。
- SOP 指标/观测对象表：启用指标必须有 `sop_id`、`metric_id`、`data_source_id`、`grain` 或明确可由 process skill 默认。
- 数据源表：启用数据源必须有 `data_source_id`、`数据源类型`、`数据集/表标识`、`日期字段`、`数据延迟天数`、`freshness_policy`。
- SOP 规则组表：生效规则必须有 `sop_id`、`rule_group_id`、`sop_level_id`、`condition_logic`、`metric_refs`。

### 8.2 关联关系校验

- `metric_id.sop_id` 必须存在于 SOP 注册表。
- `rule_group.sop_level_id` 必须存在于同一个 `sop_id` 的 SOP 等级字典表。
- `process_skill` 必须存在于 Process Skill 注册表，且支持当前 `sop_type`。
- `report_type` 必须存在于 Report Template 注册表，且支持当前 process skill 的输出。
- `owner_source_id` 必须存在且启用。
- `role_alias` 必须存在于 SOP 角色目录或全局角色目录。

### 8.3 枚举与注册校验

- `run_mode` 只能是 `baseline`、`shadow`、`canary`、`active`、`rollback`。
- `source_type` 只能是已允许值：`lark_base_table`、`query_template`、`process_output`、`manual_fallback`。
- `normalized_severity` 只能使用系统允许枚举，但不能替代 `level_label`。
- `rule_key/sql_key` 必须存在于 process skill 注册的模板清单。
- `report_type`、`local_template_name`、`cardkit_template_id` 必须已注册。

### 8.4 安全与门禁校验

- 配置中出现 access token、app secret、tenant token 时直接失败。
- 配置中出现未注册 SQL 模板骨架、Python 片段、任意 shell 命令时直接失败。
- `requires_human_confirm=true` 的等级不得配置自动绕过确认。
- `touch_policy.auto_send=true` 时，必须先通过 owner、模板、chat_id 或建群策略校验。
- `chat_id` 若存在必须为 `oc_` 开头，并与路由策略来源一致；不能把临时群 ID 当通用配置。

### 8.5 数据与输出校验

- freshness gate 未通过时，不允许进入判断，不写事件主表。
- process skill 输出必须满足注册的 `output_contract`。
- `route_grain` 必须存在于 process skill 的 hit row 输出字段，或由映射规则明确派生。
- 多条 hit 对应不同 owner 时，触达策略必须声明拆分或合并规则。
- `missing_object_owner=true` 时，只有显式 fallback policy 允许继续，否则停止触达。

### 8.6 状态与回写校验

- 事件状态只能由 orchestrator 按 `state_policy` 推进。
- dry-run 不得写事件表、触达记录表、建群或发送消息。
- shadow 模式只允许产出报告和对比，不写事件主表、不触达。
- canary 模式只能作用于明确配置的 SOP、等级或业务对象范围。

## 9. 配置失败提示格式

配置校验失败时，输出必须面向运营可修复，至少包含表名、记录、字段、错误原因、期望值、当前值、修复建议和停止规则。

标准格式：

```text
配置校验失败
code: <ERROR_CODE>
severity: <error|warning>
sop_id: <sop_id>
run_mode: <baseline|shadow|canary|active|rollback>
table: <表名>
record: <record_id 或业务键>
field: <字段名>
reason: <失败原因>
expected: <期望值或规则>
actual: <当前值>
fix_hint: <运营可执行的修复建议>
stop_rule: <系统本次如何停止或降级>
```

示例：

```text
配置校验失败
code: UNREGISTERED_PROCESS_SKILL
severity: error
sop_id: review_latency
run_mode: active
table: SOP 注册表
record: sop_id=review_latency
field: process_skill
reason: process_skill 未在 Process Skill 注册表启用
expected: 已注册且 status=active 的 process skill
actual: review-latency-analysis
fix_hint: 在 Process Skill 注册表补充 review-latency-analysis，并填写 input/output contract 与 validation_command；或将 SOP 置为 shadow/draft
stop_rule: 停止本 SOP，不进入数据取数和触达
```

```text
配置校验失败
code: SOP_LEVEL_NOT_FOUND
severity: error
sop_id: low_efficiency_labeling
run_mode: shadow
table: SOP 规则组表
record: rule_group_id=low_efficiency_p2
field: sop_level_id
reason: 规则组引用的等级不属于当前 SOP
expected: SOP 等级字典表中存在 sop_id=low_efficiency_labeling 且启用的 sop_level_id
actual: P2
fix_hint: 在 SOP 等级字典表新增或关联正确的 sop_level_id，例如 low_efficiency_p2
stop_rule: 跳过该规则组；若 SOP 无其他生效规则组，则停止本 SOP
```

```text
配置校验失败
code: OWNER_SOURCE_MISSING
severity: error
sop_id: review_latency
run_mode: canary
table: Owner Source 注册表
record: route_policy=queue_owner_policy
field: owner_source_id
reason: 路由策略引用的 owner source 不存在或未启用
expected: 已启用 owner_source_id，且 route_grain=queue_id
actual: 空
fix_hint: 注册 queue owner 来源，或将 touch_policy.auto_send=false 只发布报告
stop_rule: 分析可继续，事件触达停止，不发送给兜底群
```

```text
配置校验失败
code: FORBIDDEN_EXECUTABLE_CONFIG
severity: error
sop_id: low_efficiency_labeling
run_mode: active
table: SOP 规则组表
record: rule_group_id=custom_rule_001
field: rule_params
reason: 配置中包含疑似 SQL/Python 执行片段
expected: 只允许已注册 sql_key 的参数 JSON 或五章节规则描述
actual: SELECT ...; DROP ...
fix_hint: 删除执行片段，改为选择已注册 sql_key；新增模板需走代码评审和测试
stop_rule: 停止本规则组，不渲染 SQL，不触达
```

## 10. 迁移落点摘要

Task 1/2 的目标交付不是建表或写代码，而是明确后续迁移时的模型边界：

- 旧 9 表不是废弃重建，而是保留可复用审计表、增强数据源和触达表、将指标/规则/等级降级到 SOP 下。
- `review-monitoring-shared` 应先承接本文的 SOP-first schema 和 lint 规则。
- `owner-routing` 的下一步重点不是优化旧匹配，而是增加 Owner Source 注册和对象级 `route_result`。
- `anomaly-touch` 的下一步重点是将报告发布和正式事件触达都绑定到 Report Template 注册表与 SOP 触达策略。
- `monitoring-orchestrator` 是后续 Task 3 的核心缺口，必须读取 SOP 配置而不是直接读取“启用指标”。
