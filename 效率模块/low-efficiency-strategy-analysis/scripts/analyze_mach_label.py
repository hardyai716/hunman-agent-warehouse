#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""低效 reason 通用维度拆解聚合脚本。

文件名保留 `analyze_mach_label.py` 是为了兼容历史调用；实际能力已经泛化为
dimension_breakdown。输入为日粒度 CSV，输出两张 CSV：

1. dimensions × reason 低效明细；
2. dimensions 维度汇总。

输入 CSV 必须包含：
  - dt
  - reason
  - review_in
  - review_done
  - labeled
  - 一个或多个由 --dimensions 指定的维度列

兼容性：
  - 未传 --dimensions 时默认使用 mach_label，保持旧单维度行为；
  - --dimensions mach_root_label_name 会自动兼容输入列 mach_label；
  - --dimensions 支持空格分隔或逗号分隔。
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

import pandas as pd

DEFAULT_DIMENSIONS = ("mach_label",)
REQUIRED_COLUMNS = {"dt", "reason", "review_in", "review_done", "labeled"}

DIMENSION_ALIASES = {
    "mach_label": ("mach_label", "mach_root_label_name", "机审一级标签"),
    "mach_root_label_name": ("mach_root_label_name", "mach_label", "机审一级标签"),
}

DISPLAY_NAMES = {
    "mach_label": "机审一级标签",
    "mach_root_label_name": "机审一级标签",
}


def parse_dimensions(raw: Sequence[str] | None) -> list[str]:
    """Parse --dimensions values from comma-separated or repeated args."""
    if not raw:
        return list(DEFAULT_DIMENSIONS)

    dimensions: list[str] = []
    for item in raw:
        for part in item.split(","):
            name = part.strip()
            if name:
                dimensions.append(name)

    if not dimensions:
        raise ValueError("--dimensions 至少需要一个维度列")
    return dimensions


def _resolve_dimensions(df: pd.DataFrame, requested: Sequence[str]) -> tuple[list[str], dict[str, str]]:
    """Resolve requested dimension names to actual CSV columns.

    Returns:
        (source_columns, display_name_by_source_column)
    """
    source_columns: list[str] = []
    display_names: dict[str, str] = {}
    missing: list[str] = []

    for dimension in requested:
        candidates = DIMENSION_ALIASES.get(dimension, (dimension,))
        source = next((candidate for candidate in candidates if candidate in df.columns), None)
        if source is None:
            missing.append(f"{dimension}（候选列: {', '.join(candidates)}）")
            continue
        if source in source_columns:
            raise ValueError(f"维度列重复解析到同一 CSV 列: {source}")
        source_columns.append(source)
        display_names[source] = DISPLAY_NAMES.get(dimension, DISPLAY_NAMES.get(source, dimension))

    if missing:
        available = ", ".join(str(column) for column in df.columns)
        raise ValueError(
            "输入 CSV 缺少 --dimensions 指定的维度列: "
            + "; ".join(missing)
            + f"。可用列: {available}"
        )

    return source_columns, display_names


def _fill_dimension_nulls(df: pd.DataFrame, source_columns: Sequence[str], display_names: dict[str, str]) -> None:
    for column in source_columns:
        display = display_names.get(column, column)
        df[column] = df[column].fillna(f"（空/{display}）")


def _ensure_output_parent(path: str) -> None:
    parent = Path(path).expanduser().parent
    if str(parent) not in ("", "."):
        parent.mkdir(parents=True, exist_ok=True)


def _validate_input(df: pd.DataFrame) -> None:
    missing = sorted(REQUIRED_COLUMNS - set(df.columns))
    if missing:
        raise ValueError(f"输入 CSV 缺少必要列: {', '.join(missing)}")


