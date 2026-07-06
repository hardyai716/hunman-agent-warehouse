# 人审运营 AI 监控自动化体系实施路线图

本文基于当前架构设计方案，明确从已跑通的低效策略链路迁移到 SOP-first 多 Skill 体系的实施顺序、模块优先级、依赖关系和阶段验收标准。

## 1. 路线图原则

1. 先保护 baseline，再引入新编排。当前已跑通的低效策略查询、维度拆解、飞书表格发布和报告卡片推送必须保持可独立运行。
2. 先做契约和校验，再做自动执行。SOP-first 配置、registry、lint、dry-run 没有闭环前，不进入自动触达。
3. 先复用低效策略作为 canary，再扩展审核延时 SOP。低效策略已有 process skill、SQL 模板和报告发布能力，是最小风险验证样例。
4. 先 report-only / shadow，再 canary / active。新链路初期只产报告、审计和对比结果，不写主事件表、不触达 POC。
5. 横向能力必须先于新业务 SOP 稳定。`review-monitoring-shared`、`anomaly-touch`、`owner-routing`、`monitoring-orchestrator` 的契约稳定后，再扩展质量、成本等业务域。

## 2. 模块优先级总览

| 优先级 | 模块 | 目标 | 主要产物 | 依赖 |
|---|---|---|---|---|
| P0 | Baseline 保护与回归门禁 | 确保当前低效策略链路不被新架构破坏 | smoke test 脚本、稳定 zip、baseline runbook | 现有 `low-efficiency-strategy-analysis`、`anomaly-touch`、打包脚本 |
| P0 | `review-monitoring-shared` 契约底座 | 承接 SOP-first schema、registry schema、lint 公共逻辑 | SOP schema、registry schema、validation report schema、lint CLI | 现有 `base_schema.md`、`card_validator.py` |
| P0 | Process Skill Registry / Report Template Registry | 限制可调用 process skill 和 report type | registry 配置文件、校验器、manifest 对齐规则 | `review-monitoring-shared` |
| P0 | 配置 lint 与 dry-run 框架 | 阻断缺配置、未注册 skill、未注册等级、危险触达 | `validate_config` 命令、validation report JSON | SOP schema、registry schema |
| P1 | `anomaly-touch` 报告发布配置化 | 把 `publish_lark_report.py` 从 CLI 参数升级为配置驱动能力 | report policy 解析、template registry 校验、dry-run 输出 | Report Template Registry、现有发布脚本 |
| P1 | `owner-routing` 对象级路由 MVP | 支持 `reason/strategy -> owner`，输出 `route_result` | Owner Source registry、对象映射解析、missing owner 策略 | SOP 等级字典、process 输出契约 |
| P1 | `monitoring-orchestrator` MVP | 串联配置读取、lint、process、报告发布、审计，不做正式触达 | `manual`、`report_only`、`shadow` 运行模式，`run_audit.jsonl` | shared lint、process registry、anomaly-touch dry-run |
| P1 | 低效策略 SOP-first canary | 用现有低效策略验证新配置和新 orchestrator | `low_efficiency_labeling` SOP 配置、shadow 对比、P2 canary | orchestrator MVP、owner-routing MVP 可选 |
| P2 | `owner-routing` 完整触达策略 | 支持角色目录、等级受众、群聊/私聊/临时群策略 | 角色目录解析、chat_strategy、分组触达计划 | Owner Source MVP、SOP 等级字典 |
| P2 | `anomaly-touch` 正式事件触达 | 基于 `route_result` 渲染事件卡片、人工确认、发送与触达记录 | touch preview、hash 校验、touch record、message_id 写回 | owner-routing 完整输出、orchestrator 状态机 |
| P2 | `monitoring-orchestrator` 完整状态机 | 支持事件预览、状态推进、touch_execute、节点重试与降级 | 运行实例状态、事件状态、节点 retry、resume | 事件表契约、anomaly-touch 触达 |
| P2 | `review-latency-analysis` | 新增审核延时 SOP process skill | 审核延时 domain reference、SQL/查询模板、summary/workbook | warehouse 口径、process registry、report template |
| P3 | 质量/成本域扩展 | 接入自动处置准确率、成本类 SOP | 新 domain reference、新 process skill、新 report type | P0-P2 横向能力稳定 |

