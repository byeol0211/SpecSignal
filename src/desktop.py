"""SpecSignal 데스크톱 실행: python -m src.desktop."""

import argparse
import json
import threading

import webview
from webview.window import FixPoint

from src.certification.collect_items import PROJECT_ROOT
from src.web.server import Handler, ThreadingHTTPServer


PROFILE_PATH = PROJECT_ROOT / "data" / "local" / "profile.json"
MIN_SIZE = (820, 620)


class DesktopApi:
    """화면에 필요한 창 제어와 로컬 프로필 기능만 노출한다."""

    def __init__(self):
        self._window = None
        self._maximized = False

    def minimize(self):
        self._window.minimize()

    def toggle_maximize(self):
        if self._maximized:
            self._window.restore()
        else:
            self._window.maximize()
        self._maximized = not self._maximized

    def close(self):
        self._window.destroy()

    def resize_window(self, width, height, edge):
        """잡은 가장자리의 반대쪽을 고정하고 최소 크기를 보장한다."""
        if edge not in {"n", "s", "e", "w", "ne", "nw", "se", "sw"}:
            raise ValueError("잘못된 크기 조절 방향입니다.")
        if self._maximized:
            return
        width = max(MIN_SIZE[0], min(10000, int(width)))
        height = max(MIN_SIZE[1], min(10000, int(height)))
        anchor = (FixPoint.EAST if "w" in edge else FixPoint.WEST)
        anchor |= FixPoint.SOUTH if "n" in edge else FixPoint.NORTH
        self._window.resize(width, height, fix_point=anchor)

    def get_profile(self):
        try:
            data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
            name = data.get("name", "")
            return {"name": name[:20] if isinstance(name, str) else ""}
        except (OSError, ValueError, AttributeError):
            return {"name": ""}

    def save_profile(self, name):
        if not isinstance(name, str) or len(name) > 20:
            raise ValueError("이름은 20자 이내로 입력해주세요.")
        PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        PROFILE_PATH.write_text(json.dumps({"name": name.strip()}, ensure_ascii=False), encoding="utf-8")
        return {"ok": True}


def main():
    parser = argparse.ArgumentParser(description="SpecSignal 데스크톱 앱")
    parser.add_argument("--debug", action="store_true", help="개발자 도구 활성화")
    args = parser.parse_args()
    # 빈 포트를 할당하므로 실행 중인 개발용 웹 서버와 충돌하지 않는다.
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.desktop_bridge = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    bridge = DesktopApi()
    try:
        bridge._window = webview.create_window(
            "SpecSignal", f"http://127.0.0.1:{server.server_port}", js_api=bridge,
            width=1440, height=960, min_size=MIN_SIZE, resizable=True,
            frameless=True, easy_drag=False, shadow=True,
            background_color="#94A5CF", text_select=True,
        )
        webview.settings["ALLOW_FILE_URLS"] = False
        webview.start(gui="edgechromium", debug=args.debug, private_mode=True)
    finally:
        # 창을 닫으면 로컬 서버도 함께 종료한다.
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


if __name__ == "__main__":
    main()
