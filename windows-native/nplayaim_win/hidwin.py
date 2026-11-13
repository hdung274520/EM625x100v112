"""HID access through hidapi (hid.dll on Windows) and the background workers that use it.

On Windows every HID top-level collection is its own device path:
  * usage page 0xFF00 / usage 0x01 carries the 33-byte feature report 0x0c (all commands);
  * usage page 0x01 / usage 0x00 carries input report 5 (DPI button presses).
"""

from __future__ import annotations

import queue
import sys
import threading
import time
from typing import Callable

from nplayaim import protocol

if sys.platform == "win32":
    import hid
else:  # same code on Linux through the hidraw backend, used for testing
    import hidraw as hid

Post = Callable[..., None]  # runs fn(*args) on the GUI thread


def _entries(usage_page: int, usage: int) -> list[dict]:
    found = [d for d in hid.enumerate(protocol.VENDOR_ID)
             if d["product_id"] in protocol.PRODUCT_IDS
             and d["usage_page"] == usage_page and d["usage"] == usage]
    found.sort(key=lambda d: d["product_id"] != 0x5B2E)  # wired cable first
    return found


class HidMouse(protocol.Mouse):
    """protocol.Mouse over hidapi instead of Linux hidraw ioctls."""

    def __init__(self, entry: dict):
        pid = entry["product_id"]
        self.node = protocol.HidrawNode(entry["path"].decode(errors="replace"), pid,
                                        protocol.PRODUCT_IDS[pid])
        self._dev = hid.device()
        try:
            self._dev.open_path(entry["path"])
        except OSError as e:
            raise protocol.DeviceError(f"Không mở được chuột: {e}") from e
        self._seq = 1
        self._lock = threading.Lock()

    @classmethod
    def open_first(cls) -> "HidMouse":
        entries = _entries(0xFF00, 0x01)
        if not entries:
            raise protocol.DeviceError("Không tìm thấy chuột (248a:5b2e / 248a:5b2f)")
        return cls(entries[0])

    def close(self) -> None:
        with self._lock:
            self._dev.close()

    def _write_feature(self, pkt: bytes) -> None:
        if self._dev.send_feature_report(pkt) < 0:
            raise OSError(self._dev.error() or "send_feature_report")

    def _read_feature(self) -> bytes:
        return bytes(self._dev.get_feature_report(protocol.REPORT_ID, protocol.REPORT_LEN))


class EventListener:
    """Reads input report 05 06 01 02 <level 1-6> <dpi code> and reports DPI button presses."""

    def __init__(self, post: Post, on_dpi: Callable[[int, int], None]):
        self._post, self._on_dpi = post, on_dpi
        self._stop = False
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self) -> None:
        self._stop = True

    def _run(self) -> None:
        while not self._stop:
            devs = []
            for path in dict.fromkeys(d["path"] for d in _entries(0x01, 0x00)):
                try:
                    dev = hid.device()
                    dev.open_path(path)
                    devs.append(dev)
                except OSError:
                    pass
            if not devs:
                time.sleep(3)
                continue
            try:
                # The receiver exposes several collections with the same usage and some of them
                # fail on read. Drop only the failing one; retry everything once none are left.
                while devs and not self._stop:
                    for dev in list(devs):
                        try:
                            data = dev.read(64, 200)
                        except OSError:
                            devs.remove(dev)
                            dev.close()
                            continue
                        if len(data) >= 6 and data[0] == 0x05 and data[1] == 0x06:
                            level, code = data[4], data[5]
                            if 1 <= code <= len(protocol.DPI_VALUES):
                                self._post(self._on_dpi, level, protocol.DPI_VALUES[code - 1])
            finally:
                for dev in devs:
                    dev.close()
            time.sleep(1)


class DeviceWorker:
    """Runs jobs `fn(mouse)` in order on one thread; reconnects automatically."""

    def __init__(self, post: Post, on_info: Callable[[protocol.DeviceInfo | None, str | None], None]):
        self._post, self._on_info = post, on_info
        self._q: queue.Queue = queue.Queue()
        self.mouse: HidMouse | None = None
        threading.Thread(target=self._run, daemon=True).start()

    def submit(self, fn: Callable[[protocol.Mouse], object],
               done: Callable[[object, str | None], None] | None = None) -> None:
        self._q.put((fn, done))

    def poll_info(self) -> None:
        if self._q.empty():
            self.submit(lambda m: m.info(), lambda info, err: self._on_info(info, err))

    def stop(self) -> None:
        self._q.put(None)

    def _run(self) -> None:
        while True:
            job = self._q.get()
            if job is None:
                break
            fn, done = job
            result, err = None, None
            try:
                if self.mouse is None:
                    self.mouse = HidMouse.open_first()
                result = fn(self.mouse)
            except protocol.DeviceError as e:
                err = str(e)
                if self.mouse is not None:
                    self.mouse.close()
                    self.mouse = None
            except Exception as e:  # keep the worker alive on unexpected errors
                err = f"{type(e).__name__}: {e}"
            if done is not None:
                self._post(done, result, err)
            elif err:
                self._post(self._on_info, None, err)
        if self.mouse is not None:
            self.mouse.close()
