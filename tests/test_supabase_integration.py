"""Supabase(PostgreSQL) 통합 테스트: 저장·조회·중복 방지와 RLS 정책.

로컬 Supabase(npx supabase start)에서만 실행한다. 모든 변경은 테스트마다 롤백된다.
  set TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres
  python -m unittest tests.test_supabase_integration -v
"""

import json
import os
import unittest
import uuid
from contextlib import contextmanager, nullcontext
from datetime import date, datetime, timezone
from unittest.mock import patch
from urllib.parse import urlsplit

import psycopg
from psycopg.rows import dict_row

from src.certification import normalize
from src.db import certifications as repo
from tests.test_certification_sync import PROFESSIONAL, RECORDS, schedule_record


URL = os.getenv("TEST_DATABASE_URL", "")
IS_LOCAL = urlsplit(URL).hostname in {"127.0.0.1", "localhost"}
T1 = datetime(2026, 10, 13, 1, 0, tzinfo=timezone.utc)
T2 = datetime(2026, 10, 14, 1, 0, tzinfo=timezone.utc)
ITEMS = [
    {"jmcd": "1320", "jmfldnm": "정보처리기사", "qualgbcd": "T", "qualgbnm": "국가기술자격",
     "seriescd": "02", "seriesnm": "기사", "obligfldcd": "21", "obligfldnm": "정보통신",
     "mdobligfldcd": "211", "mdobligfldnm": "정보기술"},
    {"jmcd": "9750", "jmfldnm": "공인중개사", "qualgbcd": "S", "qualgbnm": "국가전문자격"},
]


@unittest.skipUnless(URL and IS_LOCAL, "TEST_DATABASE_URL(로컬 Supabase)이 설정된 경우에만 실행")
class DatabaseTestCase(unittest.TestCase):
    def setUp(self):
        self.conn = psycopg.connect(URL, row_factory=dict_row)
        self.conn.execute("select 1")  # 테스트 전체를 하나의 트랜잭션으로 묶는다

    def tearDown(self):
        self.conn.rollback()
        self.conn.close()

    def seed_certifications(self) -> dict[str, int]:
        repo.upsert_certifications(self.conn, [normalize.item_to_row(i) for i in ITEMS], T1)
        return {r["jm_cd"]: r["id"] for r in self.conn.execute(
            "select id, jm_cd from public.certifications where jm_cd in ('1320', '9750')")}

    def create_user(self, name: str) -> str:
        user_id = str(uuid.uuid4())
        self.conn.execute(
            """insert into auth.users (id, instance_id, aud, role, email, raw_user_meta_data,
                                       raw_app_meta_data, created_at, updated_at)
               values (%s, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated',
                       %s, %s, '{}', now(), now())""",
            (user_id, f"{user_id}@test.local", json.dumps({"name": name})))
        return user_id

    @contextmanager
    def as_role(self, role: str, user_id: str | None = None, admin: bool = False):
        """백엔드 user_transaction과 같은 방식으로 역할과 JWT claims를 설정한다."""
        claims = {"role": role, "aud": "authenticated" if user_id else None}
        if user_id:
            claims["sub"] = user_id
            claims["app_metadata"] = {"role": "admin"} if admin else {}
        with self.conn.transaction():  # savepoint: 실패해도 바깥 트랜잭션은 유지
            self.conn.execute("select set_config('request.jwt.claims', %s, true), "
                              "set_config('request.jwt.claim.sub', %s, true)",
                              (json.dumps(claims), user_id or ""))
            self.conn.execute(f"set local role {role}")
            try:
                yield self.conn
            finally:
                if not self.conn.info.transaction_status == psycopg.pq.TransactionStatus.INERROR:
                    self.conn.execute("reset role")
                    self.conn.execute("select set_config('request.jwt.claims', '', true), "
                                      "set_config('request.jwt.claim.sub', '', true)")

    def assert_denied(self, role, sql, params=(), user_id=None):
        with self.assertRaises(psycopg.errors.InsufficientPrivilege):
            with self.as_role(role, user_id) as conn:
                conn.execute(sql, params)


