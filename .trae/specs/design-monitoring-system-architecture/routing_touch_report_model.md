# 配置驱动的报告发布与触达复用模型

本文定义 Task 5 的目标设计：把 `anomaly-touch` 中已跑通的飞书报告发布能力抽象为配置驱动的横向能力，同时把正式异常触达建立在对象级责任路由之上，避免继续依赖“指标 + 等级 + 适用范围”的粗粒度匹配。

## 1. 设计目标

目标链路分为两个互相独立但可串联的节点：

| 节点 | 目标 | 典型产物 | 是否必须 owner-routing | 是否写触达记录 |
|---|---|---|---|---|
| Report Publishing | 将标准分析目录发布为飞书电子表格和报告卡片 | `*.card.json`、`*.card.with_meta.json`、`*.publish_summary.json`、sheet URL、message_id | 否 | 否，最多写报告发布日志 |
| Anomaly Touch | 将已确认的异常事件或命中行发送给责任对象 | 事件卡片、preview、正式消息、touch_record、message_id | 是 | 是 |

核心原则：

- 报告发布面向“看全局结果的人”，例如人审运营、SOP owner、复盘群；不等于正式事件触达。
- 正式异常触达面向“需要行动的人”，必须先按业务对象解析 owner，再决定群聊、私聊或临时群。
- `anomaly-touch` 负责卡片渲染、人工确认、发送校验、消息发送和触达记录；不负责判断异常，也不负责匹配责任人。
- `owner-routing` 负责对象 owner、角色受众、升级对象、SLA 和通道策略；不发送消息。
- `monitoring-orchestrator` 是流程权威，决定是否只发布报告、是否进入正式触达、是否推进事件状态。

## 2. 报告发布配置模型

现有 `publish_lark_report.py` 的命令行参数应进入 `Report Publish Policy` 和 `Report Template Registry`，由 SOP 配置解析后传给发布入口。

| 当前参数/常量 | 目标配置字段 | 说明 |
|---|---|---|
| `--report-type` | `report_type` | 必须来自已注册 report type，例如 `low_efficiency_dimension_breakdown`、`low_efficiency_grading`、`low_efficiency_level_detail` |
| 模板函数/模板名 | `template_name`、`local_template_name`、`cardkit_template_id` | 支持本地 Card 2.0 模板和未来 CardKit 模板 |
| `--target-user` / `--target-chat` | `report_target_policy` | 报告推送对象，可来自固定用户、固定群、SOP 角色目录或运行时指定 |
| `--sheet-url` | `sheet_policy.source_url` | 复用已有电子表格时使用 |
| 未传 `--sheet-url` 时导入 xlsx | `sheet_policy.strategy=import_workbook` | 自动导入 workbook，并把 sheet URL 写入发布摘要；是否回写配置由策略控制 |
| `--sheet-name` | `sheet_policy.sheet_name_template` | 可使用 `{sop_name}`、`{period}`、`{report_type}` 等变量 |
| `--identity` | `sender_identity` | `bot` 或 `user`，缺少 user 权限时允许按策略降级到 bot |
| `--top-n` | `render_options.top_n` | 卡片 TopN 行数，不改变完整明细 |
| `--level` | `level_selector` | 仅适用于等级明细类报告，等级来自当前 SOP 等级字典 |
| `--title` | `title_template` | 支持 SOP、周期、等级等变量 |
| `--dry-run` | `run_mode` | 由编排运行模式控制，不作为运营绕过校验的开关 |

推荐配置字段：

| 字段 | 必填 | 说明 |
|---|---|---|
| `sop_id` | 是 | 所属 SOP |
| `report_policy_id` | 是 | 发布策略唯一标识 |
| `report_type` | 是 | 已注册报告类型 |
| `template_name` | 是 | 模板注册表中的名称 |
| `required_artifacts` | 是 | 依赖的 `summary.json`、CSV、xlsx 等产物 |
| `sheet_policy.strategy` | 是 | `reuse_existing`、`import_workbook`、`reuse_or_import`、`none` |
| `sheet_policy.writeback_target` | 否 | 仅允许写运行实例或报告发布日志，不直接覆盖人工配置 |
| `report_target_policy.target_type` | 是 | `fixed_user`、`fixed_chat`、`sop_role`、`runtime_override` |
| `report_target_policy.target_ref` | 条件必填 | 用户 open_id、chat_id 或角色别名 |
| `sender_identity` | 是 | `bot` 或 `user` |
| `render_options` | 否 | `top_n`、标题模板、颜色策略、是否展示口径折叠面板 |
| `idempotency_policy` | 是 | 幂等 key 组成字段，必须安全化且长度受控 |
| `enabled` | 是 | 策略启停 |

