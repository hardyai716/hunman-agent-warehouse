#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run a controlled low-efficiency production-flow integration test.

The script uses existing analysis/touch artifacts and writes a production-like
event + touch record into a configured Lark Base. It is deliberately explicit:
the Base token must come from an environment variable or CLI arg and is never
stored in repository files.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ANOMALY_TOUCH_SCRIPTS = PROJECT_ROOT / "通用能力" / "anomaly-touch" / "scripts"
sys.path.insert(0, str(ANOMALY_TOUCH_SCRIPTS))

from base_writeback import BaseWritebackClient, BaseWritebackLogger, masked_token, write_json  # noqa: E402


DEFAULT_PROCESS_RUN_DIR = PROJECT_ROOT / "dist/analysis_results/low_efficiency_shadow_current_20260706_232031"
DEFAULT_ROUTE_RESULTS = PROJECT_ROOT / "dist/production_rollout/low_efficiency_20260706_2325/canary_p2_single_user_20260706_233053/route_results.json"
DEFAULT_TOUCH_RECORDS = PROJECT_ROOT / "dist/production_rollout/low_efficiency_20260706_2325/formal_touch_p2_20260706_234431/sent/touch_records.jsonl"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "dist/production_rollout/original_base_writeback_20260707/integration_flow"
DEFAULT_EVENT_TABLE_ID = "tblHOC5Y8j58xDYQ"
DEFAULT_TOUCH_TABLE_ID = "tbl39ZotgZJ8Q8aL"
DEFAULT_LEVEL = "P2"
DEFAULT_PERIOD = "2026-06-29~2026-07-05"


