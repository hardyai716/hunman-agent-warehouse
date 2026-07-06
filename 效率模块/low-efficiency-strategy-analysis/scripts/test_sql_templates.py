#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sql_templates.py v2.1 单元测试（动态天数版）。覆盖：
1. notice 规则默认渲染（双层聚合 + COUNT(DISTINCT dt) 动态日均）
2. 自定义阈值渲染
3. bracket 引用风格
4. 结构化 base_filter 渲染
5. 字符串 base_filter 向后兼容
6. 不除日均（divide_by_days=False）
7. 参数校验：缺失参数、非法算子、非法字段
8. P1/P2 双周期骨架渲染
9. 字段映射覆盖
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import sql_templates as st


def test_notice_default_render():
    """notice 默认 ctx 应渲染出正确 SQL（bracket 语义字段、物理表、默认过滤、动态日均除法）。"""
    ctx = st.build_notice_ctx()
    sql = st.render_sql("rule_low_label_rate_notice", {}, ctx)
    assert "`[reason]`" in sql, "应使用 `[Name]` 语义字段占位符包裹 reason"
    assert "`[p_date]`" in sql, "分区字段应为 `[p_date]` 语义占位符"
    assert "/ COUNT(DISTINCT dt)" in sql, "应使用 COUNT(DISTINCT dt) 动态计算日均，而非硬编码 /7"
    assert "SUM(da_biao) / SUM(wan_shen)" in sql, "外层打标率应由 SUM(打标)/SUM(完审) 计算（分母是完审量）"
    assert "SUM(jin_shen) > 0" in sql, "默认守卫进审量>0（外层 SUM 聚合）"
    assert "ORDER BY avg_wanshen DESC" in sql, "默认按 avg_wanshen 降序（外层别名）"
    assert "`[project_title]` NOT LIKE '%虚假%'" in sql, "默认过滤应包含标题黑名单"
    assert "`[scene]` IN (" in sql, "默认过滤应包含场景白名单"
    assert "(`[机审一级标签]` IS NULL OR `[机审一级标签]` IN (" in sql, "默认过滤应包含机审一级标签"
    assert "FROM olap_content_security_community.dws_sft_tcs_review_task_detail_di" in sql, "表名应为裸写物理表（db.table 含点不加反引号）"
    assert "GROUP BY `[reason]`, `[p_date]`" in sql, "内层应按 reason+date 聚合"
    assert "concat('打标率偏低（近7天打标率<" in sql, "命中条件应为动态文本描述而非单字母 A"
    assert "'A' AS hit_condition" not in sql, "notice 不应再输出裸标记 A"
    print("✅ test_notice_default_render passed")


def test_notice_custom_threshold():
    """自定义阈值应正确覆盖默认值。"""
    ctx = st.build_notice_ctx()
    sql = st.render_sql("rule_low_label_rate_notice", {
        "ratio_threshold": 0.05,
        "guard_threshold": 100,
        "guard_op": ">",
    }, ctx)
    assert "SUM(da_biao) / SUM(wan_shen)) < 0.05" in sql, "自定义打标率阈值 0.05"
    assert "SUM(jin_shen) > 100" in sql, "自定义守卫进审量>100"
    print("✅ test_notice_custom_threshold passed")


def test_bracket_quote_style():
    """bracket 引用风格应输出 `[Name]` 语义字段占位符。"""
    ctx = st.build_notice_ctx(quote_style="bracket")
    sql = st.render_sql("rule_low_label_rate_notice", {}, ctx)
    assert "`[reason]`" in sql
    assert "`[p_date]`" in sql
    assert "/ COUNT(DISTINCT dt)" in sql, "bracket 风格也应使用动态天数"
    print("✅ test_bracket_quote_style passed")


def test_backtick_quote_style():
    """backtick 引用风格（物理列裸名，需重建指标场景）应输出 `Name` 形式。"""
    ctx = st.build_notice_ctx(quote_style="backtick")
    sql = st.render_sql("rule_low_label_rate_notice", {}, ctx)
    assert "`reason`" in sql and "`[reason]`" not in sql, "backtick 风格不应带方括号"
    assert "`p_date`" in sql
    print("✅ test_backtick_quote_style passed")


def test_structured_base_filter():
    """自定义结构化 base_filter 应正确渲染。"""
    ctx = st.build_notice_ctx(
        use_default_base_filter=False,
        base_filter=[
            {"field": "scene", "op": "in", "values": ["community_audit_safe"]},
            {"field": "reason", "op": "like", "value": "%test%", "negate": True},
        ],
    )
    sql = st.render_sql("rule_low_label_rate_notice", {}, ctx)
    assert "`[scene]` IN ('community_audit_safe')" in sql
    assert "`[reason]` NOT LIKE '%test%'" in sql
    # 默认过滤不应出现
    assert "`[project_title]` NOT LIKE" not in sql
    print("✅ test_structured_base_filter passed")


