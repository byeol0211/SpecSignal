import unittest
from unittest.mock import patch

import requests

from src.certification import collect_info as info


def response(body, code="00"):
    result = requests.Response()
    result.status_code = 200
    result._content = f"<response><header><resultCode>{code}</resultCode></header><body>{body}</body></response>".encode()
    return result


def schedule(page, total, rows=1):
    item = "<item><implYy>2026</implYy><qualgbCd>T</qualgbCd><implSeq>1</implSeq></item>"
    return response(f"<items>{item * rows}</items><pageNo>{page}</pageNo><totalCount>{total}</totalCount>")


class InfoTests(unittest.TestCase):
    def setUp(self):
        for target, value in [("load_api_key", "dummy-key"), ("save_raw_response", info.PROJECT_ROOT / "data/raw/test.xml")]:
            patcher = patch.object(info, target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def connection_error(self):
        result = response("", "99")
        result._content = result.content.replace(b"</resultCode>", b"</resultCode><resultMsg>Failed to validate a newly established connection.</resultMsg>")
        return result

    @patch.object(info.time, "sleep")
    def test_connection_error_retries_then_succeeds(self, sleep):
        with patch.object(info.requests, "get", side_effect=[self.connection_error(), response("<items/>")]) as call:
            result = info.collect_info("9750")
        self.assertTrue(result["ok"])
        self.assertTrue(result["empty"])
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(call.call_count, 2)
        sleep.assert_called_once_with(1)

    @patch.object(info.time, "sleep")
    def test_persistent_connection_error_is_not_no_data(self, sleep):
        with patch.object(info.requests, "get", side_effect=[self.connection_error() for _ in range(3)]) as call:
            result = info.collect_info("9750")
        self.assertFalse(result["ok"])
        self.assertTrue(result["retryable"])
        self.assertNotIn("empty", result)
        self.assertEqual(call.call_count, 3)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [1, 2])

    def test_authentication_and_unknown_errors_are_not_retried(self):
        for code in ("30", "99"):
            with patch.object(info.requests, "get", return_value=response("", code)) as call:
                result = info.collect_info("9750")
            self.assertFalse(result["ok"])
            self.assertFalse(result["retryable"])
            call.assert_called_once()

    def test_empty_details_and_missing_structure_are_distinct(self):
        with patch.object(info.requests, "get", return_value=response("<items/>")):
            result = info.collect_info("9750")
        self.assertTrue(result["ok"])
        self.assertTrue(result["empty"])
        with patch.object(info.requests, "get", return_value=response("")):
            self.assertFalse(info.collect_info("9750")["ok"])

    @patch.object(info.time, "sleep")
    def test_timeout_retry_redacts_secret(self, sleep):
        with patch.object(info.requests, "get", side_effect=requests.Timeout("dummy-key")) as call:
            result = info.collect_info("9750")
        self.assertEqual(call.call_count, 3)
        self.assertIsNone(result["http_status"])
        self.assertNotIn("dummy-key", result["diagnostic"])

    def test_details_uses_documented_key_and_preserves_text(self):
        xml = response("<items><item><infogb>exam</infogb><jmfldnm>test</jmfldnm><contents>&amp;lt;test&amp;gt;</contents></item></items>")
        with patch.object(info.requests, "get", return_value=xml) as call:
            result = info.collect_info("0123")
        self.assertTrue(result["ok"])
        self.assertEqual(result["items"][0]["contents"], "<test>")
        self.assertEqual(call.call_args.kwargs["params"]["ServiceKey"], "dummy-key")
        self.assertEqual(call.call_args.kwargs["params"]["jmCd"], "0123")

    def test_collects_all_schedule_pages(self):
        with patch.object(info.requests, "get", side_effect=[schedule(1, 51, 50), schedule(2, 51)]) as call:
            result = info.collect_info("1320", year="2026", category="T")
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["items"]), 51)
        self.assertEqual(call.call_count, 2)

    def test_empty_schedule_is_success(self):
        with patch.object(info.requests, "get", return_value=schedule(1, 0, 0)):
            result = info.collect_info("1320", year="2026", category="T")
        self.assertTrue(result["ok"])
        self.assertEqual(result["items"], [])

    def test_business_error_and_incomplete_pages_fail(self):
        for responses in ([response("", "99")], [schedule(1, 2), schedule(2, 2, 0)]):
            with patch.object(info.requests, "get", side_effect=responses):
                result = info.collect_info("1320", year="2026", category="T")
            self.assertFalse(result["ok"])

    def test_rejects_wrong_year_and_invalid_input(self):
        with patch.object(info.requests, "get", return_value=schedule(1, 1)):
            self.assertFalse(info.collect_info("1320", year="2025", category="T")["ok"])
        with self.assertRaises(ValueError):
            info.collect_info("../bad")


if __name__ == "__main__":
    unittest.main()
