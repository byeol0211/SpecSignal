"""DB 없이 매핑·검증과 수집 정책(실패 시 기존 데이터 유지, 재시도, 빈 결과)을 검증한다."""

import unittest
from contextlib import nullcontext
from datetime import date
from unittest.mock import MagicMock, patch

from src.certification import normalize, sync


# data/raw 실응답(1320, 2026년 3회)과 같은 구조: 필기 접수기간만 다른 두 행
def schedule_record(reg_start, reg_end, **overrides):
    record = {
        "implYy": "2026", "implSeq": "3", "qualgbCd": "T", "qualgbNm": "국가기술자격",
        "description": "국가기술자격 기사 (2026년도 제3회)",
        "docRegStartDt": reg_start, "docRegEndDt": reg_end, "docExamStartDt": "20260807",
        "docExamEndDt": "20260901", "docPassDt": "20260909", "pracRegStartDt": "20260921",
        "pracRegEndDt": "20261019", "pracExamStartDt": "20261024", "pracExamEndDt": "20261113",
        "pracPassDt": "20261211",
    }
    record.update(overrides)
    return record


RECORDS = [schedule_record("20260801", "20260802"), schedule_record("20260720", "20260723")]
PROFESSIONAL = {  # 국가전문자격: 실기(prac*) 필드가 비어 있음
    "implYy": "2026", "implSeq": "34", "qualgbCd": "S", "qualgbNm": "국가전문자격",
    "description": "공인중개사 (2026년도 34회 1차)", "docRegStartDt": "20260629",
    "docRegEndDt": "20260814", "docExamStartDt": "20260822", "docExamEndDt": "20260822",
    "docPassDt": "20261104", "pracRegStartDt": None, "pracRegEndDt": "", "pracExamStartDt": None,
    "pracExamEndDt": None, "pracPassDt": None,
}


