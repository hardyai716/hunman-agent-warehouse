#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import unittest
from pathlib import Path

import route_owner


CONFIG = Path(__file__).resolve().parents[2] / "review-monitoring-shared" / "examples" / "low_efficiency_sop_config.sample.json"


def load_config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


class RouteOwnerTest(unittest.TestCase):
    def test_reason_routes_to_distinct_owners(self) -> None:
        hits = [
            {"hit_id": "h1", "_level": "P2", "reason": "N1_chuxing_model_llm_pe_review", "metric_id": "metric_low_label_rate_reason"},
            {"hit_id": "h2", "_level": "P2", "reason": "political_figure_risk_review", "metric_id": "metric_low_label_rate_reason"},
        ]
        result = route_owner.route_hits(load_config(), "low_efficiency_labeling", hits, run_id="RUN-1")
        self.assertEqual(result["summary"]["routed_count"], 2)
        self.assertEqual(result["summary"]["missing_owner_count"], 0)
        owners = [item["owners"][0]["id"] for item in result["route_results"]]
        self.assertEqual(owners, ["ou_owner_a", "ou_owner_b"])
        self.assertEqual(result["route_results"][0]["delivery_policy"]["chat_id"], "oc_reason_a")
        self.assertEqual(result["route_results"][1]["delivery_policy"]["chat_id"], "oc_reason_b")

    def test_missing_reason_owner_is_explicit(self) -> None:
        hits = [{"hit_id": "h1", "_level": "P2", "reason": "unknown_reason"}]
        result = route_owner.route_hits(load_config(), "low_efficiency_labeling", hits, run_id="RUN-1")
        route = result["route_results"][0]
        self.assertEqual(result["summary"]["missing_owner_count"], 1)
        self.assertTrue(route["missing_object_owner"])
        self.assertEqual(route["missing_reason"], "owner_mapping_not_found")
        self.assertEqual(route["delivery_policy"]["chat_strategy"], "manual_fallback")

    def test_default_owner_mapping_routes_unknown_reason(self) -> None:
        config = load_config()
        source = config["owner_source_registry"][0]
        source["mappings"].append(
            {
                "route_key": "__default__",
                "route_key_alias": "默认 owner",
                "owner_role": "默认负责人",
                "owner_user": {"id": "ou_default_owner", "name": "默认负责人"},
                "enabled": True,
                "priority": 9999,
            }
        )
        hits = [{"hit_id": "h1", "_level": "P2", "reason": "unknown_reason"}]
        result = route_owner.route_hits(config, "low_efficiency_labeling", hits, run_id="RUN-1")
        route = result["route_results"][0]
        self.assertEqual(result["summary"]["missing_owner_count"], 0)
        self.assertFalse(route["missing_object_owner"])
        self.assertEqual(route["owners"][0]["id"], "ou_default_owner")

    def test_no_route_policy_match_is_missing_owner(self) -> None:
        hits = [{"hit_id": "h1", "_level": "P2", "strategy": "strategy_a"}]
        result = route_owner.route_hits(load_config(), "low_efficiency_labeling", hits, run_id="RUN-1")
        route = result["route_results"][0]
        self.assertTrue(route["missing_object_owner"])
        self.assertEqual(route["missing_reason"], "no_route_policy_matched")


if __name__ == "__main__":
    unittest.main()
