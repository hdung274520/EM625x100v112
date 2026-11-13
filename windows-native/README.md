# Nplay AIM cho Windows

Bản Windows native (Qt / PySide6) của phần mềm cấu hình chuột **Nplay AIM10** (M220).
Phần giao thức, hồ sơ và macro dùng chung với bản Linux trong `..\linux-native\nplayaim`.
Không cần driver và không cần quyền admin.

---

## Hướng dẫn build trên Windows (làm một lần)

### Bước 1 — Chép mã nguồn sang Windows

Chép **cả thư mục `EM625x100v112`** (USB, mạng, Git…), không chỉ riêng `windows-native`.
Bản Windows đọc code từ thư mục `linux-native` nằm bên cạnh.

```
EM625x100v112\
├── linux-native\      ← lõi dùng chung (bắt buộc phải có)
└── windows-native\    ← bản Windows, build.bat, installer.iss
```

Nên đặt ở một đường dẫn ngắn, không có dấu tiếng Việt, ví dụ `C:\src\EM625x100v112`.

### Bước 2 — Cài Python

1. Tải **Python 3.12** (64-bit) từ <https://www.python.org/downloads/windows/>.
2. Khi cài, tích **"Add python.exe to PATH"**. Giữ tùy chọn **"py launcher"** (mặc định đã bật).
3. Mở **Command Prompt** mới và kiểm tra:
   ```
   py --version
   ```
   Lệnh này phải in ra `Python 3.12.x`.

### Bước 3 — Cài Inno Setup (để tạo file cài đặt)

Tải và cài **Inno Setup 6** từ <https://jrsoftware.org/isdl.php>, cài vào vị trí mặc định.
Nếu bỏ qua bước này, bạn vẫn có `Nplay AIM.exe` chạy trực tiếp được, chỉ không có file cài đặt.

### Bước 4 — Build

Mở Command Prompt rồi chạy:

```
cd C:\src\EM625x100v112\windows-native
build.bat
```

Script sẽ lần lượt:
1. cài PySide6, hidapi và PyInstaller bằng pip (cần mạng, mất khoảng 1–3 phút);
2. chạy test (6 test, tất cả phải báo `OK`);
3. đóng gói thành `dist\Nplay AIM.exe`;
4. nếu đã cài Inno Setup: tạo `dist\NplayAIM-Setup-1.0.0.exe`.

### Bước 5 — Cài và chạy

Chạy `dist\NplayAIM-Setup-1.0.0.exe`. Installer:
- cài vào `%LOCALAPPDATA%\Programs\NplayAIM`, cho riêng người dùng hiện tại, không hỏi quyền admin;
- tạo lối tắt trong Start Menu, có tùy chọn thêm biểu tượng trên màn hình nền;
- có tùy chọn **chạy nền khi đăng nhập** (icon ở khay hệ thống, báo DPI, cảnh báo pin yếu).

Gỡ cài đặt: **Settings → Apps → Nplay AIM → Uninstall**. Khi gỡ, mục tự khởi động cũng bị xóa.
Hồ sơ của bạn vẫn được giữ lại.

---

## Kiểm tra lần chạy đầu

Bản Windows mới chỉ được chạy thử trên Linux. Lần đầu chạy trên Windows, hãy thử các mục sau:

- [ ] Góc phải trên cửa sổ hiện **Pin xx%**. Thẻ **Thiết bị** hiện M220, PAW3325, firmware.
- [ ] Đổi DPI hoặc polling trong app, rồi kiểm tra chuột có đổi theo không.
- [ ] Bấm **nút DPI trên chuột**: ô DPI hiện ở góc phải dưới màn hình, và mức DPI trong thẻ DPI đổi theo.
- [ ] Thẻ **Macro**: bấm Ghi, gõ vài phím (thử cả phím mũi tên và Ctrl phải), rồi kiểm tra tên phím hiện đúng.
- [ ] Đóng cửa sổ: app vẫn còn ở khay hệ thống. Chuột phải vào icon để mở menu.
- [ ] Menu **Tùy chọn → Chạy nền khi đăng nhập Windows**: bật/tắt, rồi khởi động lại máy để thử.

