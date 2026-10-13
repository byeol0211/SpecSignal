"""공공데이터 API 응답 → DB 행 매핑과 검증. API가 제공하지 않은 값은 만들지 않고 None으로 둔다."""

import re
from datetime import date, datetime


# 15003024 국가자격 종목 목록: 응답 필드 → certifications 컬럼
ITEM_FIELDS = {
    "jmcd": "jm_cd", "jmfldnm": "name",
    "qualgbcd": "qualgb_cd", "qualgbnm": "qualgb_nm",
    "seriescd": "series_cd", "seriesnm": "series_nm",
    "obligfldcd": "oblig_fld_cd", "obligfldnm": "oblig_fld_nm",
    "mdobligfldcd": "mdoblig_fld_cd", "mdobligfldnm": "mdoblig_fld_nm",
}

# 15074408 시험일정: 한 응답 행의 필기(doc*)/실기(prac*) 날짜를 단계별 행으로 분리
PHASE_PREFIXES = {"written": "doc", "practical": "prac"}
PHASE_DATE_FIELDS = {
    "reg_start_date": "RegStartDt", "reg_end_date": "RegEndDt",
    "exam_start_date": "ExamStartDt", "exam_end_date": "ExamEndDt",
    "pass_date": "PassDt",
}
EXAM_KEY_FIELDS = ("impl_year", "impl_seq", "qualgb_cd", "description",
                   "exam_phase", "reg_start_date", "reg_end_date")
EXAM_VALUE_FIELDS = ("qualgb_nm", "exam_start_date", "exam_end_date", "pass_date")


def blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def parse_api_date(value: str | None, field: str) -> date | None:
    """API 날짜는 YYYYMMDD. 비어 있으면 None, 형식이 다르면 저장하지 않도록 오류."""
    value = blank_to_none(value)
    if value is None:
        return None
    if not re.fullmatch(r"\d{8}", value):
        raise ValueError(f"{field} 날짜 형식이 YYYYMMDD가 아닙니다: {value!r}")
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError:
        raise ValueError(f"{field}에 존재하지 않는 날짜가 있습니다: {value!r}") from None


def item_to_row(item: dict[str, str]) -> dict:
    row = {column: blank_to_none(item.get(field)) for field, column in ITEM_FIELDS.items()}
    if not row["jm_cd"] or not re.fullmatch(r"[A-Za-z0-9]{4}", row["jm_cd"]):
        raise ValueError(f"종목코드 형식이 올바르지 않습니다: {row['jm_cd']!r}")
    if not row["name"]:
        raise ValueError(f"종목명이 없습니다: {row['jm_cd']}")
    return row


def detail_to_row(record: dict[str, str]) -> dict:
    info_gb = blank_to_none(record.get("infogb"))
    if not info_gb:
        raise ValueError("상세정보 구분(infogb)이 없습니다.")
    return {"info_gb": info_gb, "contents": record.get("contents") or None}


def schedule_to_rows(record: dict[str, str]) -> tuple[list[dict], list[str]]:
    """일정 응답 한 행 → 단계별 행 목록과 경고. 날짜가 하나도 없는 단계는 만들지 않는다."""
    year, seq = blank_to_none(record.get("implYy")), blank_to_none(record.get("implSeq"))
    if not year or not re.fullmatch(r"\d{4}", year):
        raise ValueError(f"시행연도(implYy)가 올바르지 않습니다: {year!r}")
    if not seq or not re.fullmatch(r"\d{1,6}", seq):
        raise ValueError(f"회차(implSeq)가 올바르지 않습니다: {seq!r}")
    qualgb_cd = blank_to_none(record.get("qualgbCd"))
    if not qualgb_cd:
        raise ValueError("자격구분(qualgbCd)이 없습니다.")
    base = {
        "impl_year": int(year), "impl_seq": int(seq), "qualgb_cd": qualgb_cd,
        "qualgb_nm": blank_to_none(record.get("qualgbNm")),
        "description": blank_to_none(record.get("description")),
    }
    rows, warnings = [], []
    for phase, prefix in PHASE_PREFIXES.items():
        dates = {column: parse_api_date(record.get(prefix + suffix), prefix + suffix)
                 for column, suffix in PHASE_DATE_FIELDS.items()}
        if not any(dates.values()):
            continue
        # 공식 값은 고치지 않고 저장하되 이상 여부는 로그로 남긴다.
        for start, end in (("reg_start_date", "reg_end_date"), ("exam_start_date", "exam_end_date")):
            if dates[start] and dates[end] and dates[end] < dates[start]:
                warnings.append(f"{year}년 {seq}회 {phase}: {end}가 {start}보다 빠릅니다.")
        rows.append({**base, "exam_phase": phase, **dates})
    return rows, warnings


def schedules_to_rows(records: list[dict[str, str]]) -> tuple[list[dict], list[str]]:
    """같은 식별 키를 가진 단계 행은 하나로 합친다 (실기 날짜가 같은 접수 회차 행)."""
    merged: dict[tuple, dict] = {}
    warnings: list[str] = []
    for record in records:
        rows, row_warnings = schedule_to_rows(record)
        warnings.extend(row_warnings)
        for row in rows:
            key = tuple(row[field] for field in EXAM_KEY_FIELDS)
            previous = merged.get(key)
            if previous and any(previous[f] != row[f] for f in EXAM_VALUE_FIELDS):
                raise ValueError(f"같은 일정 식별값에 서로 다른 날짜가 반환됐습니다: {key}")
            merged[key] = row
    return list(merged.values()), warnings


def format_api_date(value: date | None) -> str | None:
    return value.strftime("%Y%m%d") if value else None


def rows_to_legacy_schedules(rows: list[dict]) -> list[dict]:
    """단계별 행을 기존 /api/schedules 응답(필기+실기 한 행) 형태로 되돌린다.

    API는 접수기간이 다른 필기 행마다 같은 실기 일정을 붙여 보내므로,
    같은 회차의 필기 행 각각에 실기 행을 결합하면 원래 응답과 같아진다.
    """
    rounds: dict[tuple, dict[str, list[dict]]] = {}
    for row in rows:
        key = (row["impl_year"], row["impl_seq"], row["qualgb_cd"], row["description"])
        rounds.setdefault(key, {"written": [], "practical": []})[row["exam_phase"]].append(row)

    def phase_fields(prefix: str, row: dict | None) -> dict:
        return {prefix + suffix: format_api_date(row[column]) if row else None
                for column, suffix in PHASE_DATE_FIELDS.items()}

    result = []
    for (year, seq, qualgb_cd, description), phases in rounds.items():
        sample = (phases["written"] or phases["practical"])[0]
        for written in phases["written"] or [None]:
            for practical in phases["practical"] or [None]:
                result.append({
                    "implYy": str(year), "implSeq": str(seq), "qualgbCd": qualgb_cd,
                    "qualgbNm": sample["qualgb_nm"], "description": description,
                    **phase_fields("doc", written), **phase_fields("prac", practical),
                })
    # 실응답과 같이 최근 회차·늦은 접수일 순으로 정렬
    result.sort(key=lambda r: (int(r["implYy"]), int(r["implSeq"]), r["docRegStartDt"] or ""),
                reverse=True)
    return result
