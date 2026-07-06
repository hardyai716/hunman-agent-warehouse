# data_fetch — 取数（经 bytedcli 调风神执行 SQL）

> 本 Skill 不自己实现查询引擎，也不做自然语言转 SQL。SQL 由 `scripts/sql_templates.py` 渲染好，本文只负责把它交风神执行并标准化结果。**严禁臆造数据**：未真正查询成功时如实报告失败，绝不编造数值。

## 取数底座

| 数据源 | 底座 | 适用 |
|---|---|---|
| 风神数据集（ClickHouse 物理表） | `bytedcli` 调 `bytedance-aeolus` | **首选**。执行 Agent 渲染好的 SQL。 |
| 风神数据集（无 aeolus sibling 的 runtime，如 IDA） | 平台内置风神查数技能 | `bytedcli aeolus` 不可用时的同源替代（见下「风神取数技能探测顺序」）。 |
| 非 Aeolus 源（RDS/API/跨源） | `sqless-data-analysis` | 仅当数据不在风神时的自然语言取数兜底。 |

> 调用前必须先 `view_skill` 加载 `bytedcli`（含 `bytedance-aeolus`），按其文档执行命令，禁止凭空拼命令行参数。

### 风神取数技能探测顺序（跨 runtime 兼容）

不同 runtime 装的风神查数工具名不同。按下列顺序探测，命中第一个可用的即用它执行渲染好的 SQL（**都查同一份风神数据集 3888816，口径一致**）：

1. **`bytedcli aeolus query`**（含 `bytedance-aeolus` sibling）— 首选。若 `bytedcli aeolus ...` 报 `unknown command 'aeolus'`，说明本 runtime 的 lark-cli/bytedcli 没集成 aeolus，转下一档。
2. **平台内置风神查数技能** — 依次找名字含 `aeolus` 的可用技能/工具：`aeolus-query` / `aeolus_sql_query` / `aeolus-sql` / 其它风神 SQL 查询能力。命中即用（走入口 B 逻辑数据集，见「两种取数入口」）。
3. **`sqless-data-analysis`** — 前两者都没有时的自然语言取数兜底。
4. 全都不可用 → 如实报告「无可用风神取数技能」，转人工，**不臆造数据**。

> 判定要点：报 `unknown command 'aeolus'` 不是失败终点，而是「换入口 B」的信号——先 `view_skill`/列出可用技能确认有没有 `aeolus-query` 类工具，再决定。

## 连接参数解析（运行时获取，不写死）

| 参数 | 怎么拿 |
|---|---|
| **region** | 看数据地址 URL 域名：`data.bytedance.net` → `cn`；国内默认 `cn`。 |
| **dataset-id** | 数据集详情页 URL 里的 `sid`；或直接用已知数据集标识。 |
| **appId** | 详情页常不含 → 用 `bytedcli aeolus list-authorized -r <region> --type data_set` 按 dataset-id 匹配 `app.id`。 |
| **engine / 物理表** | `bytedcli aeolus dataset-model-info -r <region> --app-id <appId> --dataset-id <id>` 读 `nodeConf.dataSourceType`（`click_house`）与 `nodeConf.dbName`/`tbName` 拿物理表 `db.table`。 |

社区人工审核明细数据集为 ClickHouse，物理表 `olap_content_security_community.dws_sft_tcs_review_task_detail_di`（与 `sql_templates.py` 默认一致）。

## 两种取数入口（按 runtime 选，口径一致）

不同 runtime 提供的取数工具不同，SQL 的 FROM/字段引用风格随之变化。`sql_templates.py` 两种都支持——只需切 `ctx.quote_style` / `ctx.quote_table` / `ctx.field_map`，**计算口径不变**。渲染前先确认当前环境是哪种入口：

| | 入口 A · 物理表（默认） | 入口 B · 逻辑数据集 |
|---|---|---|
| 工具 | `bytedcli aeolus query`（含 `bytedance-aeolus` sibling） | 平台内置 `aeolus_sql_query` 等（走逻辑数据集） |
| FROM | 物理表裸写 `olap_content_security_community.dws_sft_tcs_review_task_detail_di` | 数据集 ID：`` `3888816` `` |
| 字段引用 | `` `[Name]` ``（反引号包方括号，服务端展开聚合） | 纯反引号中文显示名 `` `送审原因` `` |
| 分区字段 | `` `[p_date]` `` | `` `日期` ``（显示名，**不能**用 `[]` 包裹） |
| 机审标签字段 | Name `机审一级标签` | 显示名 `机审根标签名` |
| render 参数 | `quote_style="bracket"`, `quote_table=False`（默认） | `quote_style="backtick"`, `quote_table=True`, 覆盖 `field_map` 为中文显示名 |

