#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render a unified Lark Card 2.0 report for low-efficiency dimension analysis."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any


SCRIPT_PATH = Path(__file__).resolve()
SKILL_DIR = SCRIPT_PATH.parents[1]


def find_shared_scripts() -> Path:
    candidates = [
        # Source layout: 通用能力/anomaly-touch sibling to 通用能力/review-monitoring-shared.
        SKILL_DIR.parent / "review-monitoring-shared" / "scripts",
        # Project-root layout: 通用能力/review-monitoring-shared.
        SCRIPT_PATH.parents[3] / "通用能力" / "review-monitoring-shared" / "scripts",
    ]
    for candidate in candidates:
        if (candidate / "card_validator.py").exists():
            return candidate
    raise RuntimeError("cannot locate review-monitoring-shared/scripts/card_validator.py")


sys.path.insert(0, str(find_shared_scripts()))

from card_validator import compute_hits_hash, embed_hash_in_card  # noqa: E402


def load_csv(path: Path, limit: int | None = None) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    return rows[:limit] if limit else rows


def int_text(value: Any) -> str:
    try:
        return f"{int(float(value)):,}"
    except (TypeError, ValueError):
        return str(value)


def float_value(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def table_rows(detail_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in detail_rows:
        rows.append(
            {
                "rank": int(float_value(row.get("排名"))),
                "dimension": row.get("机审一级标签", ""),
                "reason": row.get("送审原因(reason)", ""),
                "avg_in": int(float_value(row.get("日均进审量"))),
                "avg_done": int(float_value(row.get("日均完审量"))),
                "rate": float_value(row.get("打标率(%)")),
            }
        )
    return rows


def chart_values(summary_rows: list[dict[str, str]], limit: int = 6) -> list[dict[str, Any]]:
    values = []
    for row in summary_rows[:limit]:
        values.append(
            {
                "dimension": row.get("机审一级标签", ""),
                "avg_in": int(float_value(row.get("日均进审量"))),
                "label_rate": float_value(row.get("打标率(%)")),
            }
        )
    return values


def build_metric_column(value: str, label: str) -> dict[str, Any]:
    return {
        "tag": "column",
        "width": "weighted",
        "weight": 1,
        "background_style": "blue-50",
        "padding": "12px",
        "vertical_spacing": "2px",
        "elements": [
            {"tag": "markdown", "content": f"## <font color='blue'>{value}</font>", "text_align": "center"},
            {
                "tag": "markdown",
                "content": f"<font color='grey'>{label}</font>",
                "text_align": "center",
                "text_size": "notation",
            },
        ],
    }


def build_card(
    summary: dict[str, Any],
    detail_rows: list[dict[str, str]],
    dimension_rows: list[dict[str, str]],
    sheet_url: str,
    top_n: int,
    title: str,
) -> dict[str, Any]:
    period = summary.get("period", {})
    start = period.get("start", "")
    end = period.get("end", "")
    threshold = float_value(summary.get("threshold"), 0.1)
    aggregate = summary.get("aggregate_result", {})
    daily = summary.get("daily_detail", {})
    top_detail = detail_rows[:top_n]
    top_table_rows = table_rows(top_detail)
    chart_data = chart_values(dimension_rows)
    top1_avg_in = top_table_rows[0]["avg_in"] if top_table_rows else 0

    hits_hash_source = [
        {
            "rank": row.get("排名"),
            "dimension": row.get("机审一级标签"),
            "reason": row.get("送审原因(reason)"),
            "avg_in": row.get("日均进审量"),
            "label_rate_pct": row.get("打标率(%)"),
        }
        for row in top_detail
    ]

    card: dict[str, Any] = {
        "schema": "2.0",
        "config": {
            "update_multi": True,
            "width_mode": "fill",
            "summary": {"content": title},
            "style": {
                "text_size": {
                    "title": {"default": "heading-2", "pc": "heading-2", "mobile": "heading-3"},
                    "body": {"default": "normal", "pc": "normal", "mobile": "normal"},
                    "caption": {"default": "notation", "pc": "notation", "mobile": "notation"},
                }
            },
        },
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "subtitle": {
                "tag": "plain_text",
                "content": f"机审一级标签 × reason · {start} ~ {end}",
            },
            "template": "blue",
            "icon": {"tag": "standard_icon", "token": "chart_colorful"},
            "text_tag_list": [
                {
                    "tag": "text_tag",
                    "text": {"tag": "plain_text", "content": f"打标率<{threshold * 100:.0f}%"},
                    "color": "blue",
                },
                {"tag": "text_tag", "text": {"tag": "plain_text", "content": "维度拆解"}, "color": "wathet"},
            ],
        },
        "body": {
            "direction": "vertical",
            "padding": "12px 12px 20px 12px",
            "vertical_spacing": "12px",
            "elements": [
                {
                    "tag": "column_set",
                    "flex_mode": "flow",
                    "horizontal_spacing": "12px",
                    "columns": [
                        build_metric_column(int_text(aggregate.get("low_dimension_reason_count")), "低效组合"),
                        build_metric_column(int_text(aggregate.get("dimension_count")), "机审一级标签"),
                        build_metric_column(int_text(daily.get("row_count")), "日粒度明细"),
                        build_metric_column(int_text(top1_avg_in), "Top1 日均进审"),
                    ],
                },
                {
                    "tag": "chart",
                    "height": "240px",
                    "color_theme": "primary",
                    "chart_spec": {
                        "type": "bar",
                        "direction": "horizontal",
                        "title": {"visible": True, "text": "机审一级标签日均进审量 Top 6"},
                        "data": {"values": chart_data},
                        "xField": "avg_in",
                        "yField": "dimension",
                        "axes": [
                            {"orient": "bottom", "title": {"visible": True, "text": "日均进审量"}},
                            {"orient": "left", "label": {"autoLimit": True}},
                        ],
                        "label": {"visible": True},
                    },
                },
                {
                    "tag": "table",
                    "page_size": min(5, max(1, len(top_table_rows))),
                    "row_height": "auto",
                    "freeze_first_column": True,
                    "header_style": {
                        "background_style": "grey",
                        "bold": True,
                        "text_size": "notation",
                        "lines": 1,
                    },
                    "columns": [
                        {"name": "rank", "display_name": "排名", "data_type": "number", "width": "80px"},
                        {"name": "dimension", "display_name": "机审一级标签", "data_type": "text", "width": "150px"},
                        {"name": "reason", "display_name": "reason", "data_type": "text", "width": "280px"},
                        {
                            "name": "avg_in",
                            "display_name": "日均进审",
                            "data_type": "number",
                            "width": "110px",
                            "format": {"precision": 0, "separator": True},
                        },
                        {
                            "name": "avg_done",
                            "display_name": "日均完审",
                            "data_type": "number",
                            "width": "110px",
                            "format": {"precision": 0, "separator": True},
                        },
                        {
                            "name": "rate",
                            "display_name": "打标率%",
                            "data_type": "number",
                            "width": "90px",
                            "format": {"precision": 2},
                        },
                    ],
                    "rows": top_table_rows,
                },
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "查看完整飞书电子表格"},
                    "type": "primary_filled",
                    "width": "fill",
                    "behaviors": [
                        {
                            "type": "open_url",
                            "default_url": sheet_url,
                            "pc_url": sheet_url,
                            "ios_url": sheet_url,
                            "android_url": sheet_url,
                        }
                    ],
                },
                {
                    "tag": "collapsible_panel",
                    "expanded": False,
                    "background_color": "grey-50",
                    "padding": "10px",
                    "header": {"title": {"tag": "plain_text", "content": "口径与溯源"}},
                    "elements": [
                        {
                            "tag": "markdown",
                            "content": (
                                f"- 数据集：`{summary.get('dataset_id')}` / `{summary.get('region')}`\n"
                                f"- 取数窗口：`{start}` ~ `{end}`\n"
                                "- 打标率：`SUM(打标量) / SUM(完审量)`，分母为完审量\n"
                                f"- 日粒度明细：{int_text(daily.get('row_count'))} 行，截断：{daily.get('truncated')}\n"
                                f"- fallback_reason：`{summary.get('fallback_reason')}`"
                            ),
                            "text_size": "notation",
                        }
                    ],
                },
            ],
        },
        "_meta": {
            "template": "low_efficiency_dimension_report",
            "template_version": "1.0.0",
            "level": "dimension_breakdown",
        },
    }

    return embed_hash_in_card(card, compute_hits_hash(hits_hash_source))


def strip_internal_keys(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: strip_internal_keys(val) for key, val in value.items() if not str(key).startswith("_")}
    if isinstance(value, list):
        return [strip_internal_keys(item) for item in value]
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Render unified Lark report card JSON.")
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--detail-csv", required=True, type=Path)
    parser.add_argument("--dimension-summary-csv", required=True, type=Path)
    parser.add_argument("--sheet-url", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--meta-output", type=Path)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--title", default="近7天低效打标结果")
    args = parser.parse_args()

    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    detail_rows = load_csv(args.detail_csv, args.top_n)
    dimension_rows = load_csv(args.dimension_summary_csv, 6)
    card_with_meta = build_card(summary, detail_rows, dimension_rows, args.sheet_url, args.top_n, args.title)
    send_card = strip_internal_keys(card_with_meta)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(send_card, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    if args.meta_output:
        args.meta_output.parent.mkdir(parents=True, exist_ok=True)
        args.meta_output.write_text(
            json.dumps(card_with_meta, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
