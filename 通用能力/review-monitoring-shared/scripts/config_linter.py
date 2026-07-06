#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SOP-first configuration linter.

The linter validates the machine-readable configuration used by the
monitoring-orchestrator, owner-routing and anomaly-touch report publishing
adapter. It intentionally performs structural checks only; it does not read
Lark Base, execute SQL, send messages, or modify runtime state.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


EXTERNAL_RUNTIME_DEP_PREFIXES = ("lark-",)
EXTERNAL_RUNTIME_DEP_NAMES = {
    "sqless",
    "sqless-data-analysis",
    "bytedcli",
    "bytedance-aeolus",
    "bytedance_aeolus",
}
ALLOWED_RUN_MODES = {
    "manual",
    "scheduled",
    "report_only",
    "touch_execute",
    "shadow",
    "canary",
    "active",
    "rollback",
}
ALLOWED_SOURCE_TYPES = {
    "inline_mapping",
    "lark_base_table",
    "query_template",
    "process_output",
    "manual_fallback",
}


@dataclass(frozen=True)
class Finding:
    severity: str
    category: str
    check_id: str
    table_name: str
    record_key: str
    field_name: str
    current_value: Any
    expected_value: Any
    message: str
    fix_hint: str
    can_auto_fix: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "category": self.category,
            "check_id": self.check_id,
            "table_name": self.table_name,
            "record_key": self.record_key,
            "field_name": self.field_name,
            "current_value": self.current_value,
            "expected_value": self.expected_value,
            "message": self.message,
            "fix_hint": self.fix_hint,
            "can_auto_fix": self.can_auto_fix,
        }


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _index_by(items: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        if isinstance(item, dict) and item.get(key):
            result[str(item[key])] = item
    return result


def _is_external_runtime_dependency(name: str) -> bool:
    return name in EXTERNAL_RUNTIME_DEP_NAMES or any(name.startswith(prefix) for prefix in EXTERNAL_RUNTIME_DEP_PREFIXES)


class ConfigLinter:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.findings: list[Finding] = []
        self.process_registry = _index_by(_as_list(config.get("process_skill_registry")), "process_skill")
        self.report_registry = _index_by(_as_list(config.get("report_template_registry")), "report_type")
        self.owner_sources = _index_by(_as_list(config.get("owner_source_registry")), "owner_source_id")

    def add(
        self,
        *,
        severity: str,
        category: str,
        check_id: str,
        table_name: str,
        record_key: str,
        field_name: str,
        current_value: Any,
        expected_value: Any,
        message: str,
        fix_hint: str,
        can_auto_fix: bool = False,
    ) -> None:
        self.findings.append(
            Finding(
                severity=severity,
                category=category,
                check_id=check_id,
                table_name=table_name,
                record_key=record_key,
                field_name=field_name,
                current_value=current_value,
                expected_value=expected_value,
                message=message,
                fix_hint=fix_hint,
                can_auto_fix=can_auto_fix,
            )
        )

    def require(self, record: dict[str, Any], fields: list[str], *, table_name: str, record_key: str, category: str) -> None:
        for field in fields:
            if record.get(field) in (None, "", []):
                self.add(
                    severity="error",
                    category=category,
                    check_id="REQUIRED_FIELD_MISSING",
                    table_name=table_name,
                    record_key=record_key,
                    field_name=field,
                    current_value=record.get(field),
                    expected_value="non-empty",
                    message=f"{table_name} 缺少必填字段 {field}",
                    fix_hint=f"补充 {record_key} 的 {field} 字段。",
                )

    def lint(self) -> list[Finding]:
        if not isinstance(self.config, dict):
            self.add(
                severity="blocker",
                category="config",
                check_id="CONFIG_NOT_OBJECT",
                table_name="配置根",
                record_key="<root>",
                field_name="<root>",
                current_value=type(self.config).__name__,
                expected_value="object",
                message="配置根必须是 JSON object。",
                fix_hint="将配置文件改为包含 registry 和 sops 的 JSON object。",
            )
            return self.findings

        self._lint_registries()
        for sop in _as_list(self.config.get("sops")):
            if isinstance(sop, dict):
                self._lint_sop(sop)

        if not _as_list(self.config.get("sops")):
            self.add(
                severity="error",
                category="sop_lint",
                check_id="NO_SOPS",
                table_name="SOP注册表",
                record_key="<root>",
                field_name="sops",
                current_value=self.config.get("sops"),
                expected_value="non-empty list",
                message="配置中没有任何 SOP。",
                fix_hint="至少增加一个 SOP 配置记录。",
            )
        return self.findings

    def _lint_registries(self) -> None:
        for process in _as_list(self.config.get("process_skill_registry")):
            if not isinstance(process, dict):
                continue
            key = str(process.get("process_skill", "<missing>"))
            self.require(
                process,
                ["process_skill", "business_domain", "supported_report_types", "output_contract", "validation_command"],
                table_name="Process Skill Registry",
                record_key=key,
                category="registry_lint",
            )
            for sibling in _as_list(process.get("required_siblings")):
                if isinstance(sibling, str) and _is_external_runtime_dependency(sibling):
                    self.add(
                        severity="error",
                        category="registry_lint",
                        check_id="EXTERNAL_DEP_IN_REQUIRED_SIBLINGS",
                        table_name="Process Skill Registry",
                        record_key=key,
                        field_name="required_siblings",
                        current_value=sibling,
                        expected_value="project-local sibling skill only",
                        message="外部平台能力不能写入项目上传包 required_siblings。",
                        fix_hint="将该依赖移动到 runtime_tool_dependencies。",
                    )

        for report in _as_list(self.config.get("report_template_registry")):
            if not isinstance(report, dict):
                continue
            key = str(report.get("report_type", "<missing>"))
            self.require(
                report,
                ["report_type", "template_name", "scene", "required_artifacts", "enabled"],
                table_name="Report Template Registry",
                record_key=key,
                category="registry_lint",
            )

        for source in _as_list(self.config.get("owner_source_registry")):
            if not isinstance(source, dict):
                continue
            key = str(source.get("owner_source_id", "<missing>"))
            self.require(
                source,
                ["owner_source_id", "sop_id", "route_grain", "source_type", "key_field", "owner_fields", "fallback_policy", "freshness_policy"],
                table_name="Owner Source Registry",
                record_key=key,
                category="registry_lint",
            )
            if source.get("source_type") and source.get("source_type") not in ALLOWED_SOURCE_TYPES:
                self.add(
                    severity="error",
                    category="registry_lint",
                    check_id="OWNER_SOURCE_TYPE_INVALID",
                    table_name="Owner Source Registry",
                    record_key=key,
                    field_name="source_type",
                    current_value=source.get("source_type"),
                    expected_value=sorted(ALLOWED_SOURCE_TYPES),
                    message="Owner Source 使用了未支持的 source_type。",
                    fix_hint="改为已注册的 source_type，或先扩展 owner-routing 实现。",
                )

    def _lint_sop(self, sop: dict[str, Any]) -> None:
        sop_id = str(sop.get("sop_id", "<missing>"))
        self.require(
            sop,
            ["sop_id", "sop_name", "business_domain", "process_skill", "domain_reference", "run_frequency", "run_mode", "default_report_type"],
            table_name="SOP注册表",
            record_key=sop_id,
            category="sop_lint",
        )
        if sop.get("run_mode") and sop.get("run_mode") not in ALLOWED_RUN_MODES:
            self.add(
                severity="error",
                category="sop_lint",
                check_id="SOP_RUN_MODE_INVALID",
                table_name="SOP注册表",
                record_key=sop_id,
                field_name="run_mode",
                current_value=sop.get("run_mode"),
                expected_value=sorted(ALLOWED_RUN_MODES),
                message="SOP run_mode 不合法。",
                fix_hint="改为已支持的运行模式。",
            )

        process = self.process_registry.get(str(sop.get("process_skill")))
        if not process:
            self.add(
                severity="error",
                category="sop_lint",
                check_id="PROCESS_SKILL_NOT_REGISTERED",
                table_name="SOP注册表",
                record_key=sop_id,
                field_name="process_skill",
                current_value=sop.get("process_skill"),
                expected_value=sorted(self.process_registry),
                message="SOP 引用了未注册 process skill。",
                fix_hint="先在 Process Skill Registry 中注册该 skill，并补齐 output contract。",
            )

        report_type = str(sop.get("default_report_type", ""))
        if report_type:
            if report_type not in self.report_registry:
                self.add(
                    severity="error",
                    category="sop_lint",
                    check_id="REPORT_TYPE_NOT_REGISTERED",
                    table_name="SOP注册表",
                    record_key=sop_id,
                    field_name="default_report_type",
                    current_value=report_type,
                    expected_value=sorted(self.report_registry),
                    message="SOP default_report_type 未在 Report Template Registry 注册。",
                    fix_hint="注册 report type 和模板，或改为已注册 report type。",
                )
            if process and report_type not in _as_list(process.get("supported_report_types")):
                self.add(
                    severity="error",
                    category="sop_lint",
                    check_id="REPORT_TYPE_NOT_SUPPORTED_BY_PROCESS",
                    table_name="SOP注册表",
                    record_key=sop_id,
                    field_name="default_report_type",
                    current_value=report_type,
                    expected_value=process.get("supported_report_types"),
                    message="SOP 的 report type 不在 process skill 支持范围内。",
                    fix_hint="改用 process skill 支持的 report type，或扩展 process registry。",
                )

        self._lint_nodes(sop, sop_id)
        levels = self._lint_levels(sop, sop_id)
        self._lint_metrics(sop, sop_id)
        self._lint_rule_groups(sop, sop_id, process, levels)
        self._lint_report_policies(sop, sop_id, process)
        self._lint_route_policies(sop, sop_id, process)

    def _lint_nodes(self, sop: dict[str, Any], sop_id: str) -> None:
        nodes = [node for node in _as_list(sop.get("nodes")) if isinstance(node, dict)]
        if not nodes:
            self.add(
                severity="error",
                category="sop_lint",
                check_id="SOP_NODES_EMPTY",
                table_name="SOP节点表",
                record_key=sop_id,
                field_name="nodes",
                current_value=nodes,
                expected_value="non-empty list",
                message="SOP 没有配置节点。",
                fix_hint="至少配置 config_load、config_lint、process_analysis、audit_finalize 等节点。",
            )
            return
        orders: dict[int, str] = {}
        node_types = {str(node.get("node_type")) for node in nodes}
        for node in nodes:
            key = str(node.get("node_type", "<missing>"))
            self.require(node, ["node_type", "node_order", "enabled"], table_name="SOP节点表", record_key=f"{sop_id}:{key}", category="sop_lint")
            if isinstance(node.get("node_order"), int):
                if node["node_order"] in orders:
                    self.add(
                        severity="error",
                        category="sop_lint",
                        check_id="NODE_ORDER_DUPLICATED",
                        table_name="SOP节点表",
                        record_key=f"{sop_id}:{key}",
                        field_name="node_order",
                        current_value=node["node_order"],
                        expected_value="unique integer per SOP",
                        message="SOP 节点顺序重复。",
                        fix_hint="为同一 SOP 下的节点设置唯一 node_order，或显式拆依赖。",
                    )
                orders[node["node_order"]] = key
        if "touch_send" in node_types and "owner_routing" not in node_types:
            self.add(
                severity="error",
                category="sop_lint",
                check_id="TOUCH_SEND_WITHOUT_OWNER_ROUTING",
                table_name="SOP节点表",
                record_key=sop_id,
                field_name="nodes",
                current_value=sorted(node_types),
                expected_value="owner_routing before touch_send",
                message="启用正式触达前必须先启用 owner_routing。",
                fix_hint="补充 owner_routing 节点，或关闭 touch_send。",
            )

    def _lint_levels(self, sop: dict[str, Any], sop_id: str) -> dict[str, dict[str, Any]]:
        levels = [level for level in _as_list(sop.get("levels")) if isinstance(level, dict)]
        level_map = _index_by(levels, "sop_level_id")
        if not levels:
            self.add(
                severity="error",
                category="level_lint",
                check_id="SOP_LEVELS_EMPTY",
                table_name="SOP等级字典表",
                record_key=sop_id,
                field_name="levels",
                current_value=levels,
                expected_value="non-empty list",
                message="SOP 没有等级字典。",
                fix_hint="为当前 SOP 配置 sop_level_id、level_label、SLA 和受众策略。",
            )
            return level_map
        priorities: dict[Any, str] = {}
        for level in levels:
            key = str(level.get("sop_level_id", "<missing>"))
            self.require(
                level,
                ["sop_level_id", "level_label", "normalized_severity", "priority_order", "sla_minutes", "requires_human_confirm", "default_audience_policy"],
                table_name="SOP等级字典表",
                record_key=f"{sop_id}:{key}",
                category="level_lint",
            )
            if level.get("sop_id") and level.get("sop_id") != sop_id:
                self.add(
                    severity="error",
                    category="level_lint",
                    check_id="LEVEL_SOP_ID_MISMATCH",
                    table_name="SOP等级字典表",
                    record_key=f"{sop_id}:{key}",
                    field_name="sop_id",
                    current_value=level.get("sop_id"),
                    expected_value=sop_id,
                    message="等级字典记录不属于当前 SOP。",
                    fix_hint="确保等级配置使用当前 SOP 的 sop_id，不跨 SOP 复用。",
                )
            priority = level.get("priority_order")
            if priority in priorities:
                self.add(
                    severity="error",
                    category="level_lint",
                    check_id="LEVEL_PRIORITY_DUPLICATED",
                    table_name="SOP等级字典表",
                    record_key=f"{sop_id}:{key}",
                    field_name="priority_order",
                    current_value=priority,
                    expected_value="unique per SOP",
                    message="同一 SOP 下等级 priority_order 重复。",
                    fix_hint="为每个等级设置唯一优先级。",
                )
            priorities[priority] = key
        return level_map

    def _lint_metrics(self, sop: dict[str, Any], sop_id: str) -> None:
        metrics = [metric for metric in _as_list(sop.get("metrics")) if isinstance(metric, dict)]
        if not metrics:
            self.add(
                severity="error",
                category="sop_lint",
                check_id="SOP_METRICS_EMPTY",
                table_name="SOP指标/观测对象表",
                record_key=sop_id,
                field_name="metrics",
                current_value=metrics,
                expected_value="non-empty list",
                message="SOP 没有观测对象。",
                fix_hint="至少配置一个 metric_id 和 data_source_id。",
            )
        for metric in metrics:
            key = str(metric.get("metric_id", "<missing>"))
            self.require(metric, ["metric_id", "data_source_id", "period_policy", "canonical_metric", "enabled"], table_name="SOP指标/观测对象表", record_key=f"{sop_id}:{key}", category="sop_lint")

    def _lint_rule_groups(
        self,
        sop: dict[str, Any],
        sop_id: str,
        process: dict[str, Any] | None,
        levels: dict[str, dict[str, Any]],
    ) -> None:
        route_grains = set(_as_list((process or {}).get("output_contract", {}).get("route_grains")))
        for rule in [item for item in _as_list(sop.get("rule_groups")) if isinstance(item, dict)]:
            key = str(rule.get("rule_group_id", "<missing>"))
            self.require(
                rule,
                ["rule_group_id", "sop_level_id", "condition_logic", "window_policy", "metric_refs", "audience_policy"],
                table_name="SOP规则组表",
                record_key=f"{sop_id}:{key}",
                category="sop_lint",
            )
            level_id = str(rule.get("sop_level_id", ""))
            if level_id and level_id not in levels:
                self.add(
                    severity="error",
                    category="level_lint",
                    check_id="RULE_LEVEL_NOT_IN_SOP",
                    table_name="SOP规则组表",
                    record_key=f"{sop_id}:{key}",
                    field_name="sop_level_id",
                    current_value=level_id,
                    expected_value=sorted(levels),
                    message="规则组引用的 sop_level_id 不属于当前 SOP。",
                    fix_hint="改为当前 SOP 等级字典中的 sop_level_id。",
                )
            route_grain = rule.get("route_grain")
            if route_grain and process and route_grain not in route_grains:
                self.add(
                    severity="error",
                    category="sop_lint",
                    check_id="ROUTE_GRAIN_NOT_IN_PROCESS_OUTPUT",
                    table_name="SOP规则组表",
                    record_key=f"{sop_id}:{key}",
                    field_name="route_grain",
                    current_value=route_grain,
                    expected_value=sorted(route_grains),
                    message="route_grain 不在 process skill 输出契约中。",
                    fix_hint="改为 process 输出字段，或先扩展 process skill output_contract.route_grains。",
                )

    def _lint_report_policies(self, sop: dict[str, Any], sop_id: str, process: dict[str, Any] | None) -> None:
        for policy in [item for item in _as_list(sop.get("report_policies")) if isinstance(item, dict)]:
            key = str(policy.get("report_policy_id", "<missing>"))
            self.require(
                policy,
                ["report_policy_id", "report_type", "template_name", "sheet_policy", "report_target_policy", "sender_identity", "idempotency_policy", "enabled"],
                table_name="Report Publish Policy",
                record_key=f"{sop_id}:{key}",
                category="report_lint",
            )
            report_type = str(policy.get("report_type", ""))
            if report_type and report_type not in self.report_registry:
                self.add(
                    severity="error",
                    category="report_lint",
                    check_id="REPORT_POLICY_TYPE_NOT_REGISTERED",
                    table_name="Report Publish Policy",
                    record_key=f"{sop_id}:{key}",
                    field_name="report_type",
                    current_value=report_type,
                    expected_value=sorted(self.report_registry),
                    message="报告发布策略引用了未注册 report type。",
                    fix_hint="注册该 report type，或改用已注册报告类型。",
                )
            if process and report_type and report_type not in _as_list(process.get("supported_report_types")):
                self.add(
                    severity="error",
                    category="report_lint",
                    check_id="REPORT_POLICY_TYPE_NOT_SUPPORTED",
                    table_name="Report Publish Policy",
                    record_key=f"{sop_id}:{key}",
                    field_name="report_type",
                    current_value=report_type,
                    expected_value=process.get("supported_report_types"),
                    message="报告发布策略使用了 process skill 不支持的 report type。",
                    fix_hint="更新 process registry supported_report_types 或更换 report type。",
                )
            target = policy.get("report_target_policy") if isinstance(policy.get("report_target_policy"), dict) else {}
            if target.get("auto_send") is True and sop.get("run_mode") == "shadow":
                self.add(
                    severity="blocker",
                    category="touch_safety",
                    check_id="SHADOW_REPORT_AUTO_SEND",
                    table_name="Report Publish Policy",
                    record_key=f"{sop_id}:{key}",
                    field_name="report_target_policy.auto_send",
                    current_value=True,
                    expected_value=False,
                    message="shadow 模式禁止自动发送报告。",
                    fix_hint="将 auto_send 改为 false，或切到 canary/active 后再开启。",
                )

    def _lint_route_policies(self, sop: dict[str, Any], sop_id: str, process: dict[str, Any] | None) -> None:
        route_grains = set(_as_list((process or {}).get("output_contract", {}).get("route_grains")))
        for policy in [item for item in _as_list(sop.get("route_policies")) if isinstance(item, dict)]:
            key = str(policy.get("route_policy_id", "<missing>"))
            self.require(
                policy,
                ["route_policy_id", "route_grain", "route_key_fields", "owner_source_id", "fallback_policy", "enabled"],
                table_name="SOP路由策略表",
                record_key=f"{sop_id}:{key}",
                category="route_lint",
            )
            owner_source_id = str(policy.get("owner_source_id", ""))
            if owner_source_id and owner_source_id not in self.owner_sources:
                self.add(
                    severity="error",
                    category="route_lint",
                    check_id="OWNER_SOURCE_NOT_REGISTERED",
                    table_name="SOP路由策略表",
                    record_key=f"{sop_id}:{key}",
                    field_name="owner_source_id",
                    current_value=owner_source_id,
                    expected_value=sorted(self.owner_sources),
                    message="路由策略引用了未注册 Owner Source。",
                    fix_hint="先在 Owner Source Registry 注册该来源。",
                )
            route_grain = policy.get("route_grain")
            if route_grain and process and route_grain not in route_grains:
                self.add(
                    severity="error",
                    category="route_lint",
                    check_id="ROUTE_POLICY_GRAIN_NOT_IN_PROCESS_OUTPUT",
                    table_name="SOP路由策略表",
                    record_key=f"{sop_id}:{key}",
                    field_name="route_grain",
                    current_value=route_grain,
                    expected_value=sorted(route_grains),
                    message="路由策略的 route_grain 不在 process skill 输出契约中。",
                    fix_hint="修改 route_grain 或扩展 process 输出契约。",
                )


def validation_report(config: dict[str, Any], *, mode: str | None = None, sop_id: str | None = None) -> dict[str, Any]:
    linter = ConfigLinter(config)
    findings = linter.lint()
    blocker_count = sum(1 for item in findings if item.severity == "blocker")
    error_count = sum(1 for item in findings if item.severity == "error")
    warning_count = sum(1 for item in findings if item.severity == "warning")
    status = "failed" if blocker_count or error_count else "passed"
    return {
        "schema_version": "validation_report.v1",
        "mode": mode or config.get("mode") or "manual",
        "scope": {
            "sop_id": sop_id,
        },
        "summary": {
            "status": status,
            "blocker_count": blocker_count,
            "error_count": error_count,
            "warning_count": warning_count,
            "finding_count": len(findings),
        },
        "findings": [item.to_dict() for item in findings],
    }


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint SOP-first monitoring configuration.")
    parser.add_argument("--config", required=True, type=Path, help="Path to SOP-first JSON configuration.")
    parser.add_argument("--mode", help="Validation mode label.")
    parser.add_argument("--sop-id", help="Optional SOP scope label for the report.")
    parser.add_argument("--output", type=Path, help="Optional path to write validation report JSON.")
    args = parser.parse_args()

    report = validation_report(load_config(args.config), mode=args.mode, sop_id=args.sop_id)
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if report["summary"]["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