## 3. 推荐实施阶段

### Phase 0：基线冻结与回归门禁

目标：把当前已跑通链路固化为回归基线，任何新开发先过 baseline。

开发项：

- 固化低效策略 P2、全等级、机审一级标签维度拆解的 smoke test 命令。
- 固化 report publishing dry-run 和真实发送前校验命令。
- 保留上一稳定 `dist/agent_upload/zips/*.zip` 和 manifest。
- 为 `tools/package_agent_skills.py` 增加或保留输出目录保护，禁止清理源码目录。

验收标准：

- `test_sql_templates.py`、`test_card_validator.py`、`test_report_publisher.py` 全部通过。
- `python3 tools/package_agent_skills.py` 可生成 6 个根级包含 `SKILL.md` 的单 Skill zip，包含新增 `monitoring-orchestrator`。
- baseline runbook 明确“新链路失败时如何回到旧直跑路径”。

依赖关系：

```text
无上游依赖
  -> 后续所有阶段的合入门禁
```

### Phase 1：SOP-first 契约与配置校验

目标：先让配置可被机器校验，不急于自动执行。

开发项：

- 在 `review-monitoring-shared` 中新增 SOP-first schema 定义：
  - SOP 注册表
  - SOP 节点表
  - SOP 指标/观测对象表
  - SOP 规则组表
  - SOP 等级字典表
  - SOP 角色目录表
  - Owner Source 注册表
  - Process Skill Registry
  - Report Template Registry
- 实现配置 lint：
  - 必填字段
  - 关联关系
  - 枚举值
  - process skill 是否注册
  - report type 是否注册
  - `sop_level_id` 是否属于当前 SOP
  - `route_grain` 是否在 process 输出契约中存在
- 输出 `validation_report.v1`，让运营可按表名、记录、字段修复。

验收标准：

- 构造低效策略 SOP 样例配置，lint 通过。
- 构造未注册 process skill、跨 SOP 等级、shadow 自动触达、缺 owner source 等反例，lint 必须失败。
- validation report 能输出 `severity`、`table_name`、`record_key`、`field_name`、`fix_hint`。

依赖关系：

```text
Phase 0 baseline
  -> SOP schema
  -> Registry schema
  -> Config lint
  -> Validation report
```

### Phase 2：报告发布配置化与 process 输出契约收敛

目标：先把“报告发布”做成配置驱动能力，避免直接进入高风险触达。

开发项：

- 将 `publish_lark_report.py` 的参数映射为 report policy：
  - `report_type`
  - `template_name`
  - `sheet_policy`
  - `report_target_policy`
  - `sender_identity`
  - `render_options`
  - `idempotency_policy`
- 为现有三类低效报告注册模板：
  - `low_efficiency_dimension_breakdown`
  - `low_efficiency_grading`
  - `low_efficiency_level_detail`
- 统一 process skill 标准产物目录校验：
  - `summary.json`
  - 明细 CSV
  - 汇总 CSV
  - workbook
  - provenance 或 fallback reason
- 增加 report publishing dry-run，不导入、不发送，只生成卡片和 publish summary。

验收标准：

- 现有低效策略 run dir 可以通过 report policy 完成 dry-run 渲染。
- 发送版卡片剥离 `_meta`，表格列宽不小于 80px。
- 幂等 key 安全化且长度受控。
- 缺 report type、缺模板、缺必填变量时必须被 lint 或 dry-run 阻断。

依赖关系：

```text
Phase 1 Registry schema
  -> Report Template Registry
  -> Report policy parser
  -> publish_lark_report config adapter
  -> report-only dry-run
```

### Phase 3：对象级 owner-routing MVP

目标：先支持低效策略的 `reason/strategy -> owner`，为正式触达铺路。

开发项：

- 在 `owner-routing` 中实现 Owner Source Registry 解析。
- 支持 `lark_base_table` 或本地样例映射作为第一版 owner source。
- 支持低效策略 route grain：
  - `reason`
  - `strategy`
- 输出标准 `route_result`：
  - business object
  - owner source
  - owners / collaborators / escalation
  - delivery policy
  - route confidence
  - `missing_object_owner`
- 缺 owner 时只允许 report 标注或转人工，不允许发给任意指标负责人。

