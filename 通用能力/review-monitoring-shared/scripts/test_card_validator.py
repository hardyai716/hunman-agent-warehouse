#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest

from card_validator import (
    compute_hits_hash,
    embed_hash_in_card,
    verify_card_hash,
    verify_route_chat_id,
    verify_route_match,
)


class TestVerifyRouteMatch(unittest.TestCase):
    def test_level_match_returns_true(self):
        card = {"_meta": {"level": "P1"}}
        self.assertTrue(verify_route_match(card, "p1"))

    def test_level_mismatch_raises_value_error(self):
        card = {"_meta": {"level": "P1"}}
        with self.assertRaises(ValueError):
            verify_route_match(card, "P0")

    def test_missing_meta_level_raises_value_error(self):
        with self.assertRaises(ValueError):
            verify_route_match({"_meta": {}}, "P1")
        with self.assertRaises(ValueError):
            verify_route_match({}, "P1")

    def test_route_chat_id_match_returns_true(self):
        card = {"_meta": {"level": "notice"}}
        self.assertTrue(verify_route_chat_id(card, "notice", "oc_notice", "oc_notice"))

    def test_route_chat_id_mismatch_raises_value_error(self):
        card = {"_meta": {"level": "notice"}}
        with self.assertRaises(ValueError):
            verify_route_chat_id(card, "notice", "oc_p0", "oc_notice")

    def test_empty_route_chat_id_raises_value_error(self):
        card = {"_meta": {"level": "notice"}}
        with self.assertRaises(ValueError):
            verify_route_chat_id(card, "notice", "oc_notice", "")


class TestComputeHitsHash(unittest.TestCase):
    def test_same_hits_same_hash(self):
        hits = [{"id": 1, "reason": "a"}, {"id": 2, "reason": "b"}]
        self.assertEqual(compute_hits_hash(hits), compute_hits_hash(hits))

    def test_hash_is_order_independent(self):
        hits_a = [{"id": 1, "reason": "a"}, {"id": 2, "reason": "b"}]
        hits_b = [{"id": 2, "reason": "b"}, {"id": 1, "reason": "a"}]
        self.assertEqual(compute_hits_hash(hits_a), compute_hits_hash(hits_b))

    def test_hash_is_key_order_independent(self):
        hits_a = [{"id": 1, "reason": "a"}]
        hits_b = [{"reason": "a", "id": 1}]
        self.assertEqual(compute_hits_hash(hits_a), compute_hits_hash(hits_b))

    def test_different_data_different_hash(self):
        hits_a = [{"id": 1, "reason": "a"}]
        hits_b = [{"id": 1, "reason": "changed"}]
        self.assertNotEqual(compute_hits_hash(hits_a), compute_hits_hash(hits_b))

    def test_added_row_changes_hash(self):
        hits_a = [{"id": 1, "reason": "a"}]
        hits_b = [{"id": 1, "reason": "a"}, {"id": 2, "reason": "b"}]
        self.assertNotEqual(compute_hits_hash(hits_a), compute_hits_hash(hits_b))

    def test_empty_hits_returns_valid_hash(self):
        digest = compute_hits_hash([])
        self.assertEqual(len(digest), 64)

    def test_non_list_raises_type_error(self):
        with self.assertRaises(TypeError):
            compute_hits_hash({"id": 1})

    def test_non_dict_item_raises_type_error(self):
        with self.assertRaises(TypeError):
            compute_hits_hash([{"id": 1}, "not a dict"])


class TestEmbedHashInCard(unittest.TestCase):
    def test_embeds_hash_into_meta(self):
        card = {"_meta": {"level": "P1"}}
        result = embed_hash_in_card(card, "abc123")
        self.assertEqual(result["_meta"]["_data_hash"], "abc123")

    def test_creates_meta_when_missing(self):
        result = embed_hash_in_card({}, "abc123")
        self.assertEqual(result["_meta"]["_data_hash"], "abc123")

    def test_does_not_mutate_input(self):
        card = {"_meta": {"level": "P1"}}
        embed_hash_in_card(card, "abc123")
        self.assertNotIn("_data_hash", card["_meta"])

    def test_non_dict_card_raises_type_error(self):
        with self.assertRaises(TypeError):
            embed_hash_in_card(["not a dict"], "abc123")

    def test_empty_hash_raises_type_error(self):
        with self.assertRaises(TypeError):
            embed_hash_in_card({"_meta": {}}, "")

    def test_non_string_hash_raises_type_error(self):
        with self.assertRaises(TypeError):
            embed_hash_in_card({"_meta": {}}, 123)


class TestVerifyCardHash(unittest.TestCase):
    def test_matching_hash_returns_true(self):
        hits = [{"id": 1, "reason": "a"}, {"id": 2, "reason": "b"}]
        card = embed_hash_in_card({"_meta": {"level": "P1"}}, compute_hits_hash(hits))
        self.assertTrue(verify_card_hash(card, hits))

    def test_matching_hash_order_independent(self):
        hits = [{"id": 1, "reason": "a"}, {"id": 2, "reason": "b"}]
        card = embed_hash_in_card({"_meta": {"level": "P1"}}, compute_hits_hash(hits))
        shuffled = [{"id": 2, "reason": "b"}, {"id": 1, "reason": "a"}]
        self.assertTrue(verify_card_hash(card, shuffled))

    def test_modified_data_raises_value_error(self):
        hits = [{"id": 1, "reason": "a"}]
        card = embed_hash_in_card({"_meta": {"level": "P1"}}, compute_hits_hash(hits))
        tampered = [{"id": 1, "reason": "tampered"}]
        with self.assertRaises(ValueError):
            verify_card_hash(card, tampered)

    def test_added_row_raises_value_error(self):
        hits = [{"id": 1, "reason": "a"}]
        card = embed_hash_in_card({"_meta": {"level": "P1"}}, compute_hits_hash(hits))
        with self.assertRaises(ValueError):
            verify_card_hash(card, hits + [{"id": 2, "reason": "b"}])

    def test_missing_meta_raises_value_error(self):
        with self.assertRaises(ValueError):
            verify_card_hash({}, [{"id": 1}])

    def test_missing_data_hash_raises_value_error(self):
        with self.assertRaises(ValueError):
            verify_card_hash({"_meta": {"level": "P1"}}, [{"id": 1}])

    def test_non_dict_card_raises_type_error(self):
        with self.assertRaises(TypeError):
            verify_card_hash(["not a dict"], [{"id": 1}])


if __name__ == "__main__":
    unittest.main()
