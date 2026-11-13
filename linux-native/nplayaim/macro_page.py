"""Macro library editor: record keyboard/mouse input, edit events and delays."""

from __future__ import annotations

import time
from typing import Callable

from gi.repository import Adw, Gtk

from . import macro
from .dialogs import KeyCapture
from .hidkeys import hid_from_x11_keycode

GDK_BUTTONS = {1: "left", 2: "middle", 3: "right", 8: "back", 9: "forward"}


class MacroPage(Gtk.Box):
    def __init__(self, state, on_changed: Callable[[str], None], toast: Callable[[str], None]):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=18,
                         margin_top=18, margin_bottom=18, margin_start=18, margin_end=18)
        self.state = state
        self._on_changed = on_changed
        self._toast = toast
        self.current: str | None = None
        self._recording = False
        self._last_t = 0.0

        # -- left: macro list ----------------------------------------------------
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, width_request=240)
        left.append(Gtk.Label(label="Danh sách macro", xalign=0, css_classes=["heading"]))
        self.names = Gtk.ListBox(css_classes=["navigation-sidebar"],
                                 selection_mode=Gtk.SelectionMode.SINGLE)
        self.names.connect("row-selected", self._on_select)
        sc = Gtk.ScrolledWindow(vexpand=True, child=self.names, css_classes=["card"])
        left.append(sc)
        bar = Gtk.Box(spacing=6, homogeneous=True)
        for icon, tip, cb in (("list-add-symbolic", "Macro mới", self._new),
                              ("document-edit-symbolic", "Đổi tên", self._rename),
                              ("user-trash-symbolic", "Xóa", self._delete)):
            b = Gtk.Button(icon_name=icon, tooltip_text=tip)
            b.connect("clicked", lambda *_, f=cb: f())
            bar.append(b)
        left.append(bar)
        self.append(left)

        # -- right: editor ---------------------------------------------------------
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, hexpand=True)
        tools = Gtk.Box(spacing=8)
        self.rec = Gtk.ToggleButton(css_classes=["destructive-action", "pill"])
        self.rec.set_child(Adw.ButtonContent(icon_name="media-record-symbolic", label="Ghi"))
        self.rec.connect("toggled", self._on_record)
        tools.append(self.rec)
        self.auto_delay = Gtk.CheckButton(label="Tự chèn độ trễ thực", active=True)
        tools.append(self.auto_delay)
        tools.append(Gtk.Label(label="Mặc định", css_classes=["dim-label"], margin_start=8))
        self.default_delay = Gtk.SpinButton.new_with_range(0, macro.MAX_DELAY, 10)
        self.default_delay.set_value(50)
        tools.append(self.default_delay)
        tools.append(Gtk.Label(label="ms", css_classes=["dim-label"]))
        spacer = Gtk.Box(hexpand=True)
        tools.append(spacer)
        add = Gtk.MenuButton(icon_name="list-add-symbolic", tooltip_text="Chèn sự kiện")
        pop = Gtk.Popover()
        pbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        for label, cb in (("Phím…", self._add_key), ("Click chuột…", self._add_click),
                          ("Di chuyển / cuộn…", self._add_move)):
            b = Gtk.Button(label=label, css_classes=["flat"])
            b.connect("clicked", lambda *_, f=cb: (pop.popdown(), f()))
            pbox.append(b)
        pop.set_child(pbox)
        add.set_popover(pop)
        tools.append(add)
        for icon, tip, cb in (("go-up-symbolic", "Lên", lambda: self._move(-1)),
                              ("go-down-symbolic", "Xuống", lambda: self._move(1)),
                              ("edit-delete-symbolic", "Xóa sự kiện", self._delete_event),
                              ("edit-clear-all-symbolic", "Xóa hết", self._clear)):
            b = Gtk.Button(icon_name=icon, tooltip_text=tip)
            b.connect("clicked", lambda *_, f=cb: f())
            tools.append(b)
        right.append(tools)

        self.capture = Gtk.Label(label="● Đang ghi — gõ phím hoặc click chuột vào ô này. Bấm Ghi lần nữa để dừng.",
                                 wrap=True, focusable=True, visible=False,
                                 css_classes=["capture-area"], height_request=72)
        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", lambda c, kv, kc, st: self._rec_key(kc, True))
        keys.connect("key-released", lambda c, kv, kc, st: self._rec_key(kc, False))
        self.capture.add_controller(keys)
        click = Gtk.GestureClick(button=0)
        click.connect("pressed", lambda g, n, x, y: self._rec_button(g.get_current_button(), True))
        click.connect("released", lambda g, n, x, y: self._rec_button(g.get_current_button(), False))
        self.capture.add_controller(click)
        scroll = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.VERTICAL
                                           | Gtk.EventControllerScrollFlags.DISCRETE)
        scroll.connect("scroll", self._rec_scroll)
        self.capture.add_controller(scroll)
        right.append(self.capture)

        self.events = Gtk.ListBox(css_classes=["boxed-list"], selection_mode=Gtk.SelectionMode.SINGLE)
        self.empty = Adw.StatusPage(icon_name="input-keyboard-symbolic", title="Macro trống",
                                    description="Bấm Ghi rồi gõ phím / click chuột, hoặc dùng nút + để chèn sự kiện.")
        self.stack = Gtk.Stack()
        self.stack.add_named(Gtk.ScrolledWindow(vexpand=True, child=self.events), "list")
        self.stack.add_named(self.empty, "empty")
        self.none = Adw.StatusPage(icon_name="media-playlist-repeat-symbolic", title="Chưa chọn macro",
                                   description="Tạo macro mới bằng nút + bên trái.")
        self.stack.add_named(self.none, "none")
        right.append(self.stack)
        self.count_label = Gtk.Label(xalign=0, css_classes=["dim-label", "caption"])
        right.append(self.count_label)
        self.append(right)
        self.reload()

    # -- list of macros --------------------------------------------------------------
    def reload(self, select: str | None = None) -> None:
        select = select or self.current
        while (row := self.names.get_row_at_index(0)) is not None:
            self.names.remove(row)
        names = sorted(self.state.macros)
        for n in names:
            self.names.append(Gtk.Label(label=n, xalign=0, margin_top=6, margin_bottom=6,
                                        ellipsize=3))
        if select in names:
            self.names.select_row(self.names.get_row_at_index(names.index(select)))
        elif names:
            self.names.select_row(self.names.get_row_at_index(0))
        else:
            self.current = None
            self._show_events()

    def _on_select(self, lb, row) -> None:
        self.current = row.get_child().get_label() if row else None
        self._show_events()

    def _ask_name(self, heading: str, initial: str, done: Callable[[str], None]) -> None:
        dlg = Adw.AlertDialog(heading=heading)
        entry = Gtk.Entry(text=initial, activates_default=True)
        dlg.set_extra_child(entry)
        dlg.add_response("cancel", "Hủy")
        dlg.add_response("ok", "Đồng ý")
        dlg.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
        dlg.set_default_response("ok")

        def resp(d, r):
            name = entry.get_text().strip()
            if r != "ok":
                return
            if not name:
                self._toast("Tên macro không được để trống")
            elif name != initial and name in self.state.macros:
                self._toast("Tên macro đã tồn tại")
            elif len(name) > 40:
                self._toast("Tên macro quá dài")
            else:
                done(name)
        dlg.connect("response", resp)
        dlg.present(self.get_root())

    def _new(self) -> None:
        n = 1
        while f"Macro {n}" in self.state.macros:
            n += 1

        def done(name):
            self.state.macros[name] = {"events": []}
            self.state.save()
            self.reload(name)
        self._ask_name("Tên macro mới", f"Macro {n}", done)

    def _rename(self) -> None:
        if not self.current:
            return
        old = self.current

        def done(name):
            if name == old:
                return
            self.state.macros[name] = self.state.macros.pop(old)
            for p in self.state.profiles:
                for act in p["buttons"].values():
                    if act.get("kind") == "macro" and act.get("macro") == old:
                        act["macro"] = name
            self.state.save()
            self.reload(name)
            self._on_changed(name)
        self._ask_name("Đổi tên macro", old, done)

    def _delete(self) -> None:
        if not self.current:
            return
        used = [p["name"] for p in self.state.profiles
                if any(a.get("kind") == "macro" and a.get("macro") == self.current
                       for a in p["buttons"].values())]
        if used:
            self._toast(f"Macro đang được gán trong: {', '.join(used)}")
            return
        dlg = Adw.AlertDialog(heading="Xóa macro?", body=f"“{self.current}” sẽ bị xóa vĩnh viễn.")
        dlg.add_response("cancel", "Hủy")
        dlg.add_response("delete", "Xóa")
        dlg.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)

        def resp(d, r):
            if r == "delete":
                del self.state.macros[self.current]
                self.state.save()
                self.current = None
                self.reload()
        dlg.connect("response", resp)
        dlg.present(self.get_root())

    # -- events ------------------------------------------------------------------------
    @property
    def _evs(self) -> list[dict]:
        return self.state.macros[self.current]["events"] if self.current else []

    def _show_events(self, select: int | None = None) -> None:
        while (row := self.events.get_row_at_index(0)) is not None:
            self.events.remove(row)
        if not self.current:
            self.stack.set_visible_child_name("none")
            self.count_label.set_text("")
            self.rec.set_sensitive(False)
            return
        self.rec.set_sensitive(True)
        evs = self._evs
        for i, ev in enumerate(evs):
            row = Adw.ActionRow(title=macro.describe_event(ev), subtitle=f"#{i + 1}")
            spin = Gtk.SpinButton.new_with_range(0, macro.MAX_DELAY, 10)
            spin.set_value(int(ev.get("delay", 0)))
            spin.set_valign(Gtk.Align.CENTER)
            spin.connect("value-changed", self._on_delay, i)
            row.add_suffix(spin)
            row.add_suffix(Gtk.Label(label="ms", css_classes=["dim-label"]))
            self.events.append(row)
        self.stack.set_visible_child_name("list" if evs else "empty")
        self.count_label.set_text(f"{len(evs)}/{macro.MAX_EVENTS} sự kiện")
        if select is not None and 0 <= select < len(evs):
            self.events.select_row(self.events.get_row_at_index(select))

    def _commit(self, select: int | None = None) -> None:
        self.state.save()
        self._show_events(select)
        self._on_changed(self.current)

    def _on_delay(self, spin, i) -> None:
        self._evs[i]["delay"] = int(spin.get_value())
        self.state.save()
        self._on_changed(self.current)

    def _selected(self) -> int:
        row = self.events.get_selected_row()
        return row.get_index() if row else -1

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

    # -- recording -------------------------------------------------------------------
    def _on_record(self, btn) -> None:
        self._recording = btn.get_active()
        self.capture.set_visible(self._recording)
        btn.get_child().set_label("Dừng" if self._recording else "Ghi")
        if self._recording:
            self._last_t = 0.0
            self.capture.grab_focus()

    def _append_recorded(self, ev: dict) -> None:
        if not self.current:
            return
        now = time.monotonic()
        evs = self._evs
        if evs:
            if self.auto_delay.get_active() and self._last_t:
                evs[-1]["delay"] = min(macro.MAX_DELAY, int((now - self._last_t) * 1000))
            else:
                evs[-1]["delay"] = int(self.default_delay.get_value())
        self._last_t = now
        ev.setdefault("delay", int(self.default_delay.get_value()))
        if len(evs) >= macro.MAX_EVENTS:
            self.rec.set_active(False)
            self._toast("Macro đã đầy")
            return
        evs.append(ev)
        self._commit(len(evs) - 1)
        self.capture.grab_focus()

    def _rec_key(self, keycode: int, down: bool) -> bool:
        if not self._recording:
            return False
        usage = hid_from_x11_keycode(keycode)
        if usage is not None:
            evs = self._evs
            # ignore key auto-repeat
            if down and evs and evs[-1].get("t") == "key" and evs[-1]["code"] == usage and evs[-1]["down"]:
                return True
            self._append_recorded({"t": "key", "code": usage, "down": down})
        return True

    def _rec_button(self, button: int, down: bool) -> None:
        if self._recording and button in GDK_BUTTONS:
            self._append_recorded({"t": "mouse", "button": GDK_BUTTONS[button], "down": down})

    def _rec_scroll(self, ctl, dx, dy) -> bool:
        if self._recording and dy:
            self._append_recorded({"t": "move", "axis": "wheel", "value": -int(dy)})
        return True

    # -- manual insertion -------------------------------------------------------------
    def _dialog(self, heading: str, child: Gtk.Widget, done: Callable[[], None]) -> None:
        if not self.current:
            return
        dlg = Adw.AlertDialog(heading=heading)
        dlg.set_extra_child(child)
        dlg.add_response("cancel", "Hủy")
        dlg.add_response("ok", "Chèn")
        dlg.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
        dlg.connect("response", lambda d, r: done() if r == "ok" else None)
        dlg.present(self.get_root())

    def _add_key(self) -> None:
        cap = KeyCapture()
        d = int(self.default_delay.get_value())

        def done():
            mods = [u for bit, u in ((1, 0xE0), (2, 0xE1), (4, 0xE2), (8, 0xE3)) if cap.mods & bit]
            seq = [{"t": "key", "code": u, "down": True, "delay": d} for u in mods]
            if cap.key:
                seq += [{"t": "key", "code": cap.key, "down": True, "delay": d},
                        {"t": "key", "code": cap.key, "down": False, "delay": d}]
            seq += [{"t": "key", "code": u, "down": False, "delay": d} for u in reversed(mods)]
            if seq:
                self._insert(seq)
        self._dialog("Chèn phím (nhấn + nhả)", cap, done)

    def _add_click(self) -> None:
        names = ["left", "right", "middle", "back", "forward"]
        from .actions import MOUSE_NAMES
        dd = Gtk.DropDown.new_from_strings([MOUSE_NAMES[n] for n in names])
        d = int(self.default_delay.get_value())
        self._dialog("Chèn click chuột", dd, lambda: self._insert([
            {"t": "mouse", "button": names[dd.get_selected()], "down": True, "delay": d},
            {"t": "mouse", "button": names[dd.get_selected()], "down": False, "delay": d}]))

    def _add_move(self) -> None:
        box = Gtk.Box(spacing=8)
        axes = ["x", "y", "wheel"]
        dd = Gtk.DropDown.new_from_strings(["Ngang (X)", "Dọc (Y)", "Cuộn"])
        spin = Gtk.SpinButton.new_with_range(-127, 127, 1)
        spin.set_value(10)
        box.append(dd)
        box.append(spin)
        d = int(self.default_delay.get_value())
        self._dialog("Chèn di chuyển / cuộn", box, lambda: self._insert([
            {"t": "move", "axis": axes[dd.get_selected()], "value": int(spin.get_value()), "delay": d}]))
