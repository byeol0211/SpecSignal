import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src import desktop


class DesktopTests(unittest.TestCase):
    def test_resize_minimum_and_opposite_anchor(self):
        bridge = desktop.DesktopApi()
        bridge._window = MagicMock()
        bridge.resize_window(100, 200, 'nw')
        bridge._window.resize.assert_called_once_with(820, 620, fix_point=desktop.FixPoint.EAST | desktop.FixPoint.SOUTH)
        with self.assertRaises(ValueError):
            bridge.resize_window(1000, 700, 'invalid')
        bridge._maximized = True
        bridge.resize_window(1000, 700, 'se')
        self.assertEqual(bridge._window.resize.call_count, 1)

    def test_profile_persists_and_recovers_from_invalid_file(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(desktop, 'PROFILE_PATH', Path(folder) / 'local/profile.json'):
            bridge = desktop.DesktopApi()
            self.assertEqual(bridge.get_profile(), {'name': ''})
            bridge.save_profile('  미래  ')
            self.assertEqual(desktop.DesktopApi().get_profile(), {'name': '미래'})
            with self.assertRaises(ValueError):
                bridge.save_profile('a' * 21)
            desktop.PROFILE_PATH.write_text('broken json', encoding='utf-8')
            self.assertEqual(bridge.get_profile(), {'name': ''})

    def test_window_controls_and_restore(self):
        bridge = desktop.DesktopApi()
        bridge._window = MagicMock()
        bridge.minimize()
        bridge.toggle_maximize()
        bridge.toggle_maximize()
        bridge.close()
        for method in ('minimize', 'maximize', 'restore', 'destroy'):
            getattr(bridge._window, method).assert_called_once()

    def test_server_closes_when_window_engine_fails(self):
        with patch('sys.argv', ['desktop']), patch.object(desktop, 'ThreadingHTTPServer') as cls, patch.object(desktop.webview, 'create_window'), patch.object(desktop.webview, 'start', side_effect=RuntimeError('test startup failure')):
            with self.assertRaises(RuntimeError):
                desktop.main()
            cls.return_value.shutdown.assert_called_once()
            cls.return_value.server_close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
