#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Base writeback primitives with explicit idempotency logging."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_text() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def masked_token(token: str) -> str:
    if len(token) <= 8:
        return "<masked>"
    return f"{token[:4]}...{token[-4:]}"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@dataclass
class BaseWritebackLogger:
    log_path: Path
    verbose: bool = True

    def log(self, event: str, **payload: Any) -> None:
        record = {
            "ts": utc_now_text(),
            "event": event,
            **payload,
        }
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        if self.verbose:
            print(json.dumps(record, ensure_ascii=False))


class BaseWritebackClient:
    def __init__(self, *, base_token: str, output_dir: Path, logger: BaseWritebackLogger) -> None:
        self.base_token = base_token
        self.output_dir = output_dir
        self.logger = logger

    def run_lark(self, args: list[str], label: str) -> dict[str, Any]:
        stdout_path = self.output_dir / f"{label}.stdout.json"
        stderr_path = self.output_dir / f"{label}.stderr.txt"
        redacted_args = ["<base-token>" if item == self.base_token else item for item in args]
        self.logger.log("lark_cli_start", label=label, argv=redacted_args)
        proc = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_path.write_text(proc.stdout, encoding="utf-8")
        stderr_path.write_text(proc.stderr, encoding="utf-8")
        self.logger.log(
            "lark_cli_done",
            label=label,
            returncode=proc.returncode,
            stdout=str(stdout_path),
            stderr=str(stderr_path),
        )
        if proc.returncode != 0:
            raise RuntimeError(f"{label} failed: exit={proc.returncode}\n{proc.stdout}\n{proc.stderr}")
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"{label} returned non-json output: {proc.stdout}") from exc
        if payload.get("ok") is False:
            raise RuntimeError(f"{label} returned ok=false: {json.dumps(payload, ensure_ascii=False)}")
        return payload

    @staticmethod
    def record_ids(payload: dict[str, Any]) -> list[str]:
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            return []
        ids = data.get("record_id_list")
        if isinstance(ids, list):
            return [str(item) for item in ids]
        record = data.get("record")
        if isinstance(record, dict):
            ids = record.get("record_id_list")
            if isinstance(ids, list):
                return [str(item) for item in ids]
            for key in ("record_id", "id"):
                if record.get(key):
                    return [str(record[key])]
        records = data.get("records")
        if isinstance(records, list):
            result = []
            for record_item in records:
                if isinstance(record_item, dict):
                    record_id = record_item.get("record_id") or record_item.get("id")
                    if record_id:
                        result.append(str(record_id))
            return result
        for key in ("record_id", "id"):
            if data.get(key):
                return [str(data[key])]
        return []

    def query_by_conditions(
        self,
        *,
        table_id: str,
        conditions: list[list[Any]],
        field_ids: list[str],
        label: str,
    ) -> list[str]:
        filter_json = json.dumps({"logic": "and", "conditions": conditions}, ensure_ascii=False)
        args = [
            "lark-cli",
            "base",
            "+record-list",
            "--as",
            "user",
            "--format",
            "json",
            "--base-token",
            self.base_token,
            "--table-id",
            table_id,
            "--filter-json",
            filter_json,
            "--limit",
            "10",
        ]
        for field_id in field_ids:
            args.extend(["--field-id", field_id])
        self.logger.log("idempotency_query_start", table_id=table_id, conditions=conditions, projected_fields=field_ids)
        payload = self.run_lark(args, label)
        ids = self.record_ids(payload)
        self.logger.log("idempotency_query_done", table_id=table_id, match_count=len(ids), record_ids=ids)
        return ids

    def create_record(self, *, table_id: str, fields: dict[str, Any], label: str) -> str:
        payload = self.run_lark(
            [
                "lark-cli",
                "base",
                "+record-upsert",
                "--as",
                "user",
                "--format",
                "json",
                "--base-token",
                self.base_token,
                "--table-id",
                table_id,
                "--json",
                json.dumps(fields, ensure_ascii=False),
            ],
            label,
        )
        ids = self.record_ids(payload)
        if not ids:
            raise RuntimeError(f"{label} created no visible record id: {json.dumps(payload, ensure_ascii=False)}")
        self.logger.log("record_created", table_id=table_id, record_id=ids[0], fields=sorted(fields))
        return ids[0]

    def update_record(self, *, table_id: str, record_id: str, fields: dict[str, Any], label: str) -> str:
        payload = self.run_lark(
            [
                "lark-cli",
                "base",
                "+record-upsert",
                "--as",
                "user",
                "--format",
                "json",
                "--base-token",
                self.base_token,
                "--table-id",
                table_id,
                "--record-id",
                record_id,
                "--json",
                json.dumps(fields, ensure_ascii=False),
            ],
            label,
        )
        ids = self.record_ids(payload) or [record_id]
        self.logger.log("record_updated", table_id=table_id, record_id=ids[0], fields=sorted(fields))
        return ids[0]

    def upsert_event(
        self,
        *,
        table_id: str,
        event_fields: dict[str, Any],
        dedupe_conditions: list[list[Any]],
        label_prefix: str = "event",
    ) -> tuple[str, str]:
        matches = self.query_by_conditions(
            table_id=table_id,
            conditions=dedupe_conditions,
            field_ids=["sop_id", "run_id", "业务对象", "rule_group_id"],
            label=f"{label_prefix}_query",
        )
        if matches:
            self.logger.log("event_upsert_decision", action="update", record_id=matches[0])
            return self.update_record(table_id=table_id, record_id=matches[0], fields=event_fields, label=f"{label_prefix}_update"), "updated"
        self.logger.log("event_upsert_decision", action="create")
        return self.create_record(table_id=table_id, fields=event_fields, label=f"{label_prefix}_create"), "created"

    def upsert_touch_record(
        self,
        *,
        table_id: str,
        idempotency_key: str,
        touch_fields: dict[str, Any],
        label_prefix: str = "touch",
    ) -> tuple[str, str]:
        matches = self.query_by_conditions(
            table_id=table_id,
            conditions=[["idempotency_key", "==", idempotency_key]],
            field_ids=["idempotency_key", "消息ID", "触达状态"],
            label=f"{label_prefix}_query_by_idempotency",
        )
        if matches:
            self.logger.log("touch_upsert_decision", action="update", idempotency_key=idempotency_key, record_id=matches[0])
            return self.update_record(table_id=table_id, record_id=matches[0], fields=touch_fields, label=f"{label_prefix}_update"), "updated"
        self.logger.log("touch_upsert_decision", action="create", idempotency_key=idempotency_key)
        return self.create_record(table_id=table_id, fields=touch_fields, label=f"{label_prefix}_create"), "created"
