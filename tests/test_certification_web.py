"""실제 API를 반복 호출하지 않고 응답 처리와 로컬 웹 경로를 검증한다."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

import requests

from src.certification import collect_items as collector
from src.web.server import background_server


SUCCESS = b'''<response><header><resultCode>00</resultCode></header><body><items>
<item><jmcd>0123</jmcd><jmfldnm>Test qualification</jmfldnm><qualgbnm>Test type</qualgbnm></item>
</items></body></response>'''


class CollectorTests(unittest.TestCase):
    def test_parse_preserves_code_and_optional_fields(self):
        item = collector.parse_items(SUCCESS)[0]
        self.assertEqual(item["jmcd"], "0123")
        self.assertEqual(item["obligfldnm"], "")

    def test_rejects_business_error_malformed_and_missing_fields(self):
        for content in (
            SUCCESS.replace(b"<resultCode>00", b"<resultCode>30"),
            b"<html>not XML", SUCCESS.replace(b"<jmcd>0123</jmcd>", b""),
            b"<!DOCTYPE response><response/>",
        ):
            with self.subTest(content=content), self.assertRaises(ValueError):
                collector.parse_items(content)

    def test_saves_raw_success_and_http_error_and_redacts_key(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.multiple(collector, PROJECT_ROOT=root, RAW_DIR=root / "data" / "raw"), patch.object(collector, "load_api_key", return_value="test-secret"):
                for status, content in [(200, SUCCESS), (403, b"denied test-secret")]:
                    response = requests.Response()
                    response.status_code = status
                    response._content = content
                    with patch.object(collector, "request_items", return_value=response):
                        result = collector.collect_items()
                    self.assertEqual(result["ok"], status == 200)
                    self.assertEqual(result["http_status"], status)
                    self.assertEqual((root / result["raw_file"]).read_bytes(), content)
                    self.assertNotIn("test-secret", json.dumps(result))

    def test_timeout_is_reported_without_secret(self):
        with patch.object(collector.requests, "request", side_effect=requests.Timeout("key=test-secret")):
            with self.assertRaises(RuntimeError) as error:
                collector.request_items("test-secret")
        self.assertNotIn("test-secret", str(error.exception))


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = background_server()
        cls.base = cls.server.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.server.__exit__(None, None, None)

    def test_page_and_static_assets(self):
        for path in ("/", "/app.js", "/style.css", "/assets/home.svg"):
            with urlopen(self.base + path) as response:
                self.assertEqual(response.status, 200)
                self.assertTrue(response.read())

    def test_web_policy_disallows_unsafe_eval(self):
        with urlopen(self.base) as response:
            self.assertNotIn("unsafe-eval", response.headers["Content-Security-Policy"])

    def test_private_files_are_not_served(self):
        for path in ("/.env", "/../.env", "/data/raw/example.bin"):
            with self.assertRaises(HTTPError) as error:
                urlopen(self.base + path)
            self.assertEqual(error.exception.code, 404)
            error.exception.close()

    def test_api_success_and_failure(self):
        # 화면 API는 Supabase에 저장된 데이터를 조회한다 (load_items). DB 미연결/미수집은 503.
        for result in ({"ok": True, "items": collector.parse_items(SUCCESS), "fetched_at": "2026-10-13T00:00:00+00:00"}, {"ok": False, "error": "test failure", "http_status": None}):
            with patch("src.web.server.load_items", return_value=result):
                try:
                    response = urlopen(self.base + "/api/items")
                except HTTPError as error:
                    response = error
                with response:
                    self.assertEqual(response.status, 200 if result["ok"] else 503)
                    self.assertEqual(json.load(response), result)


if __name__ == "__main__":
    unittest.main()
