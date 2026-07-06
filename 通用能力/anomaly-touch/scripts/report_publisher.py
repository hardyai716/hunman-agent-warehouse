#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reusable Lark report publishing primitives.

This module turns a standard analysis run directory into:

1. an optional Lark spreadsheet;
2. a Card 2.0 payload;
3. an optional Lark IM message.

It intentionally keeps business SQL / analysis logic out of the publishing
layer. Upstream skills only need to produce summary.json, CSV files and an
optional workbook.
"""

from __future__ import annotations

import csv
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


SCRIPT_PATH = Path(__file__).resolve()
SKILL_DIR = SCRIPT_PATH.parents[1]


REPORT_DIMENSION = "low_efficiency_dimension_breakdown"
REPORT_GRADING = "low_efficiency_grading"
REPORT_LEVEL_DETAIL = "low_efficiency_level_detail"
REPORT_TYPES = {REPORT_DIMENSION, REPORT_GRADING, REPORT_LEVEL_DETAIL}

LEVEL_PRIORITY = {"P0": 0, "P1": 1, "P2": 2, "notice": 3}
LEVEL_COLORS = {"P0": "red", "P1": "orange", "P2": "yellow", "notice": "blue"}
IDEMPOTENCY_SAFE_RE = re.compile(r"[^A-Za-z0-9-]+")


def find_shared_scripts() -> Path:
    candidates = [
        SKILL_DIR.parent / "review-monitoring-shared" / "scripts",
        SCRIPT_PATH.parents[3] / "通用能力" / "review-monitoring-shared" / "scripts",
    ]
    for candidate in candidates:
        if (candidate / "card_validator.py").exists():
            return candidate
    raise RuntimeError("cannot locate review-monitoring-shared/scripts/card_validator.py")


import sys  # noqa: E402

sys.path.insert(0, str(find_shared_scripts()))
from card_validator import compute_hits_hash, embed_hash_in_card  # noqa: E402


@dataclass(frozen=True)
class PublishResult:
    report_type: str
    run_dir: str
    sheet_url: str | None
    card_json: str
    card_json_with_meta: str
    sent: bool
    message_id: str | None = None
    chat_id: str | None = None
    identity: str | None = None


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path, limit: int | None = None) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    return rows[:limit] if limit else rows


def write_json(path: Path, value: Any, *, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if compact:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"
    else:
        text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, encoding="utf-8")


def resolve_path(run_dir: Path, value: str | None, fallback_name: str | None = None) -> Path:
    if value:
        candidate = Path(value)
        if candidate.is_absolute():
            return candidate
        if candidate.exists():
            return candidate
        if (run_dir / candidate).exists():
            return run_dir / candidate
    if fallback_name:
        return run_dir / fallback_name
    raise ValueError("missing path value")


def first_existing(paths: Sequence[Path]) -> Path:
    for path in paths:
        if path.exists():
            return path
    raise FileNotFoundError("none of the candidate files exist: " + ", ".join(str(path) for path in paths))


def float_value(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def int_value(value: Any) -> int:
    return int(round(float_value(value)))


def int_text(value: Any) -> str:
    try:
        return f"{int(float(value)):,}"
    except (TypeError, ValueError):
        return str(value)


def pct_from_ratio(value: Any) -> float:
    return round(float_value(value) * 100, 2)


def strip_internal_keys(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: strip_internal_keys(val) for key, val in value.items() if not str(key).startswith("_")}
    if isinstance(value, list):
        return [strip_internal_keys(item) for item in value]
    return value


def safe_idempotency_key(raw: str) -> str:
    key = IDEMPOTENCY_SAFE_RE.sub("-", raw).strip("-")
    key = re.sub(r"-{2,}", "-", key)
    if len(key) > 50:
        key = key[-50:].strip("-")
    return key or "lark-report"


def card_base(title: str, subtitle: str, *, template: str = "blue", tags: list[dict[str, Any]] | None = None) -> dict[str, Any]:
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
                    "caption": {"default": "notation", "pc": "notation", "mobile": "notation"},
                }
            },
        },
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "subtitle": {"tag": "plain_text", "content": subtitle},
            "template": template,
            "icon": {"tag": "standard_icon", "token": "chart_colorful"},
            "text_tag_list": tags or [],
        },
        "body": {
            "direction": "vertical",
            "padding": "12px 12px 20px 12px",
            "vertical_spacing": "12px",
            "elements": [],
        },
    }


def text_tag(text: str, color: str = "blue") -> dict[str, Any]:
    return {"tag": "text_tag", "text": {"tag": "plain_text", "content": text}, "color": color}


def metric_column(value: str, label: str, *, color: str = "blue") -> dict[str, Any]:
    background = f"{color}-50" if color in {"red", "orange", "yellow", "blue", "green"} else "blue-50"
    return {
        "tag": "column",
        "width": "weighted",
        "weight": 1,
        "background_style": background,
        "padding": "12px",
        "vertical_spacing": "2px",
        "elements": [
            {"tag": "markdown", "content": f"## <font color='{color}'>{value}</font>", "text_align": "center"},
            {
                "tag": "markdown",
                "content": f"<font color='grey'>{label}</font>",
                "text_align": "center",
                "text_size": "notation",
            },
        ],
    }


def metrics_block(columns: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "tag": "column_set",
        "flex_mode": "flow",
        "horizontal_spacing": "12px",
        "columns": columns,
    }


def sheet_button(sheet_url: str) -> dict[str, Any]:
    return {
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
    }


def methodology_panel(lines: list[str]) -> dict[str, Any]:
    return {
        "tag": "collapsible_panel",
        "expanded": False,
        "background_color": "grey-50",
        "padding": "10px",
        "header": {"title": {"tag": "plain_text", "content": "口径与溯源"}},
        "elements": [{"tag": "markdown", "content": "\n".join(lines), "text_size": "notation"}],
    }


def render_dimension_breakdown(run_dir: Path, summary: dict[str, Any], sheet_url: str, top_n: int, title: str) -> dict[str, Any]:
    outputs = summary.get("outputs", {})
    detail_path = resolve_path(run_dir, outputs.get("detail_csv"), "sheet1_mach_label_reason_detail.csv")
    dimension_path = resolve_path(run_dir, outputs.get("summary_csv"), "sheet2_mach_label_summary.csv")
    details = read_csv(detail_path, top_n)
    dimensions = read_csv(dimension_path, 6)

    period = summary.get("period", {})
    start, end = period.get("start", ""), period.get("end", "")
    threshold = float_value(summary.get("threshold"), 0.1)
    aggregate = summary.get("aggregate_result", {})
    daily = summary.get("daily_detail", {})

    top_rows = [
        {
            "rank": int_value(row.get("排名")),
            "dimension": row.get("机审一级标签", ""),
            "reason": row.get("送审原因(reason)", ""),
            "avg_in": int_value(row.get("日均进审量")),
            "avg_done": int_value(row.get("日均完审量")),
            "rate": float_value(row.get("打标率(%)")),
        }
        for row in details
    ]
    chart_values = [
        {
            "dimension": row.get("机审一级标签", ""),
            "avg_in": int_value(row.get("日均进审量")),
            "label_rate": float_value(row.get("打标率(%)")),
        }
        for row in dimensions
    ]
    top1_avg_in = top_rows[0]["avg_in"] if top_rows else 0

    card = card_base(
        title,
        f"机审一级标签 × reason · {start} ~ {end}",
        tags=[text_tag(f"打标率<{threshold * 100:.0f}%"), text_tag("维度拆解", "wathet")],
    )
    elements = card["body"]["elements"]
    elements.extend(
        [
            metrics_block(
                [
                    metric_column(int_text(aggregate.get("low_dimension_reason_count")), "低效组合"),
                    metric_column(int_text(aggregate.get("dimension_count")), "机审一级标签"),
                    metric_column(int_text(daily.get("row_count")), "日粒度明细"),
                    metric_column(int_text(top1_avg_in), "Top1 日均进审"),
                ]
            ),
            {
                "tag": "chart",
                "height": "240px",
                "color_theme": "primary",
                "chart_spec": {
                    "type": "bar",
                    "direction": "horizontal",
                    "title": {"visible": True, "text": "机审一级标签日均进审量 Top 6"},
                    "data": {"values": chart_values},
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
                "page_size": min(5, max(1, len(top_rows))),
                "row_height": "auto",
                "freeze_first_column": True,
                "header_style": {"background_style": "grey", "bold": True, "text_size": "notation", "lines": 1},
                "columns": [
                    {"name": "rank", "display_name": "排名", "data_type": "number", "width": "80px"},
                    {"name": "dimension", "display_name": "机审一级标签", "data_type": "text", "width": "150px"},
                    {"name": "reason", "display_name": "reason", "data_type": "text", "width": "280px"},
                    {"name": "avg_in", "display_name": "日均进审", "data_type": "number", "width": "110px", "format": {"precision": 0, "separator": True}},
                    {"name": "avg_done", "display_name": "日均完审", "data_type": "number", "width": "110px", "format": {"precision": 0, "separator": True}},
                    {"name": "rate", "display_name": "打标率%", "data_type": "number", "width": "90px", "format": {"precision": 2}},
                ],
                "rows": top_rows,
            },
            sheet_button(sheet_url),
            methodology_panel(
                [
                    f"- 数据集：`{summary.get('dataset_id')}` / `{summary.get('region')}`",
                    f"- 取数窗口：`{start}` ~ `{end}`",
                    "- 打标率：`SUM(打标量) / SUM(完审量)`，分母为完审量",
                    f"- 日粒度明细：{int_text(daily.get('row_count'))} 行，截断：{daily.get('truncated')}",
                    f"- fallback_reason：`{summary.get('fallback_reason')}`",
                ]
            ),
        ]
    )
    return embed_hash_in_card(card, compute_hits_hash(top_rows))


def load_grading_rows(run_dir: Path, level: str | None = None) -> list[dict[str, str]]:
    if level:
        return read_csv(run_dir / f"{level}.csv")
    rows = read_csv(run_dir / "综合.csv")
    rows.sort(key=lambda row: (LEVEL_PRIORITY.get(row.get("_level", ""), 99), -float_value(row.get("avg_jinshen"))))
    return rows


def grading_table_rows(rows: list[dict[str, str]], top_n: int, include_level: bool) -> list[dict[str, Any]]:
    result = []
    for index, row in enumerate(rows[:top_n], 1):
        item: dict[str, Any] = {
            "rank": index,
            "reason": row.get("reason", ""),
            "avg_in": int_value(row.get("avg_jinshen")),
            "avg_done": int_value(row.get("avg_wanshen")),
            "avg_labeled": int_value(row.get("avg_dabiao")),
            "rate": pct_from_ratio(row.get("ratio_val")),
        }
        if include_level:
            level = row.get("_level", "")
            item["level"] = [{"text": level, "color": LEVEL_COLORS.get(level, "blue")}]
        result.append(item)
    return result


def grading_columns(include_level: bool) -> list[dict[str, Any]]:
    columns = [{"name": "rank", "display_name": "排名", "data_type": "number", "width": "80px"}]
    if include_level:
        columns.append({"name": "level", "display_name": "最高等级", "data_type": "options", "width": "100px"})
    columns.extend(
        [
            {"name": "reason", "display_name": "reason", "data_type": "text", "width": "340px"},
            {"name": "avg_in", "display_name": "日均进审", "data_type": "number", "width": "110px", "format": {"precision": 0, "separator": True}},
            {"name": "avg_done", "display_name": "日均完审", "data_type": "number", "width": "110px", "format": {"precision": 0, "separator": True}},
            {"name": "avg_labeled", "display_name": "日均打标", "data_type": "number", "width": "110px", "format": {"precision": 0, "separator": True}},
            {"name": "rate", "display_name": "打标率%", "data_type": "number", "width": "90px", "format": {"precision": 2}},
        ]
    )
    return columns


def grading_methodology(summary: dict[str, Any]) -> list[str]:
    window = summary.get("window", {})
    return [
        f"- 数据集：`{summary.get('dataset_id')}` / `{summary.get('region')}`",
        f"- 当前窗口：`{window.get('cur_start')}` ~ `{window.get('cur_end')}`",
        "- 打标率：`SUM(打标量) / SUM(完审量)`",
        f"- fallback_reason：`{summary.get('fallback_reason')}`",
    ]


def render_grading(run_dir: Path, summary: dict[str, Any], sheet_url: str, top_n: int, title: str) -> dict[str, Any]:
    window = summary.get("window", {})
    levels = summary.get("levels", {})
    counts = {level: int_value(conf.get("row_count")) for level, conf in levels.items()}
    rows = load_grading_rows(run_dir)
    top_rows = grading_table_rows(rows, top_n, include_level=True)
    chart_values = [{"level": level, "count": counts.get(level, 0)} for level in ["P0", "P1", "P2", "notice"]]

    card = card_base(
        title,
        f"reason 粒度 · {window.get('cur_start')} ~ {window.get('cur_end')}",
        tags=[text_tag("全等级"), text_tag("P0/P1/P2/notice", "wathet")],
    )
    elements = card["body"]["elements"]
    elements.extend(
        [
            metrics_block(
                [
                    metric_column(int_text(counts.get("P0")), "P0"),
                    metric_column(int_text(counts.get("P1")), "P1"),
                    metric_column(int_text(counts.get("P2")), "P2"),
                    metric_column(int_text(counts.get("notice")), "notice"),
                ]
            ),
            {
                "tag": "chart",
                "height": "220px",
                "color_theme": "primary",
                "chart_spec": {
                    "type": "bar",
                    "title": {"visible": True, "text": "各等级命中 reason 数"},
                    "data": {"values": chart_values},
                    "xField": "level",
                    "yField": "count",
                    "label": {"visible": True},
                    "axes": [
                        {"orient": "left", "title": {"visible": True, "text": "命中数"}},
                        {"orient": "bottom", "title": {"visible": False}},
                    ],
                },
            },
            {
                "tag": "table",
                "page_size": min(5, max(1, len(top_rows))),
                "row_height": "auto",
                "freeze_first_column": True,
                "header_style": {"background_style": "grey", "bold": True, "text_size": "notation", "lines": 1},
                "columns": grading_columns(include_level=True),
                "rows": top_rows,
            },
            sheet_button(sheet_url),
            methodology_panel(grading_methodology(summary)),
        ]
    )
    return embed_hash_in_card(card, compute_hits_hash(top_rows))


def render_level_detail(run_dir: Path, summary: dict[str, Any], sheet_url: str, top_n: int, title: str, level: str) -> dict[str, Any]:
    if level not in {"P0", "P1", "P2", "notice"}:
        raise ValueError("--level must be one of P0/P1/P2/notice")
    rows = load_grading_rows(run_dir, level)
    rows.sort(key=lambda row: -float_value(row.get("avg_jinshen")))
    top_rows = grading_table_rows(rows, top_n, include_level=False)
    color = LEVEL_COLORS.get(level, "blue")
    total_avg_in = sum(float_value(row.get("avg_jinshen")) for row in rows)
    top_avg_in = max((float_value(row.get("avg_jinshen")) for row in rows), default=0)
    min_rate = min((pct_from_ratio(row.get("ratio_val")) for row in rows), default=0)
    window = summary.get("window", {})
    descriptions = {
        "P0": "最高优先级，持续/爆量低效",
        "P1": "高量或双周持续低效",
        "P2": "单策略低效或环比上涨",
        "notice": "打标率偏低，纳入观察",
    }

    card = card_base(
        title or f"{level} 低效 reason 明细",
        f"reason 粒度 · {window.get('cur_start')} ~ {window.get('cur_end')}",
        template=color,
        tags=[text_tag(level, color), text_tag(f"{len(rows)} 条")],
    )
    elements = card["body"]["elements"]
    elements.extend(
        [
            metrics_block(
                [
                    metric_column(int_text(len(rows)), "命中 reason", color=color),
                    metric_column(int_text(total_avg_in), "合计日均进审", color=color),
                    metric_column(int_text(top_avg_in), "Top1 日均进审", color=color),
                    metric_column(f"{min_rate:.2f}%", "最低打标率", color=color),
                ]
            ),
            {"tag": "markdown", "content": f"**等级说明**\n{descriptions[level]}"},
            {
                "tag": "table",
                "page_size": min(10, max(1, len(top_rows))),
                "row_height": "auto",
                "freeze_first_column": True,
                "header_style": {"background_style": "grey", "bold": True, "text_size": "notation", "lines": 1},
                "columns": grading_columns(include_level=False),
                "rows": top_rows,
            },
            sheet_button(sheet_url),
            methodology_panel(grading_methodology(summary)),
        ]
    )
    card["_meta"] = {"level": level}
    return embed_hash_in_card(card, compute_hits_hash(top_rows))


def render_card(report_type: str, run_dir: Path, summary: dict[str, Any], sheet_url: str, top_n: int, title: str, level: str | None = None) -> dict[str, Any]:
    if report_type == REPORT_DIMENSION:
        return render_dimension_breakdown(run_dir, summary, sheet_url, top_n, title or "近7天机审标签×reason低效打标报告")
    if report_type == REPORT_GRADING:
        return render_grading(run_dir, summary, sheet_url, top_n, title or "近7天单reason低效打标全等级结果")
    if report_type == REPORT_LEVEL_DETAIL:
        if not level:
            raise ValueError("--level is required for low_efficiency_level_detail")
        return render_level_detail(run_dir, summary, sheet_url, top_n, title or f"{level} 低效 reason 明细", level)
    raise ValueError(f"unsupported report_type: {report_type}")


def find_workbook(run_dir: Path, summary: dict[str, Any]) -> Path | None:
    outputs = summary.get("outputs", {})
    candidates = []
    if outputs.get("workbook"):
        candidates.append(resolve_path(run_dir, outputs.get("workbook")))
    candidates.extend(sorted(run_dir.glob("*.xlsx")))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def run_lark_cli(args: list[str]) -> dict[str, Any]:
    proc = subprocess.run(args, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError((proc.stdout + "\n" + proc.stderr).strip())
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"lark-cli returned non-json output: {proc.stdout}") from exc


def import_workbook(workbook: Path, name: str, identity: str) -> str:
    try:
        workbook_arg = str(workbook.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        workbook_arg = str(workbook)
    payload = run_lark_cli(
        [
            "lark-cli",
            "sheets",
            "+workbook-import",
            "--json",
            "--as",
            identity,
            "--file",
            workbook_arg,
            "--name",
            name,
        ]
    )
    data = payload.get("data", {})
    url = data.get("url")
    if not url:
        raise RuntimeError(f"workbook import did not return url: {payload}")
    return str(url)


def send_card(card_json: Path, *, identity: str, target_user: str | None, target_chat: str | None, idempotency_key: str, fallback_bot: bool = True) -> dict[str, Any]:
    if bool(target_user) == bool(target_chat):
        raise ValueError("exactly one of target_user or target_chat is required")
    args = [
        "lark-cli",
        "im",
        "+messages-send",
        "--json",
        "--as",
        identity,
        "--msg-type",
        "interactive",
        "--content",
        card_json.read_text(encoding="utf-8"),
        "--idempotency-key",
        idempotency_key,
    ]
    if target_user:
        args.extend(["--user-id", target_user])
    else:
        args.extend(["--chat-id", str(target_chat)])

    proc = subprocess.run(args, text=True, capture_output=True)
    if proc.returncode == 0:
        return json.loads(proc.stdout)

    combined = proc.stdout + "\n" + proc.stderr
    if identity == "user" and fallback_bot and "im:message.send_as_user" in combined:
        return send_card(card_json, identity="bot", target_user=target_user, target_chat=target_chat, idempotency_key=idempotency_key + "-bot", fallback_bot=False)
    raise RuntimeError(combined.strip())


def publish_report(
    *,
    run_dir: Path,
    report_type: str,
    output_dir: Path | None = None,
    sheet_url: str | None = None,
    sheet_name: str | None = None,
    target_user: str | None = None,
    target_chat: str | None = None,
    identity: str = "bot",
    top_n: int = 10,
    level: str | None = None,
    title: str | None = None,
    dry_run: bool = False,
) -> PublishResult:
    if report_type not in REPORT_TYPES:
        raise ValueError(f"report_type must be one of {sorted(REPORT_TYPES)}")
    run_dir = run_dir.resolve()
    output_dir = (output_dir or run_dir).resolve()
    summary = read_json(run_dir / "summary.json")

    if not sheet_url:
        if dry_run:
            sheet_url = "https://bytedance.larkoffice.com/sheets/<dry_run_sheet_token>"
        else:
            workbook = find_workbook(run_dir, summary)
            if not workbook:
                raise FileNotFoundError(f"cannot find workbook in {run_dir}")
            sheet_url = import_workbook(workbook, sheet_name or f"{report_type} 结果", "user")

    card_with_meta = render_card(report_type, run_dir, summary, sheet_url, top_n, title or "", level)
    send_card_payload = strip_internal_keys(card_with_meta)

    suffix = report_type if not level else f"{report_type}_{level}"
    card_path = output_dir / f"{suffix}.card.json"
    meta_path = output_dir / f"{suffix}.card.with_meta.json"
    publish_summary_path = output_dir / f"{suffix}.publish_summary.json"
    write_json(card_path, send_card_payload, compact=True)
    write_json(meta_path, card_with_meta)

    sent = False
    message_id = None
    chat_id = None
    sent_identity = None
    if (target_user or target_chat) and not dry_run:
        payload = send_card(
            card_path,
            identity=identity,
            target_user=target_user,
            target_chat=target_chat,
            idempotency_key=safe_idempotency_key(f"{suffix}-{run_dir.name}"),
        )
        sent = bool(payload.get("ok"))
        sent_identity = payload.get("identity")
        data = payload.get("data", {})
        message_id = data.get("message_id")
        chat_id = data.get("chat_id")

    result = PublishResult(
        report_type=report_type,
        run_dir=str(run_dir),
        sheet_url=sheet_url,
        card_json=str(card_path),
        card_json_with_meta=str(meta_path),
        sent=sent,
        message_id=message_id,
        chat_id=chat_id,
        identity=sent_identity,
    )
    write_json(publish_summary_path, result.__dict__)
    return result
