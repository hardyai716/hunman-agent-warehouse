#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compile table-shaped SOP configuration exports into sop_config.v1.

This is the migration bridge between Lark Base configuration tables and the
current orchestrator JSON contract. It intentionally accepts local JSON
exports only; live Base reads should stay in a separate, explicitly authorized
adapter.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from config_linter import validation_report


TABLE_ALIASES: dict[str, tuple[str, ...]] = {
    "process_skill_registry": ("process_skill_registry", "Process Skill Registry", "Process Skill 注册表"),
    "report_template_registry": ("report_template_registry", "Report Template Registry", "Report Template 注册表"),
    "owner_source_registry": ("owner_source_registry", "Owner Source Registry", "Owner Source 注册表"),
    "sop_registry": ("sop_registry", "SOP 注册表", "SOP Registry"),
    "sop_nodes": ("sop_nodes", "SOP 节点表", "SOP Nodes"),
    "sop_metrics": ("sop_metrics", "SOP 指标表", "SOP 指标/观测对象表", "SOP 指标观测对象表", "SOP Metrics"),
    "sop_levels": ("sop_levels", "SOP 等级字典表", "SOP Levels"),
    "sop_rule_groups": ("sop_rule_groups", "SOP 规则组表", "SOP Rule Groups"),
    "report_policies": ("report_policies", "Report Publish Policy", "报告发布策略表"),
    "route_policies": ("route_policies", "SOP 路由策略表", "Route Policies"),
}

FIELD_ALIASES: dict[str, str] = {
    "SOP ID": "sop_id",
    "SOP 标识": "sop_id",
    "SOP 名称": "sop_name",
    "SOP 类型": "sop_type",
    "业务域": "business_domain",
    "归属团队": "owner_team",
    "是否启用": "enabled",
    "运行频率": "run_frequency",
    "运行模式": "run_mode",
    "过程 Skill": "process_skill",
    "Process Skill": "process_skill",
    "领域知识": "domain_reference",
    "默认报告类型": "default_report_type",
    "默认触达策略": "default_touch_policy",
    "状态策略": "state_policy",
    "配置版本": "config_version",
    "SOP 节点标识": "sop_node_id",
    "所属 SOP": "sop_id",
    "节点类型": "node_type",
    "节点顺序": "node_order",
    "必需输入": "required_inputs",
    "输出契约": "output_contract",
    "失败策略": "fail_policy",
    "Dry Run 行为": "dry_run_behavior",
    "指标 ID": "metric_id",
    "指标名称": "metric_name",
    "指标角色": "metric_role",
    "标准指标": "canonical_metric",
    "数据源 ID": "data_source_id",
    "周期策略": "period_policy",
    "等级 ID": "sop_level_id",
    "等级标签": "level_label",
    "等级名称": "level_name",
    "标准严重度": "normalized_severity",
    "优先级": "priority_order",
    "SLA 分钟": "sla_minutes",
    "SLA 文案": "sla_text",
    "需要人工确认": "requires_human_confirm",
    "默认受众策略": "default_audience_policy",
    "升级策略": "escalation_policy",
    "规则组 ID": "rule_group_id",
    "规则状态": "rule_status",
    "条件逻辑": "condition_logic",
    "窗口策略": "window_policy",
    "指标引用": "metric_refs",
    "规则 Key": "rule_key",
    "SQL Key": "sql_key",
    "路由粒度": "route_grain",
    "受众策略": "audience_policy",
    "报告策略 ID": "report_policy_id",
    "报告类型": "report_type",
    "模板名称": "template_name",
    "表格策略": "sheet_policy",
    "报告目标策略": "report_target_policy",
    "发送身份": "sender_identity",
    "渲染选项": "render_options",
    "幂等策略": "idempotency_policy",
    "等级选择": "level_selector",
    "路由策略 ID": "route_policy_id",
    "路由键字段": "route_key_fields",
    "Owner Source ID": "owner_source_id",
    "兜底策略": "fallback_policy",
    "支持 SOP 类型": "supported_sop_types",
    "支持报告类型": "supported_report_types",
    "必需领域知识": "required_domain_reference",
    "依赖 sibling": "required_siblings",
    "运行时工具依赖": "runtime_tool_dependencies",
    "校验命令": "validation_command",
    "输入契约": "input_contract",
    "Owner 字段": "owner_fields",
    "来源类型": "source_type",
    "来源引用": "source_ref",
    "键字段": "key_field",
    "新鲜度策略": "freshness_policy",
    "映射": "mappings",
    "场景": "scene",
    "本地模板名": "local_template_name",
    "必需产物": "required_artifacts",
    "必需变量": "required_variables",
}

