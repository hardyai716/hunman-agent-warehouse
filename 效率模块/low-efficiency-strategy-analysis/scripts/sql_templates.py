#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""撞线规则 SQL 模板字典 + 渲染 + 参数校验。

v2.1 优化点（针对 2026-07-02 硬编码 /7 问题复盘）：
1. **动态天数计算**：所有日均计算从硬编码 `/ {ctx.cur_days}`（即 /7）改为
   `COUNT(DISTINCT p_date)` 动态计算实际有数据的天数，避免某天数据未就绪时
   日均被低估（如只有 6 天数据却除以 7）。
2. **双层聚合架构**：单周期/双周期/P1/P2 骨架全部改为双层查询——
   - 内层：按 reason + date 聚合（或按 reason 聚合并 COUNT(DISTINCT date) 得到 data_days）
   - 外层：按 reason 聚合，用 SUM(metric) / COUNT(DISTINCT dt) 或 SUM(metric)/data_days 计算日均
3. **打标率重算**：外层不再直接引用数据集预聚合 `打标率__reviewid`，而是用
   `if(SUM(wan_shen)=0, 0, SUM(da_biao)/SUM(wan_shen))` 基于内层 SUM 结果重算
   （分母是完审量 wan_shen，不是进审量），确保打标率与动态日均口径一致。
4. **环比公式修正**：双周期环比从 `(cur-prev)/prev`（总量比）改为
   `(cur/data_days_cur - prev/data_days_prev) / (prev/data_days_prev)`（日均比），
   避免两周期天数不一致时环比失真。

v2.0 优化点（针对 2026-07-02 notice 规则踩坑复盘）：
1. **字段别名映射**：模板内部使用逻辑字段名（reason/jin_shen/wan_shen/da_biao/ratio_val 等），
   渲染时通过 ctx.field_map 映射到数据集真实字段名（默认 reason→reason；逻辑数据集入口可覆盖为中文显示名），不再硬编码中文字段。
2. **引用风格可配置**：通过 ctx.quote_style 控制字段包裹方式，支持：
   - "bracket"：`[字段]`（旧默认，部分数据集支持）
   - "backtick"：`字段`（数据集 3888816 等 ClickHouse 方言）
   - "none"：不包裹（字段无特殊字符时）
3. **聚合字段识别**：通过 ctx.agg_fields 声明哪些字段是数据集已定义的聚合指标（如进审量_reviewid），
   渲染时自动避免二次聚合（不套 SUM/COUNT），并在 SELECT 中直接引用。
4. **日均计算支持**：单周期骨架新增 {div_expr} 支持，可选择输出日均量（/COUNT(DISTINCT dt)）或原始量，
   由 ctx.divide_by_days 控制（默认 True，输出日均）。
5. **base_filter 结构化**：ctx.base_filter 既接受"已拼好的 SQL 片段"（向后兼容），也接受
   list[dict] 结构化过滤条件（见 _build_base_filter），运行时自动渲染，避免自然语言解析。
6. **分区字段校验**：渲染前校验 ctx.date_field 非空且为安全标识符，避免分区字段错配。
7. **表名引用**：表名通过 ctx.quote_table 控制是否加反引号（风神数据集名常含 []/- 等特殊字符，
   默认加反引号）。

分层架构「配置表存元数据 + Skill 代码存 SQL 模板字典」的代码层：
- SQL_TEMPLATES：**按规则维度**建设的 SQL 模板字典，key 与规则 ID 一一对应。
- validate_params：校验 sql_params 是否满足该规则模板声明，失败即转人工、不告警。
- render_sql：把 {p.*}（规则参数）与 {ctx.*}（运行时上下文）填进骨架，产出最终 SQL。

占位符两套命名空间，彼此不串号：
- {p.xxx}   来自撞线规则表 sql_params（阈值、算子、字段名、排序字段、过滤子句）。
- {ctx.xxx} 由编排层运行时计算注入（表名、日期字段、基础过滤、分区窗口、窗口天数、字段映射）。

方言边界（重要）：本模块只产出 **SQL 文本**。SQL 方言相关的只有 ctx.quote_style / ctx.quote_table
/ ctx.field_map，这些决定 SQL 长什么样：
- 默认 quote_style="bracket" → 字段渲染成 `` `[Name]` ``（反引号+方括号），是风神物理表 FROM 下的
  **语义字段占位符**，服务端自动展开成底层 ClickHouse 表达式（`[完审量_reviewid]` → uniqExact(if(...))），
  口径由数据集定义保证，无需手抄聚合表达式。
- 默认 quote_table=False → 物理表 `db.table`（含点）裸写，如
  olap_content_security_community.dws_sft_tcs_review_task_detail_di。
