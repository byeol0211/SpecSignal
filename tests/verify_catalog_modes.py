"""실제 API 호출 없이 Edge에서 화면 검증: python tests/verify_ui.py."""

import json
import sys
import threading
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playwright.sync_api import sync_playwright, expect
from src.web.server import Handler, ThreadingHTTPServer


def main():
    # 화면 테스트 전용 데이터. 앱 코드에는 샘플 데이터를 넣지 않는다.
    names = ["정보처리기사", "전기기사", "건축기사", "산업안전기사", "사회조사분석사2급", "정보처리산업기사", "한식조리기능사", "직업상담사2급", "가스기사"]
    items = [{"jmcd": f"{1320+i:04}", "jmfldnm": name, "qualgbcd": "T", "qualgbnm": "국가기술자격", "seriesnm": "기사" if i < 4 else "기능·서비스", "obligfldnm": "정보통신" if i in (0, 5) else "전문분야", "mdobligfldnm": "정보기술" if i in (0, 5) else "관련 직무"} for i, name in enumerate(names)]
    listing = {"ok": True, "items": items, "http_status": 200, "fetched_at": "2026-09-24T00:00:00Z"}
    mode = {"details": "success", "list": "success"}

    def mock_items():
        return listing if mode["list"] == "success" else {"ok": False, "http_status": 503, "error": "테스트 연결 실패"}

    def mock_info(jmcd, *, year=None, category=None):
        if year:
            data = [] if year == "2027" else [{"implYy": year, "implSeq": "1", "qualgbCd": category, "description": f"국가기술자격 기사 ({year}년도 제1회)", "docRegStartDt": "20260112", "docRegEndDt": "20260115", "docExamStartDt": "20260130", "docExamEndDt": "20260303", "docPassDt": "20260311"}]
        elif mode["details"] == "error":
            return {"ok": False, "http_status": 200, "error": "제공기관 API의 일시적인 연결 장애입니다.", "diagnostic": "test failure"}
        elif mode["details"] == "empty":
            data = []
        else:
            data = [{"infogb": "취득방법", "contents": "시행처: 한국산업인력공단\n필기 및 실기 시험 정보를 확인하세요."}, {"infogb": "출제기준", "contents": "공식 출제기준을 확인하세요.\n<script>window.untrusted = true</script>"}]
        return {"ok": True, "http_status": 200, "items": data}

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    output = Path("artifacts/ui")
    output.mkdir(parents=True, exist_ok=True)
    try:
        with patch("src.web.server.collect_items", side_effect=mock_items) as calls, patch("src.web.server.collect_info", side_effect=mock_info), sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 960}, device_scale_factor=1)
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{server.server_port}/#cert")
            expect(page.locator('.card')).to_have_count(8)
            assert calls.call_count == 1, "목록은 시작 시 자동으로 한 번 조회해야 함"
            assets = page.locator('img').evaluate_all("nodes => nodes.map(n => ({src:n.getAttribute('src'),w:n.getBoundingClientRect().width,h:n.getBoundingClientRect().height,nw:n.naturalWidth,nh:n.naturalHeight,loaded:n.complete}))")
            for asset in assets:
                assert asset['loaded'] and asset['nw'] > 0
                assert (asset['w'], asset['h']) == (asset['nw'], asset['nh']), asset
            (output / "asset-geometry.json").write_text(json.dumps(assets, indent=2), encoding="utf-8")
            page.screenshot(path=str(output / "catalog.png"))
            page.get_by_role('button', name='더 보기', exact=True).click()
            expect(page.locator('.card')).to_have_count(9)
            page.keyboard.press('Control+k')
            expect(page.locator('#search')).to_be_focused()
            page.locator('#search').fill('정보처리')
            expect(page.locator('.card')).to_have_count(2)
            page.locator('#search').fill('존재하지않는종목')
            expect(page.locator('#empty')).to_be_visible()
            page.locator('#search').fill('')
            page.locator('#field').select_option('정보통신')
            expect(page.locator('.card')).to_have_count(2)
            page.locator('.info-button').first.click()
            expect(page.locator('.qualification-detail')).to_have_count(2)
            expect(page.locator('.schedule-card')).to_have_count(1)
            assert page.evaluate('window.untrusted === undefined')
            page.screenshot(path=str(output / "details.png"))
            page.locator('#year').fill('2027')
            page.locator('#schedule-form button').click()
            expect(page.locator('#schedule-content')).to_contain_text('반환한 일정이 없습니다')
            page.keyboard.press('Escape')
            expect(page.locator('#info-dialog')).not_to_be_visible()
            mode['details'] = 'error'
            page.locator('.info-button').first.click()
            expect(page.locator('#details-content')).to_contain_text('일시적인 연결 장애')
            mode['details'] = 'empty'
            page.locator('#details-content').get_by_role('button', name='다시 조회').click()
            expect(page.locator('#details-content')).to_contain_text('관련 정보가 없습니다')
            page.locator('#close-info').click()
            page.locator('#mode-personal').click()
            expect(page.locator('.card')).to_have_count(2)
            expect(page.locator('#mode-personal')).to_have_attribute('aria-pressed', 'true')
            page.locator('#mode-all').click()
            expect(page.locator('.card')).to_have_count(8)
            page.locator('#more').click()
            expect(page.locator('.card')).to_have_count(9)
            page.locator('#navigation [data-page="profile"]').click()
            page.locator('[name="major"]').fill('전기공학')
            page.locator('[name="role"]').fill('전기 기술자')
            page.locator('[name="interest"]').select_option('디자인')
            page.get_by_role('button', name='변경사항 저장').click()
            page.locator('#navigation [data-page="cert"]').click()
            expect(page.locator('.card')).to_have_count(8)
            expect(page.locator('#mode-all')).to_have_attribute('aria-pressed', 'true')
            page.locator('#mode-personal').click()
            expect(page.locator('.card')).to_have_count(1)
            expect(page.locator('.card')).to_contain_text('전기기사')
            page.locator('#search').fill('없는종목')
            expect(page.locator('#empty')).to_be_visible()
            page.locator('#mode-all').click()
            expect(page.locator('.card')).to_have_count(8)
            page.screenshot(path=str(output / 'catalog-all-mode.png'))
            for width in (1440,1100,820):
                page.set_viewport_size({'width':width,'height':960})
                assert page.locator('.main-content').evaluate('(n) => n.scrollWidth <= n.clientWidth')
            mode['list'] = 'error'
            page.locator('#reload').click()
            expect(page.locator('#result-summary')).to_contain_text('갱신 실패')
            expect(page.locator('.card')).to_have_count(8)
            page.reload()
            expect(page.locator('#error-panel')).to_be_visible()
            expect(page.locator('.card')).to_have_count(0)
            mode['list'] = 'success'
            page.locator('#reload').click()
            expect(page.locator('.card')).to_have_count(8)
            assert not errors, errors
            browser.close()
            print('PASS: all/personal modes, profile independence, API list/detail/schedule, filters, pagination, retries, responsive layout')
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == '__main__':
    main()

