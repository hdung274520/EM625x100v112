#!/usr/bin/env bash
# Cài Nplay AIM (bản native cho Linux) cho người dùng hiện tại.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.local/share/nplayaim"
BIN="$HOME/.local/bin"
APPS="$HOME/.local/share/applications"

need=()
python3 -c 'import gi; gi.require_version("Gtk","4.0"); gi.require_version("Adw","1")' 2>/dev/null \
  || need+=(python3-gi gir1.2-gtk-4.0 gir1.2-adw-1)
if [ ${#need[@]} -gt 0 ]; then
  echo "==> Cài thư viện: ${need[*]}"
  sudo apt-get install -y "${need[@]}"
fi

if ! cmp -s "$HERE/99-nplayaim10.rules" /etc/udev/rules.d/99-nplayaim10.rules; then
  echo "==> Cài udev rule (cần sudo)"
  sudo install -m 644 "$HERE/99-nplayaim10.rules" /etc/udev/rules.d/99-nplayaim10.rules
  sudo udevadm control --reload-rules
  sudo udevadm trigger --subsystem-match=hidraw --action=change
fi

echo "==> Chép chương trình vào $DEST"
rm -rf "$DEST"
mkdir -p "$DEST" "$BIN" "$APPS"
cp -r "$HERE/nplayaim" "$DEST/"
find "$DEST" -name __pycache__ -prune -exec rm -rf {} +

cat > "$BIN/nplayaim" <<LAUNCH
#!/bin/sh
PYTHONPATH="$DEST\${PYTHONPATH:+:\$PYTHONPATH}" exec python3 -m nplayaim "\$@"
LAUNCH
chmod +x "$BIN/nplayaim"

cat > "$APPS/io.github.nplayaim.Control.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=Nplay AIM
GenericName=Cấu hình chuột gaming
Comment=Nút bấm, DPI, đèn LED, polling rate, macro cho chuột Nplay AIM10 / M220
Exec=$BIN/nplayaim
Icon=input-mouse
Terminal=false
Categories=Settings;HardwareSettings;
Keywords=mouse;dpi;macro;gaming;chuột;
StartupWMClass=io.github.nplayaim.Control
DESK
update-desktop-database "$APPS" 2>/dev/null || true

# Chạy nền khi đăng nhập (icon khay + thông báo DPI). Tắt được trong menu của app.
AUTO="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
mkdir -p "$AUTO"
cat > "$AUTO/io.github.nplayaim.Control.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=Nplay AIM
Exec=$BIN/nplayaim --background
Icon=input-mouse
NoDisplay=true
X-GNOME-Autostart-enabled=true
DESK

# Khởi động lại bản đang chạy (nếu có) để dùng mã mới
pkill -f "^python3 -m nplayaim" 2>/dev/null || true
sleep 0.5
setsid "$BIN/nplayaim" --background >/dev/null 2>&1 < /dev/null &

echo
echo "Xong. Mở 'Nplay AIM' trong menu ứng dụng, hoặc chạy: nplayaim"
echo "Dòng lệnh: nplayaim info | nplayaim dpi 800 1600 3200 | nplayaim polling 1000 | nplayaim apply"
