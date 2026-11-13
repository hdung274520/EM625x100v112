# Nplay AIM cho Windows — Hướng dẫn sử dụng

Phần mềm cấu hình chuột gaming **Nplay AIM10** (M220). Không cần driver, không cần quyền admin.
Hỗ trợ đầu thu không dây USB và cáp USB.

> Muốn tự build từ mã nguồn? Xem [BUILD.md](BUILD.md).

## 1. Bắt đầu

1. Cắm đầu thu (hoặc cáp USB) của chuột vào máy.
2. Mở **Nplay AIM**. Nếu chưa có file chạy, hãy build theo [BUILD.md](BUILD.md).
3. Nếu có chuột trong tình trạng ngủ, di chuyển chuột để đánh thức.

Khi kết nối thành công, góc phải trên cửa sổ hiện **Pin xx%**, và thẻ **Thiết bị** hiện model, cảm biến,
firmware. Mọi thay đổi được ghi vào chuột ngay khi bạn chỉnh. Nếu chuột đang ngủ hoặc chưa cắm, app ghi nhớ
và tự đồng bộ khi chuột kết nối lại.

> Nếu phần mềm gốc `GamingMS.exe` đang chạy, hãy đóng hẳn nó trước, vì hai chương trình không dùng chung chuột được.

## 2. Các thẻ trong cửa sổ

### Nút bấm
Chuột có 6 nút. Bấm **Đổi…** cạnh nút cần đổi để gán chức năng:

- chuột trái, phải, giữa, tiến, lùi;
- DPI: vòng lặp, tăng, giảm, hoặc khóa ở một mức DPI cố định;
- phím bắn (chọn chu kỳ và số lần), nhấn ba lần;
- một phím hoặc tổ hợp phím, phím media, phím tắt văn phòng và cửa sổ;
- chạy một macro;
- chuyển hiệu ứng đèn;
- tắt nút.

Nút **Khôi phục chức năng mặc định cho tất cả nút** đưa mọi nút về ban đầu.

### DPI
6 mức DPI, từ 200 đến 10000.
- Kéo thanh trượt hoặc nhập số để đổi DPI của từng mức (giá trị tự khớp với bước của cảm biến).
- Công tắc bên phải để bật/tắt từng mức. Luôn phải còn ít nhất một mức bật.
- Chọn nút tròn để đặt mức đang dùng.
- Bấm ô màu để đổi màu đèn báo của mức đó.

Khi bạn bấm **nút DPI trên chuột**, mức DPI trong thẻ này tự đổi theo.

### Đèn LED
Chọn chế độ **Tắt**, **Nhịp thở**, **Đứng yên** hoặc **Neon**. Tùy chế độ mà có thêm tốc độ (1–3), độ sáng
(25–100 %) và màu. Với Nhịp thở, bật các ô màu muốn dùng (tối đa 7) rồi bấm từng ô để đổi màu.

### Tần số
Polling rate của chuột: 125, 250, 500 hoặc 1000 Hz. Số càng cao càng mượt nhưng tốn pin hơn.

### Nguồn
Hiện % pin và trạng thái sạc. Có thể chỉnh:
- **Tự ngủ sau** 3–10 phút không dùng;
- **Tắt đèn khi di chuột** để tiết kiệm pin;
- **Di chuyển để đánh thức** (tắt thì phải bấm nút mới đánh thức được chuột).

### Macro
Macro là chuỗi thao tác phím và chuột được ghi sẵn, gán được cho một nút.
1. Bấm **Mới**, đặt tên.
2. Bấm **● Ghi** rồi thao tác phím, chuột hoặc cuộn. Bấm lại để dừng. Bật **Tự chèn độ trễ thực** để ghi đúng nhịp bạn bấm.
3. Chỉnh lại: **Chèn ▾** thêm phím, click hoặc di chuyển; **▲ ▼** đổi thứ tự; sửa cột **Trễ sau (ms)**; **Xóa sự kiện** hoặc **Xóa hết**.
4. Vào thẻ **Nút bấm**, gán macro cho nút và chọn chế độ lặp: theo số lần, lặp tới khi nhả nút, hoặc lặp tới khi nhấn lại.

Một macro tối đa 125 sự kiện.

### Thiết bị
Hiện thông tin chuột. Có hai thao tác:
- **Ghi toàn bộ hồ sơ vào chuột**: gửi lại toàn bộ cấu hình hiện tại.
- **Khôi phục cài đặt gốc của chuột…**: đưa chuột về mặc định của nhà sản xuất.

## 3. Hồ sơ

App có **5 hồ sơ**, chọn ở hộp thả xuống trên cửa sổ. Mỗi hồ sơ lưu riêng nút, DPI, đèn, tần số và nguồn.
Khi đổi hồ sơ, toàn bộ cấu hình được ghi vào chuột.