发布结果标准输出应至少包含：

| 字段 | 说明 |
|---|---|
| `report_type` | 实际发布的报告类型 |
| `run_dir` | 输入分析目录 |
| `sheet_url` | 导入或复用的电子表格 URL |
| `card_json` | 发送版卡片路径，已剥离内部 `_` 字段 |
| `card_json_with_meta` | 审计版卡片路径，保留 `_meta._data_hash` |
| `sent` | 是否已发送 |
| `message_id` | 飞书消息 ID，未发送则为空 |
| `chat_id` | 实际发送群或私聊会话 |
| `identity` | 实际发送身份 |

## 3. Report Publishing 与正式 Anomaly Touch 的边界

| 能力点 | Report Publishing | 正式 Anomaly Touch |
|---|---|---|
| 输入 | process skill 标准结果目录 | 事件或命中行 + `route_result` + 触达模板 |
| 目标对象 | 报告订阅人、SOP owner、运营复盘群 | 业务对象 owner、协作方、升级人、确认人 |
| 是否按行路由 | 否，除非配置为 POC 分包报告 | 是，每条命中行都必须有 `route_result` |
| 人工确认 | 默认不走正式触达确认门禁，可配置报告发布审批但不推进事件 | 按 SOP 等级字典 `requires_human_confirm` 强制执行 |
| 群聊管理 | 只向配置目标发送，不自动建事件群 | 可按 `chat_strategy` 复用群、私聊或建临时群 |
| 发送前校验 | 卡片结构、内部字段剥离、幂等 key | 卡片哈希、等级匹配、chat_id 匹配、内部字段剥离 |
| 写入 | 发布摘要或运行实例日志 | 触达记录表、确认审计字段、message_id；事件状态由 orchestrator 推进 |
| 禁止事项 | 不创建异常事件，不写触达记录，不替代 owner-routing | 不取数、不判断异常、不生成全局报告、不猜 owner/chat_id |

因此，一个 SOP 可出现三种运行模式：

- `report_only`：只发布报告，不调用 owner-routing，不写触达记录。
- `report_then_touch`：先发布全局报告，再对命中行逐条路由并正式触达。
- `touch_only`：上游已经有事件和明细，只执行 owner-routing 与 anomaly touch。

## 4. 模板注册与 CardKit 变量契约

模板注册表用于约束“什么 report type 或 touch scene 可以用什么模板”，避免运行时临时拼卡片。

| 字段 | 说明 |
|---|---|
| `template_id` | 模板唯一标识 |
| `template_name` | 业务可读名称，例如 `low_efficiency_grading_report` |
| `scene` | `report_card`、`event_touch_card`、`preview_card`、`escalation_card` |
| `sop_id` | 可为空，表示跨 SOP 通用模板 |
| `report_type` | 报告卡片必填 |
| `template_engine` | `card2_json` 或 `cardkit` |
| `local_template_name` | 本地模板文件名或渲染器名称 |
| `cardkit_template_id` | CardKit 模板 ID，使用 CardKit 发布版本时必填 |
| `schema_version` | 模板变量契约版本 |
| `required_variables` | 必填变量清单 |
| `optional_variables` | 可选变量清单 |
| `allowed_channels` | `group`、`dm`、`preview_dm` 等 |
| `validation_policy` | 表格列宽、`_meta` 剥离、哈希校验、变量缺失处理 |
| `enabled` | 是否启用 |

报告卡片的通用变量：

| 变量 | 说明 |
|---|---|
| `sop_name`、`sop_id` | SOP 信息 |
| `run_id`、`period` | 运行批次和周期 |
| `report_type`、`report_title` | 报告类型和标题 |
| `summary_metrics` | 核心指标卡数据 |
| `top_items` | 卡片展示 TopN 明细 |
| `sheet_url` | 完整电子表格或授权视图 |
| `methodology` | 口径、数据源、fallback reason |
| `provenance` | 数据集、分区、取数窗口、产物路径 |