def utc_now_text() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_base_datetime() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        return [dict(row) for row in csv.DictReader(file)]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def float_value(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def choose_touch_record(records: list[dict[str, Any]]) -> dict[str, Any]:
    sent = [record for record in records if record.get("send_status") == "sent"]
    if sent:
        return sent[0]
    if records:
        return records[0]
    raise ValueError("touch_records.jsonl is empty")


def build_route_group(route_results: list[dict[str, Any]]) -> dict[str, Any]:
    routed = [route for route in route_results if not route.get("missing_object_owner")]
    if not routed:
        raise ValueError("route_results contains no routed rows")
    route_keys = [route.get("business_object", {}).get("route_key") for route in routed]
    owners: dict[str, str] = {}
    for route in routed:
        for owner in route.get("owners", []) if isinstance(route.get("owners"), list) else []:
            if isinstance(owner, dict) and owner.get("id"):
                owners[str(owner["id"])] = str(owner.get("name", owner["id"]))
    return {
        "route_count": len(routed),
        "route_keys": [key for key in route_keys if key],
        "owners": owners,
        "route_result_id": "route_group:" + ",".join(sorted(str(key) for key in route_keys if key)[:5]),
        "route_snapshot": routed,
    }


def build_writeback_payloads(
    *,
    hits: list[dict[str, Any]],
    route_group: dict[str, Any],
    touch_record: dict[str, Any],
    run_id: str,
    level: str,
    period: str,
    config_version: str,
    idempotency_prefix: str,
) -> tuple[dict[str, Any], dict[str, Any], list[list[Any]], str]:
    target = touch_record.get("target_chat") or touch_record.get("target_user") or "unknown_target"
    route_group_key = str(route_group["route_result_id"])
    idempotency_key = f"{idempotency_prefix}:{run_id}:{level}:{target}:{route_group_key}"
    total_avg_in = sum(float_value(row.get("avg_jinshen")) for row in hits)
    min_rate = min((float_value(row.get("ratio_val")) for row in hits), default=0)
    business_object = f"{level}:{route_group['route_count']} reasons"
    node_trace = [
        {"node": "analysis", "status": "completed", "hit_count": len(hits), "at": utc_now_text()},
        {"node": "owner_routing", "status": "completed", "route_count": route_group["route_count"], "at": utc_now_text()},
        {"node": "formal_touch", "status": touch_record.get("send_status"), "message_id": touch_record.get("message_id"), "at": touch_record.get("sent_at") or utc_now_text()},
        {"node": "base_writeback", "status": "running", "at": utc_now_text()},
    ]

    event_fields = {
        "事件标题": f"{period} {level} 低效 reason 正式触达",
        "当前状态": "处理中",
        "业务对象": business_object,
        "场景/范围": "low_efficiency_labeling",
        "当前值": round(total_avg_in, 4),
        "影响说明": f"{level} 命中 {len(hits)} 条 reason，最低打标率 {min_rate * 100:.2f}%。",
        "路由触达摘要": f"{period} {level} 触达 {route_group['route_count']} 条 reason，message_id={touch_record.get('message_id')}",
        "最近触达时间": now_base_datetime(),
        "sop_id": "low_efficiency_labeling",
        "run_id": run_id,
        "node_trace": json.dumps(node_trace, ensure_ascii=False),
        "rule_group_id": "rule_low_label_rate_p2" if level == "P2" else f"rule_low_label_rate_{level.lower()}",
        "config_version": config_version,
        "route_result": json.dumps(route_group["route_snapshot"], ensure_ascii=False),
    }
    event_dedupe_conditions = [
        ["sop_id", "==", "low_efficiency_labeling"],
        ["run_id", "==", run_id],
        ["业务对象", "==", business_object],
        ["rule_group_id", "==", event_fields["rule_group_id"]],
    ]

    target_user = touch_record.get("target_user")
    touch_fields = {
        "触达标题": f"{period} {level} 低效 reason 正式触达",
        "触达内容": f"命中 {len(hits)} 条 reason；幂等键 {idempotency_key}",
        "触达渠道": "飞书群" if touch_record.get("target_chat") else "私聊",
        "群聊ID": touch_record.get("chat_id") or touch_record.get("target_chat") or "",
        "消息ID": touch_record.get("message_id") or "",
        "触达状态": "已发送" if touch_record.get("send_status") == "sent" else "待发送",
        "触达时间": now_base_datetime(),
        "是否需要人工确认": False,
        "idempotency_key": idempotency_key,
        "card_hash": touch_record.get("card_hash") or "card_hash_recorded_in_card_meta",
        "sop_id": "low_efficiency_labeling",
        "run_id": run_id,
        "route_result_id": route_group_key,
    }
    if target_user:
        touch_fields["触达对象"] = [{"id": target_user}]
    return event_fields, touch_fields, event_dedupe_conditions, idempotency_key


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run low-efficiency production integration writeback test.")
    parser.add_argument("--base-token", help="Real Lark Base token. Prefer --base-token-env.")
    parser.add_argument("--base-token-env", default="HUMAN_REVIEW_BASE_TOKEN")
    parser.add_argument("--event-table-id", default=DEFAULT_EVENT_TABLE_ID)
    parser.add_argument("--touch-table-id", default=DEFAULT_TOUCH_TABLE_ID)
    parser.add_argument("--process-run-dir", type=Path, default=DEFAULT_PROCESS_RUN_DIR)
    parser.add_argument("--route-results", type=Path, default=DEFAULT_ROUTE_RESULTS)
    parser.add_argument("--touch-records", type=Path, default=DEFAULT_TOUCH_RECORDS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--run-id", default="LOW-EFF-PROD-INTEGRATION-20260707")
    parser.add_argument("--level", default=DEFAULT_LEVEL)
    parser.add_argument("--period", default=DEFAULT_PERIOD)
    parser.add_argument("--config-version", default="original_base_integration_20260707")
    parser.add_argument("--idempotency-prefix", default="low_efficiency_labeling")
    parser.add_argument("--dry-run", action="store_true", help="Only write planned payloads; do not call Lark Base.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    base_token = args.base_token or os.environ.get(args.base_token_env)
    if not base_token and not args.dry_run:
        raise SystemExit(f"missing base token; pass --base-token or set {args.base_token_env}")

    hits_path = args.process_run_dir / f"{args.level}.csv"
    hits = read_csv(hits_path)
    routes_payload = read_json(args.route_results)
    route_group = build_route_group(routes_payload.get("route_results", []))
    touch_record = choose_touch_record(read_jsonl(args.touch_records))
    event_fields, touch_fields, event_dedupe_conditions, idempotency_key = build_writeback_payloads(
        hits=hits,
        route_group=route_group,
        touch_record=touch_record,
        run_id=args.run_id,
        level=args.level,
        period=args.period,
        config_version=args.config_version,
        idempotency_prefix=args.idempotency_prefix,
    )
    write_json(args.output_dir / "planned_event_fields.json", event_fields)
    write_json(args.output_dir / "planned_touch_fields.json", touch_fields)

    summary: dict[str, Any] = {
        "schema_version": "low_efficiency_production_integration.v1",
        "generated_at": utc_now_text(),
        "dry_run": args.dry_run,
        "base_token_masked": masked_token(base_token or ""),
        "event_table_id": args.event_table_id,
        "touch_table_id": args.touch_table_id,
        "hits": str(hits_path),
        "route_results": str(args.route_results),
        "touch_records": str(args.touch_records),
        "run_id": args.run_id,
        "idempotency_key": idempotency_key,
        "hit_count": len(hits),
        "route_count": route_group["route_count"],
    }

    if args.dry_run:
        summary["status"] = "planned"
        write_json(args.output_dir / "integration_summary.json", summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    logger = BaseWritebackLogger(args.output_dir / "writeback_idempotency.log.jsonl")
    client = BaseWritebackClient(base_token=base_token or "", output_dir=args.output_dir, logger=logger)
    event_record_id, event_action = client.upsert_event(
        table_id=args.event_table_id,
        event_fields=event_fields,
        dedupe_conditions=event_dedupe_conditions,
        label_prefix="integration_event",
    )
    touch_fields["关联事件"] = [{"id": event_record_id}]
    touch_record_id, touch_action = client.upsert_touch_record(
        table_id=args.touch_table_id,
        idempotency_key=idempotency_key,
        touch_fields=touch_fields,
        label_prefix="integration_touch",
    )
    event_update_fields = {
        "当前状态": "处理中",
        "触达记录": [{"id": touch_record_id}],
        "最近触达时间": now_base_datetime(),
        "路由触达摘要": f"{args.period} {args.level} 触达写回完成，touch_record={touch_record_id}",
    }
    client.update_record(
        table_id=args.event_table_id,
        record_id=event_record_id,
        fields=event_update_fields,
        label="integration_event_link_touch",
    )
    summary.update(
        {
            "status": "passed",
            "event_record_id": event_record_id,
            "event_action": event_action,
            "touch_record_id": touch_record_id,
            "touch_action": touch_action,
            "writeback_log": str(args.output_dir / "writeback_idempotency.log.jsonl"),
        }
    )
    write_json(args.output_dir / "integration_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
