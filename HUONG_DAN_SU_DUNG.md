# 📖 HƯỚNG DẪN SỬ DỤNG VEO STUDIO AI PRO (v3.1)

Chào mừng bạn đến với **Veo Studio AI PRO v3.1** — Hệ thống tự động hóa sáng tạo kịch bản, render video ngắn bằng Google Veo / Gemini API, xử lý ghép nối FFmpeg và đăng tải tự động lên các nền tảng mạng xã hội (Facebook Reels, TikTok).

---

## 📌 MỤC LỤC
1. [Khởi Động & Đăng Nhập Hệ Thống](#1-khởi-động--đăng-nhập-hệ-thống)
2. [Sinh Kịch Bản & Veo Prompt Hàng Loạt](#2-sinh-kịch-bản--veo-prompt-hàng-loạt)
3. [Quản Lý & Ghép Video Trong Thư Viện (FFmpeg Direct)](#3-quản-lý--ghép-video-trong-thư-viện-ffmpeg-direct)
4. [Đăng Video Tự Động Lên Facebook & TikTok](#4-đăng-video-tự-động-lên-facebook--tiktok)
5. [Một Số Lưu Ý & Xử Lý Lỗi Thường Gặp](#5-một-số-lưu-ý--xử-lý-lỗi-thường-gặp)

---

## 1. Khởi Động & Đăng Nhập Hệ Thống

### 🔑 Các bước đăng nhập:
1. Mở ứng dụng bằng cách nhấp đúp vào **Veo Studio AI Desktop** trên màn hình.
2. Tại màn hình Đăng Nhập:
   - **Email:** Nhập địa chỉ Email tài khoản của bạn.
   - **Mật khẩu:** Nhập mật khẩu đã đăng ký.
   - **Mã Máy (MAC ID):** Hệ thống tự động nhận diện phần cứng máy tính của bạn và tự động điền.
3. Nhấn **Đăng Nhập**.

> [!NOTE]  
> Hệ thống áp dụng cơ chế tự động liên kết thiết bị (MAC ID Binding). Khi đăng nhập thành công, phiên làm việc của bạn sẽ được giữ ổn định vĩnh viễn trên máy tính này mà không cần đăng nhập lại ở các lần khởi động sau.

---

## 2. Sinh Kịch Bản & Veo Prompt Hàng Loạt

Giao diện tab **Sinh Kịch Bản & Veo Prompt** được tối ưu hóa theo dạng **Full Screen Dashboard (2 cột)** giúp bạn thao tác nhanh chóng mà không cần di chuyển lăn chuột.

### 📝 Các thông số cấu hình:

| Thành phần | Mô tả & Cách sử dụng |
| :--- | :--- |
| **Chủ đề / Text Prompt** | Khung nhập văn bản rộng rãi đa dòng. Bạn có thể nhập ý tưởng ngắn (VD: *Mẹo AI 2026*) hoặc nhập kịch bản dài đầy đủ. |
| **Số lượng** | Số lượng tập video ngắn muốn Gemini AI khởi tạo (Mặc định: **10**). |
| **Khóa Context & Nhất Quán** | Tick chọn để giữ nguyên bối cảnh và nhân vật liên tục (Continuous Storyline) xuyên suốt các tập video. |
| **Bối cảnh cố định** | Ô nhập thông tin nhân vật/bối cảnh cố định (VD: *Nam kiến trúc sư 30 tuổi, tóc ngắn, áo khoác đen*). |
| **Veo Engine Settings** | Tùy chỉnh **Tỷ lệ** (*9:16 Shorts* hoặc *16:9 Ngang*), **Thời lượng** (*4s, 6s, 8s*), **Biến thể (x)** và **Model Veo** (*3.1 Lite, 3.1 Fast, 3.1 Standard*). |
| **Styles & Voices** | Chọn phong cách hình ảnh (*Cinematic 4K, 3D Pixar, Neon Cyberpunk...*) và giọng đọc AI (*Hoài Mỹ - Nữ Nam, Nam Minh - Nam Bắc*). |

### 🚀 Cách tiến hành render video:
- **Cách 1 (Tự động hoàn toàn qua API):** Nhấn nút **`Sinh Batch Video Kịch Bản (Gemini API)`** để hệ thống tự động sinh prompt và gửi yêu cầu render về hàng đợi.
- **Cách 2 (Mở Google Labs):** Nhấn nút **`Mở Labs.google & Tạo Video`** để trình duyệt tự động điền prompt và tạo video trực tiếp trên giao diện Google Labs.

---

## 3. Quản Lý & Ghép Video Trong Thư Viện (FFmpeg Direct)

Tab **Thư Viện Video (9:16)** là nơi tập hợp tất cả các video đã render thành công, được tự động gom nhóm theo từng chủ đề kịch bản.

### 🎬 Ghép nối nhiều video thành 1 video dài bằng FFmpeg:
1. Vào tab **Thư Viện Video**.
2. Tích chọn lần lượt từng video bạn muốn ghép lại với nhau.
3. Quan sát **Huy hiệu thứ tự chọn (`#1`, `#2`, `#3`...)** hiển thị ở góc trên bên phải từng thẻ video:
   - Video tick đầu tiên là **`#1`** (bắt đầu).
   - Video tick tiếp theo là **`#2`**, **`#3`**...
4. Nhấn nút **`Ghép X Video Đã Chọn (FFmpeg)`** ở thanh công cụ phía trên.
5. Nhập tiêu đề cho video tổng hợp và nhấn **OK**.

> [!TIP]  
> Quá trình ghép video sử dụng **FFmpeg Direct Engine** xử lý trực tiếp trên máy tính của bạn với tốc độ cực nhanh, giữ nguyên 100% chất lượng sắc nét 1080p/4K mà không cần tải lại lên mạng.

---

## 4. Đăng Video Tự Động Lên Facebook & TikTok

Hệ thống tích hợp sẵn trình đăng video tự động đa tài khoản:

### 📱 Các bước thực hiện:
1. Chuyển sang tab **Cấu Hình Mạng Xã Hội (Social)**.
2. Chọn **Facebook Profiles** hoặc **TikTok Profiles**.
3. Thêm tài khoản bằng cách nhập Cookie hoặc đăng nhập phiên duyệt web.
4. Tại mỗi thẻ video trong **Thư Viện Video**, bạn có thể:
   - Nhấn **`Đăng FB`** để đăng ngay lên Facebook Reels.
   - Nhấn **`Đăng TikTok`** để đăng trực tiếp lên tài khoản TikTok đã kết nối.

---

## 5. Một Số Lưu Ý & Xử Lý Lỗi Thường Gặp

> [!WARNING]  
> - **Không đóng cửa sở ứng dụng khi đang render:** Nếu ứng dụng bị tắt giữa chừng, các tiến trình render hoặc ghép video FFmpeg dở dang sẽ bị tạm dừng.
> - **Cập nhật phiên bản:** Khi có thông báo phiên bản mới, hãy nhấn liên kết cập nhật để đảm bảo tính ổn định và tương thích với API mới nhất của Google Veo.

*Chúc bạn sáng tạo ra nhiều video ngắn triệu view cùng Veo Studio AI PRO!*