> **判定入口**：若 `bytedcli aeolus ...` 报 `unknown command 'aeolus'`（如 Ada 沙盒），说明当前 runtime 无 aeolus sibling → 走入口 B，用平台内置数据集查询工具 + 逻辑数据集风格。两入口跑出的打标率/日均量应一致（同一底层数据）。

**入口 B 的 field_map 覆盖模板**（渲染前传给 ctx）：

```python
import sql_templates as t
ctx = t.build_notice_ctx(cur_start='...', cur_end='...',
    table='3888816',                    # 入口 B：FROM 数据集 ID，不是物理表
    quote_style='backtick', quote_table=True)
ctx['field_map'] = {**t._DEFAULT_FIELD_MAP,
    'reason': '送审原因', 'date': '日期',
    'jin_shen': '进审量_reviewid', 'wan_shen': '完审量_reviewid',
    'da_biao': '打标量__reviewid', 'mach_root_label_name': '机审根标签名'}
ctx['date_field'] = '日期'
sql = t.render_sql('rule_low_label_rate_notice', {}, ctx)
```

> 入口 B 下逻辑数据集常要求「分区字段筛选」：SQL 必带 `` `日期` BETWEEN ... `` 的 WHERE，且分区字段裸写不加 `[]`（模板已用 `{f.date}` 渲染，`date_field='日期'` 即可）。

## 执行流程（每个等级一条 SQL）

1. **可执行性预校验（防拼错，不可跳过；按入口选方式）**：
   - **入口 A（bytedcli aeolus）**：优先 `bytedcli aeolus query-editor query parse --engine ch --sql "<SQL>"`（只验方言/字段/语法、不执行）。parse 因 `LACK_PERMISSION`/物理表不可用失败 → 降级 `LIMIT 1` 小样本探测（`bytedcli -j aeolus query`）。parse 报错（非权限类）→ 按提示修正或转人工，**不带错 SQL 盲跑**。
   - **入口 B（aeolus_sql_query 等无独立 parse 能力的工具）**：没有 `query parse` 接口时，**用同一工具跑一次 `LIMIT 1` 小样本探测**当预校验——在渲染好的 SQL 尾部加 `LIMIT 1` 执行一次，确认语法可解析、字段可展开、无报错，再去掉 `LIMIT 1` 跑全量。**「工具没有 parse」不等于「可跳过预校验」——降级为 LIMIT 1 探测即可。**
   - **可信例外（可省 LIMIT 1 探测）**：四个已注册 sql_key（notice/P2/P1/P0）由 `sql_templates.py` 渲染、有 19 个单测背书，SQL 结构确定；若已确认走注册模板且参数走默认/校验通过，可直接跑全量，但需在结论里注明「已注册模板、免探测」。**兜底自然语言拼的 SQL、或改过阈值字段的，一律必须 LIMIT 1 探测。**
2. **执行全量**：`bytedcli -j aeolus query -r <region> <datasetId> "<SQL>" --limit 1000`
   - `-j` 走 JSON 输出，直接读 `data.columns` + `data.rows`，**不解析文本表格**（避免长字段截断误判）。
   - `--limit 1000` 放大防分页截断；检查返回的 `truncated` 字段，命中则说明结果被截断需注意。
3. **结果判定**：

| 结果 | 判定 |
|---|---|
| 非空 | 命中，每一行是一条低效策略，进入分级汇总 |
| 空 | 该等级本期无低效策略，正常结束 |
| 报错 / 权限 / 未就绪 | **如实报告失败**，不判为「无低效策略」（区分「确无」与「查询失败」） |

## SQL 拼接边界（能力限制）

- P0/P1/P2 都是**多子查询 UNION / 双周期 JOIN / 环比**的复杂逻辑，**必须走 `aeolus query` 写 SQL**（由 `sql_templates.py` 渲染），不要凑 `aeolus viz-query`——viz-query 只适合单数据集简单聚合，表达不了 UNION/环比，会漏判。
- SQL 骨架、字段引用、动态天数、打标率重算全部封装在 `sql_templates.py`，本步只负责把渲染产物交风神执行，不手改 SQL 文本。

## 错误与降级（必须显式返回，不得静默编造）

| 情况 | 处理 |
|---|---|
| 目标分区未到位 / 数据延迟未满足 | 停止取数，报告「未就绪」 |
| 查询报错 / 权限不足 | 停止；权限类透出申请链接转人工 |
| 字段缺失（字段名对不上真实 schema） | 不强行映射，说明并转人工核对映射；对照 `dataset-fields` 的 Name 列 |
| 返回空结果 | 区分「确无低效策略」与「查询条件写错」；后者修正重试 |
| 本轮未真正访问数据源 | 不得报告「已取数」，不得编造 rows |
| 风神路径失败且可降级 | 切 `sqless-data-analysis` 兜底重试一次；仍失败转人工 |