def test_string_base_filter_backward_compat():
    """字符串 base_filter 应向后兼容（直接拼入）。"""
    ctx = st.build_notice_ctx(
        use_default_base_filter=False,
        base_filter="AND `送审原因` = 'xxx'",
    )
    sql = st.render_sql("rule_low_label_rate_notice", {}, ctx)
    assert "AND `送审原因` = 'xxx'" in sql
    print("✅ test_string_base_filter_backward_compat passed")


def test_no_divide_by_days():
    """divide_by_days=False 时不应除以天数（输出周期总量）。"""
    ctx = st.build_notice_ctx(divide_by_days=False)
    sql = st.render_sql("rule_low_label_rate_notice", {}, ctx)
    assert "SUM(jin_shen) AS avg_jinshen" in sql, "不除天数时直接 AS avg_jinshen"
    assert "/ COUNT(DISTINCT dt)" not in sql, "不应有除法"
    print("✅ test_no_divide_by_days passed")


def test_validate_missing_param():
    """缺失必填参数应抛 TemplateError。"""
    ctx = st.build_notice_ctx()
    try:
        st.validate_params("rule_low_label_rate_notice", {
            "ratio_op": "<", "ratio_threshold": 0.1,
            # ratio_field 缺失
            "guard_field": "jin_shen", "guard_op": ">", "guard_threshold": 0,
            "order_field": "wan_shen",
        }, ctx, use_defaults=False)
        assert False, "应抛异常"
    except st.TemplateError as e:
        assert "ratio_field" in str(e)
    print("✅ test_validate_missing_param passed")


def test_validate_bad_op():
    """非法算子应抛 TemplateError。"""
    ctx = st.build_notice_ctx()
    try:
        st.validate_params("rule_low_label_rate_notice", {
            "ratio_field": "ratio", "ratio_op": "DROP", "ratio_threshold": 0.1,
            "guard_field": "jin_shen", "guard_op": ">", "guard_threshold": 0,
            "order_field": "wan_shen",
        }, ctx)
        assert False, "应抛异常"
    except st.TemplateError as e:
        assert "DROP" in str(e)
    print("✅ test_validate_bad_op passed")


def test_validate_unknown_logical_field():
    """逻辑字段名不在 field_map 中应抛异常。"""
    ctx = st.build_notice_ctx()
    try:
        st.validate_params("rule_low_label_rate_notice", {
            "ratio_field": "not_exist_field", "ratio_op": "<", "ratio_threshold": 0.1,
            "guard_field": "jin_shen", "guard_op": ">", "guard_threshold": 0,
            "order_field": "wan_shen",
        }, ctx)
        assert False, "应抛异常"
    except st.TemplateError as e:
        assert "not_exist_field" in str(e)
    print("✅ test_validate_unknown_logical_field passed")


def test_p1_dual_period_render():
    """P1 三条件 UNION 骨架应正确渲染，使用 data_days 动态天数。"""
    ctx = st.build_p1_ctx()
    sql = st.render_sql("rule_low_label_rate_p1", {}, ctx)
    assert sql.count("UNION ALL") == 2
    assert "'双周持续低效" in sql and "'单周高量低效" in sql and "'低效策略爆量" in sql
    assert "arrayStringConcat(arraySort(groupUniqArray(hit_condition))" in sql
    assert "COUNT(DISTINCT `[p_date]`) AS data_days" in sql, "应使用 COUNT(DISTINCT [p_date]) 动态计算天数"
    assert "max(data_days)" in sql, "外层日均应使用动态 data_days，而非硬编码 /7"
    assert "max(jin_shen) / max(data_days) AS avg_jinshen" in sql, \
        "P1 外层指标应只取当前周期唯一值，不能按命中条件重复 SUM"
    assert "SUM(jin_shen) / data_days AS avg_jinshen" not in sql, \
        "P1 多条件命中时外层 SUM 会导致日均量翻倍"
    assert "GROUP BY reason, data_days" not in sql, "P1 外层应仅按 reason 去重合并命中条件"
    assert "NULLIF(prev.jin_shen / prev.data_days, 0)" in sql, "环比应防除零（基于日均）"
    assert "ORDER BY avg_wanshen DESC" in sql
    print("✅ test_p1_dual_period_render passed")


