"""HID protocol of the NPLAYAIM10 / M220 gaming mouse (VID 0x248a, PID 0x5b2e wired, 0x5b2f dongle).

Reverse engineered from the vendor's Windows tool (GamingMS.exe) and verified against
feature reports captured from it.  Every command is a 33-byte feature report:

    [0]  0x0c          report id
    [1]  0x01          target = mouse
    [2]  cmd
    [3]  0x00
    [4]  seq           rolling counter
    [5]  sub           0x01 for normal commands; (chunk<<4 | chunks) for macro uploads
    [6]  len           number of payload bytes that follow
    [7:] payload
"""

from __future__ import annotations

import errno
import glob
import os
import struct
import sys
import threading
import time

if sys.platform != "win32":
    import fcntl  # Linux hidraw backend; Windows uses nplayaim_win.hidwin
from dataclasses import dataclass

VENDOR_ID = 0x248A
PRODUCT_IDS = {0x5B2E: "wired", 0x5B2F: "wireless"}
REPORT_ID = 0x0C
REPORT_LEN = 33
WRITE_DELAY = 0.06  # the vendor tool sleeps 60 ms after every report

CMD_KEY = 0x04
CMD_DPI = 0x05
CMD_DPI_COLORS = 0x06
CMD_POLLING = 0x07
CMD_LIGHTING = 0x08
CMD_POWER = 0x0B
CMD_MOTION_WAKEUP = 0x0C
CMD_MACRO = 0x0E
CMD_FACTORY_RESET = 0x0F
CMD_INFO = 0x20

# Physical button -> firmware key slot (HID button bit order).
BUTTON_SLOTS = {"left": 0, "right": 1, "middle": 2, "back": 3, "forward": 4, "dpi": 5}

# DPI steps for sensor PAW3325 (sensor code 0x25).  DPI = step * 50, device code = index + 1.
DPI_STEPS_3325 = [4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32, 34, 36, 38, 40, 42,
                  44, 46, 48, 50, 52, 54, 56, 58, 60, 62, 64, 66, 68, 70, 72, 74, 76, 78, 80, 82,
                  84, 86, 88, 90, 92, 94, 96, 98, 100, 110, 120, 128, 140, 150, 160, 170, 180,
                  190, 200]
DPI_VALUES = [s * 50 for s in DPI_STEPS_3325]

POLLING_RATES = {125: 8, 250: 4, 500: 2, 1000: 1}  # Hz -> report interval in ms

LIGHT_OFF, LIGHT_BREATHING, LIGHT_STEADY, LIGHT_NEON = 0, 2, 3, 4

SENSORS = {0x04: "PAW3104", 0x25: "PAW3325", 0x27: "PAW3327", 0x12: "PAW3212"}


def _ioc(direction: int, nr: int, size: int) -> int:
    return (direction << 30) | (size << 16) | (ord("H") << 8) | nr


HIDIOCSFEATURE = _ioc(3, 0x06, REPORT_LEN)
HIDIOCGFEATURE = _ioc(3, 0x07, REPORT_LEN)
HIDIOCGRDESCSIZE = _ioc(2, 0x01, 4)
HIDIOCGRDESC = _ioc(2, 0x02, 4 + 4096)


class DeviceError(Exception):
    pass


@dataclass
class DeviceInfo:
    model: str
    sensor: int
    firmware: str
    battery: int
    charging: int  # 0 = no, 1 = charging, 2 = full
    online: bool
    dpi_current: int  # 1-based index among enabled levels
    dpi_count: int

    @property
    def sensor_name(self) -> str:
        return SENSORS.get(self.sensor, f"0x{self.sensor:02x}")


def dpi_to_code(dpi: int) -> int:
    """Nearest supported DPI -> device code."""
    idx = min(range(len(DPI_VALUES)), key=lambda i: abs(DPI_VALUES[i] - dpi))
    return idx + 1


def snap_dpi(dpi: int) -> int:
    return DPI_VALUES[dpi_to_code(dpi) - 1]


