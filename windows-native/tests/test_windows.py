"""Windows build checks: key mapping and UI -> packets (fake mouse, no hardware needed).

Run from windows-native/:  python -m unittest discover -s tests
"""

import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(HERE), str(HERE.parent / "linux-native")]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nplayaim import profile, protocol  # noqa: E402
from nplayaim.hidkeys import hid_from_win_scancode  # noqa: E402


class WinKeys(unittest.TestCase):
    def test_scancodes(self):
        self.assertEqual(hid_from_win_scancode(0x1E), 0x04)    # A
        self.assertEqual(hid_from_win_scancode(0x2A), 0xE1)    # left Shift
        self.assertEqual(hid_from_win_scancode(0x1D), 0xE0)    # left Ctrl
        self.assertEqual(hid_from_win_scancode(0x11D), 0xE4)   # right Ctrl (E0 1D)
        self.assertEqual(hid_from_win_scancode(0x148), 0x52)   # ↑ (not Num 8)
        self.assertEqual(hid_from_win_scancode(0x48), 0x60)    # Num 8
        self.assertEqual(hid_from_win_scancode(0x15B), 0xE3)   # Win
        self.assertEqual(hid_from_win_scancode(0x45, 0x13), 0x48)  # Pause
        self.assertEqual(hid_from_win_scancode(0x145, 0x90), 0x53)  # Num Lock
        self.assertEqual(hid_from_win_scancode(0x76), 0x73)    # F24
        self.assertIsNone(hid_from_win_scancode(0x1FF))


class FakeMouse(protocol.Mouse):
    def __init__(self):
        self._seq = 1
        self._lock = threading.Lock()
        self.sent = []

    def _set(self, pkt):
        self.sent.append(pkt)


class FakeWorker:
    def __init__(self, post, on_info):
        self.mouse = FakeMouse()

    def submit(self, fn, done=None):
        fn(self.mouse)

    def poll_info(self):
        pass

    def stop(self):
        pass


class UiPackets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        from nplayaim_win import app
        cls.tmp = tempfile.TemporaryDirectory()
        profile.STATE_FILE = Path(cls.tmp.name) / "state.json"
        profile.CONFIG_DIR = Path(cls.tmp.name)
        app.DeviceWorker = FakeWorker
        app.EventListener = lambda *a: type("L", (), {"stop": lambda self: None})()
        cls.qapp = QApplication.instance() or QApplication([])
        cls.win = app.Window()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def flush(self):
        from PySide6.QtTest import QTest
        QTest.qWait(400)  # push() coalesces for 250 ms
        sent, self.win.worker.mouse.sent = self.win.worker.mouse.sent, []
        return [(p[2], bytes(p[5:])) for p in sent]

    def test_polling(self):
        self.flush()
        self.win.polling_buttons[1000].setChecked(True)
        self.assertEqual(self.flush(), [(protocol.CMD_POLLING, bytes.fromhex("010101") + bytes(25))])
        self.assertEqual(profile.State().profile["polling"], 1000)  # saved to disk

    def test_dpi_disable_level(self):
        self.flush()
        self.win.dpi_widgets[1]["switch"].setChecked(False)
        (cmd, body), = self.flush()
        self.assertEqual(cmd, protocol.CMD_DPI)
        self.assertEqual(body[3], 0b111101)  # mask without level 2
        self.win.dpi_widgets[1]["switch"].setChecked(True)
        self.flush()

    def test_last_dpi_level_cannot_be_disabled(self):
        for w in self.win.dpi_widgets[1:]:
            w["switch"].setChecked(False)
        self.win.dpi_widgets[0]["switch"].setChecked(False)
        self.assertTrue(self.win.dpi_widgets[0]["switch"].isChecked())
        for w in self.win.dpi_widgets[1:]:
            w["switch"].setChecked(True)
        self.flush()

    def test_dpi_spin_snaps_and_sends(self):
        self.flush()
        self.win.dpi_widgets[0]["value"].setValue(5120)  # not a sensor step -> nearest
        self.assertEqual(self.win.p["dpi"]["values"][0], protocol.snap_dpi(5120))
        self.assertEqual(self.win.dpi_widgets[0]["value"].value(), protocol.snap_dpi(5120))
        self.assertEqual([c for c, _ in self.flush()], [protocol.CMD_DPI])

    def test_light_mode(self):
        self.flush()
        self.win.light_mode.setCurrentIndex(0)  # off
        self.assertEqual(self.flush(), [(protocol.CMD_LIGHTING, bytes([1, 2, 0, 0x22]) + bytes(24))])


if __name__ == "__main__":
    unittest.main()
