# 🚀 Hướng Dẫn Chi Tiết Triển Khai Phương Án 3 (Cloudflare Tunnel - Miễn Phí Qua Internet)

Phương án này giúp bạn **biến máy tính cá nhân ở nhà thành Máy Chủ Trung Tâm**. Các máy cài App ở bất kỳ đâu trên thế giới (khác mạng Wifi/LAN) vẫn có thể kết nối về máy bạn để xác thực bản quyền & lưu trữ dữ liệu hoàn toàn **MIỄN PHÍ**, không cần mua Cloud VPS và không cần mở Port Router!

---

## 🛠️ BƯỚC 1: Bật Server Trung Tâm trên Máy Chủ của bạn

Tại máy chủ chính (máy chạy Docker), nhấp đúp vào tệp **`Chay_Docker_WebAdmin.bat`** hoặc mở Terminal chạy:

```bash
docker-compose -f docker-compose.admin.yml up --build -d
```

Lệnh này sẽ tự động khởi chạy 3 dịch vụ:
1. `veostudio_postgres`: Database PostgreSQL lưu trữ toàn bộ User, License & MAC ID.
2. `veostudio_webadmin`: Web Admin quản trị hệ thống.
3. `veostudio_admin_tunnel`: Cloudflare Tunnel kết nối máy bạn ra Internet với chuẩn bảo mật HTTPS.

---

## 🌐 BƯỚC 2: Lấy Đường Dẫn Public (HTTPS URL)

Nhấp đúp vào tệp **`Get_Tunnel_Url.bat`** (hoặc gõ `docker logs veostudio_admin_tunnel`).

Bạn sẽ nhìn thấy một đường dẫn Public HTTPS do Cloudflare cấp, ví dụ:
👉 `https://abc-xyz-123.trycloudflare.com`

- Bạn có thể vào trình duyệt máy tính/điện thoại bất kỳ gõ: `https://abc-xyz-123.trycloudflare.com/admin` để quản lý Web Admin từ xa.

---

## 📦 BƯỚC 3: Cấu Hình Bản Build App để gửi sang Máy Khác

Khi bạn Build file cài đặt (`.exe`) để gửi cho khách hàng / máy khác:

1. Trong thư mục dự án trên máy dev, mở file **`.env`** (hoặc `config/settings.py`).
2. Sửa thuộc tính `CENTRAL_SERVER_URL` thành đường dẫn Cloudflare Tunnel thu được ở Bước 2:

```env
CENTRAL_SERVER_URL=https://abc-xyz-123.trycloudflare.com
```

3. Tiến hành Build ra ứng dụng Desktop (`.exe`).
4. Gửi file `.exe` sang máy khách hàng.

---

## 📱 BƯỚC 4: Trải Nghiệm Trên Máy Khách Hàng (Client)

1. Máy khách hàng mở ứng dụng `.exe`.
2. Đăng nhập bằng **Email & Mật khẩu** mà bạn đã tạo cho họ trên Web Admin.
3. App tự động gửi yêu cầu về `https://abc-xyz-123.trycloudflare.com/api/auth/login`.
4. Server tại nhà bạn xác thực thành công $\rightarrow$ Giao diện App ở máy khách hàng tự động mở khóa các tính năng và ghi nhớ mã máy MAC ID!

---

### 💡 Mẹo Nâng Cấp (Tùy chọn):
Nếu muốn cố định đường dẫn (không bị đổi URL mỗi lần khởi động lại Docker), bạn có thể gán Tên miền cá nhân của bạn (ví dụ `https://admin.veostudio.ai`) vào Cloudflare Tunnel hoàn toàn miễn phí trong bảng điều khiển Cloudflare Zero Trust.
