"""실제 Windows 창/WebView2/실 API 통합 확인. 검증 완료 시 창을 닫는다."""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import webview
from playwright.sync_api import sync_playwright, expect
from src import desktop


def main():
    original_start = webview.start
    failures = []
    output = Path('artifacts/ui')
    output.mkdir(parents=True, exist_ok=True)

    def verify():
        try:
            with sync_playwright() as p:
                deadline = time.monotonic() + 40
                while True:
                    try:
                        browser = p.chromium.connect_over_cdp('http://127.0.0.1:9225', timeout=1500)
                        break
                    except Exception:
                        if time.monotonic() > deadline:
                            raise
                        time.sleep(.5)
                page = browser.contexts[0].pages[0]
                page.wait_for_function('window.pywebview && window.pywebview.api', timeout=40000)
                expect(page.locator('#window-controls')).to_be_visible(timeout=10000)
                expect(page.locator('.day')).to_have_count(42)
                page.screenshot(path=str(output / 'native-dashboard.png'))
                # 기존 실 API 회귀 검증은 보존된 전용 화면에서 실행한다.
                page.goto(page.url.split('#')[0].rstrip('/') + '/catalog-live')
                page.wait_for_function('window.pywebview && window.pywebview.api', timeout=40000)
                expect(page.locator('.card')).to_have_count(8, timeout=90000)
                page.screenshot(path=str(output / 'native-catalog.png'))
                data = {'cards': page.locator('.card').count(), 'status': page.locator('#status').inner_text(), 'bridge': True}
                window = webview.windows[0]
                initial_width = page.evaluate('innerWidth')
                page.locator('#window-maximize').click()
                page.wait_for_function('(w) => innerWidth !== w', arg=initial_width)
                page.locator('#window-maximize').click()
                page.wait_for_function('(w) => innerWidth === w', arg=initial_width)
                data['maximize_restore'] = True
                old_x, old_y = window.x, window.y
                page.mouse.move(300, 20)
                page.mouse.down()
                page.mouse.move(340, 50, steps=10)
                page.mouse.up()
                time.sleep(.3)
                data['drag'] = (window.x, window.y) != (old_x, old_y)
                assert data['drag'], '타이틀바 드래그로 창이 이동하지 않음'
                page.locator('#window-minimize').click()
                time.sleep(.4)
                window.restore()
                data['minimize_restore'] = True
                # 실제 모서리를 드래그하여 네이티브 창 크기가 바뀌는지 확인한다.
                for edge in ('se', 'e', 's', 'nw'):
                    before = page.evaluate('({width: innerWidth, height: innerHeight})')
                    rect = page.locator(f'.resize-{edge}').bounding_box()
                    x, y = rect['x'] + rect['width']/2, rect['y'] + rect['height']/2
                    page.mouse.move(x, y)
                    page.mouse.down()
                    page.mouse.move(x + (-40 if 'e' in edge else 40 if 'w' in edge else 0), y + (-30 if 's' in edge else 30 if 'n' in edge else 0), steps=8)
                    page.mouse.up()
                    page.wait_for_function('(s) => innerWidth !== s.width || innerHeight !== s.height', arg=before)
                data['edge_resize'] = True
                page.evaluate("window.pywebview.api.resize_window(100, 100, 'se')")
                page.wait_for_function('innerWidth >= 820 && innerWidth <= 822 && innerHeight >= 620 && innerHeight <= 622')
                data['minimum_size'] = True
                page.evaluate("window.pywebview.api.resize_window(1440, 900, 'se')")
                page.locator('#search').fill('정보처리기사')
                expect(page.locator('.card')).to_have_count(1)
                page.locator('.info-button').click()
                expect(page.locator('.qualification-detail')).to_have_count(3, timeout=90000)
                expect(page.locator('.schedule-card').first).to_be_visible(timeout=90000)
                page.screenshot(path=str(output / 'native-details.png'))
                data['details'] = page.locator('.qualification-detail').count()
                data['schedules'] = page.locator('.schedule-card').count()
                (output / 'native-check.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
                page.locator('#close-info').click()
                # 닫기 버튼은 실제 Python bridge를 통해 창을 종료한다.
                page.locator('#window-close').click()
                print('Native desktop checks passed:', json.dumps(data, ensure_ascii=True), flush=True)
        except Exception as exc:
            failures.append(str(exc))
            print('Native verification failed:', str(exc), flush=True)
            webview.windows[0].destroy()

    def start(**kwargs):
        webview.settings['REMOTE_DEBUGGING_PORT'] = 9225
        return original_start(func=verify, **kwargs)

    webview.start = start
    sys.argv = ['desktop']
    desktop.main()
    if failures:
        raise RuntimeError(failures[0])


if __name__ == '__main__':
    main()
