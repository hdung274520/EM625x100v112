"""Profiles (5 slots, like the vendor tool) and the shared macro library, stored as JSON."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path

from . import actions, macro, protocol

CONFIG_DIR = Path(os.environ.get("APPDATA") or os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "nplayaim"
STATE_FILE = CONFIG_DIR / "state.json"
PROFILE_COUNT = 5
BUTTON_ORDER = ["left", "right", "middle", "forward", "back", "dpi"]
BUTTON_NAMES = {"left": "Nút trái", "right": "Nút phải", "middle": "Nút giữa (cuộn)",
                "forward": "Nút bên trước", "back": "Nút bên sau", "dpi": "Nút DPI"}

DEFAULT_PALETTE = [[255, 0, 0], [0, 255, 0], [0, 0, 255], [0, 255, 255],
                   [255, 255, 0], [255, 0, 255], [255, 255, 255]]


def default_profile(name: str) -> dict:
    """Factory settings of the mouse (what the firmware restores to)."""
    return {
        "name": name,
        "buttons": copy.deepcopy(actions.DEFAULT_ACTIONS),
        "dpi": {
            "values": [800, 1600, 2400, 3200, 6400, 10000],
            "enabled": [True] * 6,
            "current": 1,
            "colors": [[255, 0, 0], [0, 255, 0], [0, 0, 255], [0, 255, 255],
                       [255, 255, 0], [255, 0, 255], [255, 255, 255], [255, 255, 255]],
        },
        "polling": 500,
        "lighting": {
            "mode": protocol.LIGHT_BREATHING,
            "speed": {"0": 2, "2": 2, "3": 2, "4": 2},
            "brightness": {"0": 2, "2": 2, "3": 4, "4": 2},
            "palette": copy.deepcopy(DEFAULT_PALETTE),
            "selected": [True] * 7,
            "steady_color": [255, 0, 255],
        },
        "power": {"sleep": 6, "light_off_moving": False, "motion_wakeup": True},
    }


class State:
    def __init__(self) -> None:
        self.current = 0
        self.profiles = [default_profile(f"Hồ sơ {i + 1}") for i in range(PROFILE_COUNT)]
        self.macros: dict[str, dict] = {}
        self.settings = {"notify_dpi": False, "notify_battery": True, "dpi_label": "flash"}
        self.load()

    @property
    def profile(self) -> dict:
        return self.profiles[self.current]

    def load(self) -> None:
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.current = int(data.get("current", 0)) % PROFILE_COUNT
        for i, p in enumerate(data.get("profiles", [])[:PROFILE_COUNT]):
            base = default_profile(p.get("name", f"Hồ sơ {i + 1}"))
            _merge(base, p)
            self.profiles[i] = base
        self.macros = data.get("macros", {})
        self.settings.update(data.get("settings", {}))

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps({"current": self.current, "profiles": self.profiles,
                                   "macros": self.macros,
                                   "settings": self.settings}, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        tmp.replace(STATE_FILE)

    def macro_slots(self, profile: dict | None = None) -> dict[str, int]:
        """Button -> firmware macro slot (1-based, sequential like the vendor tool)."""
        p = profile or self.profile
        slots, n = {}, 1
        for b in BUTTON_ORDER:
            if p["buttons"][b].get("kind") == "macro":
                slots[b] = n
                n += 1
        return slots


def _merge(base: dict, new: dict) -> None:
    for k, v in new.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v


# -- pushing settings to the mouse -------------------------------------------------

def apply_dpi(mouse: protocol.Mouse, p: dict) -> None:
    d = p["dpi"]
    mouse.set_dpi(d["values"], d["enabled"], d["current"])


def apply_dpi_colors(mouse: protocol.Mouse, p: dict) -> None:
    mouse.set_dpi_colors([tuple(c) for c in p["dpi"]["colors"]])


def apply_lighting(mouse: protocol.Mouse, p: dict) -> None:
    L = p["lighting"]
    mode = int(L["mode"])
    colors = None
    if mode == protocol.LIGHT_BREATHING:
        colors = [tuple(c) for c, on in zip(L["palette"], L["selected"]) if on]
    elif mode == protocol.LIGHT_STEADY:
        colors = [tuple(L["steady_color"])]
    mouse.set_lighting(mode, int(L["speed"].get(str(mode), 2)),
                       int(L["brightness"].get(str(mode), 2)), colors)


def apply_power(mouse: protocol.Mouse, p: dict) -> None:
    pw = p["power"]
    mouse.set_power(int(pw["sleep"]), bool(pw["light_off_moving"]))
    mouse.set_motion_wakeup(bool(pw["motion_wakeup"]))


def apply_button(mouse: protocol.Mouse, state: State, p: dict, button: str) -> None:
    act = p["buttons"][button]
    slot = state.macro_slots(p).get(button, 1)
    if act.get("kind") == "macro":
        m = state.macros.get(act.get("macro", ""))
        mouse.upload_macro(slot, macro.encode_events(m["events"] if m else []))
    mouse.set_key(button, actions.encode(act, slot))


def apply_all(mouse: protocol.Mouse, state: State, p: dict | None = None) -> None:
    p = p or state.profile
    apply_dpi(mouse, p)
    apply_dpi_colors(mouse, p)
    mouse.set_polling(int(p["polling"]))
    apply_lighting(mouse, p)
    apply_power(mouse, p)
    for b in BUTTON_ORDER:
        apply_button(mouse, state, p, b)
