#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Formal event touch sender for routed low-efficiency hits.

This script is intentionally narrower than report publishing:
- input is hit rows plus route_results.json;
- output is one or more event touch cards and local touch records;
- it does not write the production event table or touch-record table directly.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from report_publisher import safe_idempotency_key, send_card, strip_internal_keys, write_json

import sys  # noqa: E402

SCRIPT_PATH = Path(__file__).resolve()
SKILL_DIR = SCRIPT_PATH.parents[1]
SKILLS_DIR = SKILL_DIR.parent
sys.path.insert(0, str(SKILLS_DIR / "review-monitoring-shared" / "scripts"))

from card_validator import compute_hits_hash, embed_hash_in_card, verify_card_hash, verify_route_chat_id, verify_route_match  # noqa: E402


@dataclass(frozen=True)
class TouchGroup:
    group_key: str
    target_user: str | None
    target_chat: str | None
    route_chat_id: str | None
    owner_names: list[str]
    route_results: list[dict[str, Any]]
    hits: list[dict[str, Any]]


def utc_now_text() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        return [dict(row) for row in csv.DictReader(file)]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def float_value(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def int_text(value: Any) -> str:
    try:
        return f"{int(round(float(value))):,}"
    except (TypeError, ValueError):
        return str(value)


def pct_text(value: Any) -> str:
    return f"{float_value(value) * 100:.2f}%"


def load_route_results(path: Path) -> list[dict[str, Any]]:
    payload = read_json(path)
    routes = payload.get("route_results")
    if not isinstance(routes, list):
        raise ValueError("route_results.json must contain route_results[]")
    return [item for item in routes if isinstance(item, dict)]


def validate_routes(routes: list[dict[str, Any]], *, require_all_routed: bool) -> None:
    missing = [route for route in routes if route.get("missing_object_owner")]
    if missing and require_all_routed:
        sample = [route.get("business_object", {}).get("route_key") for route in missing[:5]]
        raise ValueError(f"{len(missing)} route(s) missing owner; sample={sample}")


def group_hits(hits: list[dict[str, Any]], routes: list[dict[str, Any]], *, target_allowlist: set[str] | None) -> list[TouchGroup]:
    if len(hits) != len(routes):
        raise ValueError(f"hit count and route count mismatch: hits={len(hits)}, routes={len(routes)}")

    groups: dict[str, dict[str, Any]] = {}
    for hit, route in zip(hits, routes):
        if route.get("missing_object_owner"):
            continue
        delivery = route.get("delivery_policy") if isinstance(route.get("delivery_policy"), dict) else {}
        owners = route.get("owners") if isinstance(route.get("owners"), list) else []
        target_chat = delivery.get("chat_id")
        target_user = None
        if not target_chat:
            for owner in owners:
                if isinstance(owner, dict) and owner.get("id"):
                    target_user = str(owner["id"])
                    break
        if not target_chat and not target_user:
            raise ValueError(f"route has no target chat or owner user: {route.get('hit_id')}")
        target = str(target_chat or target_user)
        if target_allowlist is not None and target not in target_allowlist:
            raise ValueError(f"target {target} is not in allowlist")
        key = f"chat:{target_chat}" if target_chat else f"user:{target_user}"
        bucket = groups.setdefault(
            key,
            {
                "target_chat": str(target_chat) if target_chat else None,
                "target_user": str(target_user) if target_user else None,
                "route_chat_id": str(target_chat) if target_chat else None,
                "owner_names": [],
                "routes": [],
                "hits": [],
            },
        )
        for owner in owners:
            if isinstance(owner, dict) and owner.get("name") and str(owner["name"]) not in bucket["owner_names"]:
                bucket["owner_names"].append(str(owner["name"]))
        bucket["routes"].append(route)
        bucket["hits"].append(dict(hit))

    return [
        TouchGroup(
            group_key=key,
            target_user=value["target_user"],
            target_chat=value["target_chat"],
            route_chat_id=value["route_chat_id"],
            owner_names=value["owner_names"],
            route_results=value["routes"],
            hits=value["hits"],
        )
        for key, value in sorted(groups.items())
    ]


def card_base(title: str, subtitle: str, *, template: str = "yellow") -> dict[str, Any]:
    return {
        "schema": "2.0",
        "config": {
            "update_multi": True,
            "width_mode": "fill",
            "summary": {"content": title},
            "style": {
                "text_size": {
                    "title": {"default": "heading-2", "pc": "heading-2", "mobile": "heading-3"},
                    "body": {"default": "normal", "pc": "normal", "mobile": "normal"},
                }
            },
        },
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "subtitle": {"tag": "plain_text", "content": subtitle},
            "template": template,
            "icon": {"tag": "standard_icon", "token": "warning_colorful"},
        },
        "body": {"direction": "vertical", "padding": "12px 12px 20px 12px", "vertical_spacing": "12px", "elements": []},
    }