class NormalizeTests(unittest.TestCase):
    def test_item_mapping_keeps_missing_values_null(self):
        row = normalize.item_to_row({"jmcd": "1320", "jmfldnm": "정보처리기사", "qualgbcd": "T",
                                     "seriesnm": "", "obligfldnm": " 정보통신 "})
        self.assertEqual(row["jm_cd"], "1320")
        self.assertEqual(row["oblig_fld_nm"], "정보통신")
        self.assertIsNone(row["series_nm"])
        self.assertIsNone(row["mdoblig_fld_cd"])

    def test_item_mapping_rejects_bad_code_or_name(self):
        for item in ({"jmcd": "12", "jmfldnm": "x"}, {"jmcd": "1320", "jmfldnm": ""}):
            with self.subTest(item=item), self.assertRaises(ValueError):
                normalize.item_to_row(item)

    def test_date_validation(self):
        self.assertEqual(normalize.parse_api_date("20260228", "f"), date(2026, 2, 28))
        self.assertIsNone(normalize.parse_api_date("", "f"))
        self.assertIsNone(normalize.parse_api_date(None, "f"))
        for bad in ("2026-08-01", "20261301", "20260230", "2026081"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                normalize.parse_api_date(bad, "f")

    def test_duplicate_registration_rows_are_kept_and_practical_merged(self):
        rows, warnings = normalize.schedules_to_rows(RECORDS)
        self.assertEqual(warnings, [])
        written = [r for r in rows if r["exam_phase"] == "written"]
        practical = [r for r in rows if r["exam_phase"] == "practical"]
        self.assertEqual(len(written), 2)  # 접수기간이 다른 두 필기 행 모두 보존
        self.assertEqual(len(practical), 1)  # 동일한 실기 일정은 하나로
        self.assertEqual(practical[0]["reg_start_date"], date(2026, 9, 21))
        self.assertEqual({r["reg_start_date"] for r in written}, {date(2026, 8, 1), date(2026, 7, 20)})

    def test_professional_qualification_has_no_practical_row(self):
        rows, _ = normalize.schedules_to_rows([PROFESSIONAL])
        self.assertEqual([r["exam_phase"] for r in rows], ["written"])
        self.assertEqual(rows[0]["impl_seq"], 34)

    def test_conflicting_values_for_same_key_fail(self):
        changed = schedule_record("20260801", "20260802", docPassDt="20260910")
        with self.assertRaises(ValueError):
            normalize.schedules_to_rows([RECORDS[0], changed])

    def test_invalid_schedule_fields_fail(self):
        for record in (schedule_record("2026-08-01", "20260802"), {**RECORDS[0], "implSeq": ""},
                       {**RECORDS[0], "implYy": "26"}):
            with self.subTest(record=record), self.assertRaises(ValueError):
                normalize.schedules_to_rows([record])

    def test_reversed_dates_are_stored_with_warning(self):
        rows, warnings = normalize.schedules_to_rows([schedule_record("20260805", "20260801")])
        self.assertEqual(len(warnings), 1)
        self.assertEqual(rows[0]["reg_start_date"], date(2026, 8, 5))  # 공식 값은 수정하지 않음

    def test_legacy_round_trip_matches_api_rows(self):
        rows, _ = normalize.schedules_to_rows(RECORDS + [PROFESSIONAL])
        legacy = normalize.rows_to_legacy_schedules(rows)
        expected = [{k: (v or None) for k, v in r.items()} for r in RECORDS + [PROFESSIONAL]]
        self.assertCountEqual(legacy, expected)
        self.assertEqual(legacy[0]["implSeq"], "34")  # 최신 회차 우선


def fake_conn():
    conn = MagicMock()
    conn.transaction.side_effect = lambda: nullcontext()
    conn.closed = False
    return conn


TARGETS = [{"id": 1, "jm_cd": "1320", "name": "정보처리기사", "qualgb_cd": "T"},
           {"id": 2, "jm_cd": "2193", "name": "정보보안기사", "qualgb_cd": "T"}]


@patch.object(sync.time, "sleep")
@patch.object(sync, "repo")
class SyncPolicyTests(unittest.TestCase):
    def setUp(self):
        sync.get_settings.cache_clear()

    def test_failed_item_keeps_existing_data_and_logs_state(self, repo, _sleep):
        repo.certifications_to_sync.return_value = TARGETS
        repo.replace_details.return_value = {"inserted": 1, "updated": 0, "unchanged": 0, "deactivated": 0}
        responses = {
            "1320": {"ok": True, "items": [{"infogb": "취득방법", "contents": "내용"}]},
            "2193": {"ok": False, "error": "업무 오류 30", "retryable": False},
        }
        with patch.object(sync, "collect_info", side_effect=lambda j: responses[j]):
            status = sync.sync_details(fake_conn(), force=True)
        self.assertEqual(status, "partial")
        repo.replace_details.assert_called_once()  # 실패 종목은 저장 함수 호출 없음
        states = [c.args[4] for c in repo.record_sync_state.call_args_list]
        self.assertEqual(states, ["success", "error"])
        stats = repo.finish_run.call_args.args[3]
        self.assertEqual((stats["success"], stats["error"], stats["inserted"]), (1, 1, 1))

    def test_transient_failure_is_retried_once_at_end(self, repo, sleep):
        repo.certifications_to_sync.return_value = TARGETS[:1]
        repo.replace_details.return_value = {"inserted": 0, "updated": 0, "unchanged": 1, "deactivated": 0}
        results = iter([{"ok": False, "error": "연결 장애", "retryable": True},
                        {"ok": True, "items": [{"infogb": "취득방법", "contents": "내용"}]}])
        with patch.object(sync, "collect_info", side_effect=lambda j: next(results)):
            status = sync.sync_details(fake_conn(), force=True)
        self.assertEqual(status, "success")
        sleep.assert_any_call(sync.DEFERRED_RETRY_DELAY_SECONDS)
        self.assertEqual(repo.record_sync_state.call_count, 1)

    def test_empty_result_does_not_delete_existing_rows(self, repo, _sleep):
        repo.certifications_to_sync.return_value = TARGETS[:1]
        with patch.object(sync, "collect_info", return_value={"ok": True, "items": [], "empty": True}):
            status = sync.sync_schedules(fake_conn(), years=["2027"], force=True)
        self.assertEqual(status, ["empty"])
        repo.replace_exams.assert_not_called()
        self.assertEqual(repo.record_sync_state.call_args.args[4], "empty")

    def test_invalid_response_is_not_stored(self, repo, _sleep):
        repo.certifications_to_sync.return_value = TARGETS[:1]
        bad = {"ok": True, "items": [schedule_record("2026/08/01", "20260802")]}
        with patch.object(sync, "collect_info", return_value=bad):
            status = sync.sync_schedules(fake_conn(), years=["2026"], force=True)
        self.assertEqual(status, ["error"])
        repo.replace_exams.assert_not_called()

    def test_schedule_uses_year_and_category_from_db(self, repo, _sleep):
        repo.certifications_to_sync.return_value = TARGETS[:1]
        repo.replace_exams.return_value = {"inserted": 3, "updated": 0, "unchanged": 0, "deactivated": 0}
        with patch.object(sync, "collect_info", return_value={"ok": True, "items": RECORDS}) as collect:
            sync.sync_schedules(fake_conn(), years=["2026"], force=True)
        collect.assert_called_once_with("1320", year="2026", category="T")
        args = repo.replace_exams.call_args.args
        self.assertEqual((args[1], args[2], args[3], len(args[4])), (1, 2026, "T", 3))

    def test_list_failure_keeps_existing_rows(self, repo, _sleep):
        repo.last_list_sync.return_value = None
        with patch.object(sync, "collect_items", return_value={"ok": False, "http_status": 500, "error": "x"}):
            self.assertEqual(sync.sync_list(fake_conn()), "error")
        repo.upsert_certifications.assert_not_called()
        self.assertEqual(repo.finish_run.call_args.args[2], "error")


if __name__ == "__main__":
    unittest.main()
