"""Dialogs: choosing a button function, capturing key combinations."""

from __future__ import annotations

from typing import Callable

from gi.repository import Adw, Gtk

from . import actions
from .hidkeys import MODIFIER_BITS, combo_name, hid_from_x11_keycode


class KeyCapture(Gtk.Box):
    """Click, then press a key (optionally with modifiers)."""

    def __init__(self, mods: int = 0, key: int = 0):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.mods, self.key = mods, key
        self.button = Gtk.Button(css_classes=["pill", "capture"])
        self.button.connect("clicked", lambda *_: self._arm())
        self.append(self.button)

        mods_box = Gtk.Box(spacing=6, halign=Gtk.Align.CENTER)
        self.toggles = {}
        for bit, name in ((0x01, "Ctrl"), (0x02, "Shift"), (0x04, "Alt"), (0x08, "Win")):
            t = Gtk.ToggleButton(label=name, active=bool(mods & bit))
            t.connect("toggled", self._on_toggle, bit)
            self.toggles[bit] = t
            mods_box.append(t)
        self.append(mods_box)

        self._armed = False
        ctl = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        ctl.connect("key-pressed", self._on_key)
        self.button.add_controller(ctl)
        self._refresh()

    def _arm(self) -> None:
        self._armed = True
        self.button.grab_focus()
        self._refresh()

    def _on_toggle(self, t: Gtk.ToggleButton, bit: int) -> None:
        self.mods = (self.mods | bit) if t.get_active() else (self.mods & ~bit)
        self._refresh()

    def _on_key(self, ctl, keyval, keycode, state) -> bool:
        if not self._armed:
            return False
        usage = hid_from_x11_keycode(keycode)
        if usage is None:
            return True
        if usage in MODIFIER_BITS:
            bit = MODIFIER_BITS[usage] & 0x0F or MODIFIER_BITS[usage] >> 4
            self.toggles[bit].set_active(True)
            return True
        self.key = usage
        self._armed = False
        self._refresh()
        return True

    def _refresh(self) -> None:
        if self._armed:
            self.button.set_label("Nhấn một phím…")
            self.button.add_css_class("suggested-action")
        else:
            self.button.remove_css_class("suggested-action")
            self.button.set_label(combo_name(self.mods, self.key) if self.key else "Bấm để chọn phím")


