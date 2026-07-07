# touch_message_writer — 触达内容生成

## 用途
把事件转成可直接发送、对方看得懂、知道怎么做的消息。

## 当前实现状态

本文保留历史触达内容生成契约。当前低效策略 SOP-first 链路不直接读取触达模板表、旧责任路由表或旧等级字典表：

- 报告卡片结构来自 `../templates/*.card_template.json` 和 `report_publisher.py`。
- 正式事件触达卡片由 `event_touch_sender.py` 根据命中行和 `route_results.json` 渲染。
- 是否需要人工确认、SLA、受众策略等来自 SOP-first 编译配置；旧 Base 表仅作 legacy 兼容。

## 写入的多维表格
- 无。本 Skill 只产出触达内容，不直接写表；实际发送、拉群、写「触达记录表」及回写事件表「最近触达时间」由 [touch_sender.md](touch_sender.md) 负责。

## 输入
```json
{
  "event_id": "<事件ID>",
  "level": "<等级，如P1>",
  "scene": "首次触达",
  "audience": "业务负责人",
  "variables": {
    "metric": "<指标名称>", "period": "<周期>",
    "business_object": "<业务对象ID>", "current_value": "<当前值>",
    "rule": "<命中规则描述>", "sla": "<来自等级字典表「默认响应时长」>"
  }
}
```

### 批量表格输入（同等级命中 ≥2 条时）
当同一等级一次命中多条策略时，传入 `hits` 数组（每个元素一条命中），由本 Skill 汇总渲染为**一条表格消息**：
```json
{
  "level": "P0",
  "scene": "首次触达",
  "hits": [
    {"strategy_id":"reason_1001","scene":"抖音安全审核","review_cnt":58000,"label_rate":"0.21%","rule":"P0规则"},
    {"strategy_id":"reason_1002","scene":"抖音画风审核","review_cnt":42000,"label_rate":"0.18%","rule":"P0规则"}
  ]
}
```

## 输出（结构固定）
```json
{
  "title": "【P1告警】近7天高完审低打标策略异常",
  "body": "...",
  "need_human_confirm": true,
  "card_hash": "sha256:...",
  "preview_mode": true
}
```

- `need_human_confirm`：SOP-first 链路中由 SOP 等级配置决定；旧等级字典表字段 `fldFzR90Aa` 只作为历史兼容说明，不作为当前低效策略触达内容生成入口。
- `card_hash`：命中数据的顺序无关 SHA256 哈希，由 [../../review-monitoring-shared/scripts/card_validator.py](../../review-monitoring-shared/scripts/card_validator.py) 的 `compute_hits_hash` 计算、`embed_hash_in_card` 写入卡片 `_meta._data_hash`，供 [touch_sender.md](touch_sender.md) 的 `verify_card_hash` 校验。卡片本身由 Agent 按模板渲染，日期口径（`run_date`/`data_lag_days`）由编排显式传入，不依赖任何脚本内部默认值。
- preview 模式（`need_human_confirm=true`、首次触达）：卡片末尾含「请回复确认发送」提示，发至私聊；final 模式发群并含审计说明。

## 方法（写在 Skill 里）
- 必填变量缺失时返回 `missing_variables` 错误，不降级渲染。
- 卡片摘要标准格式：`{周期} 发现 {X} 条 {等级}级「{规则名称}」（{规则具体阈值条件}），请相关方及时排查。`
- 批量命中时渲染为单条表格消息，不拆多条发送。

## 与表的边界
当前实现不以触达模板表作为内容权威源。触达模板表若继续保留，只作为 legacy/未来非结构化通知模板的预留表，不作为运营日常配置入口。
