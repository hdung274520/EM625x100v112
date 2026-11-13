"""System-tray icon (StatusNotifierItem + com.canonical.dbusmenu) and desktop notifications,
implemented directly over D-Bus so it works next to GTK4 without extra libraries."""

from __future__ import annotations

import os
from typing import Callable

from gi.repository import Gio, GLib

SNI_XML = """
<node>
 <interface name="org.kde.StatusNotifierItem">
  <property name="Category" type="s" access="read"/>
  <property name="Id" type="s" access="read"/>
  <property name="Title" type="s" access="read"/>
  <property name="Status" type="s" access="read"/>
  <property name="IconName" type="s" access="read"/>
  <property name="IconThemePath" type="s" access="read"/>
  <property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
  <property name="ItemIsMenu" type="b" access="read"/>
  <property name="Menu" type="o" access="read"/>
  <property name="XAyatanaLabel" type="s" access="read"/>
  <property name="XAyatanaLabelGuide" type="s" access="read"/>
  <method name="Activate"><arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/></method>
  <method name="SecondaryActivate"><arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/></method>
  <method name="ContextMenu"><arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/></method>
  <method name="Scroll"><arg name="delta" type="i" direction="in"/><arg name="orientation" type="s" direction="in"/></method>
  <signal name="NewTitle"/>
  <signal name="NewIcon"/>
  <signal name="NewToolTip"/>
  <signal name="NewStatus"><arg name="status" type="s"/></signal>
  <signal name="XAyatanaNewLabel"><arg name="label" type="s"/><arg name="guide" type="s"/></signal>
 </interface>
</node>
"""

MENU_XML = """
<node>
 <interface name="com.canonical.dbusmenu">
  <property name="Version" type="u" access="read"/>
  <property name="TextDirection" type="s" access="read"/>
  <property name="Status" type="s" access="read"/>
  <property name="IconThemePath" type="as" access="read"/>
  <method name="GetLayout">
   <arg type="i" name="parentId" direction="in"/><arg type="i" name="recursionDepth" direction="in"/>
   <arg type="as" name="propertyNames" direction="in"/>
   <arg type="u" name="revision" direction="out"/><arg type="(ia{sv}av)" name="layout" direction="out"/>
  </method>
  <method name="GetGroupProperties">
   <arg type="ai" name="ids" direction="in"/><arg type="as" name="propertyNames" direction="in"/>
   <arg type="a(ia{sv})" name="properties" direction="out"/>
  </method>
  <method name="GetProperty">
   <arg type="i" name="id" direction="in"/><arg type="s" name="name" direction="in"/>
   <arg type="v" name="value" direction="out"/>
  </method>
  <method name="Event">
   <arg type="i" name="id" direction="in"/><arg type="s" name="eventId" direction="in"/>
   <arg type="v" name="data" direction="in"/><arg type="u" name="timestamp" direction="in"/>
  </method>
  <method name="EventGroup">
   <arg type="a(isvu)" name="events" direction="in"/><arg type="ai" name="idErrors" direction="out"/>
  </method>
  <method name="AboutToShow">
   <arg type="i" name="id" direction="in"/><arg type="b" name="needUpdate" direction="out"/>
  </method>
  <method name="AboutToShowGroup">
   <arg type="ai" name="ids" direction="in"/>
   <arg type="ai" name="updatesNeeded" direction="out"/><arg type="ai" name="idErrors" direction="out"/>
  </method>
  <signal name="LayoutUpdated"><arg type="u" name="revision"/><arg type="i" name="parent"/></signal>
  <signal name="ItemsPropertiesUpdated">
   <arg type="a(ia{sv})" name="updatedProps"/><arg type="a(ias)" name="removedProps"/>
  </signal>
 </interface>
</node>
"""

SNI_PATH = "/StatusNotifierItem"
MENU_PATH = "/MenuBar"


class MenuItem:
    def __init__(self, label: str = "", action: Callable[[], None] | None = None, *,
                 enabled: bool = True, radio: bool | None = None, check: bool | None = None,
                 separator: bool = False, icon: str | None = None,
                 children: list["MenuItem"] | None = None):
        self.label, self.action, self.enabled = label, action, enabled
        self.radio, self.check, self.separator, self.icon = radio, check, separator, icon
        self.children = children or []
        self.id = 0

    def props(self) -> dict:
        if self.separator:
            return {"type": GLib.Variant("s", "separator")}
        p = {"label": GLib.Variant("s", self.label), "enabled": GLib.Variant("b", self.enabled)}
        if self.radio is not None:
            p["toggle-type"] = GLib.Variant("s", "radio")
            p["toggle-state"] = GLib.Variant("i", int(self.radio))
        elif self.check is not None:
            p["toggle-type"] = GLib.Variant("s", "checkmark")
            p["toggle-state"] = GLib.Variant("i", int(self.check))
        if self.icon:
            p["icon-name"] = GLib.Variant("s", self.icon)
        if self.children:
            p["children-display"] = GLib.Variant("s", "submenu")
        return p