class ActionDialog(Adw.Dialog):
    """Pick a function for one mouse button."""

    def __init__(self, title: str, current: dict, macro_names: list[str],
                 on_pick: Callable[[dict], None]):
        super().__init__(title=title, content_width=520, content_height=680)
        self._on_pick = on_pick
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        page = Adw.PreferencesPage()
        view.set_content(page)
        self.set_child(view)

        def pick_row(group, label, action, subtitle=None):
            row = Adw.ActionRow(title=label, activatable=True)
            if subtitle:
                row.set_subtitle(subtitle)
            if actions.encode(action) == actions.encode(current) and action.get("kind") != "macro":
                row.add_suffix(Gtk.Image(icon_name="object-select-symbolic"))
            row.connect("activated", lambda *_: self._pick(action))
            if isinstance(group, Adw.ExpanderRow):
                group.add_row(row)
            else:
                group.add(row)

        g = Adw.PreferencesGroup(title="Chuột")
        for b in ("left", "right", "middle", "back", "forward"):
            pick_row(g, actions.MOUSE_NAMES[b], {"kind": "mouse", "button": b})
        page.add(g)

        g = Adw.PreferencesGroup(title="DPI")
        for op in ("loop", "up", "down"):
            pick_row(g, actions.DPI_OP_NAMES[op], {"kind": "dpi", "op": op})
        lock = Adw.ComboRow(title="Khóa DPI (sniper)",
                            subtitle="Giữ nút để tạm hạ DPI",
                            model=Gtk.StringList.new([str(v) for v in actions.DPI_LOCK_VALUES]))
        if current.get("kind") == "dpi_lock":
            lock.set_selected(actions.DPI_LOCK_VALUES.index(int(current["dpi"])))
        lock.add_suffix(self._apply_button(
            lambda: {"kind": "dpi_lock", "dpi": actions.DPI_LOCK_VALUES[lock.get_selected()]}))
        g.add(lock)
        page.add(g)

        g = Adw.PreferencesGroup(title="Nhấn liên tục")
        pick_row(g, "Nhấn ba lần", {"kind": "triple"}, "Một lần bấm = ba lần click trái")
        fire = Adw.ExpanderRow(title="Phím bắn (auto-fire)",
                               subtitle="Lặp lại click trái theo chu kỳ")
        interval = Adw.SpinRow.new_with_range(5, 255, 1)
        interval.set_title("Chu kỳ (ms)")
        interval.set_subtitle("Càng nhỏ bắn càng nhanh")
        loops = Adw.SpinRow.new_with_range(0, 255, 1)
        loops.set_title("Số lần")
        loops.set_subtitle("0 = bắn liên tục khi giữ nút")
        if current.get("kind") == "fire":
            interval.set_value(int(current.get("interval", 50)))
            loops.set_value(int(current.get("loops", 0)))
        else:
            interval.set_value(50)
        apply_row = Adw.ActionRow()
        apply_row.add_suffix(self._apply_button(lambda: {
            "kind": "fire", "interval": int(interval.get_value()), "loops": int(loops.get_value())}))
        for r in (interval, loops, apply_row):
            fire.add_row(r)
        g.add(fire)
        page.add(g)

        g = Adw.PreferencesGroup(title="Bàn phím")
        combo = Adw.ExpanderRow(title="Phím đơn / tổ hợp phím",
                                expanded=current.get("kind") == "combo")
        cap = KeyCapture(int(current.get("mods", 0)), int(current.get("key", 0))) \
            if current.get("kind") == "combo" else KeyCapture()
        cap.set_margin_top(12)
        cap.set_margin_bottom(12)
        combo.add_row(cap)
        r = Adw.ActionRow()
        r.add_suffix(self._apply_button(
            lambda: {"kind": "combo", "mods": cap.mods, "key": cap.key} if cap.key or cap.mods else None))
        combo.add_row(r)
        g.add(combo)
        office = Adw.ExpanderRow(title="Văn phòng")
        for label, mods, key in actions.OFFICE:
            pick_row(office, label, {"kind": "combo", "mods": mods, "key": key, "label": label},
                     combo_name(mods, key))
        g.add(office)
        win = Adw.ExpanderRow(title="Quản lý cửa sổ")
        pick_row(win, "Trình quản lý tệp", {"kind": "media", "usage": 0x0194})
        for label, mods, key in actions.WINDOW:
            pick_row(win, label, {"kind": "combo", "mods": mods, "key": key, "label": label},
                     combo_name(mods, key))
        g.add(win)
        page.add(g)

        g = Adw.PreferencesGroup(title="Đa phương tiện")
        media = Adw.ExpanderRow(title="Phím media", expanded=current.get("kind") == "media")
        for usage, label in actions.MEDIA:
            pick_row(media, label, {"kind": "media", "usage": usage})
        g.add(media)
        page.add(g)

        g = Adw.PreferencesGroup(title="Macro")
        if macro_names:
            mrow = Adw.ComboRow(title="Macro", model=Gtk.StringList.new(macro_names))
            mode_keys = list(actions.MACRO_MODES)
            mode = Adw.ComboRow(title="Chế độ lặp", model=Gtk.StringList.new(
                [actions.MACRO_MODE_NAMES[k] for k in mode_keys]))
            count = Adw.SpinRow.new_with_range(1, 255, 1)
            count.set_title("Số lần lặp")
            if current.get("kind") == "macro":
                if current.get("macro") in macro_names:
                    mrow.set_selected(macro_names.index(current["macro"]))
                mode.set_selected(mode_keys.index(current.get("mode", "count")))
                count.set_value(int(current.get("count", 1)))
            mode.connect("notify::selected",
                         lambda *_: count.set_sensitive(mode_keys[mode.get_selected()] == "count"))
            count.set_sensitive(mode_keys[mode.get_selected()] == "count")
            r = Adw.ActionRow()
            r.add_suffix(self._apply_button(lambda: {
                "kind": "macro", "macro": macro_names[mrow.get_selected()],
                "mode": mode_keys[mode.get_selected()], "count": int(count.get_value())}))
            for w in (mrow, mode, count, r):
                g.add(w)
        else:
            g.set_description("Chưa có macro nào — tạo ở thẻ Macro trước.")
        page.add(g)

        g = Adw.PreferencesGroup(title="Khác")
        pick_row(g, "Chuyển hiệu ứng đèn", {"kind": "switch_effect"})
        pick_row(g, "Tắt nút", {"kind": "disable"})
        page.add(g)

    def _apply_button(self, make: Callable[[], dict | None]) -> Gtk.Button:
        b = Gtk.Button(label="Gán", valign=Gtk.Align.CENTER, css_classes=["suggested-action"])

        def clicked(*_):
            act = make()
            if act:
                self._pick(act)
        b.connect("clicked", clicked)
        return b

    def _pick(self, action: dict) -> None:
        self._on_pick(action)
        self.close()
