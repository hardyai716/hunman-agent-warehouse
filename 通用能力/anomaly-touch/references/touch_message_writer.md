# touch_message_writer — 触达内容生成

## 用途
把事件转成可直接发送、对方看得懂、知道怎么做的消息。

## 读取的多维表格
- 触达模板表 `tblDLzboh47WqJla`：按「模板场景 + 适用等级 + 接收对象」选模板
- 责任路由表 `tblvFGVbTBQ3Vfws`：取接收方与渠道
- 等级字典表 `tblgcg6zvhaY3Qrw`：取「是否需要人工确认」（唯一权威来源）和「默认响应时长」（渲染 `{sla}` 变量）

> ⚠️ 触达模板表的「是否需要人工确认」字段已废弃，不再读取。统一从等级字典表读取。

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

- `need_human_confirm`：运行时以等级字典表字段 `fldFzR90Aa`（是否需要人工确认）为唯一权威来源动态读取，不在文档或代码中枚举等级名写死取值（当前配置 P0/P1/notice=true、P2=false，以表内实时配置为准）。
- `card_hash`：命中数据的顺序无关 SHA256 哈希，由 [../../review-monitoring-shared/scripts/card_validator.py](../../review-monitoring-shared/scripts/card_validator.py) 的 `compute_hits_hash` 计算、`embed_hash_in_card` 写入卡片 `_meta._data_hash`，供 [touch_sender.md](touch_sender.md) 的 `verify_card_hash` 校验。卡片本身由 Agent 按模板渲染，日期口径（`run_date`/`data_lag_days`）由编排显式传入，不依赖任何脚本内部默认值。
- preview 模式（`need_human_confirm=true`、首次触达）：卡片末尾含「请回复确认发送」提示，发至私聊；final 模式发群并含审计说明。

## 方法（写在 Skill 里）
- 必填变量缺失时返回 `missing_variables` 错误，不降级渲染。
- 卡片摘要标准格式：`{周期} 发现 {X} 条 {等级}级「{规则名称}」（{规则具体阈值条件}），请相关方及时排查。`
- 批量命中时渲染为单条表格消息，不拆多条发送。

## 与表的边界
模板内容来自触达模板表；`是否需要人工确认` 和 `{sla}` 变量来自等级字典表；Skill 只负责选模板、填变量、渲染。