正式事件触达卡片的通用变量：

| 变量 | 说明 |
|---|---|
| `event_id`、`hit_id` | 事件和命中行标识 |
| `business_object` | 触发异常的业务对象展示名 |
| `level_label`、`sop_level_id`、`sla_text` | 当前 SOP 自己的等级与 SLA |
| `route_grain`、`route_key` | 路由粒度和业务对象 key |
| `owners`、`collaborators`、`escalation` | owner-routing 解析出的人员 |
| `mention_targets` | 需要在群内 @ 的对象 |
| `action_required` | 需要责任人执行的动作 |
| `confirm_hint` | 人工确认 preview 的提示 |
| `sheet_url` | 仅允许放 POC 可见的过滤视图或对象级明细 |

模板规则：

- CardKit 模板变量名必须稳定，新增变量需升级 `schema_version`。
- 业务变量不得使用 `_` 前缀；`_meta` 只允许作为发送前校验的内部审计字段。
- 发送版卡片必须剥离所有 `_` 前缀字段。
- Card 2.0 表格列宽不得小于 `80px`。
- 报告卡片默认使用蓝色主色；正式告警升级卡片可按 `normalized_severity` 使用更强提示色。
- 卡片只展示 TopN 或对象级必要明细，全量数据进入电子表格或授权视图。

## 5. SOP 角色目录与等级受众策略

SOP 角色目录用于维护“某类角色是谁”，等级受众策略用于维护“某个等级需要通知哪些角色”。二者与对象 owner 是不同概念：对象 owner 来自业务对象映射，角色目录负责补齐治理、运营、VOC、CQC 等横向角色。

### 5.1 SOP 角色目录

| 字段 | 说明 |
|---|---|
| `sop_id` | 所属 SOP |
| `role_alias` | 角色别名，例如 `governance_bp`、`voc_poc`、`review_ops`、`cqc_owner` |
| `role_display_name` | 中文展示名，例如治理 BP、VOC POC、人审运营、CQC 负责人 |
| `role_category` | `business_owner`、`operations`、`governance`、`escalation`、`confirmation` |
| `users` | 默认人员，存可解析的用户引用，不直接写不可校验文本 |
| `default_chat_id` | 角色默认群，可为空 |
| `priority_order` | 同类角色排序 |
| `effective_start`、`effective_end` | 生效时间 |
| `enabled` | 是否启用 |

### 5.2 等级受众策略

| 字段 | 说明 |
|---|---|
| `sop_id` | 所属 SOP |
| `sop_level_id` | SOP 等级字典中的等级 |
| `audience_roles` | 应知角色 |
| `action_roles` | 需要行动或被 @ 的角色 |
| `confirmation_roles` | 需要人工确认时的确认人 |
| `escalation_roles` | 升级角色 |
| `channel_preference` | 群聊、私聊、临时群优先级 |
| `requires_human_confirm` | 来自等级字典，策略表只能引用，不另行定义 |

审核延时 SOP 的示例：

| 等级 | 触达对象 |
|---|---|
| P2 | 治理 BP、审核 VOC POC、人审运营、交付调度负责人 |
| P1 | 治理 BP+1、VOC 负责人、人审运营负责人、群组负责人 |
| P0 | 治理负责人、CQC 负责人，并可加入对象 owner 和必要运营角色 |

## 6. 对象级责任路由

`owner-routing` 的目标模型应从“指标 + 等级 + 适用范围”升级为“每条命中结果按业务对象解析 owner，再按等级扩展受众”。

对象级路由分三步：

1. 结果归属解析：从命中行读取业务对象 key，解析业务 POC、owner、负责团队。
2. 触达受众扩展：根据 SOP 等级策略补齐治理 BP、VOC POC、人审运营、CQC 负责人等角色。
3. 触达通道决策：决定发已有对象群、SOP 通用群、私聊，还是临时专项群。

路由策略配置：

| 字段 | 说明 |
|---|---|
| `route_policy_id` | 路由策略唯一标识 |
| `sop_id` | 所属 SOP |
| `route_grain` | `reason`、`strategy`、`queue`、`group`、`scene`、`project` 等 |
| `route_key_fields` | process skill 输出中的字段名，例如 `reason`、`queue_id`、`scene` |
| `owner_source_id` | 绑定的 Owner Source |
| `level_scope` | 适用等级，空表示全部 |
| `match_priority` | 多个 grain 可用时的优先级 |
| `fallback_policy` | 未命中 owner 时是否转人工、是否使用 SOP 默认 owner |
| `audience_policy_id` | 等级受众策略 |
| `chat_policy_id` | 通道策略 |
| `enabled` | 是否启用 |

