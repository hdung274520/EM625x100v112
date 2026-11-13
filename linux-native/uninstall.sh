#!/usr/bin/env bash
# Gỡ Nplay AIM. Thêm --purge để xóa cả hồ sơ đã lưu (~/.config/nplayaim).
set -eu
pkill -f "^python3 -m nplayaim" 2>/dev/null || true
rm -f "${XDG_CONFIG_HOME:-$HOME/.config}/autostart/io.github.nplayaim.Control.desktop"
rm -rf "$HOME/.local/share/nplayaim" "$HOME/.local/bin/nplayaim" \
       "$HOME/.local/share/applications/io.github.nplayaim.Control.desktop"
[ "${1:-}" = "--purge" ] && rm -rf "${XDG_CONFIG_HOME:-$HOME/.config}/nplayaim"
if [ -f /etc/udev/rules.d/99-nplayaim10.rules ]; then
  echo "Gỡ udev rule (cần sudo)…"
  sudo rm -f /etc/udev/rules.d/99-nplayaim10.rules && sudo udevadm control --reload-rules
fi
echo "Đã gỡ."
