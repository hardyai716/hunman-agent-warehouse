#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Offline smoke test for low-efficiency SOP report generation.

The default path is local/Skill-first:

1. read a local sop_config.v1 config from review-monitoring-shared/examples;
2. lint the config;
3. verify registered report templates point to local template files;
4. run monitoring-orchestrator in shadow mode;
5. assert report card artifacts and publish summary are generated offline.

Pass --table-export only when you explicitly want to validate the optional
Lark Base control-plane export path.

It does not send Lark messages and does not write Base records.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SHARED_DIR = PROJECT_ROOT / "通用能力" / "review-monitoring-shared"
ANOMALY_TOUCH_DIR = PROJECT_ROOT / "通用能力" / "anomaly-touch"
ORCHESTRATOR_DIR = PROJECT_ROOT / "通用能力" / "monitoring-orchestrator"
OWNER_ROUTING_DIR = PROJECT_ROOT / "通用能力" / "owner-routing"

sys.path.insert(0, str(SHARED_DIR / "scripts"))
sys.path.insert(0, str(ANOMALY_TOUCH_DIR / "scripts"))
sys.path.insert(0, str(ORCHESTRATOR_DIR / "scripts"))
sys.path.insert(0, str(OWNER_ROUTING_DIR / "scripts"))

from config_linter import validation_report  # noqa: E402
from table_config_compiler import compile_table_config  # noqa: E402
from run_orchestrator import OrchestratorRun  # noqa: E402


DEFAULT_CONFIG = SHARED_DIR / "examples" / "low_efficiency_sop_config.sample.json"
DEFAULT_PROCESS_RUN_DIR = ORCHESTRATOR_DIR / "examples" / "low_efficiency_run"
SOP_ID = "low_efficiency_labeling"
REPORT_TYPE = "low_efficiency_grading"


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def assert_file(path: Path) -> None:
    if not path.exists():
        raise AssertionError(f"expected file missing: {path}")


def assert_no_internal_meta(path: Path) -> None:
    payload = read_json(path)

    def walk(value: Any, location: str = "$") -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if str(key).startswith("_"):
                    raise AssertionError(f"send card contains internal key {location}.{key}")
                walk(child, f"{location}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{location}[{index}]")

    walk(payload)


def assert_report_templates_registered(config: dict[str, Any], process_run_dir: Path) -> list[dict[str, Any]]:
    registry = config.get("report_template_registry")
    if not isinstance(registry, list) or not registry:
        raise AssertionError("report_template_registry is empty")

    by_type = {item.get("report_type"): item for item in registry if isinstance(item, dict)}
    if REPORT_TYPE not in by_type:
        raise AssertionError(f"missing report template registration for {REPORT_TYPE}")

    item = by_type[REPORT_TYPE]
    if not item.get("enabled", True):
        raise AssertionError(f"report template registration for {REPORT_TYPE} is disabled")

    local_template_name = item.get("local_template_name")
    if local_template_name:
        assert_file(ANOMALY_TOUCH_DIR / "templates" / str(local_template_name))
    for artifact in item.get("required_artifacts", []):
        if "{" in str(artifact):
            continue
        assert_file(process_run_dir / str(artifact))

    return [
        {
            "report_type": item.get("report_type"),
            "template_name": item.get("template_name"),
            "local_template_name": local_template_name,
        }
    ]


def assert_card_outputs(output_dir: Path) -> dict[str, Any]:
    card_path = output_dir / f"{REPORT_TYPE}.card.json"
    meta_path = output_dir / f"{REPORT_TYPE}.card.with_meta.json"
    publish_summary_path = output_dir / f"{REPORT_TYPE}.publish_summary.json"
    route_results_path = output_dir / "route_results.json"

    for path in (card_path, meta_path, publish_summary_path, route_results_path):
        assert_file(path)

    assert_no_internal_meta(card_path)

    meta_card = read_json(meta_path)
    meta = meta_card.get("_meta") if isinstance(meta_card, dict) else None
    if not isinstance(meta, dict) or not meta.get("_data_hash"):
        raise AssertionError("card.with_meta missing _meta._data_hash")

    publish_summary = read_json(publish_summary_path)
    if publish_summary.get("sent") is not False:
        raise AssertionError("smoke must not send Lark messages")
    if publish_summary.get("report_type") != REPORT_TYPE:
        raise AssertionError(f"unexpected report_type: {publish_summary.get('report_type')}")

    route_results = read_json(route_results_path)
    route_summary = route_results.get("summary", {})
    if route_summary.get("hit_count", 0) <= 0:
        raise AssertionError("route preview did not read any hit rows")

    return {
        "card_json": str(card_path),
        "card_json_with_meta": str(meta_path),
        "publish_summary": str(publish_summary_path),
        "data_hash": meta["_data_hash"],
        "route_summary": route_summary,
    }