Menu **Hồ sơ** có: đổi tên, nhập/xuất hồ sơ ra file JSON (để chép sang máy khác), đặt lại về mặc định.
Hồ sơ lưu tại `%APPDATA%\nplayaim\state.json`. Chép file này sang nếu muốn giữ hồ sơ cũ khi cài lại máy.

## 4. Chạy nền và khay hệ thống

Đóng cửa sổ thì app **vẫn chạy ở khay hệ thống**, cạnh đồng hồ. Chuột phải vào icon để:
- đổi nhanh mức DPI;
- đổi hồ sơ;
- chọn kiểu hiển thị DPI;
- mở cài đặt hoặc thoát hẳn.

Nếu không thấy icon, bấm mũi tên `^` cạnh đồng hồ rồi kéo icon ra thanh taskbar.

**Hiển thị DPI** (menu **Tùy chọn → Hiển thị DPI** hoặc menu khay):
- **Hiện nhanh khi đổi DPI** (mặc định): khi đổi DPI, một ô hiện số DPI ở góc phải dưới màn hình trong 2,5 giây.
  Áp dụng cho cả nút DPI trên chuột và khi chỉnh trong app.
- **Luôn hiện trên icon**: số DPI được vẽ lên icon khay (ví dụ `3.2k`).
- **Không hiện**.

**Chạy nền khi đăng nhập Windows** (menu **Tùy chọn**): app tự mở ở khay mỗi khi bật máy.
Nếu bạn di chuyển hoặc xóa file chạy, hãy bật lại tùy chọn này ở vị trí mới.

**Cảnh báo pin yếu**: khi pin chuột còn 15 % trở xuống, app báo một lần. Bật/tắt trong menu **Tùy chọn**.

Mở app lần thứ hai chỉ đưa cửa sổ đang chạy lên trước, không mở thêm bản thứ hai.

## 5. Gỡ cài đặt

- Nếu cài bằng installer: **Settings → Apps → Nplay AIM → Uninstall**. Mục tự khởi động cũng bị xóa.
- Nếu chạy trực tiếp file exe: tắt **Chạy nền khi đăng nhập Windows**, thoát app ở khay rồi xóa file.

Hồ sơ của bạn ở `%APPDATA%\nplayaim` vẫn được giữ lại, xóa thư mục đó nếu muốn xóa sạch.

## 6. Xử lý sự cố

| Hiện tượng | Cách xử lý |
|---|---|
| "Không tìm thấy chuột" | Cắm đầu thu vào cổng USB khác, rồi đóng hẳn `GamingMS.exe` nếu đang chạy |
| "Chuột đang ngủ hoặc tắt" | Di chuyển chuột để đánh thức. Thay đổi sẽ tự ghi khi chuột kết nối lại |
| Bấm nút DPI trên chuột nhưng không thấy ô DPI | Kiểm tra **Tùy chọn → Hiển thị DPI** đang là "Hiện nhanh". Ô hiện ở góc phải dưới của màn hình chính, ngay trên thanh taskbar |
| Không thấy icon ở khay | Bấm mũi tên `^` cạnh đồng hồ, rồi kéo icon ra thanh taskbar |
| Windows báo *"An Application Control policy has blocked this file"* | **Smart App Control** chặn file chưa ký số. Xem bên dưới |
| SmartScreen chặn file | Bấm **More info → Run anyway**. Hoặc chuột phải file → Properties → tích **Unblock** |
| Phần mềm diệt virus báo nhầm | Thường gặp với exe do PyInstaller tạo. Thêm file vào danh sách ngoại lệ |
| Số DPI trên icon khay nhỏ khó đọc | Khay Windows chỉ cho icon 16–24 px. Kéo icon ra taskbar, hoặc dùng chế độ "Hiện nhanh" |

### Smart App Control chặn file

Smart App Control không có danh sách ngoại lệ cho từng app, và nút "Run anyway" không có tác dụng với nó.
File exe tự build không có chữ ký số nên bị chặn. Có hai cách:

1. **Chạy từ mã nguồn** (không đổi cài đặt bảo mật): cài Python 3.12, rồi chạy
   `py -m pip install -r requirements.txt` và `py run.pyw` trong thư mục `windows-native`.
2. **Tắt Smart App Control**: Windows Security → App & browser control → Smart App Control settings → **Off**.
   Lưu ý: tắt rồi không bật lại được nếu không cài lại Windows, và máy sẽ được bảo vệ ít hơn.

## 7. Khác biệt so với bản Linux

| Bản Linux | Bản Windows |
|---|---|
| Chữ `3200 DPI` cạnh icon khay | Khay Windows không hiện được chữ: dùng ô DPI ở góc màn hình, hoặc vẽ số lên icon |
| Tự chạy qua `~/.config/autostart` | Tự chạy qua registry `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` |
| Hồ sơ ở `~/.config/nplayaim/state.json` | Hồ sơ ở `%APPDATA%\nplayaim\state.json` |
| Cần udev rule | Không cần |
| Có lệnh `nplayaim info/dpi/…` | Không có |

Các tính năng còn lại giống bản Linux.
