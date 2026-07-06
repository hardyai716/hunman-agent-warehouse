#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Report publish policy adapter.

This module maps SOP-first report policy configuration to the existing
report_publisher.publish_report primitive. It keeps the current CLI-compatible
publisher intact while allowing monitoring-orchestrator to call report
publishing by policy id.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from report_publisher import PublishResult, publish_report


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def find_sop(config: dict[str, Any], sop_id: str) -> dict[str, Any]:
    for sop in config.get("sops", []):
        if isinstance(sop, dict) and sop.get("sop_id") == sop_id:
            return sop
    raise KeyError(f"sop_id not found: {sop_id}")


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
    default_type = sop.get("default_report_type")
    for policy in policies:
        if policy.get("report_type") == default_type:
            return policy
    raise KeyError(f"no enabled report policy found for sop={sop.get('sop_id')}")


def format_sheet_name(template: str | None, *, sop: dict[str, Any], report_type: str, level: str | None, run_id: str | None) -> str | None:
    if not template:
        return None
    return template.format(
        sop_id=sop.get("sop_id", ""),
        sop_name=sop.get("sop_name", ""),
        report_type=report_type,
        level=level or "",
        run_id=run_id or "",
        period="{period}",
    )


def publish_report_from_policy(
    *,
    config: dict[str, Any],
    sop_id: str,
    run_dir: Path,
    policy_id: str | None = None,
    report_type: str | None = None,
    output_dir: Path | None = None,
    sheet_url: str | None = None,
    target_user: str | None = None,
    target_chat: str | None = None,
    run_id: str | None = None,
    dry_run: bool = False,
) -> PublishResult:
    sop = find_sop(config, sop_id)
    policy = find_report_policy(sop, policy_id, report_type)
    resolved_report_type = str(policy["report_type"])
    render_options = policy.get("render_options") if isinstance(policy.get("render_options"), dict) else {}
    sheet_policy = policy.get("sheet_policy") if isinstance(policy.get("sheet_policy"), dict) else {}
    target_policy = policy.get("report_target_policy") if isinstance(policy.get("report_target_policy"), dict) else {}

    resolved_target_user = target_user
    resolved_target_chat = target_chat
    target_ref = target_policy.get("target_ref")
    if not resolved_target_user and not resolved_target_chat and target_policy.get("auto_send") and target_ref:
        if str(target_ref).startswith("oc_"):
            resolved_target_chat = str(target_ref)
        else:
            resolved_target_user = str(target_ref)

    # Policy-level auto_send=false is authoritative for shadow/report-only
    # usage. Runtime callers can still force dry_run=True for safety.
    effective_dry_run = dry_run or not bool(target_policy.get("auto_send", False))
    level = policy.get("level_selector")
    title = policy.get("title_template")
    sheet_name = format_sheet_name(
        sheet_policy.get("sheet_name_template"),
        sop=sop,
        report_type=resolved_report_type,
        level=level,
        run_id=run_id,
    )

    return publish_report(
        run_dir=run_dir,
        report_type=resolved_report_type,
        output_dir=output_dir,
        sheet_url=sheet_url,
        sheet_name=sheet_name,
        target_user=resolved_target_user,
        target_chat=resolved_target_chat,
        identity=policy.get("sender_identity", "bot"),
        top_n=int(render_options.get("top_n", 10)),
        level=level,
        title=title,
        dry_run=effective_dry_run,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish a report using SOP-first report policy.")
    parser.add_argument("--policy-file", required=True, type=Path)
    parser.add_argument("--sop-id", required=True)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--policy-id")
    parser.add_argument("--report-type")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--sheet-url")
    parser.add_argument("--target-user")
    parser.add_argument("--target-chat")
    parser.add_argument("--run-id")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = publish_report_from_policy(
        config=load_config(args.policy_file),
        sop_id=args.sop_id,
        run_dir=args.run_dir,
        policy_id=args.policy_id,
        report_type=args.report_type,
        output_dir=args.output_dir,
        sheet_url=args.sheet_url,
        target_user=args.target_user,
        target_chat=args.target_chat,
        run_id=args.run_id,
        dry_run=args.dry_run,
    )
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