- 需查物理列裸名（自行重建指标）时可切 quote_style="backtick"（`Name`）。
而 region / app_id / dataset_id / 执行引擎属于 **bytedcli 命令行参数**，不是 SQL 内容，
由编排层调 `bytedcli aeolus query` 时传入，本模块不涉及、也不应写死。
"""

from __future__ import annotations

import re
from typing import Any

# ============================================================
# 常量
# ============================================================

# 允许出现在 sql_params 里的比较算子白名单（防注入）。
_ALLOWED_OPS = {"<", ">", "<=", ">=", "=", "!=", "<>"}

# dual_period_growth_compare 外层查询实际暴露的计算列别名白名单。
_DUAL_OUTER_ALIASES = {"cur_val", "prev_val", "growth_rate", "daily_delta"}

# 字段名 / 排序字段允许的字符：中文、字母、数字、下划线。禁止反引号、引号、空格、分号等。
_IDENT_RE = re.compile(r"^[\w\u4e00-\u9fff]+$")

# LIKE 值允许的字符（防注入）：中文、字母、数字、下划线、百分号、空格、短横。
_LIKE_VALUE_RE = re.compile(r"^[\w\u4e00-\u9fff% _\-./]+$")

# IN 列表值允许的字符（单值）：中文、字母、数字、下划线、短横、点、斜杠。
_IN_VALUE_RE = re.compile(r"^[\w\u4e00-\u9fff\-./]+$")

# 支持的引用风格
_QUOTE_STYLES = {"bracket", "backtick", "none"}

# 占位符匹配：{p.xxx} 或 {ctx.xxx}
_TOKEN_RE = re.compile(r"\{(p|ctx)\.([\w]+)\}")

# 模板内部使用的"逻辑字段名"→ 真实字段名的默认映射（数据集 3888816 社区人工审核明细）。
# 编排层可通过 ctx.field_map 覆盖。
#
# 取值口径（2026-07-03 三方实测对齐）：这里的值是风神 `dataset-fields` 的 **Name 列**
# 真值（不是中文 description/显示名）。默认 quote_style="bracket"，渲染时被包成
# `` `[Name]` ``（反引号+方括号）——这是物理表 FROM 下风神服务端识别的**语义字段占位符**，
# 会被自动展开成底层 ClickHouse 表达式（如 `[完审量_reviewid]` → uniqExact(if(...))）。
# 注意：裸 `[Name]`（无反引号）在物理表上会被 ClickHouse 当数组下标语法直接报错；
# 纯反引号 `Name`（无方括号）对逻辑数据集报「未知表/字段权限」。三者只有 `` `[Name]` `` 可跑通。
_DEFAULT_FIELD_MAP: dict[str, str] = {
    # 维度（Name 列真值：reason/scene/project_title 的 Name 是英文，机审标签的 Name 是中文）
    "reason": "reason",
    "project_title": "project_title",
    "scene": "scene",
    "mach_root_label_name": "机审一级标签",  # Name 列真值（description 才是「机审根标签名」）
    "date": "p_date",  # 分区字段 Name（UI 显示名/别名为「日期」）
    # 聚合指标（数据集已定义的语义聚合字段，`[Name]` 由服务端展开，不可二次聚合套 SUM）
    "jin_shen": "进审量_reviewid",
    "wan_shen": "完审量_reviewid",
    "da_biao": "打标量__reviewid",
    "ratio": "打标率__reviewid",
}

# 默认聚合字段集合（逻辑字段名）——这些字段在数据集中已是聚合表达式，SELECT/HAVING 中直接引用。
_DEFAULT_AGG_FIELDS: set[str] = {"jin_shen", "wan_shen", "da_biao", "ratio"}


# ============================================================
# 引用/转义工具
# ============================================================

def _quote_ident(name: str, style: str) -> str:
    """按引用风格包裹标识符。name 必须已通过 _IDENT_RE 校验。"""
    if style == "bracket":
        return f"`[{name}]`"
    if style == "backtick":
        return f"`{name}`"
    if style == "none":
        return name
    raise TemplateError(f"未知 quote_style: {style!r}，可选：{sorted(_QUOTE_STYLES)}")


def _quote_table(name: str, quote: bool) -> str:
    """包裹表名。表名可能含 []/- 等特殊字符（风神数据集显示名），默认加反引号。"""
    return f"`{name}`" if quote else name


def _sql_literal(value: str) -> str:
    """SQL 字符串字面量转义（单引号转义）。"""
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


# ============================================================
# 结构化 base_filter 渲染
# ============================================================
# 支持的过滤项结构（list[dict]）：
#   {"field": "<逻辑字段名>", "op": "like", "value": "%xxx%", "negate": true}   → NOT LIKE
#   {"field": "<逻辑字段名>", "op": "in", "values": ["a","b"], "negate": false} → IN / NOT IN
#   {"field": "<逻辑字段名>", "op": "is_null", "negate": false}                 → IS NULL / IS NOT NULL
#   {"field": "<逻辑字段名>", "op": "is_null_or_in", "values": [...]}           → (f IS NULL OR f IN (...))
#   {"field": "<逻辑字段名>", "op": "cmp", "cmp_op": "<", "value": 123}         → 比较
# 所有 field 必须是 field_map 中的逻辑字段名，渲染时自动映射 + 加引用。

def _build_base_filter(
    raw: Any,
    field_map: dict[str, str],
    quote_style: str,
) -> str:
    """把 ctx.base_filter 渲染成可直接拼入 WHERE 的 SQL 片段（以 AND 开头，或空串）。

    - raw 为 str：直接返回（向后兼容，调用方负责安全）。
    - raw 为 list[dict]：按结构化规则渲染。
    - raw 为 None / 空：返回空串。
    """
    if raw is None or raw == "":
        return ""
    if isinstance(raw, str):
        return raw
    if not isinstance(raw, list):
        raise TemplateError(
            f"base_filter 必须是 SQL 字符串或结构化 list[dict]，收到 {type(raw).__name__}"
        )

    clauses: list[str] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise TemplateError(f"base_filter[{i}] 必须是 dict，收到 {type(item).__name__}")
        op = item.get("op")
        logical_field = item.get("field")
        negate = bool(item.get("negate", False))

        if logical_field is None and op != "raw":
            raise TemplateError(f"base_filter[{i}] 缺少 field")
        if logical_field is not None and logical_field not in field_map:
            raise TemplateError(
                f"base_filter[{i}] field={logical_field!r} 不在 field_map 中，"
                f"可用：{sorted(field_map)}"
            )
        real = field_map.get(logical_field, "") if logical_field else ""
        quoted = _quote_ident(real, quote_style) if real else ""

        if op == "like":
            value = item.get("value")
            if not isinstance(value, str) or not _LIKE_VALUE_RE.match(value):
                raise TemplateError(f"base_filter[{i}] like value 非法：{value!r}")
            kw = "NOT LIKE" if negate else "LIKE"
            clauses.append(f"AND {quoted} {kw} {_sql_literal(value)}")

        elif op == "in":
            values = item.get("values")
            if not isinstance(values, list) or not values:
                raise TemplateError(f"base_filter[{i}] in values 必须是非空 list")
            for v in values:
                if not isinstance(v, str) or not _IN_VALUE_RE.match(v):
                    raise TemplateError(f"base_filter[{i}] in 列表含非法值：{v!r}")
            in_list = ", ".join(_sql_literal(v) for v in values)
            kw = "NOT IN" if negate else "IN"
            clauses.append(f"AND {quoted} {kw} ({in_list})")

        elif op == "is_null":
            kw = "IS NOT NULL" if negate else "IS NULL"
            clauses.append(f"AND {quoted} {kw}")

        elif op == "is_null_or_in":
            # 机审根标签名这类：(f IS NULL OR f IN (...))
            values = item.get("values")
            if not isinstance(values, list) or not values:
                raise TemplateError(f"base_filter[{i}] is_null_or_in values 必须是非空 list")
            for v in values:
                if not isinstance(v, str) or not _IN_VALUE_RE.match(v):
                    raise TemplateError(f"base_filter[{i}] is_null_or_in 列表含非法值：{v!r}")
            in_list = ", ".join(_sql_literal(v) for v in values)
            clauses.append(f"AND ({quoted} IS NULL OR {quoted} IN ({in_list}))")

        elif op == "cmp":
            cmp_op = item.get("cmp_op")
            if cmp_op not in _ALLOWED_OPS:
                raise TemplateError(f"base_filter[{i}] cmp_op={cmp_op!r} 非法")
            value = item.get("value")
            if isinstance(value, (int, float)):
                lit = str(value)
            elif isinstance(value, str) and re.match(r"^-?\d+(?:\.\d+)?$", value):
                lit = value
            else:
                raise TemplateError(f"base_filter[{i}] cmp value 必须是数字：{value!r}")
            clauses.append(f"AND {quoted} {cmp_op} {lit}")

        elif op == "raw":
            # 直接拼入的安全 SQL 片段（调用方负责注入安全）
            sql = item.get("sql", "")
            if not isinstance(sql, str) or not sql.strip():
                raise TemplateError(f"base_filter[{i}] raw.sql 必须是非空字符串")
            clauses.append(f"AND {sql.strip()}")

        else:
            raise TemplateError(f"base_filter[{i}] 未知 op: {op!r}")

    return "\n  ".join(clauses)


# ============================================================
# 默认 base_filter（高完审低打标策略的标准过滤条件）
# 可通过 ctx.base_filter 覆盖；若 ctx.base_filter 未传且 ctx.use_default_base_filter=True，
# 则使用此默认值。
# ============================================================

_DEFAULT_BASE_FILTER_LOW_LABEL: list[dict] = [
    # A: project_title NOT LIKE 黑名单
    {"field": "project_title", "op": "like", "value": "%虚假%", "negate": True},
    {"field": "project_title", "op": "like", "value": "%标注%", "negate": True},
    {"field": "project_title", "op": "like", "value": "%虚假不实%", "negate": True},
    {"field": "project_title", "op": "like", "value": "%封面%", "negate": True},
    {"field": "project_title", "op": "like", "value": "%自动处置%", "negate": True},
    {"field": "project_title", "op": "like", "value": "%演绎%", "negate": True},
    {"field": "project_title", "op": "like", "value": "%模型%", "negate": True},
    {"field": "project_title", "op": "like", "value": "%run%", "negate": True},
    {"field": "project_title", "op": "like", "value": "%质检%", "negate": True},
    {"field": "project_title", "op": "like", "value": "%QA%", "negate": True},
    {"field": "project_title", "op": "like", "value": "%测试%", "negate": True},
    {"field": "project_title", "op": "like", "value": "%大模型%", "negate": True},
    {"field": "project_title", "op": "like", "value": "%离线%", "negate": True},
    # B: scene IN 三个社区审核场景
    {"field": "scene", "op": "in", "values": [
        "community_audit_safe", "community_audit_style", "community_audit_moderate",
    ]},
    # C: reason NOT IN 两个排除项
    {"field": "reason", "op": "in", "values": ["recall_skip_L6", "fatal_output"], "negate": True},
    # D: mach_root_label_name IS NULL OR IN 白名单
    {"field": "mach_root_label_name", "op": "is_null_or_in", "values": [
        "不良行为或争议价值观", "侵犯未成年权益", "偏激社会情绪和涉外言论",
        "党和国家形象负面", "危险行为", "国家安全", "引人不适",
        "指令舆情相关", "短期策略迁移", "色情性化", "违法违规", "领导人",
    ]},
]


# ============================================================
# SQL 骨架（v2：使用 {f.xxx} 逻辑字段引用，由渲染器替换为真实引用）
# ============================================================
# 注意：骨架里的 {f.xxx} 不是 {p.xxx}/{ctx.xxx} 占位符，而是渲染器识别的"逻辑字段引用"，
# 会被替换成 _quote_ident(field_map[xxx], quote_style)。这样模板与数据集字段彻底解耦。

_SINGLE_PERIOD_SQL_V2 = """SELECT reason,
       SUM(jin_shen){div_expr} AS avg_jinshen,
       SUM(wan_shen){div_expr} AS avg_wanshen,
       SUM(da_biao){div_expr} AS avg_dabiao,
       if(SUM(wan_shen) = 0, 0, SUM(da_biao) / SUM(wan_shen)) AS ratio_val,
       concat('打标率偏低（近7天打标率<', toString(round({p.ratio_threshold}*100,2)), '%且进审量>', toString({p.guard_threshold}), '，纳入周报观察）') AS hit_condition
FROM (
  SELECT {f.reason} AS reason,
         {f.date} AS dt,
         {a.jin_shen} AS jin_shen,
         {a.wan_shen} AS wan_shen,
         {a.da_biao} AS da_biao
  FROM {t}
  WHERE {f.date} >= '{ctx.cur_start}' AND {f.date} <= '{ctx.cur_end}'
    {base_filter}
  GROUP BY {f.reason}, {f.date}
) t
GROUP BY reason
HAVING if(SUM(wan_shen) = 0, 0, SUM(da_biao) / SUM(wan_shen)) {p.ratio_op} {p.ratio_threshold}
   AND SUM({guard_real}) {p.guard_op} {p.guard_threshold}
ORDER BY {order_real} DESC
LIMIT 500"""

_DUAL_PERIOD_GROWTH_SQL_V2 = """SELECT cur.reason AS reason,
       cur.metric_val / cur.data_days AS cur_val,
       prev.metric_val / prev.data_days AS prev_val,
       (cur.metric_val / cur.data_days - prev.metric_val / prev.data_days)
         / NULLIF(prev.metric_val / prev.data_days, 0) AS growth_rate,
       (cur.metric_val / cur.data_days - prev.metric_val / prev.data_days) AS daily_delta
