"""GTK4 / libadwaita user interface."""

from __future__ import annotations

import copy
import json
import os
import subprocess
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import __version__, actions, profile, protocol  # noqa: E402
from .device import DeviceWorker, EventListener  # noqa: E402
from .dialogs import ActionDialog  # noqa: E402
from .macro_page import MacroPage  # noqa: E402
from .tray import MenuItem, Notifier, TrayIcon  # noqa: E402

APP_ID = "io.github.nplayaim.Control"
AUTOSTART = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart" / f"{APP_ID}.desktop"
DATA = Path(__file__).parent / "data"

CSS = """
.capture { font-weight: bold; min-height: 40px; }
.capture-area { border: 2px dashed @accent_color; border-radius: 12px; padding: 12px;
                color: @accent_color; font-weight: bold; }
.capture-area:focus { background: alpha(@accent_bg_color, 0.12); }
.dpi-value { font-feature-settings: "tnum"; font-weight: bold; min-width: 64px; }
.battery-big { font-size: 28pt; font-weight: 800; }
.swatch { min-width: 36px; min-height: 36px; padding: 0; border-radius: 10px; }
.mouse-art { margin: 12px; }
"""

LIGHT_MODES = [(protocol.LIGHT_OFF, "Tắt"), (protocol.LIGHT_BREATHING, "Nhịp thở"),
               (protocol.LIGHT_STEADY, "Đứng yên"), (protocol.LIGHT_NEON, "Neon (đổi màu)")]


def rgba(c) -> Gdk.RGBA:
    r = Gdk.RGBA()
    r.red, r.green, r.blue, r.alpha = c[0] / 255, c[1] / 255, c[2] / 255, 1.0
    return r


def to_rgb(r: Gdk.RGBA) -> list[int]:
    return [round(r.red * 255), round(r.green * 255), round(r.blue * 255)]


def scale_row(title: str, lo: int, hi: int, value: int, fmt=None, subtitle: str | None = None):
    row = Adw.ActionRow(title=title)
    if subtitle:
        row.set_subtitle(subtitle)
    sc = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, lo, hi, 1)
    sc.set_hexpand(True)
    sc.set_size_request(260, -1)
    sc.set_draw_value(True)
    sc.set_value_pos(Gtk.PositionType.RIGHT)
    sc.set_round_digits(0)
    for v in range(lo, hi + 1):
        sc.add_mark(v, Gtk.PositionType.BOTTOM, None)
    if fmt:
        sc.set_format_value_func(lambda s, v: fmt(int(round(v))))
    sc.set_value(value)
    sc.set_valign(Gtk.Align.CENTER)
    row.add_suffix(sc)
    return row, sc


