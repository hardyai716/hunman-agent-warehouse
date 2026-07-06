#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CardKit 卡片命中数据哈希校验工具。

用于防止卡片生成、私聊预览、正式发送三个环节误用不同命中数据。
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any


_META_KEY = "_meta"
_HASH_KEY = "_data_hash"
_LEVEL_KEY = "level"


def _canonicalize(value: Any) -> Any:
    """递归规范化数据，保证 dict key 顺序稳定。"""
    if isinstance(value, dict):
        return {str(key): _canonicalize(value[key]) for key in sorted(value, key=lambda x: str(x))}
    if isinstance(value, list):
        return [_canonicalize(item) for item in value]
    return value


def compute_hits_hash(hits: list[dict]) -> str:
    """计算命中行数据的顺序无关 SHA256 哈希。

    Args:
        hits: 命中行列表，每个元素必须是 dict。

    Returns:
        64 位十六进制 SHA256 字符串。

    Raises:
        TypeError: hits 不是 list[dict] 时抛出。
    """
    if not isinstance(hits, list):
        raise TypeError("hits must be a list of dict")
    if not all(isinstance(item, dict) for item in hits):
        raise TypeError("each hit must be a dict")

    canonical_hits = [_canonicalize(item) for item in hits]
    canonical_hits.sort(key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    payload = json.dumps(canonical_hits, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def embed_hash_in_card(card_json: dict, hits_hash: str) -> dict:
    """把命中数据哈希写入 card_json['_meta']['_data_hash']。

    不原地修改输入对象，返回写入后的新 card dict。
    """
    if not isinstance(card_json, dict):
        raise TypeError("card_json must be a dict")
    if not isinstance(hits_hash, str) or not hits_hash:
        raise TypeError("hits_hash must be a non-empty string")

    card = copy.deepcopy(card_json)
    meta = card.setdefault(_META_KEY, {})
    if not isinstance(meta, dict):
        raise TypeError("card_json['_meta'] must be a dict when present")
    meta[_HASH_KEY] = hits_hash
    return card


def verify_card_hash(card_json: dict, current_hits: list[dict]) -> bool:
    """校验卡片内嵌哈希与当前命中数据是否一致。

    Returns:
        一致时返回 True。

    Raises:
        ValueError: 卡片缺少哈希或哈希不一致时抛出。
    """
    if not isinstance(card_json, dict):
        raise TypeError("card_json must be a dict")

    meta = card_json.get(_META_KEY)
    if not isinstance(meta, dict) or not meta.get(_HASH_KEY):
        raise ValueError("card missing _meta._data_hash")

    expected_hash = meta[_HASH_KEY]
    current_hash = compute_hits_hash(current_hits)
    if expected_hash != current_hash:
        raise ValueError(f"card data hash mismatch: expected {expected_hash}, got {current_hash}")
    return True


def verify_route_match(card_json: dict, target_level: str) -> bool:
    """校验卡片等级与目标路由等级是否一致。

    card_json["_meta"]["level"] 必须等于 target_level（大小写不敏感）。

    Returns:
        一致时返回 True。

    Raises:
        ValueError: 卡片缺少 _meta.level、目标等级为空或二者不一致时抛出。
    """
    if not isinstance(card_json, dict):
        raise TypeError("card_json must be a dict")
    if not isinstance(target_level, str) or not target_level.strip():
        raise ValueError("target_level must be a non-empty string")

    meta = card_json.get(_META_KEY)
    if not isinstance(meta, dict) or not meta.get(_LEVEL_KEY):
        raise ValueError("card missing _meta.level")

    card_level = str(meta[_LEVEL_KEY]).strip()
    route_level = target_level.strip()
    if card_level.casefold() != route_level.casefold():
        raise ValueError(f"card route level mismatch: card {card_level}, target {route_level}")
    return True


def verify_route_chat_id(card_json: dict, target_level: str, target_chat_id: str, route_chat_id: str) -> bool:
    """校验发送目标 chat_id 与责任路由表中的 chat_id 完全一致。

    正式发群前必须先校验等级，再校验 chat_id；如果责任路由表缺少群聊 ID，
    或调用方传入的目标 chat_id 与路由表不一致，必须停止发送。
    """
    verify_route_match(card_json, target_level)
    if not isinstance(target_chat_id, str) or not target_chat_id.strip():
        raise ValueError("target_chat_id must be a non-empty string")
    if not isinstance(route_chat_id, str) or not route_chat_id.strip():
        raise ValueError("route_chat_id must be a non-empty string from route table")
    if target_chat_id.strip() != route_chat_id.strip():
        raise ValueError(f"route chat_id mismatch: target {target_chat_id.strip()}, route {route_chat_id.strip()}")
    return True