FROM (
  SELECT {f.reason} AS reason,
         SUM({f.metric}) AS metric_val,
         COUNT(DISTINCT {f.date}) AS data_days
  FROM {t}
  WHERE {f.date} >= '{ctx.cur_start}' AND {f.date} <= '{ctx.cur_end}'
    {base_filter}
  GROUP BY {f.reason}
  HAVING 1 = 1 {p.label_rate_filter}
) cur
JOIN (
  SELECT {f.reason} AS reason,
         SUM({f.metric}) AS metric_val,
         COUNT(DISTINCT {f.date}) AS data_days
  FROM {t}
  WHERE {f.date} >= '{ctx.prev_start}' AND {f.date} <= '{ctx.prev_end}'
    {base_filter}
  GROUP BY {f.reason}
  HAVING 1 = 1 {p.label_rate_filter}
) prev ON cur.reason = prev.reason
WHERE prev.metric_val / prev.data_days > {p.prev_daily_guard}
  AND (cur.metric_val / cur.data_days - prev.metric_val / prev.data_days)
        / NULLIF(prev.metric_val / prev.data_days, 0) > {p.growth_rate_threshold}
  AND (cur.metric_val / cur.data_days - prev.metric_val / prev.data_days) > {p.daily_delta_threshold}
ORDER BY {p.order_field} DESC
LIMIT 500"""


_P2_UNION_SQL_V2 = """SELECT reason,
       max(jin_shen) / max(data_days) AS avg_jinshen,
       max(wan_shen) / max(data_days) AS avg_wanshen,
       max(da_biao) / max(data_days) AS avg_dabiao,
       if(max(wan_shen) = 0, 0, max(da_biao) / max(wan_shen)) AS ratio_val,
       arrayStringConcat(arraySort(groupUniqArray(hit_condition)), '；') AS hit_condition
FROM (
  -- 条件一：单策略低效（近7天累计进审>{p.c1_jinshen_threshold} 且 打标率<{p.c1_ratio_threshold}）
  SELECT reason, jin_shen, wan_shen, da_biao, data_days, ratio_val, hit_condition
  FROM (
    SELECT {f.reason} AS reason,
           {a.jin_shen} AS jin_shen,
           {a.wan_shen} AS wan_shen,
           {a.da_biao} AS da_biao,
           COUNT(DISTINCT {f.date}) AS data_days,
           if({a.wan_shen} = 0, 0, {a.da_biao} / {a.wan_shen}) AS ratio_val,
           concat('单策略低效（近7天累计进审>', toString({p.c1_jinshen_threshold}), '且打标率<', toString(round({p.c1_ratio_threshold}*100,2)), '%）') AS hit_condition
    FROM {t}
    WHERE {f.date} >= '{ctx.cur_start}' AND {f.date} <= '{ctx.cur_end}'
      {base_filter}
    GROUP BY {f.reason}
    HAVING {a.jin_shen} > {p.c1_jinshen_threshold}
       AND if({a.wan_shen} = 0, 0, {a.da_biao} / {a.wan_shen}) < {p.c1_ratio_threshold}
  ) c1

  UNION ALL

  -- 条件二：风险域进审量异常上涨（本周期 vs 上周期，低效策略环比增长）
  SELECT cur.reason AS reason,
         cur.jin_shen AS jin_shen,
         cur.wan_shen AS wan_shen,
         cur.da_biao AS da_biao,
         cur.data_days AS data_days,
         cur.ratio_val AS ratio_val,
         concat('进审量异常上涨（近7天vs前7天环比增长>', toString(round({p.growth_rate_threshold}*100,0)), '%且日均增量>', toString({p.daily_delta_threshold}), '，本周期打标率<', toString(round({p.c2_ratio_threshold}*100,2)), '%）') AS hit_condition
  FROM (
    SELECT {f.reason} AS reason,
           {a.jin_shen} AS jin_shen,
           {a.wan_shen} AS wan_shen,
           {a.da_biao} AS da_biao,
           COUNT(DISTINCT {f.date}) AS data_days,
           if({a.wan_shen} = 0, 0, {a.da_biao} / {a.wan_shen}) AS ratio_val
    FROM {t}
    WHERE {f.date} >= '{ctx.cur_start}' AND {f.date} <= '{ctx.cur_end}'
      {base_filter}
    GROUP BY {f.reason}
    HAVING if({a.wan_shen} = 0, 0, {a.da_biao} / {a.wan_shen}) < {p.c2_ratio_threshold}
  ) cur
  JOIN (
    SELECT {f.reason} AS reason,
           {a.jin_shen} AS jin_shen,
           COUNT(DISTINCT {f.date}) AS data_days
    FROM {t}
    WHERE {f.date} >= '{ctx.prev_start}' AND {f.date} <= '{ctx.prev_end}'
      {base_filter}
    GROUP BY {f.reason}
  ) prev ON cur.reason = prev.reason
  WHERE prev.jin_shen / prev.data_days > {p.prev_daily_guard}
    AND (cur.jin_shen / cur.data_days - prev.jin_shen / prev.data_days)
          / NULLIF(prev.jin_shen / prev.data_days, 0) > {p.growth_rate_threshold}
    AND (cur.jin_shen / cur.data_days - prev.jin_shen / prev.data_days) > {p.daily_delta_threshold}
)
GROUP BY reason
ORDER BY avg_wanshen DESC
LIMIT 500"""


# ============================================================
# 模板规格
# ============================================================

_SINGLE_PERIOD_SPEC = {
    "version": "2.0",
    "required_params": [
        "ratio_field", "ratio_op", "ratio_threshold",
        "guard_field", "guard_op", "guard_threshold",
        "order_field",
    ],
    "optional_params": {},
    "param_types": {
        "ratio_field": "logical_field",   # 逻辑字段名，必须在 field_map 中
        "ratio_op": "op",
        "ratio_threshold": "number",
        "guard_field": "logical_field",
        "guard_op": "op",
        "guard_threshold": "number",
        "order_field": "logical_field",
    },
    "ctx_keys": [
        "table", "cur_start", "cur_end",
        # 可选 ctx（有默认值）：date_field, cur_days, field_map, agg_fields,
        # quote_style, quote_table, divide_by_days, base_filter, use_default_base_filter
    ],
    "optional_ctx_keys": [
        "date_field", "cur_days", "field_map", "agg_fields",
        "quote_style", "quote_table", "divide_by_days",
        "base_filter", "use_default_base_filter",
    ],
    "sql": _SINGLE_PERIOD_SQL_V2,
}

_DUAL_PERIOD_SPEC = {
    "version": "2.0",
    "required_params": [
        "metric_field", "prev_daily_guard",
        "growth_rate_threshold", "daily_delta_threshold",
        "order_field", "label_rate_filter",
    ],
    "param_types": {
        "metric_field": "logical_field",
        "prev_daily_guard": "number",
        "growth_rate_threshold": "number",
        "daily_delta_threshold": "number",
        "order_field": "outer_alias",
        "label_rate_filter": "filter_clause",
    },
    "ctx_keys": [
        "table",
        "cur_start", "cur_end", "prev_start", "prev_end",
        "cur_days", "prev_days",
    ],
    "optional_ctx_keys": [
        "date_field", "field_map", "agg_fields",
        "quote_style", "quote_table",
        "base_filter", "use_default_base_filter",
    ],
    "sql": _DUAL_PERIOD_GROWTH_SQL_V2,
}


_P2_UNION_SPEC = {
    "version": "2.0",
    "required_params": [
        "c1_jinshen_threshold", "c1_ratio_threshold",
        "c2_ratio_threshold",
        "prev_daily_guard", "growth_rate_threshold", "daily_delta_threshold",
    ],
    "optional_params": {},
    "param_types": {
        "c1_jinshen_threshold": "number",
        "c1_ratio_threshold": "number",
        "c2_ratio_threshold": "number",
        "prev_daily_guard": "number",
        "growth_rate_threshold": "number",
        "daily_delta_threshold": "number",
    },
    "ctx_keys": [
        "table",
        "cur_start", "cur_end", "prev_start", "prev_end",
        "cur_days", "prev_days",
    ],
    "optional_ctx_keys": [
        "date_field", "field_map", "agg_fields",
        "quote_style", "quote_table",
        "base_filter", "use_default_base_filter",
    ],
    "sql": _P2_UNION_SQL_V2,
}


_P1_UNION_SQL_V2 = """SELECT reason,
       max(jin_shen) / max(data_days) AS avg_jinshen,
       max(wan_shen) / max(data_days) AS avg_wanshen,
       max(da_biao) / max(data_days) AS avg_dabiao,
       if(max(wan_shen) = 0, 0, max(da_biao) / max(wan_shen)) AS ratio_val,
       arrayStringConcat(arraySort(groupUniqArray(hit_condition)), '；') AS hit_condition
