"""Macro library editor: record keyboard/mouse input, edit events and delays."""

from __future__ import annotations

import time
from typing import Callable

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QHBoxLayout, QHeaderView, QInputDialog, QLabel, QListWidget,
                               QMenu, QMessageBox, QPushButton, QSpinBox, QTableWidget,
                               QTableWidgetItem, QToolButton, QVBoxLayout, QWidget)

from nplayaim import macro
from nplayaim.actions import MOUSE_NAMES

from .widgets import KeyCapture, hid_usage

QT_BUTTONS = {Qt.LeftButton: "left", Qt.RightButton: "right", Qt.MiddleButton: "middle",
              Qt.BackButton: "back", Qt.ForwardButton: "forward"}


class CaptureArea(QLabel):
    """Focusable box that records keys, clicks and wheel while the page is recording."""

    def __init__(self, page: "MacroPage"):
        super().__init__("● Đang ghi — gõ phím hoặc click chuột vào ô này. Bấm Dừng để kết thúc.")
        self.page = page
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignCenter)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumHeight(72)
        self.setStyleSheet("QLabel { border: 2px dashed #c42b1c; border-radius: 8px; color: #c42b1c;"
                           " font-weight: bold; padding: 8px; }")

    def event(self, e) -> bool:
        t = e.type()
        if t in (QEvent.ShortcutOverride, QEvent.KeyPress, QEvent.KeyRelease):
            if t != QEvent.ShortcutOverride and not e.isAutoRepeat():
                self.page.rec_key(hid_usage(e), t == QEvent.KeyPress)
            e.accept()
            return True
        if t in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.MouseButtonDblClick):
            if e.button() in QT_BUTTONS:
                self.page.rec_button(QT_BUTTONS[e.button()], t != QEvent.MouseButtonRelease)
            self.setFocus()
            return True
        if t == QEvent.Wheel:
            y = e.angleDelta().y()
            if y:
                self.page.rec_wheel(int(y / 120) or (1 if y > 0 else -1))
            return True
        return super().event(e)