def load_config(config_path: Path, table_export: Path | None, output_dir: Path) -> tuple[dict[str, Any], Path, str]:
    if table_export is not None:
        assert_file(table_export)
        config = compile_table_config(read_json(table_export))
        compiled_config_path = output_dir / "compiled_sop_config.json"
        write_json(compiled_config_path, config)
        return config, compiled_config_path, "base_table_export"

    assert_file(config_path)
    return read_json(config_path), config_path, "local_sop_config"


def run_smoke(config_path: Path, table_export: Path | None, process_run_dir: Path, output_dir: Path) -> dict[str, Any]:
    assert_file(process_run_dir / "summary.json")
    assert_file(process_run_dir / "综合.csv")

    config, effective_config_path, config_source = load_config(config_path, table_export, output_dir)

    lint_report = validation_report(config, mode="shadow", sop_id=SOP_ID)
    write_json(output_dir / "validation_report.json", lint_report)
    if lint_report["summary"]["status"] != "passed":
        raise AssertionError(f"config lint failed: {json.dumps(lint_report, ensure_ascii=False)}")

    checked_templates = assert_report_templates_registered(config, process_run_dir)

    orchestrator_output_dir = output_dir / "orchestrator_shadow"
    run = OrchestratorRun(
        config_path=effective_config_path,
        config=config,
        sop_id=SOP_ID,
        run_mode="shadow",
        process_run_dir=process_run_dir,
        output_dir=orchestrator_output_dir,
        run_id=f"SOP-TEMPLATE-SMOKE-{utc_stamp()}",
        dry_run=True,
        report_policy_id=None,
        report_type=REPORT_TYPE,
        route_preview=True,
        state_writeback_preview=False,
        baseline_run_dir=None,
        production_authorization_file=None,
    )
    run_summary = run.run()
    if run_summary.get("run_status") != "completed":
        raise AssertionError(f"orchestrator did not complete: {json.dumps(run_summary, ensure_ascii=False)}")

    output_checks = assert_card_outputs(orchestrator_output_dir)

    result = {
        "schema_version": "low_efficiency_sop_template_smoke.v1",
        "status": "passed",
        "config_source": config_source,
        "config_path": str(config_path),
        "table_export": str(table_export) if table_export else None,
        "process_run_dir": str(process_run_dir),
        "output_dir": str(output_dir),
        "effective_config": str(effective_config_path),
        "validation_summary": lint_report["summary"],
        "checked_report_templates": checked_templates,
        "orchestrator_summary": str(orchestrator_output_dir / "run_summary.json"),
        "report_outputs": output_checks,
    }
    write_json(output_dir / "smoke_summary.json", result)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test low-efficiency SOP report generation.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Local sop_config.v1 JSON. Default is Skill-first.")
    parser.add_argument(
        "--table-export",
        type=Path,
        help="Optional Base table export JSON. When set, it is compiled and used instead of --config.",
    )
    parser.add_argument("--process-run-dir", type=Path, default=DEFAULT_PROCESS_RUN_DIR)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "dist" / "smoke_low_efficiency_sop_template" / utc_stamp())
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = run_smoke(
            config_path=args.config.resolve(),
            table_export=args.table_export.resolve() if args.table_export else None,
            process_run_dir=args.process_run_dir.resolve(),
            output_dir=args.output_dir.resolve(),
        )
    except Exception as exc:
        failure = {
            "schema_version": "low_efficiency_sop_template_smoke.v1",
            "status": "failed",
            "output_dir": str(args.output_dir),
            "error": str(exc),
        }
        write_json(args.output_dir / "smoke_summary.json", failure)
        print(json.dumps(failure, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