FROM (
  -- 条件一：单策略持续低效（近7天+前7天 双周期均高量低效）
  SELECT cur.reason AS reason,
         cur.jin_shen AS jin_shen,
         cur.wan_shen AS wan_shen,
         cur.da_biao AS da_biao,
         cur.data_days AS data_days,
         cur.ratio_val AS ratio_val,
         concat('双周持续低效（近7天+前7天双周期日均进审>', toString({p.c1_cur_daily_jinshen}), '且双周期打标率<', toString(round({p.c1_ratio_threshold}*100,2)), '%）') AS hit_condition
  FROM (
    SELECT {f.reason} AS reason,
           {a.jin_shen} AS jin_shen,
           {a.wan_shen} AS wan_shen,
           {a.da_biao} AS da_biao,
           COUNT(DISTINCT {f.date}) AS data_days,
           if({a.wan_shen} = 0, 0, {a.da_biao} / {a.wan_shen}) AS ratio_val
    FROM {t}
    WHERE {f.date} >= '{ctx.cur_start}' AND {f.date} <= '{ctx.cur_end}'
      {base_filter}
    GROUP BY {f.reason}
    HAVING if({a.wan_shen} = 0, 0, {a.da_biao} / {a.wan_shen}) < {p.c1_ratio_threshold}
       AND {a.jin_shen} / COUNT(DISTINCT {f.date}) > {p.c1_cur_daily_jinshen}
  ) cur
  JOIN (
    SELECT {f.reason} AS reason,
           {a.jin_shen} AS jin_shen,
           if({a.wan_shen} = 0, 0, {a.da_biao} / {a.wan_shen}) AS ratio_val
    FROM {t}
    WHERE {f.date} >= '{ctx.prev_start}' AND {f.date} <= '{ctx.prev_end}'
      {base_filter}
    GROUP BY {f.reason}
    HAVING if({a.wan_shen} = 0, 0, {a.da_biao} / {a.wan_shen}) < {p.c1_ratio_threshold}
       AND {a.jin_shen} / COUNT(DISTINCT {f.date}) > {p.c1_prev_daily_jinshen}
  ) prev ON cur.reason = prev.reason

  UNION ALL

  -- 条件二：单策略高量低效（近7天日均进审>{p.c2_daily_jinshen} 且 打标率<{p.c2_ratio_threshold}）
  SELECT reason, jin_shen, wan_shen, da_biao, data_days, ratio_val, hit_condition
  FROM (
    SELECT {f.reason} AS reason,
           {a.jin_shen} AS jin_shen,
           {a.wan_shen} AS wan_shen,
           {a.da_biao} AS da_biao,
           COUNT(DISTINCT {f.date}) AS data_days,
           if({a.wan_shen} = 0, 0, {a.da_biao} / {a.wan_shen}) AS ratio_val,
           concat('单周高量低效（近7天日均进审>', toString({p.c2_daily_jinshen}), '且打标率<', toString(round({p.c2_ratio_threshold}*100,2)), '%）') AS hit_condition
    FROM {t}
    WHERE {f.date} >= '{ctx.cur_start}' AND {f.date} <= '{ctx.cur_end}'
      {base_filter}
    GROUP BY {f.reason}
    HAVING {a.jin_shen} / COUNT(DISTINCT {f.date}) > {p.c2_daily_jinshen}
       AND if({a.wan_shen} = 0, 0, {a.da_biao} / {a.wan_shen}) < {p.c2_ratio_threshold}
  ) c2

  UNION ALL

  -- 条件三：低效策略爆量（近7天打标率<{p.c3_ratio_threshold}，上周期打标率<{p.c3_prev_ratio_threshold}，环比增长>{p.c3_growth_rate_threshold}且日均增量>{p.c3_daily_delta_threshold}）
  SELECT cur.reason AS reason,
         cur.jin_shen AS jin_shen,
         cur.wan_shen AS wan_shen,
         cur.da_biao AS da_biao,
         cur.data_days AS data_days,
         cur.ratio_val AS ratio_val,
         concat('低效策略爆量（近7天vs前7天环比增长>', toString(round({p.c3_growth_rate_threshold}*100,0)), '%且日均增量>', toString({p.c3_daily_delta_threshold}), '，双周期打标率<', toString(round({p.c3_ratio_threshold}*100,2)), '%）') AS hit_condition
  FROM (
    SELECT {f.reason} AS reason,
           {a.jin_shen} AS jin_shen,
           {a.wan_shen} AS wan_shen,
           {a.da_biao} AS da_biao,
           COUNT(DISTINCT {f.date}) AS data_days,
           if({a.wan_shen} = 0, 0, {a.da_biao} / {a.wan_shen}) AS ratio_val
    FROM {t}
    WHERE {f.date} >= '{ctx.cur_start}' AND {f.date} <= '{ctx.cur_end}'
      {base_filter}
    GROUP BY {f.reason}
    HAVING if({a.wan_shen} = 0, 0, {a.da_biao} / {a.wan_shen}) < {p.c3_ratio_threshold}
  ) cur
  JOIN (
    SELECT {f.reason} AS reason,
           {a.jin_shen} AS jin_shen,
           COUNT(DISTINCT {f.date}) AS data_days,
           if({a.wan_shen} = 0, 0, {a.da_biao} / {a.wan_shen}) AS ratio_val
    FROM {t}
    WHERE {f.date} >= '{ctx.prev_start}' AND {f.date} <= '{ctx.prev_end}'
      {base_filter}
    GROUP BY {f.reason}
    HAVING if({a.wan_shen} = 0, 0, {a.da_biao} / {a.wan_shen}) < {p.c3_prev_ratio_threshold}
  ) prev ON cur.reason = prev.reason
  WHERE prev.jin_shen / prev.data_days > {p.c3_prev_daily_guard}
    AND (cur.jin_shen / cur.data_days - prev.jin_shen / prev.data_days)
          / NULLIF(prev.jin_shen / prev.data_days, 0) > {p.c3_growth_rate_threshold}
    AND (cur.jin_shen / cur.data_days - prev.jin_shen / prev.data_days) > {p.c3_daily_delta_threshold}
)
GROUP BY reason
ORDER BY avg_wanshen DESC
LIMIT 500"""


_P0_UNION_SQL_V2 = """SELECT r AS reason,
       round(ajs) AS avg_jinshen,
       round(aws) AS avg_wanshen,
       round(adb) AS avg_dabiao,
       rv AS ratio_val,
       arrayStringConcat(arraySort(groupUniqArray(hit)), '；') AS hit_condition
