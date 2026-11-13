"""Button functions: catalog, 3-byte firmware encoding and display text."""

from __future__ import annotations

from .hidkeys import combo_name

MOUSE_BUTTONS = {"left": 0x01, "right": 0x02, "middle": 0x04, "back": 0x08, "forward": 0x10}
MOUSE_NAMES = {"left": "Chuột trái", "right": "Chuột phải", "middle": "Chuột giữa",
               "back": "Lùi lại", "forward": "Tiến tới"}

DPI_OPS = {"loop": 0x01, "up": 0x02, "down": 0x03}
DPI_OP_NAMES = {"loop": "DPI vòng lặp", "up": "DPI tăng", "down": "DPI giảm"}

DPI_LOCK_VALUES = list(range(200, 1300, 100))  # 200..1200

# Consumer-page usages offered by the vendor tool
MEDIA = [
    (0x0183, "Trình phát media"),
    (0x00B6, "Bài trước"),
    (0x00B5, "Bài tiếp theo"),
    (0x00B7, "Dừng"),
    (0x00CD, "Phát / Tạm dừng"),
    (0x00E2, "Tắt tiếng"),
    (0x00E9, "Tăng âm lượng"),
    (0x00EA, "Giảm âm lượng"),
    (0x018A, "Thư điện tử"),
    (0x0192, "Máy tính bỏ túi"),
    (0x0194, "Trình quản lý tệp"),
]
MEDIA_NAMES = dict(MEDIA)

# Shortcut presets (modifier bits, HID usage)
OFFICE = [
    ("Sao chép", 0x01, 0x06), ("Dán", 0x01, 0x19), ("Cắt", 0x01, 0x1B),
    ("Chọn tất cả", 0x01, 0x04), ("Tạo mới", 0x01, 0x11), ("Lưu", 0x01, 0x16),
    ("In", 0x01, 0x13), ("Mở (Win+E)", 0x08, 0x08), ("Hoàn tác", 0x01, 0x1D),
]
WINDOW = [
    ("Đóng cửa sổ (Alt+F4)", 0x04, 0x3D), ("Hiện màn hình nền (Win+D)", 0x08, 0x07),
    ("Chạy (Win+R)", 0x08, 0x15), ("Thu nhỏ (Win+↓)", 0x08, 0x51),
    ("Phóng to (Win+↑)", 0x08, 0x52),
]

MACRO_MODES = {"count": 2, "until_release": 1, "toggle": 4}
MACRO_MODE_NAMES = {"count": "Lặp số lần chỉ định", "until_release": "Lặp tới khi nhả nút",
                    "toggle": "Lặp tới khi nhấn lại"}

DEFAULT_ACTIONS = {
    "left": {"kind": "mouse", "button": "left"},
    "right": {"kind": "mouse", "button": "right"},
    "middle": {"kind": "mouse", "button": "middle"},
    "forward": {"kind": "mouse", "button": "forward"},
    "back": {"kind": "mouse", "button": "back"},
    "dpi": {"kind": "dpi", "op": "loop"},
}


def encode(action: dict, macro_slot: int = 1) -> bytes:
    k = action.get("kind")
    if k == "mouse":
        return bytes([0x10, MOUSE_BUTTONS[action["button"]], 0])
    if k == "fire":
        return bytes([0x30, max(5, min(255, int(action.get("interval", 50)))),
                      max(0, min(255, int(action.get("loops", 0))))])
    if k == "triple":
        return bytes([0x30, 0x32, 0x03])
    if k == "dpi":
        return bytes([0x40, DPI_OPS[action["op"]], 0])
    if k == "dpi_lock":
        return bytes([0x50, int(action["dpi"]) // 100 - 1, 0])
    if k == "switch_effect":
        return bytes([0x60, 0x04, 0])
    if k == "combo":
        return bytes([0x70, int(action.get("mods", 0)) & 0xFF, int(action.get("key", 0)) & 0xFF])
    if k == "media":
        u = int(action["usage"])
        return bytes([0x80, u & 0xFF, u >> 8])
    if k == "macro":
        mode = MACRO_MODES[action.get("mode", "count")]
        count = int(action.get("count", 1)) if mode == 2 else 0
        return bytes([0x90, (mode << 4) | (macro_slot & 0x0F), max(0, min(255, count))])
    return bytes(3)  # disabled


def describe(action: dict) -> str:
    k = action.get("kind")
    if k == "mouse":
        return MOUSE_NAMES[action["button"]]
    if k == "fire":
        loops = int(action.get("loops", 0))
        return f"Phím bắn ({action.get('interval', 50)} ms, {'giữ' if loops == 0 else f'{loops} lần'})"
    if k == "triple":
        return "Nhấn ba lần"
    if k == "dpi":
        return DPI_OP_NAMES[action["op"]]
    if k == "dpi_lock":
        return f"Khóa DPI {action['dpi']}"
    if k == "switch_effect":
        return "Chuyển hiệu ứng đèn"
    if k == "combo":
        label = action.get("label")
        text = combo_name(int(action.get("mods", 0)), int(action.get("key", 0)))
        return f"{label} — {text}" if label else text
    if k == "media":
        return MEDIA_NAMES.get(int(action["usage"]), f"Media 0x{int(action['usage']):04X}")
    if k == "macro":
        return f"Macro: {action.get('macro', '?')}"
    return "Tắt"