@dataclass
class HidrawNode:
    path: str
    product_id: int
    mode: str


def _report_descriptor(fd: int) -> bytes:
    size = struct.unpack("<I", fcntl.ioctl(fd, HIDIOCGRDESCSIZE, b"\0" * 4))[0]
    buf = bytearray(struct.pack("<I", size) + b"\0" * 4096)
    fcntl.ioctl(fd, HIDIOCGRDESC, buf)
    return bytes(buf[4:4 + size])


def find_devices() -> list[HidrawNode]:
    """hidraw nodes that expose the 32-byte vendor feature report 0x0c."""
    found = []
    for sys_path in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        try:
            with open(os.path.join(sys_path, "device", "uevent")) as f:
                uevent = f.read()
        except OSError:
            continue
        hid_id = next((l.split("=", 1)[1] for l in uevent.splitlines() if l.startswith("HID_ID=")), "")
        parts = hid_id.split(":")
        if len(parts) != 3:
            continue
        vid, pid = int(parts[1], 16), int(parts[2], 16)
        if vid != VENDOR_ID or pid not in PRODUCT_IDS:
            continue
        dev = "/dev/" + os.path.basename(sys_path)
        try:
            fd = os.open(dev, os.O_RDWR)
        except OSError as e:
            if e.errno in (errno.EACCES, errno.EPERM):
                found.append(HidrawNode(dev, pid, "no-permission"))
            continue
        try:
            desc = _report_descriptor(fd)
        finally:
            os.close(fd)
        # Vendor page 0xff00 with "Report ID (12)" and a feature main item.
        if b"\x06\x00\xff" in desc and b"\x85\x0c" in desc and b"\xb1\x02" in desc:
            found.append(HidrawNode(dev, pid, PRODUCT_IDS[pid]))
    # Prefer the receiver/wired node we can open; wired first if both are present.
    found.sort(key=lambda n: (n.mode == "no-permission", n.product_id != 0x5B2E))
    return found