典型映射：

| SOP | 推荐 route_grain | 业务对象 key | owner 解析 |
|---|---|---|---|
| 低效打标 | `reason`、`strategy` | `reason`、`strategy_id` | `reason/策略 -> owner` |
| 审核延时 | `queue`、`group`、`scene` | `queue_id`、`group_id`、`scene` | `queue/group/scene -> owner` |
| 自动处置准确率 | `model`、`policy`、`scene` | `model_id`、`policy_id`、`scene` | `模型/策略/场景 -> owner` |

约束：

- process skill 输出必须包含当前 `route_grain` 所需字段，否则配置 lint 失败。
- 同一个 metric、同一个 level 下，不同 reason、queue 或 scene 可以路由到不同 owner。
- 未命中对象 owner 时，返回 `missing_object_owner=true`，不得臆造责任人。
- “指标 + 等级 + 适用范围”只能作为显式 fallback，不再作为唯一责任模型。

## 7. Owner Source 注册机制

所有 owner 来源必须先注册，配置只能引用已注册来源。运营不得直接写临时 SQL 或未校验查询逻辑。

### 7.1 Owner Source Registry

| 字段 | 说明 |
|---|---|
| `owner_source_id` | 来源唯一标识 |
| `sop_id` | 所属 SOP，可为空表示跨 SOP 通用 |
| `route_grain` | 支持的路由粒度 |
| `source_type` | `lark_base_table`、`query_template`、`process_output`、`manual_fallback` |
| `source_ref` | base table token、query key、输出字段路径或人工兜底策略 ID |
| `key_field` | 用于匹配 route key 的字段 |
| `owner_fields` | owner、协作方、升级人字段映射 |
| `chat_fields` | 默认群聊 ID、群聊名称字段映射 |
| `fallback_policy` | 未命中、重复命中、过期时的处理 |
| `freshness_policy` | 映射表或查询结果有效期 |
| `match_rules` | 精确匹配、别名匹配、优先级、启停过滤 |
| `enabled` | 是否启用 |

### 7.2 多维表格映射字段

| 字段 | 说明 |
|---|---|
| `sop_id` | 所属 SOP |
| `route_grain` | 路由粒度 |
| `route_key` | 标准 key |
| `route_key_alias` | 别名，可多值 |
| `owner_role` | owner 角色名，通常为业务 POC |
| `owner_user` | 主负责人 |
| `collaborators` | 协作方 |
| `escalation_users` | 升级人 |
| `default_chat_id` | 对象默认群 |
| `default_chat_name` | 对象默认群名 |
| `effective_start`、`effective_end` | 生效时间 |
| `enabled` | 是否启用 |
| `priority` | 多条匹配时的优先级 |
| `notes` | 说明 |

### 7.3 来源类型规则

| source_type | 使用方式 | 限制 |
|---|---|---|
| `lark_base_table` | 按 `route_key` 查映射表，返回 owner、协作方、升级人、chat_id | 必须启用、未过期；重复命中按 priority 处理 |
| `query_template` | 调用已注册 query key，按结构化参数查询 owner | 禁止执行运营临时填写的任意 SQL |
| `process_output` | 直接消费 process skill 输出中的 owner 字段 | process skill registry 必须声明字段含义和可信度 |
| `manual_fallback` | 转人工确认或固定兜底角色 | 只能用于缺 owner 或低置信度场景，必须在 `route_result` 中标记 |

推荐优先级：对象映射表优先，其次注册查询逻辑，再其次 process skill 明确输出，最后人工兜底。实际优先级由 `match_priority` 配置决定。

## 8. `route_result` 标准输出 schema

`owner-routing` 必须为每条命中行生成一个可审计的 `route_result`。该结构随命中行进入正式触达，必要时也写入事件表或结果明细。

