"""종목별 상세정보 및 연도별 시험일정. 공식 명세와 실응답 기준."""

import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html import unescape

import requests

from .collect_items import PROJECT_ROOT, load_api_key, redact_api_key, save_raw_response

# https://www.data.go.kr/data/15003003/openapi.do
DETAIL_URL = "http://openapi.q-net.or.kr/api/service/rest/InquiryInformationTradeNTQSVC/getList"
# https://www.data.go.kr/data/15074408/openapi.do
SCHEDULE_URL = "https://apis.data.go.kr/B490007/qualExamSchd/getQualExamSchdList"
MAX_ATTEMPTS = 3
CONNECTION_ERROR = "Failed to validate a newly established connection."


def validate_query(jmcd: str, year: str | None = None, category: str | None = None) -> None:
    if not re.fullmatch(r"[A-Za-z0-9]{4}", jmcd):
        raise ValueError("종목코드는 영문/숫자 4자리여야 합니다.")
    if year is not None and not re.fullmatch(r"[0-9]{4}", year):
        raise ValueError("조회 연도는 4자리 숫자여야 합니다.")
    if category is not None and category not in {"T", "S", "C", "W"}:
        raise ValueError("자격구분은 T, S, C, W 중 하나여야 합니다.")


def parse_response(content: bytes) -> tuple[ET.Element, list[dict[str, str]]]:
    if b"<!DOCTYPE" in content.upper() or b"<!ENTITY" in content.upper():
        raise ValueError("지원하지 않는 XML 선언입니다.")
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        raise ValueError("올바른 XML 응답이 아닙니다.") from None
    code = root.findtext("header/resultCode")
    if root.tag != "response" or code != "00":
        raise ValueError(f"업무 오류 {code or '미확인'}: {root.findtext('header/resultMsg') or '응답 원문 확인 필요'}")
    if root.find("body/items") is None:
        raise ValueError("응답의 종목 데이터 구조를 확인할 수 없습니다.")
    records = [{child.tag: (child.text or "").strip() for child in item}
               for item in root.findall("body/items/item")]
    return root, records


def fetch_page(url: str, params: dict, prefix: str, api_key: str, raw_files: list) -> dict:
    """일시적 연결 장애만 1초/2초 간격으로 재시도한다. 인증·명세 오류는 즉시 반환."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        status = None
        retryable = False
        diagnostic = ""
        try:
            with requests.get(url, params=params, timeout=(10, 20), allow_redirects=False) as response:
                status = response.status_code
                path = save_raw_response(response, prefix)
                raw_files.append(str(path.relative_to(PROJECT_ROOT)))
                diagnostic = redact_api_key(response.text, api_key)[:6000]
                retryable = status in {502, 503, 504}
                if not 200 <= status < 300:
                    raise ValueError(f"HTTP 오류 {status}")
                # 코드 99 전체를 재시도하지 않고, 실제로 관측한 연결 오류만 구분한다.
                if b"<!DOCTYPE" not in response.content.upper() and b"<!ENTITY" not in response.content.upper():
                    try:
                        envelope = ET.fromstring(response.content)
                        retryable = (envelope.findtext("header/resultCode") == "99" and
                                     (envelope.findtext("header/resultMsg") or "").strip() == CONNECTION_ERROR)
                    except ET.ParseError:
                        pass
                root, page = parse_response(response.content)
                return {"ok": True, "root": root, "page": page,
                        "http_status": status, "attempts": attempt}
        except (requests.RequestException, ValueError) as exc:
            if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
                retryable = True
            technical_error = redact_api_key(str(exc), api_key)
            if retryable and attempt < MAX_ATTEMPTS:
                time.sleep(attempt)
                continue
            message = (
                "제공기관 API의 일시적인 연결 장애로 정보를 확인하지 못했습니다. "
                f"총 {attempt}회 시도했습니다. 잠시 후 다시 조회해주세요. 정보가 없다는 뜻은 아닙니다."
                if retryable else "API 응답을 처리하지 못했습니다. 오류 상세를 확인해주세요."
            )
            return {"ok": False, "http_status": status, "attempts": attempt,
                    "retryable": retryable, "error": message,
                    "diagnostic": technical_error + "\n" + diagnostic}


def collect_info(jmcd: str, *, year: str | None = None, category: str | None = None) -> dict:
    """연도가 있으면 일정 전체 페이지, 없으면 종목 상세정보를 조회한다."""
    validate_query(jmcd, year, category)
    if year is not None and category is None:
        raise ValueError("일정 조회에는 자격구분이 필요합니다.")
    schedule = year is not None
    api_key = ""
    status = None
    raw_files = []
    records = []
    attempts = 0
    try:
        api_key = load_api_key()
        params = {"jmCd": jmcd, "serviceKey" if schedule else "ServiceKey": api_key}
        if schedule:
            # 실응답 오류 코드 930으로 확인한 페이지당 상한은 50건이다.
            params.update(implYy=year, qualgbCd=category, dataFormat="xml", numOfRows=50, pageNo=1)
        expected_total = None
        while True:
            prefix = f"certification_{'schedule' if schedule else 'details'}_{jmcd}"
            if schedule:
                prefix += f"_{year}_p{params['pageNo']}"
            result = fetch_page(SCHEDULE_URL if schedule else DETAIL_URL, params,
                                prefix, api_key, raw_files)
            status = result["http_status"]
            attempts += result["attempts"]
            if not result["ok"]:
                return {**result, "jmcd": jmcd, "raw_files": raw_files}
            root, page = result["root"], result["page"]
            if not schedule:
                for record in page:
                    if not record.get("infogb") or not record.get("jmfldnm"):
                        raise ValueError("상세정보 필수 필드가 누락됐습니다.")
                    # HTML로 실행하지 않고 프런트에서 textContent로 표시한다.
                    record["contents"] = unescape(record.get("contents", ""))
                records.extend(page)
                break
            total = int(root.findtext("body/totalCount", "-1"))
            page_no = int(root.findtext("body/pageNo", "0"))
            if total < 0 or page_no != params["pageNo"]:
                raise ValueError("일정의 페이지 메타데이터가 올바르지 않습니다.")
            if expected_total is not None and total != expected_total:
                raise ValueError("조회 중 일정 건수가 변경됐습니다. 다시 조회해주세요.")
            expected_total = total
            for record in page:
                if record.get("implYy") != year or record.get("qualgbCd") != category:
                    raise ValueError("요청한 연도/자격구분과 다른 일정이 반환됐습니다.")
            records.extend(page)
            if len(records) == total:
                break
            if not page or len(records) > total or params["pageNo"] >= 200:
                raise ValueError("전체 일정을 수집하지 못했습니다. 페이지 응답을 확인하세요.")
            params["pageNo"] += 1
        return {"ok": True, "http_status": status, "jmcd": jmcd, "year": year,
                "items": records, "raw_files": raw_files,
                "empty": not records, "attempts": attempts,
                "fetched_at": datetime.now(timezone.utc).isoformat()}
    except (requests.RequestException, ValueError, OSError) as exc:
        message = redact_api_key(str(exc), api_key) if api_key else str(exc)
        return {"ok": False, "http_status": status, "jmcd": jmcd,
                "error": message, "raw_files": raw_files}
