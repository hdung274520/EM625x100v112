"""Entry point: GUI by default, or a small CLI (`nplayaim info|apply|dpi|polling|reset`)."""

from __future__ import annotations

import argparse
import sys


def cli(argv: list[str]) -> int:
    from . import profile, protocol

    ap = argparse.ArgumentParser(prog="nplayaim", description="Cấu hình chuột Nplay AIM10 / M220")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("info", help="thông tin thiết bị và pin")
    a = sub.add_parser("apply", help="ghi hồ sơ đã lưu vào chuột")
    a.add_argument("profile", nargs="?", type=int, help="số hồ sơ 1-5 (mặc định: hồ sơ hiện tại)")
    d = sub.add_parser("dpi", help="đặt các mức DPI, ví dụ: dpi 800 1600 3200")
    d.add_argument("values", nargs="+", type=int)
    d.add_argument("--current", type=int, default=1, help="mức đang dùng (1-6)")
    p = sub.add_parser("polling", help="đặt polling rate")
    p.add_argument("hz", type=int, choices=sorted(protocol.POLLING_RATES))
    sub.add_parser("reset", help="khôi phục cài đặt gốc")
    args = ap.parse_args(argv)

    try:
        mouse = protocol.Mouse.open_first()
        if args.cmd == "info":
            i = mouse.info()
            print(f"Thiết bị : {mouse.node.path} ({mouse.node.mode})")
            print(f"Mẫu     : {i.model}   cảm biến {i.sensor_name}   firmware {i.firmware}")
            print(f"Chuột   : {'online' if i.online else 'offline'}")
            print(f"Pin     : {i.battery}% {['', '(đang sạc)', '(đầy)'][i.charging] if i.charging < 3 else ''}")
            print(f"DPI     : mức {i.dpi_current}/{i.dpi_count}")
        elif args.cmd == "apply":
            st = profile.State()
            if args.profile:
                st.current = (args.profile - 1) % profile.PROFILE_COUNT
                st.save()
            profile.apply_all(mouse, st)
            print(f"Đã ghi {st.profile['name']}")
        elif args.cmd == "dpi":
            vals = [protocol.snap_dpi(v) for v in args.values[:6]]
            st = profile.State()
            d = st.profile["dpi"]
            d["values"][:len(vals)] = vals
            d["enabled"] = [i < len(vals) for i in range(6)]
            d["current"] = max(0, min(len(vals), args.current) - 1)
            st.save()
            profile.apply_dpi(mouse, st.profile)
            print("DPI:", ", ".join(map(str, vals)))
        elif args.cmd == "polling":
            st = profile.State()
            st.profile["polling"] = args.hz
            st.save()
            mouse.set_polling(args.hz)
            print(f"Polling {args.hz} Hz")
        elif args.cmd == "reset":
            mouse.factory_reset()
            print("Đã khôi phục cài đặt gốc")
    except protocol.DeviceError as e:
        print(f"Lỗi: {e}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    background = "--background" in sys.argv[1:]
    args = [a for a in sys.argv[1:] if a != "--background"]
    if args:
        return cli(args)
    from .ui import main as gui
    return gui(background)


if __name__ == "__main__":
    sys.exit(main())
