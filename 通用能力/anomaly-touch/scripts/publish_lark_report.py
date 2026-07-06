#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Publish analysis run artifacts to Lark spreadsheet + Lark card."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from report_publisher import REPORT_TYPES, publish_report
from report_policy import load_config, publish_report_from_policy


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish a standard analysis result directory to Lark.")
    parser.add_argument("--run-dir", required=True, type=Path, help="Analysis result directory containing summary.json.")
    parser.add_argument("--report-type", choices=sorted(REPORT_TYPES))
    parser.add_argument("--policy-file", type=Path, help="SOP-first config JSON containing report policies.")
    parser.add_argument("--sop-id", help="SOP id used with --policy-file.")
    parser.add_argument("--policy-id", help="Report policy id used with --policy-file.")
    parser.add_argument("--run-id", help="Run id used by policy templates.")
    parser.add_argument("--output-dir", type=Path, help="Where to write rendered card and publish summary. Defaults to run-dir.")
    parser.add_argument("--sheet-url", help="Reuse an existing Lark spreadsheet URL instead of importing workbook.")
    parser.add_argument("--sheet-name", help="Spreadsheet name when importing a workbook.")
    parser.add_argument("--target-user", help="Send card to user open_id (ou_xxx). Mutually exclusive with --target-chat.")
    parser.add_argument("--target-chat", help="Send card to chat_id (oc_xxx). Mutually exclusive with --target-user.")
    parser.add_argument("--identity", choices=["bot", "user"], default="bot", help="Lark sender identity. Defaults to bot.")
    parser.add_argument("--top-n", type=int, default=10, help="TopN rows shown in card table.")
    parser.add_argument("--level", choices=["P0", "P1", "P2", "notice"], help="Required for low_efficiency_level_detail.")
    parser.add_argument("--title", help="Override card title.")
    parser.add_argument("--dry-run", action="store_true", help="Render only; do not import spreadsheet or send message.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.policy_file:
        if not args.sop_id:
            raise SystemExit("--sop-id is required when --policy-file is used")
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
    else:
        if not args.report_type:
            raise SystemExit("--report-type is required unless --policy-file is used")
        result = publish_report(
            run_dir=args.run_dir,
            report_type=args.report_type,
            output_dir=args.output_dir,
            sheet_url=args.sheet_url,
            sheet_name=args.sheet_name,
            target_user=args.target_user,
            target_chat=args.target_chat,
            identity=args.identity,
            top_n=args.top_n,
            level=args.level,
            title=args.title,
            dry_run=args.dry_run,
        )
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