class TrayIcon:
    """Registers with org.kde.StatusNotifierWatcher (Ubuntu AppIndicators / KDE / XFCE)."""

    def __init__(self, app_id: str, title: str, icon: str, on_activate: Callable[[], None]):
        self.app_id, self.title, self.icon = app_id, title, icon
        self.tooltip = title
        self.label = ""
        self.on_activate = on_activate
        self.root = MenuItem(children=[])
        self._items: dict[int, MenuItem] = {}
        self._revision = 1
        self._bus: Gio.DBusConnection | None = None
        self._ids: list[int] = []
        self._name = f"org.kde.StatusNotifierItem-{os.getpid()}-1"
        self.available = False
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except GLib.Error:
            return
        sni = Gio.DBusNodeInfo.new_for_xml(SNI_XML).interfaces[0]
        menu = Gio.DBusNodeInfo.new_for_xml(MENU_XML).interfaces[0]
        self._ids.append(self._bus.register_object(SNI_PATH, sni, self._sni_call, self._sni_prop, None))
        self._ids.append(self._bus.register_object(MENU_PATH, menu, self._menu_call, self._menu_prop, None))
        Gio.bus_own_name_on_connection(self._bus, self._name, Gio.BusNameOwnerFlags.NONE, None, None)
        self._watch = Gio.bus_watch_name_on_connection(
            self._bus, "org.kde.StatusNotifierWatcher", Gio.BusNameWatcherFlags.NONE,
            self._on_watcher, lambda *_: setattr(self, "available", False))

    def _on_watcher(self, conn, name, owner) -> None:
        conn.call("org.kde.StatusNotifierWatcher", "/StatusNotifierWatcher",
                  "org.kde.StatusNotifierWatcher", "RegisterStatusNotifierItem",
                  GLib.Variant("(s)", (self._name,)), None, Gio.DBusCallFlags.NONE, -1, None,
                  lambda c, res: self._registered(c, res))

    def _registered(self, conn, res) -> None:
        try:
            conn.call_finish(res)
            self.available = True
        except GLib.Error:
            self.available = False

    # -- public API -------------------------------------------------------------------
    def set_menu(self, items: list[MenuItem]) -> None:
        self.root = MenuItem(children=items)
        self._items = {}
        n = [1]

        def number(it):
            for c in it.children:
                c.id = n[0]
                self._items[c.id] = c
                n[0] += 1
                number(c)
        number(self.root)
        self._revision += 1
        self._emit(MENU_PATH, "com.canonical.dbusmenu", "LayoutUpdated",
                   GLib.Variant("(ui)", (self._revision, 0)))

    def set_tooltip(self, text: str) -> None:
        if text != self.tooltip:
            self.tooltip = text
            self._emit(SNI_PATH, "org.kde.StatusNotifierItem", "NewToolTip", None)
            self._emit(SNI_PATH, "org.kde.StatusNotifierItem", "NewTitle", None)

    def set_label(self, text: str) -> None:
        """Text shown right next to the icon in the panel (Ubuntu AppIndicators / Ayatana)."""
        if text != self.label:
            self.label = text
            self._emit(SNI_PATH, "org.kde.StatusNotifierItem", "XAyatanaNewLabel",
                       GLib.Variant("(ss)", (text, "10000 DPI")))

    def set_icon(self, icon: str) -> None:
        if icon != self.icon:
            self.icon = icon
            self._emit(SNI_PATH, "org.kde.StatusNotifierItem", "NewIcon", None)

    def _emit(self, path, iface, signal, params) -> None:
        if self._bus:
            self._bus.emit_signal(None, path, iface, signal, params)

    # -- StatusNotifierItem ---------------------------------------------------------------
    def _sni_prop(self, conn, sender, path, iface, prop):
        return {
            "Category": GLib.Variant("s", "Hardware"),
            "Id": GLib.Variant("s", self.app_id),
            "Title": GLib.Variant("s", self.tooltip),
            "Status": GLib.Variant("s", "Active"),
            "IconName": GLib.Variant("s", self.icon),
            "IconThemePath": GLib.Variant("s", ""),
            "ToolTip": GLib.Variant("(sa(iiay)ss)", (self.icon, [], self.title, self.tooltip)),
            "ItemIsMenu": GLib.Variant("b", False),
            "Menu": GLib.Variant("o", MENU_PATH),
            "XAyatanaLabel": GLib.Variant("s", self.label),
            "XAyatanaLabelGuide": GLib.Variant("s", "10000 DPI"),
        }.get(prop)

    def _sni_call(self, conn, sender, path, iface, method, params, inv) -> None:
        if method in ("Activate", "SecondaryActivate"):
            GLib.idle_add(lambda: self.on_activate() and False)
        inv.return_value(None)

    # -- dbusmenu ------------------------------------------------------------------------
    def _layout(self, item: MenuItem, depth: int) -> GLib.Variant:
        children = []
        if depth != 0:
            children = [self._layout(c, depth - 1) for c in item.children]
        props = item.props() if item.id else {"children-display": GLib.Variant("s", "submenu")}
        return GLib.Variant("(ia{sv}av)", (item.id, props, children))

    def _menu_prop(self, conn, sender, path, iface, prop):
        return {"Version": GLib.Variant("u", 3), "TextDirection": GLib.Variant("s", "ltr"),
                "Status": GLib.Variant("s", "normal"),
                "IconThemePath": GLib.Variant("as", [])}.get(prop)

    def _menu_call(self, conn, sender, path, iface, method, params, inv) -> None:
        args = params.unpack()
        if method == "GetLayout":
            parent, depth = args[0], args[1]
            item = self.root if parent == 0 else self._items.get(parent, self.root)
            inv.return_value(GLib.Variant.new_tuple(GLib.Variant("u", self._revision),
                                                    self._layout(item, depth)))
        elif method == "GetGroupProperties":
            ids = args[0] or list(self._items)
            out = [(i, self._items[i].props()) for i in ids if i in self._items]
            inv.return_value(GLib.Variant("(a(ia{sv}))", (out,)))
        elif method == "GetProperty":
            it = self._items.get(args[0])
            val = it.props().get(args[1]) if it else None
            inv.return_value(GLib.Variant("(v)", (val or GLib.Variant("s", ""),)))
        elif method == "Event":
            self._event(args[0], args[1])
            inv.return_value(None)
        elif method == "EventGroup":
            for ev in args[0]:
                self._event(ev[0], ev[1])
            inv.return_value(GLib.Variant("(ai)", ([],)))
        elif method == "AboutToShow":
            inv.return_value(GLib.Variant("(b)", (False,)))
        elif method == "AboutToShowGroup":
            inv.return_value(GLib.Variant("(aiai)", ([], [])))
        else:
            inv.return_value(None)

    def _event(self, item_id: int, event: str) -> None:
        it = self._items.get(item_id)
        if event == "clicked" and it and it.action and it.enabled:
            GLib.idle_add(lambda: it.action() and False)


