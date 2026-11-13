"""Shared widgets: colour button, key capture, and the dialog that picks a button function."""

from __future__ import annotations

import sys

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent
from PySide6.QtWidgets import (QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QHBoxLayout, QLabel, QPushButton, QSpinBox, QToolBox, QVBoxLayout,
                               QWidget)

from nplayaim import actions
from nplayaim.hidkeys import MODIFIER_BITS, combo_name, hid_from_win_scancode, hid_from_x11_keycode


def hid_usage(e: QKeyEvent) -> int | None:
    """Physical key of a Qt key event -> HID usage."""
    if sys.platform == "win32":
        return hid_from_win_scancode(e.nativeScanCode(), e.nativeVirtualKey())
    return hid_from_x11_keycode(e.nativeScanCode())


class ColorButton(QPushButton):
    """Swatch that opens the colour picker. `changed` fires only on user edits."""

    changed = Signal(list)

    def __init__(self, tip: str = "Đổi màu"):
        super().__init__()
        self.setFixedSize(40, 28)
        self.setToolTip(tip)
        self.setAccessibleName(tip)
        self._rgb = [255, 255, 255]
        self.clicked.connect(self._pick)
        self.set_rgb(self._rgb)

    def set_rgb(self, c) -> None:
        self._rgb = [int(v) for v in c]
        r, g, b = self._rgb
        self.setStyleSheet(f"QPushButton {{ background: rgb({r},{g},{b}); border: 1px solid #777; }}"
                           "QPushButton:disabled { background: #bbb; }")

    def _pick(self) -> None:
        col = QColorDialog.getColor(QColor(*self._rgb), self.window(), "Chọn màu")
        if col.isValid():
            c = [col.red(), col.green(), col.blue()]
            if c != self._rgb:
                self.set_rgb(c)
                self.changed.emit(c)


class _CaptureButton(QPushButton):
    def __init__(self, owner: "KeyCapture"):
        super().__init__()
        self.owner = owner
        self.setMinimumHeight(40)

    def event(self, e) -> bool:
        # Catch every key (Tab, Space, Alt…) before Qt uses it for focus or clicking.
        if self.owner.armed and e.type() in (QEvent.ShortcutOverride, QEvent.KeyPress):
            if e.type() == QEvent.KeyPress:
                self.owner.on_key(e)
            e.accept()
            return True
        return super().event(e)


class KeyCapture(QWidget):
    """Click, then press a key (optionally with modifiers)."""

    def __init__(self, mods: int = 0, key: int = 0):
        super().__init__()
        self.mods, self.key, self.armed = mods, key, False
        lay = QVBoxLayout(self)
        self.button = _CaptureButton(self)
        f = self.button.font()
        f.setBold(True)
        self.button.setFont(f)
        self.button.clicked.connect(self._arm)
        lay.addWidget(self.button)
        row = QHBoxLayout()
        self.toggles = {}
        for bit, name in ((0x01, "Ctrl"), (0x02, "Shift"), (0x04, "Alt"), (0x08, "Win")):
            t = QPushButton(name, checkable=True, checked=bool(mods & bit))
            t.toggled.connect(lambda on, bit=bit: self._on_toggle(bit, on))
            self.toggles[bit] = t
            row.addWidget(t)
        lay.addLayout(row)
        self._refresh()

    def _arm(self) -> None:
        self.armed = True
        self.button.setFocus()
        self._refresh()

    def _on_toggle(self, bit: int, on: bool) -> None:
        self.mods = (self.mods | bit) if on else (self.mods & ~bit)
        self._refresh()

    def on_key(self, e: QKeyEvent) -> None:
        usage = hid_usage(e)
        if usage is None:
            return
        if usage in MODIFIER_BITS:
            bit = MODIFIER_BITS[usage] & 0x0F or MODIFIER_BITS[usage] >> 4
            self.toggles[bit].setChecked(True)
            return
        self.key = usage
        self.armed = False
        self._refresh()

    def _refresh(self) -> None:
        if self.armed:
            self.button.setText("Nhấn một phím…")
        else:
            self.button.setText(combo_name(self.mods, self.key) if self.key else "Bấm để chọn phím")


