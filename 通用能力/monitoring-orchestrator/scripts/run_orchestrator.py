#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SOP-first monitoring orchestrator MVP.

MVP scope:
- manual/report_only/shadow only;
- config lint;
- process artifact validation;
- report publishing through anomaly-touch report policy adapter;
- optional owner-routing route preview;
- run summary and audit JSONL.

No event-table writes, no touch records, no group creation and no formal POC
messages are performed by this script.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_PATH = Path(__file__).resolve()
SKILL_DIR = SCRIPT_PATH.parents[1]
SKILLS_DIR = SKILL_DIR.parent

sys.path.insert(0, str(SKILLS_DIR / "review-monitoring-shared" / "scripts"))
sys.path.insert(0, str(SKILLS_DIR / "anomaly-touch" / "scripts"))
sys.path.insert(0, str(SKILLS_DIR / "owner-routing" / "scripts"))

from config_linter import load_config, validation_report  # noqa: E402
from report_policy import publish_report_from_policy  # noqa: E402
from route_owner import route_hits  # noqa: E402


ALLOWED_MVP_RUN_MODES = {"manual", "report_only", "shadow"}
LIVE_SIDE_EFFECT_RUN_MODES = {"canary", "active", "touch_execute"}
SUPPORTED_RUN_MODES = ALLOWED_MVP_RUN_MODES | LIVE_SIDE_EFFECT_RUN_MODES
SHADOW_COMPARE_RUN_MODES = {"report_only", "shadow"}
TOP_REASON_FIELDS = ("reason", "strategy", "route_key", "business_object", "queue", "scene")
LEVEL_FIELDS = ("_level", "level", "level_label", "sop_level_id")
LIVE_MODE_REQUIRED_ACTIONS = [
    "Configure platform-side Lark/Aeolus credentials for the production identity.",
    "Validate production SOP/report/touch configuration and target allowlists.",
    "Enable a manual production authorization switch before running live side-effect modes.",
    "Use report_only or shadow until production authorization is complete.",
]


def utc_now_text() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_run_id(sop_id: str) -> str:
    return f"{sop_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"


