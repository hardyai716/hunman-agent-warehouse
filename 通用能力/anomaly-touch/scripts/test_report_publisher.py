#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import report_publisher as rp


class ReportPublisherTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_json(self, name: str, value: dict) -> None:
        (self.run_dir / name).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def write_csv(self, name: str, rows: list[dict]) -> None:
        path = self.run_dir / name
        with path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    def assert_send_card_is_clean(self, card: dict) -> None:
        self.assertEqual(card["schema"], "2.0")
        self.assertFalse(any(str(key).startswith("_") for key in card))

    def assert_table_widths_safe(self, card: dict) -> None:
        for element in card["body"]["elements"]:
            if element.get("tag") != "table":
                continue
            for column in element["columns"]:
                width = column.get("width")
                if width and width.endswith("px"):
                    self.assertGreaterEqual(int(width[:-2]), 80, column)

    def test_dimension_breakdown_dry_run_publish(self) -> None:
        self.write_json(
            "summary.json",
            {
                "dataset_id": "3888816",
                "region": "cn",
                "period": {"start": "2026-06-29", "end": "2026-07-05"},
                "threshold": 0.1,
                "daily_detail": {"row_count": 12, "truncated": False},
                "aggregate_result": {"low_dimension_reason_count": 2, "dimension_count": 1},
                "fallback_reason": "dimension_reason_breakdown_requires_curated_sql",
            },
        )
        self.write_csv(
            "sheet1_mach_label_reason_detail.csv",
            [
                {"排名": "1", "机审一级标签": "领导人", "送审原因(reason)": "r1", "日均进审量": "100", "日均完审量": "90", "日均打标量": "1", "打标率(%)": "1.11", "有数据天数": "7"},
                {"排名": "2", "机审一级标签": "国家安全", "送审原因(reason)": "r2", "日均进审量": "80", "日均完审量": "70", "日均打标量": "2", "打标率(%)": "2.86", "有数据天数": "7"},
            ],
        )
        self.write_csv(
            "sheet2_mach_label_summary.csv",
            [
                {"机审一级标签": "领导人", "覆盖reason数": "1", "日均进审量": "100", "日均完审量": "90", "日均打标量": "1", "打标率(%)": "1.11", "有数据天数": "7"}
            ],
        )

        result = rp.publish_report(
            run_dir=self.run_dir,
            report_type=rp.REPORT_DIMENSION,
            dry_run=True,
        )

        card = json.loads(Path(result.card_json).read_text(encoding="utf-8"))
        self.assert_send_card_is_clean(card)
        self.assert_table_widths_safe(card)
        self.assertFalse(result.sent)

    def test_grading_render(self) -> None:
        self.write_json(
            "summary.json",
            {
                "dataset_id": "3888816",
                "region": "cn",
                "window": {"cur_start": "2026-06-29", "cur_end": "2026-07-05", "prev_start": "2026-06-22", "prev_end": "2026-06-28"},
                "fallback_reason": "complex_grading_rule_not_covered_by_semantic_layer",
                "levels": {
                    "P0": {"row_count": 1},
                    "P1": {"row_count": 1},
                    "P2": {"row_count": 1},
                    "notice": {"row_count": 3},
                },
            },
        )
        rows = [
            {"_level": "P0", "reason": "r0", "avg_jinshen": "100", "avg_wanshen": "90", "avg_dabiao": "1", "ratio_val": "0.01", "hit_condition": "p0"},
            {"_level": "P1", "reason": "r1", "avg_jinshen": "90", "avg_wanshen": "80", "avg_dabiao": "2", "ratio_val": "0.02", "hit_condition": "p1"},
        ]
        self.write_csv("综合.csv", rows)

        card_with_meta = rp.render_card(rp.REPORT_GRADING, self.run_dir, rp.read_json(self.run_dir / "summary.json"), "https://example.com/sheets/x", 10, "测试全等级")
        card = rp.strip_internal_keys(card_with_meta)

        self.assert_send_card_is_clean(card)
        self.assert_table_widths_safe(card)
        self.assertIn("_meta", card_with_meta)

    def test_level_detail_render_requires_level(self) -> None:
        self.write_json(
            "summary.json",
            {
                "dataset_id": "3888816",
                "region": "cn",
                "window": {"cur_start": "2026-06-29", "cur_end": "2026-07-05", "prev_start": "2026-06-22", "prev_end": "2026-06-28"},
                "fallback_reason": "complex_grading_rule_not_covered_by_semantic_layer",
            },
        )
        self.write_csv(
            "P0.csv",
            [{"reason": "r0", "avg_jinshen": "100", "avg_wanshen": "90", "avg_dabiao": "1", "ratio_val": "0.01", "hit_condition": "p0"}],
        )
        with self.assertRaises(ValueError):
            rp.render_card(rp.REPORT_LEVEL_DETAIL, self.run_dir, rp.read_json(self.run_dir / "summary.json"), "https://example.com/sheets/x", 10, "测试", None)

        card = rp.strip_internal_keys(
            rp.render_card(rp.REPORT_LEVEL_DETAIL, self.run_dir, rp.read_json(self.run_dir / "summary.json"), "https://example.com/sheets/x", 10, "测试 P0", "P0")
        )
        self.assert_send_card_is_clean(card)
        self.assert_table_widths_safe(card)

    def test_safe_idempotency_key(self) -> None:
        key = rp.safe_idempotency_key("low_efficiency_level_detail_P2-p2_low_efficiency_20260706_155512")
        self.assertLessEqual(len(key), 50)
        self.assertRegex(key, r"^[A-Za-z0-9-]+$")
        self.assertNotIn("_", key)

    def test_cli_dry_run(self) -> None:
        self.write_json(
            "summary.json",
            {
                "dataset_id": "3888816",
                "region": "cn",
                "window": {"cur_start": "2026-06-29", "cur_end": "2026-07-05", "prev_start": "2026-06-22", "prev_end": "2026-06-28"},
                "fallback_reason": "complex_grading_rule_not_covered_by_semantic_layer",
                "levels": {"P0": {"row_count": 1}, "P1": {"row_count": 0}, "P2": {"row_count": 0}, "notice": {"row_count": 1}},
            },
        )
        self.write_csv(
            "综合.csv",
            [{"_level": "P0", "reason": "r0", "avg_jinshen": "100", "avg_wanshen": "90", "avg_dabiao": "1", "ratio_val": "0.01", "hit_condition": "p0"}],
        )
        script = Path(__file__).with_name("publish_lark_report.py")
        proc = subprocess.run(
            [
                sys.executable,
                str(script),
                "--run-dir",
                str(self.run_dir),
                "--report-type",
                rp.REPORT_GRADING,
                "--dry-run",
            ],
            text=True,
            capture_output=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["sent"])
        self.assertTrue(Path(payload["card_json"]).exists())


if __name__ == "__main__":
    unittest.main()
