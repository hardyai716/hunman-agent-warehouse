#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build uploadable agent-platform skill packages.

Source directories keep the human-friendly project layout:

  通用能力/<skill-name>/
  效率模块/<skill-name>/

This script generates the platform layout:

  dist/agent_upload/.trae/skills/<skill-name>/SKILL.md

It also creates:

  dist/agent_upload/human_review_monitoring_skills.zip
  dist/agent_upload/zips/<skill-name>.zip

The bulk bundle is for importers that understand .trae/skills. Individual zips
are for platforms that validate SKILL.md at the zip root.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import shutil
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


FRONTMATTER_RE = re.compile(r"^---\n(?P<body>.*?)\n---\n", re.S)
NAME_RE = re.compile(r"^name:\s*[\"']?(?P<name>[^\"'\n]+)[\"']?\s*$", re.M)
DESCRIPTION_RE = re.compile(r"^description:\s*(?P<description>.+)$", re.M)
ALLOWED_OUTPUT_DIR = Path("dist/agent_upload")


@dataclass(frozen=True)
class SkillSpec:
    name: str
    source: Path
    exclude_paths: tuple[str, ...] = ()


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_frontmatter(skill_md: Path) -> tuple[str, str]:
    text = skill_md.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError(f"{skill_md} 缺少 YAML frontmatter")
    frontmatter = match.group("body")
    name_match = NAME_RE.search(frontmatter)
    desc_match = DESCRIPTION_RE.search(frontmatter)
    if not name_match:
        raise ValueError(f"{skill_md} frontmatter 缺少 name")
    if not desc_match:
        raise ValueError(f"{skill_md} frontmatter 缺少 description")
    return name_match.group("name").strip(), desc_match.group("description").strip()


def normalize_exclude_path(pattern: str) -> str:
    return pattern.strip().replace("\\", "/").lstrip("./")


def rel_path_matches(rel: Path, pattern: str) -> bool:
    rel_text = rel.as_posix()
    pattern = normalize_exclude_path(pattern)
    if not pattern:
        return False
    if rel_text == pattern:
        return True
    if pattern.endswith("/"):
        return rel_text.startswith(pattern)
    if pattern.endswith("/**") and rel_text == pattern[:-3].rstrip("/"):
        return True
    return fnmatch.fnmatchcase(rel_text, pattern)


def should_ignore_path(rel: Path, exclude_paths: Iterable[str]) -> bool:
    return any(rel_path_matches(rel, pattern) for pattern in exclude_paths)


def should_ignore(path: Path, exclude_names: set[str], exclude_suffixes: set[str]) -> bool:
    return path.name in exclude_names or path.suffix in exclude_suffixes


def copy_skill_tree(
    src: Path,
    dst: Path,
    exclude_names: set[str],
    exclude_suffixes: set[str],
    exclude_paths: Iterable[str],
) -> None:
    for item in src.rglob("*"):
        rel = item.relative_to(src)
        if any(part in exclude_names for part in rel.parts):
            continue
        if should_ignore_path(rel, exclude_paths):
            continue
        if should_ignore(item, exclude_names, exclude_suffixes):
            continue
        target = dst / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


def rewrite_text_files(root: Path, rewrites: list[dict[str, str]]) -> None:
    text_suffixes = {".md", ".json", ".txt", ".yaml", ".yml"}
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in text_suffixes:
            continue
        text = path.read_text(encoding="utf-8")
        new_text = text
        for rule in rewrites:
            new_text = new_text.replace(rule["from"], rule["to"])
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")


def iter_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if path.is_file():
            yield path


def zip_dir(src_dir: Path, zip_path: Path, arc_root: Path | None = None) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    base = arc_root or src_dir.parent
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in iter_files(src_dir):
            zf.write(path, path.relative_to(base))