Nếu mục nào sai, ghi lại lỗi hiện trên thanh vàng hoặc ở thanh trạng thái dưới cùng.

---

## Xử lý sự cố

| Hiện tượng | Cách xử lý |
|---|---|
| `'py' is not recognized` | Cài lại Python và tích "py launcher" / "Add to PATH". Sau đó mở Command Prompt **mới** |
| pip báo lỗi khi cài PySide6 | Kiểm tra mạng. Dùng Python 3.12 64-bit (bản 32-bit không có PySide6) |
| `ModuleNotFoundError: nplayaim` | Thiếu thư mục `linux-native` bên cạnh `windows-native` (xem Bước 1) |
| Windows SmartScreen chặn installer/exe | File chưa được ký số. Bấm **More info → Run anyway** |
| Phần mềm diệt virus báo nhầm `Nplay AIM.exe` | Thường gặp với exe do PyInstaller tạo. Thêm thư mục cài vào danh sách ngoại lệ |
| "Không tìm thấy chuột" | Cắm đầu thu vào cổng khác, rồi đóng hẳn phần mềm gốc `GamingMS.exe` nếu đang chạy |
| "Chuột đang ngủ hoặc tắt" | Di chuyển chuột để đánh thức. Các thay đổi sẽ tự được ghi khi chuột kết nối lại |
| Không thấy icon ở khay | Bấm mũi tên `^` cạnh đồng hồ, rồi kéo icon ra thanh taskbar |

---

## Dành cho phát triển

Chạy thẳng từ mã nguồn, không cần build:

```
cd windows-native
py -m pip install -r requirements.txt
pyw run.pyw              REM hoặc: py run.pyw  để xem lỗi trong console
```

Chạy test (dùng chuột giả, không cần cắm chuột):

```
py -m unittest discover -s tests
cd ..\linux-native && py -m unittest discover -s tests
```

| Tệp | Nội dung |
|---|---|
| `run.pyw` | Điểm khởi chạy |
| `nplayaim_win\app.py` | Cửa sổ chính, các thẻ, khay hệ thống, tự khởi động |
| `nplayaim_win\hidwin.py` | Truy cập HID qua hidapi, luồng nền, nghe nút DPI |
| `nplayaim_win\widgets.py` | Chọn màu, bắt phím, hộp thoại gán chức năng nút |
| `nplayaim_win\macro_page.py` | Trình sửa macro |
| `build.bat`, `installer.iss` | Đóng gói exe và tạo installer |

Đổi phiên bản: sửa `__version__` trong `linux-native\nplayaim\__init__.py` và `AppVersion` trong `installer.iss`.

## Khác biệt so với bản Linux

| Bản Linux | Bản Windows |
|---|---|
| Chữ `3200 DPI` cạnh icon khay | Khay Windows không hiện được chữ. Chế độ "Hiện nhanh" hiện một ô DPI ở góc phải dưới màn hình trong 2,5 giây. Chế độ "Luôn hiện" vẽ số DPI lên icon (ví dụ `3.2k`) |
| Tự chạy qua `~/.config/autostart` | Tự chạy qua registry `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` |
| Hồ sơ ở `~/.config/nplayaim/state.json` | Hồ sơ ở `%APPDATA%\nplayaim\state.json` (chép file này sang nếu muốn giữ hồ sơ từ Linux) |
| Cần udev rule | Không cần |
| Có lệnh `nplayaim info/dpi/…` | Không có (exe chạy không có console) |

Các tính năng còn lại giống bản Linux: gán nút, 6 mức DPI, đèn LED, polling rate, nguồn và pin, macro,
5 hồ sơ, nhập/xuất hồ sơ, cảnh báo pin yếu. Mở app lần thứ hai chỉ đưa cửa sổ đang chạy lên trước.