class Mouse:
    """Thread-safe handle to the mouse's vendor HID interface."""

    def __init__(self, node: HidrawNode):
        if node.mode == "no-permission":
            raise DeviceError(f"Không có quyền truy cập {node.path} (cần cài udev rule)")
        self.node = node
        self._fd = os.open(node.path, os.O_RDWR)
        self._seq = 1
        self._lock = threading.Lock()

    @classmethod
    def open_first(cls) -> "Mouse":
        nodes = find_devices()
        if not nodes:
            raise DeviceError("Không tìm thấy chuột (248a:5b2e / 248a:5b2f)")
        return cls(nodes[0])

    def close(self) -> None:
        with self._lock:
            if self._fd >= 0:
                os.close(self._fd)
                self._fd = -1

    # -- low level -------------------------------------------------------
    def _packet(self, cmd: int, payload: bytes = b"", sub: int = 0x01, length: int | None = None) -> bytes:
        pkt = bytearray(REPORT_LEN)
        pkt[0] = REPORT_ID
        pkt[1] = 0x01
        pkt[2] = cmd
        pkt[4] = self._seq & 0xFF
        self._seq += 1
        pkt[5] = sub
        pkt[6] = len(payload) if length is None else length
        pkt[7:7 + len(payload)] = payload[:REPORT_LEN - 7]
        return bytes(pkt)

    def _write_feature(self, pkt: bytes) -> None:
        fcntl.ioctl(self._fd, HIDIOCSFEATURE, pkt)

    def _read_feature(self) -> bytes:
        buf = bytearray(REPORT_LEN)
        buf[0] = REPORT_ID
        fcntl.ioctl(self._fd, HIDIOCGFEATURE, buf)
        return bytes(buf)

    def _set(self, pkt: bytes) -> None:
        try:
            self._write_feature(pkt)
        except OSError as e:
            raise DeviceError(f"Gửi lệnh thất bại: {e.strerror or e}") from e
        time.sleep(WRITE_DELAY)

    def send(self, cmd: int, payload: bytes = b"", sub: int = 0x01, length: int | None = None) -> None:
        with self._lock:
            self._set(self._packet(cmd, payload, sub, length))

    # -- commands --------------------------------------------------------
    def info(self) -> DeviceInfo:
        with self._lock:
            pkt = self._packet(CMD_INFO, b"", sub=0x00, length=0)
            try:
                self._write_feature(pkt)
                time.sleep(0.01)
                buf = self._read_feature()
            except OSError as e:
                raise DeviceError(f"Đọc thông tin thất bại: {e.strerror or e}") from e
        if len(buf) < 22 or buf[2] != CMD_INFO:
            raise DeviceError("Phản hồi không hợp lệ")
        return DeviceInfo(
            model=bytes(buf[8:12]).decode("ascii", "replace"),
            sensor=buf[15],
            firmware=f"{buf[13]:x}.{buf[12]:02x}",
            battery=100 if buf[19] == 2 else buf[18],
            charging=buf[19],
            online=buf[21] != 0,
            dpi_current=buf[16] >> 4,
            dpi_count=buf[16] & 0x0F,
        )

    def set_key(self, button: str, action: bytes) -> None:
        assert len(action) == 3
        self.send(CMD_KEY, bytes([BUTTON_SLOTS[button]]) + action)

    def set_dpi(self, dpis: list[int], enabled: list[bool], current: int) -> None:
        """dpis/enabled: 6 levels.  current: 0-based index of the active level (must be enabled)."""
        mask = sum(1 << i for i, on in enumerate(enabled) if on)
        count = bin(mask).count("1")
        cur = sum(1 for i in range(current + 1) if enabled[i]) if enabled[current] else 1
        payload = bytearray([(cur << 4) | (count & 0x0F), mask])
        for dpi in dpis[:6]:
            payload += struct.pack("<H", dpi_to_code(dpi))
        payload += bytes(18 - len(payload))
        self.send(CMD_DPI, bytes(payload))

    def set_dpi_colors(self, colors: list[tuple[int, int, int]]) -> None:
        payload = bytearray()
        for rgb in (list(colors) + [(255, 255, 255)] * 8)[:8]:
            payload += bytes(rgb)
        self.send(CMD_DPI_COLORS, bytes(payload))

    def set_polling(self, hz: int) -> None:
        self.send(CMD_POLLING, bytes([POLLING_RATES[hz]]))

    def set_lighting(self, mode: int, speed: int = 2, brightness: int = 2,
                     colors: list[tuple[int, int, int]] | None = None) -> None:
        """speed 1..3, brightness 1..4 (25 %..100 %)."""
        sb = ((brightness & 0x0F) << 4) | (speed & 0x0F)
        payload = bytearray([mode, sb])
        if mode == LIGHT_BREATHING:
            colors = list(colors or [])[:7] or [(255, 0, 0)]
            payload.append(len(colors))
            for rgb in colors:
                payload += bytes(rgb)
        elif mode == LIGHT_STEADY:
            payload += bytes((colors or [(255, 0, 0)])[0])
        self.send(CMD_LIGHTING, bytes(payload))

    def set_power(self, sleep_minutes: int, light_off_when_moving: bool) -> None:
        self.send(CMD_POWER, bytes([sleep_minutes, int(light_off_when_moving)]))

    def set_motion_wakeup(self, on: bool) -> None:
        self.send(CMD_MOTION_WAKEUP, bytes([int(on)]))

    def factory_reset(self) -> None:
        self.send(CMD_FACTORY_RESET, b"\xff")

    def upload_macro(self, slot: int, events: bytes) -> None:
        """events: encoded 3-byte macro events (see macro.encode_events)."""
        total = len(events)
        chunks = max(1, -(-total // 25))
        with self._lock:
            for k in range(chunks):
                part = events[k * 25:(k + 1) * 25]
                payload = bytes([slot & 0x0F]) + part.ljust(25, b"\0")
                self._set(self._packet(CMD_MACRO, payload, sub=(k << 4) | (chunks & 0x0F),
                                       length=len(part) + 1))