def live_mode_error_message(run_mode: str) -> str:
    return (
        f"Live side-effect run mode '{run_mode}' is blocked in the current MVP. "
        "Production execution requires platform-side Lark/Aeolus credentials, "
        "validated production configuration, and a manual enable switch / production authorization. "
        "Use report_only or shadow for offline-safe validation."
    )


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_audit(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def find_sop(config: dict[str, Any], sop_id: str) -> dict[str, Any]:
    for sop in config.get("sops", []):
        if isinstance(sop, dict) and sop.get("sop_id") == sop_id:
            return sop
    raise KeyError(f"sop_id not found: {sop_id}")


def find_process(config: dict[str, Any], process_skill: str) -> dict[str, Any]:
    for item in config.get("process_skill_registry", []):
        if isinstance(item, dict) and item.get("process_skill") == process_skill:
            return item
    raise KeyError(f"process_skill not found: {process_skill}")


def find_report_policy(sop: dict[str, Any], policy_id: str | None, report_type: str | None) -> dict[str, Any]:
    policies = [item for item in sop.get("report_policies", []) if isinstance(item, dict) and item.get("enabled", True)]
    if policy_id:
        for policy in policies:
            if policy.get("report_policy_id") == policy_id:
                return policy
        raise KeyError(f"report_policy_id not found: {policy_id}")
    if report_type:
        for policy in policies:
            if policy.get("report_type") == report_type:
                return policy
    for policy in policies:
        if policy.get("report_type") == sop.get("default_report_type"):
            return policy
    raise KeyError("no enabled report policy found")


def required_files_for_report(process: dict[str, Any], report_type: str, level: str | None) -> list[str]:
    contract = process.get("output_contract") if isinstance(process.get("output_contract"), dict) else {}
    required_by_type = contract.get("required_files_by_report_type") if isinstance(contract.get("required_files_by_report_type"), dict) else {}
    patterns = required_by_type.get(report_type, ["summary.json"])
    return [str(item).format(level=level or "") for item in patterns]


def validate_process_artifacts(run_dir: Path, required_files: list[str]) -> list[str]:
    missing = []
    for rel in required_files:
        if "{level}" in rel:
            missing.append(rel)
            continue
        if not (run_dir / rel).exists():
            missing.append(rel)
    return missing


def read_csv_hits(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        rows = [dict(row) for row in csv.DictReader(file)]
    return rows[:limit] if limit else rows


def infer_hits_file(run_dir: Path, report_type: str, level: str | None) -> Path | None:
    if report_type == "low_efficiency_level_detail" and level:
        candidate = run_dir / f"{level}.csv"
        return candidate if candidate.exists() else None
    for name in ("综合.csv", "sheet1_mach_label_reason_detail.csv"):
        candidate = run_dir / name
        if candidate.exists():
            return candidate
    return None


def core_csv_rel_for_report(required_files: list[str], report_type: str, level: str | None) -> str | None:
    if report_type == "low_efficiency_level_detail" and level:
        return f"{level}.csv"
    if report_type == "low_efficiency_grading":
        return "综合.csv"
    if report_type == "low_efficiency_dimension_breakdown":
        return "sheet1_mach_label_reason_detail.csv"
    for rel in required_files:
        if rel.endswith(".csv") and "{" not in rel:
            return rel
    return None


def int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def compare_scalar(baseline: int | None, current: int | None) -> dict[str, Any]:
    delta = None if baseline is None or current is None else current - baseline
    return {"baseline": baseline, "current": current, "delta": delta}


def compare_count_maps(baseline: dict[str, int], current: dict[str, int]) -> dict[str, dict[str, int]]:
    result = {}
    for key in sorted(set(baseline) | set(current)):
        base_value = baseline.get(key, 0)
        current_value = current.get(key, 0)
        result[key] = {
            "baseline": base_value,
            "current": current_value,
            "delta": current_value - base_value,
        }
    return result


def read_summary_for_compare(run_dir: Path, label: str, warnings: list[str]) -> dict[str, Any] | None:
    path = run_dir / "summary.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        warnings.append(f"{label}_summary_missing: {path}")
        return None
    except json.JSONDecodeError as exc:
        warnings.append(f"{label}_summary_invalid_json: {path}: {exc}")
        return None
    if not isinstance(value, dict):
        warnings.append(f"{label}_summary_not_object: {path}")
        return None
    return value


def read_core_csv_for_compare(run_dir: Path, core_csv_rel: str | None, label: str, warnings: list[str]) -> list[dict[str, Any]] | None:
    if not core_csv_rel:
        warnings.append(f"{label}_core_csv_unresolved")
        return None
    path = run_dir / core_csv_rel
    try:
        return read_csv_hits(path)
    except FileNotFoundError:
        warnings.append(f"{label}_core_csv_missing: {path}")
        return None
    except csv.Error as exc:
        warnings.append(f"{label}_core_csv_invalid: {path}: {exc}")
        return None
    except UnicodeDecodeError as exc:
        warnings.append(f"{label}_core_csv_decode_failed: {path}: {exc}")
        return None


def level_counts_from_summary(summary: dict[str, Any] | None) -> dict[str, int]:
    if not summary:
        return {}
    levels = summary.get("levels")
    if not isinstance(levels, dict):
        return {}
    counts = {}
    for level, payload in levels.items():
        raw_count = payload.get("row_count") if isinstance(payload, dict) else payload
        count = int_or_none(raw_count)
        if count is not None:
            counts[str(level)] = count
    return counts


def count_rows_by_field(rows: list[dict[str, Any]] | None, fields: tuple[str, ...]) -> dict[str, int]:
    if rows is None:
        return {}
    field = next((candidate for candidate in fields if any(row.get(candidate) not in (None, "") for row in rows)), None)
    if not field:
        return {}
    counts: dict[str, int] = {}
    for row in rows:
        value = row.get(field)
        if value in (None, ""):
            continue
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return counts


def top_reason_values(rows: list[dict[str, Any]] | None, warnings: list[str], label: str, limit: int = 5) -> tuple[str | None, list[dict[str, Any]]]:
    if rows is None:
        return None, []
    field = next((candidate for candidate in TOP_REASON_FIELDS if any(row.get(candidate) not in (None, "") for row in rows)), None)
    if not field:
        warnings.append(f"{label}_top_reason_field_missing")
        return None, []
    counts: dict[str, int] = {}
    first_seen: dict[str, int] = {}
    for index, row in enumerate(rows):
        value = row.get(field)
        if value in (None, ""):
            continue
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
        first_seen.setdefault(key, index)
    ranked = sorted(counts, key=lambda key: (-counts[key], first_seen[key], key))
    return field, [{"reason": key, "count": counts[key]} for key in ranked[:limit]]


def build_artifact_profile(run_dir: Path, core_csv_rel: str | None, label: str, warnings: list[str]) -> dict[str, Any]:
    summary = read_summary_for_compare(run_dir, label, warnings)
    rows = read_core_csv_for_compare(run_dir, core_csv_rel, label, warnings)
    top_reason_field, top_reasons = top_reason_values(rows, warnings, label)
    level_counts = level_counts_from_summary(summary) or count_rows_by_field(rows, LEVEL_FIELDS)
    return {
        "run_dir": str(run_dir),
        "summary_path": str(run_dir / "summary.json"),
        "core_csv_path": str(run_dir / core_csv_rel) if core_csv_rel else None,
        "row_count": len(rows) if rows is not None else None,
        "top_reason_field": top_reason_field,
        "top_reasons": top_reasons,
        "level_counts": level_counts,
    }


def build_shadow_comparison(
    *,
    run_id: str,
    sop_id: str,
    run_mode: str,
    baseline_run_dir: Path,
    current_run_dir: Path,
    report_type: str,
    core_csv_rel: str | None,
) -> dict[str, Any]:
    warnings: list[str] = []
    baseline = build_artifact_profile(baseline_run_dir, core_csv_rel, "baseline", warnings)
    current = build_artifact_profile(current_run_dir, core_csv_rel, "current", warnings)

    row_count = compare_scalar(baseline["row_count"], current["row_count"])
    level_counts = compare_count_maps(baseline["level_counts"], current["level_counts"])
    baseline_top = baseline["top_reasons"][0]["reason"] if baseline["top_reasons"] else None
    current_top = current["top_reasons"][0]["reason"] if current["top_reasons"] else None
    top_reason_changed = baseline_top != current_top

    diff_items = []
    if row_count["delta"] is None:
        diff_items.append("row_count unavailable")
    elif row_count["delta"] == 0:
        diff_items.append("row_count unchanged")
    else:
        diff_items.append(f"row_count delta {row_count['delta']}")
    if baseline_top is None or current_top is None:
        diff_items.append("top_reason unavailable")
    elif top_reason_changed:
        diff_items.append(f"top_reason changed from {baseline_top} to {current_top}")
    else:
        diff_items.append(f"top_reason unchanged: {current_top}")
    changed_levels = [level for level, values in level_counts.items() if values["delta"] != 0]
    if changed_levels:
        diff_items.append(f"level_counts changed: {', '.join(changed_levels)}")
    else:
        diff_items.append("level_counts unchanged")
    if warnings:
        diff_items.append(f"{len(warnings)} warning(s) while reading comparison artifacts")

    status = "warning" if warnings else ("different" if row_count["delta"] or top_reason_changed or changed_levels else "matched")
    return {
        "schema_version": "shadow_comparison.v1",
        "run_id": run_id,
        "sop_id": sop_id,
        "run_mode": run_mode,
        "report_type": report_type,
        "generated_at": utc_now_text(),
        "baseline": baseline,
        "current": current,
        "row_count": row_count,
        "top_reason": {
            "baseline": baseline_top,
            "current": current_top,
            "changed": top_reason_changed,
            "baseline_top_reasons": baseline["top_reasons"],
            "current_top_reasons": current["top_reasons"],
        },
        "level_counts": level_counts,
        "warnings": warnings,
        "diff_summary": {
            "status": status,
            "items": diff_items,
        },
    }


class OrchestratorRun:
    def __init__(
        self,
        *,
        config_path: Path,
        config: dict[str, Any],
        sop_id: str,
        run_mode: str,
        process_run_dir: Path,
        output_dir: Path,
        run_id: str,
        dry_run: bool,
        report_policy_id: str | None,
        report_type: str | None,
        route_preview: bool,
        baseline_run_dir: Path | None,
    ) -> None:
        self.config_path = config_path
        self.config = config
        self.sop_id = sop_id
        self.run_mode = run_mode
        self.process_run_dir = process_run_dir.resolve()
        self.baseline_run_dir = baseline_run_dir.resolve() if baseline_run_dir else None
        self.output_dir = output_dir.resolve()
        self.run_id = run_id
        self.dry_run = dry_run
        self.report_policy_id = report_policy_id
        self.report_type = report_type
        self.route_preview = route_preview
        self.audit_path = self.output_dir / "run_audit.jsonl"
        self.summary_path = self.output_dir / "run_summary.json"

    def audit(self, node_type: str, node_status: str, **extra: Any) -> None:
        append_audit(
            self.audit_path,
            {
                "audit_version": "orchestrator-audit-v1",
                "run_id": self.run_id,
                "sop_id": self.sop_id,
                "run_mode": self.run_mode,
                "node_type": node_type,
                "node_status": node_status,
                "timestamp": utc_now_text(),
                **extra,
            },
        )

    def run(self) -> dict[str, Any]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if self.run_mode in LIVE_SIDE_EFFECT_RUN_MODES:
            message = live_mode_error_message(self.run_mode)
            self.audit(
                "live_mode_guard",
                "blocked",
                stop_reason="live_mode_requires_production_authorization",
                error_message=message,
                required_actions=LIVE_MODE_REQUIRED_ACTIONS,
            )
            summary = self._summary(
                "blocked",
                stop_reason="live_mode_requires_production_authorization",
                error_message=message,
                required_actions=LIVE_MODE_REQUIRED_ACTIONS,
                live_mode_status={
                    "requested_run_mode": self.run_mode,
                    "authorized": False,
                    "mvp_supported": False,
                    "safe_alternatives": sorted(ALLOWED_MVP_RUN_MODES),
                },
            )
            write_json(self.summary_path, summary)
            return summary
        if self.run_mode not in ALLOWED_MVP_RUN_MODES:
            raise ValueError(f"MVP run_mode must be one of {sorted(SUPPORTED_RUN_MODES)}")

        self.audit("config_load", "success", input_ref=str(self.config_path))
        sop = find_sop(self.config, self.sop_id)
        process = find_process(self.config, str(sop.get("process_skill")))
        policy = find_report_policy(sop, self.report_policy_id, self.report_type)
        resolved_report_type = str(policy["report_type"])
        level = policy.get("level_selector")

        report = validation_report(self.config, mode=self.run_mode, sop_id=self.sop_id)
        validation_path = self.output_dir / "validation_report.json"
        write_json(validation_path, report)
        if report["summary"]["status"] != "passed":
            self.audit("config_lint", "blocked", output_ref=str(validation_path), summary=report["summary"])
            summary = self._summary("blocked", validation_report=str(validation_path), stop_reason="config_lint_failed")
            write_json(self.summary_path, summary)
            return summary
        self.audit("config_lint", "success", output_ref=str(validation_path), summary=report["summary"])

        if not (self.process_run_dir / "summary.json").exists():
            self.audit("data_ready_gate", "blocked", input_ref=str(self.process_run_dir), stop_reason="summary_json_missing")
            summary = self._summary("blocked", stop_reason="summary_json_missing")
            write_json(self.summary_path, summary)
            return summary
        self.audit("data_ready_gate", "success", input_ref=str(self.process_run_dir / "summary.json"))

        required_files = required_files_for_report(process, resolved_report_type, level)
        missing = validate_process_artifacts(self.process_run_dir, required_files)
        if missing:
            self.audit("process_analysis", "blocked", input_ref=str(self.process_run_dir), missing_files=missing)
            summary = self._summary("blocked", stop_reason="process_artifacts_missing", missing_files=missing)
            write_json(self.summary_path, summary)
            return summary
        self.audit("process_analysis", "success", input_ref=str(self.process_run_dir), required_files=required_files)

        shadow_comparison_path = None
        if self.baseline_run_dir and self.run_mode in SHADOW_COMPARE_RUN_MODES:
            core_csv_rel = core_csv_rel_for_report(required_files, resolved_report_type, level)
            if not core_csv_rel:
                current_hits = infer_hits_file(self.process_run_dir, resolved_report_type, level)
                if current_hits:
                    core_csv_rel = str(current_hits.relative_to(self.process_run_dir))
            comparison = build_shadow_comparison(
                run_id=self.run_id,
                sop_id=self.sop_id,
                run_mode=self.run_mode,
                baseline_run_dir=self.baseline_run_dir,
                current_run_dir=self.process_run_dir,
                report_type=resolved_report_type,
                core_csv_rel=core_csv_rel,
            )
            shadow_comparison_path = self.output_dir / "shadow_comparison.json"
            write_json(shadow_comparison_path, comparison)
            node_status = "warning" if comparison["warnings"] else "success"
            self.audit(
                "shadow_comparison",
                node_status,
                input_ref={
                    "baseline_run_dir": str(self.baseline_run_dir),
                    "current_run_dir": str(self.process_run_dir),
                },
                output_ref=str(shadow_comparison_path),
                summary=comparison["diff_summary"],
                warnings=comparison["warnings"],
            )
        elif self.baseline_run_dir:
            self.audit(
                "shadow_comparison",
                "skipped",
                input_ref=str(self.baseline_run_dir),
                stop_reason=f"run_mode_not_in_{sorted(SHADOW_COMPARE_RUN_MODES)}",
            )

        route_result_path = None
        if self.route_preview:
            hits_file = infer_hits_file(self.process_run_dir, resolved_report_type, level)
            if hits_file:
                routes = route_hits(self.config, self.sop_id, read_csv_hits(hits_file), run_id=self.run_id)
                route_result_path = self.output_dir / "route_results.json"
                write_json(route_result_path, routes)
                self.audit("owner_routing", "success", input_ref=str(hits_file), output_ref=str(route_result_path), summary=routes["summary"])
            else:
                self.audit("owner_routing", "skipped", stop_reason="no_supported_hits_file")

        publish = publish_report_from_policy(
            config=self.config,
            sop_id=self.sop_id,
            run_dir=self.process_run_dir,
            policy_id=self.report_policy_id,
            report_type=self.report_type,
            output_dir=self.output_dir,
            run_id=self.run_id,
            dry_run=True if self.run_mode in {"report_only", "shadow"} else self.dry_run,
        )
        self.audit("report_publish", "success", output_ref=publish.card_json, publish_result=publish.__dict__)

        summary = self._summary(
            "completed",
            process_run_dir=str(self.process_run_dir),
            validation_report=str(validation_path),
            publish_result=publish.__dict__,
            route_results=str(route_result_path) if route_result_path else None,
            baseline_run_dir=str(self.baseline_run_dir) if self.baseline_run_dir else None,
            shadow_comparison=str(shadow_comparison_path) if shadow_comparison_path else None,
        )
        write_json(self.summary_path, summary)
        self.audit("audit_finalize", "success", output_ref=str(self.summary_path))
        return summary

    def _summary(self, run_status: str, **extra: Any) -> dict[str, Any]:
        return {
            "schema_version": "orchestrator_run_summary.v1",
            "run_id": self.run_id,
            "sop_id": self.sop_id,
            "run_mode": self.run_mode,
            "run_status": run_status,
            "dry_run": self.dry_run,
            "audit_log_path": str(self.audit_path),
            **extra,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run SOP-first monitoring orchestrator MVP.")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--sop-id", required=True)
    parser.add_argument("--run-mode", required=True, choices=sorted(SUPPORTED_RUN_MODES))
    parser.add_argument("--process-run-dir", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--report-policy-id")
    parser.add_argument("--report-type")
    parser.add_argument("--route-preview", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--baseline-run-dir", type=Path)
    args = parser.parse_args()

    run_id = args.run_id or default_run_id(args.sop_id)
    output_dir = args.output_dir or (args.process_run_dir / "orchestrator" / run_id)
    run = OrchestratorRun(
        config_path=args.config,
        config=load_config(args.config),
        sop_id=args.sop_id,
        run_mode=args.run_mode,
        process_run_dir=args.process_run_dir,
        output_dir=output_dir,
        run_id=run_id,
        dry_run=args.dry_run,
        report_policy_id=args.report_policy_id,
        report_type=args.report_type,
        route_preview=args.route_preview,
        baseline_run_dir=args.baseline_run_dir,
    )
    summary = run.run()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["run_status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