def test_field_map_override():
    """自定义 field_map 应覆盖默认映射。"""
    ctx = st.build_notice_ctx()
    ctx["field_map"] = {
        **st._DEFAULT_FIELD_MAP,
        "reason": "strategy_name",  # 覆盖 reason 映射
    }
    sql = st.render_sql("rule_low_label_rate_notice", {}, ctx)
    assert "`[strategy_name]`" in sql
    assert "`[reason]`" not in sql
    print("✅ test_field_map_override passed")


def test_unknown_sql_key():
    """未知 sql_key 应抛异常。"""
    try:
        st.render_sql("not_exist_key", {}, st.build_notice_ctx())
        assert False
    except st.TemplateError as e:
        assert "未知 sql_key" in str(e)
    print("✅ test_unknown_sql_key passed")


def test_is_null_filter():
    """is_null / is_not_null 过滤应正确渲染。"""
    ctx = st.build_notice_ctx(
        use_default_base_filter=False,
        base_filter=[
            {"field": "mach_root_label_name", "op": "is_null"},
            {"field": "project_title", "op": "is_null", "negate": True},
        ],
    )
    sql = st.render_sql("rule_low_label_rate_notice", {}, ctx)
    assert "`[机审一级标签]` IS NULL" in sql
    assert "`[project_title]` IS NOT NULL" in sql
    print("✅ test_is_null_filter passed")


def test_p1_default_render():
    """P1 默认渲染：三条件 UNION，应包含三个子查询 + 外层聚合，使用动态天数。"""
    ctx = st.build_p1_ctx()
    sql = st.render_sql("rule_low_label_rate_p1", {}, ctx)
    assert sql.count("UNION ALL") == 2, "P1 应包含 2 个 UNION ALL（三条件）"
    assert "'双周持续低效" in sql
    assert "'单周高量低效" in sql
    assert "'低效策略爆量" in sql
    assert "arrayStringConcat(arraySort(groupUniqArray(hit_condition))" in sql
    assert "> 2000" in sql, "条件一日均阈值"
    assert "> 5000" in sql, "条件二日均阈值"
    assert "> 0.3" in sql, "条件三增长率阈值"
    # 条件三A+E：本周期和上周期都应有打标率<10%（用 if+SUM 形式，分母完审量）
    assert sql.count(") < 0.1") >= 2, "条件三A+E：本周期和上周期都应打标率<10%"
    # 条件三D：日均增量应为 cur/data_days - prev/data_days
    assert "cur.jin_shen / cur.data_days - prev.jin_shen / prev.data_days" in sql, \
        "条件三D应为基于动态天数的日均差"
    assert "COUNT(DISTINCT `[p_date]`)" in sql, "应使用 COUNT(DISTINCT [p_date]) 而非硬编码 7"
    print("✅ test_p1_default_render passed")


def test_p1_custom_threshold():
    """P1 自定义阈值应生效。"""
    ctx = st.build_p1_ctx()
    sql = st.render_sql("rule_low_label_rate_p1", {
        "c2_daily_jinshen": 8000,
        "c3_growth_rate_threshold": 0.5,
        "c3_prev_ratio_threshold": 0.05,
    }, ctx)
    assert "> 8000" in sql
    assert "> 0.5" in sql
    # 自定义上周期打标率阈值 0.05，应出现在 prev 子查询的 HAVING 中
    assert ") < 0.05" in sql, "c3_prev_ratio_threshold=0.05 应生效"
    print("✅ test_p1_custom_threshold passed")


def test_p2_default_render():
    """P2 默认渲染：双条件 UNION，应包含两个子查询 + 外层聚合，使用动态天数。"""
    ctx = st.build_p2_ctx()
    sql = st.render_sql("rule_low_label_rate_p2", {}, ctx)
    assert "UNION ALL" in sql, "P2 应包含 UNION ALL"
    assert "'单策略低效" in sql, "应标记条件一（单策略低效）"
    assert "'进审量异常上涨" in sql, "应标记条件二（进审量异常上涨）"
    assert "arrayStringConcat(arraySort(groupUniqArray(hit_condition))" in sql, "外层应合并命中条件（排序去重）"
    assert "`[p_date]` >= '2026-06-25'" in sql, "本周期分区"
    assert "`[p_date]` >= '2026-06-18'" in sql, "上周期分区"
    assert "`[进审量_reviewid]` > 14000" in sql, "条件一进审量阈值（聚合字段直接引用）"
    assert ") < 0.03" in sql, "条件一打标率阈值（if+SUM 形式，分母完审量）"
    assert "> 0.2" in sql, "条件二增长率阈值"
    assert "> 2000" in sql, "条件二日均增量阈值"
    assert "COUNT(DISTINCT `[p_date]`) AS data_days" in sql, "应使用 COUNT(DISTINCT [p_date])"
    assert "max(data_days)" in sql, "外层日均应使用动态 data_days"
    assert "max(jin_shen) / max(data_days) AS avg_jinshen" in sql, \
        "P2 外层指标应只取当前周期唯一值，不能按命中条件重复 SUM"
    assert "SUM(jin_shen) / data_days AS avg_jinshen" not in sql, \
        "P2 多条件命中时外层 SUM 会导致日均量翻倍"
    assert "GROUP BY reason, data_days" not in sql, "P2 外层应仅按 reason 去重合并命中条件"
    print("✅ test_p2_default_render passed")


