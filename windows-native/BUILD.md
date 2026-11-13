# Build và phát triển bản Windows

Tài liệu này dành cho người build từ mã nguồn hoặc sửa code. Hướng dẫn sử dụng nằm ở [README.md](README.md).

Bản Windows là app Qt (PySide6). Phần giao thức, hồ sơ và macro dùng chung với bản Linux trong
`..\linux-native\nplayaim`.

## Cấu trúc thư mục

Phải lấy **cả repo**, không chỉ riêng `windows-native`, vì bản Windows đọc code từ thư mục `linux-native` bên cạnh.

```
EM625x100v112\
├── linux-native\      ← lõi dùng chung (bắt buộc phải có)
└── windows-native\    ← bản Windows, build.bat, installer.iss
```

Nên đặt ở đường dẫn ngắn, không có dấu tiếng Việt, ví dụ `C:\src\EM625x100v112`.

## Chạy thẳng từ mã nguồn

Cài Python 3.12 (64-bit) từ <https://www.python.org/downloads/windows/>, tích **"Add python.exe to PATH"** và giữ **"py launcher"**.

```
cd windows-native
py -m pip install -r requirements.txt
pyw run.pyw              REM hoặc: py run.pyw  để xem lỗi trong console
```

## Đóng gói thành exe và installer

1. (Tùy chọn) Cài **Inno Setup 6** từ <https://jrsoftware.org/isdl.php> vào vị trí mặc định để tạo file cài đặt.
2. Chạy:

   ```
   cd windows-native
   build.bat
   ```

`build.bat` lần lượt:
1. cài PySide6, hidapi và PyInstaller bằng pip (cần mạng);
2. chạy test (6 test, tất cả phải báo `OK`);
3. đóng gói thành `dist\Nplay AIM.exe`;
4. nếu đã cài Inno Setup: tạo `dist\NplayAIM-Setup-1.0.0.exe`.

Installer cài vào `%LOCALAPPDATA%\Programs\NplayAIM` cho riêng người dùng hiện tại, không cần quyền admin.

## Kiểm thử

Dùng chuột giả, không cần cắm chuột:

```
py -m unittest discover -s tests
cd ..\linux-native && py -m unittest discover -s tests
```

### Checklist thử với chuột thật

- [ ] Góc phải trên cửa sổ hiện **Pin xx%**. Thẻ **Thiết bị** hiện M220, PAW3325, firmware.
- [ ] Đổi DPI hoặc polling trong app, rồi kiểm tra chuột có đổi theo không.
- [ ] Bấm **nút DPI trên chuột**: ô DPI hiện ở góc phải dưới màn hình, mức DPI trong thẻ DPI đổi theo.
- [ ] Thẻ **Macro**: bấm Ghi, gõ vài phím (thử cả phím mũi tên và Ctrl phải), kiểm tra tên phím hiện đúng.
- [ ] Đóng cửa sổ: app vẫn còn ở khay hệ thống.
- [ ] Bật **Chạy nền khi đăng nhập Windows**, khởi động lại máy để thử.

## Các tệp chính

| Tệp | Nội dung |
|---|---|
| `run.pyw` | Điểm khởi chạy |
| `nplayaim_win\app.py` | Cửa sổ chính, các thẻ, khay hệ thống, tự khởi động |
| `nplayaim_win\hidwin.py` | Truy cập HID qua hidapi, luồng nền, nghe nút DPI |
| `nplayaim_win\widgets.py` | Chọn màu, bắt phím, hộp thoại gán chức năng nút |
| `nplayaim_win\macro_page.py` | Trình sửa macro |
| `build.bat`, `installer.iss`, `version_info.txt` | Đóng gói exe, tạo installer, thông tin phiên bản nhúng vào exe |

Đổi phiên bản: sửa `__version__` trong `linux-native\nplayaim\__init__.py`, `AppVersion` trong `installer.iss`
và số phiên bản trong `version_info.txt`.

## Ghi chú kỹ thuật

- Trên Windows mỗi collection HID là một đường dẫn thiết bị riêng. Lệnh cấu hình đi qua feature report `0x0c`
  của collection `0xFF00/0x01`. Nút DPI gửi input report `05 06 01 02 <mức> <mã>` ở các collection `0x01/0x00`.
  Một số collection báo lỗi khi đọc, nên bộ nghe bỏ riêng từng cổng lỗi chứ không dừng cả bộ nghe.
- File hồ sơ luôn đọc/ghi UTF-8, vì mặc định của Windows (cp1252) không ghi được tiếng Việt.
- Exe chưa ký số: Smart App Control hoặc SmartScreen có thể chặn. Xem README mục xử lý sự cố.
