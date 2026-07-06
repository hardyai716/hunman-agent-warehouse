#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local smoke test for the low-efficiency SOP-first orchestration flow.

The smoke is intentionally offline-only:
- no Lark import;
- no message send;
- no event table write.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any


SCRIPT_PATH = Path(__file__).resolve()
SKILL_DIR = SCRIPT_PATH.parents[1]
SKILLS_DIR = SKILL_DIR.parent
CONFIG_PATH = SKILLS_DIR / "review-monitoring-shared" / "examples" / "low_efficiency_sop_config.sample.json"
FIXTURE_DIR = SKILL_DIR / "examples" / "low_efficiency_run"
SOP_ID = "low_efficiency_labeling"
RUN_ID = "SMOKE-LOW-EFFICIENCY-SOP"

sys.path.insert(0, str(SKILL_DIR / "scripts"))
sys.path.insert(0, str(SKILLS_DIR / "review-monitoring-shared" / "scripts"))
sys.path.insert(0, str(SKILLS_DIR / "owner-routing" / "scripts"))
sys.path.insert(0, str(SKILLS_DIR / "anomaly-touch" / "scripts"))

from config_linter import load_config, validation_report  # noqa: E402
from report_policy import publish_report_from_policy  # noqa: E402
from route_owner import read_hits, route_hits  # noqa: E402
from run_orchestrator import OrchestratorRun  # noqa: E402


FORBIDDEN_FIXTURE_PATTERNS = {
    "access token": re.compile(r"(?i)\b(access[_-]?token|bearer\s+[A-Za-z0-9._-]+)\b"),
    "secret": re.compile(r"(?i)\b(app[_-]?secret|secret[_-]?key)\b"),
    "open_id": re.compile(r"\bou_[A-Za-z0-9_-]+\b"),
    "chat_id": re.compile(r"\boc_[A-Za-z0-9_-]+\b"),
    "token-like lark url": re.compile(r"(?i)larkoffice\.com/(?:sheets|base|docx|wiki)/[A-Za-z0-9_-]+"),
}


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def assert_file(path: Path) -> None:
    if not path.exists():
        raise AssertionError(f"expected artifact missing: {path}")


def assert_summary_passed(summary: dict[str, Any], label: str) -> None:
    if summary.get("run_status") != "completed":
        raise AssertionError(f"{label} did not complete: {json.dumps(summary, ensure_ascii=False)}")


def lint_fixture_secrets(fixture_dir: Path) -> list[str]:
    violations: list[str] = []
    for path in sorted(fixture_dir.iterdir()):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8-sig")
        for label, pattern in FORBIDDEN_FIXTURE_PATTERNS.items():
            if pattern.search(text):
                violations.append(f"{path.name}: {label}")
    return violations


def run_config_lint(config: dict[str, Any], output_root: Path) -> dict[str, Any]:
    report = validation_report(config, mode="shadow", sop_id=SOP_ID)
    write_json(output_root / "config_lint" / "validation_report.json", report)
    if report["summary"]["status"] != "passed":
        raise AssertionError(f"config lint failed: {json.dumps(report, ensure_ascii=False)}")
    return report


def run_route_preview(config: dict[str, Any], output_root: Path) -> dict[str, Any]:
    routes = route_hits(config, SOP_ID, read_hits(FIXTURE_DIR / "综合.csv"), run_id=RUN_ID)
    write_json(output_root / "route_preview" / "route_results.json", routes)
    summary = routes["summary"]
    expected = {"hit_count": 2, "routed_count": 1, "missing_owner_count": 1}
    for key, value in expected.items():
        if summary.get(key) != value:
            raise AssertionError(f"route preview {key} expected {value}, got {summary.get(key)}")
    missing = [item for item in routes["route_results"] if item.get("missing_object_owner")]
    if not missing or missing[0].get("missing_reason") != "owner_mapping_not_found":
        raise AssertionError("route preview did not preserve explicit missing owner reason")
    return routes


