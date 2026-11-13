"""Packets produced by nplayaim must match reports captured from the vendor tool (seq byte ignored)."""

import unittest

from nplayaim import actions, macro, protocol


class FakeMouse(protocol.Mouse):
    def __init__(self):
        self._seq = 1
        self._lock = __import__("threading").Lock()
        self.sent = []

    def _set(self, pkt):
        self.sent.append(pkt)


def norm(hexstr: str) -> bytes:
    b = bytearray.fromhex(hexstr)
    b[4] = 0
    return bytes(b)


def sent(m):
    out = []
    for p in m.sent:
        b = bytearray(p)
        b[4] = 0
        out.append(bytes(b))
    return out


CAPTURED = {
    "dpi_default": "0c010500040112463f07000f0017001f0034003b00000000000000000000000000",
    "dpi_level2_off": "0c010500030112353d07000f0017001f0034003b00000000000000000000000000",
    "poll_1000": "0c0107000601010100000000000000000000000000000000000000000000000000",
    "poll_125": "0c0107000701010800000000000000000000000000000000000000000000000000",
    "light_breath7": "0c010800070118022207ff000000ff000000ff00ffffffff00ff00ffffffff0000",
    "light_breath6": "0c0108001a011502220600ff000000ff00ffffffff00ff00ffffffff0000000000",
    "light_steady": "0c0108001e01050342ff00ff000000000000000000000000000000000000000000",
    "light_steady_25": "0c0108001f01050312ff00ff000000000000000000000000000000000000000000",
    "light_neon": "0c0108000f01020422000000000000000000000000000000000000000000000000",
    "light_off": "0c0108000b01020022000000000000000000000000000000000000000000000000",
    "light_breath_speed1": "0c010800160118022107ff000000ff000000ff00ffffffff00ff00ffffffff0000",
    "power": "0c010b002401020601000000000000000000000000000000000000000000000000",
    "wakeup_off": "0c010c002501010000000000000000000000000000000000000000000000000000",
    "reset": "0c010f00040101ff00000000000000000000000000000000000000000000000000",
    "dpi_colors": "0c0106008201180080ff00ff000000ff00ffffffff00ff00ffffffffffffff0000",
    "key_fwd_left": "0c0104003201040410010000000000000000000000000000000000000000000000",
    "key_back_left": "0c0104007901040310010000000000000000000000000000000000000000000000",
    "key_combo": "0c0104006b01040470060400000000000000000000000000000000000000000000",
    "key_media": "0c0104004101040480830100000000000000000000000000000000000000000000",
    "key_dpi_up": "0c0104003e01040440020000000000000000000000000000000000000000000000",
    "key_triple": "0c0104003b01040430320300000000000000000000000000000000000000000000",
    "key_dpilock200": "0c0104004401040450010000000000000000000000000000000000000000000000",
    "key_disable": "0c0104003901040400000000000000000000000000000000000000000000000000",
    "key_effect": "0c0104003801040460040000000000000000000000000000000000000000000000",
}

PAL = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (0, 255, 255), (255, 255, 0), (255, 0, 255), (255, 255, 255)]


