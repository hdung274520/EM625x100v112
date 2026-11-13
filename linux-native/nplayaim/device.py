"""Background worker that owns the hidraw handle so the UI never blocks on I/O."""

from __future__ import annotations

import queue
import threading
from typing import Callable

from gi.repository import GLib

from . import protocol


class EventListener:
    """Reads the mouse's input reports (report 5) and reports DPI button presses.

    Report: 05 06 01 02 <level 1-6> <dpi code> …
    """

    def __init__(self, on_dpi: Callable[[int, int], None]):
        self._on_dpi = on_dpi
        self._stop = False
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self) -> None:
        self._stop = True

    def _run(self) -> None:
        import os
        import select
        import time
        while not self._stop:
            nodes = [n for n in protocol.find_devices() if n.mode != "no-permission"]
            if not nodes:
                time.sleep(3)
                continue
            try:
                fd = os.open(nodes[0].path, os.O_RDONLY | os.O_NONBLOCK)
            except OSError:
                time.sleep(3)
                continue
            try:
                while not self._stop:
                    r, _, _ = select.select([fd], [], [], 1.0)
                    if not r:
                        continue
                    data = os.read(fd, 64)
                    if len(data) >= 6 and data[0] == 0x05 and data[1] == 0x06:
                        level, code = data[4], data[5]
                        if 1 <= code <= len(protocol.DPI_VALUES):
                            GLib.idle_add(self._on_dpi, level, protocol.DPI_VALUES[code - 1])
            except OSError:
                pass  # unplugged: retry
            finally:
                os.close(fd)
            time.sleep(1)


class DeviceWorker:
    """Runs jobs `fn(mouse)` in order on one thread; reconnects automatically."""

    def __init__(self, on_info: Callable[[protocol.DeviceInfo | None, str | None], None]):
        self._on_info = on_info
        self._q: queue.Queue = queue.Queue()
        self._mouse: protocol.Mouse | None = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    @property
    def busy(self) -> bool:
        return not self._q.empty()

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
                if self._mouse is None:
                    self._mouse = protocol.Mouse.open_first()
                result = fn(self._mouse)
            except protocol.DeviceError as e:
                err = str(e)
                if self._mouse is not None:
                    self._mouse.close()
                    self._mouse = None
            except Exception as e:  # keep the worker alive on unexpected errors
                err = f"{type(e).__name__}: {e}"
            if done is not None:
                GLib.idle_add(done, result, err)
            elif err:
                GLib.idle_add(self._on_info, None, err)
        if self._mouse is not None:
            self._mouse.close()
