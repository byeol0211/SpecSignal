"""한국산업인력공단 국가자격 종목 목록 API 수집."""

import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, quote_plus, unquote

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw"

# 공식 명세: https://www.data.go.kr/data/15003024/openapi.do
API_ENDPOINT = "http://openapi.q-net.or.kr/api/service/rest/InquiryListNationalQualifcationSVC"
API_OPERATION_PATH = "getList"
API_HTTP_METHOD = "GET"
API_KEY_PARAM = "serviceKey"
API_KEY_LOCATION = "query"
# 공식 요청변수는 serviceKey 한 개이며 페이지 변수가 없다.
API_PARAMS: dict = {}


def validate_api_spec() -> None:
    """불완전한 설정으로 실제 요청을 보내지 않는다."""
    required = {
        "API_ENDPOINT": API_ENDPOINT,
        "API_OPERATION_PATH": API_OPERATION_PATH,
        "API_HTTP_METHOD": API_HTTP_METHOD,
        "API_KEY_PARAM": API_KEY_PARAM,
        "API_KEY_LOCATION": API_KEY_LOCATION,
    }
    missing = [name for name, value in required.items() if not value.strip()]
    if API_PARAMS is None:
        missing.append("API_PARAMS")
    if missing:
        raise ValueError("API 명세 TODO를 입력하세요: " + ", ".join(missing))
    if API_KEY_LOCATION not in {"query", "header"}:
        raise ValueError("키 전달 위치를 확인하세요. 현재 지원: query, header")
    # 다른 요청 본문 방식이 필요하면 명세 확인 후 구현한다.


def load_api_key() -> str:
    """실행 위치와 관계없이 프로젝트 루트의 .env를 읽는다."""
    load_dotenv(PROJECT_ROOT / ".env", encoding="utf-8-sig")
    api_key = os.getenv("DATA_GO_KR_API_KEY", "").strip()
    if not api_key:
        raise ValueError(".env에 DATA_GO_KR_API_KEY를 설정하세요.")
    # requests의 params가 인코딩하므로 인코딩된 키도 한 번 복원한다.
    return unquote(api_key)


def redact_api_key(text: str, api_key: str) -> str:
    """오류 응답에 인증키가 포함되면 화면에서 가린다."""
    for secret in {api_key, quote(api_key, safe=""), quote_plus(api_key)}:
        text = text.replace(secret, "[REDACTED]")
    return text


def request_items(api_key: str) -> requests.Response:
    """설정된 요청 한 건을 수행한다. HTTP 오류 응답도 저장용으로 반환한다."""
    validate_api_spec()
    url = API_ENDPOINT.rstrip("/") + "/" + API_OPERATION_PATH.lstrip("/")
    params = dict(API_PARAMS)
    headers = {}
    if API_KEY_LOCATION == "query":
        params[API_KEY_PARAM] = api_key
    else:
        headers[API_KEY_PARAM] = api_key
    try:
        return requests.request(
            method=API_HTTP_METHOD,
            url=url,
            params=params,
            headers=headers,
            timeout=(10, 60),
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        # 예외 문자열에는 인증키가 포함된 요청 URL이 들어갈 수 있다.
        raise RuntimeError(
            f"API 요청 실패 ({type(exc).__name__}, HTTP 상태코드 없음): "
            + redact_api_key(str(exc), api_key)
        ) from None


def save_raw_response(response: requests.Response, prefix: str = "certification_items") -> Path:
    """형식을 추측하지 않고 성공/오류 응답의 본문을 바이트 그대로 저장한다."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    path = RAW_DIR / f"{prefix}_{stamp}_http{response.status_code}.bin"
    path.write_bytes(response.content)
    return path


def parse_items(content: bytes) -> list[dict[str, str]]:
    """공식 출력 필드와 실제 응답에서 확인한 XML 경로로 파싱한다."""
    if b"<!DOCTYPE" in content.upper() or b"<!ENTITY" in content.upper():
        raise ValueError("지원하지 않는 XML 선언이 포함되어 있습니다.")
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        raise ValueError("API가 올바른 XML 응답을 반환하지 않았습니다.") from None
    # 실호출 확인: response/header/resultCode=00, body/items/item.
    result_code = root.findtext("header/resultCode")
    if root.tag != "response" or result_code != "00":
        raise ValueError("API 업무 성공을 확인하지 못했습니다. 아래 오류 응답을 확인하세요.")
    fields = (
        "qualgbcd", "qualgbnm", "seriescd", "seriesnm", "jmcd",
        "jmfldnm", "obligfldcd", "obligfldnm", "mdobligfldcd", "mdobligfldnm",
    )
    items = []
    for node in root.findall("body/items/item"):
        values = {child.tag.rsplit("}", 1)[-1]: (child.text or "").strip()
                  for child in node}
        if not values.get("jmcd") or not values.get("jmfldnm"):
            raise ValueError("종목코드 또는 종목명이 누락된 응답입니다.")
        items.append({field: values.get(field, "") for field in fields})
    if not items:
        # 오류 응답을 빈 목록 성공으로 취급하지 않는다.
        raise ValueError("응답에 종목 목록이 없습니다. 아래 원문의 인증/업무 오류를 확인하세요.")
    return sorted(items, key=lambda item: (item["jmfldnm"], item["jmcd"]))


def collect_items() -> dict:
    """CLI와 웹에서 같은 수집 로직을 사용한다."""
    api_key = ""
    http_status = None
    try:
        api_key = load_api_key()
        with request_items(api_key) as response:
            http_status = response.status_code
            raw_path = save_raw_response(response)
            error = None
            if not 200 <= http_status < 300:
                error = f"API 요청 실패: HTTP {http_status}"
            else:
                try:
                    items = parse_items(response.content)
                except ValueError as exc:
                    error = str(exc)
            if error:
                return {
                    "ok": False, "http_status": http_status,
                    "error": error + "\n" + redact_api_key(response.text, api_key)[:6000],
                    "raw_file": str(raw_path.relative_to(PROJECT_ROOT)),
                }
            return {
                "ok": True, "http_status": http_status, "items": items,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "raw_file": str(raw_path.relative_to(PROJECT_ROOT)),
            }
    except (ValueError, RuntimeError, OSError) as exc:
        message = redact_api_key(str(exc), api_key) if api_key else str(exc)
        return {"ok": False, "http_status": http_status, "error": message}


def main() -> int:
    result = collect_items()
    print(f"HTTP 상태코드: {result['http_status']}")
    if "raw_file" in result:
        print(f"응답 원문 저장: {result['raw_file']}")
    if not result["ok"]:
        print(f"수집 실패: {result['error']}", file=sys.stderr)
        return 1
    print(f"국가자격 종목 {len(result['items'])}개 수집 완료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
