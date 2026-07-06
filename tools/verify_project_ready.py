#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run final project acceptance checks and audit packaged skill zips."""

from __future__ import annotations

import datetime as dt
import fnmatch
import json
import posixpath
import re
import subprocess
import time
import zipfile
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FINAL_ACCEPTANCE_DIR = PROJECT_ROOT / "dist" / "final_acceptance"
SUMMARY_PATH = FINAL_ACCEPTANCE_DIR / "acceptance_summary.json"
ZIPS_DIR = PROJECT_ROOT / "dist" / "agent_upload" / "zips"
PROJECT_SKILL_NAMES = {
    "review-monitoring-shared",
    "warehouse-skill",
    "owner-routing",
    "monitoring-orchestrator",
    "anomaly-touch",
    "low-efficiency-strategy-analysis",
}

FRONTMATTER_RE = re.compile(r"^---\n(?P<body>.*?)\n---\n", re.S)
NAME_RE = re.compile(r"^name:\s*[\"']?(?P<name>[^\"'\n]+)[\"']?\s*$", re.M)
TEXT_MEMBER_SUFFIXES = {".md", ".json", ".txt", ".yaml", ".yml", ".py"}
FORBIDDEN_MEMBER_NAMES = {".DS_Store", "__pycache__", ".pytest_cache"}
FORBIDDEN_MEMBER_SUFFIXES = {".pyc", ".pyo", ".xlsx", ".xls", ".tmp", ".temp", ".bak", ".swp", ".swo"}
FORBIDDEN_REQUIRED_SIBLINGS = {
    "sqless",
    "sqless-data-analysis",
    "bytedcli",
    "bytedance-aeolus",
    "bytedance_aeolus",
}
OPEN_ID_RE = re.compile(r"(?<![A-Za-z0-9_-])ou_[A-Za-z0-9_-]{12,}(?![A-Za-z0-9_-])")
CHAT_ID_RE = re.compile(r"(?<![A-Za-z0-9_-])oc_[A-Za-z0-9_-]{12,}(?![A-Za-z0-9_-])")
BEARER_TOKEN_RE = re.compile(r"(?i)\bBearer\s+(?P<value>[A-Za-z0-9][A-Za-z0-9._~+/=-]{11,})")
CREDENTIAL_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(?:access[_-]?token|app[_-]?secret|secret[_-]?key)\b\s*[:=]\s*[\"']?(?P<value>[^\"'\s,;}\]]+)"
)
MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^\]\n]+\]\((?P<target>[^)\s]+)(?:\s+\"[^\"]*\")?\)")
LOCAL_PAREN_REF_RE = re.compile(r"\((?P<target>(?:references|scripts|templates|examples)/[^)\s]+)\)")
JSON_LOCAL_REF_RE = re.compile(r"^(?:references/.+\.md|scripts/.+\.py|templates/.+\.json|examples/.+)$")


def timestamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def command_text(argv: list[str]) -> str:
    return " ".join(argv)