```json
{
  "schema_version": "1.0",
  "sop_id": "review_latency",
  "run_id": "RUN-20260706-001",
  "event_id": "EVT-20260706-0001",
  "hit_id": "HIT-0001",
  "metric_id": "metric_realtime_latency",
  "level": {
    "sop_level_id": "review_latency_p1",
    "level_label": "P1",
    "normalized_severity": "high",
    "sla_minutes": 120
  },
  "business_object": {
    "route_grain": "queue",
    "route_key": "queue_123",
    "display_name": "南区审核队列",
    "source_fields": {
      "queue_id": "queue_123",
      "queue_name": "南区审核队列",
      "scene": "电商"
    }
  },
  "owner_source": {
    "owner_source_id": "review_latency_queue_owner",
    "source_type": "lark_base_table",
    "source_ref": "registered_base_table",
    "match_type": "exact",
    "matched_record_id": "rec_xxx",
    "freshness_at": "2026-07-06 10:00:00"
  },
  "owners": [
    {
      "role": "业务POC",
      "id": "ou_xxx",
      "name": "负责人",
      "source": "review_latency_queue_owner"
    }
  ],
  "collaborators": [
    {
      "role": "人审运营",
      "id": "ou_yyy",
      "name": "协作人",
      "source": "sop_role_directory"
    }
  ],
  "escalation": [
    {
      "role": "治理负责人",
      "id": "ou_zzz",
      "name": "升级人",
      "source": "level_audience_policy"
    }
  ],
  "delivery_policy": {
    "primary_channel": "group",
    "chat_strategy": "reuse_object_group",
    "chat_id": "oc_xxx",
    "chat_name": "审核延时-南区审核队列",
    "mention_targets": ["ou_xxx", "ou_yyy"],
    "fallback_channel": "dm",
    "chat_id_writeback": false
  },
  "sla": {
    "sla_text": "2小时内响应",
    "sla_deadline": "2026-07-06 12:00:00"
  },
  "route_confidence": "high",
  "missing_object_owner": false,
  "missing_roles": [],
  "fallback_reason": null,
  "audit": {
    "config_version": "cfg_20260706",
    "resolved_at": "2026-07-06 10:03:00",
    "resolver": "owner-routing"
  }
}
```

字段要求：

- `business_object.route_grain`、`owner_source.owner_source_id`、`delivery_policy.chat_strategy` 必须存在，保证每条结果可追溯。
- `owners` 必须至少包含业务 POC；若缺失，必须标记 `missing_object_owner=true` 并走 fallback。
- `delivery_policy.chat_id` 为空时，必须明确是否允许建群、是否允许回写。
- `route_confidence` 建议取 `high`、`medium`、`low`、`missing`。
- 所有人员 ID 和 chat_id 必须来自可解析来源，不允许手工猜测。

## 9. 触达通道策略

触达通道由 `delivery_policy` 决定，默认优先群聊，必要时私聊或临时建群。

| chat_strategy | 适用场景 | 行为 | 是否回写 chat_id |
|---|---|---|---|
| `reuse_object_group` | 对象已有专属群，例如 queue 或 reason 治理群 | 发送到对象群并 @ owner/协作方 | 否，除非本策略允许首次建群后作为对象群复用 |
| `reuse_sop_group` | SOP 通用通知群 | 发送到 SOP 群，按对象分组展示 | 否 |
| `dm_owner` | 低影响、隐私、缺群但不适合建群 | 私聊 owner，必要时抄送确认人 | 不适用 |
| `preview_dm` | 需人工确认的 preview | 私聊确认人，等待“确认发送” | 不适用 |
| `create_incident_group` | 高等级、持续未处理、跨角色协同 | 创建临时专项群，拉 owner、协作方、升级人、运营角色 | 仅当 `writeback_policy=reuse_future` 时回写；默认只写触达记录 |
| `manual_fallback_queue` | 缺 owner、缺 chat_id、校验失败 | 发到人工兜底队列或停止触达 | 不回写 |
| `report_only_fixed_target` | 报告发布 | 发给报告配置目标 | 不回写责任路由 |

通道约束：

- 默认群聊通知优先使用 `route_result.delivery_policy.chat_id`，不得按群名模糊搜索历史群。
- `chat_id` 非空且以 `oc_` 开头时可复用；为空且策略允许时才建群。
- dry-run 下不建群、不回写、不正式发送。
- 临时建群必须包含对象 owner、等级升级角色和必要运营角色。
- 是否回写 `chat_id` 由 `writeback_policy` 决定：
  - `never`：仅本次使用；
  - `reuse_future`：作为对象群或 SOP 群长期复用；
  - `runtime_only`：只写触达记录，不写配置；
  - `manual_approval_required`：待人工确认后再回写。