class TestCaptured(unittest.TestCase):
    def check(self, name, fn):
        m = FakeMouse()
        fn(m)
        self.assertEqual(sent(m), [norm(CAPTURED[name])], name)

    def test_dpi(self):
        vals = [800, 1600, 2400, 3200, 6400, 10000]
        self.check("dpi_default", lambda m: m.set_dpi(vals, [True] * 6, 3))
        self.check("dpi_level2_off", lambda m: m.set_dpi(vals, [True, False, True, True, True, True], 3))

    def test_dpi_colors(self):
        cols = [(0, 0x80, 0xFF), (0, 255, 0), (0, 0, 255), (0, 255, 255), (255, 255, 0), (255, 0, 255),
                (255, 255, 255), (255, 255, 255)]
        self.check("dpi_colors", lambda m: m.set_dpi_colors(cols))

    def test_polling(self):
        self.check("poll_1000", lambda m: m.set_polling(1000))
        self.check("poll_125", lambda m: m.set_polling(125))

    def test_lighting(self):
        self.check("light_breath7", lambda m: m.set_lighting(2, 2, 2, PAL))
        self.check("light_breath6", lambda m: m.set_lighting(2, 2, 2, PAL[1:]))
        self.check("light_breath_speed1", lambda m: m.set_lighting(2, 1, 2, PAL))
        self.check("light_steady", lambda m: m.set_lighting(3, 2, 4, [(255, 0, 255)]))
        self.check("light_steady_25", lambda m: m.set_lighting(3, 2, 1, [(255, 0, 255)]))
        self.check("light_neon", lambda m: m.set_lighting(4, 2, 2))
        self.check("light_off", lambda m: m.set_lighting(0, 2, 2))

    def test_power(self):
        self.check("power", lambda m: m.set_power(6, True))
        self.check("wakeup_off", lambda m: m.set_motion_wakeup(False))
        self.check("reset", lambda m: m.factory_reset())

    def test_keys(self):
        k = lambda b, a: (lambda m: m.set_key(b, actions.encode(a)))
        self.check("key_fwd_left", k("forward", {"kind": "mouse", "button": "left"}))
        self.check("key_back_left", k("back", {"kind": "mouse", "button": "left"}))
        self.check("key_combo", k("forward", {"kind": "combo", "mods": 6, "key": 4}))
        self.check("key_media", k("forward", {"kind": "media", "usage": 0x183}))
        self.check("key_dpi_up", k("forward", {"kind": "dpi", "op": "up"}))
        self.check("key_triple", k("forward", {"kind": "triple"}))
        self.check("key_dpilock200", k("forward", {"kind": "dpi_lock", "dpi": 200}))
        self.check("key_disable", k("forward", {"kind": "disable"}))
        self.check("key_effect", k("forward", {"kind": "switch_effect"}))


class TestMacro(unittest.TestCase):
    def test_event_encoding(self):
        self.assertEqual(macro.encode_event({"t": "key", "code": 0x04, "down": True, "delay": 172}),
                         bytes([0x30, 0xAC, 0x04]))
        self.assertEqual(macro.encode_event({"t": "key", "code": 0x04, "down": False, "delay": 0x123}),
                         bytes([0xB1, 0x23, 0x04]))
        self.assertEqual(macro.encode_event({"t": "key", "code": 0xE1, "down": True, "delay": 5}),
                         bytes([0x20, 0x05, 0x02]))
        self.assertEqual(macro.encode_event({"t": "mouse", "button": "right", "down": False, "delay": 10}),
                         bytes([0x90, 0x0A, 0x02]))
        self.assertEqual(macro.encode_event({"t": "move", "axis": "wheel", "value": -1, "delay": 0}),
                         bytes([0x60, 0x00, 0xFF]))

    def test_chunks(self):
        m = FakeMouse()
        evs = bytes(range(30))  # 10 events -> 2 chunks
        m.upload_macro(2, evs)
        a, b = sent(m)
        self.assertEqual(a[:8], bytes([0x0C, 1, 0x0E, 0, 0, 0x02, 26, 2]))
        self.assertEqual(a[8:], evs[:25])
        self.assertEqual(b[:8], bytes([0x0C, 1, 0x0E, 0, 0, 0x12, 6, 2]))
        self.assertEqual(b[8:13], evs[25:])

    def test_macro_key(self):
        self.assertEqual(actions.encode({"kind": "macro", "mode": "count", "count": 3}, 1), bytes([0x90, 0x21, 3]))
        self.assertEqual(actions.encode({"kind": "macro", "mode": "toggle"}, 2), bytes([0x90, 0x42, 0]))


if __name__ == "__main__":
    unittest.main()