FROM (
  -- 条件A：持续四周低效（严重）：近1周日均进审>{p.c1_weekly_daily_jinshen} 且 近1周打标率<{p.c1_ratio_threshold} 且 近2/3/4周打标率均<{p.c1_ratio_threshold}
  SELECT w1.reason AS r, w1.avg_js AS ajs, w1.avg_ws AS aws, w1.avg_db AS adb, w1.rv AS rv,
         concat('持续四周低效（严重）：近1周日均进审>', toString({p.c1_weekly_daily_jinshen}), '且近4周每周打标率<', toString(round({p.c1_ratio_threshold}*100,2)), '%') AS hit
  FROM (
    SELECT {f.reason} AS reason,
           {a.jin_shen} / COUNT(DISTINCT {f.date}) AS avg_js,
           {a.wan_shen} / COUNT(DISTINCT {f.date}) AS avg_ws,
           {a.da_biao} / COUNT(DISTINCT {f.date}) AS avg_db,
           if({a.wan_shen} = 0, 0, {a.da_biao} / {a.wan_shen}) AS rv
    FROM {t}
    WHERE {f.date} >= '{ctx.w1_start}' AND {f.date} <= '{ctx.w1_end}'
      {base_filter}
    GROUP BY {f.reason}
  ) w1
  JOIN (
    SELECT {f.reason} AS reason
    FROM {t}
    WHERE {f.date} >= '{ctx.w2_start}' AND {f.date} <= '{ctx.w2_end}'
      {base_filter}
    GROUP BY {f.reason}
    HAVING if({a.wan_shen} = 0, 0, {a.da_biao} / {a.wan_shen}) < {p.c1_ratio_threshold}
  ) w2 ON w1.reason = w2.reason
  JOIN (
    SELECT {f.reason} AS reason
    FROM {t}
    WHERE {f.date} >= '{ctx.w3_start}' AND {f.date} <= '{ctx.w3_end}'
      {base_filter}
    GROUP BY {f.reason}
    HAVING if({a.wan_shen} = 0, 0, {a.da_biao} / {a.wan_shen}) < {p.c1_ratio_threshold}
  ) w3 ON w1.reason = w3.reason
  JOIN (
    SELECT {f.reason} AS reason
    FROM {t}
    WHERE {f.date} >= '{ctx.w4_start}' AND {f.date} <= '{ctx.w4_end}'
      {base_filter}
    GROUP BY {f.reason}
    HAVING if({a.wan_shen} = 0, 0, {a.da_biao} / {a.wan_shen}) < {p.c1_ratio_threshold}
  ) w4 ON w1.reason = w4.reason
  WHERE w1.avg_js > {p.c1_weekly_daily_jinshen}
    AND w1.rv < {p.c1_ratio_threshold}

  UNION ALL

  -- 条件B：持续两周低效（高量）：近1周日均进审>{p.c2_daily_jinshen} 且 近1、2周打标率均<{p.c2_ratio_threshold}
  SELECT w1.reason AS r, w1.avg_js AS ajs, w1.avg_ws AS aws, w1.avg_db AS adb, w1.rv AS rv,
         concat('持续两周低效（高量）：近1周日均进审>', toString({p.c2_daily_jinshen}), '且近2周每周打标率<', toString(round({p.c2_ratio_threshold}*100,2)), '%') AS hit
  FROM (
    SELECT {f.reason} AS reason,
           {a.jin_shen} / COUNT(DISTINCT {f.date}) AS avg_js,
           {a.wan_shen} / COUNT(DISTINCT {f.date}) AS avg_ws,
           {a.da_biao} / COUNT(DISTINCT {f.date}) AS avg_db,
           if({a.wan_shen} = 0, 0, {a.da_biao} / {a.wan_shen}) AS rv
    FROM {t}
    WHERE {f.date} >= '{ctx.w1_start}' AND {f.date} <= '{ctx.w1_end}'
      {base_filter}
    GROUP BY {f.reason}
  ) w1
  JOIN (
    SELECT {f.reason} AS reason
    FROM {t}
    WHERE {f.date} >= '{ctx.w2_start}' AND {f.date} <= '{ctx.w2_end}'
      {base_filter}
    GROUP BY {f.reason}
    HAVING if({a.wan_shen} = 0, 0, {a.da_biao} / {a.wan_shen}) < {p.c2_ratio_threshold}
  ) w2 ON w1.reason = w2.reason
  WHERE w1.avg_js > {p.c2_daily_jinshen}
    AND w1.rv < {p.c2_ratio_threshold}

  UNION ALL

  -- 条件C：持续一周低效（超高量）：近1周日均进审>{p.c3_daily_jinshen} 且 近1周打标率<{p.c3_ratio_threshold}
  SELECT reason AS r, avg_js AS ajs, avg_ws AS aws, avg_db AS adb, rv AS rv,
         concat('持续一周低效（超高量）：近1周日均进审>', toString({p.c3_daily_jinshen}), '且近1周打标率<', toString(round({p.c3_ratio_threshold}*100,2)), '%') AS hit
  FROM (
    SELECT {f.reason} AS reason,
           {a.jin_shen} / COUNT(DISTINCT {f.date}) AS avg_js,
           {a.wan_shen} / COUNT(DISTINCT {f.date}) AS avg_ws,
           {a.da_biao} / COUNT(DISTINCT {f.date}) AS avg_db,
           if({a.wan_shen} = 0, 0, {a.da_biao} / {a.wan_shen}) AS rv
    FROM {t}
    WHERE {f.date} >= '{ctx.w1_start}' AND {f.date} <= '{ctx.w1_end}'
      {base_filter}
    GROUP BY {f.reason}
    HAVING {a.jin_shen} / COUNT(DISTINCT {f.date}) > {p.c3_daily_jinshen}
       AND if({a.wan_shen} = 0, 0, {a.da_biao} / {a.wan_shen}) < {p.c3_ratio_threshold}
  ) c

  UNION ALL

  -- 条件D：进审量异常爆量（近1周日均进审>上1周×(1+{p.c4_growth_rate}) 且 日均增量>{p.c4_daily_delta} 且 近1周打标率<{p.c4_ratio_threshold}；上1周仅作环比基线，不设打标率门槛）
  SELECT w1.reason AS r, w1.avg_js AS ajs, w1.avg_ws AS aws, w1.avg_db AS adb, w1.rv AS rv,
         concat('进审量异常爆量：近1周日均进审>上1周×', toString(1 + {p.c4_growth_rate}), '且日均增量>', toString({p.c4_daily_delta}), '，近1周打标率<', toString(round({p.c4_ratio_threshold}*100,2)), '%') AS hit
  FROM (
    SELECT {f.reason} AS reason,
           {a.jin_shen} / COUNT(DISTINCT {f.date}) AS avg_js,
           {a.wan_shen} / COUNT(DISTINCT {f.date}) AS avg_ws,
           {a.da_biao} / COUNT(DISTINCT {f.date}) AS avg_db,
           if({a.wan_shen} = 0, 0, {a.da_biao} / {a.wan_shen}) AS rv
    FROM {t}
    WHERE {f.date} >= '{ctx.w1_start}' AND {f.date} <= '{ctx.w1_end}'
      {base_filter}
    GROUP BY {f.reason}
    HAVING if({a.wan_shen} = 0, 0, {a.da_biao} / {a.wan_shen}) < {p.c4_ratio_threshold}
  ) w1
  JOIN (
    SELECT {f.reason} AS reason,
           {a.jin_shen} / COUNT(DISTINCT {f.date}) AS avg_js
    FROM {t}
    WHERE {f.date} >= '{ctx.w2_start}' AND {f.date} <= '{ctx.w2_end}'
      {base_filter}
    GROUP BY {f.reason}
  ) w2 ON w1.reason = w2.reason
  WHERE w2.avg_js > {p.c4_prev_daily_guard}
    AND w1.avg_js > w2.avg_js * (1 + {p.c4_growth_rate})
    AND (w1.avg_js - w2.avg_js) > {p.c4_daily_delta}
) all_hits
GROUP BY r, ajs, aws, adb, rv
ORDER BY ajs DESC
LIMIT 500"""


_P0_UNION_SPEC = {
    "version": "2.0",
    "required_params": [
        "c1_weekly_daily_jinshen", "c1_ratio_threshold",
        "c2_daily_jinshen", "c2_ratio_threshold",
        "c3_daily_jinshen", "c3_ratio_threshold",
        "c4_prev_daily_guard", "c4_growth_rate", "c4_daily_delta", "c4_ratio_threshold",
    ],
    "optional_params": {},
    "param_types": {
        "c1_weekly_daily_jinshen": "number",
        "c1_ratio_threshold": "number",
        "c2_daily_jinshen": "number",
        "c2_ratio_threshold": "number",
        "c3_daily_jinshen": "number",
        "c3_ratio_threshold": "number",
        "c4_prev_daily_guard": "number",
        "c4_growth_rate": "number",
        "c4_daily_delta": "number",
        "c4_ratio_threshold": "number",
    },
    "ctx_keys": [
        "table",
        "w1_start", "w1_end", "w2_start", "w2_end",
        "w3_start", "w3_end", "w4_start", "w4_end",
    ],
    "optional_ctx_keys": [
        "date_field", "field_map", "agg_fields",
        "quote_style", "quote_table",
        "base_filter", "use_default_base_filter",
        "cur_start", "cur_end", "prev_start", "prev_end",
        "cur_days", "prev_days",
    ],
    "sql": _P0_UNION_SQL_V2,
}


_P1_UNION_SPEC = {
    "version": "2.0",
    "required_params": [
        "c1_ratio_threshold", "c1_cur_daily_jinshen", "c1_prev_daily_jinshen",
        "c2_daily_jinshen", "c2_ratio_threshold",
        "c3_ratio_threshold", "c3_prev_ratio_threshold", "c3_prev_daily_guard",
        "c3_growth_rate_threshold", "c3_daily_delta_threshold",
    ],
    "optional_params": {},
    "param_types": {
        "c1_ratio_threshold": "number",
        "c1_cur_daily_jinshen": "number",
        "c1_prev_daily_jinshen": "number",
        "c2_daily_jinshen": "number",
        "c2_ratio_threshold": "number",
        "c3_ratio_threshold": "number",
        "c3_prev_ratio_threshold": "number",
        "c3_prev_daily_guard": "number",
        "c3_growth_rate_threshold": "number",
        "c3_daily_delta_threshold": "number",
    },
    "ctx_keys": [
        "table",
        "cur_start", "cur_end", "prev_start", "prev_end",
        "cur_days", "prev_days",
    ],
    "optional_ctx_keys": [
        "date_field", "field_map", "agg_fields",
        "quote_style", "quote_table",
        "base_filter", "use_default_base_filter",
    ],
    "sql": _P1_UNION_SQL_V2,
}


# ============================================================
# 按规则维度建设：key == 规则 ID
# ============================================================
# 每条规则独占一个 key，直接绑定一条完整 SQL（**_SPEC 里的 "sql" 字段）。渲染纯靠占位符替换，
# 不存在"公共骨架被多规则复用"的抽象——新增指标就新增一条规则 key + 一条 SQL 模板即可。
# 其余字段（level_hint / desc）仅为人读元数据，render_sql 不据此分支。

SQL_TEMPLATES: dict[str, dict[str, Any]] = {
    "rule_low_label_rate_notice": {
        "version": "2.0",
        "level_hint": "notice",
        "desc": "notice·高完审低打标：单周期 GROUP BY reason，HAVING 打标率<阈值 + 进审量>守卫，输出日均量",
        "default_params": {
            # 业务默认值（可被 sql_params 覆盖）；字段值统一使用逻辑字段名
            "ratio_field": "ratio",
            "ratio_op": "<",
            "ratio_threshold": 0.1,
            "guard_field": "jin_shen",
            "guard_op": ">",
            "guard_threshold": 0,
            "order_field": "wan_shen",  # 逻辑字段名，渲染时映射到 完审量_reviewid
        },
        **_SINGLE_PERIOD_SPEC,
    },
    "rule_low_label_rate_p1": {
        "version": "2.0",
        "level_hint": "P1",
        "desc": "P1·三条件OR：条件一(持续低效：近7天+前7天双周期日均进审>2000且打标率<3%) UNION 条件二(高量低效：近7天日均进审>5000且打标率<3%) UNION 条件三(低效爆量：近7天+前7天打标率均<10%，环比增长>30%且日均增量>5000)",
        "default_params": {
            "c1_ratio_threshold": 0.03,         # 条件一：双周期打标率 < 3%
            "c1_cur_daily_jinshen": 2000,       # 条件一：近7天日均进审 > 2000
            "c1_prev_daily_jinshen": 2000,      # 条件一：前7天日均进审 > 2000
            "c2_daily_jinshen": 5000,           # 条件二：近7天日均进审 > 5000
            "c2_ratio_threshold": 0.03,         # 条件二：打标率 < 3%
            "c3_ratio_threshold": 0.1,          # 条件三A：近7天打标率 < 10%
            "c3_prev_ratio_threshold": 0.1,     # 条件三E：前7天打标率 < 10%
            "c3_prev_daily_guard": 0,           # 条件三B：上周期日均进审 > 0
            "c3_growth_rate_threshold": 0.3,    # 条件三C：环比增长率 > 30%
            "c3_daily_delta_threshold": 5000,   # 条件三D：日均增量 > 5000
        },
        **_P1_UNION_SPEC,
    },
    "rule_low_label_rate_p2": {
        "version": "2.0",
        "level_hint": "P2",
        "desc": "P2·双条件OR：条件一(单策略低效：近7天累计进审>14000且打标率<3%) UNION 条件二(低效策略环比增长：本周期vs上周期，增长率>20%且日均增量>2000)",
        "default_params": {
            "c1_jinshen_threshold": 14000,   # 条件一：近7天累计进审量 > 14000（即日均>2000）
            "c1_ratio_threshold": 0.03,      # 条件一：打标率 < 3%
            "c2_ratio_threshold": 0.1,       # 条件二前置：打标率 < 10%（低效策略）
            "prev_daily_guard": 0,           # 条件二：上周期日均进审量 > 0
            "growth_rate_threshold": 0.2,    # 条件二：环比增长率 > 20%
            "daily_delta_threshold": 2000,   # 条件二：日均增量 > 2000
        },
        **_P2_UNION_SPEC,
    },
    "rule_low_label_rate_p0": {
        "version": "2.0",
        "level_hint": "P0",
        "desc": "P0·四条件OR（按周拆分，展示近1周日均量）：条件A(持续4周低效/严重：近1周日均进审>2000 且 近1~4周每周打标率<3%) UNION 条件B(持续2周低效/高量：近1周日均进审>5000 且 近1、2周打标率<3%) UNION 条件C(持续1周低效/超高量：近1周日均进审>10000 且 近1周打标率<3%) UNION 条件D(进审量异常爆量：近1周日均进审>上1周×1.5 且 日均增量>10000 且 近1周打标率<10%；上1周仅作环比基线)；打标率=打标量/完审量",
        "default_params": {
            "c1_weekly_daily_jinshen": 2000,   # 条件A：近1周日均进审 > 2000（w2/w3/w4 只校验打标率）
            "c1_ratio_threshold": 0.03,        # 条件A：近1~4周每周打标率 < 3%
            "c2_daily_jinshen": 5000,          # 条件B：近1周日均进审 > 5000
            "c2_ratio_threshold": 0.03,        # 条件B：近1、2周打标率 < 3%
            "c3_daily_jinshen": 10000,         # 条件C：近1周日均进审 > 10000
            "c3_ratio_threshold": 0.03,        # 条件C：近1周打标率 < 3%
            "c4_prev_daily_guard": 0,          # 条件D：上1周日均进审 > 0（防除零基线）
            "c4_growth_rate": 0.5,             # 条件D：近1周 > 上1周 ×1.5（增长50%）
            "c4_daily_delta": 10000,           # 条件D：日均增量 > 10000
            "c4_ratio_threshold": 0.10,        # 条件D：近1周打标率 < 10%（上1周不设门槛）
        },
        **_P0_UNION_SPEC,
    },
}


# ============================================================
# 异常
# ============================================================

class TemplateError(ValueError):
    """模板键不存在、参数缺失/类型错、或渲染时占位符未填满时抛出。"""


# ============================================================
# 校验工具
# ============================================================

def _is_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        try:
            float(value)
            return True
        except ValueError:
            return False
    return False


def _validate_logical_field(name: str, field_map: dict[str, str], where: str) -> None:
    """校验逻辑字段名合法且在 field_map 中。"""
    if not isinstance(name, str) or not _IDENT_RE.match(name):
        raise TemplateError(f"{where}={name!r} 不是安全标识符（仅允许中文/字母/数字/下划线）")
    if name not in field_map:
        raise TemplateError(
            f"{where}={name!r} 不在 field_map 中，可用逻辑字段：{sorted(field_map)}"
        )


# ============================================================
# 渲染核心
# ============================================================

# 骨架里 {f.xxx} 的引用：xxx 是逻辑字段名（普通字段，可套 SUM）
_FIELD_REF_RE = re.compile(r"\{f\.([\w]+)\}")
# {a.xxx} 的引用：xxx 是逻辑字段名（聚合字段，直接引用，不套 SUM）
_AGG_REF_RE = re.compile(r"\{a\.([\w]+)\}")
# {t} 表名占位
_TABLE_REF_RE = re.compile(r"\{t\}")
# {div_expr} 日均除法占位（单周期骨架里的统一除数：/ COUNT(DISTINCT dt) 或空串）
_DIV_EXPR_RE = re.compile(r"\{div_expr\}")
# {guard_real} 单周期 HAVING 守卫字段（外层子查询别名，如 jin_shen）
_GUARD_REAL_RE = re.compile(r"\{guard_real\}")
# {order_real} 单周期 ORDER BY 字段（外层子查询别名，如 avg_wanshen / ratio_val）
_ORDER_REAL_RE = re.compile(r"\{order_real\}")
# {base_filter} 占位
_BASE_FILTER_RE = re.compile(r"\{base_filter\}")
# {f.order} 单周期 ORDER BY 字段（由 p.order_field 决定）
_ORDER_REF_RE = re.compile(r"\{f\.order\}")
# {f.metric} 双周期 metric 字段（由 p.metric_field 决定）
_METRIC_REF_RE = re.compile(r"\{f\.metric\}")


def _resolve_ctx(ctx: dict[str, Any]) -> dict[str, Any]:
    """应用默认值，返回解析后的 ctx 副本。"""
    out = dict(ctx)
    out.setdefault("date_field", "p_date")
    out.setdefault("cur_days", 7)
    out.setdefault("prev_days", 7)
    out.setdefault("field_map", dict(_DEFAULT_FIELD_MAP))
    out.setdefault("agg_fields", set(_DEFAULT_AGG_FIELDS))
    out.setdefault("quote_style", "bracket")  # v2.2 默认 bracket（`[Name]` 语义字段占位符，物理表 FROM 下由风神服务端展开）
    out.setdefault("quote_table", False)  # 物理表 db.table 含点，裸写；逻辑数据集名才需反引号
    out.setdefault("divide_by_days", True)
    out.setdefault("use_default_base_filter", False)
    # base_filter 默认 None → 由 use_default_base_filter 决定
    return out


def _resolve_params(sql_key: str, params: dict[str, Any]) -> dict[str, Any]:
    """合并 default_params，返回参数副本。"""
    tpl = SQL_TEMPLATES[sql_key]
    out: dict[str, Any] = {}
    # 先填默认值
    for k, v in tpl.get("default_params", {}).items():
        out[k] = v
    # 再用传入值覆盖
    out.update(params)
    return out


def validate_params(sql_key: str, params: dict[str, Any], ctx: dict[str, Any] | None = None,
                    use_defaults: bool = True) -> None:
    """校验 sql_params 是否满足该规则模板声明。不通过则抛 TemplateError（编排层转人工，不告警）。

    v2.0 新增：ctx 参数用于校验 logical_field 类型字段是否在 field_map 中。
    若 ctx 为 None，仅做基础类型校验（logical_field 退化为 ident 校验）。
    use_defaults=False 时不合并 default_params（用于测试"缺参"场景）。
    """
    tpl = SQL_TEMPLATES.get(sql_key)
    if tpl is None:
        raise TemplateError(f"未知 sql_key: {sql_key!r}，可选：{sorted(SQL_TEMPLATES)}")

    if use_defaults:
        params = _resolve_params(sql_key, params)
    rctx = _resolve_ctx(ctx or {})
    field_map: dict[str, str] = rctx["field_map"]

    required = tpl["required_params"]
    missing = [k for k in required if k not in params]
    if missing:
        raise TemplateError(f"{sql_key} 缺少必填参数：{missing}")

    for key, ptype in tpl["param_types"].items():
        if key not in params:
            # optional_params 里有默认值的已被 _resolve_params 填上；这里仍缺失则跳过
            continue
        val = params[key]
        if ptype == "number":
            if not _is_number(val):
                raise TemplateError(f"参数 {key}={val!r} 必须是数字")
        elif ptype == "op":
            if str(val) not in _ALLOWED_OPS:
                raise TemplateError(f"参数 {key}={val!r} 不是合法算子，可选：{sorted(_ALLOWED_OPS)}")
        elif ptype == "string":
            if not isinstance(val, str) or not val:
                raise TemplateError(f"参数 {key}={val!r} 必须是非空字符串")
        elif ptype == "ident":
            if not isinstance(val, str) or not _IDENT_RE.match(val):
                raise TemplateError(f"参数 {key}={val!r} 不是安全标识符")
        elif ptype == "logical_field":
            _validate_logical_field(str(val), field_map, f"参数 {key}")
        elif ptype == "outer_alias":
            if not isinstance(val, str) or not re.match(r"^[A-Za-z0-9_]+$", val):
                raise TemplateError(f"参数 {key}={val!r} 不是安全别名（仅允许字母/数字/下划线）")
            if val not in _DUAL_OUTER_ALIASES:
                raise TemplateError(
                    f"参数 {key}={val!r} 不在环比外层别名白名单 {sorted(_DUAL_OUTER_ALIASES)} 内"
                    "（排序对象必须是外层已计算列，而非数据集字段）"
                )
        elif ptype == "filter_clause":
            # v2 放宽：允许空串或 AND 开头的安全子句（字段名不再强制 [] 包裹）
            if not isinstance(val, str):
                raise TemplateError(f"参数 {key} 必须是字符串")
            if val and not val.lstrip().startswith("AND"):
                raise TemplateError(f"参数 {key}={val!r} 必须以 AND 开头（或为空串）")
        else:  # pragma: no cover
            raise TemplateError(f"模板 {sql_key} 参数 {key} 的类型声明 {ptype!r} 非法")

    # ctx 基础校验
    if "table" not in rctx or not rctx["table"]:
        raise TemplateError(f"{sql_key} ctx.table 不能为空")
    date_field = rctx.get("date_field", "p_date")
    if not _IDENT_RE.match(str(date_field)):
        raise TemplateError(f"ctx.date_field={date_field!r} 不是安全标识符")
    if rctx["quote_style"] not in _QUOTE_STYLES:
        raise TemplateError(f"ctx.quote_style={rctx['quote_style']!r} 非法，可选：{sorted(_QUOTE_STYLES)}")


def render_sql(sql_key: str, params: dict[str, Any], ctx: dict[str, Any]) -> str:
    """校验并渲染 SQL。先 validate_params，再把骨架渲染成最终 SQL。

    v2.0 渲染流程：
    1. 合并 default_params / 默认 ctx；
    2. validate_params 全量校验；
    3. 解析 base_filter（结构化 list 或 SQL 字符串）；
    4. 替换骨架里的 {f.xxx} / {t} / {div_xxx} / {base_filter} / {f.order} / {f.metric}；
    5. 替换 {p.xxx} / {ctx.xxx} 普通占位符；
    6. 检查无残留占位符，返回 SQL。
    """
    if sql_key not in SQL_TEMPLATES:
        raise TemplateError(f"未知 sql_key: {sql_key!r}，可选：{sorted(SQL_TEMPLATES)}")

    params = _resolve_params(sql_key, params)
    ctx = _resolve_ctx(ctx)
    validate_params(sql_key, params, ctx)
    tpl = SQL_TEMPLATES[sql_key]

    field_map: dict[str, str] = ctx["field_map"]
    quote_style: str = ctx["quote_style"]

    # ---- 3. base_filter 解析 ----
    base_filter_raw = ctx.get("base_filter")
    if base_filter_raw is None and ctx.get("use_default_base_filter"):
        base_filter_raw = _DEFAULT_BASE_FILTER_LOW_LABEL
    base_filter_sql = _build_base_filter(base_filter_raw, field_map, quote_style)

    # ---- 4. 构造替换字典 ----
    # date 字段走 ctx.date_field（可能被覆盖）
    effective_field_map = dict(field_map)
    effective_field_map["date"] = ctx["date_field"]

    # 4a. 字段引用工具：logical 是逻辑字段名，real 是真实字段名（已映射）
    def _q_logical(logical: str) -> str:
        """按逻辑字段名加引用。"""
        if logical not in field_map and logical not in effective_field_map:
            raise TemplateError(f"逻辑字段 {logical!r} 不在 field_map 中")
        real = effective_field_map.get(logical, field_map.get(logical, logical))
        return _quote_ident(real, quote_style)

    def _q_real(real: str) -> str:
        """按真实字段名加引用（不做映射）。"""
        return _quote_ident(real, quote_style)

    def _quoted(real: str) -> str:
        """兼容旧 {p.xxx} 占位符路径：按真实字段名和当前 quote_style 加引用。"""
        return _quote_ident(real, quote_style)

    def _is_agg(logical: str) -> bool:
        """判断逻辑字段是否为聚合字段（数据集已定义聚合表达式，不可二次聚合）。"""
        return logical in ctx["agg_fields"]

    def _agg_expr(logical: str) -> str:
        """返回聚合表达式：聚合字段直接引用，普通字段套 SUM。"""
        real = effective_field_map.get(logical, field_map.get(logical, logical))
        quoted = _quote_ident(real, quote_style)
        if _is_agg(logical):
            return quoted
        return f"SUM({quoted})"

    # 4b. 表名
    table_sql = _quote_table(ctx["table"], bool(ctx["quote_table"]))

    # 4c. 日均除数表达式：用 COUNT(DISTINCT dt) 动态计算实际有数据天数，而非硬编码 /7
    if ctx["divide_by_days"]:
        div_sql = " / COUNT(DISTINCT dt)"
    else:
        div_sql = ""

    # 4d. order / metric / guard 字段（由参数决定）
    order_logical = str(params.get("order_field", "wan_shen"))
    metric_logical = str(params.get("metric_field", "jin_shen"))
    guard_logical = str(params.get("guard_field", "jin_shen"))

    # 外层子查询别名映射（逻辑字段名 → 内层子查询输出的列名）
    _OUTER_ALIAS_MAP = {
        "jin_shen": "jin_shen",
        "wan_shen": "wan_shen",
        "da_biao": "da_biao",
        "ratio": "ratio_val",
    }
    # guard 在 HAVING 中用 SUM(内层别名)，因为外层 GROUP BY reason 后需要再聚合
    guard_inner = _OUTER_ALIAS_MAP.get(guard_logical, guard_logical)
    guard_real_sql = f"{guard_inner}"
    # order 在外层 SELECT 中已有别名：avg_jinshen/avg_wanshen/avg_dabiao/ratio_val
    order_alias_map = {
        "jin_shen": "avg_jinshen",
        "wan_shen": "avg_wanshen",
        "da_biao": "avg_dabiao",
        "ratio": "ratio_val",
    }
    order_real_sql = order_alias_map.get(order_logical, "avg_wanshen")

    # ---- 5. 逐阶段替换骨架 ----
    sql = tpl["sql"]

    # 先替换 {f.xxx}（普通字段引用，仅加引号）
    def _sub_field(match: re.Match) -> str:
        logical = match.group(1)
        return _q_logical(logical)

    # 替换 {a.xxx}（聚合字段引用：聚合字段直接引用，普通字段套 SUM）
    def _sub_agg(match: re.Match) -> str:
        logical = match.group(1)
        return _agg_expr(logical)

    # 注意：{f.order} 和 {f.metric} 单独处理，先把它们替换为真实引用
    metric_real = field_map.get(metric_logical, metric_logical)
    sql = _METRIC_REF_RE.sub(lambda m: _q_real(metric_real), sql)
    sql = _AGG_REF_RE.sub(_sub_agg, sql)
    sql = _FIELD_REF_RE.sub(_sub_field, sql)

    # 表名
    sql = _TABLE_REF_RE.sub(table_sql.replace("\\", "\\\\"), sql)

    # 日均除法
    sql = _DIV_EXPR_RE.sub(div_sql, sql)

    # guard / order 外层别名
    sql = _GUARD_REAL_RE.sub(guard_real_sql, sql)
    sql = _ORDER_REAL_RE.sub(order_real_sql, sql)

    # base_filter
    sql = _BASE_FILTER_RE.sub(base_filter_sql, sql)

    # 清理旧的 {f.order} 占位符（若骨架中仍有残留，替换为 order_real_sql）
    sql = _ORDER_REF_RE.sub(order_real_sql, sql)

    # ---- 6. 替换 {p.xxx} / {ctx.xxx} ----
    # 构造合并字典（p 优先用 params，ctx 用 ctx；注意 p 里的 ratio_field 等 logical_field 已在骨架里通过 {f.xxx} 处理，
    # 但为了兼容旧占位符，仍把它们的"真实引用名"放进 p 里——v2 骨架已不直接用 {p.ratio_field}）
    merged: dict[str, str] = {}
    for k, v in params.items():
        if k in ("ratio_field", "guard_field", "order_field", "metric_field"):
            # 这些是逻辑字段名，若骨架里直接引用 {p.k}，替换为真实引用
            if k in field_map:
                merged[k] = _quoted(field_map[k])
            else:
                merged[k] = str(v)
        else:
            merged[k] = str(v)
    for k, v in ctx.items():
        if k in ("field_map", "agg_fields"):
            continue  # 不直接拼入 SQL
        merged[k] = str(v)

    def _sub_token(match: re.Match) -> str:
        ns, key = match.group(1), match.group(2)
        source = params if ns == "p" else ctx
        if key in ("field_map", "agg_fields"):
            raise TemplateError(f"占位符 {{{ns}.{key}}} 不应直接出现在 SQL 中")
        if key not in source:
            raise TemplateError(f"占位符 {{{ns}.{key}}} 无对应取值")
        val = source[key]
        # 对 logical_field 类型的 p 参数，输出真实引用
        if ns == "p":
            ptypes = tpl["param_types"]
            if key in ptypes and ptypes[key] == "logical_field" and isinstance(val, str) and val in field_map:
                return _quoted(field_map[val])
        return str(val)

    sql = _TOKEN_RE.sub(_sub_token, sql)

    # ---- 7. 残留检查 ----
    leftover_tokens = _TOKEN_RE.findall(sql)
    leftover_field = _FIELD_REF_RE.findall(sql)
    leftover_agg = _AGG_REF_RE.findall(sql)
    leftover_table = _TABLE_REF_RE.findall(sql)
    leftover_div = _DIV_EXPR_RE.findall(sql)
    leftover_guard = _GUARD_REAL_RE.findall(sql)
    leftover_order = _ORDER_REAL_RE.findall(sql)
    leftover_bf = _BASE_FILTER_RE.findall(sql)
    if leftover_tokens or leftover_field or leftover_agg or leftover_table or leftover_div or leftover_guard or leftover_order or leftover_bf:
        raise TemplateError(
            f"渲染后仍有未填占位符：tokens={leftover_tokens}, fields={leftover_field}, "
            f"aggs={leftover_agg}, table={leftover_table}, div={leftover_div}, guard={leftover_guard}, "
            f"order={leftover_order}, base_filter={leftover_bf}"
        )

    return sql.strip()


# ============================================================
# 便捷：构造 notice 规则默认 ctx（针对数据集 3888816）
# ============================================================

def build_notice_ctx(
    table: str = "olap_content_security_community.dws_sft_tcs_review_task_detail_di",
    cur_start: str = "2026-06-25",
    cur_end: str = "2026-07-01",
    cur_days: int = 7,
    quote_style: str = "bracket",
    use_default_base_filter: bool = True,
    base_filter: list[dict] | str | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    """构造 rule_low_label_rate_notice 的标准 ctx（数据集 3888816 社区人工审核明细）。

    使用方式：
        ctx = build_notice_ctx(cur_start="2026-06-25", cur_end="2026-07-01")
        sql = render_sql("rule_low_label_rate_notice", {}, ctx)

    自定义阈值：
        sql = render_sql("rule_low_label_rate_notice", {
            "ratio_threshold": 0.05, "guard_threshold": 100,
        }, ctx)
    """
    ctx: dict[str, Any] = {
        "table": table,
        "date_field": "p_date",  # 物理字段名（UI 显示名/别名为「日期」）
        "cur_start": cur_start,
        "cur_end": cur_end,
        "cur_days": cur_days,
        "quote_style": quote_style,
        "quote_table": False,
        "divide_by_days": True,
        "field_map": dict(_DEFAULT_FIELD_MAP),
        "agg_fields": set(_DEFAULT_AGG_FIELDS),
        "use_default_base_filter": use_default_base_filter,
    }
    if base_filter is not None:
        ctx["base_filter"] = base_filter
        ctx["use_default_base_filter"] = False
    ctx.update(overrides)
    return ctx


def build_p1_ctx(
    table: str = "olap_content_security_community.dws_sft_tcs_review_task_detail_di",
    cur_start: str = "2026-06-25",
    cur_end: str = "2026-07-01",
    prev_start: str = "2026-06-18",
    prev_end: str = "2026-06-24",
    cur_days: int = 7,
    prev_days: int = 7,
    quote_style: str = "bracket",
    use_default_base_filter: bool = True,
    base_filter: list[dict] | str | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    """构造 rule_low_label_rate_p1 的标准 ctx（数据集 3888816 社区人工审核明细）。"""
    ctx: dict[str, Any] = {
        "table": table,
        "date_field": "p_date",
        "cur_start": cur_start,
        "cur_end": cur_end,
        "prev_start": prev_start,
        "prev_end": prev_end,
        "cur_days": cur_days,
        "prev_days": prev_days,
        "quote_style": quote_style,
        "quote_table": False,
        "field_map": dict(_DEFAULT_FIELD_MAP),
        "agg_fields": set(_DEFAULT_AGG_FIELDS),
        "use_default_base_filter": use_default_base_filter,
    }
    if base_filter is not None:
        ctx["base_filter"] = base_filter
        ctx["use_default_base_filter"] = False
    ctx.update(overrides)
    return ctx


def build_p0_ctx(
    table: str = "olap_content_security_community.dws_sft_tcs_review_task_detail_di",
    w1_start: str = "2026-06-25",
    w1_end: str = "2026-07-01",
    w2_start: str = "2026-06-18",
    w2_end: str = "2026-06-24",
    w3_start: str = "2026-06-11",
    w3_end: str = "2026-06-17",
    w4_start: str = "2026-06-04",
    w4_end: str = "2026-06-10",
    quote_style: str = "bracket",
    use_default_base_filter: bool = True,
    base_filter: list[dict] | str | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    """构造 rule_low_label_rate_p0 的标准 ctx（数据集 3888816 社区人工审核明细）。

    P0 按周拆分窗口：w1=近7天, w2=前7天, w3=前前7天, w4=前前前7天（共28天）。
    同时兼容 cur/prev 别名（cur=w1, prev=w2），方便编排层统一传参。
    打标率口径：打标量/完审量。
    """
    ctx: dict[str, Any] = {
        "table": table,
        "date_field": "p_date",
        # 4 个周窗口
        "w1_start": w1_start, "w1_end": w1_end,
        "w2_start": w2_start, "w2_end": w2_end,
        "w3_start": w3_start, "w3_end": w3_end,
        "w4_start": w4_start, "w4_end": w4_end,
        # 兼容 cur/prev 别名（cur=w1 近7天, prev=w2 前7天）
        "cur_start": w1_start, "cur_end": w1_end,
        "prev_start": w2_start, "prev_end": w2_end,
        "cur_days": 7, "prev_days": 7,
        "quote_style": quote_style,
        "quote_table": False,
        "field_map": dict(_DEFAULT_FIELD_MAP),
        "agg_fields": set(_DEFAULT_AGG_FIELDS),
        "use_default_base_filter": use_default_base_filter,
    }
    if base_filter is not None:
        ctx["base_filter"] = base_filter
        ctx["use_default_base_filter"] = False
    ctx.update(overrides)
    return ctx


def build_p2_ctx(
    table: str = "olap_content_security_community.dws_sft_tcs_review_task_detail_di",
    cur_start: str = "2026-06-25",
    cur_end: str = "2026-07-01",
    prev_start: str = "2026-06-18",
    prev_end: str = "2026-06-24",
    cur_days: int = 7,
    prev_days: int = 7,
    quote_style: str = "bracket",
    use_default_base_filter: bool = True,
    base_filter: list[dict] | str | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    """构造 rule_low_label_rate_p2 的标准 ctx（数据集 3888816 社区人工审核明细）。

    使用方式：
        ctx = build_p2_ctx()
        sql = render_sql("rule_low_label_rate_p2", {}, ctx)
    """
    ctx: dict[str, Any] = {
        "table": table,
        "date_field": "p_date",
        "cur_start": cur_start,
        "cur_end": cur_end,
        "prev_start": prev_start,
        "prev_end": prev_end,
        "cur_days": cur_days,
        "prev_days": prev_days,
        "quote_style": quote_style,
        "quote_table": False,
        "field_map": dict(_DEFAULT_FIELD_MAP),
        "agg_fields": set(_DEFAULT_AGG_FIELDS),
        "use_default_base_filter": use_default_base_filter,
    }
    if base_filter is not None:
        ctx["base_filter"] = base_filter
        ctx["use_default_base_filter"] = False
    ctx.update(overrides)
    return ctx


if __name__ == "__main__":
    # 本地冒烟测试：依次渲染 notice/P2/P1/P0 规则默认 SQL
    import sys
    for key, builder in [
        ("rule_low_label_rate_notice", build_notice_ctx),
        ("rule_low_label_rate_p2", build_p2_ctx),
        ("rule_low_label_rate_p1", build_p1_ctx),
        ("rule_low_label_rate_p0", build_p0_ctx),
    ]:
        ctx = builder()
        sql = render_sql(key, {}, ctx)
        print(f"-- {key} ({len(sql)} chars) --")
        if "--verbose" in sys.argv:
            print(sql)
    print("\n-- OK --")