class Window(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application):
        super().__init__(application=app, title="Nplay AIM", default_width=1080, default_height=760)
        self.state = profile.State()
        self._timers: dict[str, int] = {}
        self._loading = False
        self._dirty = False  # changes made while the mouse was asleep / unplugged
        self.info: protocol.DeviceInfo | None = None
        self.worker = DeviceWorker(self._on_info)

        self.toasts = Adw.ToastOverlay()
        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self.stack = Adw.ViewStack(vexpand=True)
        switcher = Adw.ViewSwitcher(stack=self.stack, policy=Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(switcher)

        # profile selector
        self.profile_dd = Gtk.DropDown.new_from_strings([p["name"] for p in self.state.profiles])
        self.profile_dd.set_selected(self.state.current)
        self.profile_dd.set_tooltip_text("Hồ sơ cấu hình")
        self.profile_dd.connect("notify::selected", self._on_profile_changed)
        header.pack_start(self.profile_dd)

        menu = Gio.Menu()
        menu.append("Ghi toàn bộ hồ sơ vào chuột", "win.apply-all")
        menu.append("Đổi tên hồ sơ…", "win.rename-profile")
        menu.append("Nhập hồ sơ…", "win.import-profile")
        menu.append("Xuất hồ sơ…", "win.export-profile")
        menu.append("Đặt lại hồ sơ về mặc định", "win.reset-profile")
        opts = Gio.Menu()
        label = Gio.Menu()
        label.append("Chỉ hiện khi đổi DPI", "win.dpi-label::flash")
        label.append("Luôn hiện", "win.dpi-label::always")
        label.append("Không hiện", "win.dpi-label::off")
        opts.append_submenu("DPI cạnh icon khay", label)
        opts.append("Thông báo hệ thống khi đổi DPI", "win.notify-dpi")
        opts.append("Cảnh báo pin yếu", "win.notify-battery")
        opts.append("Chạy nền khi đăng nhập", "win.autostart")
        menu.append_section(None, opts)
        sec = Gio.Menu()
        sec.append("Cài đặt chuột của hệ thống", "win.system-mouse")
        sec.append("Giới thiệu", "win.about")
        menu.append_section(None, sec)
        header.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu,
                                       primary=True, tooltip_text="Menu"))
        self.status = Gtk.Box(spacing=6, valign=Gtk.Align.CENTER)
        self.status_icon = Gtk.Image(icon_name="battery-missing-symbolic")
        self.status_label = Gtk.Label(label="…")
        self.status.append(self.status_icon)
        self.status.append(self.status_label)
        header.pack_end(self.status)

        view.add_top_bar(header)
        self.banner = Adw.Banner(revealed=False)
        self.banner.connect("button-clicked", lambda *_: self._open_udev_help())
        view.add_top_bar(self.banner)
        view.set_content(self.stack)
        bottom = Adw.ViewSwitcherBar(stack=self.stack)
        view.add_bottom_bar(bottom)
        self.toasts.set_child(view)
        self.set_content(self.toasts)

        bp = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 760sp"))
        bp.add_setter(switcher, "visible", False)
        bp.add_setter(bottom, "reveal", True)
        self.add_breakpoint(bp)

        for name, cb in (("apply-all", self._apply_all), ("rename-profile", self._rename_profile),
                         ("import-profile", self._import_profile),
                         ("export-profile", self._export_profile),
                         ("reset-profile", self._reset_profile),
                         ("system-mouse", self._system_mouse), ("about", self._about)):
            a = Gio.SimpleAction.new(name, None)
            a.connect("activate", lambda *_, f=cb: f())
            self.add_action(a)
        for name, key in (("notify-dpi", "notify_dpi"), ("notify-battery", "notify_battery")):
            a = Gio.SimpleAction.new_stateful(name, None, GLib.Variant("b", bool(self.state.settings[key])))
            a.connect("change-state", self._on_setting, key)
            self.add_action(a)
        a = Gio.SimpleAction.new_stateful("dpi-label", GLib.VariantType("s"),
                                          GLib.Variant("s", self.state.settings.get("dpi_label", "flash")))
        a.connect("change-state", self._on_dpi_label_mode)
        self.add_action(a)
        a = Gio.SimpleAction.new_stateful("autostart", None, GLib.Variant("b", AUTOSTART.exists()))
        a.connect("change-state", self._on_autostart)
        self.add_action(a)

        self._build_buttons_page()
        self._build_dpi_page()
        self._build_lighting_page()
        self._build_performance_page()
        self._build_power_page()
        self.macro_page = MacroPage(self.state, self._on_macro_changed, self.toast)
        self.stack.add_titled_with_icon(self.macro_page, "macro", "Macro", "media-playlist-repeat-symbolic")
        self._build_device_page()
        self._load_profile()
        if os.environ.get("NPLAYAIM_PAGE"):
            self.stack.set_visible_child_name(os.environ["NPLAYAIM_PAGE"])

        self._low_battery_warned = False
        self._label_timer = 0
        self.notifier = Notifier("Nplay AIM", APP_ID)
        self.tray = TrayIcon(APP_ID, "Nplay AIM", "input-mouse-symbolic", self.show_window)
        self._update_tray()
        self.listener = EventListener(self._on_dpi_event)

        self.worker.poll_info()
        GLib.timeout_add_seconds(5, self._poll)
        self.connect("close-request", self._on_close)

    # -- background / tray -------------------------------------------------------------
    def show_window(self) -> None:
        self.set_visible(True)
        self.present()

    def _on_close(self, *_) -> bool:
        if self.tray.available:
            self.set_visible(False)
            if not self.state.settings.get("tray_hint_shown"):
                self.state.settings["tray_hint_shown"] = True
                self.state.save()
                self.notifier.notify("hint", "Nplay AIM vẫn chạy nền",
                                     "Bấm vào biểu tượng chuột trên thanh trên cùng để mở lại.",
                                     timeout_ms=5000)
            return True
        self.listener.stop()
        self.worker.stop()
        return False

    def _quit(self) -> None:
        self.listener.stop()
        self.worker.stop()
        self.get_application().quit()

    def _on_setting(self, action, value, key) -> None:
        action.set_state(value)
        self.state.settings[key] = value.get_boolean()
        self.state.save()
        self._update_tray()

    def _on_autostart(self, action, value) -> None:
        on = value.get_boolean()
        try:
            if on:
                launcher = Path.home() / ".local" / "bin" / "nplayaim"
                exe = str(launcher) if launcher.exists() else "python3 -m nplayaim"
                AUTOSTART.parent.mkdir(parents=True, exist_ok=True)
                AUTOSTART.write_text(
                    "[Desktop Entry]\nType=Application\nName=Nplay AIM\n"
                    f"Exec={exe} --background\nIcon=input-mouse\nNoDisplay=true\n"
                    "X-GNOME-Autostart-enabled=true\n")
            else:
                AUTOSTART.unlink(missing_ok=True)
        except OSError as e:
            self.toast(f"Không đổi được tự khởi động: {e.strerror}")
            return
        action.set_state(value)

    def _on_dpi_label_mode(self, action, value) -> None:
        action.set_state(value)
        self.state.settings["dpi_label"] = value.get_string()
        self.state.save()
        self._update_tray()

    def _set_dpi_label_mode(self, mode: str) -> None:
        self.lookup_action("dpi-label").change_state(GLib.Variant("s", mode))

    def _refresh_label(self) -> None:
        """Persistent label (mode 'always'), or clear it when not flashing."""
        mode = self.state.settings.get("dpi_label", "flash")
        if mode == "always":
            self.tray.set_label(self._dpi_text())
        elif not self._label_timer:
            self.tray.set_label("")

    def _flash_label(self) -> None:
        mode = self.state.settings.get("dpi_label", "flash")
        if mode == "off":
            return
        self.tray.set_label(self._dpi_text())
        if mode == "flash":
            if self._label_timer:
                GLib.source_remove(self._label_timer)

            def clear():
                self._label_timer = 0
                self._refresh_label()
                return False
            self._label_timer = GLib.timeout_add(2500, clear)

    def _dpi_text(self) -> str:
        d = self.p["dpi"]
        return f"{d['values'][d['current']]} DPI"

    def _update_tray(self) -> None:
        if not hasattr(self, "tray"):
            return
        d = self.p["dpi"]
        info = self.info
        bat = f" · pin {info.battery}%" if info and info.online else ""
        self.tray.set_tooltip(f"{self._dpi_text()}{bat}")
        items = [MenuItem(f"Nplay AIM — {self._dpi_text()}{bat}", enabled=False),
                 MenuItem(separator=True)]
        for i in range(6):
            if d["enabled"][i]:
                items.append(MenuItem(f"Mức {i + 1}: {d['values'][i]} DPI",
                                      lambda i=i: self._select_dpi(i), radio=d["current"] == i))
        items.append(MenuItem(separator=True))
        items.append(MenuItem("Hồ sơ", children=[
            MenuItem(pr["name"], lambda k=k: self.profile_dd.set_selected(k), radio=k == self.state.current)
            for k, pr in enumerate(self.state.profiles)]))
        mode = self.state.settings.get("dpi_label", "flash")
        items.append(MenuItem("DPI cạnh icon", children=[
            MenuItem(text, lambda m=m: self._set_dpi_label_mode(m), radio=mode == m)
            for m, text in (("flash", "Chỉ hiện khi đổi DPI"), ("always", "Luôn hiện"),
                            ("off", "Không hiện"))]))
        items.append(MenuItem("Thông báo hệ thống khi đổi DPI", self._toggle_notify,
                              check=bool(self.state.settings["notify_dpi"])))
        items.append(MenuItem(separator=True))
        items.append(MenuItem("Mở cài đặt", self.show_window))
        items.append(MenuItem("Thoát", self._quit))
        self.tray.set_menu(items)
        self._refresh_label()

    def _toggle_notify(self) -> None:
        a = self.lookup_action("notify-dpi")
        a.change_state(GLib.Variant("b", not a.get_state().get_boolean()))

    def _select_dpi(self, i: int) -> None:
        self.dpi_widgets[i]["radio"].set_active(True)  # triggers _on_dpi_radio -> push
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
                w["radio"].set_active(True)
                w["scale"].set_value(protocol.dpi_to_code(dpi) - 1)
                self._loading = False
        self._update_tray()
        self._flash_label()
        if self.state.settings.get("notify_dpi", False):
            self.notifier.notify("dpi", f"DPI {dpi}", f"Mức {level} · {self.p['name']}",
                                 icon="input-mouse", timeout_ms=1500)

    def _check_battery(self, info: protocol.DeviceInfo) -> None:
        if not info.online or info.charging:
            self._low_battery_warned = False if info.charging else self._low_battery_warned
            return
        if info.battery <= 15 and not self._low_battery_warned:
            self._low_battery_warned = True
            if self.state.settings.get("notify_battery", True):
                self.notifier.notify("battery", f"Pin chuột yếu: {info.battery}%",
                                     "Hãy sạc chuột sớm.", icon="battery-caution",
                                     transient=False, urgency=2, timeout_ms=8000)
        elif info.battery >= 25:
            self._low_battery_warned = False

    # -- helpers -----------------------------------------------------------------------
    @property
    def p(self) -> dict:
        return self.state.profile

    def toast(self, text: str) -> None:
        self.toasts.add_toast(Adw.Toast(title=text, timeout=3))

    def push(self, key: str, fn, delay_ms: int = 250) -> None:
        """Save state and send to the mouse, coalescing rapid changes per key."""
        if self._loading:
            return
        self.state.save()
        if self.info is None or not self.info.online:
            self._dirty = True
        if key in self._timers:
            GLib.source_remove(self._timers[key])

        def fire():
            self._timers.pop(key, None)
            self.worker.submit(fn, self._job_done)
            return False
        self._timers[key] = GLib.timeout_add(delay_ms, fire)

    def _job_done(self, result, err) -> None:
        if err:
            self._on_info(None, err)

    def _poll(self) -> bool:
        self.worker.poll_info()
        return True

    def _on_info(self, info: protocol.DeviceInfo | None, err: str | None) -> None:
        if err or info is None:
            self.info = None
            self.status_icon.set_from_icon_name("battery-missing-symbolic")
            self.status_label.set_text("Không kết nối")
            self.banner.set_title(err or "Không tìm thấy chuột")
            self.banner.set_button_label("Hướng dẫn quyền" if err and "quyền" in err else None)
            self.banner.set_revealed(True)
            self._update_device_page()
            return
        was_online = self.info is not None and self.info.online
        self.info = info
        if info.online and not was_online and self._dirty:
            self._dirty = False
            self._apply_all(quiet=True)
            self.toast("Chuột đã kết nối lại — đã đồng bộ các thay đổi")
        self.banner.set_revealed(not info.online)
        if not info.online:
            self.banner.set_title("Chuột đang ngủ hoặc tắt — di chuyển chuột để đánh thức")
            self.banner.set_button_label(None)
        level = (info.battery + 5) // 10 * 10
        icon = f"battery-level-{min(100, level)}{'-charging' if info.charging == 1 else ''}-symbolic"
        self.status_icon.set_from_icon_name(icon if info.online else "battery-missing-symbolic")
        self.status_label.set_text(f"{info.battery}%" if info.online else "Ngoại tuyến")
        self._sync_current_dpi(info)
        self._check_battery(info)
        self._update_device_page()
        self._update_tray()

    # -- profile handling ------------------------------------------------------------------
    def _on_profile_changed(self, dd, _pspec) -> None:
        idx = dd.get_selected()
        if self._loading or idx == self.state.current or idx == Gtk.INVALID_LIST_POSITION:
            return
        self.state.current = idx
        self.state.save()
        self._load_profile()
        self._apply_all(quiet=True)
        self.toast(f"Đã chuyển sang {self.p['name']}")

    def _refresh_profile_names(self) -> None:
        self._loading = True
        self.profile_dd.set_model(Gtk.StringList.new([p["name"] for p in self.state.profiles]))
        self.profile_dd.set_selected(self.state.current)
        self._loading = False

    def _apply_all(self, quiet: bool = False) -> None:
        state, p = self.state, copy.deepcopy(self.p)

        def job(m):
            profile.apply_all(m, state, p)

        def done(_r, err):
            if err:
                self._on_info(None, err)
            elif not quiet:
                self.toast("Đã ghi toàn bộ hồ sơ vào chuột")
        self.worker.submit(job, done)

    def _rename_profile(self) -> None:
        dlg = Adw.AlertDialog(heading="Đổi tên hồ sơ")
        entry = Gtk.Entry(text=self.p["name"], activates_default=True)
        dlg.set_extra_child(entry)
        dlg.add_response("cancel", "Hủy")
        dlg.add_response("ok", "Đổi tên")
        dlg.set_default_response("ok")
        dlg.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)

        def resp(d, r):
            name = entry.get_text().strip()
            if r == "ok" and name:
                self.p["name"] = name
                self.state.save()
                self._refresh_profile_names()
        dlg.connect("response", resp)
        dlg.present(self)

    def _reset_profile(self) -> None:
        dlg = Adw.AlertDialog(heading="Đặt lại hồ sơ?",
                              body="Mọi thiết lập của hồ sơ hiện tại sẽ trở về mặc định của nhà sản xuất.")
        dlg.add_response("cancel", "Hủy")
        dlg.add_response("reset", "Đặt lại")
        dlg.set_response_appearance("reset", Adw.ResponseAppearance.DESTRUCTIVE)

        def resp(d, r):
            if r == "reset":
                self.state.profiles[self.state.current] = profile.default_profile(self.p["name"])
                self.state.save()
                self._load_profile()
                self._apply_all()
        dlg.connect("response", resp)
        dlg.present(self)

    def _export_profile(self) -> None:
        fd = Gtk.FileDialog(title="Xuất hồ sơ", initial_name=f"{self.p['name']}.json")

        def done(d, res):
            try:
                f = d.save_finish(res)
            except GLib.Error:
                return
            used = {a.get("macro") for a in self.p["buttons"].values() if a.get("kind") == "macro"}
            data = {"profile": self.p, "macros": {k: v for k, v in self.state.macros.items() if k in used}}
            Path(f.get_path()).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            self.toast("Đã xuất hồ sơ")
        fd.save(self, None, done)

    def _import_profile(self) -> None:
        fd = Gtk.FileDialog(title="Nhập hồ sơ")

        def done(d, res):
            try:
                f = d.open_finish(res)
                data = json.loads(Path(f.get_path()).read_text(encoding="utf-8"))
                prof = data["profile"]
            except (GLib.Error, OSError, ValueError, KeyError):
                self.toast("Tệp hồ sơ không hợp lệ")
                return
            base = profile.default_profile(prof.get("name", self.p["name"]))
            profile._merge(base, prof)
            for k, v in data.get("macros", {}).items():
                self.state.macros.setdefault(k, v)
            self.state.profiles[self.state.current] = base
            self.state.save()
            self._refresh_profile_names()
            self._load_profile()
            self.macro_page.reload()
            self._apply_all()
        fd.open(self, None, done)

    def _system_mouse(self) -> None:
        for cmd in (["gnome-control-center", "mouse"], ["systemsettings", "kcm_mouse"],
                    ["xfce4-mouse-settings"]):
            try:
                subprocess.Popen(cmd)
                return
            except OSError:
                continue
        self.toast("Không tìm thấy trình cài đặt chuột của hệ thống")

    def _about(self) -> None:
        about = Adw.AboutDialog(application_name="Nplay AIM", version=__version__,
                                application_icon="input-mouse",
                                comments="Phần mềm cấu hình chuột Nplay AIM10 / M220 cho Linux.\n"
                                         "Giao thức được dịch ngược từ phần mềm Windows của hãng.",
                                license_type=Gtk.License.MIT_X11)
        about.present(self)

    def _open_udev_help(self) -> None:
        dlg = Adw.AlertDialog(
            heading="Cần quyền truy cập thiết bị",
            body="Chạy lệnh sau một lần rồi rút/cắm lại đầu thu:\n\n"
                 "sudo install -m 644 99-nplayaim10.rules /etc/udev/rules.d/ && "
                 "sudo udevadm control --reload && sudo udevadm trigger")
        dlg.add_response("ok", "Đã hiểu")
        dlg.present(self)

    def _load_profile(self) -> None:
        """Refresh every page from the current profile without sending anything."""
        self._loading = True
        try:
            p = self.p
            for b, row in self.button_rows.items():
                row.set_subtitle(actions.describe(p["buttons"][b]))
            d = p["dpi"]
            for i, w in enumerate(self.dpi_widgets):
                w["switch"].set_active(d["enabled"][i])
                w["scale"].set_value(protocol.dpi_to_code(d["values"][i]) - 1)
                w["color"].set_rgba(rgba(d["colors"][i]))
                w["radio"].set_active(d["current"] == i)
            L = p["lighting"]
            self.light_mode.set_selected([m for m, _ in LIGHT_MODES].index(int(L["mode"])))
            for i, (tog, btn) in enumerate(self.palette):
                tog.set_active(L["selected"][i])
                btn.set_rgba(rgba(L["palette"][i]))
            self.steady_color.set_rgba(rgba(L["steady_color"]))
            self._update_light_rows()
            self.polling.set_active_name(str(p["polling"]))
            pw = p["power"]
            self.sleep_scale.set_value(int(pw["sleep"]))
            self.light_off_row.set_active(bool(pw["light_off_moving"]))
            self.wakeup_row.set_active(bool(pw["motion_wakeup"]))
        finally:
            self._loading = False

    # -- page: buttons ---------------------------------------------------------------------
    def _build_buttons_page(self) -> None:
        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(title="Gán chức năng cho nút",
                                     description="Bấm vào một nút để chọn chức năng mới. Thay đổi được ghi vào chuột ngay.")
        self.button_rows = {}
        for i, b in enumerate(profile.BUTTON_ORDER):
            row = Adw.ActionRow(title=profile.BUTTON_NAMES[b], activatable=True)
            num = Gtk.Label(label=str(i + 1), css_classes=["numeric", "dim-label"], width_chars=2)
            row.add_prefix(num)
            row.add_suffix(Gtk.Image(icon_name="go-next-symbolic"))
            row.connect("activated", lambda *_, btn=b: self._pick_action(btn))
            self.button_rows[b] = row
            group.add(row)
        reset = Adw.ButtonRow(title="Khôi phục chức năng mặc định cho tất cả nút",
                              start_icon_name="edit-undo-symbolic")
        reset.connect("activated", lambda *_: self._reset_buttons())
        group.add(reset)
        page.add(group)

        box = Gtk.Box(spacing=24, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        art = Gtk.Picture.new_for_filename(str(DATA / "mouse.png"))
        art.set_can_shrink(True)
        art.set_content_fit(Gtk.ContentFit.CONTAIN)
        art.add_css_class("mouse-art")
        holder = Gtk.Box(width_request=240, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        art.set_size_request(240, 440)
        holder.append(art)
        box.append(holder)
        scroll = Gtk.ScrolledWindow(child=page, hexpand=True,
                                    hscrollbar_policy=Gtk.PolicyType.NEVER)
        box.append(scroll)
        self.stack.add_titled_with_icon(box, "buttons", "Nút bấm", "input-mouse-symbolic")

    def _pick_action(self, button: str) -> None:
        def picked(act):
            self.p["buttons"][button] = act
            self.button_rows[button].set_subtitle(actions.describe(act))
            self._push_button(button)
        ActionDialog(profile.BUTTON_NAMES[button], self.p["buttons"][button],
                     sorted(self.state.macros), picked).present(self)

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

    # -- page: DPI -------------------------------------------------------------------------
    def _build_dpi_page(self) -> None:
        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(
            title="Các mức DPI",
            description="Nút DPI chuyển vòng qua các mức đang bật. Chọn ● để đặt mức đang dùng; màu là màu đèn báo của mức đó.")
        self.dpi_widgets = []
        radio_group = None
        for i in range(6):
            row = Adw.ActionRow()
            radio = Gtk.CheckButton(valign=Gtk.Align.CENTER, tooltip_text="Đặt làm mức hiện tại",
                                    label=f"Mức {i + 1}")
            if radio_group:
                radio.set_group(radio_group)
            radio_group = radio_group or radio
            row.add_prefix(radio)
            scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, len(protocol.DPI_VALUES) - 1, 1)
            scale.set_hexpand(True)
            scale.set_size_request(220, -1)
            scale.set_draw_value(False)
            scale.set_valign(Gtk.Align.CENTER)
            for mark in (200, 1600, 3200, 6400, 10000):
                scale.add_mark(protocol.dpi_to_code(mark) - 1, Gtk.PositionType.BOTTOM, None)
            value = Gtk.SpinButton.new_with_range(200, 10000, 50)
            value.set_valign(Gtk.Align.CENTER)
            value.add_css_class("dpi-value")
            color = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(with_alpha=False),
                                          valign=Gtk.Align.CENTER, tooltip_text="Màu đèn báo")
            sw = Gtk.Switch(valign=Gtk.Align.CENTER, tooltip_text="Bật/tắt mức này")
            for w in (scale, value, color, sw):
                row.add_suffix(w)
            group.add(row)
            w = {"row": row, "radio": radio, "scale": scale, "value": value, "color": color, "switch": sw}
            self.dpi_widgets.append(w)
            scale.connect("value-changed", self._on_dpi_scale, i)
            value.connect("value-changed", self._on_dpi_spin, i)
            sw.connect("notify::active", self._on_dpi_switch, i)
            radio.connect("toggled", self._on_dpi_radio, i)
            color.connect("notify::rgba", self._on_dpi_color, i)
        page.add(group)
        info = Adw.PreferencesGroup()
        info.add(Adw.ActionRow(title="Cảm biến PixArt PAW3325",
                               subtitle="200 – 10000 DPI, bước 100 tới 5000 DPI, sau đó theo bảng của cảm biến"))
        page.add(info)
        self.stack.add_titled_with_icon(page, "dpi", "DPI", "find-location-symbolic")

    def _on_dpi_scale(self, scale, i) -> None:
        dpi = protocol.DPI_VALUES[int(round(scale.get_value()))]
        w = self.dpi_widgets[i]
        if int(w["value"].get_value()) != dpi:
            w["value"].set_value(dpi)
        if self.p["dpi"]["values"][i] != dpi:
            self.p["dpi"]["values"][i] = dpi
            self._push_dpi()

    def _on_dpi_spin(self, spin, i) -> None:
        dpi = protocol.snap_dpi(int(spin.get_value()))
        idx = protocol.dpi_to_code(dpi) - 1
        w = self.dpi_widgets[i]
        if int(round(w["scale"].get_value())) != idx:
            w["scale"].set_value(idx)
        elif int(spin.get_value()) != dpi:
            spin.set_value(dpi)

    def _on_dpi_switch(self, sw, _pspec, i) -> None:
        d = self.p["dpi"]
        on = sw.get_active()
        if not on and sum(d["enabled"]) <= 1 and d["enabled"][i]:
            sw.set_active(True)
            self.toast("Phải bật ít nhất một mức DPI")
            return
        self.dpi_widgets[i]["row"].set_sensitive(True)
        for k in ("scale", "value", "radio", "color"):
            self.dpi_widgets[i][k].set_sensitive(on)
        if d["enabled"][i] != on:
            d["enabled"][i] = on
            if not on and d["current"] == i:
                d["current"] = next(j for j in range(6) if d["enabled"][j])
                self.dpi_widgets[d["current"]]["radio"].set_active(True)
            self._push_dpi()

    def _on_dpi_radio(self, radio, i) -> None:
        if radio.get_active() and self.p["dpi"]["current"] != i:
            self.p["dpi"]["current"] = i
            self._push_dpi()
            self._update_tray()

    def _on_dpi_color(self, btn, _pspec, i) -> None:
        c = to_rgb(btn.get_rgba())
        if self.p["dpi"]["colors"][i] != c:
            self.p["dpi"]["colors"][i] = c
            p = copy.deepcopy(self.p)
            self.push("dpi-colors", lambda m: profile.apply_dpi_colors(m, p))

    def _push_dpi(self) -> None:
        p = copy.deepcopy(self.p)
        self.push("dpi", lambda m: profile.apply_dpi(m, p))

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
            self.dpi_widgets[idx]["radio"].set_active(True)
            self._loading = False

    # -- page: lighting ----------------------------------------------------------------------
    def _build_lighting_page(self) -> None:
        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(title="Hiệu ứng đèn")
        self.light_mode = Adw.ComboRow(title="Chế độ",
                                       model=Gtk.StringList.new([n for _, n in LIGHT_MODES]))
        self.light_mode.connect("notify::selected", self._on_light_mode)
        group.add(self.light_mode)
        self.speed_row, self.speed = scale_row("Tốc độ", 1, 3, 2)
        self.speed.connect("value-changed", self._on_light_param, "speed")
        group.add(self.speed_row)
        self.bright_row, self.bright = scale_row("Độ sáng", 1, 4, 4, fmt=lambda v: f"{v * 25}%")
        self.bright.connect("value-changed", self._on_light_param, "brightness")
        group.add(self.bright_row)
        page.add(group)

        self.palette_group = Adw.PreferencesGroup(
            title="Màu nhịp thở",
            description="Bật các màu sẽ được dùng (theo thứ tự). Bấm vào ô màu để đổi màu.")
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=7,
                           min_children_per_line=4, column_spacing=12, row_spacing=12,
                           homogeneous=True)
        self.palette = []
        for i in range(7):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, halign=Gtk.Align.CENTER)
            btn = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(with_alpha=False))
            tog = Gtk.CheckButton(halign=Gtk.Align.CENTER)
            btn.connect("notify::rgba", self._on_palette, i)
            tog.connect("toggled", self._on_palette_toggle, i)
            box.append(btn)
            box.append(tog)
            flow.append(box)
            self.palette.append((tog, btn))
        frame = Gtk.Frame(child=flow, css_classes=["card"])
        flow.set_margin_top(12)
        flow.set_margin_bottom(12)
        flow.set_margin_start(12)
        flow.set_margin_end(12)
        self.palette_group.add(frame)
        page.add(self.palette_group)

        self.steady_group = Adw.PreferencesGroup(title="Màu đứng yên")
        row = Adw.ActionRow(title="Màu")
        self.steady_color = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(with_alpha=False),
                                                  valign=Gtk.Align.CENTER)
        self.steady_color.connect("notify::rgba", self._on_steady_color)
        row.add_suffix(self.steady_color)
        self.steady_group.add(row)
        page.add(self.steady_group)
        self.stack.add_titled_with_icon(page, "lighting", "Đèn LED", "display-brightness-symbolic")

    def _mode(self) -> int:
        return LIGHT_MODES[self.light_mode.get_selected()][0]

    def _update_light_rows(self) -> None:
        mode = self._mode()
        L = self.p["lighting"]
        was = self._loading
        self._loading = True
        self.speed.set_value(int(L["speed"].get(str(mode), 2)))
        self.bright.set_value(int(L["brightness"].get(str(mode), 4)))
        self._loading = was
        self.speed_row.set_visible(mode in (protocol.LIGHT_BREATHING, protocol.LIGHT_NEON))
        self.bright_row.set_visible(mode == protocol.LIGHT_STEADY)
        self.palette_group.set_visible(mode == protocol.LIGHT_BREATHING)
        self.steady_group.set_visible(mode == protocol.LIGHT_STEADY)

    def _push_light(self) -> None:
        p = copy.deepcopy(self.p)
        self.push("light", lambda m: profile.apply_lighting(m, p))

    def _on_light_mode(self, row, _pspec) -> None:
        mode = self._mode()
        self._update_light_rows()
        if self._loading or self.p["lighting"]["mode"] == mode:
            return
        self.p["lighting"]["mode"] = mode
        self._push_light()

    def _on_light_param(self, scale, key) -> None:
        if self._loading:
            return
        self.p["lighting"][key][str(self._mode())] = int(round(scale.get_value()))
        self._push_light()

    def _on_palette(self, btn, _pspec, i) -> None:
        c = to_rgb(btn.get_rgba())
        L = self.p["lighting"]
        if L["palette"][i] != c:
            L["palette"][i] = c
            if L["selected"][i]:
                self._push_light()
            else:
                self.state.save()

    def _on_palette_toggle(self, tog, i) -> None:
        L = self.p["lighting"]
        on = tog.get_active()
        if L["selected"][i] == on:
            return
        if not on and sum(L["selected"]) <= 1:
            tog.set_active(True)
            self.toast("Chọn ít nhất một màu")
            return
        L["selected"][i] = on
        self._push_light()

    def _on_steady_color(self, btn, _pspec) -> None:
        c = to_rgb(btn.get_rgba())
        if self.p["lighting"]["steady_color"] != c:
            self.p["lighting"]["steady_color"] = c
            self._push_light()

    # -- page: performance -----------------------------------------------------------------
    def _build_performance_page(self) -> None:
        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(title="Tần số phản hồi (polling rate)",
                                     description="Tần số cao cho độ trễ thấp hơn nhưng tốn pin hơn.")
        self.polling = Adw.ToggleGroup(halign=Gtk.Align.CENTER, css_classes=["round"],
                                       margin_top=12, margin_bottom=12)
        for hz in (125, 250, 500, 1000):
            self.polling.add(Adw.Toggle(label=f"{hz} Hz", name=str(hz)))
        self.polling.connect("notify::active-name", self._on_polling)
        group.add(self.polling)
        self.polling_row = Adw.ActionRow(title="Chu kỳ báo cáo", css_classes=["property"])
        group.add(self.polling_row)
        page.add(group)
        self.stack.add_titled_with_icon(page, "performance", "Tần số", "power-profile-performance-symbolic")

    def _on_polling(self, tg, _pspec) -> None:
        name = tg.get_active_name()
        if name:
            self.polling_row.set_subtitle(
                f"{protocol.POLLING_RATES[int(name)]} ms — {name} lần mỗi giây")
        if not name or self._loading or int(name) == self.p["polling"]:
            return
        self.p["polling"] = int(name)
        self.push("polling", lambda m: m.set_polling(int(name)), 0)

    # -- page: power -------------------------------------------------------------------------
    def _build_power_page(self) -> None:
        page = Adw.PreferencesPage()
        bat = Adw.PreferencesGroup(title="Pin")
        brow = Gtk.Box(spacing=18, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        self.bat_label = Gtk.Label(label="—", css_classes=["battery-big"])
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, hexpand=True,
                        valign=Gtk.Align.CENTER)
        self.bat_bar = Gtk.LevelBar(min_value=0, max_value=100, hexpand=True)
        self.bat_bar.add_offset_value("low", 20)
        self.bat_bar.add_offset_value("high", 50)
        self.bat_state = Gtk.Label(xalign=0, css_classes=["dim-label"])
        right.append(self.bat_bar)
        right.append(self.bat_state)
        brow.append(self.bat_label)
        brow.append(right)
        bat.add(Gtk.Frame(child=brow, css_classes=["card"]))
        page.add(bat)

        group = Adw.PreferencesGroup(title="Quản lý nguồn")
        row, self.sleep_scale = scale_row("Tự ngủ sau", 3, 10, 6, fmt=lambda v: f"{v} phút",
                                          subtitle="Thời gian không dùng trước khi chuột tắt")
        self.sleep_scale.connect("value-changed", lambda *_: self._on_power())
        group.add(row)
        self.light_off_row = Adw.SwitchRow(title="Tắt đèn khi di chuột",
                                           subtitle="Tiết kiệm pin khi đang sử dụng")
        self.light_off_row.connect("notify::active", lambda *_: self._on_power())
        group.add(self.light_off_row)
        self.wakeup_row = Adw.SwitchRow(title="Di chuyển để đánh thức",
                                        subtitle="Tắt thì phải bấm nút để đánh thức chuột")
        self.wakeup_row.connect("notify::active", lambda *_: self._on_wakeup())
        group.add(self.wakeup_row)
        page.add(group)
        self.stack.add_titled_with_icon(page, "power", "Nguồn", "battery-good-symbolic")

    def _on_power(self) -> None:
        if self._loading:
            return
        pw = self.p["power"]
        pw["sleep"] = int(round(self.sleep_scale.get_value()))
        pw["light_off_moving"] = self.light_off_row.get_active()
        s, l = pw["sleep"], pw["light_off_moving"]
        self.push("power", lambda m: m.set_power(s, l))

    def _on_wakeup(self) -> None:
        if self._loading:
            return
        on = self.wakeup_row.get_active()
        self.p["power"]["motion_wakeup"] = on
        self.push("wakeup", lambda m: m.set_motion_wakeup(on), 0)

    # -- page: device ------------------------------------------------------------------------
    def _build_device_page(self) -> None:
        page = Adw.PreferencesPage()
        g = Adw.PreferencesGroup(title="Thiết bị")
        self.dev_rows = {}
        for key, title in (("model", "Mẫu"), ("conn", "Kết nối"), ("sensor", "Cảm biến"),
                           ("fw", "Firmware"), ("node", "Giao diện HID")):
            r = Adw.ActionRow(title=title, subtitle="—", css_classes=["property"])
            self.dev_rows[key] = r
            g.add(r)
        page.add(g)
        g = Adw.PreferencesGroup(title="Thao tác")
        apply = Adw.ButtonRow(title="Ghi toàn bộ hồ sơ vào chuột", start_icon_name="document-send-symbolic")
        apply.connect("activated", lambda *_: self._apply_all())
        g.add(apply)
        reset = Adw.ButtonRow(title="Khôi phục cài đặt gốc của chuột", start_icon_name="edit-undo-symbolic")
        reset.add_css_class("destructive-action")
        reset.connect("activated", lambda *_: self._factory_reset())
        g.add(reset)
        page.add(g)
        self.stack.add_titled_with_icon(page, "device", "Thiết bị", "computer-symbolic")

    def _update_device_page(self) -> None:
        info = self.info
        r = self.dev_rows
        if info is None:
            for k in r:
                r[k].set_subtitle("—")
            r["conn"].set_subtitle("Không kết nối")
            self.bat_label.set_text("—")
            self.bat_bar.set_value(0)
            self.bat_state.set_text("Không kết nối")
            return
        node = getattr(self.worker._mouse, "node", None)
        r["model"].set_subtitle(f"Nplay AIM ({info.model})")
        mode = {"wireless": "Đầu thu không dây 2.4 GHz", "wired": "Cáp USB"}.get(node.mode if node else "", "?")
        r["conn"].set_subtitle(f"{mode} — chuột {'đang hoạt động' if info.online else 'đang ngủ/tắt'}")
        r["sensor"].set_subtitle(info.sensor_name)
        r["fw"].set_subtitle(info.firmware)
        r["node"].set_subtitle(node.path if node else "—")
        self.bat_label.set_text(f"{info.battery}%" if info.online else "—")
        self.bat_bar.set_value(info.battery if info.online else 0)
        self.bat_state.set_text({1: "Đang sạc", 2: "Đã sạc đầy"}.get(info.charging, "Đang dùng pin")
                                if info.online else "Chuột ngoại tuyến")

    def _factory_reset(self) -> None:
        dlg = Adw.AlertDialog(heading="Khôi phục cài đặt gốc?",
                              body="Chuột sẽ trở về thiết lập của nhà sản xuất và hồ sơ hiện tại cũng được đặt lại.")
        dlg.add_response("cancel", "Hủy")
        dlg.add_response("reset", "Khôi phục")
        dlg.set_response_appearance("reset", Adw.ResponseAppearance.DESTRUCTIVE)

        def resp(d, rsp):
            if rsp != "reset":
                return
            self.state.profiles[self.state.current] = profile.default_profile(self.p["name"])
            self.state.save()
            self._load_profile()
            self.worker.submit(lambda m: m.factory_reset(),
                               lambda _r, err: self._on_info(None, err) if err else self.toast("Đã khôi phục cài đặt gốc"))
        dlg.connect("response", resp)
        dlg.present(self)


class App(Adw.Application):
    def __init__(self, background: bool = False):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.background = background

    def do_startup(self):
        Adw.Application.do_startup(self)
        css = Gtk.CssProvider()
        css.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.PREFER_DARK)

    def do_activate(self):
        wins = self.get_windows()
        if wins:
            wins[0].show_window()
            return
        win = Window(self)
        if not self.background:
            win.present()
            return
        # Started at login: stay in the tray; fall back to a window if there is no tray.
        GLib.timeout_add_seconds(3, lambda: None if win.tray.available else win.present())


def main(background: bool = False) -> int:
    return App(background).run(None)