class MacroPage(QWidget):
    def __init__(self, state, on_changed: Callable[[str | None], None], toast: Callable[[str], None]):
        super().__init__()
        self.state = state
        self._on_changed = on_changed
        self._toast = toast
        self.current: str | None = None
        self._recording = False
        self._last_t = 0.0
        self._filling = False

        lay = QHBoxLayout(self)
        # -- left: macro list
        left = QVBoxLayout()
        left.addWidget(QLabel("<b>Danh sách macro</b>"))
        self.names = QListWidget()
        self.names.setFixedWidth(220)
        self.names.currentTextChanged.connect(self._on_select)
        left.addWidget(self.names)
        bar = QHBoxLayout()
        for text, cb in (("Mới", self._new), ("Đổi tên", self._rename), ("Xóa", self._delete)):
            b = QPushButton(text)
            b.clicked.connect(cb)
            bar.addWidget(b)
        left.addLayout(bar)
        lay.addLayout(left)

        # -- right: editor
        right = QVBoxLayout()
        tools = QHBoxLayout()
        self.rec = QPushButton("● Ghi", checkable=True)
        self.rec.toggled.connect(self._on_record)
        tools.addWidget(self.rec)
        self.auto_delay = QCheckBox("Tự chèn độ trễ thực", checked=True)
        tools.addWidget(self.auto_delay)
        tools.addWidget(QLabel("Mặc định"))
        self.default_delay = QSpinBox(maximum=macro.MAX_DELAY, singleStep=10, value=50, suffix=" ms")
        tools.addWidget(self.default_delay)
        tools.addStretch()
        add = QToolButton(text="Chèn ▾", popupMode=QToolButton.InstantPopup)
        menu = QMenu(add)
        menu.addAction("Phím…", self._add_key)
        menu.addAction("Click chuột…", self._add_click)
        menu.addAction("Di chuyển / cuộn…", self._add_move)
        add.setMenu(menu)
        tools.addWidget(add)
        for text, cb in (("▲", lambda: self._move(-1)), ("▼", lambda: self._move(1)),
                         ("Xóa sự kiện", self._delete_event), ("Xóa hết", self._clear)):
            b = QPushButton(text)
            b.clicked.connect(cb)
            tools.addWidget(b)
        right.addLayout(tools)

        self.capture = CaptureArea(self)
        self.capture.hide()
        right.addWidget(self.capture)

        self.events = QTableWidget(0, 2)
        self.events.setHorizontalHeaderLabels(["Sự kiện", "Trễ sau (ms)"])
        self.events.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.events.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.events.setSelectionMode(QAbstractItemView.SingleSelection)
        self.events.setEditTriggers(QAbstractItemView.NoEditTriggers)
        right.addWidget(self.events)
        self.hint = QLabel()
        right.addWidget(self.hint)
        lay.addLayout(right, 1)
        self.reload()

    # -- list of macros -----------------------------------------------------------------
    def reload(self, select: str | None = None) -> None:
        select = select or self.current
        names = sorted(self.state.macros)
        self.names.blockSignals(True)
        self.names.clear()
        self.names.addItems(names)
        self.names.blockSignals(False)
        if select in names:
            self.names.setCurrentRow(names.index(select))
        elif names:
            self.names.setCurrentRow(0)
        else:
            self._on_select("")

    def _on_select(self, name: str) -> None:
        self.current = name or None
        self._show_events()

    def _ask_name(self, title: str, initial: str) -> str | None:
        name, ok = QInputDialog.getText(self, title, "Tên macro:", text=initial)
        name = name.strip()
        if not ok:
            return None
        if not name:
            self._toast("Tên macro không được để trống")
        elif name != initial and name in self.state.macros:
            self._toast("Tên macro đã tồn tại")
        elif len(name) > 40:
            self._toast("Tên macro quá dài")
        else:
            return name
        return None

    def _new(self) -> None:
        n = 1
        while f"Macro {n}" in self.state.macros:
            n += 1
        name = self._ask_name("Macro mới", f"Macro {n}")
        if name:
            self.state.macros[name] = {"events": []}
            self.state.save()
            self.reload(name)

    def _rename(self) -> None:
        old = self.current
        name = self._ask_name("Đổi tên macro", old) if old else None
        if not name or name == old:
            return
        self.state.macros[name] = self.state.macros.pop(old)
        for p in self.state.profiles:
            for act in p["buttons"].values():
                if act.get("kind") == "macro" and act.get("macro") == old:
                    act["macro"] = name
        self.state.save()
        self.reload(name)
        self._on_changed(name)

    def _delete(self) -> None:
        if not self.current:
            return
        used = [p["name"] for p in self.state.profiles
                if any(a.get("kind") == "macro" and a.get("macro") == self.current
                       for a in p["buttons"].values())]
        if used:
            self._toast(f"Macro đang được gán trong: {', '.join(used)}")
            return
        if QMessageBox.question(self, "Xóa macro?", f"“{self.current}” sẽ bị xóa vĩnh viễn.") \
                != QMessageBox.Yes:
            return
        del self.state.macros[self.current]
        self.state.save()
        self.current = None
        self.reload()

    # -- events ---------------------------------------------------------------------------
    @property
    def _evs(self) -> list[dict]:
        return self.state.macros[self.current]["events"] if self.current else []

    def _show_events(self, select: int | None = None) -> None:
        evs = self._evs
        self._filling = True
        self.events.setRowCount(len(evs))
        for i, ev in enumerate(evs):
            self.events.setItem(i, 0, QTableWidgetItem(macro.describe_event(ev)))
            spin = QSpinBox(maximum=macro.MAX_DELAY, singleStep=10, value=int(ev.get("delay", 0)))
            spin.setFrame(False)
            spin.valueChanged.connect(lambda v, i=i: self._on_delay(i, v))
            self.events.setCellWidget(i, 1, spin)
        self._filling = False
        self.rec.setEnabled(bool(self.current))
        self.events.setEnabled(bool(self.current))
        if not self.current:
            self.hint.setText("Chưa chọn macro — tạo macro mới bằng nút Mới bên trái.")
        elif not evs:
            self.hint.setText("Macro trống — bấm Ghi rồi gõ phím / click chuột, hoặc dùng Chèn.")
        else:
            self.hint.setText(f"{len(evs)}/{macro.MAX_EVENTS} sự kiện")
        if select is not None and 0 <= select < len(evs):
            self.events.selectRow(select)
            self.events.scrollToItem(self.events.item(select, 0))

    def _commit(self, select: int | None = None) -> None:
        self.state.save()
        self._show_events(select)
        self._on_changed(self.current)

    def _on_delay(self, i: int, v: int) -> None:
        if self._filling or i >= len(self._evs):
            return
        self._evs[i]["delay"] = v
        self.state.save()
        self._on_changed(self.current)

    def _selected(self) -> int:
        rows = self.events.selectionModel().selectedRows()
        return rows[0].row() if rows else -1

    def _insert(self, evs: list[dict]) -> None:
        if not self.current:
            return
        if len(self._evs) + len(evs) > macro.MAX_EVENTS:
            self._toast("Macro đã đầy")
            return
        pos = self._selected()
        pos = len(self._evs) if pos < 0 else pos + 1
        self._evs[pos:pos] = evs
        self._commit(pos + len(evs) - 1)

    def _move(self, d: int) -> None:
        i = self._selected()
        j = i + d
        if i < 0 or not 0 <= j < len(self._evs):
            return
        e = self._evs
        e[i], e[j] = e[j], e[i]
        self._commit(j)

    def _delete_event(self) -> None:
        i = self._selected()
        if i >= 0:
            del self._evs[i]
            self._commit(min(i, len(self._evs) - 1))

    def _clear(self) -> None:
        if self.current and self._evs:
            self._evs.clear()
            self._commit()

    # -- recording ------------------------------------------------------------------------
    def _on_record(self, on: bool) -> None:
        self._recording = on
        self.capture.setVisible(on)
        self.rec.setText("■ Dừng" if on else "● Ghi")
        if on:
            self._last_t = 0.0
            self.capture.setFocus()

    def _append_recorded(self, ev: dict) -> None:
        if not self.current:
            return
        now = time.monotonic()
        evs = self._evs
        if evs:
            if self.auto_delay.isChecked() and self._last_t:
                evs[-1]["delay"] = min(macro.MAX_DELAY, int((now - self._last_t) * 1000))
            else:
                evs[-1]["delay"] = self.default_delay.value()
        self._last_t = now
        ev.setdefault("delay", self.default_delay.value())
        if len(evs) >= macro.MAX_EVENTS:
            self.rec.setChecked(False)
            self._toast("Macro đã đầy")
            return
        evs.append(ev)
        self._commit(len(evs) - 1)
        self.capture.setFocus()

    def rec_key(self, usage: int | None, down: bool) -> None:
        if self._recording and usage is not None:
            self._append_recorded({"t": "key", "code": usage, "down": down})

    def rec_button(self, button: str, down: bool) -> None:
        if self._recording:
            self._append_recorded({"t": "mouse", "button": button, "down": down})

    def rec_wheel(self, amount: int) -> None:
        if self._recording:
            self._append_recorded({"t": "move", "axis": "wheel", "value": amount})

    # -- manual insertion -------------------------------------------------------------------
    def _dialog(self, title: str, child: QWidget) -> bool:
        if not self.current:
            return False
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        v = QVBoxLayout(dlg)
        v.addWidget(child)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Chèn")
        bb.button(QDialogButtonBox.Ok).setAutoDefault(False)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        return dlg.exec() == QDialog.Accepted

    def _add_key(self) -> None:
        cap = KeyCapture()
        if not self._dialog("Chèn phím (nhấn + nhả)", cap):
            return
        d = self.default_delay.value()
        mods = [u for bit, u in ((1, 0xE0), (2, 0xE1), (4, 0xE2), (8, 0xE3)) if cap.mods & bit]
        seq = [{"t": "key", "code": u, "down": True, "delay": d} for u in mods]
        if cap.key:
            seq += [{"t": "key", "code": cap.key, "down": True, "delay": d},
                    {"t": "key", "code": cap.key, "down": False, "delay": d}]
        seq += [{"t": "key", "code": u, "down": False, "delay": d} for u in reversed(mods)]
        if seq:
            self._insert(seq)

    def _add_click(self) -> None:
        names = ["left", "right", "middle", "back", "forward"]
        dd = QComboBox()
        dd.addItems([MOUSE_NAMES[n] for n in names])
        if self._dialog("Chèn click chuột", dd):
            d, b = self.default_delay.value(), names[dd.currentIndex()]
            self._insert([{"t": "mouse", "button": b, "down": True, "delay": d},
                          {"t": "mouse", "button": b, "down": False, "delay": d}])

    def _add_move(self) -> None:
        box = QWidget()
        h = QHBoxLayout(box)
        axes = ["x", "y", "wheel"]
        dd = QComboBox()
        dd.addItems(["Ngang (X)", "Dọc (Y)", "Cuộn"])
        spin = QSpinBox(minimum=-127, maximum=127, value=10)
        h.addWidget(dd)
        h.addWidget(spin)
        if self._dialog("Chèn di chuyển / cuộn", box):
            self._insert([{"t": "move", "axis": axes[dd.currentIndex()], "value": spin.value(),
                           "delay": self.default_delay.value()}])
