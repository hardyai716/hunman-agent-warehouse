#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

import config_linter


SAMPLE_CONFIG = Path(__file__).resolve().parents[1] / "examples" / "low_efficiency_sop_config.sample.json"


def load_sample() -> dict:
    return json.loads(SAMPLE_CONFIG.read_text(encoding="utf-8"))


def check_ids(report: dict) -> set[str]:
    return {finding["check_id"] for finding in report["findings"]}


class ConfigLinterTest(unittest.TestCase):
    def test_sample_config_passes(self) -> None:
        report = config_linter.validation_report(load_sample(), mode="shadow", sop_id="low_efficiency_labeling")
        self.assertEqual(report["summary"]["status"], "passed", report["findings"])
        self.assertEqual(report["summary"]["error_count"], 0)
        self.assertEqual(report["summary"]["blocker_count"], 0)

    def test_unknown_process_skill_fails(self) -> None:
        config = load_sample()
        config["sops"][0]["process_skill"] = "unknown-skill"
        report = config_linter.validation_report(config)
        self.assertEqual(report["summary"]["status"], "failed")
        self.assertIn("PROCESS_SKILL_NOT_REGISTERED", check_ids(report))

    def test_cross_sop_level_fails(self) -> None:
        config = load_sample()
        config["sops"][0]["rule_groups"][0]["sop_level_id"] = "other_sop_p2"
        report = config_linter.validation_report(config)
        self.assertEqual(report["summary"]["status"], "failed")
        self.assertIn("RULE_LEVEL_NOT_IN_SOP", check_ids(report))

    def test_shadow_auto_send_is_blocker(self) -> None:
        config = load_sample()
        config["sops"][0]["report_policies"][0]["report_target_policy"]["auto_send"] = True
        report = config_linter.validation_report(config)
        self.assertEqual(report["summary"]["status"], "failed")
        self.assertEqual(report["summary"]["blocker_count"], 1)
        self.assertIn("SHADOW_REPORT_AUTO_SEND", check_ids(report))

    def test_external_dependency_in_required_siblings_fails(self) -> None:
        config = load_sample()
        process = copy.deepcopy(config["process_skill_registry"][0])
        process["process_skill"] = "bad-process"
        process["required_siblings"] = ["warehouse-skill", "lark-im"]
        config["process_skill_registry"].append(process)
        report = config_linter.validation_report(config)
        self.assertEqual(report["summary"]["status"], "failed")
        self.assertIn("EXTERNAL_DEP_IN_REQUIRED_SIBLINGS", check_ids(report))


if __name__ == "__main__":
    unittest.main()
