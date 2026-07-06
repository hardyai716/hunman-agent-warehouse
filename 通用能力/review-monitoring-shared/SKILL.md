---
name: review-monitoring-shared
description: 人审运营监控体系公共底座。Invoke when other monitoring skills need Base schema, shared redlines, card validation, or run gates.
metadata:
  version: "0.1.0"
  author: 李中涛
  status: MVP
  tags: [人审运营, 监控体系, 公共底座, 配置中心, 飞书多维表格]
  requires:
    bins: ["python3"]
    siblings: []
  requires_note: "本 skill 是被依赖方（公共底座），自身不主动调用其他 skill。card_validator.py 为纯 Python，无外部依赖。"
---

# 人审运营监控体系 · 公共底座（shared）

把整个「人审运营监控」skill 家族共用的**不变资产**集中到一处，避免各业务 skill 重复维护、口径漂移。本 skill 不做业务判断、不含指标口径，只被别的 skill 依赖。

## 定位（一句话）

**「一处维护、全体一致」** ——配置中心、schema、校验脚本、通用红线只在这里改一次，所有依赖它的监控 skill 自动对齐。

## 谁依赖本 skill

体系内所有横向能力 skill 与纵向业务 skill 都应在 `requires.siblings` 里声明依赖本 skill，并用相对路径引用其资产：

```yaml
requires:
  siblings:
    - review-monitoring-shared
```

引用示例（在别的 skill 的正文里）：
- 查表结构 → `../review-monitoring-shared/references/base_schema.md`
- 发送前校验 → `../review-monitoring-shared/scripts/card_validator.py`
- 跑批前 checklist → `../review-monitoring-shared/references/dry_run_pitfalls.md`

## 公共资产索引

| 资产 | 路径 | 作用 |
|---|---|---|
| 配置中心 & 9 表 schema | [references/base_schema.md](references/base_schema.md) | base_token=`<BASE_TOKEN>`；数据源/指标注册/撞线规则/等级字典/责任路由/触达模板/触达记录/事件/案例沉淀 9 张表完整字段结构 |
| 卡片一致性校验脚本 | [scripts/card_validator.py](scripts/card_validator.py) | 命中数据顺序无关 SHA256、`embed_hash_in_card` 写入 `_meta._data_hash`、发送前三重硬校验（哈希/等级/chat_id 一致）。 |
| 跑批踩坑规避清单 | [references/dry_run_pitfalls.md](references/dry_run_pitfalls.md) | 首次端到端干运行复盘的坑规避动作 + 环境/配置/数据/SQL/取数/字段/dry_run/门禁八道 gate |

## 配置中心（飞书多维表格）

- base_token：`<BASE_TOKEN>`（当前体系共用同一个 base；真实值应放在私有配置或运行环境中，定位与是否按业务模块拆分待后续明确）
- 完整字段结构见 [base_schema.md](references/base_schema.md)。

| 表 | table_id | 作用 |
|---|---|---|
| 数据源表 | `tblykQRCZjiqdhX5` | 数据从哪来、字段口径、就绪校验 |
| 指标注册表 | `tblKsDBLYwSHSNwm` | 有哪些指标（主配置表） |
| 撞线规则表 | `tbl73HpcA7rWtJ8T` | 什么情况算 notice/P2/P1/P0 |
| 等级字典表 | `tblgcg6zvhaY3Qrw` | 各等级优先级/SLA/「是否需要人工确认」（**所有等级口径的唯一权威来源**） |
| 责任路由表 | `tblvFGVbTBQ3Vfws` | 不同等级找谁（含「群聊ID」字段，字段ID：fldzVXrZB8） |
| 触达模板表 | `tblDLzboh47WqJla` | 怎么说 |
| 触达记录表 | `tbl39ZotgZJ8Q8aL` | 每次触达明细（运行时写入） |
| 事件表 | `tblHOC5Y8j58xDYQ` | 全流程状态（运行时写入） |
| 案例沉淀表 | `tblXrNg8vSXlhSFB` | 沉淀经验（MVP 暂不使用） |

## 三条不可违背的底线（全体系通用）

- **不臆造数据**：取数未成功时如实记录失败，绝不编造数值，也不得把数据源状态写成「已就绪」。
- **不误报**：数据未就绪/未到位/样本不足时不建高等级事件、不定高等级。
- **高风险需人工确认**：P0、下线/豁免等不可逆动作必须人工确认后再执行。

## 🔴 红灯反例黑名单（通用部分，命中即停）

以下是整个监控体系运行中**绝对不要做**的通用动作。业务 skill 可在此基础上追加自己的专有红线，但不得放松这里的通用底线。

| # | ❌ 禁止动作 | 为什么 | ✅ 正确做法 |
|---|---|---|---|
| 1 | 取数失败/未就绪时编造数值或把状态写成「已就绪」 | 污染事件与触达，违背「不臆造」底线 | 如实回写「未到位/异常」，本轮停止 |
| 2 | 数据未就绪/样本不足时仍建高等级事件/定高等级 | 误报，浪费人审资源、伤害信任 | 降置信度、不定高等级；就绪 gate 未过直接停 |
| 3 | 未做任何可执行性预校验就跑全量 SQL | 方言(ClickHouse)易拼错，浪费算力/污染结果 | 先预校验：优先 `query parse`；失败则降级 `LIMIT 1` 小样本探测，通过后再跑全量 |
| 4 | 凭空拼 `bytedcli`/风神命令行参数或臆造 region/appId | 参数错会查错库、报错或拿错数据 | 先加载对应 skill，参数按 URL 解析或 `list-authorized`/`dataset-model-info` 查得 |
| 5 | 臆造 open_id / chat_id / 责任人 | 发错人、发错群，触达失效 | 用 `lark-contact`/`lark-im` 解析；匹配不到标 `missing_route` 转人工 |
| 6 | 未经人工确认就发送 P0 或执行下线/豁免等不可逆动作 | 不可逆、高影响 | 走人工确认门禁，确认后再发/执行 |
| 7 | 发送前不剥离 `_` 前缀内部字段（如 `_meta`） | 飞书报 `unknown property`，发送失败 | 三重硬校验通过后递归剥离 `_` 键再发 |
| 8 | 跳过卡片哈希/等级/chat_id 一致性校验直接发 | 内容被篡改或发错群 | 发送前必过 `card_validator.py` 三重硬校验 |
| 9 | 遇取数/表读写异常静默跳过或静默失败 | 破坏状态一致性、难追溯 | 先如实记录/告知，再按各步停止规则处理 |

> 业务专有红线（如「打标率分母必须是完审量」「打标量字段是双下划线」等指标口径类）由各纵向业务 skill 自行维护，不进本表。

## 与业务 skill 的边界

- 本 skill **只提供公共资产**：schema、校验脚本、通用红线、配置中心索引。
- **不含**任何指标口径、阈值、SQL 模板、分级规则、路由/触达/编排逻辑——这些分别归纵向业务 skill 与横向能力 skill。