class Notifier:
    """org.freedesktop.Notifications with in-place replacement (one bubble per topic)."""

    def __init__(self, app_name: str, desktop_entry: str):
        self.app_name, self.desktop_entry = app_name, desktop_entry
        self._ids: dict[str, int] = {}
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except GLib.Error:
            self._bus = None

    def notify(self, topic: str, summary: str, body: str = "", icon: str = "input-mouse",
               timeout_ms: int = 2000, transient: bool = True, urgency: int = 1) -> None:
        if not self._bus:
            return
        hints = {"desktop-entry": GLib.Variant("s", self.desktop_entry),
                 "urgency": GLib.Variant("y", urgency),
                 "category": GLib.Variant("s", "device")}
        if transient:
            hints["transient"] = GLib.Variant("b", True)
        params = GLib.Variant("(susssasa{sv}i)", (self.app_name, self._ids.get(topic, 0), icon,
                                                  summary, body, [], hints, timeout_ms))

        def done(conn, res):
            try:
                self._ids[topic] = conn.call_finish(res).unpack()[0]
            except GLib.Error:
                pass
        self._bus.call("org.freedesktop.Notifications", "/org/freedesktop/Notifications",
                       "org.freedesktop.Notifications", "Notify", params, GLib.VariantType("(u)"),
                       Gio.DBusCallFlags.NONE, -1, None, done)