- 正式发群前必须校验实际目标 `chat_id` 与 `route_result` 或已回写配置一致。

## 10. 多 POC 结果的拆分与合并规则

报告发布可以展示全量结果，但正式触达必须避免把结果发给无关 POC。

### 10.1 标准处理顺序

1. process skill 输出命中行。
2. owner-routing 为每条命中行生成 `route_result`。
3. 根据 `delivery_policy` 计算触达分组 key。
4. 每个触达分组只包含该组 owner 需要处理或有权限查看的行。
5. anomaly-touch 为每个分组渲染独立卡片、执行确认和发送。

推荐触达分组 key：

```text
sop_id + sop_level_id + chat_strategy + target_chat_id/target_user_id + owner_set + route_grain
```

### 10.2 拆分规则

- 不同 `target_chat_id` 或不同 `target_user_id` 必须拆分。
- 私聊 owner 时，不同 owner 必须拆分。
- 对象群不同时必须拆分。
- `missing_object_owner=true` 的行必须拆到人工兜底分组，不得混入任意 POC 分组。
- 如果完整 sheet 包含多个 POC 的明细，POC 触达卡片只能链接对象级过滤视图、对象级 sheet 或权限受控产物；不得把全量 sheet 作为行动入口发给无关 POC。

### 10.3 合并规则

- 同一对象群、同一等级、同一 owner 集合的多条命中可合并为一张表格卡片。
- SOP 通用群可合并多 POC 行，但卡片必须按 `business_object` 或 owner 分组展示，并明确每行责任人；这种合并只适用于群成员本身具备全局可见权限的运营/治理群。
- 全局报告可以合并全量结果，但它属于 Report Publishing，不自动触发正式触达记录。

## 11. 端到端契约

一轮 `report_then_touch` 的推荐契约：

| 步骤 | 输入 | 输出 | 失败处理 |
|---|---|---|---|
| Process Skill | SOP 配置、数据源、规则组 | `summary.json`、CSV、xlsx、命中行 | 无标准产物则停止 |
| Report Publishing | run_dir、report policy、template registry | sheet URL、报告卡片、publish summary | 只影响报告节点，不得写触达记录 |
| Owner Routing | 命中行、route policy、owner source、角色目录、等级字典 | 每条命中行的 `route_result` | 缺 owner 或配置非法则转人工 |
| Anomaly Touch Preview | 需确认的触达分组 | preview 私聊、确认审计 | 未确认不正式发群 |
| Anomaly Touch Send | 触达分组、卡片、`route_result` | message_id、touch_record | 校验失败则 blocked，不推进事件 |
| Orchestrator State | 各节点结果 | 事件状态和运行实例审计 | 任一关键节点失败按状态机停止或降级 |

最低验证要求：

- `report_type`、`template_name`、`route_grain`、`owner_source_id`、`role_alias`、`chat_strategy` 都必须已注册。
- `route_grain` 必须能在 process skill 输出字段中找到。
- 等级必须来自当前 SOP 等级字典，而不是全局 P0/P1/P2 枚举。
- 需人工确认的等级必须能解析确认人。
- 正式触达必须有对象级 `route_result`；没有 `route_result` 时只能发布报告或转人工。

## 12. 对现有能力的兼容路径

低效打标已跑通的三个报告类型先作为首批注册项：

| report_type | 模板 | 路由建议 |
|---|---|---|
| `low_efficiency_dimension_breakdown` | `low_efficiency_dimension_report` | 报告发布为主；若正式触达，按 `reason` 或 `机审一级标签 + reason` 分包 |
| `low_efficiency_grading` | `low_efficiency_grading_report` | 全局报告发运营或治理群；正式触达按 `reason -> owner` |
| `low_efficiency_level_detail` | `low_efficiency_level_detail` | 等级专项报告可发等级治理群；正式触达仍按 `reason/strategy -> owner` |

审核延时作为新增 SOP 时，不复用低效打标的 `reason` owner 逻辑，而注册自己的 `queue/group/scene` Owner Source，并由等级受众策略补齐治理 BP、VOC POC、人审运营、CQC 负责人等角色。