def validate_packaged_skill(skill_dir: Path, expected_name: str) -> None:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        raise ValueError(f"{skill_dir} 缺少 SKILL.md")
    actual_name, description = parse_frontmatter(skill_md)
    if actual_name != expected_name:
        raise ValueError(f"{skill_md} name={actual_name!r} 与目录/manifest={expected_name!r} 不一致")
    if len(description) > 260:
        print(f"warn: {expected_name} description 较长（{len(description)} chars）", file=sys.stderr)


def validate_output_dir(project_root: Path, out_dir: Path) -> None:
    project_root = project_root.resolve()
    out_dir = out_dir.resolve()

    try:
        rel = out_dir.relative_to(project_root)
    except ValueError as exc:
        raise ValueError(f"output_dir 必须位于项目目录内：{out_dir}") from exc

    if rel != ALLOWED_OUTPUT_DIR:
        raise ValueError(f"拒绝清理非标准输出目录：{rel}；只允许 {ALLOWED_OUTPUT_DIR}")


def build(manifest_path: Path, clean: bool = True) -> Path:
    project_root = manifest_path.resolve().parents[1]
    manifest = load_manifest(manifest_path)

    out_dir = project_root / manifest["output_dir"]
    platform_skills_dir = out_dir / ".trae" / "skills"
    bundle_name = manifest.get("bundle_name", "agent_skills")

    validate_output_dir(project_root, out_dir)

    if clean and out_dir.exists():
        shutil.rmtree(out_dir)

    platform_skills_dir.mkdir(parents=True, exist_ok=True)

    exclude_names = set(manifest.get("exclude_names", []))
    exclude_suffixes = set(manifest.get("exclude_suffixes", []))
    global_exclude_paths = tuple(manifest.get("exclude_paths", []))
    rewrites = manifest.get("path_rewrites", [])

    specs = [
        SkillSpec(
            name=item["name"],
            source=project_root / item["source"],
            exclude_paths=tuple(item.get("exclude_paths", [])),
        )
        for item in manifest["skills"]
    ]

    for spec in specs:
        source_skill_md = spec.source / "SKILL.md"
        if not source_skill_md.exists():
            raise ValueError(f"{spec.source} 缺少 SKILL.md")
        actual_name, _ = parse_frontmatter(source_skill_md)
        if actual_name != spec.name:
            raise ValueError(f"{source_skill_md} name={actual_name!r} 与 manifest={spec.name!r} 不一致")

        dst = platform_skills_dir / spec.name
        copy_skill_tree(
            spec.source,
            dst,
            exclude_names,
            exclude_suffixes,
            (*global_exclude_paths, *spec.exclude_paths),
        )
        rewrite_text_files(dst, rewrites)
        validate_packaged_skill(dst, spec.name)

    # Bulk bundle: root contains .trae/skills/...
    zip_dir(out_dir / ".trae", out_dir / f"{bundle_name}.zip", arc_root=out_dir)

    # Individual skill zips: root contains SKILL.md
    zips_dir = out_dir / "zips"
    for spec in specs:
        skill_dir = platform_skills_dir / spec.name
        zip_dir(skill_dir, zips_dir / f"{spec.name}.zip", arc_root=skill_dir)

    summary = {
        "output_dir": str(out_dir.relative_to(project_root)),
        "bulk_bundle": str((out_dir / f"{bundle_name}.zip").relative_to(project_root)),
        "skills_dir": str(platform_skills_dir.relative_to(project_root)),
        "single_skill_zips_dir": str(zips_dir.relative_to(project_root)),
        "skills": [spec.name for spec in specs],
    }
    (out_dir / "build_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return out_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build uploadable agent skill packages.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).with_name("agent_skill_manifest.json"),
        help="Path to agent_skill_manifest.json",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Do not delete output_dir before building.",
    )
    args = parser.parse_args(argv)

    out_dir = build(args.manifest, clean=not args.no_clean)
    print(f"built: {out_dir}")
    print(f"skills: {out_dir / '.trae' / 'skills'}")
    print(f"bundle: {next(out_dir.glob('*.zip'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
