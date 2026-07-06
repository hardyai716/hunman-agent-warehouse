#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Offline production-readiness preflight for local handoff artifacts."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUMMARY_REL = Path("dist/production_readiness/readiness_summary.json")

SPEC_DIR_REL = Path(".trae/specs/design-monitoring-system-architecture")
ACCEPTANCE_SUMMARY_REL = Path("dist/final_acceptance/acceptance_summary.json")
AGENT_ZIPS_DIR_REL = Path("dist/agent_upload/zips")
AGENT_BUILD_SUMMARY_REL = Path("dist/agent_upload/build_summary.json")
AGENT_MANIFEST_REL = Path("tools/agent_skill_manifest.json")

REQUIRED_SKILL_NAMES = {
    "review-monitoring-shared",
    "warehouse-skill",
    "owner-routing",
    "monitoring-orchestrator",
    "anomaly-touch",
    "low-efficiency-strategy-analysis",
}

REQUIRED_DOCUMENTS = {
    "spec": SPEC_DIR_REL / "spec.md",
    "tasks": SPEC_DIR_REL / "tasks.md",
    "checklist": SPEC_DIR_REL / "checklist.md",
    "readme": Path("README.md"),
    "agent_platform_upload": Path("AGENT_PLATFORM_UPLOAD.md"),
}

STALE_DOC_PATTERNS = {
    "stale_five_packages": re.compile(r"(?<!\d)(?:5\s*个包|5个包|五个包|5\s*包)(?!\d)"),
    "stale_orchestrator_deferred": re.compile(r"orchestrator\s*暂缓", re.I),
}

EXTERNAL_SIBLING_NAMES = {
    "sqless",
    "sqless-data-analysis",
    "bytedcli",
    "bytedance-aeolus",
    "bytedance_aeolus",
}
EXTERNAL_SIBLING_PREFIXES = ("lark-", "aeolus", "bytedance-aeolus", "bytedance_aeolus")

MARKDOWN_UNCHECKED_RE = re.compile(r"^\s*[-*]\s+\[\s\]\s+(?P<text>.+?)\s*$")
ROUND5_TASK_RE = re.compile(r"\b(?:Task|SubTask)\s+(?:18|19|20|21|22)(?:\b|\.)")
FRONTMATTER_RE = re.compile(r"^---\n(?P<body>.*?)\n---\n", re.S)
FRONTMATTER_NAME_RE = re.compile(r"^name:\s*[\"']?(?P<name>[^\"'\n]+)[\"']?\s*$", re.M)
JSON_TEXT_SUFFIXES = {".json"}
TEXT_MEMBER_SUFFIXES = {".json", ".md", ".yaml", ".yml"}

