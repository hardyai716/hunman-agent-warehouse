---
name: anomaly-touch
description: 人审运营监控体系·异常触达横向能力。Invoke when anomaly events or hit lists need card rendering, preview, confirmation, group creation, send, or touch records.
metadata:
  version: "0.3.0"
  author: 李中涛
  status: beta
  tags: [人审运营, 横向能力, 异常触达, 飞书群, 人工确认, 三重校验]
  requires:
    bins: ["lark-cli", "python3"]
    siblings: ["review-monitoring-shared"]
  requires_optional:
    - "lark-base：平台内置多维表格能力，用于读取触达模板/路由配置并写入触达记录"
    - "lark-im：平台内置 IM 能力，用于建群、查群、发卡片和发送确认消息"
    - "lark-contact：平台内置通讯录能力，用于解析责任人与人工确认对象"
  requires_note: "本 skill 是横向触达能力；卡片一致性校验脚本来自随包上传的 review-monitoring-shared/scripts/card_validator.py，飞书读写与消息能力由平台内置 lark-* skill 提供。"
---

# anomaly-touch — 异常触达

## 定位

把上游已经确认的异常事件或命中清单，转成「可理解、可追踪、可审计」的飞书触达：

1. 生成触达内容与卡片；
2. 计算并嵌入 `card_hash`；
3. 群聊自主管理（有则复用、无则建群并回填）；
4. 人工确认门禁；
5. 发送前三重硬校验；
6. 发群/私聊并写触达记录。

本 skill 是**横向能力层**，不关心异常来自哪个业务模块。它可被 `monitoring-orchestrator` 或任意纵向分析 skill 调用。

## 触发场景

当上游已经产出事件、命中清单和路由结果，并需要：

- 把事件渲染为飞书卡片；
- 同等级多条命中汇总为一条表格卡片；
- 先私聊 preview，等待人工回复「确认发送」；
- 按责任路由表自动建群/复用群，并回填 chat_id；
- 通过哈希/等级/chat_id 三重校验后正式发送；
- 写入触达记录表；

使用本 skill。

## 输入（标准形态）

```json
{
  "level": "P1",
  "metric": "近7天高完审低打标策略",
  "period": "2026-06-27~2026-07-03",
  "hits": [
    {
      "event_id": "EVT-20260704-0001",
      "business_object": "N1_chuxing_model_llm_pe_review",
      "review_cnt": 7646,
      "label_cnt": 116,
      "label_rate": "1.51%",
      "rule": "双周高量低效"
    }
  ],
  "route": {
    "route_id": "route_low_label_p1",
    "owner": [{"id": "ou_xxx", "name": "负责人"}],
    "collaborators": [],
    "escalation": [],
    "channel": ["飞书群"],
    "chat_name": "人审监控-P1-高完审低打标策略",
    "chat_id": "oc_xxx"
  }
}
```

## 输出（标准形态）

```json
{
  "send_status": "sent",
  "message_id": "om_xxx",
  "touch_record_ids": ["recxxx"],
  "need_human_confirm": true,
  "card_hash": "sha256..."
}
```

若被门禁拦截或校验失败：

```json
{
  "send_status": "blocked",
  "blocked_reason": "route chat_id mismatch",
  "need_human_confirm": true
}
```

## 读取与写入

配置中心与字段结构统一引用 [review-monitoring-shared/references/base_schema.md](../review-monitoring-shared/references/base_schema.md)。

| 类型 | 表 | 用途 |
|---|---|---|
| 读 | 触达模板表 `tblDLzboh47WqJla` | 按「模板场景 + 适用等级 + 接收对象」选模板 |
| 读 | 责任路由表 `tblvFGVbTBQ3Vfws` | 取群聊名、群聊ID、负责人、协作方、升级人 |
| 读 | 等级字典表 `tblgcg6zvhaY3Qrw` | 取「是否需要人工确认」和 `{sla}` 文案 |
| 读/写 | 触达记录表 `tbl39ZotgZJ8Q8aL` | 幂等查重；发送后新增触达记录与审计字段 |
| 写 | 责任路由表 `tblvFGVbTBQ3Vfws` | 首次自动建群后回填「群聊ID」和「群聊/接收方」 |
| 写 | 事件表 `tblHOC5Y8j58xDYQ` | 可回写「最近触达时间」「路由触达摘要」「触达记录」；状态推进不在本 skill 内做 |

## 关键流程

### 0. 报告发布统一入口

当上游已经产出标准分析结果目录（`summary.json`、CSV、xlsx）并需要推送到飞书时，优先调用统一发布入口，不要临时手写发送脚本：

```bash
python3 scripts/publish_lark_report.py \
  --run-dir <analysis_result_dir> \
  --report-type <low_efficiency_dimension_breakdown|low_efficiency_grading|low_efficiency_level_detail> \
  --target-user <ou_xxx> \
  --identity bot
```

SOP-first 新链路应优先使用 report policy，而不是在 orchestrator 中硬编码发布参数：

```bash
python3 scripts/publish_lark_report.py \
  --policy-file ../review-monitoring-shared/examples/low_efficiency_sop_config.sample.json \
  --sop-id low_efficiency_labeling \
  --report-type low_efficiency_grading \
  --run-dir <analysis_result_dir> \
  --dry-run
```