class ActionDialog(QDialog):
    """Pick a function for one mouse button. After exec(), the choice is in `.action`."""

    def __init__(self, parent: QWidget, title: str, current: dict, macro_names: list[str]):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(460, 620)
        self.action: dict | None = None
        lay = QVBoxLayout(self)
        tb = QToolBox()
        lay.addWidget(tb)
        close = QDialogButtonBox(QDialogButtonBox.Cancel)
        close.rejected.connect(self.reject)
        lay.addWidget(close)

        def section(name: str) -> QVBoxLayout:
            w = QWidget()
            v = QVBoxLayout(w)
            v.setAlignment(Qt.AlignTop)
            tb.addItem(w, name)
            return v

        def pick(v, label, action, subtitle=None):
            mark = "✓  " if (actions.encode(action) == actions.encode(current)
                             and action.get("kind") != "macro") else "     "
            b = QPushButton(f"{mark}{label}" + (f"    ({subtitle})" if subtitle else ""))
            b.setStyleSheet("text-align: left; padding: 5px 8px;")
            b.clicked.connect(lambda: self._pick(action))
            v.addWidget(b)

        def assign(v, make, layout=None):
            b = QPushButton("Gán")
            b.setDefault(False)
            b.clicked.connect(lambda: (a := make()) and self._pick(a))
            (layout or v).addWidget(b)

        open_kind = {"mouse": 0, "dpi": 1, "dpi_lock": 1, "triple": 2, "fire": 2, "combo": 3,
                     "media": 6, "macro": 7, "switch_effect": 8, "disable": 8}

        v = section("Chuột")
        for b in ("left", "right", "middle", "back", "forward"):
            pick(v, actions.MOUSE_NAMES[b], {"kind": "mouse", "button": b})

        v = section("DPI")
        for op in ("loop", "up", "down"):
            pick(v, actions.DPI_OP_NAMES[op], {"kind": "dpi", "op": op})
        row = QHBoxLayout()
        row.addWidget(QLabel("Khóa DPI (sniper) — giữ nút để tạm hạ DPI:"))
        lock = QComboBox()
        lock.addItems([str(x) for x in actions.DPI_LOCK_VALUES])
        if current.get("kind") == "dpi_lock":
            lock.setCurrentIndex(actions.DPI_LOCK_VALUES.index(int(current["dpi"])))
        row.addWidget(lock)
        assign(v, lambda: {"kind": "dpi_lock", "dpi": actions.DPI_LOCK_VALUES[lock.currentIndex()]}, row)
        v.addLayout(row)

        v = section("Nhấn liên tục")
        pick(v, "Nhấn ba lần", {"kind": "triple"}, "một lần bấm = ba lần click trái")
        v.addWidget(QLabel("<b>Phím bắn (auto-fire)</b> — lặp lại click trái theo chu kỳ"))
        form = QFormLayout()
        interval = QSpinBox(minimum=5, maximum=255, value=50, suffix=" ms")
        loops = QSpinBox(minimum=0, maximum=255, value=0, specialValueText="0 = bắn liên tục khi giữ")
        if current.get("kind") == "fire":
            interval.setValue(int(current.get("interval", 50)))
            loops.setValue(int(current.get("loops", 0)))
        form.addRow("Chu kỳ (càng nhỏ càng nhanh)", interval)
        form.addRow("Số lần", loops)
        v.addLayout(form)
        assign(v, lambda: {"kind": "fire", "interval": interval.value(), "loops": loops.value()})

        v = section("Phím đơn / tổ hợp phím")
        cap = KeyCapture(int(current.get("mods", 0)), int(current.get("key", 0))) \
            if current.get("kind") == "combo" else KeyCapture()
        v.addWidget(cap)
        assign(v, lambda: {"kind": "combo", "mods": cap.mods, "key": cap.key}
               if cap.key or cap.mods else None)

        v = section("Văn phòng")
        for label, mods, key in actions.OFFICE:
            pick(v, label, {"kind": "combo", "mods": mods, "key": key, "label": label},
                 combo_name(mods, key))

        v = section("Quản lý cửa sổ")
        pick(v, "Trình quản lý tệp", {"kind": "media", "usage": 0x0194})
        for label, mods, key in actions.WINDOW:
            pick(v, label, {"kind": "combo", "mods": mods, "key": key, "label": label},
                 combo_name(mods, key))

        v = section("Phím media")
        for usage, label in actions.MEDIA:
            pick(v, label, {"kind": "media", "usage": usage})

        v = section("Macro")
        if macro_names:
            form = QFormLayout()
            mname = QComboBox()
            mname.addItems(macro_names)
            mode_keys = list(actions.MACRO_MODES)
            mode = QComboBox()
            mode.addItems([actions.MACRO_MODE_NAMES[k] for k in mode_keys])
            count = QSpinBox(minimum=1, maximum=255)
            if current.get("kind") == "macro":
                if current.get("macro") in macro_names:
                    mname.setCurrentIndex(macro_names.index(current["macro"]))
                mode.setCurrentIndex(mode_keys.index(current.get("mode", "count")))
                count.setValue(int(current.get("count", 1)))
            mode.currentIndexChanged.connect(lambda i: count.setEnabled(mode_keys[i] == "count"))
            count.setEnabled(mode_keys[mode.currentIndex()] == "count")
            form.addRow("Macro", mname)
            form.addRow("Chế độ lặp", mode)
            form.addRow("Số lần lặp", count)
            v.addLayout(form)
            assign(v, lambda: {"kind": "macro", "macro": macro_names[mname.currentIndex()],
                               "mode": mode_keys[mode.currentIndex()], "count": count.value()})
        else:
            v.addWidget(QLabel("Chưa có macro nào — tạo ở thẻ Macro trước."))

        v = section("Khác")
        pick(v, "Chuyển hiệu ứng đèn", {"kind": "switch_effect"})
        pick(v, "Tắt nút", {"kind": "disable"})

        tb.setCurrentIndex(open_kind.get(current.get("kind"), 0))

    def _pick(self, action: dict) -> None:
        self.action = action
        self.accept()
