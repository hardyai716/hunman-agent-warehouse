#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Object-level owner routing MVP.

This script consumes SOP-first configuration and hit rows, then produces a
route_result for each hit. MVP source support is intentionally conservative:
inline mappings are supported for local/shadow validation, while external
sources are represented but not queried by this script.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_hits(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [dict(item) for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict) and isinstance(payload.get("hits"), list):
            return [dict(item) for item in payload["hits"] if isinstance(item, dict)]
        raise ValueError("JSON hits file must be a list or an object with hits[]")
    with path.open(encoding="utf-8-sig", newline="") as file:
        return [dict(row) for row in csv.DictReader(file)]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def find_sop(config: dict[str, Any], sop_id: str) -> dict[str, Any]:
    for sop in config.get("sops", []):
        if isinstance(sop, dict) and sop.get("sop_id") == sop_id:
            return sop
    raise KeyError(f"sop_id not found: {sop_id}")


def index_owner_sources(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(source["owner_source_id"]): source
        for source in config.get("owner_source_registry", [])
        if isinstance(source, dict) and source.get("owner_source_id")
    }


def normalize_person(value: Any, role: str) -> list[dict[str, str]]:
    if value in (None, "", []):
        return []
    if isinstance(value, dict):
        item = {"role": role, "id": str(value.get("id", "")), "name": str(value.get("name", ""))}
        return [item]
    if isinstance(value, list):
        result: list[dict[str, str]] = []
        for person in value:
            if isinstance(person, dict):
                result.append({"role": role, "id": str(person.get("id", "")), "name": str(person.get("name", ""))})
            else:
                result.append({"role": role, "id": str(person), "name": str(person)})
        return result
    return [{"role": role, "id": str(value), "name": str(value)}]


def find_level_config(sop: dict[str, Any], hit: dict[str, Any]) -> dict[str, Any]:
    raw = hit.get("sop_level_id") or hit.get("_sop_level_id") or hit.get("level") or hit.get("_level")
    for level in sop.get("levels", []):
        if not isinstance(level, dict):
            continue
        if raw in (level.get("sop_level_id"), level.get("level_label")):
            return level
    return {
        "sop_level_id": str(raw or ""),
        "level_label": str(raw or ""),
        "normalized_severity": "",
        "sla_minutes": None,
    }


def choose_route_policy(sop: dict[str, Any], hit: dict[str, Any]) -> dict[str, Any] | None:
    for policy in sop.get("route_policies", []):
        if not isinstance(policy, dict) or not policy.get("enabled", True):
            continue
        fields = policy.get("route_key_fields", [])
        if all(field in hit and hit.get(field) not in (None, "") for field in fields):
            return policy
    return None


def build_source_index(source: dict[str, Any]) -> dict[str, dict[str, Any]]:
    mappings = [item for item in source.get("mappings", []) if isinstance(item, dict) and item.get("enabled", True)]
    mappings.sort(key=lambda item: int(item.get("priority", 9999)))
    result: dict[str, dict[str, Any]] = {}
    for item in mappings:
        key = str(item.get("route_key", ""))
        if key and key not in result:
            result[key] = item
        for alias in item.get("route_key_aliases", []) if isinstance(item.get("route_key_aliases"), list) else []:
            alias_key = str(alias)
            if alias_key and alias_key not in result:
                result[alias_key] = item
    return result


def route_hit(
    *,
    config: dict[str, Any],
    sop: dict[str, Any],
    hit: dict[str, Any],
    hit_index: int,
    run_id: str | None,
    owner_sources: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    policy = choose_route_policy(sop, hit)
    level_config = find_level_config(sop, hit)
    base = {
        "schema_version": "1.0",
        "sop_id": sop.get("sop_id"),
        "run_id": run_id,
        "event_id": hit.get("event_id"),
        "hit_id": hit.get("hit_id") or f"HIT-{hit_index:04d}",
        "metric_id": hit.get("metric_id"),
        "level": {
            "sop_level_id": level_config.get("sop_level_id"),
            "level_label": level_config.get("level_label"),
            "normalized_severity": level_config.get("normalized_severity"),
            "sla_minutes": level_config.get("sla_minutes"),
        },
    }
    if not policy:
        return {
            **base,
            "business_object": {"route_grain": None, "route_key": None, "display_name": ""},
            "owner_source": None,
            "owners": [],
            "collaborators": [],
            "escalation": [],
            "delivery_policy": {"primary_channel": None, "chat_strategy": "manual_fallback", "chat_id": None, "mention_targets": [], "fallback_channel": "manual_review"},
            "route_confidence": "low",
            "missing_object_owner": True,
            "missing_reason": "no_route_policy_matched",
        }

    route_key_field = policy["route_key_fields"][0]
    route_key = str(hit.get(route_key_field, ""))
    owner_source = owner_sources.get(str(policy.get("owner_source_id")))
    source_record: dict[str, Any] | None = None
    if owner_source and owner_source.get("source_type") == "inline_mapping":
        source_record = build_source_index(owner_source).get(route_key)

    if not source_record:
        return {
            **base,
            "business_object": {"route_grain": policy.get("route_grain"), "route_key": route_key, "display_name": route_key},
            "owner_source": policy.get("owner_source_id"),
            "owners": [],
            "collaborators": [],
            "escalation": [],
            "delivery_policy": {"primary_channel": None, "chat_strategy": "manual_fallback", "chat_id": None, "mention_targets": [], "fallback_channel": "manual_review"},
            "route_confidence": "low",
            "missing_object_owner": True,
            "missing_reason": "owner_mapping_not_found",
        }

    owners = normalize_person(source_record.get("owner_user"), source_record.get("owner_role", "业务POC"))
    collaborators = normalize_person(source_record.get("collaborators"), "协作方")
    escalation = normalize_person(source_record.get("escalation_users"), "升级人")
    mention_targets = [person["id"] for person in [*owners, *escalation] if person.get("id")]
    chat_id = source_record.get("default_chat_id")
    return {
        **base,
        "business_object": {
            "route_grain": policy.get("route_grain"),
            "route_key": route_key,
            "display_name": source_record.get("route_key_alias") or route_key,
        },
        "owner_source": policy.get("owner_source_id"),
        "owners": owners,
        "collaborators": collaborators,
        "escalation": escalation,
        "delivery_policy": {
            "primary_channel": "group" if chat_id else "dm",
            "chat_strategy": "reuse_object_group" if chat_id else "dm_owner",
            "chat_id": chat_id,
            "chat_name": source_record.get("default_chat_name"),
            "mention_targets": mention_targets,
            "fallback_channel": "dm",
        },
        "route_confidence": "high",
        "missing_object_owner": False,
    }


def route_hits(config: dict[str, Any], sop_id: str, hits: list[dict[str, Any]], *, run_id: str | None = None) -> dict[str, Any]:
    sop = find_sop(config, sop_id)
    owner_sources = index_owner_sources(config)
    results = [
        route_hit(config=config, sop=sop, hit=hit, hit_index=index, run_id=run_id, owner_sources=owner_sources)
        for index, hit in enumerate(hits, 1)
    ]
    return {
        "schema_version": "route_results.v1",
        "sop_id": sop_id,
        "run_id": run_id,
        "summary": {
            "hit_count": len(hits),
            "routed_count": sum(1 for item in results if not item.get("missing_object_owner")),
            "missing_owner_count": sum(1 for item in results if item.get("missing_object_owner")),
        },
        "route_results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve object-level owners for SOP hit rows.")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--sop-id", required=True)
    parser.add_argument("--hits", required=True, type=Path, help="CSV or JSON hit rows.")
    parser.add_argument("--run-id")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = route_hits(load_json(args.config), args.sop_id, read_hits(args.hits), run_id=args.run_id)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        write_json(args.output, result)
    print(text, end="")
    return 0 if result["summary"]["missing_owner_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