def rel_artifact(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def write_text_artifact(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_item(
    name: str,
    status: str,
    command: str,
    duration_seconds: float,
    artifacts: list[Path | str],
    error: str | None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "name": name,
        "status": status,
        "command": command,
        "duration_seconds": round(duration_seconds, 3),
        "artifacts": [rel_artifact(a) if isinstance(a, Path) else a for a in artifacts],
        "error": error,
    }
    if extra:
        item.update(extra)
    return item


def run_command(name: str, argv: list[str], tmp_dir: Path, artifacts: list[Path] | None = None) -> dict[str, Any]:
    stdout_path = tmp_dir / f"{name}.stdout.txt"
    stderr_path = tmp_dir / f"{name}.stderr.txt"
    started = time.monotonic()
    error: str | None = None

    try:
        result = subprocess.run(
            argv,
            cwd=PROJECT_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except Exception as exc:  # pragma: no cover - defensive acceptance harness
        duration = time.monotonic() - started
        write_text_artifact(stdout_path, "")
        write_text_artifact(stderr_path, repr(exc))
        return make_item(
            name=name,
            status="failed",
            command=command_text(argv),
            duration_seconds=duration,
            artifacts=[stdout_path, stderr_path, *(artifacts or [])],
            error=repr(exc),
            extra={"returncode": None},
        )

    duration = time.monotonic() - started
    write_text_artifact(stdout_path, result.stdout)
    write_text_artifact(stderr_path, result.stderr)

    if result.returncode != 0:
        stderr_tail = result.stderr.strip().splitlines()[-10:]
        stdout_tail = result.stdout.strip().splitlines()[-10:]
        tail = "\n".join(stderr_tail or stdout_tail)
        error = f"exit {result.returncode}" + (f": {tail}" if tail else "")

    return make_item(
        name=name,
        status="passed" if result.returncode == 0 else "failed",
        command=command_text(argv),
        duration_seconds=duration,
        artifacts=[stdout_path, stderr_path, *(artifacts or [])],
        error=error,
        extra={"returncode": result.returncode},
    )


def read_text_if_exists(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, IsADirectoryError, UnicodeDecodeError):
        return ""


def collect_artifact_text(paths: list[Path]) -> str:
    chunks: list[str] = []
    text_suffixes = TEXT_MEMBER_SUFFIXES | {".jsonl"}
    for path in paths:
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and child.suffix.lower() in text_suffixes:
                    chunks.append(read_text_if_exists(child))
        elif path.exists() and path.suffix.lower() in text_suffixes:
            chunks.append(read_text_if_exists(path))
    return "\n".join(chunk for chunk in chunks if chunk)


def run_expected_blocked_command(
    name: str,
    argv: list[str],
    tmp_dir: Path,
    artifacts: list[Path] | None = None,
    guard_terms: list[str] | None = None,
    authorization_terms: list[str] | None = None,
) -> dict[str, Any]:
    stdout_path = tmp_dir / f"{name}.stdout.txt"
    stderr_path = tmp_dir / f"{name}.stderr.txt"
    started = time.monotonic()
    error: str | None = None
    returncode: int | None = None

    try:
        result = subprocess.run(
            argv,
            cwd=PROJECT_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        returncode = result.returncode
        stdout = result.stdout
        stderr = result.stderr
    except Exception as exc:  # pragma: no cover - defensive acceptance harness
        stdout = ""
        stderr = repr(exc)
        error = repr(exc)

    duration = time.monotonic() - started
    write_text_artifact(stdout_path, stdout)
    write_text_artifact(stderr_path, stderr)

    artifact_paths = artifacts or []
    evidence_text = "\n".join([stdout, stderr, collect_artifact_text(artifact_paths)]).lower()
    guard_terms = guard_terms or ["live-mode guard", "live_mode_guard"]
    authorization_terms = authorization_terms or ["production authorization", "production_authorization"]
    guard_hits = [term for term in guard_terms if term.lower() in evidence_text]
    authorization_hits = [term for term in authorization_terms if term.lower() in evidence_text]

    failures: list[str] = []
    if returncode is None:
        failures.append("command did not complete")
    elif returncode == 0:
        failures.append("expected non-zero return code because live mode must be blocked")
    if not guard_hits:
        failures.append("missing live-mode guard evidence")
    if not authorization_hits:
        failures.append("missing production authorization evidence")
    if error:
        failures.append(error)

    return make_item(
        name=name,
        status="passed" if not failures else "failed",
        command=command_text(argv),
        duration_seconds=duration,
        artifacts=[stdout_path, stderr_path, *artifact_paths],
        error="; ".join(failures) if failures else None,
        extra={
            "returncode": returncode,
            "expected_blocked": True,
            "guard_evidence_terms_found": guard_hits,
            "authorization_evidence_terms_found": authorization_hits,
        },
    )


def read_json_object(path: Path, label: str, issues: list[str]) -> dict[str, Any] | None:
    if not path.exists():
        issues.append(f"{label} missing: {rel_artifact(path)}")
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        issues.append(f"{label} invalid json: {rel_artifact(path)}: {exc}")
        return None
    if not isinstance(value, dict):
        issues.append(f"{label} is not a JSON object: {rel_artifact(path)}")
        return None
    return value


def audit_orchestrator_shadow_output(output_dir: Path) -> tuple[list[str], dict[str, Any]]:
    issues: list[str] = []
    summary_path = output_dir / "run_summary.json"
    comparison_path = output_dir / "shadow_comparison.json"
    run_audit_path = output_dir / "run_audit.jsonl"

    run_summary = read_json_object(summary_path, "run_summary", issues)
    if run_summary and run_summary.get("run_status") != "completed":
        issues.append(f"run_summary run_status={run_summary.get('run_status')!r}, expected 'completed'")

    publish_result = run_summary.get("publish_result") if isinstance(run_summary, dict) else None
    if not isinstance(publish_result, dict):
        issues.append("run_summary publish_result missing or not object")
    elif publish_result.get("sent") is not False:
        issues.append(f"publish_result.sent={publish_result.get('sent')!r}, expected false")

    comparison = read_json_object(comparison_path, "shadow_comparison", issues)
    if comparison:
        if comparison.get("schema_version") != "shadow_comparison.v1":
            issues.append(f"shadow_comparison schema_version={comparison.get('schema_version')!r}")
        warnings = comparison.get("warnings")
        if warnings != []:
            issues.append(f"shadow_comparison warnings not empty: {warnings!r}")
        diff_summary = comparison.get("diff_summary")
        if not isinstance(diff_summary, dict) or diff_summary.get("status") != "matched":
            status = diff_summary.get("status") if isinstance(diff_summary, dict) else None
            issues.append(f"shadow_comparison diff_summary.status={status!r}, expected 'matched'")

    touch_send_records: list[str] = []
    if not run_audit_path.exists():
        issues.append(f"run_audit missing: {rel_artifact(run_audit_path)}")
    else:
        for line_no, line in enumerate(run_audit_path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                issues.append(f"run_audit invalid json line {line_no}: {exc}")
                continue
            if isinstance(record, dict) and record.get("node_type") == "touch_send":
                touch_send_records.append(f"line {line_no}")
        if touch_send_records:
            issues.append("run_audit contains node_type=touch_send at " + ", ".join(touch_send_records))

    return issues, {
        "status": "passed" if not issues else "failed",
        "output_dir": rel_artifact(output_dir),
        "run_summary": rel_artifact(summary_path),
        "shadow_comparison": rel_artifact(comparison_path),
        "run_audit": rel_artifact(run_audit_path),
        "issues": issues,
    }


def attach_orchestrator_shadow_audit(item: dict[str, Any], tmp_dir: Path) -> dict[str, Any]:
    audit_path = tmp_dir / "orchestrator_shadow_cli_audit.json"
    output_dir = tmp_dir / "orchestrator_shadow_cli"
    issues, payload = audit_orchestrator_shadow_output(output_dir)
    write_text_artifact(audit_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    item["post_audit"] = payload
    item["artifacts"].append(rel_artifact(audit_path))
    if issues:
        item["status"] = "failed"
        audit_error = "; ".join(issues)
        item["error"] = f"{item['error']}; {audit_error}" if item["error"] else audit_error
    return item


def attach_live_mode_guard_audit(item: dict[str, Any], tmp_dir: Path) -> dict[str, Any]:
    audit_path = tmp_dir / "orchestrator_live_mode_guard_audit.json"
    output_dir = tmp_dir / "orchestrator_live_mode_guard"
    run_summary_path = output_dir / "run_summary.json"
    run_audit_path = output_dir / "run_audit.jsonl"
    issues: list[str] = []

    run_summary = read_json_object(run_summary_path, "live_mode_guard run_summary", issues)
    if run_summary:
        if run_summary.get("run_status") != "blocked":
            issues.append(f"run_summary run_status={run_summary.get('run_status')!r}, expected 'blocked'")
        if run_summary.get("stop_reason") != "live_mode_requires_production_authorization":
            issues.append(
                "run_summary stop_reason="
                f"{run_summary.get('stop_reason')!r}, expected 'live_mode_requires_production_authorization'"
            )
        live_mode_status = run_summary.get("live_mode_status")
        if not isinstance(live_mode_status, dict):
            issues.append("run_summary live_mode_status missing or not object")
        else:
            if live_mode_status.get("requested_run_mode") != "canary":
                issues.append(f"live_mode_status requested_run_mode={live_mode_status.get('requested_run_mode')!r}")
            if live_mode_status.get("authorized") is not False:
                issues.append(f"live_mode_status authorized={live_mode_status.get('authorized')!r}, expected false")
            if live_mode_status.get("mvp_supported") is not False:
                issues.append(f"live_mode_status mvp_supported={live_mode_status.get('mvp_supported')!r}, expected false")

    audit_text = read_text_if_exists(run_audit_path)
    if not audit_text:
        issues.append(f"run_audit missing or empty: {rel_artifact(run_audit_path)}")
    else:
        if '"node_type":"live_mode_guard"' not in audit_text:
            issues.append("run_audit missing node_type=live_mode_guard")
        if '"node_status":"blocked"' not in audit_text:
            issues.append("run_audit missing node_status=blocked")

    payload = {
        "status": "passed" if not issues else "failed",
        "output_dir": rel_artifact(output_dir),
        "run_summary": rel_artifact(run_summary_path),
        "run_audit": rel_artifact(run_audit_path),
        "issues": issues,
    }
    write_text_artifact(audit_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    item["post_audit"] = payload
    item["artifacts"].append(rel_artifact(audit_path))
    if issues:
        item["status"] = "failed"
        audit_error = "; ".join(issues)
        item["error"] = f"{item['error']}; {audit_error}" if item["error"] else audit_error
    return item


def attach_readiness_summary_audit(item: dict[str, Any], readiness_summary_path: Path, tmp_dir: Path) -> dict[str, Any]:
    audit_path = tmp_dir / "production_readiness_preflight_audit.json"
    issues: list[str] = []
    readiness = read_json_object(readiness_summary_path, "readiness_summary", issues)

    payload: dict[str, Any] = {
        "status": "passed",
        "readiness_summary": rel_artifact(readiness_summary_path),
        "issues": issues,
    }
    if readiness:
        payload.update(
            {
                "readiness_status": readiness.get("status"),
                "allow_open_round5": readiness.get("allow_open_round5"),
                "issue_count": readiness.get("issue_count"),
                "checks_count": len(readiness.get("checks", [])) if isinstance(readiness.get("checks"), list) else None,
                "exemptions_count": len(readiness.get("exemptions", []))
                if isinstance(readiness.get("exemptions"), list)
                else None,
            }
        )
        if readiness.get("status") != "passed":
            issues.append(f"readiness status={readiness.get('status')!r}, expected 'passed'")
        if readiness.get("allow_open_round5") is not True:
            issues.append(f"readiness allow_open_round5={readiness.get('allow_open_round5')!r}, expected true")
        if readiness.get("issue_count") != 0:
            issues.append(f"readiness issue_count={readiness.get('issue_count')!r}, expected 0")

    payload["status"] = "passed" if not issues else "failed"
    payload["issues"] = issues
    write_text_artifact(audit_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    item["post_audit"] = payload
    item["artifacts"].append(rel_artifact(audit_path))
    if issues:
        item["status"] = "failed"
        audit_error = "; ".join(issues)
        item["error"] = f"{item['error']}; {audit_error}" if item["error"] else audit_error
    return item


def parse_frontmatter_name(skill_md: bytes, zip_path: Path) -> str:
    try:
        text = skill_md.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{zip_path.name}: SKILL.md is not valid UTF-8") from exc

    match = FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError(f"{zip_path.name}: SKILL.md missing YAML frontmatter")
    name_match = NAME_RE.search(match.group("body"))
    if not name_match:
        raise ValueError(f"{zip_path.name}: SKILL.md frontmatter missing name")
    return name_match.group("name").strip()


def text_member_suffix(name: str) -> str:
    return Path(name).suffix.lower()


def is_forbidden_zip_member(name: str) -> str | None:
    normalized = name.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part]

    if normalized.startswith("通用能力/") or normalized.startswith("效率模块/"):
        return "path starts with source layout prefix"
    for part in parts:
        if part in FORBIDDEN_MEMBER_NAMES:
            return f"contains {part}"
    if text_member_suffix(normalized) in FORBIDDEN_MEMBER_SUFFIXES:
        return f"contains {text_member_suffix(normalized)}"
    if normalized.endswith(".py") and parts:
        if fnmatch.fnmatchcase(parts[-1], "test_*.py"):
            return "contains test_*.py"
        if any(part.startswith("test_") for part in parts):
            return "contains Python file under test_* path segment"
    return None


def is_placeholder_secret_value(value: str) -> bool:
    value = value.strip().strip("\"'`")
    lowered = value.lower()
    if not value:
        return True
    if value.startswith("<") and value.endswith(">"):
        return True
    if value.startswith("${") or value.startswith("$") or value.startswith("{{"):
        return True
    if "getenv" in lowered or "placeholder" in lowered or "redacted" in lowered:
        return True
    if lowered in {"null", "none", "true", "false", "xxx", "xxxx", "token", "secret", "sample", "mock", "dummy"}:
        return True
    if lowered.startswith(("your_", "example_", "sample_", "mock_", "dummy_")):
        return True
    return False


def line_number_for_index(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def scan_text_for_sensitive_values(member: str, text: str) -> list[str]:
    issues: list[str] = []
    for pattern_name, pattern in (
        ("open_id", OPEN_ID_RE),
        ("chat_id", CHAT_ID_RE),
    ):
        for match in pattern.finditer(text):
            issues.append(f"{member}: line {line_number_for_index(text, match.start())}: real-looking {pattern_name}")

    for match in BEARER_TOKEN_RE.finditer(text):
        value = match.group("value")
        if not is_placeholder_secret_value(value):
            issues.append(f"{member}: line {line_number_for_index(text, match.start())}: real-looking Bearer token")

    for match in CREDENTIAL_ASSIGNMENT_RE.finditer(text):
        value = match.group("value").rstrip(".")
        if not is_placeholder_secret_value(value):
            key = match.group(0).split(match.group("value"), 1)[0].strip()
            issues.append(f"{member}: line {line_number_for_index(text, match.start())}: real-looking credential assignment {key}")
    return issues


def walk_json(value: Any, path: str = "$") -> list[tuple[str, Any]]:
    items = [(path, value)]
    if isinstance(value, dict):
        for key, child in value.items():
            items.extend(walk_json(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            items.extend(walk_json(child, f"{path}[{index}]"))
    return items


def audit_required_siblings(member: str, value: Any) -> list[str]:
    issues: list[str] = []
    for json_path, node in walk_json(value):
        if not json_path.endswith(".required_siblings"):
            continue
        if not isinstance(node, list):
            continue
        for sibling in node:
            if not isinstance(sibling, str):
                continue
            normalized = sibling.strip()
            if normalized.startswith("lark-") or normalized in FORBIDDEN_REQUIRED_SIBLINGS:
                issues.append(f"{member}: {json_path} contains external dependency {normalized!r}")
    return issues


def strip_ref_suffix(target: str) -> str:
    path = target.strip()
    if path.startswith("<") and path.endswith(">"):
        path = path[1:-1].strip()
    path = path.split("#", 1)[0].split("?", 1)[0]
    return path.replace("\\", "/")


def should_skip_local_ref_target(target: str, current_skill: str) -> bool:
    if not target:
        return True
    lowered = target.lower()
    if target.startswith("#") or target.startswith("/"):
        return True
    if lowered.startswith(("http://", "https://", "mailto:")):
        return True
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target):
        return True
    if any(token in target for token in ("*", "<", ">", "{", "}")):
        return True

    parts = [part for part in target.split("/") if part and part != "."]
    non_parent = [part for part in parts if part != ".."]
    if target.startswith("../") and non_parent:
        first = non_parent[0]
        if first != current_skill and (first in PROJECT_SKILL_NAMES or first.startswith("lark-")):
            return True
    return False


def resolve_zip_ref(source_member: str, target: str, current_skill: str) -> str | None:
    path = strip_ref_suffix(target)
    if should_skip_local_ref_target(path, current_skill):
        return None
    base_dir = posixpath.dirname(source_member)
    normalized = posixpath.normpath(posixpath.join(base_dir, path))
    if normalized == ".":
        return None
    return normalized.lstrip("./")


def zip_member_exists(members: set[str], ref: str) -> bool:
    normalized = ref.rstrip("/")
    return normalized in members or any(member.startswith(normalized + "/") for member in members)


def markdown_local_refs(text: str) -> set[str]:
    refs = {match.group("target") for match in MARKDOWN_LINK_RE.finditer(text)}
    refs.update(match.group("target") for match in LOCAL_PAREN_REF_RE.finditer(text))
    return refs


def json_string_refs(value: Any) -> set[str]:
    refs: set[str] = set()
    for _, node in walk_json(value):
        if isinstance(node, str) and JSON_LOCAL_REF_RE.match(node.strip()):
            refs.add(node.strip())
    return refs


def audit_local_references(member: str, refs: set[str], members: set[str], current_skill: str) -> list[str]:
    issues: list[str] = []
    for target in sorted(refs):
        resolved = resolve_zip_ref(member, target, current_skill)
        if not resolved:
            continue
        if resolved.startswith("../") or not zip_member_exists(members, resolved):
            issues.append(f"{member}: local reference missing from zip: {target!r} -> {resolved!r}")
    return issues


def audit_zip(zip_path: Path) -> dict[str, Any]:
    issues: list[str] = []
    sensitive_issue_count = 0
    reference_issue_count = 0
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        member_set = set(names)
        if "SKILL.md" not in names:
            issues.append("root SKILL.md missing")
        else:
            actual_name = parse_frontmatter_name(zf.read("SKILL.md"), zip_path)
            expected_name = zip_path.stem
            if actual_name != expected_name:
                issues.append(f"SKILL.md name={actual_name!r}, expected {expected_name!r}")

        for member in names:
            issue = is_forbidden_zip_member(member)
            if issue:
                issues.append(f"{member}: {issue}")
            if member.endswith("/"):
                continue
            if text_member_suffix(member) not in TEXT_MEMBER_SUFFIXES:
                continue
            try:
                text = zf.read(member).decode("utf-8")
            except UnicodeDecodeError as exc:
                issues.append(f"{member}: text file is not valid UTF-8: {exc}")
                continue

            sensitive_issues = scan_text_for_sensitive_values(member, text)
            sensitive_issue_count += len(sensitive_issues)
            issues.extend(sensitive_issues)

            if text_member_suffix(member) == ".md":
                ref_issues = audit_local_references(member, markdown_local_refs(text), member_set, zip_path.stem)
                reference_issue_count += len(ref_issues)
                issues.extend(ref_issues)
            elif text_member_suffix(member) == ".json":
                try:
                    json_value = json.loads(text)
                except json.JSONDecodeError as exc:
                    issues.append(f"{member}: invalid JSON: {exc}")
                    continue
                sibling_issues = audit_required_siblings(member, json_value)
                issues.extend(sibling_issues)
                ref_issues = audit_local_references(member, json_string_refs(json_value), member_set, zip_path.stem)
                reference_issue_count += len(ref_issues)
                issues.extend(ref_issues)

    return {
        "zip": rel_artifact(zip_path),
        "status": "passed" if not issues else "failed",
        "issues": issues,
        "sensitive_issue_count": sensitive_issue_count,
        "reference_issue_count": reference_issue_count,
    }


def audit_zips(tmp_dir: Path) -> dict[str, Any]:
    started = time.monotonic()
    audit_path = tmp_dir / "agent_upload_zip_audit.json"
    details: list[dict[str, Any]] = []
    errors: list[str] = []

    try:
        zip_paths = sorted(ZIPS_DIR.glob("*.zip"))
        if len(zip_paths) != 6:
            errors.append(f"expected exactly 6 zip files, found {len(zip_paths)}")

        for zip_path in zip_paths:
            try:
                detail = audit_zip(zip_path)
            except Exception as exc:  # pragma: no cover - corrupt zip or invalid SKILL.md
                detail = {
                    "zip": rel_artifact(zip_path),
                    "status": "failed",
                    "issues": [repr(exc)],
                }
            details.append(detail)
            errors.extend(f"{detail['zip']}: {issue}" for issue in detail["issues"])
    except Exception as exc:  # pragma: no cover - defensive acceptance harness
        errors.append(repr(exc))

    write_text_artifact(
        audit_path,
        json.dumps({"zips_dir": rel_artifact(ZIPS_DIR), "zips": details}, ensure_ascii=False, indent=2) + "\n",
    )
    duration = time.monotonic() - started

    return make_item(
        name="audit_agent_upload_zips",
        status="passed" if not errors else "failed",
        command="audit dist/agent_upload/zips/*.zip",
        duration_seconds=duration,
        artifacts=[audit_path, *sorted(ZIPS_DIR.glob("*.zip"))],
        error="; ".join(errors) if errors else None,
        extra={"zips": details},
    )


def acceptance_commands(tmp_dir: Path) -> list[tuple[str, list[str], list[Path]]]:
    warehouse_eval_out = tmp_dir / "warehouse_eval_runs.mock.json"
    smoke_out_dir = tmp_dir / "low_efficiency_sop_smoke"
    orchestrator_shadow_out_dir = tmp_dir / "orchestrator_shadow_cli"
    return [
        (
            "test_sql_templates",
            ["python3", "效率模块/low-efficiency-strategy-analysis/scripts/test_sql_templates.py"],
            [],
        ),
        (
            "test_card_validator",
            ["python3", "通用能力/review-monitoring-shared/scripts/test_card_validator.py"],
            [],
        ),
        (
            "test_config_linter",
            ["python3", "通用能力/review-monitoring-shared/scripts/test_config_linter.py"],
            [],
        ),
        (
            "test_route_owner",
            ["python3", "通用能力/owner-routing/scripts/test_route_owner.py"],
            [],
        ),
        (
            "test_report_publisher",
            ["python3", "通用能力/anomaly-touch/scripts/test_report_publisher.py"],
            [],
        ),
        (
            "test_run_orchestrator",
            ["python3", "通用能力/monitoring-orchestrator/scripts/test_run_orchestrator.py"],
            [],
        ),
        (
            "simulate_offline_eval",
            [
                "python3",
                "通用能力/warehouse-skill/scripts/simulate_offline_eval.py",
                "--cases",
                "通用能力/warehouse-skill/examples/warehouse_eval_cases.sample.json",
                "--out",
                str(warehouse_eval_out),
            ],
            [warehouse_eval_out],
        ),
        (
            "smoke_low_efficiency_sop",
            [
                "python3",
                "通用能力/monitoring-orchestrator/scripts/smoke_low_efficiency_sop.py",
                "--output-dir",
                str(smoke_out_dir),
            ],
            [smoke_out_dir],
        ),
        (
            "orchestrator_shadow_cli",
            [
                "python3",
                "通用能力/monitoring-orchestrator/scripts/run_orchestrator.py",
                "--config",
                "通用能力/review-monitoring-shared/examples/low_efficiency_sop_config.sample.json",
                "--sop-id",
                "low_efficiency_labeling",
                "--run-mode",
                "shadow",
                "--process-run-dir",
                "通用能力/monitoring-orchestrator/examples/low_efficiency_run",
                "--baseline-run-dir",
                "通用能力/monitoring-orchestrator/examples/low_efficiency_run",
                "--output-dir",
                str(orchestrator_shadow_out_dir),
                "--run-id",
                "FINAL-ACCEPTANCE-SHADOW",
                "--report-type",
                "low_efficiency_grading",
                "--route-preview",
                "--dry-run",
            ],
            [
                orchestrator_shadow_out_dir,
                orchestrator_shadow_out_dir / "run_summary.json",
                orchestrator_shadow_out_dir / "shadow_comparison.json",
                orchestrator_shadow_out_dir / "run_audit.jsonl",
            ],
        ),
        (
            "package_agent_skills",
            ["python3", "tools/package_agent_skills.py"],
            [
                PROJECT_ROOT / "dist" / "agent_upload" / "build_summary.json",
                PROJECT_ROOT / "dist" / "agent_upload" / "human_review_monitoring_skills.zip",
                ZIPS_DIR,
            ],
        ),
    ]


def live_mode_guard_item(tmp_dir: Path) -> dict[str, Any]:
    output_dir = tmp_dir / "orchestrator_live_mode_guard"
    item = run_expected_blocked_command(
        "orchestrator_live_mode_guard",
        [
            "python3",
            "通用能力/monitoring-orchestrator/scripts/run_orchestrator.py",
            "--config",
            "通用能力/review-monitoring-shared/examples/low_efficiency_sop_config.sample.json",
            "--sop-id",
            "low_efficiency_labeling",
            "--run-mode",
            "canary",
            "--process-run-dir",
            "通用能力/monitoring-orchestrator/examples/low_efficiency_run",
            "--output-dir",
            str(output_dir),
            "--run-id",
            "FINAL-ACCEPTANCE-LIVE-GUARD",
            "--report-type",
            "low_efficiency_grading",
            "--dry-run",
        ],
        tmp_dir,
        [
            output_dir,
            output_dir / "run_summary.json",
            output_dir / "run_audit.jsonl",
        ],
        guard_terms=["live-mode guard", "live_mode_guard", "Live side-effect run mode"],
        authorization_terms=["production authorization", "production_authorization", "manual enable switch"],
    )
    return attach_live_mode_guard_audit(item, tmp_dir)


def production_readiness_preflight_item(tmp_dir: Path) -> dict[str, Any]:
    readiness_summary_path = tmp_dir / "readiness_summary.json"
    item = run_command(
        "production_readiness_preflight",
        [
            "python3",
            "tools/verify_production_readiness.py",
            "--allow-open-round5",
            "--summary-out",
            str(readiness_summary_path),
        ],
        tmp_dir,
        [readiness_summary_path],
    )
    return attach_readiness_summary_audit(item, readiness_summary_path, tmp_dir)


def write_acceptance_summary(items: list[dict[str, Any]], tmp_dir: Path) -> str:
    overall_status = "passed" if all(item["status"] == "passed" for item in items) else "failed"
    summary = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "project_root": str(PROJECT_ROOT),
        "tmp_dir": rel_artifact(tmp_dir),
        "status": overall_status,
        "items": items,
        "checks": items,
    }
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return overall_status


def main() -> int:
    FINAL_ACCEPTANCE_DIR.mkdir(parents=True, exist_ok=True)
    tmp_dir = FINAL_ACCEPTANCE_DIR / "tmp" / timestamp()
    tmp_dir.mkdir(parents=True, exist_ok=True)

    items: list[dict[str, Any]] = []
    for name, argv, artifacts in acceptance_commands(tmp_dir):
        item = run_command(name, argv, tmp_dir, artifacts)
        if name == "orchestrator_shadow_cli":
            item = attach_orchestrator_shadow_audit(item, tmp_dir)
        items.append(item)

    items.append(audit_zips(tmp_dir))
    items.append(live_mode_guard_item(tmp_dir))

    # Production readiness reads the final acceptance summary. Write an interim
    # summary for the checks completed so far, add readiness once, then rerun it
    # after the 13-item summary exists so its own artifact records the final
    # acceptance check count instead of the pre-readiness count.
    write_acceptance_summary(items, tmp_dir)
    items.append(production_readiness_preflight_item(tmp_dir))
    write_acceptance_summary(items, tmp_dir)
    items[-1] = production_readiness_preflight_item(tmp_dir)
    overall_status = write_acceptance_summary(items, tmp_dir)

    print(f"summary: {rel_artifact(SUMMARY_PATH)}")
    print(f"tmp_dir: {rel_artifact(tmp_dir)}")
    print(f"status: {overall_status}")
    for item in items:
        print(f"- {item['name']}: {item['status']} ({item['duration_seconds']}s)")
        if item["error"]:
            print(f"  error: {item['error']}")

    return 0 if overall_status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
