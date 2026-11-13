# Nplay AIM cho Linux

Phần mềm cấu hình **native** (GTK4 / libadwaita, Python) cho chuột gaming **Nplay AIM10** (mã thiết bị
M220, cảm biến PixArt PAW3325). Chương trình thay thế `GamingMS.exe` của hãng, không cần Wine.

Hỗ trợ đầu thu không dây `248a:5b2f` và cáp USB `248a:5b2e`.

## Cài đặt

```bash
./install.sh        # cài thư viện thiếu, udev rule, lệnh `nplayaim` và mục trong menu ứng dụng
```

Sau khi cài udev rule, nếu chương trình báo không có quyền thì rút đầu thu ra rồi cắm lại.
Gỡ cài đặt bằng `./uninstall.sh`. Thêm `--purge` nếu muốn xóa luôn các hồ sơ đã lưu.

## Tính năng (tương đương bản Windows)

| Mục | Nội dung |
|---|---|
| Nút bấm | 6 nút. Gán được: chuột trái/phải/giữa/tiến/lùi, DPI vòng lặp/tăng/giảm, khóa DPI 200–1200, phím bắn (chu kỳ 5–255 ms, số lần), nhấn ba lần, phím đơn/tổ hợp phím, phím media, phím tắt văn phòng và cửa sổ, macro, chuyển hiệu ứng đèn, tắt nút |
| DPI | 6 mức (200–10000), bật/tắt từng mức, chọn mức đang dùng, màu đèn báo cho từng mức. Mức hiện tại tự đồng bộ khi bạn bấm nút DPI trên chuột |
| Đèn LED | Tắt, Nhịp thở (tốc độ 1–3, tối đa 7 màu), Đứng yên (độ sáng 25–100 %, 1 màu), Neon (tốc độ 1–3) |
| Tần số | 125 / 250 / 500 / 1000 Hz |
| Nguồn | % pin và trạng thái sạc, thời gian tự ngủ 3–10 phút, tắt đèn khi di chuột, di chuyển để đánh thức |
| Macro | Ghi phím, chuột và cuộn kèm độ trễ thực. Sửa độ trễ, chèn hoặc xóa, đổi thứ tự sự kiện. Tối đa 125 sự kiện. Chế độ lặp: số lần / tới khi nhả / tới khi nhấn lại |
| Hồ sơ | 5 hồ sơ, đổi tên, nhập/xuất JSON. Khi chuyển hồ sơ, toàn bộ cấu hình được ghi vào chuột |
| Thiết bị | Model, cảm biến, firmware, khôi phục cài đặt gốc |

### Chạy nền và icon khay

App tự chạy nền khi đăng nhập và có icon chuột trên thanh trên cùng (cần extension Ubuntu AppIndicators,
Ubuntu đã bật sẵn). Khi bấm nút DPI trên chuột, chữ `3200 DPI` hiện cạnh icon khoảng 2,5 giây.
Có thể chọn cho chữ luôn hiện, không hiện, hoặc bật thêm thông báo hệ thống.
Menu của icon gồm: chọn mức DPI, đổi hồ sơ, tùy chọn hiển thị, mở cài đặt, thoát.
Đóng cửa sổ thì app vẫn chạy ở khay. Khi pin chuột còn ≤ 15 %, app gửi cảnh báo pin yếu.
Muốn tắt tự chạy khi đăng nhập, bỏ chọn "Chạy nền khi đăng nhập" trong menu ☰ của app.

Mọi thay đổi được ghi vào chuột ngay khi bạn chỉnh. Nếu lúc đó chuột đang ngủ, chương trình đánh dấu
lại và tự đồng bộ khi chuột thức dậy. Hồ sơ lưu tại `~/.config/nplayaim/state.json`.

### Dòng lệnh

```bash
nplayaim info                      # pin, firmware, mức DPI hiện tại
nplayaim dpi 800 1600 3200 --current 2
nplayaim polling 1000
nplayaim apply 2                   # ghi hồ sơ 2 vào chuột
nplayaim reset                     # khôi phục cài đặt gốc
```

## Giao thức (dịch ngược)

Mỗi lệnh là một HID feature report dài 33 byte, report ID `0x0c`, gửi tới giao diện vendor `0xff00`:

```
0c 01 CMD 00 SEQ 01 LEN DATA…
```

| CMD | Dữ liệu |
|---|---|
| `04` | phím: `slot, b0, b1, b2`. Slot: trái 0, phải 1, giữa 2, lùi 3, tiến 4, DPI 5 |
| `05` | DPI: `(mức_hiện_tại<<4)\|số_mức_bật, mask, 6 × u16le mã` (mã = chỉ số trong bảng PAW3325 + 1) |
| `06` | màu đèn DPI: 8 × RGB |
| `07` | polling: chu kỳ ms (1/2/4/8) |
| `08` | đèn: `mode, (độ_sáng<<4)\|tốc_độ, [n, n×RGB]` |
| `0b` | `phút_ngủ, tắt_đèn_khi_di_chuyển` |
| `0c` | `đánh_thức_bằng_chuyển_động` |
| `0e` | macro: byte 5 = `(chunk<<4)\|số_chunk`, `slot`, 25 byte sự kiện (3 byte mỗi sự kiện) |
| `0f` | `ff` = khôi phục cài đặt gốc |
| `20` | hỏi thông tin. Đọc phản hồi bằng GET_FEATURE: model `[8:12]`, firmware `[12:14]`, cảm biến `[15]`, DPI `[16]`, pin `[18]`, sạc `[19]`, online `[21]` |

Mã chức năng phím: `10 mask` chuột, `30 chu_kỳ lần` phím bắn, `40 01/02/03` DPI vòng lặp/tăng/giảm,
`50 n` khóa DPI (DPI = (n+1)×100), `60 04` đổi hiệu ứng, `70 mods key` tổ hợp phím, `80 usage_le` media,
`90 (mode<<4)|slot count` macro, `00` tắt.

`tests/test_protocol.py` so sánh gói tin do chương trình tạo ra với 24 gói tin thật bắt được từ phần mềm gốc.
Chạy kiểm thử bằng lệnh: `python3 -m unittest discover -s tests`.