def analyze(
    input_csv: str,
    threshold: float,
    sheet1_csv: str,
    sheet2_csv: str,
    dimensions: Sequence[str] | None = None,
) -> None:
    """Aggregate daily detail into dimension breakdown outputs.

    Args:
        input_csv: Daily detail CSV.
        threshold: Low-efficiency label rate threshold, e.g. 0.1.
        sheet1_csv: Output path for dimensions × reason low-efficiency detail.
        sheet2_csv: Output path for dimensions summary.
        dimensions: Requested CSV dimension columns. Defaults to mach_label.
    """
    requested_dimensions = parse_dimensions(dimensions)
    df = pd.read_csv(input_csv)
    _validate_input(df)
    source_dimensions, display_names = _resolve_dimensions(df, requested_dimensions)

    df["dt"] = pd.to_datetime(df["dt"])
    n_days = df["dt"].nunique()
    _fill_dimension_nulls(df, source_dimensions, display_names)

    dimension_text = " × ".join(display_names[column] for column in source_dimensions)
    print("=== 数据概览 ===")
    print(f"时间范围: {df['dt'].min().date()} ~ {df['dt'].max().date()}, 共 {n_days} 天")
    print(f"明细行数: {len(df)}  reason 数: {df['reason'].nunique()}  维度: {dimension_text}")
    for column in source_dimensions:
        print(f"{display_names[column]} 取值数(含空值填充): {df[column].nunique()}")

    # Sheet1: dimensions × reason low-efficiency detail.
    detail = df.groupby([*source_dimensions, "reason"], dropna=False).agg(
        total_in=("review_in", "sum"),
        total_done=("review_done", "sum"),
        total_labeled=("labeled", "sum"),
        days=("dt", "nunique"),
    ).reset_index()
    detail = detail[detail["total_done"] > 0].copy()
    detail["label_rate"] = detail["total_labeled"] / detail["total_done"]
    detail["avg_in"] = (detail["total_in"] / detail["days"]).round(0).astype(int)
    detail["avg_done"] = (detail["total_done"] / detail["days"]).round(0).astype(int)
    detail["avg_labeled"] = (detail["total_labeled"] / detail["days"]).round(0).astype(int)
    detail["label_rate_pct"] = (detail["label_rate"] * 100).round(2)

    low = detail[detail["label_rate"] < threshold].copy()
    low = low.sort_values("avg_in", ascending=False).reset_index(drop=True)
    sheet1_columns = [*source_dimensions, "reason", "avg_in", "avg_done", "avg_labeled", "label_rate_pct", "days"]
    sheet1 = low[sheet1_columns].copy()
    sheet1.columns = [
        *(display_names[column] for column in source_dimensions),
        "送审原因(reason)",
        "日均进审量",
        "日均完审量",
        "日均打标量",
        "打标率(%)",
        "有数据天数",
    ]
    sheet1.insert(0, "排名", range(1, len(sheet1) + 1))
    _ensure_output_parent(sheet1_csv)
    sheet1.to_csv(sheet1_csv, index=False, encoding="utf-8-sig")
    print(f"\n=== Sheet1: {dimension_text} × reason 低效明细 ===")
    print(f"低效组合数(打标率<{threshold*100:.0f}%): {len(sheet1)}  "
          f"合计日均进审量: {sheet1['日均进审量'].sum():,.0f}")
    print(sheet1.head(20).to_string(index=False))

    # Sheet2: dimensions summary, including non-low-efficiency combinations.
    summary = df.groupby(list(source_dimensions), dropna=False).agg(
        total_in=("review_in", "sum"),
        total_done=("review_done", "sum"),
        total_labeled=("labeled", "sum"),
        days=("dt", "nunique"),
        reason_cnt=("reason", "nunique"),
    ).reset_index()
    summary = summary[summary["total_done"] > 0].copy()
    summary["label_rate_pct"] = (summary["total_labeled"] / summary["total_done"] * 100).round(2)
    summary["avg_in"] = (summary["total_in"] / summary["days"]).round(0).astype(int)
    summary["avg_done"] = (summary["total_done"] / summary["days"]).round(0).astype(int)
    summary["avg_labeled"] = (summary["total_labeled"] / summary["days"]).round(0).astype(int)
    summary = summary.sort_values("avg_in", ascending=False).reset_index(drop=True)
    sheet2_columns = [*source_dimensions, "reason_cnt", "avg_in", "avg_done", "avg_labeled", "label_rate_pct", "days"]
    sheet2 = summary[sheet2_columns].copy()
    sheet2.columns = [
        *(display_names[column] for column in source_dimensions),
        "覆盖reason数",
        "日均进审量",
        "日均完审量",
        "日均打标量",
        "打标率(%)",
        "有数据天数",
    ]
    _ensure_output_parent(sheet2_csv)
    sheet2.to_csv(sheet2_csv, index=False, encoding="utf-8-sig")
    print(f"\n=== Sheet2: {dimension_text} 维度汇总（全量）===")
    print(sheet2.to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="低效 reason 通用维度拆解聚合")
    parser.add_argument(
        "--input",
        default="output/reason_label_daily.csv",
        help="日粒度明细 CSV（必要列: dt,reason,review_in,review_done,labeled + dimensions）",
    )
    parser.add_argument(
        "--dimensions",
        nargs="+",
        default=list(DEFAULT_DIMENSIONS),
        help="维度列，支持空格或逗号分隔；默认 mach_label；mach_root_label_name 兼容 mach_label",
    )
    parser.add_argument("--threshold", type=float, default=0.1, help="低效阈值（打标率小数），默认 0.1")
    parser.add_argument("--sheet1", default="output/sheet1_detail.csv")
    parser.add_argument("--sheet2", default="output/sheet2_label_summary.csv")
    args = parser.parse_args()
    analyze(args.input, args.threshold, args.sheet1, args.sheet2, args.dimensions)


if __name__ == "__main__":
    main()