class RepositoryTests(DatabaseTestCase):
    def test_certification_upsert_is_idempotent_and_tracks_changes(self):
        rows = [normalize.item_to_row(i) for i in ITEMS]
        first = repo.upsert_certifications(self.conn, rows, T1)
        self.assertEqual((first["inserted"], first["updated"], first["unchanged"]), (2, 0, 0))
        created = self.conn.execute(
            "select updated_at from public.certifications where jm_cd = '1320'").fetchone()["updated_at"]

        second = repo.upsert_certifications(self.conn, rows, T2)
        self.assertEqual((second["inserted"], second["updated"], second["unchanged"]), (0, 0, 2))
        row = self.conn.execute("select count(*) as n, max(list_synced_at) as at from public.certifications "
                                "where jm_cd in ('1320', '9750')").fetchone()
        self.assertEqual((row["n"], row["at"]), (2, T2))
        # 수집 시각만 바뀐 경우 updated_at은 유지
        same = self.conn.execute(
            "select updated_at from public.certifications where jm_cd = '1320'").fetchone()["updated_at"]
        self.assertEqual(same, created)

        rows[0]["name"] = "정보처리기사(변경)"
        third = repo.upsert_certifications(self.conn, rows, T2)
        self.assertEqual(third["updated"], 1)

    def test_missing_api_values_are_null(self):
        self.seed_certifications()
        row = self.conn.execute("select series_nm, oblig_fld_nm from public.certifications "
                                "where jm_cd = '9750'").fetchone()
        self.assertEqual(row, {"series_nm": None, "oblig_fld_nm": None})

    def test_exam_upsert_keeps_registration_variants_and_deactivates_removed(self):
        ids = self.seed_certifications()
        rows, _ = normalize.schedules_to_rows(RECORDS)
        counts = repo.replace_exams(self.conn, ids["1320"], 2026, "T", rows, T1)
        self.assertEqual(counts["inserted"], 3)
        again = repo.replace_exams(self.conn, ids["1320"], 2026, "T", rows, T2)
        self.assertEqual((again["inserted"], again["unchanged"]), (0, 3))

        # 추가 접수 행이 공고에서 빠지면 비활성화 (삭제하지 않음)
        rows, _ = normalize.schedules_to_rows(RECORDS[1:])
        changed = repo.replace_exams(self.conn, ids["1320"], 2026, "T", rows, T2)
        self.assertEqual(changed["deactivated"], 1)
        active = repo.get_exams(self.conn, ids["1320"], year=2026)
        self.assertEqual(len(active), 2)
        total = self.conn.execute("select count(*) as n from public.certification_exams "
                                  "where certification_id = %s", (ids["1320"],)).fetchone()["n"]
        self.assertEqual(total, 3)

    def test_natural_key_rejects_duplicates_with_null_description(self):
        ids = self.seed_certifications()
        rows, _ = normalize.schedules_to_rows([schedule_record("20260801", "20260802", description="")])
        repo.replace_exams(self.conn, ids["1320"], 2026, "T", rows, T1)
        with self.assertRaises(psycopg.errors.UniqueViolation), self.conn.transaction():
            self.conn.execute(
                "insert into public.certification_exams (certification_id, impl_year, impl_seq, qualgb_cd, "
                "description, exam_phase, reg_start_date, reg_end_date, last_synced_at) "
                "values (%s, 2026, 3, 'T', null, 'written', '2026-08-01', '2026-08-02', now())", (ids["1320"],))

    def test_details_replace_and_sync_state_keeps_last_success(self):
        ids = self.seed_certifications()
        repo.replace_details(self.conn, ids["1320"], [{"info_gb": "취득방법", "contents": "A"},
                                                      {"info_gb": "응시자격", "contents": "B"}], T1)
        repo.record_sync_state(self.conn, ids["1320"], "details", 0, "success", T1, record_count=2)
        counts = repo.replace_details(self.conn, ids["1320"], [{"info_gb": "취득방법", "contents": "A2"}], T2)
        self.assertEqual((counts["updated"], counts["deactivated"]), (1, 1))

        repo.record_sync_state(self.conn, ids["1320"], "details", 0, "error", T2, error="연결 장애")
        state = repo.get_sync_state(self.conn, ids["1320"], "details")
        self.assertEqual((state["last_status"], state["last_success_at"], state["record_count"]),
                         ("error", T1, 2))

    def test_sync_targets_respect_refresh_interval(self):
        ids = self.seed_certifications()
        repo.record_sync_state(self.conn, ids["1320"], "schedule", 2026, "success",
                               datetime.now(timezone.utc))
        stale = {r["jm_cd"] for r in repo.certifications_to_sync(self.conn, "schedule", 2026, 24,
                                                                 ["1320", "9750"])}
        self.assertEqual(stale, {"9750"})
        forced = repo.certifications_to_sync(self.conn, "schedule", 2026, None, ["1320", "9750"])
        self.assertEqual(len(forced), 2)

    def test_legacy_web_endpoints_read_from_database(self):
        from src.web import server
        ids = self.seed_certifications()
        rows, _ = normalize.schedules_to_rows(RECORDS)
        repo.replace_exams(self.conn, ids["1320"], 2026, "T", rows, T1)
        repo.record_sync_state(self.conn, ids["1320"], "schedule", 2026, "success", T1)
        with patch.object(server, "service_transaction", lambda: nullcontext(self.conn)):
            items = server.load_items()
            schedules = server.load_info("1320", year="2026", category="T")
            missing = server.load_info("1320")  # 상세정보 미수집
        self.assertTrue(items["ok"])
        self.assertIn("1320", {i["jmcd"] for i in items["items"]})
        self.assertTrue(schedules["ok"])
        self.assertCountEqual(schedules["items"], RECORDS)  # 원래 API 응답 형태로 복원
        self.assertEqual((missing["ok"], missing["collected"]), (False, False))

    def test_sync_runs_log(self):
        run_id = repo.start_run(self.conn, "certification_list", {"force": True})
        repo.finish_run(self.conn, run_id, "success", {"requested": 1, "success": 1, "inserted": 613})
        run = [r for r in repo.latest_runs(self.conn) if r["job"] == "certification_list"][0]
        self.assertEqual((run["status"], run["inserted_count"]), ("success", 613))
        self.assertIsNotNone(run["finished_at"])


class RlsTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.ids = self.seed_certifications()
        self.alice = self.create_user("Alice")
        self.bob = self.create_user("Bob")

    def test_profile_created_on_signup_and_private(self):
        with self.as_role("authenticated", self.alice) as conn:
            rows = conn.execute("select id, display_name from public.profiles").fetchall()
            prefs = conn.execute("select study_period_basis from public.user_preferences").fetchall()
        self.assertEqual(rows, [{"id": uuid.UUID(self.alice), "display_name": "Alice"}])
        self.assertEqual(prefs, [{"study_period_basis": "avg"}])

    def test_official_data_is_read_only(self):
        with self.as_role("anon") as conn:
            self.assertGreaterEqual(conn.execute("select count(*) as n from public.certifications")
                                    .fetchone()["n"], 2)
        self.assert_denied("anon", "insert into public.certifications (jm_cd, name, list_synced_at) "
                                   "values ('ZZZZ', 'x', now())")
        self.assert_denied("authenticated", "update public.certifications set name = 'x'",
                           user_id=self.alice)
        self.assert_denied("authenticated", "delete from public.certification_exams", user_id=self.alice)
        self.assert_denied("anon", "select * from public.sync_runs")

    def test_calendar_events_are_isolated(self):
        with self.as_role("authenticated", self.alice) as conn:
            event_id = conn.execute(
                "insert into public.calendar_events (title, event_type, start_date) "
                "values ('정보처리기사 필기', 'exam', '2026-08-07') returning id").fetchone()["id"]
        with self.as_role("authenticated", self.bob) as conn:
            self.assertEqual(conn.execute("select * from public.calendar_events").fetchall(), [])
            updated = conn.execute("update public.calendar_events set title = 'hacked' where id = %s",
                                   (event_id,)).rowcount
            self.assertEqual(updated, 0)
        with self.assertRaises(psycopg.errors.InsufficientPrivilege):
            with self.as_role("authenticated", self.bob) as conn:  # 남의 user_id로 생성 불가
                conn.execute("insert into public.calendar_events (user_id, title, event_type, start_date) "
                             "values (%s, 'x', 'exam', '2026-01-01')", (self.alice,))
        self.assert_denied("anon", "select * from public.calendar_events")

    def test_bookmark_duplicates_rejected(self):
        with self.as_role("authenticated", self.alice) as conn:
            conn.execute("insert into public.bookmarks (certification_id) values (%s)", (self.ids["1320"],))
        with self.assertRaises(psycopg.errors.UniqueViolation):
            with self.as_role("authenticated", self.alice) as conn:
                conn.execute("insert into public.bookmarks (certification_id) values (%s)", (self.ids["1320"],))

    def test_competition_approval_is_admin_only(self):
        values = ("AI 공모전", "테스트기관", "https://example.com/notice", date(2026, 12, 1))
        with self.as_role("authenticated", self.alice) as conn:
            competition_id = conn.execute(
                "insert into public.competitions (title, organizer, official_url, apply_end_date, status) "
                "values (%s, %s, %s, %s, 'pending') returning id", values).fetchone()["id"]
        with self.as_role("anon") as conn:
            self.assertEqual(conn.execute("select * from public.competitions").fetchall(), [])
        with self.assertRaises(psycopg.errors.InsufficientPrivilege):
            with self.as_role("authenticated", self.alice) as conn:
                conn.execute("update public.competitions set status = 'approved' where id = %s",
                             (competition_id,))
        with self.as_role("authenticated", self.bob) as conn:  # 타인 검토중 공모전은 보이지 않음
            self.assertEqual(conn.execute("select * from public.competitions").fetchall(), [])
        with self.as_role("authenticated", self.bob, admin=True) as conn:
            conn.execute("update public.competitions set status = 'approved', reviewed_at = now() "
                         "where id = %s", (competition_id,))
        with self.as_role("anon") as conn:
            self.assertEqual(len(conn.execute("select id from public.competitions").fetchall()), 1)
        with self.as_role("authenticated", self.alice) as conn:  # 승인 후 작성자도 수정 불가
            self.assertEqual(conn.execute("update public.competitions set title = 'x' where id = %s",
                                          (competition_id,)).rowcount, 0)

    def test_chat_messages_user_only_and_own_session(self):
        with self.as_role("authenticated", self.alice) as conn:
            session_id = conn.execute("insert into public.chat_sessions (title) values ('추천') "
                                      "returning id").fetchone()["id"]
            conn.execute("insert into public.chat_messages (session_id, role, content) "
                         "values (%s, 'user', '정보보안 자격증 추천해줘')", (session_id,))
        with self.assertRaises(psycopg.errors.InsufficientPrivilege):
            with self.as_role("authenticated", self.alice) as conn:  # AI 응답 위조 불가
                conn.execute("insert into public.chat_messages (session_id, role, content) "
                             "values (%s, 'assistant', 'x')", (session_id,))
        with self.assertRaises(psycopg.errors.InsufficientPrivilege):
            with self.as_role("authenticated", self.bob) as conn:  # 남의 세션에 기록 불가
                conn.execute("insert into public.chat_messages (session_id, role, content) "
                             "values (%s, 'user', 'x')", (session_id,))

    def test_sync_logs_visible_to_admin_only(self):
        repo.start_run(self.conn, "certification_list", {})
        with self.as_role("authenticated", self.alice) as conn:
            self.assertEqual(conn.execute("select * from public.sync_runs").fetchall(), [])
        with self.as_role("authenticated", self.alice, admin=True) as conn:
            self.assertGreaterEqual(len(conn.execute("select * from public.sync_runs").fetchall()), 1)


if __name__ == "__main__":
    unittest.main()