验收标准：

- 同一等级、同一指标下，不同 reason 可解析到不同 owner。
- 未命中 owner 时返回 `missing_object_owner=true`。
- `route_result` 可被 report card 或后续 touch card 消费。
- route grain 不在 process 输出字段中时，配置 lint 失败。

依赖关系：

```text
Phase 1 SOP level dictionary
Phase 1 Owner Source Registry
Process skill output contract
  -> owner-routing MVP
  -> route_result schema
```

### Phase 4：`monitoring-orchestrator` MVP

目标：建立流程权威，但第一版只做 `manual`、`report_only`、`shadow`，不做正式触达。

开发项：

- 新建 `通用能力/monitoring-orchestrator/`。
- 实现运行输入契约：
  - `run_mode`
  - `sop_id`
  - `period`
  - `config_version`
  - `report_type`
  - `dry_run`
- 实现节点计划编译：
  - `config_load`
  - `config_lint`
  - `data_ready_gate`
  - `process_analysis`
  - `report_publish`
  - `audit_finalize`
- 生成 `run_id`、运行摘要和 `run_audit.jsonl`。
- 支持从 `metric_id` 兼容解析到唯一 SOP 观测对象。
- 禁止在 `report_only` 和 `shadow` 下写事件主表、建群、发送正式触达。

验收标准：

- 能驱动低效策略 P2 report-only：配置读取、process 执行、报告 dry-run、审计输出完整。
- 数据未就绪时状态为 `waiting_data` 或 `failed`，不得解释成无命中。
- process 输出缺文件时状态为 `blocked`，不得进入发布。
- shadow 运行能与 baseline 同 period 对比，并输出差异摘要。

依赖关系：

```text
Phase 1 Config lint
Phase 2 Report publishing config
Phase 0 Baseline runbook
  -> monitoring-orchestrator MVP
```

### Phase 5：低效策略 SOP-first canary

目标：用最低风险的现有业务链路验证新架构闭环。

开发项：

- 配置 `sop_id=low_efficiency_labeling`。
- 将低效策略 P2、全等级、维度拆解挂到 SOP 指标、规则组、等级字典和 report policy。
- shadow 双跑：
  - 新 orchestrator 产物
  - baseline 直跑产物
  - 结果行数、Top reason、核心指标差异对比
- P2 canary：
  - 先只开启 report publishing
  - owner-routing 只生成 route preview
  - 不自动触达 POC

验收标准：

- 同一 period 下，新旧链路主要行数和 Top 命中原因可解释一致。
- P2 报告卡片通过 hash、等级、chat_id、结构校验。
- canary 期间其他等级和其他 SOP 不受影响。

依赖关系：

```text
Phase 4 Orchestrator MVP
Phase 3 owner-routing MVP 可选
低效策略现有 process skill
  -> low_efficiency_labeling shadow
  -> P2 canary
```

### Phase 6：正式事件触达与状态机

目标：在 report-only 稳定后，再打通真正的异常触达和状态推进。

开发项：

- 扩展 `owner-routing`：
  - SOP 角色目录
  - 等级受众策略
  - 群聊、私聊、临时群策略
  - 多 POC 分组触达计划
- 扩展 `anomaly-touch`：
  - event touch card 模板
  - touch preview
  - 人工确认 gate
  - 发送前 hash / level / chat_id 校验
  - touch record 写入契约
- 扩展 `monitoring-orchestrator`：
  - `event_build`
  - `owner_routing`
  - `touch_render`
  - `human_confirm`
  - `touch_send`
  - `state_update`
  - `touch_execute`
- 引入事件状态和运行实例状态。

验收标准：

- 缺 owner、缺模板变量、hash 不一致、chat_id 不一致时必须阻断发送。
- P1/P0 或高风险等级未人工确认时停在 `waiting_confirm`。
- 多个 owner 的命中行按 `chat_strategy` 分组，不发送给无关 POC。
- 发送失败可通过 `touch_execute` 从已校验产物恢复，不默认重跑分析。

依赖关系：

```text
Phase 3 route_result
Phase 5 low-efficiency canary
SOP role directory
Touch template registry
  -> formal anomaly touch
  -> state machine
```

### Phase 7：审核延时 SOP 扩展

