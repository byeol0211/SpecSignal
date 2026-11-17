import unittest
from unittest.mock import patch

from src.web import public_api


class PublicApiTests(unittest.TestCase):
    def setUp(self):
        public_api.clear_cache()

    def test_success_is_cached_and_response_is_independent(self):
        result = {"ok": True, "items": [{"jmcd": "1320"}], "raw_file": "private"}
        with patch.object(public_api, "collect_items", return_value=result) as fetch:
            first = public_api.load_items()
            first["items"].clear()
            second = public_api.load_items()
        self.assertEqual(fetch.call_count, 1)
        self.assertTrue(second["cached"])
        self.assertEqual(len(second["items"]), 1)
        self.assertNotIn("raw_file", second)

    def test_failure_not_cached_or_exposed(self):
        with patch.object(public_api, "collect_items", return_value={"ok": False, "error": "private diagnostic"}) as fetch:
            result = public_api.load_items()
            public_api.load_items()
        self.assertEqual(fetch.call_count, 2)
        self.assertNotIn("private", result["error"])

    def test_schedule_uses_requested_category_and_year(self):
        with patch.object(public_api, "collect_info", return_value={"ok": True, "items": []}) as fetch:
            result = public_api.load_info("1320", year="2026", category="T")
        fetch.assert_called_once_with("1320", year="2026", category="T")
        self.assertTrue(result["empty"])

    def test_invalid_query_does_not_call_upstream(self):
        with patch.object(public_api, "collect_info") as fetch:
            with self.assertRaises(ValueError):
                public_api.load_info("../x")
        fetch.assert_not_called()

    def test_expired_cache_is_refetched(self):
        with patch.object(public_api, "collect_items", return_value={"ok": True, "items": []}) as fetch:
            with patch.object(public_api, "monotonic", return_value=0):
                public_api.load_items()
            with patch.object(public_api, "monotonic", return_value=301):
                public_api.load_items()
        self.assertEqual(fetch.call_count, 2)
