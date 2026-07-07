#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Export SOP-first configuration tables from Lark Base and merge into sop_config.v1.

The migration is staged but cumulative: tables that already exist in Base are
used as the source of truth, while sections that are not exported yet can still
fall back to the existing JSON config.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from config_linter import validation_report
from table_config_compiler import compile_table_config, write_json


DEFAULT_SOP_TABLE_ID = "tbl1XbKnCFRNT9B3"
DEFAULT_NODE_TABLE_ID = "tblQeV35N4hUQjhk"
DEFAULT_PROCESS_TABLE_ID = "tbl3Eb1T8UVDjpBy"
DEFAULT_REPORT_TEMPLATE_TABLE_ID = "tblkLMsbCT4qyZVk"
DEFAULT_METRIC_TABLE_ID = "tblolM7J5xosqBkU"
DEFAULT_LEVEL_TABLE_ID = "tblH70YZBJH3AGvy"
DEFAULT_RULE_TABLE_ID = "tblalz3XbnsP8p6X"
DEFAULT_REPORT_POLICY_TABLE_ID = "tblI8et5gzDGjQol"
DEFAULT_ROUTE_POLICY_TABLE_ID = "tbluiLfUfBAwZ6Xm"
DEFAULT_OWNER_SOURCE_TABLE_ID = "tbl8gUBe1eXo8y1O"
DEFAULT_BASE_CONFIG = Path(__file__).resolve().parents[1] / "examples" / "low_efficiency_sop_config.sample.json"
NESTED_SOP_KEYS = {"nodes", "metrics", "levels", "rule_groups", "report_policies", "route_policies"}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def run_record_list(
    *,
    base_token: str,
    table_id: str,
    fields: list[str],
    identity: str,
    filter_json: dict[str, Any] | None = None,
    sort_json: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    offset = 0
    limit = 200

    while True:
        command = [
            "lark-cli",
            "base",
            "+record-list",
            "--base-token",
            base_token,
            "--table-id",
            table_id,
            "--as",
            identity,
            "--limit",
            str(limit),
            "--offset",
            str(offset),
            "--format",
            "json",
        ]
        for field in fields:
            command.extend(["--field-id", field])
        if filter_json is not None:
            command.extend(["--filter-json", json.dumps(filter_json, ensure_ascii=False, separators=(",", ":"))])
        if sort_json is not None:
            command.extend(["--sort-json", json.dumps(sort_json, ensure_ascii=False, separators=(",", ":"))])

        proc = subprocess.run(command, text=True, capture_output=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(f"lark-cli record-list failed for table {table_id}: {proc.stderr or proc.stdout}")
        envelope = json.loads(proc.stdout)
        if not envelope.get("ok"):
            raise RuntimeError(f"lark-cli record-list returned not ok for table {table_id}: {proc.stdout}")
        data = envelope.get("data") if isinstance(envelope.get("data"), dict) else {}
        field_names = data.get("fields") if isinstance(data.get("fields"), list) else []
        rows = data.get("data") if isinstance(data.get("data"), list) else []
        record_ids = data.get("record_id_list") if isinstance(data.get("record_id_list"), list) else []

        for index, row in enumerate(rows):
            if not isinstance(row, list):
                continue
            fields_map = {str(field): row[pos] for pos, field in enumerate(field_names) if pos < len(row)}
            record: dict[str, Any] = {"fields": fields_map}
            if index < len(record_ids):
                record["record_id"] = record_ids[index]
            records.append(record)

        if not data.get("has_more"):
            break
        offset += len(rows) or limit

    return records


def build_base_table_export(
    *,
    base_token: str,
    sop_table_id: str,
    node_table_id: str,
    process_table_id: str,
    report_template_table_id: str,
    metric_table_id: str,
    level_table_id: str,
    rule_table_id: str,
    report_policy_table_id: str,
    route_policy_table_id: str,
    owner_source_table_id: str,
    identity: str,
    sop_id: str | None,
) -> dict[str, Any]:
    sop_filter = {"logic": "and", "conditions": [["SOP 标识", "==", sop_id]]} if sop_id else None
    node_filter = {"logic": "and", "conditions": [["所属 SOP", "==", sop_id]]} if sop_id else None
    scoped_filter = {"logic": "and", "conditions": [["所属 SOP", "==", sop_id]]} if sop_id else None
    return {
        "schema_version": "base_table_config_export.v1",
        "source": {
            "type": "lark_base",
            "tables": {
                "Process Skill 注册表": process_table_id,
                "Report Template 注册表": report_template_table_id,
                "SOP 注册表": sop_table_id,
                "SOP 节点表": node_table_id,
                "SOP 指标观测对象表": metric_table_id,
                "SOP 等级字典表": level_table_id,
                "SOP 规则组表": rule_table_id,
                "报告发布策略表": report_policy_table_id,
                "SOP 路由策略表": route_policy_table_id,
                "Owner Source 注册表": owner_source_table_id,
            },
        },
        "tables": {
            "Process Skill 注册表": run_record_list(
                base_token=base_token,
                table_id=process_table_id,
                fields=[
                    "过程 Skill",
                    "业务域",
                    "支持 SOP 类型",
                    "支持报告类型",
                    "必需领域知识",
                    "依赖 sibling",
                    "运行时工具依赖",
                    "校验命令",
                    "输入契约",
                    "输出契约",
                    "是否启用",
                ],
                identity=identity,
            ),
            "Report Template 注册表": run_record_list(
                base_token=base_token,
                table_id=report_template_table_id,
                fields=[
                    "报告类型",
                    "模板名称",
                    "场景",
                    "本地模板名",
                    "必需产物",
                    "必需变量",
                    "是否启用",
                ],
                identity=identity,
            ),
            "SOP 注册表": run_record_list(
                base_token=base_token,
                table_id=sop_table_id,
                fields=[
                    "SOP 标识",
                    "SOP 名称",
                    "SOP 类型",
                    "业务域",
                    "归属团队",
                    "是否启用",
                    "运行频率",
                    "运行模式",
                    "过程 Skill",
                    "领域知识",
                    "默认报告类型",
                    "默认触达策略",
                    "状态策略",
                    "配置版本",
                ],
                identity=identity,
                filter_json=sop_filter,
            ),
            "SOP 节点表": run_record_list(
                base_token=base_token,
                table_id=node_table_id,
                fields=[
                    "SOP 节点标识",
                    "所属 SOP",
                    "节点类型",
                    "节点顺序",
                    "是否启用",
                    "必需输入",
                    "输出契约",
                    "失败策略",
                    "Dry Run 行为",
                ],
                identity=identity,
                filter_json=node_filter,
                sort_json=[{"field": "节点顺序", "desc": False}],
            ),
            "SOP 指标观测对象表": run_record_list(
                base_token=base_token,
                table_id=metric_table_id,
                fields=[
                    "指标 ID",
                    "所属 SOP",
                    "指标名称",
                    "指标角色",
                    "标准指标",
                    "数据源 ID",
                    "周期策略",
                    "是否启用",
                ],
                identity=identity,
                filter_json=scoped_filter,
            ),
            "SOP 等级字典表": run_record_list(
                base_token=base_token,
                table_id=level_table_id,
                fields=[
                    "等级 ID",
                    "所属 SOP",
                    "等级标签",
                    "等级名称",
                    "标准严重度",
                    "优先级",
                    "SLA 分钟",
                    "SLA 文案",
                    "需要人工确认",
                    "默认受众策略",
                    "是否启用",
                ],
                identity=identity,
                filter_json=scoped_filter,
                sort_json=[{"field": "优先级", "desc": False}],
            ),
            "SOP 规则组表": run_record_list(
                base_token=base_token,
                table_id=rule_table_id,
                fields=[
                    "规则组 ID",
                    "所属 SOP",
                    "等级 ID",
                    "条件逻辑",
                    "窗口策略",
                    "指标引用",
                    "规则 Key",
                    "路由粒度",
                    "受众策略",
                    "是否启用",
                ],
                identity=identity,
                filter_json=scoped_filter,
            ),
            "报告发布策略表": run_record_list(
                base_token=base_token,
                table_id=report_policy_table_id,
                fields=[
                    "报告策略 ID",
                    "所属 SOP",
                    "报告类型",
                    "模板名称",
                    "等级选择",
                    "表格策略",
                    "报告目标策略",
                    "发送身份",
                    "渲染选项",
                    "幂等策略",
                    "是否启用",
                ],
                identity=identity,
                filter_json=scoped_filter,
            ),
            "SOP 路由策略表": run_record_list(
                base_token=base_token,
                table_id=route_policy_table_id,
                fields=[
                    "路由策略 ID",
                    "所属 SOP",
                    "路由粒度",
                    "路由键字段",
                    "Owner Source ID",
                    "兜底策略",
                    "是否启用",
                ],
                identity=identity,
                filter_json=scoped_filter,
            ),
            "Owner Source 注册表": run_record_list(
                base_token=base_token,
                table_id=owner_source_table_id,
                fields=[
                    "Owner Source ID",
                    "所属 SOP",
                    "路由粒度",
                    "来源类型",
                    "来源引用",
                    "键字段",
                    "Owner 字段",
                    "兜底策略",
                    "新鲜度策略",
                    "是否启用",
                    "映射",
                ],
                identity=identity,
                filter_json=scoped_filter,
            ),
        },
    }


def merge_base_config(base_config: dict[str, Any], table_export: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base_config)
    compiled_partial = compile_table_config(table_export)

    if compiled_partial.get("process_skill_registry"):
        result["process_skill_registry"] = compiled_partial["process_skill_registry"]
    if compiled_partial.get("report_template_registry"):
        result["report_template_registry"] = compiled_partial["report_template_registry"]
    if compiled_partial.get("owner_source_registry"):
        result["owner_source_registry"] = compiled_partial["owner_source_registry"]

    existing_sops = result.setdefault("sops", [])
    existing_by_id = {str(sop.get("sop_id")): sop for sop in existing_sops if isinstance(sop, dict) and sop.get("sop_id")}

    for partial_sop in compiled_partial.get("sops", []):
        if not isinstance(partial_sop, dict) or not partial_sop.get("sop_id"):
            continue
        sop_id = str(partial_sop["sop_id"])
        target = existing_by_id.get(sop_id)
        if target is None:
            target = {}
            existing_sops.append(target)
            existing_by_id[sop_id] = target

        for key, value in partial_sop.items():
            if key not in NESTED_SOP_KEYS:
                target[key] = value
        for key in NESTED_SOP_KEYS:
            if partial_sop.get(key):
                target[key] = partial_sop[key]

    result["schema_version"] = "sop_config.v1"
    exported_non_empty = [
        table_name
        for table_name, records in table_export.get("tables", {}).items()
        if isinstance(records, list) and records
    ]
    result["config_source"] = {
        "type": "merged_base_table_config",
        "base_tables": table_export.get("source", {}).get("tables", {}),
        "exported_non_empty_tables": sorted(exported_non_empty),
    }
    return result


def merge_sop_skeleton(base_config: dict[str, Any], table_export: dict[str, Any]) -> dict[str, Any]:
    return merge_base_config(base_config, table_export)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Base SOP skeleton tables and merge into sop_config.v1.")
    parser.add_argument("--base-token", default=os.environ.get("HUMAN_REVIEW_BASE_TOKEN") or os.environ.get("LARK_BASE_TOKEN"))
    parser.add_argument("--sop-table-id", default=DEFAULT_SOP_TABLE_ID)
    parser.add_argument("--node-table-id", default=DEFAULT_NODE_TABLE_ID)
    parser.add_argument("--process-table-id", default=DEFAULT_PROCESS_TABLE_ID)
    parser.add_argument("--report-template-table-id", default=DEFAULT_REPORT_TEMPLATE_TABLE_ID)
    parser.add_argument("--metric-table-id", default=DEFAULT_METRIC_TABLE_ID)
    parser.add_argument("--level-table-id", default=DEFAULT_LEVEL_TABLE_ID)
    parser.add_argument("--rule-table-id", default=DEFAULT_RULE_TABLE_ID)
    parser.add_argument("--report-policy-table-id", default=DEFAULT_REPORT_POLICY_TABLE_ID)
    parser.add_argument("--route-policy-table-id", default=DEFAULT_ROUTE_POLICY_TABLE_ID)
    parser.add_argument("--owner-source-table-id", default=DEFAULT_OWNER_SOURCE_TABLE_ID)
    parser.add_argument("--identity", default="user", choices=["user", "bot"])
    parser.add_argument("--sop-id", default="low_efficiency_labeling")
    parser.add_argument("--base-config", type=Path, default=DEFAULT_BASE_CONFIG)
    parser.add_argument("--raw-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--lint-output", type=Path)
    parser.add_argument("--mode", default="shadow")
    parser.add_argument("--no-lint", action="store_true")
    args = parser.parse_args()

    if not args.base_token:
        raise SystemExit("Missing Base token. Set HUMAN_REVIEW_BASE_TOKEN or pass --base-token.")

    table_export = build_base_table_export(
        base_token=args.base_token,
        sop_table_id=args.sop_table_id,
        node_table_id=args.node_table_id,
        process_table_id=args.process_table_id,
        report_template_table_id=args.report_template_table_id,
        metric_table_id=args.metric_table_id,
        level_table_id=args.level_table_id,
        rule_table_id=args.rule_table_id,
        report_policy_table_id=args.report_policy_table_id,
        route_policy_table_id=args.route_policy_table_id,
        owner_source_table_id=args.owner_source_table_id,
        identity=args.identity,
        sop_id=args.sop_id,
    )
    write_json(args.raw_output, table_export)

    merged = merge_base_config(read_json(args.base_config), table_export)
    write_json(args.output, merged)

    summary: dict[str, Any] = {
        "raw_output": str(args.raw_output),
        "merged_config": str(args.output),
        "table_counts": {
            table_name: len(records) for table_name, records in table_export["tables"].items()
        },
    }
    if not args.no_lint:
        report = validation_report(merged, mode=args.mode, sop_id=args.sop_id)
        if args.lint_output:
            write_json(args.lint_output, report)
        summary["validation_status"] = report["summary"]["status"]
        summary["finding_count"] = report["summary"]["finding_count"]
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if report["summary"]["status"] == "passed" else 1

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
