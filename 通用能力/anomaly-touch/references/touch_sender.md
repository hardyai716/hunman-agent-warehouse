# touch_sender — 触达发送

## 用途
把 [touch_message_writer.md](touch_message_writer.md) 生成的触达内容真正发出去：拉群 / 发群消息 / 发送给对应的人，并记录每次触达明细。是「触达」环节的执行端，与「内容生成」解耦——一个产文案，一个管发送。

## 读取的多维表格
- 责任路由表 `tblvFGVbTBQ3Vfws`：取接收方（主负责人/协作方/升级人）、触达渠道、群聊名（「群聊/接收方」）、**「群聊ID」字段（字段ID：fldzVXrZB8，存飞书 chat_id）**
- 等级字典表 `tblgcg6zvhaY3Qrw`：取「是否需要人工确认」字段（字段ID：fldFzR90Aa，唯一权威来源）
- 触达记录表 `tbl39ZotgZJ8Q8aL`：发送前查重，避免对同一事件同一周期重复发送

> ⚠️ 不再从触达模板表读取「是否需要人工确认」，统一从等级字典表读取。

## 写入的多维表格
- 触达记录表 `tbl39ZotgZJ8Q8aL`：新增记录，写入「触达标题」「触达内容」「触达对象」「触达渠道」「群聊ID」「消息ID」「触达状态」「触达时间」「关联事件」「关联责任路由」「关联触达模板」「是否需要人工确认」（运行时快照）。需人工确认的等级（等级字典表「是否需要人工确认」字段（字段ID：fldFzR90Aa）值为 true）在确认后、正式发群前还必须回写审计字段：`confirmed_by`、`confirmed_at`、`confirm_message_id`。
- **责任路由表 `tblvFGVbTBQ3Vfws`：当该路由原本没有 chat_id、本次自动建群后，回写两个字段到该路由记录——「群聊ID」（字段ID：fldzVXrZB8）← 飞书返回的 chat_id；「群聊/接收方」（字段ID：fldJ4jDodR）← 新群名称（原为空时）。供下次直接复用，无需重复建群**
- 事件表 `tblHOC5Y8j58xDYQ`：回写「最近触达时间」「路由触达摘要」，并把「触达记录」link 到新建记录（「当前状态」由编排层推进，本 Skill 不自行改状态）

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
3. `verify_route_chat_id`：**正式发群前**校验实际发送目标 `chat_id` 与责任路由表「群聊ID」字段（字段ID：fldzVXrZB8）完全一致。
   - **时序（不可颠倒）**：路由表 chat_id 为空时，**先执行「建群逻辑」建群并把 chat_id 回写路由表，再跑本校验**——即校验发生在建群回写之后，此时路由表 chat_id 已非空。不是"发现空就 blocked"。
   - 建群回写后，若调用方传入的目标 `chat_id` 与路由表（刷新后）不一致，才停止发送（该函数内部先复用 `verify_route_match` 校验等级，再比对 chat_id）。
   - dry_run 下不真建群：chat_id 仍为空时按预期标 `missing_route`/`blocked` 转人工，不实发（干运行不建群是红线）。

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
- **是否需要人工确认，只看配置不看等级名**：读等级字典表 `tblgcg6zvhaY3Qrw` 的「是否需要人工确认」字段（字段ID：fldFzR90Aa）；该事件等级对应值为 `true` 时必须走人工确认，`false` 时可直接发送。不再在文档里枚举「P0/P1」等具体等级名（当前 P0/P1/notice=true、P2=false，均以等级字典表实际配置为准）。
- 需人工确认时：preview 卡片先发至人工确认人的私聊会话，含「请回复确认发送」提示。私聊目标 `chat_id` 不写死具体值——通过 `lark-im` 用责任路由表主负责人/升级人的 open_id 解析对应私聊会话，或从触达配置读取，取不到时转人工并停止发送。
- 收到回复「确认发送」后，回写 `confirmed_by`、`confirmed_at`、`confirm_message_id` 三字段，再发 final 版至目标群（final 发群前仍须通过 `verify_route_chat_id`）。

## 建群逻辑（群聊自主管理）
- **判定唯一依据 = 责任路由表「群聊ID」字段（字段ID：fldzVXrZB8）**。不搜群、不靠群名匹配历史群：
  - **非空且 `oc_` 开头** → 直接复用该群，不新建。
  - **为空** → agent 自动建新群：
    - 群名取责任路由表「群聊/接收方」字段（字段ID：fldJ4jDodR）；该字段也为空时按等级生成规范群名（如「人审监控-<等级>-<指标名>」）。
    - 邀请主负责人 + 协作方 + 升级人（用 `lark-im`/通讯录按 open_id 拉群，解析不到转人工）。
    - 建群成功后**回写两个字段到该路由记录**：「群聊ID」（fldzVXrZB8）← 新群 chat_id；「群聊/接收方」（fldJ4jDodR）← 新群名称（若原为空）。回写后同步刷新本轮缓存，后续步骤复用。
- 🔴 **禁止用 `im +chat-search` 等按群名搜索历史群来兜底**：群名可能重名/模糊命中错群，一律以路由表 chat_id 字段为准；查不到就建新群，不猜群。
- **dry_run 下不真建群、不回写**：只打印预览「将建群 <群名>、拉 <主负责人/协作方/升级人>、回填 chat_id + 群名到路由表」，不调用 `lark-im` 建群接口、不写路由表。

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
接收方与群聊来自责任路由表；`是否需要人工确认` 来自等级字典表；触达记录由本 Skill 写入；状态推进由编排层执行。
