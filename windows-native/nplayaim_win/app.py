"""Qt (PySide6) user interface — the Windows counterpart of linux-native/nplayaim/ui.py."""

from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QActionGroup, QColor, QFont, QFontMetrics, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QFileDialog,
                               QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QInputDialog,
                               QLabel, QMainWindow, QMenu, QMessageBox, QProgressBar, QPushButton,
                               QRadioButton, QScrollArea, QSlider, QSpinBox, QSystemTrayIcon,
                               QTabWidget, QVBoxLayout, QWidget)

import nplayaim
from nplayaim import actions, profile, protocol

from .hidwin import DeviceWorker, EventListener
from .macro_page import MacroPage
from .widgets import ActionDialog, ColorButton

APP_NAME = "Nplay AIM"
INSTANCE_KEY = "nplayaim-control"
DATA = Path(nplayaim.__file__).parent / "data"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
LIGHT_MODES = [(protocol.LIGHT_OFF, "Tắt"), (protocol.LIGHT_BREATHING, "Nhịp thở"),
               (protocol.LIGHT_STEADY, "Đứng yên"), (protocol.LIGHT_NEON, "Neon (đổi màu)")]


class Main(QObject):
    """post(fn, *args) from any thread -> runs on the GUI thread."""
    _sig = Signal(object)

    def __init__(self):
        super().__init__()
        self._sig.connect(self._run)

    def post(self, fn, *args) -> None:
        self._sig.emit(lambda: fn(*args))

    @Slot(object)
    def _run(self, fn) -> None:
        fn()


# -- autostart (HKCU\...\Run) -------------------------------------------------------------
def _autostart_cmd() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --background'
    exe = Path(sys.executable)
    exe = exe.with_name("pythonw.exe") if exe.with_name("pythonw.exe").exists() else exe
    return f'"{exe}" "{Path(sys.argv[0]).resolve()}" --background'


def autostart_enabled() -> bool:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
        return True
    except OSError:
        return False


def set_autostart(on: bool) -> None:
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, _autostart_cmd())
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except FileNotFoundError:
                pass


# -- small helpers ---------------------------------------------------------------------------
def slider(lo: int, hi: int, fmt) -> tuple[QWidget, QSlider]:
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    s = QSlider(Qt.Horizontal, minimum=lo, maximum=hi, pageStep=1)
    s.setTickPosition(QSlider.TicksBelow)
    s.setTickInterval(1)
    lab = QLabel()
    lab.setMinimumWidth(64)
    s.valueChanged.connect(lambda v: lab.setText(fmt(v)))
    lab.setText(fmt(s.value()))
    h.addWidget(s, 1)
    h.addWidget(lab)
    return w, s


def scrolled(w: QWidget) -> QScrollArea:
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setWidget(w)
    return sa