def metric_column(value: str, label: str) -> dict[str, Any]:
    return {
        "tag": "column",
        "width": "weighted",
        "weight": 1,
        "background_style": "yellow-50",
        "padding": "12px",
        "elements": [
            {"tag": "markdown", "content": f"## <font color='orange'>{value}</font>", "text_align": "center"},
            {"tag": "markdown", "content": f"<font color='grey'>{label}</font>", "text_align": "center", "text_size": "notation"},
        ],
    }


def render_touch_card(*, level: str, period: str, group: TouchGroup, title: str) -> dict[str, Any]:
    rows = sorted(group.hits, key=lambda row: -float_value(row.get("avg_jinshen")))[:10]
    total_avg_in = sum(float_value(row.get("avg_jinshen")) for row in group.hits)
    min_rate = min((float_value(row.get("ratio_val")) for row in group.hits), default=0)
    owner_text = "、".join(group.owner_names) if group.owner_names else "未命名负责人"
    card = card_base(title, f"{level} · {period} · {owner_text}", template="yellow")
    elements = card["body"]["elements"]
    elements.extend(
        [
            {
                "tag": "column_set",
                "flex_mode": "flow",
                "horizontal_spacing": "12px",
                "columns": [
                    metric_column(int_text(len(group.hits)), "触达 reason"),
                    metric_column(int_text(total_avg_in), "合计日均进审"),
                    metric_column(pct_text(min_rate), "最低打标率"),
                    metric_column(owner_text, "责任对象"),
                ],
            },
            {
                "tag": "markdown",
                "content": (
                    "**处理建议**\n"
                    "请确认这些 reason 的召回/审核策略是否仍有效；优先处理日均进审高且打标率低的项。"
                ),
            },
            {
                "tag": "table",
                "page_size": min(10, max(1, len(rows))),
                "row_height": "auto",
                "freeze_first_column": True,
                "header_style": {"background_style": "grey", "bold": True, "text_size": "notation", "lines": 1},
                "columns": [
                    {"name": "rank", "display_name": "排名", "data_type": "number", "width": "80px"},
                    {"name": "reason", "display_name": "reason", "data_type": "text", "width": "340px"},
                    {"name": "avg_in", "display_name": "日均进审", "data_type": "number", "width": "110px"},
                    {"name": "avg_done", "display_name": "日均完审", "data_type": "number", "width": "110px"},
                    {"name": "rate", "display_name": "打标率", "data_type": "text", "width": "90px"},
                ],
                "rows": [
                    {
                        "rank": index,
                        "reason": row.get("reason", ""),
                        "avg_in": int(round(float_value(row.get("avg_jinshen")))),
                        "avg_done": int(round(float_value(row.get("avg_wanshen")))),
                        "rate": pct_text(row.get("ratio_val")),
                    }
                    for index, row in enumerate(rows, 1)
                ],
            },
            {
                "tag": "collapsible_panel",
                "expanded": False,
                "background_color": "grey-50",
                "padding": "10px",
                "header": {"title": {"tag": "plain_text", "content": "路由与审计"}},
                "elements": [
                    {
                        "tag": "markdown",
                        "content": "\n".join(
                            [
                                f"- 触达目标：`{group.group_key}`",
                                f"- route_results：{len(group.route_results)} 条",
                                "- 本卡片已通过数据 hash 与等级校验后发送。",
                            ]
                        ),
                        "text_size": "notation",
                    }
                ],
            },
        ]
    )
    card["_meta"] = {"level": level, "route_target": group.target_chat or group.target_user}
    return embed_hash_in_card(card, compute_hits_hash(group.hits))