def run_report_card_dry_run(config: dict[str, Any], output_root: Path) -> dict[str, Any]:
    output_dir = output_root / "report_card_dry_run"
    result = publish_report_from_policy(
        config=config,
        sop_id=SOP_ID,
        run_dir=FIXTURE_DIR,
        report_type="low_efficiency_grading",
        output_dir=output_dir,
        run_id=RUN_ID,
        dry_run=True,
    )
    assert_file(Path(result.card_json))
    assert_file(Path(result.card_json_with_meta))
    assert_file(output_dir / "low_efficiency_grading.publish_summary.json")
    if result.sent:
        raise AssertionError("dry-run report card must not send a message")
    return result.__dict__


def run_orchestrator_mode(config: dict[str, Any], output_root: Path, mode: str) -> dict[str, Any]:
    output_dir = output_root / f"orchestrator_{mode}"
    run = OrchestratorRun(
        config_path=CONFIG_PATH,
        config=config,
        sop_id=SOP_ID,
        run_mode=mode,
        process_run_dir=FIXTURE_DIR,
        output_dir=output_dir,
        run_id=f"{RUN_ID}-{mode.upper()}",
        dry_run=True,
        report_policy_id=None,
        report_type="low_efficiency_grading",
        route_preview=True,
        baseline_run_dir=None,
    )
    summary = run.run()
    assert_summary_passed(summary, f"orchestrator {mode}")
    for name in (
        "validation_report.json",
        "run_audit.jsonl",
        "run_summary.json",
        "route_results.json",
        "low_efficiency_grading.card.json",
        "low_efficiency_grading.card.with_meta.json",
        "low_efficiency_grading.publish_summary.json",
    ):
        assert_file(output_dir / name)

    routes = json.loads((output_dir / "route_results.json").read_text(encoding="utf-8"))
    if routes["summary"]["missing_owner_count"] != 1:
        raise AssertionError(f"orchestrator {mode} route preview should keep one missing owner")
    return summary


def smoke(output_root: Path) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    for required in (CONFIG_PATH, FIXTURE_DIR / "summary.json", FIXTURE_DIR / "综合.csv"):
        assert_file(required)

    secret_violations = lint_fixture_secrets(FIXTURE_DIR)
    if secret_violations:
        raise AssertionError("fixture contains forbidden identifiers: " + "; ".join(secret_violations))

    config = load_config(CONFIG_PATH)
    config_report = run_config_lint(config, output_root)
    route_preview = run_route_preview(config, output_root)
    report_card = run_report_card_dry_run(config, output_root)
    report_only = run_orchestrator_mode(config, output_root, "report_only")
    shadow = run_orchestrator_mode(config, output_root, "shadow")

    result = {
        "schema_version": "low_efficiency_sop_smoke.v1",
        "status": "passed",
        "fixture_dir": str(FIXTURE_DIR),
        "output_root": str(output_root),
        "checks": {
            "fixture_secret_lint": "passed",
            "config_lint": config_report["summary"],
            "route_preview": route_preview["summary"],
            "report_card_dry_run": {
                "sent": report_card["sent"],
                "card_json": report_card["card_json"],
            },
            "orchestrator_report_only": {
                "run_status": report_only["run_status"],
                "route_results": report_only.get("route_results"),
            },
            "orchestrator_shadow": {
                "run_status": shadow["run_status"],
                "route_results": shadow.get("route_results"),
            },
        },
    }
    write_json(output_root / "smoke_summary.json", result)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local low-efficiency SOP smoke validation.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory for smoke artifacts. Defaults to a new temporary directory.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_root = args.output_dir or Path(tempfile.mkdtemp(prefix="low_efficiency_sop_smoke_"))
    try:
        result = smoke(output_root.resolve())
    except Exception as exc:
        print(json.dumps({"status": "failed", "output_root": str(output_root), "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
