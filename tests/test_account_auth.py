import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from src.academic.routes import Credentials, authenticate


class AccountAuthTests(unittest.TestCase):
    def call_auth(self, payload, status=200, action="signup"):
        settings = SimpleNamespace(supabase_url="https://example.supabase.co", supabase_publishable_key="test")
        response = SimpleNamespace(ok=status < 400, status_code=status, json=lambda: payload)
        with patch("src.academic.routes.get_settings", return_value=settings), patch("src.academic.routes.requests.post", return_value=response):
            return authenticate(action, Credentials(email="student@example.com", password="password123"))

    def test_signup_waits_for_email_confirmation(self):
        result = self.call_auth({"user": {"id": "test"}})
        self.assertTrue(result["confirmation_required"])
        self.assertIsNone(result["access_token"])

    def test_login_returns_session(self):
        result = self.call_auth({"access_token": "token", "expires_in": 3600}, action="login")
        self.assertFalse(result["confirmation_required"])
        self.assertEqual(result["access_token"], "token")

    def test_actionable_errors_without_provider_details(self):
        for code, status, expected in [
            ("over_email_send_rate_limit", 429, "발송 한도"),
            ("email_not_confirmed", 400, "인증이 완료되지"),
            ("invalid_credentials", 400, "비밀번호"),
            ("unexpected_failure", 500, "DB 트리거"),
        ]:
            with self.subTest(code=code), self.assertRaises(HTTPException) as error:
                self.call_auth({"code": status, "error_code": code, "msg": "private provider detail"}, status)
            self.assertIn(expected, error.exception.detail)
            self.assertNotIn("private provider detail", error.exception.detail)
            self.assertEqual(error.exception.status_code, 503 if status == 500 else status)
