---
name: owner-routing
description: 人审运营监控体系·责任路由与 SLA 计算。Invoke when anomaly/event results need owners, collaborators, escalation targets, channels, chat_id, or SLA.
metadata:
  version: "0.1.3"
  author: 李中涛
  status: draft
  tags: [人审运营, 横向能力, 责任路由, SLA, sop_config, 可选Base控制面]
  requires:
    bins: ["lark-cli"]
    siblings: ["review-monitoring-shared"]
  requires_optional:
    - "lark-base：平台内置多维表格能力，仅在需要读取/维护 Base 配置或执行授权写回时使用；当前 route_owner.py 不直接读取旧责任路由表或旧等级字典表"
    - "lark-contact：平台内置通讯录能力，用于解析 owner/collaborator/escalation 的 open_id"
    - "lark-im：平台内置 IM 能力，用于解析或校验群聊 chat_id"
  requires_note: "本 skill 是横向能力层，只做责任路由和 SLA 计算；默认读取本地 sop_config.v1，Base 仅作为可选控制面导出来源，飞书人员/群解析能力由平台内置 lark-* skill 提供。"
---

# owner-routing — 责任路由

## 定位

判断一个已产生的异常事件「该找谁」：匹配主负责人、协作方、升级人、触达渠道、群聊信息，并计算 SLA 截止时间。

本 skill 是**横向能力层**，可被任意纵向业务分析 skill 或 `monitoring-orchestrator` 调用。它不关心异常是怎么判断出来的，只接收结构化事件/命中结果与等级信息。

## 触发场景

当上游已经产出异常事件或命中清单，并需要：

- 根据「指标 + 等级 + 适用范围」找负责人/协作方/升级人；
- 根据命中行中的业务对象解析负责人，例如 `reason/strategy -> owner`；
- 获取触达渠道、群聊名、群聊 ID；
- 计算 SLA 截止时间；
- 识别 `missing_route` 并转人工；

使用本 skill。

## 输入（标准形态）

```json
{
  "metric_id": "metric_low_label_rate_strategy",
  "level": "P1",
  "scope": "抖音安全审核",
  "event_created_at": "2026-07-04 19:00:00"
}
```

## 输出（标准形态）

```json
{
  "missing_route": false,
  "route_id": "route_low_label_p1",
  "owner": [{"id": "ou_xxx", "name": "负责人"}],
  "collaborators": [{"id": "ou_xxx", "name": "协作方"}],
  "escalation": [{"id": "ou_xxx", "name": "升级人"}],
  "channel": ["飞书群"],
  "chat_name": "人审监控-P1-高完审低打标策略",
  "chat_id": "oc_xxx",
  "sla": "2小时内响应",
  "sla_minutes": 120,
  "sla_deadline": "2026-07-04 21:00:00"
}
```

## 读取与写入

运行配置优先读取本地 `sop_config.v1`；可选 Base 字段结构统一引用 [review-monitoring-shared/references/base_schema.md](../review-monitoring-shared/references/base_schema.md)。

| 类型 | 表 | 用途 |
|---|---|---|
| 读 | `sop_config.v1` 中的 `route_policies` | 确定路由粒度、路由键字段和 owner source 引用 |
| 读 | `sop_config.v1` 中的 `owner_source_registry` | 解析 owner、协作方、升级人、默认群 ID 和兜底策略 |
| 读 | `sop_config.v1` 中的 SOP 等级配置 | 输出等级标签、标准严重度和 SLA 分钟 |
| 写 | 本地 `route_results.json` | 输出每条命中的责任路由结果，供报告、触达和写回节点消费 |

> 当前 SOP-first 路由脚本不直接读取旧 `责任路由表 tblvFGVbTBQ3Vfws` 或旧 `等级字典表 tblgcg6zvhaY3Qrw`。旧表仅作为 legacy/兼容资产保留。

## 路由匹配规则

MVP 新入口优先使用对象级路由：

```bash
python3 scripts/route_owner.py \
  --config ../review-monitoring-shared/examples/low_efficiency_sop_config.sample.json \
  --sop-id low_efficiency_labeling \
  --hits <hits.csv> \
  --run-id <run_id>
```

对象级规则：

1. 根据 SOP 的 `route_policies[].route_key_fields` 从命中行读取业务对象 key，例如 `reason`。
2. 根据 `owner_source_id` 查 Owner Source Registry。
3. 命中映射时输出标准 `route_result`，包含 owner、协作方、升级人、chat_strategy、chat_id 和 `route_confidence`。
4. 未命中映射时返回 `missing_object_owner=true`，不回退到任意指标负责人。
5. 旧的「指标 + 等级 + 适用范围」只能作为显式 fallback policy，不能作为唯一责任模型。
6. P0 必须带升级对象；缺失则返回 `missing_route=true` 或 `missing_escalation=true`，由编排层停止触达或转人工。

## SLA 口径

SOP-first 链路中，SLA 来自 SOP 等级字典配置。旧全局等级字典表只作为兼容资产，不作为当前路由脚本的读取入口。

## 边界

- 不做异常判断、不做取数、不做分级。
- 不生成触达内容、不发送消息、不建群。
- 不推进事件「当前状态」；状态推进由 `monitoring-orchestrator` 负责。
- 不猜 open_id / chat_id；人员与群 ID 必须来自 Owner Source、固定群配置或经 `lark-contact` / `lark-im` 显式解析得到。

## 详细逻辑

完整逻辑见 [references/owner_routing.md](references/owner_routing.md)。
