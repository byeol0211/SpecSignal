"""Verify responsive navigation, layouts and mobile user flows in Edge."""
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
    listing = {'ok': True, 'items': [{'jmcd': '1320', 'jmfldnm': '정보처리기사', 'qualgbcd': 'T', 'qualgbnm': '국가기술자격', 'obligfldnm': '정보통신', 'mdobligfldnm': '정보기술'}]}
    output = Path('artifacts/ui')
    output.mkdir(parents=True, exist_ok=True)
    try:
        with patch('src.web.server.collect_items', return_value=listing), sync_playwright() as p:
            browser = p.chromium.launch(channel='msedge', headless=True)
            page = browser.new_page(viewport={'width': 390, 'height': 844}, has_touch=True)
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}')

            def fits():
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), page.url
                assert page.locator('.main-content').evaluate('(n) => n.scrollWidth <= n.clientWidth'), page.url

            for width in (320, 390, 620, 760, 820, 1100, 1440):
                page.set_viewport_size({'width': width, 'height': 844})
                for route in ('home', 'ai', 'favorites', 'cert', 'contest', 'profile'):
                    if width <= 760:
                        expect(page.locator('#sidebar')).not_to_be_visible()
                        page.locator('#menu-toggle').click()
                        expect(page.locator('#menu-toggle')).to_have_attribute('aria-expanded', 'true')
                    page.locator(f'#navigation [data-page="{route}"]').click()
                    if route == 'cert':
                        expect(page.locator('.live-cards .card')).to_have_count(1)
                    if width <= 760:
                        expect(page.locator('#sidebar')).not_to_be_visible()
                    fits()
                page.screenshot(path=str(output / f'web-profile-{width}.png'), full_page=True)

            page.locator('#menu-toggle').click()
            expect(page.locator('#menu-toggle')).to_have_attribute('aria-expanded', 'false')
            expect(page.locator('#sidebar')).to_have_css('width', '76px')
            page.locator('#navigation').get_by_role('button', name='홈', exact=True).click()
            page.reload()
            expect(page.locator('#sidebar')).to_have_css('width', '76px')
            fits()
            page.screenshot(path=str(output / 'web-sidebar-collapsed.png'))
            page.set_viewport_size({'width': 390, 'height': 844})
            expect(page.locator('#sidebar')).not_to_be_visible()
            page.locator('#menu-toggle').click()
            expect(page.locator('#navigation [data-page="profile"] span')).to_be_visible()
            page.set_viewport_size({'width': 1440, 'height': 844})
            expect(page.locator('#sidebar')).to_have_css('width', '76px')
            page.locator('#menu-toggle').click()
            expect(page.locator('#menu-toggle')).to_have_attribute('aria-expanded', 'true')
            expect(page.locator('#sidebar')).to_have_css('width', '240px')
            page.set_viewport_size({'width': 320, 'height': 740})
            page.locator('#menu-toggle').click()
            page.keyboard.press('Escape')
            expect(page.locator('#menu-toggle')).to_be_focused()
            expect(page.locator('#sidebar')).not_to_be_visible()
            page.locator('#menu-toggle').click()
            page.locator('#navigation [data-page="home"]').click()
            page.locator('[data-action="new-event"]').first.click()
            page.locator('[name="title"]').fill('모바일에서 등록한 일정')
            page.get_by_role('button', name='일정 저장', exact=True).click()
            expect(page.locator('.note')).to_have_count(1)
            fits()
            page.reload()
            expect(page.locator('.note')).to_have_count(1)
            page.locator('#notifications-button').click()
            fits()
            page.screenshot(path=str(output / 'web-mobile-home.png'), full_page=True)
            page.locator('#menu-toggle').click()
            page.locator('#navigation [data-page="ai"]').click()
            page.locator('[data-action="prompt"]').first.click()
            page.locator('.messages [data-action="add-item"]').first.click()
            expect(page.locator('#modal')).to_be_visible()
            assert page.locator('#modal').evaluate('(n) => n.scrollWidth <= n.clientWidth')
            page.screenshot(path=str(output / 'web-mobile-dialog.png'))
            page.get_by_role('button', name='선택한 일정 저장').click()
            expect(page.locator('#modal')).not_to_be_visible()
            fits()
            assert not errors, errors
            browser.close()
            print('PASS: 7 widths, 6 pages, mobile navigation, schedule persistence and dialog')
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == '__main__':
    main()
