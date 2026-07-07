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


SCRIPT = Path(__file__).resolve().with_name("run_orchestrator.py")
CONFIG = Path(__file__).resolve().parents[2] / "review-monitoring-shared" / "examples" / "low_efficiency_sop_config.sample.json"
FIXTURE_RUN_DIR = Path(__file__).resolve().parents[1] / "examples" / "low_efficiency_run"


class OrchestratorRunTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.tmp.name) / "run"
        self.baseline_dir = Path(self.tmp.name) / "baseline"
        self.output_dir = Path(self.tmp.name) / "orch"
        self.run_dir.mkdir(parents=True)
        self.baseline_dir.mkdir(parents=True)
        self._write_low_efficiency_run_dir(self.run_dir)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_json(self, path: Path, value: dict) -> None:
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def _write_csv(self, path: Path, rows: list[dict]) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    def _write_low_efficiency_run_dir(self, run_dir: Path, rows: list[dict] | None = None) -> None:
        rows = rows or [
            {
                "_level": "P2",
                "reason": "N1_chuxing_model_llm_pe_review",
                "avg_jinshen": "100",
                "avg_wanshen": "90",
                "avg_dabiao": "1",
                "ratio_val": "0.01",
                "hit_condition": "p2",
            },
            {
                "_level": "P2",
                "reason": "unknown_reason",
                "avg_jinshen": "80",
                "avg_wanshen": "70",
                "avg_dabiao": "1",
                "ratio_val": "0.014",
                "hit_condition": "p2",
            },
        ]
        self._write_json(
            run_dir / "summary.json",
            {
                "dataset_id": "3888816",
                "region": "cn",
                "window": {
                    "cur_start": "2026-06-29",
                    "cur_end": "2026-07-05",
                    "prev_start": "2026-06-22",
                    "prev_end": "2026-06-28",
                },
                "fallback_reason": "unit_test",
                "levels": {
                    "P0": {"row_count": 0},
                    "P1": {"row_count": 0},
                    "P2": {"row_count": len(rows)},
                    "notice": {"row_count": 0},
                },
            },
        )
        self._write_csv(run_dir / "综合.csv", rows)
        self._write_csv(run_dir / "P2.csv", [row for row in rows if row.get("_level") == "P2"] or rows)

    def _write_authorized_canary_config(self) -> tuple[Path, Path]:
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        sop = config["sops"][0]
        sop["run_mode"] = "canary"
        target_user = "ou_canary_target"
        policy = next(item for item in sop["report_policies"] if item["report_policy_id"] == "low_efficiency_p2_detail_report_only")
        policy["report_target_policy"]["auto_send"] = True
        policy["report_target_policy"]["target_ref"] = target_user
        policy["report_target_policy"]["target_type"] = "single_user_canary"
        policy["level_selector"] = "P2"
        config_path = Path(self.tmp.name) / "low_efficiency_canary_config.json"
        auth_path = Path(self.tmp.name) / "canary_authorization.json"
        self._write_json(config_path, config)
        self._write_json(
            auth_path,
            {
                "schema_version": "production_authorization.v1",
                "enabled": True,
                "authorized_by": "unit-test",
                "reason": "single target canary dry-run",
                "run_mode": "canary",
                "sop_id": "low_efficiency_labeling",
                "report_policy_id": "low_efficiency_p2_detail_report_only",
                "report_type": "low_efficiency_level_detail",
                "level": "P2",
                "target_user": target_user,
                "expires_at": "2099-01-01T00:00:00Z",
            },
        )
        return config_path, auth_path

    def test_report_only_shadow_run(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--config",
                str(CONFIG),
                "--sop-id",
                "low_efficiency_labeling",
                "--run-mode",
                "report_only",
                "--process-run-dir",
                str(self.run_dir),
                "--output-dir",
                str(self.output_dir),
                "--run-id",
                "RUN-UNIT",
                "--route-preview",
                "--dry-run",
            ],
            text=True,
            capture_output=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        summary = json.loads(proc.stdout)
        self.assertEqual(summary["run_status"], "completed")
        self.assertTrue((self.output_dir / "validation_report.json").exists())
        self.assertTrue((self.output_dir / "run_audit.jsonl").exists())
        self.assertTrue((self.output_dir / "run_summary.json").exists())
        self.assertTrue((self.output_dir / "low_efficiency_grading.card.json").exists())
        routes = json.loads((self.output_dir / "route_results.json").read_text(encoding="utf-8"))
        self.assertEqual(routes["summary"]["hit_count"], 2)
        self.assertEqual(routes["summary"]["routed_count"], 1)
        self.assertEqual(routes["summary"]["missing_owner_count"], 1)

    def test_live_side_effect_modes_block_without_authorization(self) -> None:
        for run_mode in ("canary", "active", "touch_execute"):
            with self.subTest(run_mode=run_mode):
                output_dir = Path(self.tmp.name) / f"orch-{run_mode}"
                proc = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT),
                        "--config",
                        str(CONFIG),
                        "--sop-id",
                        "low_efficiency_labeling",
                        "--run-mode",
                        run_mode,
                        "--process-run-dir",
                        str(self.run_dir),
                        "--output-dir",
                        str(output_dir),
                        "--run-id",
                        f"RUN-{run_mode.upper()}",
                    ],
                    text=True,
                    capture_output=True,
                )
                self.assertEqual(proc.returncode, 2, proc.stderr)
                summary = json.loads(proc.stdout)
                self.assertEqual(summary["run_status"], "blocked")
                self.assertEqual(summary["stop_reason"], "live_mode_requires_production_authorization")
                self.assertEqual(summary["live_mode_status"]["requested_run_mode"], run_mode)
                self.assertFalse(summary["live_mode_status"]["authorized"])
                self.assertEqual(summary["live_mode_status"]["mvp_supported"], run_mode == "canary")
                self.assertEqual(summary["live_mode_status"]["safe_alternatives"], ["manual", "report_only", "shadow"])
                message = summary["error_message"]
                self.assertIn("platform-side Lark/Aeolus credentials", message)
                self.assertIn("validated production configuration", message)
                self.assertIn("explicit production authorization file", message)
                self.assertIn("Use report_only or shadow", message)
                self.assertTrue((output_dir / "run_summary.json").exists())
                audit = (output_dir / "run_audit.jsonl").read_text(encoding="utf-8")
                self.assertIn('"node_type":"live_mode_guard"', audit)
                self.assertIn('"node_status":"blocked"', audit)
                self.assertFalse((output_dir / "validation_report.json").exists())
                self.assertFalse((output_dir / "low_efficiency_grading.card.json").exists())

    def test_authorized_canary_can_run_single_level_dry_run(self) -> None:
        config_path, auth_path = self._write_authorized_canary_config()
        output_dir = Path(self.tmp.name) / "orch-canary-authorized"
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--config",
                str(config_path),
                "--sop-id",
                "low_efficiency_labeling",
                "--run-mode",
                "canary",
                "--process-run-dir",
                str(self.run_dir),
                "--output-dir",
                str(output_dir),
                "--run-id",
                "RUN-CANARY-AUTH",
                "--report-policy-id",
                "low_efficiency_p2_detail_report_only",
                "--production-authorization-file",
                str(auth_path),
                "--dry-run",
            ],
            text=True,
            capture_output=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        summary = json.loads(proc.stdout)
        self.assertEqual(summary["run_status"], "completed")
        self.assertEqual(summary["run_mode"], "canary")
        self.assertFalse(summary["publish_result"]["sent"])
        self.assertTrue((output_dir / "low_efficiency_level_detail_P2.card.json").exists())
        audit = (output_dir / "run_audit.jsonl").read_text(encoding="utf-8")
        self.assertIn('"node_type":"live_mode_guard"', audit)
        self.assertIn('"node_status":"authorized"', audit)

    def test_report_only_and_shadow_safe_modes_still_complete(self) -> None:
        for run_mode in ("report_only", "shadow"):
            with self.subTest(run_mode=run_mode):
                output_dir = Path(self.tmp.name) / f"orch-safe-{run_mode}"
                proc = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT),
                        "--config",
                        str(CONFIG),
                        "--sop-id",
                        "low_efficiency_labeling",
                        "--run-mode",
                        run_mode,
                        "--process-run-dir",
                        str(self.run_dir),
                        "--output-dir",
                        str(output_dir),
                        "--run-id",
                        f"RUN-SAFE-{run_mode.upper()}",
                        "--dry-run",
                    ],
                    text=True,
                    capture_output=True,
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)
                summary = json.loads(proc.stdout)
                self.assertEqual(summary["run_status"], "completed")
                self.assertEqual(summary["run_mode"], run_mode)
                self.assertTrue((output_dir / "validation_report.json").exists())
                self.assertTrue((output_dir / "low_efficiency_grading.card.json").exists())

    def test_state_writeback_preview_is_local_only(self) -> None:
        output_dir = Path(self.tmp.name) / "orch-writeback-preview"
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--config",
                str(CONFIG),
                "--sop-id",
                "low_efficiency_labeling",
                "--run-mode",
                "shadow",
                "--process-run-dir",
                str(self.run_dir),
                "--output-dir",
                str(output_dir),
                "--run-id",
                "RUN-WRITEBACK-PREVIEW",
                "--route-preview",
                "--state-writeback-preview",
                "--dry-run",
            ],
            text=True,
            capture_output=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        summary = json.loads(proc.stdout)
        preview_path = Path(summary["state_writeback_preview"])
        self.assertTrue(preview_path.exists())
        preview = json.loads(preview_path.read_text(encoding="utf-8"))
        self.assertFalse(preview["write_enabled"])
        self.assertFalse(preview["planned_event_upsert"]["write_enabled"])
        self.assertEqual(preview["summary"]["route_count"], 2)
        self.assertEqual(preview["summary"]["missing_owner_count"], 1)
        audit = (output_dir / "run_audit.jsonl").read_text(encoding="utf-8")
        self.assertIn('"node_type":"state_writeback_preview"', audit)

    def test_shadow_comparison_generated_with_baseline(self) -> None:
        self._write_low_efficiency_run_dir(
            self.baseline_dir,
            [
                {
                    "_level": "P2",
                    "reason": "baseline_reason",
                    "avg_jinshen": "60",
                    "avg_wanshen": "55",
                    "avg_dabiao": "1",
                    "ratio_val": "0.02",
                    "hit_condition": "p2",
                }
            ],
        )
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--config",
                str(CONFIG),
                "--sop-id",
                "low_efficiency_labeling",
                "--run-mode",
                "shadow",
                "--process-run-dir",
                str(self.run_dir),
                "--baseline-run-dir",
                str(self.baseline_dir),
                "--output-dir",
                str(self.output_dir),
                "--run-id",
                "RUN-COMPARE",
                "--dry-run",
            ],
            text=True,
            capture_output=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        summary = json.loads(proc.stdout)
        comparison_path = Path(summary["shadow_comparison"])
        self.assertTrue(comparison_path.exists())
        comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
        self.assertEqual(comparison["row_count"], {"baseline": 1, "current": 2, "delta": 1})
        self.assertEqual(comparison["top_reason"]["baseline"], "baseline_reason")
        self.assertEqual(comparison["top_reason"]["current"], "N1_chuxing_model_llm_pe_review")
        self.assertTrue(comparison["top_reason"]["changed"])
        self.assertEqual(comparison["level_counts"]["P2"], {"baseline": 1, "current": 2, "delta": 1})
        audit = (self.output_dir / "run_audit.jsonl").read_text(encoding="utf-8")
        self.assertIn('"node_type":"shadow_comparison"', audit)
        self.assertIn('"node_status":"success"', audit)

    def test_shadow_comparison_warns_when_baseline_csv_missing(self) -> None:
        self._write_low_efficiency_run_dir(self.baseline_dir)
        (self.baseline_dir / "综合.csv").unlink()
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--config",
                str(CONFIG),
                "--sop-id",
                "low_efficiency_labeling",
                "--run-mode",
                "report_only",
                "--process-run-dir",
                str(self.run_dir),
                "--baseline-run-dir",
                str(self.baseline_dir),
                "--output-dir",
                str(self.output_dir),
                "--run-id",
                "RUN-COMPARE-WARN",
                "--dry-run",
            ],
            text=True,
            capture_output=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        summary = json.loads(proc.stdout)
        comparison = json.loads(Path(summary["shadow_comparison"]).read_text(encoding="utf-8"))
        self.assertEqual(comparison["diff_summary"]["status"], "warning")
        self.assertTrue(any("baseline_core_csv_missing" in item for item in comparison["warnings"]))
        audit = (self.output_dir / "run_audit.jsonl").read_text(encoding="utf-8")
        self.assertIn('"node_type":"shadow_comparison"', audit)
        self.assertIn('"node_status":"warning"', audit)

    def test_missing_process_artifact_blocks(self) -> None:
        (self.run_dir / "综合.csv").unlink()
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--config",
                str(CONFIG),
                "--sop-id",
                "low_efficiency_labeling",
                "--run-mode",
                "report_only",
                "--process-run-dir",
                str(self.run_dir),
                "--output-dir",
                str(self.output_dir),
                "--run-id",
                "RUN-BLOCK",
            ],
            text=True,
            capture_output=True,
        )
        self.assertEqual(proc.returncode, 2)
        summary = json.loads(proc.stdout)
        self.assertEqual(summary["run_status"], "blocked")
        self.assertEqual(summary["stop_reason"], "process_artifacts_missing")

    def test_fixed_low_efficiency_fixture_runs(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--config",
                str(CONFIG),
                "--sop-id",
                "low_efficiency_labeling",
                "--run-mode",
                "report_only",
                "--process-run-dir",
                str(FIXTURE_RUN_DIR),
                "--output-dir",
                str(self.output_dir),
                "--run-id",
                "RUN-FIXTURE",
                "--route-preview",
                "--dry-run",
            ],
            text=True,
            capture_output=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        summary = json.loads(proc.stdout)
        self.assertEqual(summary["run_status"], "completed")
        self.assertTrue((self.output_dir / "low_efficiency_grading.card.json").exists())
        routes = json.loads((self.output_dir / "route_results.json").read_text(encoding="utf-8"))
        self.assertEqual(routes["summary"]["hit_count"], 2)
        self.assertEqual(routes["summary"]["routed_count"], 1)
        self.assertEqual(routes["summary"]["missing_owner_count"], 1)


if __name__ == "__main__":
    unittest.main()
