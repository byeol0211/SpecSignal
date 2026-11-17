"""Official certification API queries; no database or scheduled sync required."""

from collections import OrderedDict
from copy import deepcopy
from threading import Lock
from time import monotonic

from src.certification.collect_items import collect_items
from src.certification.collect_info import collect_info, validate_query

CACHE_TTL = 300
CACHE_LIMIT = 256
_cache = OrderedDict()
_lock = Lock()


def clear_cache():
    with _lock:
        _cache.clear()


def _query(key, fetch):
    with _lock:
        cached = _cache.get(key)
        if cached and monotonic() < cached[0]:
            _cache.move_to_end(key)
            return {**deepcopy(cached[1]), "cached": True}
    result = fetch()
    # Do not expose raw upstream responses, diagnostics or server file paths.
    if not result["ok"]:
        return {"ok": False, "source": "official_api", "http_status": result.get("http_status"),
                "error": "공식 API에서 정보를 불러오지 못했습니다. 잠시 후 다시 시도해주세요."}
    response = {"ok": True, "source": "official_api", "items": result["items"],
                "empty": not result["items"], "fetched_at": result.get("fetched_at"), "cached": False}
    with _lock:
        _cache[key] = (monotonic() + CACHE_TTL, deepcopy(response))
        _cache.move_to_end(key)
        while len(_cache) > CACHE_LIMIT:
            _cache.popitem(last=False)
    return response


def load_items():
    return _query(("items",), collect_items)


def load_info(jmcd, *, year=None, category=None):
    validate_query(jmcd, year, category)
    if year is not None and category is None:
        raise ValueError("일정 조회에는 자격구분이 필요합니다.")
    return _query(("info", jmcd, year, category),
                  lambda: collect_info(jmcd, year=year, category=category))