目标：验证新架构能支持第二个 SOP，而不是只服务低效策略。

开发项：

- 新增审核延时 domain reference：
  - 进审增幅
  - 机审增幅
  - 实时延时
  - 预计全天进审
  - 目标值
  - 10min 窗口和连续窗口口径
- 新建 `review-latency-analysis` process skill：
  - 注册 input/output contract
  - 支持 P2/P1/P0 规则组
  - 输出 `queue_id`、`queue_name`、`group_id`、`scene` 等 route grain 字段
- 注册 `review_latency_summary` report type 和模板。
- 配置 `queue/group/scene -> owner` Owner Source。
- 先 shadow，再 canary。

验收标准：

- 审核延时 P2/P1/P0 规则能用配置表达，不依赖全局 P0/P1/P2 枚举。
- process 输出字段满足 route grain 配置。
- shadow 下只产报告和路由预览，不写事件主表、不触达。
- canary 前通过 lint、dry-run、report publishing dry-run 和卡片安全校验。

依赖关系：

```text
Phase 1 SOP-first config
Phase 4 orchestrator MVP
Phase 6 routing/touch/state 可按需要启用
  -> review-latency-analysis
  -> review_latency shadow/canary
```

### Phase 8：多业务域扩展与 active 切换

目标：形成可复用的 SOP 接入方法，支持质量、成本等新业务域。

开发项：

- 为质量域自动处置准确率新增 domain reference 和 process skill。
- 为成本域新增对应 domain reference 和 process skill。
- 把 SOP 接入步骤标准化：
  - domain reference
  - process skill
  - process registry
  - report type
  - SOP 配置
  - owner source
  - validation report
  - shadow
  - canary
  - active
- 建立版本切换机制：
  - `baseline`
  - `shadow`
  - `canary`
  - `active`
  - `rollback`

验收标准：

- 新 SOP 接入不需要修改低效策略代码。
- 未注册 process skill、未注册 report type、缺 owner source 时 lint 必须失败。
- active 前保留上一稳定配置快照、代码 tag 和 zip 包。

依赖关系：

```text
Phase 0-7 横向能力稳定
  -> 新业务域 SOP 模板化接入
  -> active rollout
```

## 4. 模块依赖图

```text
Baseline 保护
  -> review-monitoring-shared SOP schema
    -> Process Skill Registry
    -> Report Template Registry
    -> Owner Source Registry
    -> Config lint / Validation report
      -> anomaly-touch 报告发布配置化
      -> owner-routing 对象级路由
        -> anomaly-touch 正式事件触达
      -> monitoring-orchestrator MVP
        -> 低效策略 SOP-first shadow/canary
        -> monitoring-orchestrator 完整状态机
          -> 审核延时 SOP shadow/canary
            -> 质量/成本域扩展
```

关键串行依赖：

- `monitoring-orchestrator` 不能早于配置 lint 和 registry，否则会把错误配置执行起来。
- 正式 `anomaly-touch` 不能早于 `owner-routing` 的 `route_result`，否则无法保证结果发给正确 POC。
- `review-latency-analysis` 可以先设计，但进入 canary 前必须先注册 process skill、report type、SOP level、Owner Source。
- `active` 切换不能早于 shadow/canary 和 rollback 快照。

可并行开发：

- `review-monitoring-shared` 的 schema/lint 与 `anomaly-touch` report policy adapter 可以并行，但合并时必须统一 Report Template Registry。
- `owner-routing` MVP 与 `monitoring-orchestrator` MVP 可以并行；orchestrator 第一版可先跳过正式触达，只消费 route preview。
- `review-latency-analysis` 的 domain reference 可与 Phase 4/5 并行准备，但 runtime canary 必须等横向能力稳定。

## 5. 首批落地任务建议

第一批建议只做 P0/P1，目标是在低效策略上跑通 SOP-first report-only。

