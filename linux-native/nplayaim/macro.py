"""Macro events and their 3-byte firmware encoding.

Each event:  [flags | type | delay_hi4, delay_lo8, code]
    flags  0x80 = release
    type   0x30 key, 0x20 modifier (code = bit mask), 0x10 mouse button (code = bit mask),
           0x40 move X, 0x50 move Y, 0x60 wheel (code = signed 8-bit amount)
    delay  milliseconds to wait after this event (0..4095)
"""

from __future__ import annotations

from .actions import MOUSE_BUTTONS, MOUSE_NAMES
from .hidkeys import MODIFIER_BITS, key_name

MAX_DELAY = 4095
MAX_EVENTS = 125  # 15 chunks x 25 bytes / 3

MOVE_TYPES = {"x": 0x40, "y": 0x50, "wheel": 0x60}


def encode_event(ev: dict) -> bytes:
    delay = max(0, min(MAX_DELAY, int(ev.get("delay", 0))))
    flags = 0x80 if not ev.get("down", True) else 0
    t = ev["t"]
    if t == "key":
        code = int(ev["code"])
        if code in MODIFIER_BITS:
            typ, val = 0x20, MODIFIER_BITS[code]
        else:
            typ, val = 0x30, code
    elif t == "mouse":
        typ, val = 0x10, MOUSE_BUTTONS[ev["button"]]
    elif t == "move":
        typ, val = MOVE_TYPES[ev["axis"]], int(ev["value"]) & 0xFF
        flags = 0
    else:
        raise ValueError(f"unknown macro event {t}")
    return bytes([flags | typ | (delay >> 8), delay & 0xFF, val])


def encode_events(events: list[dict]) -> bytes:
    return b"".join(encode_event(e) for e in events[:MAX_EVENTS])


def describe_event(ev: dict) -> str:
    t = ev["t"]
    if t == "key":
        what = key_name(int(ev["code"]))
    elif t == "mouse":
        what = MOUSE_NAMES[ev["button"]]
    else:
        axis = {"x": "Di chuyển ngang", "y": "Di chuyển dọc", "wheel": "Cuộn"}[ev["axis"]]
        return f"{axis} {int(ev['value']):+d}"
    return f"{'↓ Nhấn' if ev.get('down', True) else '↑ Nhả'} {what}"