LIVE_HANDOFF_SCHEMA_VERSION = "live_handoff.v1"
LIVE_HANDOFF_MANUAL_ACTIONS = {
    "lark_aeolus_live_side_effects": "requires_platform_credentials_and_manual_enablement",
    "agent_platform_upload": "requires_manual_platform_upload",
    "production_event_writeback": "requires_production_config_and_manual_enablement",
    "canary": "requires_explicit_single_target_authorization_file",
    "active_touch_execute": "blocked_by_default_in_mvp",
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def rel_path(path: Path, project_root: Path) -> str:
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def issue(
    check: str,
    message: str,
    *,
    path: Path | str | None = None,
    line: int | None = None,
    code: str | None = None,
    project_root: Path | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "check": check,
        "message": message,
        "severity": "blocker",
    }
    if code:
        payload["code"] = code
    if path is not None:
        if isinstance(path, Path) and project_root is not None:
            payload["path"] = rel_path(path, project_root)
        else:
            payload["path"] = str(path)
    if line is not None:
        payload["line"] = line
    return payload


def check_payload(name: str, issues: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "status": "passed" if not issues else "failed",
        "issues": issues,
    }
    payload.update(extra)
    return payload


def read_text(path: Path, check: str, issues: list[dict[str, Any]], project_root: Path) -> str | None:
    if not path.exists():
        issues.append(issue(check, "required file missing", path=path, code="missing_file", project_root=project_root))
        return None
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        issues.append(
            issue(
                check,
                f"file is not valid UTF-8: {exc}",
                path=path,
                code="invalid_utf8",
                project_root=project_root,
            )
        )
        return None


def read_json(path: Path, check: str, issues: list[dict[str, Any]], project_root: Path) -> dict[str, Any] | None:
    text = read_text(path, check, issues, project_root)
    if text is None:
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        issues.append(
            issue(
                check,
                f"invalid JSON: {exc}",
                path=path,
                code="invalid_json",
                project_root=project_root,
            )
        )
        return None
    if not isinstance(value, dict):
        issues.append(
            issue(check, "JSON root must be an object", path=path, code="invalid_json_root", project_root=project_root)
        )
        return None
    return value


def read_json_value(path: Path, check: str, issues: list[dict[str, Any]], project_root: Path) -> Any:
    text = read_text(path, check, issues, project_root)
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        issues.append(
            issue(
                check,
                f"invalid JSON: {exc}",
                path=path,
                code="invalid_json",
                project_root=project_root,
            )
        )
        return None


def parse_frontmatter_name(text: str) -> str | None:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None
    name_match = FRONTMATTER_NAME_RE.search(match.group("body"))
    if not name_match:
        return None
    return name_match.group("name").strip()


def check_final_acceptance(project_root: Path) -> dict[str, Any]:
    check = "final_acceptance_summary"
    issues: list[dict[str, Any]] = []
    path = project_root / ACCEPTANCE_SUMMARY_REL
    data = read_json(path, check, issues, project_root)
    reported_status = None
    failed_items: list[str] = []
    checks_count = 0

    if data is not None:
        reported_status = data.get("status")
        if reported_status != "passed":
            issues.append(
                issue(
                    check,
                    f"acceptance summary status is {reported_status!r}, expected 'passed'",
                    path=path,
                    code="acceptance_not_passed",
                    project_root=project_root,
                )
            )
        items = data.get("checks") if isinstance(data.get("checks"), list) else data.get("items")
        if isinstance(items, list):
            checks_count = len(items)
            for item in items:
                if not isinstance(item, dict):
                    continue
                if item.get("status") != "passed":
                    failed_items.append(str(item.get("name", "<unnamed>")))
            if failed_items:
                issues.append(
                    issue(
                        check,
                        "acceptance checks not passed: " + ", ".join(failed_items),
                        path=path,
                        code="acceptance_item_failed",
                        project_root=project_root,
                    )
                )

    return check_payload(
        check,
        issues,
        path=rel_path(path, project_root),
        reported_status=reported_status,
        checks_count=checks_count,
        failed_items=failed_items,
    )


def is_round5_open_item(path: Path, text: str) -> bool:
    if ROUND5_TASK_RE.search(text):
        return True
    if path.name != "checklist.md":
        return False

    round5_keywords = (
        "生产化预检",
        "readiness",
        "live-mode",
        "live mode",
        "canary",
        "active",
        "最终验收入口",
        "最终验收命令重新运行",
        "README.md",
        "AGENT_PLATFORM_UPLOAD.md",
    )
    return any(keyword in text for keyword in round5_keywords)


def find_unchecked_items(path: Path, project_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    text = read_text(path, "task_checklist_completion", issues, project_root)
    if text is None:
        return [], issues

    items: list[dict[str, Any]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        match = MARKDOWN_UNCHECKED_RE.match(line)
        if not match:
            continue
        item = {
            "path": rel_path(path, project_root),
            "line": line_no,
            "text": match.group("text"),
            "round5_exemptable": is_round5_open_item(path, match.group("text")),
        }
        items.append(item)
    return items, issues


def check_task_checklist_completion(project_root: Path, allow_open_round5: bool) -> dict[str, Any]:
    check = "task_checklist_completion"
    issues: list[dict[str, Any]] = []
    tasks_path = project_root / REQUIRED_DOCUMENTS["tasks"]
    checklist_path = project_root / REQUIRED_DOCUMENTS["checklist"]

    open_items: list[dict[str, Any]] = []
    read_issues: list[dict[str, Any]] = []
    for path in (tasks_path, checklist_path):
        items, path_issues = find_unchecked_items(path, project_root)
        open_items.extend(items)
        read_issues.extend(path_issues)

    active_open_items: list[dict[str, Any]] = []
    exempted_items: list[dict[str, Any]] = []
    for item in open_items:
        if allow_open_round5 and item["round5_exemptable"]:
            exempted_items.append({**item, "reason": "allow_open_round5"})
        else:
            active_open_items.append(item)

    issues.extend(read_issues)
    for item in active_open_items:
        issues.append(
            issue(
                check,
                "unchecked task/checklist item remains open",
                path=item["path"],
                line=item["line"],
                code="unchecked_item",
            )
        )

    return check_payload(
        check,
        issues,
        allow_open_round5=allow_open_round5,
        unchecked_total=len(open_items),
        active_open_items=active_open_items,
        exempted_items=exempted_items,
    )


def check_required_documents(project_root: Path) -> dict[str, Any]:
    check = "required_documents"
    issues: list[dict[str, Any]] = []
    document_paths = {name: project_root / rel for name, rel in REQUIRED_DOCUMENTS.items()}

    for path in document_paths.values():
        if not path.exists():
            issues.append(issue(check, "required document missing", path=path, code="missing_document", project_root=project_root))

    stale_scan_rels = [
        Path("README.md"),
        Path("AGENT_PLATFORM_UPLOAD.md"),
        Path("多Skill解耦架构方案.md"),
    ]
    stale_hits: list[dict[str, Any]] = []
    for rel in stale_scan_rels:
        path = project_root / rel
        if not path.exists():
            continue
        text = read_text(path, check, issues, project_root)
        if text is None:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            for code, pattern in STALE_DOC_PATTERNS.items():
                if pattern.search(line):
                    hit = {
                        "path": rel_path(path, project_root),
                        "line": line_no,
                        "code": code,
                        "text": line.strip(),
                    }
                    stale_hits.append(hit)
                    issues.append(
                        issue(
                            check,
                            f"stale document wording detected: {code}",
                            path=path,
                            line=line_no,
                            code=code,
                            project_root=project_root,
                        )
                    )

    return check_payload(
        check,
        issues,
        documents={name: rel_path(path, project_root) for name, path in document_paths.items()},
        stale_hits=stale_hits,
    )


def expected_skills_from_manifest(project_root: Path, issues: list[dict[str, Any]]) -> set[str]:
    check = "agent_upload_zips"
    manifest_path = project_root / AGENT_MANIFEST_REL
    manifest = read_json(manifest_path, check, issues, project_root)
    if manifest is None:
        return set(REQUIRED_SKILL_NAMES)

    skills = manifest.get("skills")
    if not isinstance(skills, list):
        issues.append(
            issue(check, "manifest skills must be a list", path=manifest_path, code="invalid_manifest", project_root=project_root)
        )
        return set(REQUIRED_SKILL_NAMES)

    manifest_names = {item.get("name") for item in skills if isinstance(item, dict)}
    if manifest_names != REQUIRED_SKILL_NAMES:
        issues.append(
            issue(
                check,
                "manifest skill set does not match required 6-skill deliverable",
                path=manifest_path,
                code="manifest_skill_set_mismatch",
                project_root=project_root,
            )
        )
    if len(manifest_names) != 6:
        issues.append(
            issue(
                check,
                f"manifest should declare exactly 6 skills, found {len(manifest_names)}",
                path=manifest_path,
                code="manifest_skill_count_mismatch",
                project_root=project_root,
            )
        )
    return set(REQUIRED_SKILL_NAMES)


def read_build_summary_skills(project_root: Path, issues: list[dict[str, Any]]) -> set[str] | None:
    check = "agent_upload_zips"
    path = project_root / AGENT_BUILD_SUMMARY_REL
    data = read_json(path, check, issues, project_root)
    if data is None:
        return None
    skills = data.get("skills")
    if not isinstance(skills, list):
        issues.append(
            issue(check, "build summary skills must be a list", path=path, code="invalid_build_summary", project_root=project_root)
        )
        return None
    return {str(skill) for skill in skills}


def audit_skill_zip(zip_path: Path, expected_name: str, project_root: Path) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    members: list[str] = []
    actual_name: str | None = None

    try:
        with zipfile.ZipFile(zip_path) as zf:
            members = zf.namelist()
            if "SKILL.md" not in members:
                issues.append(
                    issue(
                        "agent_upload_zips",
                        "zip root SKILL.md missing",
                        path=zip_path,
                        code="zip_missing_root_skill_md",
                        project_root=project_root,
                    )
                )
            else:
                try:
                    skill_text = zf.read("SKILL.md").decode("utf-8")
                except UnicodeDecodeError as exc:
                    issues.append(
                        issue(
                            "agent_upload_zips",
                            f"SKILL.md is not valid UTF-8: {exc}",
                            path=zip_path,
                            code="zip_skill_md_invalid_utf8",
                            project_root=project_root,
                        )
                    )
                else:
                    actual_name = parse_frontmatter_name(skill_text)
                    if actual_name != expected_name:
                        issues.append(
                            issue(
                                "agent_upload_zips",
                                f"SKILL.md name is {actual_name!r}, expected {expected_name!r}",
                                path=zip_path,
                                code="zip_skill_name_mismatch",
                                project_root=project_root,
                            )
                        )
    except zipfile.BadZipFile as exc:
        issues.append(
            issue(
                "agent_upload_zips",
                f"invalid zip file: {exc}",
                path=zip_path,
                code="bad_zip",
                project_root=project_root,
            )
        )

    return {
        "zip": rel_path(zip_path, project_root),
        "expected_name": expected_name,
        "actual_name": actual_name,
        "member_count": len(members),
        "size_bytes": zip_path.stat().st_size if zip_path.exists() else None,
        "status": "passed" if not issues else "failed",
        "issues": issues,
    }


def check_agent_upload_zips(project_root: Path) -> dict[str, Any]:
    check = "agent_upload_zips"
    issues: list[dict[str, Any]] = []
    expected_names = expected_skills_from_manifest(project_root, issues)
    build_summary_skills = read_build_summary_skills(project_root, issues)
    if build_summary_skills is not None and build_summary_skills != REQUIRED_SKILL_NAMES:
        issues.append(
            issue(
                check,
                "build summary skill set does not match required 6-skill deliverable",
                path=project_root / AGENT_BUILD_SUMMARY_REL,
                code="build_summary_skill_set_mismatch",
                project_root=project_root,
            )
        )

    zips_dir = project_root / AGENT_ZIPS_DIR_REL
    zip_details: list[dict[str, Any]] = []
    if not zips_dir.exists():
        issues.append(issue(check, "zip directory missing", path=zips_dir, code="missing_zips_dir", project_root=project_root))
        return check_payload(check, issues, zips_dir=rel_path(zips_dir, project_root), zips=zip_details)

    zip_paths = sorted(zips_dir.glob("*.zip"))
    found_names = {path.stem for path in zip_paths}
    if found_names != expected_names:
        missing = sorted(expected_names - found_names)
        extra = sorted(found_names - expected_names)
        issues.append(
            issue(
                check,
                f"zip set mismatch; missing={missing}, extra={extra}",
                path=zips_dir,
                code="zip_set_mismatch",
                project_root=project_root,
            )
        )
    if len(zip_paths) != 6:
        issues.append(
            issue(
                check,
                f"expected exactly 6 single-skill zip files, found {len(zip_paths)}",
                path=zips_dir,
                code="zip_count_mismatch",
                project_root=project_root,
            )
        )

    for skill_name in sorted(expected_names):
        zip_path = zips_dir / f"{skill_name}.zip"
        if not zip_path.exists():
            continue
        detail = audit_skill_zip(zip_path, skill_name, project_root)
        zip_details.append(detail)
        issues.extend(detail["issues"])

    return check_payload(
        check,
        issues,
        expected_skills=sorted(expected_names),
        zips_dir=rel_path(zips_dir, project_root),
        zips=zip_details,
    )


def walk_json(value: Any, path: str = "$") -> list[tuple[str, Any]]:
    nodes = [(path, value)]
    if isinstance(value, dict):
        for key, child in value.items():
            nodes.extend(walk_json(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            nodes.extend(walk_json(child, f"{path}[{index}]"))
    return nodes


def is_external_sibling(name: str) -> bool:
    normalized = name.strip().strip("\"'")
    lowered = normalized.lower()
    return lowered in EXTERNAL_SIBLING_NAMES or lowered.startswith(EXTERNAL_SIBLING_PREFIXES)


def audit_json_required_siblings(value: Any, source: str) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for json_path, node in walk_json(value):
        key = json_path.rsplit(".", 1)[-1]
        if key not in {"required_siblings", "siblings"}:
            continue
        if not isinstance(node, list):
            continue
        for sibling in node:
            if isinstance(sibling, str) and is_external_sibling(sibling):
                hits.append({"source": source, "json_path": json_path, "sibling": sibling})
    return hits


def parse_inline_list(value: str) -> list[str]:
    value = value.strip()
    if not value.startswith("[") or not value.endswith("]"):
        return []
    inner = value[1:-1].strip()
    if not inner:
        return []
    return [part.strip().strip("\"'") for part in inner.split(",") if part.strip()]


def extract_frontmatter_siblings(text: str) -> list[str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return []
    lines = match.group("body").splitlines()
    siblings: list[str] = []
    for index, line in enumerate(lines):
        sibling_match = re.match(r"^(?P<indent>\s*)siblings:\s*(?P<value>.*)$", line)
        if not sibling_match:
            continue
        value = sibling_match.group("value").strip()
        if value.startswith("["):
            siblings.extend(parse_inline_list(value))
            continue

        base_indent = len(sibling_match.group("indent"))
        for child in lines[index + 1 :]:
            if not child.strip():
                continue
            child_indent = len(child) - len(child.lstrip(" "))
            if child_indent <= base_indent:
                break
            item_match = re.match(r"^\s*-\s*[\"']?(?P<item>[^\"'#\n]+)", child)
            if item_match:
                siblings.append(item_match.group("item").strip())
    return siblings


def dependency_scan_files(project_root: Path) -> list[Path]:
    scan_roots = [
        project_root / "tools",
        project_root / "通用能力",
        project_root / "效率模块",
        project_root / "质量模块",
        project_root / "成本模块",
    ]
    files: list[Path] = []
    for root in scan_roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if any(part in {"__pycache__", ".pytest_cache"} for part in path.parts):
                continue
            if path.name == "SKILL.md" or path.suffix.lower() in {".json", ".yaml", ".yml"}:
                files.append(path)
    return files


def check_dependency_boundary(project_root: Path) -> dict[str, Any]:
    check = "dependency_boundary"
    issues: list[dict[str, Any]] = []
    hits: list[dict[str, Any]] = []
    scanned_sources: list[str] = []

    for path in dependency_scan_files(project_root):
        scanned_sources.append(rel_path(path, project_root))
        if path.suffix.lower() == ".json":
            data = read_json_value(path, check, issues, project_root)
            if data is None:
                continue
            for hit in audit_json_required_siblings(data, rel_path(path, project_root)):
                hits.append(hit)
                issues.append(
                    issue(
                        check,
                        f"external platform capability declared as required sibling: {hit['sibling']}",
                        path=path,
                        code="external_required_sibling",
                        project_root=project_root,
                    )
                )
        elif path.name == "SKILL.md":
            text = read_text(path, check, issues, project_root)
            if text is None:
                continue
            for sibling in extract_frontmatter_siblings(text):
                if is_external_sibling(sibling):
                    hit = {"source": rel_path(path, project_root), "json_path": "frontmatter.requires.siblings", "sibling": sibling}
                    hits.append(hit)
                    issues.append(
                        issue(
                            check,
                            f"external platform capability declared as required sibling: {sibling}",
                            path=path,
                            code="external_required_sibling",
                            project_root=project_root,
                        )
                    )

    zips_dir = project_root / AGENT_ZIPS_DIR_REL
    for zip_path in sorted(zips_dir.glob("*.zip")) if zips_dir.exists() else []:
        try:
            with zipfile.ZipFile(zip_path) as zf:
                for member in zf.namelist():
                    if member.endswith("/") or Path(member).suffix.lower() not in TEXT_MEMBER_SUFFIXES:
                        continue
                    if member != "SKILL.md" and Path(member).suffix.lower() != ".json":
                        continue
                    source = f"{rel_path(zip_path, project_root)}:{member}"
                    scanned_sources.append(source)
                    try:
                        text = zf.read(member).decode("utf-8")
                    except UnicodeDecodeError as exc:
                        issues.append(
                            issue(check, f"zip text member is not UTF-8: {exc}", path=source, code="zip_member_invalid_utf8")
                        )
                        continue
                    if member == "SKILL.md":
                        for sibling in extract_frontmatter_siblings(text):
                            if is_external_sibling(sibling):
                                hit = {"source": source, "json_path": "frontmatter.requires.siblings", "sibling": sibling}
                                hits.append(hit)
                                issues.append(
                                    issue(
                                        check,
                                        f"external platform capability declared as required sibling: {sibling}",
                                        path=source,
                                        code="external_required_sibling",
                                    )
                                )
                    elif Path(member).suffix.lower() == ".json":
                        try:
                            data = json.loads(text)
                        except json.JSONDecodeError as exc:
                            issues.append(issue(check, f"invalid JSON in zip member: {exc}", path=source, code="invalid_zip_json"))
                            continue
                        for hit in audit_json_required_siblings(data, source):
                            hits.append(hit)
                            issues.append(
                                issue(
                                    check,
                                    f"external platform capability declared as required sibling: {hit['sibling']}",
                                    path=source,
                                    code="external_required_sibling",
                                )
                            )
        except zipfile.BadZipFile:
            continue

    return check_payload(
        check,
        issues,
        scanned_source_count=len(scanned_sources),
        scanned_sources=scanned_sources,
        external_required_sibling_hits=hits,
    )


def offline_safety_check(summary_path: Path | None, project_root: Path) -> dict[str, Any]:
    return check_payload(
        "offline_safety_boundary",
        [],
        guarantees={
            "lark_called": False,
            "aeolus_called": False,
            "subprocess_started": False,
            "event_main_table_written": False,
            "baseline_fixture_overwritten": False,
            "writes": [rel_path(summary_path, project_root)] if summary_path else ["readiness summary only"],
        },
    )


def live_handoff_payload() -> dict[str, Any]:
    return {
        "schema_version": LIVE_HANDOFF_SCHEMA_VERSION,
        "manual_actions": dict(LIVE_HANDOFF_MANUAL_ACTIONS),
    }


def evaluate_readiness(project_root: Path, *, allow_open_round5: bool, summary_path: Path | None = None) -> dict[str, Any]:
    project_root = project_root.resolve()
    checks = [
        check_final_acceptance(project_root),
        check_task_checklist_completion(project_root, allow_open_round5),
        check_agent_upload_zips(project_root),
        check_required_documents(project_root),
        check_dependency_boundary(project_root),
        offline_safety_check(summary_path, project_root),
    ]
    all_issues = [item for check in checks for item in check["issues"]]
    exemptions = checks[1].get("exempted_items", [])
    status = "passed" if not all_issues else "failed"
    return {
        "schema_version": "production_readiness.v1",
        "generated_at": utc_now(),
        "project_root": str(project_root),
        "summary_path": rel_path(summary_path, project_root) if summary_path else None,
        "status": status,
        "allow_open_round5": allow_open_round5,
        "live_handoff": live_handoff_payload(),
        "exemptions": exemptions,
        "issue_count": len(all_issues),
        "issues": all_issues,
        "checks": checks,
    }


def write_summary(summary: dict[str, Any], summary_path: Path) -> None:
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify local production-readiness artifacts without external side effects.")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=PROJECT_ROOT,
        help="Project root. Defaults to the repository containing this script.",
    )
    parser.add_argument(
        "--summary-out",
        type=Path,
        default=DEFAULT_SUMMARY_REL,
        help="Readiness summary output path. Relative paths are resolved under --project-root.",
    )
    parser.add_argument(
        "--allow-open-round5",
        action="store_true",
        help="Allow current Ralph Loop Task 18-22 task/checklist items to remain unchecked during Round 5 implementation.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run this script's built-in unittest self-test suite.",
    )
    return parser.parse_args(argv)


def resolve_summary_path(project_root: Path, summary_out: Path) -> Path:
    if summary_out.is_absolute():
        return summary_out
    return project_root / summary_out


class ProductionReadinessSelfTest(unittest.TestCase):
    def make_project(
        self,
        root: Path,
        *,
        open_round5: bool,
        stale_doc: bool = False,
        external_required_sibling: bool = False,
    ) -> None:
        spec_dir = root / SPEC_DIR_REL
        spec_dir.mkdir(parents=True, exist_ok=True)
        (spec_dir / "spec.md").write_text("# Spec\n", encoding="utf-8")

        task_box = "[ ]" if open_round5 else "[x]"
        (spec_dir / "tasks.md").write_text(
            f"# Tasks\n\n- {task_box} Task 18: 建立生产化预检入口\n"
            f"  - {task_box} SubTask 18.1: 新增 readiness summary\n",
            encoding="utf-8",
        )
        (spec_dir / "checklist.md").write_text(
            f"- {task_box} 存在生产化预检命令，能够输出机器可读 readiness summary\n",
            encoding="utf-8",
        )

        readme_text = "# README\n当前交付范围包含 6 个可上传 Skill。\n"
        if stale_doc:
            readme_text += "当前只有 5 个包。\n"
        (root / "README.md").write_text(readme_text, encoding="utf-8")
        (root / "AGENT_PLATFORM_UPLOAD.md").write_text("# Upload\n上传 6 个单 Skill 包。\n", encoding="utf-8")

        acceptance_dir = root / ACCEPTANCE_SUMMARY_REL.parent
        acceptance_dir.mkdir(parents=True, exist_ok=True)
        (root / ACCEPTANCE_SUMMARY_REL).write_text(
            json.dumps({"status": "passed", "checks": [{"name": "unit", "status": "passed"}]}, ensure_ascii=False),
            encoding="utf-8",
        )

        tools_dir = root / "tools"
        tools_dir.mkdir(parents=True, exist_ok=True)
        (root / AGENT_MANIFEST_REL).write_text(
            json.dumps(
                {"skills": [{"name": name, "source": name} for name in sorted(REQUIRED_SKILL_NAMES)]},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        if external_required_sibling:
            bad_dir = root / "通用能力" / "bad"
            bad_dir.mkdir(parents=True, exist_ok=True)
            (bad_dir / "config.json").write_text(
                json.dumps({"required_siblings": ["lark-im"]}, ensure_ascii=False),
                encoding="utf-8",
            )

        upload_dir = root / AGENT_ZIPS_DIR_REL
        upload_dir.mkdir(parents=True, exist_ok=True)
        (root / AGENT_BUILD_SUMMARY_REL).parent.mkdir(parents=True, exist_ok=True)
        (root / AGENT_BUILD_SUMMARY_REL).write_text(
            json.dumps({"skills": sorted(REQUIRED_SKILL_NAMES)}, ensure_ascii=False),
            encoding="utf-8",
        )
        for name in REQUIRED_SKILL_NAMES:
            with zipfile.ZipFile(upload_dir / f"{name}.zip", "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(
                    "SKILL.md",
                    f"---\nname: {name}\ndescription: self test\nmetadata:\n  requires:\n    siblings: []\n---\n# {name}\n",
                )

    def test_allow_open_round5_exempts_current_round_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root, open_round5=True)

            blocked = evaluate_readiness(root, allow_open_round5=False)
            self.assertEqual(blocked["status"], "failed")
            self.assertGreater(blocked["issue_count"], 0)

            allowed = evaluate_readiness(root, allow_open_round5=True)
            self.assertEqual(allowed["status"], "passed")
            self.assertGreaterEqual(len(allowed["exemptions"]), 2)

    def test_live_handoff_manual_actions_are_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root, open_round5=False)

            summary = evaluate_readiness(root, allow_open_round5=False)
            live_handoff = summary.get("live_handoff")
            self.assertIsInstance(live_handoff, dict)
            self.assertEqual(live_handoff.get("schema_version"), LIVE_HANDOFF_SCHEMA_VERSION)

            manual_actions = live_handoff.get("manual_actions")
            self.assertIsInstance(manual_actions, dict)
            self.assertEqual(
                manual_actions,
                {
                    "lark_aeolus_live_side_effects": "requires_platform_credentials_and_manual_enablement",
                    "agent_platform_upload": "requires_manual_platform_upload",
                    "production_event_writeback": "requires_production_config_and_manual_enablement",
                    "canary": "requires_explicit_single_target_authorization_file",
                    "active_touch_execute": "blocked_by_default_in_mvp",
                },
            )

    def test_stale_doc_and_external_required_sibling_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root, open_round5=False, stale_doc=True, external_required_sibling=True)

            summary = evaluate_readiness(root, allow_open_round5=False)
            self.assertEqual(summary["status"], "failed")
            codes = {item.get("code") for item in summary["issues"]}
            self.assertIn("stale_five_packages", codes)
            self.assertIn("external_required_sibling", codes)


def run_self_tests() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ProductionReadinessSelfTest)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.self_test:
        return run_self_tests()

    project_root = args.project_root.resolve()
    summary_path = resolve_summary_path(project_root, args.summary_out)
    summary = evaluate_readiness(project_root, allow_open_round5=args.allow_open_round5, summary_path=summary_path)
    write_summary(summary, summary_path)

    print(f"summary: {rel_path(summary_path, project_root)}")
    print(f"status: {summary['status']}")
    print(f"issue_count: {summary['issue_count']}")
    print(f"allow_open_round5: {summary['allow_open_round5']}")
    if summary["exemptions"]:
        print(f"exemptions: {len(summary['exemptions'])}")
    for item in summary["issues"][:20]:
        location = item.get("path", "")
        if item.get("line"):
            location = f"{location}:{item['line']}"
        prefix = f"- {location}: " if location else "- "
        print(prefix + item["message"])
    if len(summary["issues"]) > 20:
        print(f"- ... {len(summary['issues']) - 20} more issue(s)")

    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