| 顺序 | 任务 | 模块 | 交付物 | 阻塞关系 |
|---:|---|---|---|---|
| 1 | 固化 baseline smoke tests | 现有模块 | 一键回归命令和 runbook | 无 |
| 2 | 定义 registry 配置文件格式 | `review-monitoring-shared` | `process_skill_registry`、`report_template_registry`、`owner_source_registry` schema | 任务 1 |
| 3 | 实现配置 lint MVP | `review-monitoring-shared` | validation report JSON | 任务 2 |
| 4 | 改造报告发布为 policy adapter | `anomaly-touch` | report policy 到 CLI 参数的适配层 | 任务 2 |
| 5 | 实现 owner-routing MVP | `owner-routing` | reason/strategy owner 解析和 `route_result` | 任务 2、3 |
| 6 | 新建 orchestrator MVP | `monitoring-orchestrator` | manual/report_only/shadow 运行入口和审计日志 | 任务 3、4 |
| 7 | 配置低效策略 SOP 样例 | 配置中心/样例 | `low_efficiency_labeling` SOP 配置样例 | 任务 3、4、6 |
| 8 | 低效策略 shadow 双跑 | orchestrator + process skill | 新旧链路对比报告 | 任务 7 |
| 9 | 低效策略 P2 report canary | orchestrator + anomaly-touch | P2 报告真实发布或受控发布 | 任务 8 |

第一批暂不做：

- 自动建群。
- POC 正式触达。
- 多 SOP active 自动调度。
- 质量/成本域新增 process skill。
- 案例沉淀转规则闭环。

## 6. 进入下一阶段的决策门槛

| 阶段 | 可进入下一阶段的条件 |
|---|---|
| Phase 0 -> Phase 1 | baseline 测试和打包验证稳定，回滚路径明确 |
| Phase 1 -> Phase 2 | SOP 样例配置 lint 通过，反例能被阻断 |
| Phase 2 -> Phase 3 | report-only dry-run 能稳定生成卡片和 publish summary |
| Phase 3 -> Phase 4 | route_result 能覆盖低效策略 reason/strategy，missing owner 可审计 |
| Phase 4 -> Phase 5 | orchestrator 能完成低效策略 report-only 且不产生越权副作用 |
| Phase 5 -> Phase 6 | 低效策略 shadow 与 baseline 差异可解释，P2 canary 稳定 |
| Phase 6 -> Phase 7 | 正式触达安全门禁可阻断缺 owner、缺确认、hash/chat_id 不一致 |
| Phase 7 -> Phase 8 | 审核延时 SOP shadow/canary 验证通过，第二个 SOP 不需要复制低效策略逻辑 |

## 7. 风险与控制点

| 风险 | 影响 | 控制点 |
|---|---|---|
| 过早实现 orchestrator，配置尚不可校验 | 错误配置被执行，可能误触达 | Phase 1 必须先完成 lint 和 validation report |
| owner-routing 不完整就启用触达 | 结果发给无关 POC | 正式触达必须依赖 `route_result`，缺 owner 阻断 |
| 把外部平台能力写成项目内 sibling | 上传包校验失败或依赖膨胀 | `required_siblings` 只写项目内 Skill，`lark-*`、`sqless`、`bytedcli` 放 runtime dependencies |
| 新链路覆盖 baseline 产物 | 无法回滚或对比 | 新产物必须带 `run_id` 和 `config_version`，baseline 目录只读 |
| 等级标签被全局化 | 不同 SOP 的 P0/P1/P2 SLA 和受众混用 | 所有等级解析必须使用 `(sop_id, sop_level_id)` |
| report publishing 与 anomaly touch 混淆 | 报告群变成行动触达，或事件无审计 | 报告发布不写 touch record，正式触达必须走 owner-routing 和人工确认 gate |

## 8. 推荐近期里程碑

| 里程碑 | 范围 | 结果 |
|---|---|---|
| M1：配置可校验 | Phase 0-1 | 低效策略 SOP 样例配置可 lint，错误配置可定位到表和字段 |
| M2：报告可编排 | Phase 2-4 | orchestrator 能以 report-only 跑低效策略并生成审计 |
| M3：低效策略 canary | Phase 5 | P2 报告通过新链路受控发布，baseline 可随时回退 |
| M4：正式触达闭环 | Phase 6 | route_result、touch preview、人工确认、发送记录和状态推进闭环 |
| M5：审核延时 SOP | Phase 7 | 第二个 SOP 通过 shadow/canary，证明架构可复用 |
| M6：多域扩展 | Phase 8 | 质量、成本等新域按模板接入，不复制低效策略全流程 |