VALUE_ALIASES: dict[str, dict[str, str]] = {
    "default_report_type": {
        "低效分级报告": "low_efficiency_grading",
        "低效等级明细": "low_efficiency_level_detail",
        "低效维度拆解": "low_efficiency_dimension_breakdown",
    },
    "business_domain": {
        "效率": "efficiency",
        "质量": "quality",
        "成本": "cost",
        "延时": "latency",
        "人审质量": "quality",
        "风险治理": "risk_governance",
    },
    "sop_type": {
        "低效打标": "low_efficiency_labeling",
        "审核延时": "review_latency",
        "质量异常": "quality_anomaly",
        "成本异常": "cost_anomaly",
    },
    "run_frequency": {
        "手动": "manual",
        "每日": "daily",
        "每周": "weekly",
        "每10分钟": "10min",
        "事件触发": "event_triggered",
    },
    "run_mode": {
        "手动": "manual",
        "定时": "scheduled",
        "仅报告": "report_only",
        "报告模式": "report_only",
        "影子运行": "shadow",
        "灰度运行": "canary",
        "正式运行": "active",
        "正式触达": "touch_execute",
        "回滚": "rollback",
    },
    "default_touch_policy": {
        "仅报告": "report_only",
        "预览触达": "preview",
        "正式触达": "touch_execute",
    },
    "state_policy": {
        "影子摘要": "shadow_summary_only",
        "人工确认": "manual_review",
    },
    "node_type": {
        "加载配置": "config_load",
        "配置校验": "config_lint",
        "数据就绪检查": "data_ready_gate",
        "过程分析": "process_analysis",
        "责任路由": "owner_routing",
        "报告发布": "report_publish",
        "触达发送": "touch_send",
        "审计收尾": "audit_finalize",
    },
    "fail_policy": {
        "阻断": "stop",
        "跳过触达": "skip_touch",
        "人工确认": "manual_review",
        "重试": "retry",
        "仅告警": "warn_only",
    },
    "supported_sop_types": {
        "低效打标": "low_efficiency_labeling",
        "审核延时": "review_latency",
        "质量异常": "quality_anomaly",
        "成本异常": "cost_anomaly",
    },
    "supported_report_types": {
        "低效分级报告": "low_efficiency_grading",
        "低效等级明细": "low_efficiency_level_detail",
        "低效维度拆解": "low_efficiency_dimension_breakdown",
    },
    "report_type": {
        "低效分级报告": "low_efficiency_grading",
        "低效等级明细": "low_efficiency_level_detail",
        "低效维度拆解": "low_efficiency_dimension_breakdown",
    },
    "scene": {
        "报告卡片": "report_card",
    },
    "normalized_severity": {
        "严重": "critical",
        "高": "high",
        "中": "medium",
        "低": "low",
    },
    "metric_role": {
        "主指标": "primary",
        "护栏指标": "guard",
        "上下文指标": "context",
    },
    "canonical_metric": {
        "打标率": "labeling_rate",
    },
    "period_policy": {
        "最近7个完整天": "last_7_complete_days",
    },
    "window_policy": {
        "最近7个完整天": "last_7_complete_days",
    },
    "route_grain": {
        "原因": "reason",
        "策略": "strategy",
    },
    "source_type": {
        "内置映射": "inline_mapping",
        "飞书多维表": "lark_base_table",
        "查询模板": "query_template",
        "过程输出": "process_output",
        "人工兜底": "manual_fallback",
    },
    "fallback_policy": {
        "仅缺失 owner 兜底": "missing_owner_only",
        "人工兜底": "manual_fallback",
    },
    "freshness_policy": {
        "样例静态": "sample_static",
        "每日刷新": "daily",
    },
    "sender_identity": {
        "机器人": "bot",
        "用户": "user",
    },
}

