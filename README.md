# Nplay AIM — phần mềm cấu hình chuột cho Linux và Windows

Phần mềm cấu hình **native** cho chuột gaming **Nplay AIM10** (mã thiết bị M220, cảm biến PixArt PAW3325),
thay thế `GamingMS.exe` của hãng. Không cần driver, không cần Wine, không cần quyền admin trên Windows.

Hỗ trợ đầu thu không dây USB `248a:5b2f` và cáp USB `248a:5b2e`.

> Đây là dự án cộng đồng, viết bằng cách dịch ngược giao thức HID. Dự án không liên kết với hãng sản xuất chuột.

## Chọn bản của bạn

| | Linux | Windows |
|---|---|---|
| Thư mục | [`linux-native/`](linux-native/) | [`windows-native/`](windows-native/) |
| Giao diện | GTK4 / libadwaita | Qt (PySide6) |
| Truy cập chuột | hidraw | hidapi |
| Cài đặt | `./install.sh` | `build.bat` rồi chạy `NplayAIM-Setup`, hoặc chạy thẳng `py run.pyw` |
| Chạy nền | icon khay (AppIndicator), tự chạy qua `~/.config/autostart` | icon khay hệ thống, tự chạy qua registry `HKCU\...\Run` |
| Hướng dẫn chi tiết | [linux-native/README.md](linux-native/README.md) | [windows-native/README.md](windows-native/README.md) |

Hai bản **dùng chung lõi** trong `linux-native/nplayaim` (giao thức, hồ sơ, macro, bảng phím), nên hành vi
và định dạng hồ sơ giống nhau. Bản Windows import code từ thư mục `linux-native` nằm bên cạnh,
vì vậy hãy luôn lấy **cả repo**, không chỉ một thư mục.

```
├── linux-native/      lõi dùng chung + giao diện Linux, udev rule, install.sh
└── windows-native/    giao diện Windows, build.bat, installer.iss
```

## Tính năng

- **Nút bấm:** gán 6 nút. Có chuột trái/phải/giữa/tiến/lùi, DPI vòng lặp/tăng/giảm, khóa DPI,
  phím bắn, nhấn ba lần, phím đơn hoặc tổ hợp phím, phím media, macro, chuyển hiệu ứng đèn, tắt nút.
- **DPI:** 6 mức (200–10000), bật/tắt từng mức, màu đèn báo cho từng mức. Mức hiện tại tự đồng bộ khi
  bấm nút DPI trên chuột.
- **Đèn LED:** tắt, nhịp thở, đứng yên, neon.
- **Polling rate:** 125 / 250 / 500 / 1000 Hz.
- **Nguồn:** hiện % pin và trạng thái sạc, thời gian tự ngủ, tắt đèn khi di chuột. Cảnh báo khi pin yếu (≤ 15 %).
- **Macro:** ghi phím, chuột và cuộn kèm độ trễ thực, sửa từng sự kiện, tối đa 125 sự kiện, nhiều chế độ lặp.
- **Hồ sơ:** 5 hồ sơ, đổi tên, nhập/xuất JSON. Chuyển hồ sơ sẽ ghi toàn bộ cấu hình vào chuột.
- **Chạy nền:** đóng cửa sổ thì app vẫn nằm ở khay hệ thống, đổi DPI bằng menu khay.
  Khi đổi DPI (bằng nút trên chuột hoặc trong app) có ô hiển thị DPI nhỏ ở góc màn hình.

Mọi thay đổi được ghi vào chuột ngay khi bạn chỉnh. Nếu lúc đó chuột đang ngủ, app tự đồng bộ khi chuột thức dậy.

## Bắt đầu nhanh

### Linux

```bash
cd linux-native
./install.sh          # cài thư viện thiếu, udev rule, lệnh `nplayaim` và mục trong menu ứng dụng
```

Sau khi cài udev rule, nếu báo không có quyền thì rút đầu thu ra rồi cắm lại.

### Windows

Cần Python 3.12 (64-bit) có "py launcher".

```bat
cd windows-native
py -m pip install -r requirements.txt
py run.pyw
```

Muốn đóng gói thành `dist\Nplay AIM.exe` (và file cài đặt nếu có Inno Setup 6): chạy `build.bat`.

Nếu Windows chặn exe tự build với thông báo "Application Control policy", đó là Smart App Control chặn file
chưa ký số. Xem mục xử lý sự cố trong [windows-native/README.md](windows-native/README.md).

## Kiểm thử

Test dùng chuột giả, không cần cắm chuột:

```bash
cd linux-native   && python3 -m unittest discover -s tests
cd windows-native && py -m unittest discover -s tests
```

Test giao thức so sánh gói tin chương trình tạo ra với 24 gói tin thật bắt từ phần mềm gốc.
Chi tiết giao thức HID nằm trong [linux-native/README.md](linux-native/README.md).

## Phiên bản

Số phiên bản nằm ở `__version__` trong `linux-native/nplayaim/__init__.py` (hiện tại 1.0.0).
Khi đổi, sửa thêm `AppVersion` trong `windows-native/installer.iss` và `version_info.txt`.
