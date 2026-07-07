# touch_sender — 触达发送

## 用途
把 [touch_message_writer.md](touch_message_writer.md) 生成的触达内容真正发出去：拉群 / 发群消息 / 发送给对应的人，并记录每次触达明细。是「触达」环节的执行端，与「内容生成」解耦——一个产文案，一个管发送。

## 当前实现状态

当前 `event_touch_sender.py` 不直接读取旧责任路由表、旧等级字典表或触达模板表。它读取的是上游已经生成的 `route_results.json`：

- `target_chat` 非空时按群目标发送；
- 否则使用 `target_user` 私聊发送；
- 目标必须通过 `--target-allowlist` 显式放行；
- 是否需要人工确认、SLA 和受众策略应由 SOP-first 配置在上游决定。

## 写入的多维表格
- 当前发送脚本只写本地 `touch_records.jsonl` 和 `touch_summary.json`。
- 事件表和触达记录表写回由显式生产写回入口完成。
- 当前实现不回写旧责任路由表，也不写「关联触达模板」。

## 输入
```json
{
  "event_id": "EVT-20260626-0001",
  "level": "P1",
  "touch_content": { "title": "...", "body": "...", "card_hash": "sha256:...", "preview_mode": true },
  "route": { "owner": "策略owner", "chat_id": "oc_xxx", "channel": ["飞书群"] }
}
```

## 发送前硬校验（不可跳过）
在调用 lark-im 发送前，必须通过以下硬校验：
1. `verify_card_hash`：校验 `touch_content.card_hash` 与当前命中数据一致，防止内容被篡改
2. `verify_route_match`：校验卡片等级（`_meta.level`）与目标路由等级一致，防止发错群/发错人
3. `verify_route_chat_id`：正式发群前校验卡片目标与上游 `route_results.json` 中的 `target_chat` 一致。当前实现不再查询旧责任路由表。

任一校验失败立即中止，不发送，标记 `send_status=blocked` 并上报原因。

详见 `references/touch_sender.md`（本文件）及 [../../review-monitoring-shared/scripts/card_validator.py](../../review-monitoring-shared/scripts/card_validator.py)。

> ⚠️ **发送前必须递归剔除所有 `_` 前缀键（App 层职责）**：校验流程会在卡片里注入内部哨兵字段（如 `_meta`，含 `_data_hash`、`level`；以及 P0 干运行实际踩坑的 `_render_note`），飞书一律不接受这类字段（会报 `unknown property: _meta` / `_render_note`）。这些字段仅供 `card_validator.py` 内部使用，**不是** CardKit 合法字段。
>
> **执行时机（顺序不可颠倒）**：三重硬校验依赖 `_meta._data_hash`、`_meta.level`，因此必须 **先完成三重硬校验（读 `_meta`）→ 全部通过 → 再剥离 → 最后调用 `lark-im` 发送**。校验在前、剥离在后。
>
> **剥离规则（伪代码）**：在卡片的**深拷贝副本**上，递归遍历所有 dict，凡是**键名**以 `_` 开头的一律删除（顶层与任意嵌套层级都要处理），list 元素逐个递归；**只删键，绝不改字符串值**（表格单元格等业务文本里出现的 "_meta" 之类值不受影响）。
>
> ```text
> def strip_internal_keys(node):
>     if isinstance(node, dict):
>         return {k: strip_internal_keys(v)
>                 for k, v in node.items()
>                 if not (isinstance(k, str) and k.startswith("_"))}
>     if isinstance(node, list):
>         return [strip_internal_keys(x) for x in node]
>     return node
>
> send_card = strip_internal_keys(deepcopy(card))   # 三重硬校验通过后再执行
> ```
>
> **约定**：`_` 前缀为内部哨兵专用，卡片构建方禁止用 `_` 前缀命名任何业务字段——CardKit 2.0 合法字段（`schema`/`header`/`body`/`elements`/`tag`/`text`/`content`/`template`/`behaviors`/`img_key` 等）均无 `_` 前缀，故递归剔除不会误删业务字段。**禁止把含任何 `_` 前缀键的卡片直接发送。**

## 幂等与查重
- 幂等口径：reason + scene + 告警等级 + 当日。同一幂等键已有「已发送」记录则跳过，不重复触达。
- 查重范围：触达记录表当日同事件同等级记录。

## 人工确认门禁（配置驱动）
- **是否需要人工确认，只看 SOP-first 配置不看等级名**：当前低效策略链路由 SOP 等级配置决定是否需要人工确认；旧等级字典表只作兼容资产。
- 需人工确认时：preview 卡片先发至人工确认人的私聊会话，含「请回复确认发送」提示。私聊目标不写死具体值，应由上游路由结果、触达配置或 allowlist 明确提供；取不到时转人工并停止发送。
- 收到回复「确认发送」后，回写 `confirmed_by`、`confirmed_at`、`confirm_message_id` 三字段，再发 final 版至目标群（final 发群前仍须通过 `verify_route_chat_id`）。

## 建群逻辑（当前不启用）
当前实现不自动建群。群级推送需要上游在 `route_results.json` 中提供明确 `target_chat`，并通过 allowlist 放行；没有明确群 ID 时停止发送或转人工。

## 输出（结构固定）
```json
{
  "send_status": "sent",
  "message_id": "om_xxx",
  "touch_record_id": "TR-20260626-0001",
  "need_human_confirm": true
}
```

## 与表的边界
接收方与群聊来自上游 `route_results.json`；触达记录由本地发送产物和显式 Base 写回入口记录；状态推进由编排层执行。旧责任路由表和旧等级字典表仅作 legacy 兼容，不作为当前 SOP-first 触达发送入口。