def send_group(
    *,
    group: TouchGroup,
    card_with_meta: dict[str, Any],
    output_dir: Path,
    level: str,
    identity: str,
    dry_run: bool,
    idempotency_prefix: str,
) -> dict[str, Any]:
    verify_card_hash(card_with_meta, group.hits)
    verify_route_match(card_with_meta, level)
    if group.target_chat:
        verify_route_chat_id(card_with_meta, level, group.target_chat, group.route_chat_id or "")

    card_path = output_dir / f"{group.group_key.replace(':', '_')}.event_touch.card.json"
    meta_path = output_dir / f"{group.group_key.replace(':', '_')}.event_touch.card.with_meta.json"
    write_json(meta_path, card_with_meta)
    write_json(card_path, strip_internal_keys(card_with_meta), compact=True)

    sent = False
    message_id = None
    chat_id = None
    sent_identity = None
    if not dry_run:
        payload = send_card(
            card_path,
            identity=identity,
            target_user=group.target_user,
            target_chat=group.target_chat,
            idempotency_key=safe_idempotency_key(f"{idempotency_prefix}-{group.group_key}"),
        )
        sent = bool(payload.get("ok"))
        sent_identity = payload.get("identity")
        data = payload.get("data", {})
        message_id = data.get("message_id")
        chat_id = data.get("chat_id")

    return {
        "touch_record_id": f"TR-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{safe_idempotency_key(group.group_key)}",
        "send_status": "sent" if sent else ("dry_run" if dry_run else "unknown"),
        "level": level,
        "target_user": group.target_user,
        "target_chat": group.target_chat,
        "hit_count": len(group.hits),
        "message_id": message_id,
        "chat_id": chat_id,
        "identity": sent_identity,
        "card_json": str(card_path),
        "card_json_with_meta": str(meta_path),
        "sent_at": utc_now_text() if sent else None,
        "event_table_writeback": "not_configured",
        "touch_record_table_writeback": "not_configured",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send formal event touch cards from routed hit rows.")
    parser.add_argument("--hits", required=True, type=Path)
    parser.add_argument("--route-results", required=True, type=Path)
    parser.add_argument("--level", required=True)
    parser.add_argument("--period", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--identity", choices=["bot", "user"], default="bot")
    parser.add_argument("--title", default="低效 reason 正式触达")
    parser.add_argument("--idempotency-prefix", default="event-touch")
    parser.add_argument("--target-allowlist", action="append", default=[])
    parser.add_argument("--allow-missing-owner", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    hits = read_csv(args.hits)
    routes = load_route_results(args.route_results)
    validate_routes(routes, require_all_routed=not args.allow_missing_owner)
    allowlist = set(args.target_allowlist) if args.target_allowlist else None
    groups = group_hits(hits, routes, target_allowlist=allowlist)
    if not groups:
        raise SystemExit("no routable touch groups")

    records = []
    for group in groups:
        card = render_touch_card(level=args.level, period=args.period, group=group, title=args.title)
        records.append(
            send_group(
                group=group,
                card_with_meta=card,
                output_dir=args.output_dir,
                level=args.level,
                identity=args.identity,
                dry_run=args.dry_run,
                idempotency_prefix=args.idempotency_prefix,
            )
        )

    records_path = args.output_dir / "touch_records.jsonl"
    with records_path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    summary = {
        "schema_version": "event_touch_summary.v1",
        "generated_at": utc_now_text(),
        "level": args.level,
        "period": args.period,
        "dry_run": args.dry_run,
        "group_count": len(groups),
        "hit_count": sum(len(group.hits) for group in groups),
        "sent_count": sum(1 for record in records if record["send_status"] == "sent"),
        "touch_records": str(records_path),
        "records": records,
    }
    write_json(args.output_dir / "touch_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["sent_count"] == len(groups) or args.dry_run else 2


if __name__ == "__main__":
    raise SystemExit(main())