该入口负责：

1. 读取标准结果目录；
2. 导入或复用飞书电子表格；
3. 按 `report_type` 选择报告卡片模板；
4. 渲染发送版卡片与审计版卡片；
5. 调用 `lark-im` 发送并记录 message id。

### 0.1 正式事件触达入口

当上游已经产出命中明细和 `owner-routing` 的 `route_results.json`，并且目标 owner / 角色目录 / allowlist 已审批后，使用正式事件触达入口：

```bash
python3 scripts/event_touch_sender.py \
  --hits <level_hits.csv> \
  --route-results <route_results.json> \
  --level P2 \
  --period 2026-06-29~2026-07-05 \
  --output-dir <touch_output_dir> \
  --target-allowlist <approved_target_id> \
  --identity bot
```

该入口负责：

1. 校验所有命中行都有 `route_result`；
2. 按 owner / chat 目标分组；
3. 渲染正式事件触达卡片；
4. 校验卡片 hash、等级和目标；
5. 剥离 `_meta` 后发送；
6. 写入本地 `touch_records.jsonl` 和 `touch_summary.json`。

当前脚本不直接写生产事件表或触达记录表；生产写回必须在写回目标和幂等策略配置完成后单独开启。

### 0.2 Base 写回与幂等日志

生产写回由 `scripts/base_writeback.py` 提供底层能力：

- `upsert_event`：按 `sop_id + run_id + 业务对象 + rule_group_id` 查询事件，命中则更新，未命中则创建；
- `upsert_touch_record`：按 `idempotency_key` 查询触达记录，命中则更新，未命中则创建；
- 每次查询、创建、更新都会写入 JSONL 日志，字段包括 `idempotency_key`、查询条件、命中记录 ID 和执行分支。

端到端集成测试脚本位于仓库根目录：

```bash
export HUMAN_REVIEW_BASE_TOKEN=<runtime_private_base_token>
python3 tools/run_low_efficiency_production_integration.py \
  --output-dir <integration_output_dir>
```

该脚本会读取低效策略分析结果、`route_results.json` 和正式触达记录，模拟生产后半段写回链路，并输出 `writeback_idempotency.log.jsonl` 便于排查幂等问题。

### 1. 内容生成

- 模板来自触达模板表。
- `是否需要人工确认` 只看等级字典表 `fldFzR90Aa`，不看触达模板或等级名硬编码。
- 批量命中时渲染为一条表格汇总卡片，不拆多条发送。
- 生成卡片后，调用 [review-monitoring-shared/scripts/card_validator.py](../review-monitoring-shared/scripts/card_validator.py) 的 `compute_hits_hash` 和 `embed_hash_in_card`，把命中数据哈希写入 `_meta._data_hash`。

### 2. 群聊自主管理

判定唯一依据 = 责任路由表「群聊ID」字段（字段ID：`fldzVXrZB8`）。

- 非空且 `oc_` 开头：复用该群，不新建。
- 为空：自动建群，邀请主负责人 + 协作方 + 升级人；建群成功后回填：
  - 「群聊ID」`fldzVXrZB8` ← 新群 chat_id；
  - 「群聊/接收方」`fldJ4jDodR` ← 新群名。
- 禁止按群名搜索历史群兜底，避免重名/模糊命中错群。
- dry_run 下不真建群、不回写，只输出将执行的建群计划。

### 3. 人工确认门禁

- 需人工确认时：先发 preview 到确认人私聊，含「请回复确认发送」提示。
- 未收到明确「确认发送」前，不发群、不写已发送触达记录、不推进事件状态。
- 收到确认后，记录 `confirmed_by`、`confirmed_at`、`confirm_message_id`，再进入正式发送前校验。

### 4. 发送前三重硬校验

正式发送前必须依次通过：

1. `verify_card_hash`：卡片哈希与当前命中数据一致；
2. `verify_route_match`：卡片 `_meta.level` 与目标等级一致；
3. `verify_route_chat_id`：实际发送目标 chat_id 与责任路由表 chat_id 完全一致。

任一失败立即 `send_status=blocked`，停止发送。

### 5. 发送前剥离内部字段

三重硬校验依赖 `_meta`，所以顺序必须是：

```text
三重硬校验（读 _meta） → 全部通过 → 递归剥离所有 "_" 前缀键 → 调 lark-im 发送
```

禁止把含 `_meta`、`_render_note` 等内部字段的卡片直接发给飞书。

## 边界

- 不取数、不判断异常、不做业务分级。
- 不匹配责任人；路由匹配由 `owner-routing` 负责，本 skill 只消费 route 结果。
- 不推进事件「当前状态」；状态推进由 `monitoring-orchestrator` 负责。
- 不绕过人工确认门禁，不绕过三重硬校验。
- 不臆造 open_id/chat_id；跨应用 open_id 必须用发送应用视角解析。

## 详细逻辑

- 内容生成：[references/touch_message_writer.md](references/touch_message_writer.md)
- 发送执行：[references/touch_sender.md](references/touch_sender.md)
- 报告卡片模板：[references/lark_report_card_templates.md](references/lark_report_card_templates.md)
