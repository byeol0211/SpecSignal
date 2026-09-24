"""데모 대시보드의 주요 사용자 흐름을 실제 Edge에서 검증한다."""
import sys
import threading
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright, expect
from src.web.server import Handler, ThreadingHTTPServer


def main():
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    output = Path('artifacts/ui')
    output.mkdir(parents=True, exist_ok=True)
    try:
        with patch('src.web.server.collect_items', return_value={'ok': True, 'items': [], 'fetched_at': '2026-09-24T00:00:00Z'}) as api, sync_playwright() as p:
            browser = p.chromium.launch(channel='msedge', headless=True)
            page = browser.new_page(viewport={'width':1440, 'height':960})
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(f'http://127.0.0.1:{server.server_port}')
            expect(page.locator('.day')).to_have_count(42)
            expect(page.locator('.note')).to_have_count(0)
            page.locator('[data-page="ai"]').click()
            page.locator('[data-action="prompt"]').first.click()
            page.locator('[data-item="cert-sql"] [data-action="favorite"]').click()
            page.locator('[data-page="home"]').first.click()
            expect(page.locator('.note')).to_have_count(0)
            page.locator('[data-page="favorites"]').click()
            expect(page.locator('.card')).to_have_count(1)
            page.locator('[data-action="add-item"]').click()
            expect(page.locator('[name="pick-deadline"]')).to_be_checked()
            expect(page.locator('[name="pick-exam"]')).to_be_checked()
            expect(page.locator('[name="pick-start"]')).not_to_be_checked()
            page.locator('[name="pick-exam"]').uncheck()
            page.locator('[name="pick-deadline"]').uncheck()
            page.get_by_role('button', name='선택한 일정 저장').click()
            expect(page.locator('#form-error')).to_contain_text('하나 이상')
            page.locator('[name="pick-deadline"]').check()
            date = page.evaluate('new Date().toLocaleDateString("en-CA")')
            page.locator('[name="date-deadline"]').fill(date)
            page.get_by_role('button', name='선택한 일정 저장').click()
            page.locator('[data-page="home"]').first.click()
            expect(page.locator('.note')).to_have_count(1)
            page.locator('#notifications-button').click()
            expect(page.locator('[data-action="notification-event"]')).to_have_count(1)
            page.locator('[data-action="notification-event"]').click()
            expect(page.locator('.selected-events')).to_contain_text('SQL')
            page.locator('.note [data-action="edit-event"]').click()
            page.locator('[name="title"]').fill('나의 SQL 접수 마감')
            page.get_by_role('button', name='일정 저장', exact=True).click()
            expect(page.locator('.note')).to_contain_text('나의 SQL')
            page.reload()
            expect(page.locator('.note')).to_have_count(1)
            page.locator('[data-page="profile"]').click()
            page.locator('[name="name"]').fill('박 미래')
            page.locator('[name="school"]').fill('테스트대학교')
            page.locator('[name="major"]').fill('컴퓨터공학')
            page.locator('[name="hours"]').fill('3')
            page.locator('[name="period"]').select_option('최대')
            page.get_by_role('button', name='변경사항 저장').click()
            page.locator('[data-action="academic-search"]').click()
            page.locator('#academic-form [name="date"]').fill(date)
            page.get_by_role('button', name='확인한 일정 등록').click()
            page.locator('[data-page="ai"]').click()
            page.locator('[data-action="prompt"]').first.click()
            expect(page.locator('.messages .card')).to_have_count(4)
            expect(page.locator('.messages')).to_contain_text('학교 일정 1개')
            page.screenshot(path=str(output/'dashboard-ai.png'))
            page.locator('#chat-message').fill('1일 안에 준비할 공모전')
            page.get_by_role('button', name='보내기').click()
            expect(page.locator('.messages')).to_contain_text('맞는 예시 항목이 없어요')
            page.locator('[data-page="home"]').first.click()
            expect(page.locator('.note')).to_have_count(2)
            page.screenshot(path=str(output/'dashboard-home.png'))
            page.locator('[data-action="new-event"]').first.click()
            page.locator('[name="title"]').fill('<img src=x onerror=alert(1)>')
            page.get_by_role('button', name='일정 저장', exact=True).click()
            expect(page.locator('.note')).to_have_count(3)
            assert page.locator('.note img').count() == 0
            page.locator('.note [data-action="delete-event"]').last.click()
            page.locator('[data-action="confirm-delete"]').click()
            expect(page.locator('.note')).to_have_count(2)
            for width in (1440,1100,820):
                page.set_viewport_size({'width':width,'height':960})
                for route in ('home','ai','favorites','cert','contest','profile'):
                    page.locator(f'#navigation [data-page="{route}"]').click()
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (width,route)
                    assert page.locator('.main-content').evaluate('(n) => n.scrollWidth <= n.clientWidth'), (width,route)
                page.screenshot(path=str(output/f'dashboard-profile-{width}.png'))
            assets = page.locator('img').evaluate_all('nodes => nodes.map(n => ({src:n.src,w:n.width,h:n.height,nw:n.naturalWidth,nh:n.naturalHeight}))')
            assert all(a['nw'] and a['w']==a['nw'] and a['h']==a['nh'] for a in assets), assets
            assert not errors, errors
            assert api.call_count == 3, '자격증 탐색에 진입한 경우에만 공식 목록 조회'
            browser.close()
            print('PASS: dashboard flows, persistence, notifications, escaping, 3 viewport sizes')
    finally:
        server.shutdown()
        server.server_close()
        thread.join()

if __name__ == '__main__':
    main()
