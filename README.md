# 🚀 AI Short Video Auto-Generator & Multi-Platform Publisher (100 Video/Ngày)

Hệ thống tự động hóa hoàn chỉnh sản xuất **100 video ngắn 10 giây/ngày** bằng **Python Đa luồng (Multi-threading)**, **Google Veo API**, **Gemini 1.5 Flash/Vision** và **Auto Poster qua Trình duyệt (Playwright)**.

---

## 🌟 Tính Năng Nổi Bật

1. **Auto Script từ Prompt**: Nhập chủ đề, AI tự động suy nghĩ kịch bản 10s + Visual Prompt chuẩn cinematic cho Google Veo API.
2. **Video Cloner & Remaker**: Tải video TikTok/Reels bất kỳ -> Tách giọng (Whisper AI) + Phân tích hình ảnh (Gemini Vision) -> Remake kịch bản mới 100% không lo gậy bản quyền.
3. **Google Veo API Engine**: Sinh video dọc (9:16) độ phân giải cao 10s tự động bất đồng bộ.
4. **Xử Lý Hậu Kỳ Tự Động (FFmpeg & Edge-TTS)**: Tự động ghép giọng đọc AI chuẩn tiếng Việt, tự động tạo & chèn Subtitle đẹp mắt, crop/scale chuẩn 1080x1920.
5. **Auto Post Social Media qua Trình Duyệt**: Tự động đăng video lên **Facebook Reels**, **TikTok**, **X (Twitter)** bằng phiên trình duyệt lưu sẵn Cookie/Session (chỉ cần đăng nhập 1 lần).
6. **Đa Luồng Multi-Threading Task Queue**: Sử dụng `ThreadPoolExecutor` chia luồng xử lý độc lập cho từng giai đoạn, giúp chạy tối đa công suất 100 video/ngày.

---

## 🛠️ Hướng Dẫn Cài Đặt

### 1. Cài đặt các thư viện Python
Mở Terminal tại thư mục dự án và chạy:
```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Cấu hình API Key
Tạo file `.env` tại thư mục gốc `d:\AI Video\.env`:
```env
GEMINI_API_KEY=AIzaSy...
```

---

## 🚀 Hướng Dẫn Sử Dụng

Khởi chạy ứng dụng điều khiển:
```bash
python main.py
```

### Bước 1: Đăng nhập Trình duyệt (Chỉ làm 1 lần đầu)
1. Chọn mục `3. 🔑 Đăng nhập Trình duyệt Social Networks`.
2. Lần lượt mở trình duyệt đăng nhập tài khoản **Facebook**, **TikTok**, **X**.
3. Hệ thống sẽ tự động lưu phiên đăng nhập (Cookies/Session) cho các lần tự động đăng tiếp theo.

### Bước 2: Thêm Job Tạo Video
- **Cách 1 (Từ Prompt)**: Chọn mục `1`, nhập chủ đề (ví dụ: `Mẹo công nghệ`) và số lượng (ví dụ: `10` hoặc `50`).
- **Cách 2 (Clone Video)**: Chọn mục `2`, dán link video TikTok/Shorts để hệ thống tự động remake.

### Bước 3: Khởi Chạy Hệ Thống Đa Luồng
- Chọn mục `4. 🚀 KHỞI CHẠY HỆ THỐNG ĐA LUỒNG`.
- Hệ thống sẽ tự động chạy ngầm toàn bộ quy trình: `Sinh kịch bản` ➔ `Gọi Veo API` ➔ `Render FFmpeg` ➔ `Tự động Đăng Facebook, TikTok, X`.

---

## 📁 Cấu Trúc Dự Án

```
d:\AI Video\
├── config/             # Cấu hình cài đặt & prompt templates
├── core/               # Engine kịch bản, Veo API, FFmpeg, Whisper, SQLite
├── publishers/         # Automation đăng bài Facebook, TikTok, X
├── storage/            # Cơ sở dữ liệu SQLite & lưu trữ video xuất ra
├── queue_manager.py    # Điều phối đa luồng ThreadPoolExecutor
├── main.py             # Dashboard điều khiển CLI
└── requirements.txt    # Danh sách thư viện
```