def test_p2_custom_threshold():
    """P2 自定义阈值应生效。"""
    ctx = st.build_p2_ctx()
    sql = st.render_sql("rule_low_label_rate_p2", {
        "c1_jinshen_threshold": 20000,
        "growth_rate_threshold": 0.5,
        "daily_delta_threshold": 5000,
    }, ctx)
    assert "`[进审量_reviewid]` > 20000" in sql, "c1_jinshen_threshold=20000 应生效"
    assert "> 0.5" in sql
    assert "> 5000" in sql
    print("✅ test_p2_custom_threshold passed")


def test_p0_default_render():
    """P0 四条件 UNION 骨架应正确渲染（4 周窗口 w1-w4，动态天数）。

    P0 已注册模板（非兜底自然语言路径），sql_key=rule_low_label_rate_p0。
    """
    ctx = st.build_p0_ctx()
    sql = st.render_sql("rule_low_label_rate_p0", {}, ctx)
    assert sql.count("UNION ALL") == 3, "P0 应包含 3 个 UNION ALL（四条件）"
    assert "'持续四周低效（严重）" in sql
    assert "'持续两周低效（高量）" in sql
    assert "'持续一周低效（超高量）" in sql
    assert "'进审量异常爆量" in sql
    assert "arrayStringConcat(arraySort(groupUniqArray(hit))" in sql
    assert "`[p_date]` >= '2026-06-04'" in sql, "应含最早的 w4 周窗口分区"
    assert "COUNT(DISTINCT `[p_date]`)" in sql, "应使用动态天数而非硬编码"
    assert "ORDER BY ajs DESC" in sql
    # 条件A：只有近1周(w1)校验日均进审>2000（外层 WHERE w1.avg_js > 2000）；
    # w2/w3/w4 只校验打标率<3%，不能带日均进审守卫（否则违反权威定义、误杀历史低量周）
    assert "w1.avg_js > 2000" in sql, "条件A w1 应校验日均进审>2000"
    assert sql.count("/ COUNT(DISTINCT `[p_date]`) > 2000") == 0, \
        "条件A 的 w2/w3/w4 子查询不得带日均进审守卫，只看打标率"
    print("✅ test_p0_default_render passed")


def test_legacy_p_logical_field_placeholder_compat():
    """旧 {p.xxx} logical_field 占位符路径应按当前 quote_style 渲染真实字段。"""
    key = "_test_legacy_placeholder"
    st.SQL_TEMPLATES[key] = {
        "version": "test",
        "level_hint": "test",
        "desc": "legacy placeholder compatibility",
        "required_params": ["ratio_field"],
        "param_types": {"ratio_field": "logical_field"},
        "required_ctx_keys": ["table"],
        "optional_ctx_keys": ["field_map", "quote_style", "quote_table"],
        "default_params": {"ratio_field": "ratio"},
        "sql": "SELECT {p.ratio_field} AS ratio_field FROM {t}",
    }
    try:
        ctx = st.build_notice_ctx()
        sql = st.render_sql(key, {}, ctx)
        assert "SELECT `[打标率__reviewid]` AS ratio_field" in sql
    finally:
        st.SQL_TEMPLATES.pop(key, None)
    print("✅ test_legacy_p_logical_field_placeholder_compat passed")


if __name__ == "__main__":
    test_notice_default_render()
    test_notice_custom_threshold()
    test_bracket_quote_style()
    test_backtick_quote_style()
    test_structured_base_filter()
    test_string_base_filter_backward_compat()
    test_no_divide_by_days()
    test_validate_missing_param()
    test_validate_bad_op()
    test_validate_unknown_logical_field()
    test_p1_dual_period_render()
    test_field_map_override()
    test_unknown_sql_key()
    test_is_null_filter()
    test_p1_default_render()
    test_p1_custom_threshold()
    test_p2_default_render()
    test_p2_custom_threshold()
    test_p0_default_render()
    test_legacy_p_logical_field_placeholder_compat()
    print("\n🎉 All 20 tests passed!")
