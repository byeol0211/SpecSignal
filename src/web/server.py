"""로컬 API 확인 페이지. 프로젝트 루트에서 python -m src.web.server 실행."""

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from src.certification.collect_items import collect_items
from src.certification.collect_info import collect_info


WEB_DIR = Path(__file__).resolve().parent
# 정해진 파일만 제공하여 .env 및 원문 데이터 접근을 막는다.
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/certifications.js": ("certifications.js", "text/javascript; charset=utf-8"),
    "/catalog-live": ("catalog-legacy.html", "text/html; charset=utf-8"),
    "/catalog-legacy.js": ("catalog-legacy.js", "text/javascript; charset=utf-8"),
    "/catalog-legacy.css": ("catalog-legacy.css", "text/css; charset=utf-8"),
}
for asset in (WEB_DIR / "assets").glob("*.svg"):
    STATIC_FILES[f"/assets/{asset.name}"] = (f"assets/{asset.name}", "image/svg+xml")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/items":
            result = collect_items()
            body = json.dumps(result, ensure_ascii=False).encode("utf-8")
            self.respond(200 if result["ok"] else 502, body, "application/json; charset=utf-8")
        elif path in {"/api/details", "/api/schedules"}:
            query = parse_qs(urlsplit(self.path).query)
            try:
                jmcd = query.get("jmcd", [""])[0]
                if path == "/api/schedules":
                    result = collect_info(jmcd, year=query.get("year", [""])[0],
                                          category=query.get("category", [""])[0])
                else:
                    result = collect_info(jmcd)
                status = 200 if result["ok"] else 502
            except ValueError as exc:
                result = {"ok": False, "error": str(exc), "http_status": None}
                status = 400
            self.respond(status, json.dumps(result, ensure_ascii=False).encode("utf-8"),
                         "application/json; charset=utf-8")
        elif path in STATIC_FILES:
            filename, content_type = STATIC_FILES[path]
            self.respond(200, (WEB_DIR / filename).read_bytes(), content_type)
        else:
            self.respond(404, b"Not found", "text/plain; charset=utf-8")

    def respond(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        policy = "default-src 'self'; base-uri 'none'; frame-ancestors 'none'"
        # pywebview는 JS↔Python 메서드를 new Function으로 생성한다.
        # 브리지 허용은 데스크톱 전용 서버에만 적용한다.
        if getattr(self.server, "desktop_bridge", False):
            policy += "; script-src 'self' 'unsafe-eval'"
        self.send_header("Content-Security-Policy", policy)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            # 응답 중 앱 창을 닫은 경우 연결 종료를 정상 처리한다.
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="SpecSignal 자격증 목록 확인 페이지")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    with ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as server:
        print(f"SpecSignal: http://127.0.0.1:{args.port} (종료: Ctrl+C)", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
