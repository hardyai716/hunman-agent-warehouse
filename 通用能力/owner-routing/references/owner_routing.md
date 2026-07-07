# owner_routing — 责任路由

## 用途
判断事件「该找谁」，输出主负责人、协作方、升级对象、渠道和 SLA。

## 当前实现状态

当前 `route_owner.py` 不直接读取旧责任路由表或旧等级字典表。它读取 `sop_config.v1`：

- `route_policies`：确定路由粒度和 route key 字段；
- `owner_source_registry`：解析 owner、协作方、升级人、默认群 ID 和兜底策略；
- SOP 等级配置：输出等级标签、标准严重度和 SLA 分钟。

输出写入本地 `route_results.json`，由编排、报告、触达和写回节点继续消费。事件表回写由显式写回节点负责。

## 输入
```json
{ "reason": "N1_chuxing_model_llm_pe_review", "_level": "P2" }
```

## 输出（结构固定）
```json
{
  "business_object": {"route_grain": "reason", "route_key": "N1_chuxing_model_llm_pe_review"},
  "owners": [{"role": "业务 POC", "id": "ou_xxx", "name": "负责人"}],
  "delivery_policy": {"primary_channel": "dm", "chat_strategy": "dm_owner", "chat_id": ""}
}
```

## 方法（写在 Skill 里）
- 匹配顺序：先根据 SOP 路由策略读取 route key，再查 Owner Source 映射，最后按配置中的兜底策略处理。
- 找不到匹配时不要臆造责任人，标记 `missing_route=true` 转人工。
- P0 必须带升级对象。
- SLA 信息来自 SOP 等级配置，旧等级字典表不再作为当前路由入口。

## 与表的边界
责任人、渠道来自 Owner Source；SLA 来自 SOP 等级配置；Skill 只负责匹配与回退逻辑。人员 ID 通过 lark-contact 解析或由受控配置提供，不猜 open_id。旧责任路由表和旧等级字典表仅作 legacy 兼容。