def app_icon(text: str | None = None) -> QIcon:
    size = 128  # drawn large; Windows scales it down to the tray size
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    if text:
        # Full-bleed badge with the largest bold text that fits: the tray icon is only 16-24 px.
        p.setBrush(QColor("#c42b1c"))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, 0, size, size, 20, 20)
        margin = 6
        font = QFont("Segoe UI", 10, QFont.Black)
        for px in range(size, 8, -2):
            font.setPixelSize(px)
            fm = QFontMetrics(font)
            if fm.horizontalAdvance(text) <= size - 2 * margin and fm.height() <= size - 2 * margin:
                break
        p.setFont(font)
        p.setPen(Qt.white)
        p.drawText(pm.rect(), Qt.AlignCenter, text)
    else:
        art = QPixmap(str(DATA / "mouse.png")).scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        p.drawPixmap((size - art.width()) // 2, (size - art.height()) // 2, art)
    p.end()
    return QIcon(pm)


def short_dpi(dpi: int) -> str:
    return str(dpi) if dpi < 1000 else f"{dpi / 1000:.1f}".rstrip("0").rstrip(".") + "k"


class Osd(QLabel):
    """Brief on-screen DPI indicator near the tray (Windows trays cannot show text labels)."""

    def __init__(self):
        super().__init__(None, Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setStyleSheet("QLabel { background: #202020; color: white; font-size: 20pt;"
                           " font-weight: bold; padding: 10px 20px; border: 1px solid #555; }")
        self._timer = QTimer(self, singleShot=True, interval=2500)
        self._timer.timeout.connect(self.hide)

    def flash(self, text: str) -> None:
        self.setText(text)
        self.adjustSize()
        g = QGuiApplication.primaryScreen().availableGeometry()
        self.move(g.right() - self.width() - 24, g.bottom() - self.height() - 24)
        self.show()
        self.raise_()
        self._timer.start()


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.resize(1000, 700)
        self.state = profile.State()
        self._timers: dict[str, QTimer] = {}
        self._pending: dict[str, object] = {}
        self._loading = False
        self._dirty = False  # changes made while the mouse was asleep / unplugged
        self._low_battery_warned = False
        self._quitting = False
        self.info: protocol.DeviceInfo | None = None
        self.main = Main()
        self.worker = DeviceWorker(self.main.post, self._on_info)
        self.osd = Osd()

        central = QWidget()
        root = QVBoxLayout(central)
        top = QHBoxLayout()
        top.addWidget(QLabel("Hồ sơ:"))
        self.profile_dd = QComboBox()
        self.profile_dd.setMinimumWidth(180)
        self.profile_dd.setToolTip("Hồ sơ cấu hình")
        self.profile_dd.currentIndexChanged.connect(self._on_profile_changed)
        top.addWidget(self.profile_dd)
        top.addStretch()
        self.status_label = QLabel("…")
        f = self.status_label.font()
        f.setBold(True)
        self.status_label.setFont(f)
        top.addWidget(self.status_label)
        root.addLayout(top)
        self.banner = QLabel(wordWrap=True)
        self.banner.setStyleSheet("QLabel { background: #fff4ce; color: #5c4400; padding: 8px;"
                                  " border: 1px solid #e0c060; }")
        self.banner.hide()
        root.addWidget(self.banner)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self.setCentralWidget(central)

        self._build_menu()
        self._build_buttons_page()
        self._build_dpi_page()
        self._build_lighting_page()
        self._build_performance_page()
        self._build_power_page()
        self.macro_page = MacroPage(self.state, self._on_macro_changed, self.toast)
        self.tabs.addTab(self.macro_page, "Macro")
        self._build_device_page()
        self._refresh_profile_names()
        self._load_profile()

        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray_menu = QMenu()
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(
            lambda r: self.show_window() if r in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick) else None)
        self.tray.show()
        self._update_tray()
        self.listener = EventListener(self.main.post, self._on_dpi_event)

        self.worker.poll_info()
        self._poll_timer = QTimer(self, interval=5000)
        self._poll_timer.timeout.connect(self.worker.poll_info)
        self._poll_timer.start()

    # -- menu -----------------------------------------------------------------------------
    def _build_menu(self) -> None:
        mb = self.menuBar()
        m = mb.addMenu("&Hồ sơ")
        m.addAction("Ghi toàn bộ hồ sơ vào chuột", self._apply_all)
        m.addSeparator()
        m.addAction("Đổi tên hồ sơ…", self._rename_profile)
        m.addAction("Nhập hồ sơ…", self._import_profile)
        m.addAction("Xuất hồ sơ…", self._export_profile)
        m.addAction("Đặt lại hồ sơ về mặc định…", self._reset_profile)
        m.addSeparator()
        m.addAction("Thoát", self._quit)

        m = mb.addMenu("&Tùy chọn")
        sub = m.addMenu("Hiển thị DPI")
        self.label_group = QActionGroup(self)
        self.label_actions = {}
        for mode, text in (("flash", "Hiện nhanh khi đổi DPI"), ("always", "Luôn hiện trên icon khay"),
                           ("off", "Không hiện")):
            a = sub.addAction(text, lambda mode=mode: self._set_dpi_label_mode(mode))
            a.setCheckable(True)
            a.setChecked(self.state.settings.get("dpi_label", "flash") == mode)
            self.label_group.addAction(a)
            self.label_actions[mode] = a
        self._toggle_action(m, "Cảnh báo pin yếu", "notify_battery")
        if sys.platform == "win32":
            a = m.addAction("Chạy nền khi đăng nhập Windows")
            a.setCheckable(True)
            a.setChecked(autostart_enabled())
            a.toggled.connect(self._on_autostart)

        m = mb.addMenu("Trợ &giúp")
        if sys.platform == "win32":
            m.addAction("Cài đặt chuột của Windows", lambda: os.startfile("ms-settings:mousetouchpad"))
        m.addAction("Giới thiệu", self._about)

    def _toggle_action(self, menu: QMenu, text: str, key: str) -> QAction:
        a = menu.addAction(text)
        a.setCheckable(True)
        a.setChecked(bool(self.state.settings.get(key)))
        a.toggled.connect(lambda on: self._on_setting(key, on))
        return a

    def _on_setting(self, key: str, on: bool) -> None:
        self.state.settings[key] = on
        self.state.save()
        self._update_tray()

    def _on_autostart(self, on: bool) -> None:
        try:
            set_autostart(on)
        except OSError as e:
            self.toast(f"Không đổi được tự khởi động: {e}")

    def _set_dpi_label_mode(self, mode: str) -> None:
        self.label_actions[mode].setChecked(True)
        self.state.settings["dpi_label"] = mode
        self.state.save()
        self._update_tray()

    # -- background / tray ------------------------------------------------------------------
    def show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, e) -> None:
        if not self._quitting and self.tray.isVisible():
            e.ignore()
            self.hide()
            if not self.state.settings.get("tray_hint_shown"):
                self.state.settings["tray_hint_shown"] = True
                self.state.save()
                self.tray.showMessage(f"{APP_NAME} vẫn chạy nền",
                                      "Bấm vào biểu tượng chuột ở khay hệ thống để mở lại.",
                                      QSystemTrayIcon.Information, 5000)
            return
        self.listener.stop()
        self.worker.stop()
        e.accept()

    def _quit(self) -> None:
        self._quitting = True
        self.listener.stop()
        self.worker.stop()
        self.tray.hide()
        QApplication.quit()

    def _dpi_text(self) -> str:
        d = self.p["dpi"]
        return f"{d['values'][d['current']]} DPI"

    def _update_tray(self) -> None:
        if not hasattr(self, "tray"):
            return
        d = self.p["dpi"]
        info = self.info
        bat = f" · pin {info.battery}%" if info and info.online else ""
        self.tray.setToolTip(f"{APP_NAME} — {self._dpi_text()}{bat}")
        mode = self.state.settings.get("dpi_label", "flash")
        self.tray.setIcon(app_icon(short_dpi(d["values"][d["current"]])) if mode == "always" else app_icon())

        m = self.tray_menu
        if m.isVisible():  # don't rebuild under the user's cursor; next poll will
            return
        m.clear()
        m.addAction(f"{APP_NAME} — {self._dpi_text()}{bat}").setEnabled(False)
        m.addSeparator()
        for i in range(6):
            if d["enabled"][i]:
                a = m.addAction(f"Mức {i + 1}: {d['values'][i]} DPI", lambda i=i: self._select_dpi(i))
                a.setCheckable(True)
                a.setChecked(d["current"] == i)
        m.addSeparator()
        sub = m.addMenu("Hồ sơ")
        for k, pr in enumerate(self.state.profiles):
            a = sub.addAction(pr["name"], lambda k=k: self.profile_dd.setCurrentIndex(k))
            a.setCheckable(True)
            a.setChecked(k == self.state.current)
        sub = m.addMenu("Hiển thị DPI")
        for mo, text in (("flash", "Hiện nhanh khi đổi DPI"), ("always", "Luôn hiện trên icon"),
                         ("off", "Không hiện")):
            a = sub.addAction(text, lambda mo=mo: self._set_dpi_label_mode(mo))
            a.setCheckable(True)
            a.setChecked(mode == mo)
        m.addSeparator()
        m.addAction("Mở cài đặt", self.show_window)
        m.addAction("Thoát", self._quit)

    def _flash_label(self) -> None:
        if self.state.settings.get("dpi_label", "flash") == "flash":
            self.osd.flash(self._dpi_text())

    def _select_dpi(self, i: int) -> None:
        self.dpi_widgets[i]["radio"].setChecked(True)  # triggers _on_dpi_radio -> push
        self._update_tray()
        self._flash_label()

    def _on_dpi_event(self, level: int, dpi: int) -> None:
        """The DPI button on the mouse was pressed."""
        d = self.p["dpi"]
        idx = level - 1
        if 0 <= idx < 6:
            changed = d["current"] != idx or d["values"][idx] != dpi
            d["current"] = idx
            d["values"][idx] = dpi
            if changed:
                self.state.save()
                self._loading = True
                w = self.dpi_widgets[idx]
                w["radio"].setChecked(True)
                w["slider"].setValue(protocol.dpi_to_code(dpi) - 1)
                self._loading = False
        self._update_tray()
        self._flash_label()  # corner box only, no Windows toast

    def _check_battery(self, info: protocol.DeviceInfo) -> None:
        if not info.online or info.charging:
            if info.charging:
                self._low_battery_warned = False
            return
        if info.battery <= 15 and not self._low_battery_warned:
            self._low_battery_warned = True
            if self.state.settings.get("notify_battery", True):
                self.tray.showMessage(f"Pin chuột yếu: {info.battery}%", "Hãy sạc chuột sớm.",
                                      QSystemTrayIcon.Warning, 8000)
        elif info.battery >= 25:
            self._low_battery_warned = False

    # -- helpers ------------------------------------------------------------------------------
    @property
    def p(self) -> dict:
        return self.state.profile

    def toast(self, text: str) -> None:
        self.statusBar().showMessage(text, 4000)

    def push(self, key: str, fn, delay_ms: int = 250) -> None:
        """Save state and send to the mouse, coalescing rapid changes per key."""
        if self._loading:
            return
        self.state.save()
        if self.info is None or not self.info.online:
            self._dirty = True
        self._pending[key] = fn
        t = self._timers.get(key)
        if t is None:
            t = self._timers[key] = QTimer(self, singleShot=True)
            t.timeout.connect(lambda: self.worker.submit(self._pending.pop(key), self._job_done))
        t.start(delay_ms)

    def _job_done(self, _result, err) -> None:
        if err:
            self._on_info(None, err)

    def _on_info(self, info: protocol.DeviceInfo | None, err: str | None) -> None:
        if err or info is None:
            self.info = None
            self.status_label.setText("Không kết nối")
            self.banner.setText(err or "Không tìm thấy chuột")
            self.banner.show()
            self._update_device_page()
            return
        was_online = self.info is not None and self.info.online
        self.info = info
        if info.online and not was_online and self._dirty:
            self._dirty = False
            self._apply_all(quiet=True)
            self.toast("Chuột đã kết nối lại — đã đồng bộ các thay đổi")
        self.banner.setVisible(not info.online)
        if not info.online:
            self.banner.setText("Chuột đang ngủ hoặc tắt — di chuyển chuột để đánh thức")
        charge = {1: " ⚡ đang sạc", 2: " ⚡ đầy"}.get(info.charging, "")
        self.status_label.setText(f"Pin {info.battery}%{charge}" if info.online else "Ngoại tuyến")
        self._sync_current_dpi(info)
        self._check_battery(info)
        self._update_device_page()
        self._update_tray()

    # -- profile handling -----------------------------------------------------------------------
    def _on_profile_changed(self, idx: int) -> None:
        if self._loading or idx < 0 or idx == self.state.current:
            return
        self.state.current = idx
        self.state.save()
        self._load_profile()
        self._apply_all(quiet=True)
        self._update_tray()
        self.toast(f"Đã chuyển sang {self.p['name']}")

    def _refresh_profile_names(self) -> None:
        self._loading = True
        self.profile_dd.clear()
        self.profile_dd.addItems([p["name"] for p in self.state.profiles])
        self.profile_dd.setCurrentIndex(self.state.current)
        self._loading = False
        self._update_tray()

    def _apply_all(self, quiet: bool = False) -> None:
        state, p = self.state, copy.deepcopy(self.p)

        def done(_r, err):
            if err:
                self._on_info(None, err)
            elif not quiet:
                self.toast("Đã ghi toàn bộ hồ sơ vào chuột")
        self.worker.submit(lambda m: profile.apply_all(m, state, p), done)

    def _rename_profile(self) -> None:
        name, ok = QInputDialog.getText(self, "Đổi tên hồ sơ", "Tên hồ sơ:", text=self.p["name"])
        if ok and name.strip():
            self.p["name"] = name.strip()
            self.state.save()
            self._refresh_profile_names()

    def _confirm(self, title: str, text: str) -> bool:
        return QMessageBox.question(self, title, text) == QMessageBox.Yes

    def _reset_profile(self) -> None:
        if self._confirm("Đặt lại hồ sơ?",
                         "Mọi thiết lập của hồ sơ hiện tại sẽ trở về mặc định của nhà sản xuất."):
            self.state.profiles[self.state.current] = profile.default_profile(self.p["name"])
            self.state.save()
            self._load_profile()
            self._apply_all()

    def _export_profile(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Xuất hồ sơ", f"{self.p['name']}.json",
                                              "Hồ sơ JSON (*.json)")
        if not path:
            return
        used = {a.get("macro") for a in self.p["buttons"].values() if a.get("kind") == "macro"}
        data = {"profile": self.p, "macros": {k: v for k, v in self.state.macros.items() if k in used}}
        try:
            Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError as e:
            self.toast(f"Không ghi được tệp: {e}")
            return
        self.toast("Đã xuất hồ sơ")

    def _import_profile(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Nhập hồ sơ", "", "Hồ sơ JSON (*.json)")
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            prof = data["profile"]
            base = profile.default_profile(prof.get("name", self.p["name"]))
            profile._merge(base, prof)
            macros = dict(data.get("macros", {}))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            self.toast("Tệp hồ sơ không hợp lệ")
            return
        for k, v in macros.items():
            self.state.macros.setdefault(k, v)
        self.state.profiles[self.state.current] = base
        self.state.save()
        self._refresh_profile_names()
        self._load_profile()
        self.macro_page.reload()
        self._apply_all()

    def _about(self) -> None:
        QMessageBox.about(self, f"Giới thiệu {APP_NAME}",
                          f"<b>{APP_NAME}</b> {nplayaim.__version__}<br><br>"
                          "Phần mềm cấu hình chuột Nplay AIM10 / M220 cho Windows.<br>"
                          "Giao thức được dịch ngược từ phần mềm gốc của hãng.<br><br>Giấy phép MIT.")

    def _load_profile(self) -> None:
        """Refresh every page from the current profile without sending anything."""
        self._loading = True
        try:
            p = self.p
            for b, lab in self.button_labels.items():
                lab.setText(actions.describe(p["buttons"][b]))
            d = p["dpi"]
            for i, w in enumerate(self.dpi_widgets):
                w["switch"].setChecked(d["enabled"][i])
                self._set_dpi_row_enabled(i, d["enabled"][i])
                w["slider"].setValue(protocol.dpi_to_code(d["values"][i]) - 1)
                w["value"].setValue(d["values"][i])
                w["color"].set_rgb(d["colors"][i])
                w["radio"].setChecked(d["current"] == i)
            L = p["lighting"]
            self.light_mode.setCurrentIndex([m for m, _ in LIGHT_MODES].index(int(L["mode"])))
            for i, (tog, btn) in enumerate(self.palette):
                tog.setChecked(L["selected"][i])
                btn.set_rgb(L["palette"][i])
            self.steady_color.set_rgb(L["steady_color"])
            self._update_light_rows()
            self.polling_buttons[int(p["polling"])].setChecked(True)
            self._update_polling_label()
            pw = p["power"]
            self.sleep_slider.setValue(int(pw["sleep"]))
            self.light_off.setChecked(bool(pw["light_off_moving"]))
            self.wakeup.setChecked(bool(pw["motion_wakeup"]))
        finally:
            self._loading = False

    # -- page: buttons ----------------------------------------------------------------------------
    def _build_buttons_page(self) -> None:
        page = QWidget()
        h = QHBoxLayout(page)
        art = QLabel()
        art.setPixmap(QPixmap(str(DATA / "mouse.png")))
        art.setAlignment(Qt.AlignCenter)
        art.setFixedWidth(260)
        h.addWidget(art)
        box = QGroupBox("Gán chức năng cho nút")
        g = QGridLayout(box)
        g.addWidget(QLabel("Bấm “Đổi…” để chọn chức năng mới. Thay đổi được ghi vào chuột ngay."),
                    0, 0, 1, 4)
        self.button_labels = {}
        for i, b in enumerate(profile.BUTTON_ORDER):
            g.addWidget(QLabel(f"<b>{i + 1}</b>"), i + 1, 0)
            g.addWidget(QLabel(profile.BUTTON_NAMES[b]), i + 1, 1)
            lab = QLabel()
            self.button_labels[b] = lab
            g.addWidget(lab, i + 1, 2)
            btn = QPushButton("Đổi…")
            btn.setAccessibleName(f"Đổi chức năng {profile.BUTTON_NAMES[b]}")
            btn.clicked.connect(lambda _=False, b=b: self._pick_action(b))
            g.addWidget(btn, i + 1, 3)
        g.setColumnStretch(2, 1)
        reset = QPushButton("Khôi phục chức năng mặc định cho tất cả nút")
        reset.clicked.connect(self._reset_buttons)
        g.addWidget(reset, len(profile.BUTTON_ORDER) + 1, 0, 1, 4)
        g.setRowStretch(len(profile.BUTTON_ORDER) + 2, 1)
        h.addWidget(box, 1)
        self.tabs.addTab(page, "Nút bấm")

    def _pick_action(self, button: str) -> None:
        dlg = ActionDialog(self, profile.BUTTON_NAMES[button], self.p["buttons"][button],
                           sorted(self.state.macros))
        if dlg.exec() and dlg.action:
            self.p["buttons"][button] = dlg.action
            self.button_labels[button].setText(actions.describe(dlg.action))
            self._push_button(button)

    def _push_button(self, button: str) -> None:
        state, p = self.state, copy.deepcopy(self.p)
        self.push(f"btn-{button}", lambda m: profile.apply_button(m, state, p, button), 0)

    def _reset_buttons(self) -> None:
        self.p["buttons"] = copy.deepcopy(actions.DEFAULT_ACTIONS)
        self._load_profile()
        for b in profile.BUTTON_ORDER:
            self._push_button(b)
        self.toast("Đã khôi phục chức năng nút mặc định")

    def _on_macro_changed(self, name: str | None) -> None:
        self._load_profile()
        for b, act in self.p["buttons"].items():
            if act.get("kind") == "macro" and act.get("macro") == name:
                self._push_button(b)

    # -- page: DPI ----------------------------------------------------------------------------------
    def _build_dpi_page(self) -> None:
        page = QWidget()
        v = QVBoxLayout(page)
        box = QGroupBox("Các mức DPI")
        g = QGridLayout(box)
        g.addWidget(QLabel("Nút DPI chuyển vòng qua các mức đang bật. Chọn ● để đặt mức đang dùng; "
                           "màu là màu đèn báo của mức đó.", wordWrap=True), 0, 0, 1, 5)
        self.dpi_widgets = []
        self.dpi_radio_group = QButtonGroup(self)
        for i in range(6):
            radio = QRadioButton(f"Mức {i + 1}")
            radio.setToolTip("Đặt làm mức hiện tại")
            self.dpi_radio_group.addButton(radio, i)
            sl = QSlider(Qt.Horizontal, minimum=0, maximum=len(protocol.DPI_VALUES) - 1)
            sl.setAccessibleName(f"DPI mức {i + 1}")
            spin = QSpinBox(minimum=200, maximum=10000, singleStep=50, suffix=" DPI", keyboardTracking=False)
            color = ColorButton("Màu đèn báo")
            sw = QCheckBox("Bật")
            sw.setToolTip("Bật/tắt mức này")
            for col, w in enumerate((radio, sl, spin, color, sw)):
                g.addWidget(w, i + 1, col)
            w = {"radio": radio, "slider": sl, "value": spin, "color": color, "switch": sw}
            self.dpi_widgets.append(w)
            sl.valueChanged.connect(lambda val, i=i: self._on_dpi_slider(i, val))
            spin.valueChanged.connect(lambda val, i=i: self._on_dpi_spin(i, val))
            sw.toggled.connect(lambda on, i=i: self._on_dpi_switch(i, on))
            radio.toggled.connect(lambda on, i=i: self._on_dpi_radio(i, on))
            color.changed.connect(lambda c, i=i: self._on_dpi_color(i, c))
        g.setColumnStretch(1, 1)
        v.addWidget(box)
        v.addWidget(QLabel("Cảm biến PixArt PAW3325 — 200 – 10000 DPI, bước 100 tới 5000 DPI, "
                           "sau đó theo bảng của cảm biến."))
        v.addStretch()
        self.tabs.addTab(page, "DPI")

    def _on_dpi_slider(self, i: int, val: int) -> None:
        dpi = protocol.DPI_VALUES[val]
        w = self.dpi_widgets[i]
        if w["value"].value() != dpi:
            w["value"].blockSignals(True)
            w["value"].setValue(dpi)
            w["value"].blockSignals(False)
        if not self._loading and self.p["dpi"]["values"][i] != dpi:
            self.p["dpi"]["values"][i] = dpi
            self._push_dpi()

    def _on_dpi_spin(self, i: int, val: int) -> None:
        dpi = protocol.snap_dpi(val)
        w = self.dpi_widgets[i]
        idx = protocol.dpi_to_code(dpi) - 1
        if w["slider"].value() != idx:
            w["slider"].setValue(idx)  # -> _on_dpi_slider snaps the spin box
        elif val != dpi:
            w["value"].blockSignals(True)
            w["value"].setValue(dpi)
            w["value"].blockSignals(False)

    def _set_dpi_row_enabled(self, i: int, on: bool) -> None:
        for k in ("slider", "value", "radio", "color"):
            self.dpi_widgets[i][k].setEnabled(on)

    def _on_dpi_switch(self, i: int, on: bool) -> None:
        if self._loading:
            return
        d = self.p["dpi"]
        if not on and sum(d["enabled"]) <= 1 and d["enabled"][i]:
            self.dpi_widgets[i]["switch"].setChecked(True)
            self.toast("Phải bật ít nhất một mức DPI")
            return
        self._set_dpi_row_enabled(i, on)
        if d["enabled"][i] != on:
            d["enabled"][i] = on
            if not on and d["current"] == i:
                d["current"] = next(j for j in range(6) if d["enabled"][j])
                self._loading = True
                self.dpi_widgets[d["current"]]["radio"].setChecked(True)
                self._loading = False
            self._push_dpi()
            self._update_tray()

    def _on_dpi_radio(self, i: int, on: bool) -> None:
        if on and not self._loading and self.p["dpi"]["current"] != i:
            self.p["dpi"]["current"] = i
            self._push_dpi()
            self._update_tray()

    def _on_dpi_color(self, i: int, c: list[int]) -> None:
        self.p["dpi"]["colors"][i] = c
        p = copy.deepcopy(self.p)
        self.push("dpi-colors", lambda m: profile.apply_dpi_colors(m, p))

    def _push_dpi(self) -> None:
        p = copy.deepcopy(self.p)
        self.push("dpi", lambda m: profile.apply_dpi(m, p))
        self._flash_label()

    def _sync_current_dpi(self, info: protocol.DeviceInfo) -> None:
        """Reflect DPI-button presses on the mouse in the UI."""
        d = self.p["dpi"]
        enabled = [i for i in range(6) if d["enabled"][i]]
        if not info.online or info.dpi_count != len(enabled) or not 1 <= info.dpi_current <= len(enabled):
            return
        idx = enabled[info.dpi_current - 1]
        if idx != d["current"]:
            d["current"] = idx
            self.state.save()
            self._loading = True
            self.dpi_widgets[idx]["radio"].setChecked(True)
            self._loading = False

    # -- page: lighting -------------------------------------------------------------------------------
    def _build_lighting_page(self) -> None:
        page = QWidget()
        v = QVBoxLayout(page)
        box = QGroupBox("Hiệu ứng đèn")
        form = QFormLayout(box)
        self.light_mode = QComboBox()
        self.light_mode.addItems([n for _, n in LIGHT_MODES])
        self.light_mode.currentIndexChanged.connect(self._on_light_mode)
        form.addRow("Chế độ", self.light_mode)
        self.speed_row, self.speed = slider(1, 3, str)
        self.speed.valueChanged.connect(lambda val: self._on_light_param("speed", val))
        form.addRow("Tốc độ", self.speed_row)
        self.bright_row, self.bright = slider(1, 4, lambda val: f"{val * 25}%")
        self.bright.valueChanged.connect(lambda val: self._on_light_param("brightness", val))
        form.addRow("Độ sáng", self.bright_row)
        self.light_form = form
        v.addWidget(box)

        self.palette_group = QGroupBox("Màu nhịp thở — bật các màu sẽ dùng (theo thứ tự), bấm ô màu để đổi")
        h = QHBoxLayout(self.palette_group)
        self.palette = []
        for i in range(7):
            col = QVBoxLayout()
            btn = ColorButton(f"Màu {i + 1}")
            tog = QCheckBox()
            tog.setAccessibleName(f"Dùng màu {i + 1}")
            btn.changed.connect(lambda c, i=i: self._on_palette(i, c))
            tog.toggled.connect(lambda on, i=i: self._on_palette_toggle(i, on))
            col.addWidget(btn, 0, Qt.AlignHCenter)
            col.addWidget(tog, 0, Qt.AlignHCenter)
            h.addLayout(col)
            self.palette.append((tog, btn))
        h.addStretch()
        v.addWidget(self.palette_group)

        self.steady_group = QGroupBox("Màu đứng yên")
        h = QHBoxLayout(self.steady_group)
        h.addWidget(QLabel("Màu"))
        self.steady_color = ColorButton("Màu đứng yên")
        self.steady_color.changed.connect(self._on_steady_color)
        h.addWidget(self.steady_color)
        h.addStretch()
        v.addWidget(self.steady_group)
        v.addStretch()
        self.tabs.addTab(page, "Đèn LED")

    def _mode(self) -> int:
        return LIGHT_MODES[self.light_mode.currentIndex()][0]

    def _update_light_rows(self) -> None:
        mode = self._mode()
        L = self.p["lighting"]
        was = self._loading
        self._loading = True
        self.speed.setValue(int(L["speed"].get(str(mode), 2)))
        self.bright.setValue(int(L["brightness"].get(str(mode), 4)))
        self._loading = was
        self.light_form.setRowVisible(self.speed_row, mode in (protocol.LIGHT_BREATHING, protocol.LIGHT_NEON))
        self.light_form.setRowVisible(self.bright_row, mode == protocol.LIGHT_STEADY)
        self.palette_group.setVisible(mode == protocol.LIGHT_BREATHING)
        self.steady_group.setVisible(mode == protocol.LIGHT_STEADY)

    def _push_light(self) -> None:
        p = copy.deepcopy(self.p)
        self.push("light", lambda m: profile.apply_lighting(m, p))

    def _on_light_mode(self, _idx: int) -> None:
        mode = self._mode()
        self._update_light_rows()
        if self._loading or self.p["lighting"]["mode"] == mode:
            return
        self.p["lighting"]["mode"] = mode
        self._push_light()

    def _on_light_param(self, key: str, val: int) -> None:
        if self._loading:
            return
        self.p["lighting"][key][str(self._mode())] = val
        self._push_light()

    def _on_palette(self, i: int, c: list[int]) -> None:
        L = self.p["lighting"]
        L["palette"][i] = c
        if L["selected"][i]:
            self._push_light()
        else:
            self.state.save()

    def _on_palette_toggle(self, i: int, on: bool) -> None:
        L = self.p["lighting"]
        if self._loading or L["selected"][i] == on:
            return
        if not on and sum(L["selected"]) <= 1:
            self.palette[i][0].setChecked(True)
            self.toast("Chọn ít nhất một màu")
            return
        L["selected"][i] = on
        self._push_light()

    def _on_steady_color(self, c: list[int]) -> None:
        self.p["lighting"]["steady_color"] = c
        self._push_light()

    # -- page: performance --------------------------------------------------------------------------
    def _build_performance_page(self) -> None:
        page = QWidget()
        v = QVBoxLayout(page)
        box = QGroupBox("Tần số phản hồi (polling rate)")
        bv = QVBoxLayout(box)
        bv.addWidget(QLabel("Tần số cao cho độ trễ thấp hơn nhưng tốn pin hơn."))
        h = QHBoxLayout()
        self.polling_group = QButtonGroup(self)
        self.polling_buttons = {}
        for hz in (125, 250, 500, 1000):
            r = QRadioButton(f"{hz} Hz")
            self.polling_group.addButton(r, hz)
            self.polling_buttons[hz] = r
            h.addWidget(r)
        h.addStretch()
        bv.addLayout(h)
        self.polling_label = QLabel()
        bv.addWidget(self.polling_label)
        self.polling_group.idToggled.connect(self._on_polling)
        v.addWidget(box)
        v.addStretch()
        self.tabs.addTab(page, "Tần số")

    def _update_polling_label(self) -> None:
        hz = self.polling_group.checkedId()
        if hz > 0:
            self.polling_label.setText(f"Chu kỳ báo cáo: {protocol.POLLING_RATES[hz]} ms — {hz} lần mỗi giây")

    def _on_polling(self, hz: int, on: bool) -> None:
        if not on:
            return
        self._update_polling_label()
        if self._loading or hz == self.p["polling"]:
            return
        self.p["polling"] = hz
        self.push("polling", lambda m: m.set_polling(hz), 0)

    # -- page: power ------------------------------------------------------------------------------------
    def _build_power_page(self) -> None:
        page = QWidget()
        v = QVBoxLayout(page)
        box = QGroupBox("Pin")
        h = QHBoxLayout(box)
        self.bat_label = QLabel("—")
        f = self.bat_label.font()
        f.setPointSize(26)
        f.setBold(True)
        self.bat_label.setFont(f)
        self.bat_label.setMinimumWidth(110)
        h.addWidget(self.bat_label)
        right = QVBoxLayout()
        self.bat_bar = QProgressBar(minimum=0, maximum=100, textVisible=False)
        self.bat_state = QLabel()
        right.addWidget(self.bat_bar)
        right.addWidget(self.bat_state)
        h.addLayout(right, 1)
        v.addWidget(box)

        box = QGroupBox("Quản lý nguồn")
        form = QFormLayout(box)
        row, self.sleep_slider = slider(3, 10, lambda val: f"{val} phút")
        self.sleep_slider.valueChanged.connect(lambda _: self._on_power())
        form.addRow("Tự ngủ sau (không dùng)", row)
        self.light_off = QCheckBox("Tắt đèn khi di chuột (tiết kiệm pin khi đang sử dụng)")
        self.light_off.toggled.connect(lambda _: self._on_power())
        form.addRow(self.light_off)
        self.wakeup = QCheckBox("Di chuyển để đánh thức (tắt thì phải bấm nút để đánh thức chuột)")
        self.wakeup.toggled.connect(self._on_wakeup)
        form.addRow(self.wakeup)
        v.addWidget(box)
        v.addStretch()
        self.tabs.addTab(page, "Nguồn")

    def _on_power(self) -> None:
        if self._loading:
            return
        pw = self.p["power"]
        pw["sleep"] = self.sleep_slider.value()
        pw["light_off_moving"] = self.light_off.isChecked()
        s, l = pw["sleep"], pw["light_off_moving"]
        self.push("power", lambda m: m.set_power(s, l))

    def _on_wakeup(self, on: bool) -> None:
        if self._loading:
            return
        self.p["power"]["motion_wakeup"] = on
        self.push("wakeup", lambda m: m.set_motion_wakeup(on), 0)

    # -- page: device -------------------------------------------------------------------------------------
    def _build_device_page(self) -> None:
        page = QWidget()
        v = QVBoxLayout(page)
        box = QGroupBox("Thiết bị")
        form = QFormLayout(box)
        self.dev_rows = {}
        for key, title in (("model", "Mẫu"), ("conn", "Kết nối"), ("sensor", "Cảm biến"),
                           ("fw", "Firmware"), ("node", "Giao diện HID")):
            lab = QLabel("—", textInteractionFlags=Qt.TextSelectableByMouse, wordWrap=True)
            self.dev_rows[key] = lab
            form.addRow(title, lab)
        v.addWidget(box)
        box = QGroupBox("Thao tác")
        h = QHBoxLayout(box)
        b = QPushButton("Ghi toàn bộ hồ sơ vào chuột")
        b.clicked.connect(lambda: self._apply_all())
        h.addWidget(b)
        b = QPushButton("Khôi phục cài đặt gốc của chuột…")
        b.clicked.connect(self._factory_reset)
        h.addWidget(b)
        h.addStretch()
        v.addWidget(box)
        v.addStretch()
        self.tabs.addTab(page, "Thiết bị")

    def _update_device_page(self) -> None:
        info, r = self.info, self.dev_rows
        if info is None:
            for lab in r.values():
                lab.setText("—")
            r["conn"].setText("Không kết nối")
            self.bat_label.setText("—")
            self.bat_bar.setValue(0)
            self.bat_state.setText("Không kết nối")
            return
        node = getattr(self.worker.mouse, "node", None)
        r["model"].setText(f"Nplay AIM ({info.model})")
        mode = {"wireless": "Đầu thu không dây 2.4 GHz", "wired": "Cáp USB"}.get(node.mode if node else "", "?")
        r["conn"].setText(f"{mode} — chuột {'đang hoạt động' if info.online else 'đang ngủ/tắt'}")
        r["sensor"].setText(info.sensor_name)
        r["fw"].setText(info.firmware)
        r["node"].setText(node.path if node else "—")
        self.bat_label.setText(f"{info.battery}%" if info.online else "—")
        self.bat_bar.setValue(info.battery if info.online else 0)
        self.bat_state.setText({1: "Đang sạc", 2: "Đã sạc đầy"}.get(info.charging, "Đang dùng pin")
                               if info.online else "Chuột ngoại tuyến")

    def _factory_reset(self) -> None:
        if not self._confirm("Khôi phục cài đặt gốc?",
                             "Chuột sẽ trở về thiết lập của nhà sản xuất và hồ sơ hiện tại cũng được đặt lại."):
            return
        self.state.profiles[self.state.current] = profile.default_profile(self.p["name"])
        self.state.save()
        self._load_profile()
        self.worker.submit(lambda m: m.factory_reset(),
                           lambda _r, err: self._on_info(None, err) if err else self.toast("Đã khôi phục cài đặt gốc"))


def main(argv: list[str]) -> int:
    background = "--background" in argv
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)

    # Single instance: a second launch just brings the running window forward.
    sock = QLocalSocket()
    sock.connectToServer(INSTANCE_KEY)
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.waitForBytesWritten(300)
        return 0
    QLocalServer.removeServer(INSTANCE_KEY)
    server = QLocalServer()
    server.listen(INSTANCE_KEY)

    win = Window()
    server.newConnection.connect(lambda: (server.nextPendingConnection(), win.show_window()))
    if not background or not QSystemTrayIcon.isSystemTrayAvailable():
        win.show()
    if os.environ.get("NPLAYAIM_PAGE"):
        names = [win.tabs.tabText(i) for i in range(win.tabs.count())]
        if os.environ["NPLAYAIM_PAGE"] in names:
            win.tabs.setCurrentIndex(names.index(os.environ["NPLAYAIM_PAGE"]))
    return app.exec()