LIST_FIELDS = {
    "supported_sop_types",
    "supported_report_types",
    "required_siblings",
    "runtime_tool_dependencies",
    "required_artifacts",
    "required_variables",
    "owner_fields",
    "mappings",
    "required_inputs",
    "metric_refs",
    "threshold_refs",
    "target_value_refs",
    "output_fields",
    "route_key_fields",
}

DICT_FIELDS = {
    "input_contract",
    "output_contract",
    "sheet_policy",
    "report_target_policy",
    "render_options",
    "idempotency_policy",
    "rule_params",
    "sql_params",
    "dry_run_behavior",
}

BOOL_FIELDS = {"enabled", "requires_human_confirm"}
INT_FIELDS = {"node_order", "priority_order", "sla_minutes", "min_sample_size", "priority"}
META_FIELDS = {"record_id", "id", "created_time", "last_modified_time", "table", "table_name", "block_name"}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def parse_json_like(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return value
    if text[0] not in "[{":
        return value
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value


def parse_list(value: Any) -> list[Any]:
    parsed = parse_json_like(value)
    if isinstance(parsed, list):
        return parsed
    if parsed in (None, ""):
        return []
    if isinstance(parsed, str):
        parts = [item.strip() for item in re.split(r"[,，;\n]+", parsed) if item.strip()]
        return parts
    return [parsed]


def parse_bool(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if not isinstance(value, str):
        return value
    text = value.strip().lower()
    if text in {"true", "1", "yes", "y", "enabled", "enable", "是", "启用"}:
        return True
    if text in {"false", "0", "no", "n", "disabled", "disable", "否", "停用"}:
        return False
    return value


def parse_int(value: Any) -> Any:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(float(value.strip()))
        except ValueError:
            return value
    return value


def canonical_field_name(name: str) -> str:
    return FIELD_ALIASES.get(name, name)


def apply_value_alias(canonical_key: str, value: Any) -> Any:
    aliases = VALUE_ALIASES.get(canonical_key)
    if not aliases:
        return value
    if isinstance(value, str):
        return aliases.get(value.strip(), value)
    if isinstance(value, list):
        return [aliases.get(item.strip(), item) if isinstance(item, str) else item for item in value]
    return value


def normalize_field(key: str, value: Any) -> tuple[str, Any]:
    canonical_key = canonical_field_name(key)
    if canonical_key not in LIST_FIELDS and isinstance(value, list) and len(value) == 1:
        value = value[0]
    if canonical_key in LIST_FIELDS:
        return canonical_key, apply_value_alias(canonical_key, parse_list(value))
    if canonical_key in DICT_FIELDS:
        return canonical_key, parse_json_like(value)
    if canonical_key in BOOL_FIELDS:
        return canonical_key, parse_bool(value)
    if canonical_key in INT_FIELDS:
        return canonical_key, parse_int(value)
    return canonical_key, apply_value_alias(canonical_key, parse_json_like(value))


def normalize_record(record: Any) -> dict[str, Any]:
    if not isinstance(record, dict):
        return {}
    raw_fields = record.get("fields") if isinstance(record.get("fields"), dict) else record
    normalized: dict[str, Any] = {}
    for raw_key, raw_value in raw_fields.items():
        if raw_key in META_FIELDS:
            continue
        key, value = normalize_field(str(raw_key), raw_value)
        if value not in (None, ""):
            normalized[key] = value
    return normalized


def table_records(payload: dict[str, Any], table_key: str) -> list[dict[str, Any]]:
    aliases = set(TABLE_ALIASES[table_key])
    candidates: list[Any] = []

    tables = payload.get("tables") if isinstance(payload.get("tables"), dict) else {}
    for source in (payload, tables):
        for alias in aliases:
            if isinstance(source, dict) and alias in source:
                candidates.extend(as_list(source[alias]))

    for record in as_list(payload.get("records")):
        if not isinstance(record, dict):
            continue
        table_name = record.get("table") or record.get("table_name") or record.get("block_name")
        if table_name in aliases:
            candidates.append(record)

    return [normalized for normalized in (normalize_record(record) for record in candidates) if normalized]


def group_by_sop(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        sop_id = record.get("sop_id")
        if not sop_id:
            continue
        grouped.setdefault(str(sop_id), []).append(record)
    return grouped


def sort_records(records: list[dict[str, Any]], *fields: str) -> list[dict[str, Any]]:
    def sort_value(value: Any) -> tuple[int, Any]:
        if isinstance(value, (int, float)):
            return (0, float(value))
        return (1, "" if value is None else str(value))

    def key(record: dict[str, Any]) -> tuple[Any, ...]:
        return tuple(sort_value(record.get(field)) for field in fields)

    return sorted(records, key=key)


def compile_table_config(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise TypeError("table config export must be a JSON object")

    nodes_by_sop = group_by_sop(table_records(payload, "sop_nodes"))
    metrics_by_sop = group_by_sop(table_records(payload, "sop_metrics"))
    levels_by_sop = group_by_sop(table_records(payload, "sop_levels"))
    rules_by_sop = group_by_sop(table_records(payload, "sop_rule_groups"))
    reports_by_sop = group_by_sop(table_records(payload, "report_policies"))
    routes_by_sop = group_by_sop(table_records(payload, "route_policies"))

    sops: list[dict[str, Any]] = []
    for sop in sort_records(table_records(payload, "sop_registry"), "sop_id"):
        sop_id = str(sop.get("sop_id", ""))
        compiled = dict(sop)
        compiled["nodes"] = sort_records(nodes_by_sop.get(sop_id, []), "node_order", "node_type")
        compiled["metrics"] = sort_records(metrics_by_sop.get(sop_id, []), "metric_id")
        compiled["levels"] = sort_records(levels_by_sop.get(sop_id, []), "priority_order", "sop_level_id")
        compiled["rule_groups"] = sort_records(rules_by_sop.get(sop_id, []), "rule_group_id")
        compiled["report_policies"] = sort_records(reports_by_sop.get(sop_id, []), "report_policy_id")
        compiled["route_policies"] = sort_records(routes_by_sop.get(sop_id, []), "route_policy_id")
        sops.append(compiled)

    return {
        "schema_version": "sop_config.v1",
        "source_schema_version": payload.get("schema_version", "base_table_config_export.v1"),
        "process_skill_registry": sort_records(table_records(payload, "process_skill_registry"), "process_skill"),
        "report_template_registry": sort_records(table_records(payload, "report_template_registry"), "report_type"),
        "owner_source_registry": sort_records(table_records(payload, "owner_source_registry"), "owner_source_id"),
        "sops": sops,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile table-shaped SOP config exports into sop_config.v1.")
    parser.add_argument("--input", required=True, type=Path, help="Local JSON export from SOP Base configuration tables.")
    parser.add_argument("--output", type=Path, help="Path to write compiled sop_config.v1 JSON.")
    parser.add_argument("--lint", action="store_true", help="Run config_linter on the compiled config.")
    parser.add_argument("--lint-output", type=Path, help="Optional path to write validation_report.v1 JSON.")
    parser.add_argument("--mode", default="shadow")
    parser.add_argument("--sop-id")
    args = parser.parse_args()

    compiled = compile_table_config(read_json(args.input))
    compiled_text = json.dumps(compiled, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        write_json(args.output, compiled)
    else:
        print(compiled_text, end="")

    if not args.lint:
        return 0

    report = validation_report(compiled, mode=args.mode, sop_id=args.sop_id)
    if args.lint_output:
        write_json(args.lint_output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2), file=sys.stderr)
    return 0 if report["summary"]["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
