# 🌐 Hướng Dẫn Kết Nối Database & Web Admin Từ Máy Khác (LAN / Internet)

Để các máy tính khác (App Desktop ở máy client hoặc VPS khác) kết nối tới Cơ sở dữ liệu PostgreSQL và Web Admin Server đang chạy ở máy chủ này:

---

### 1. 📌 Địa Chỉ IP Máy Chủ Hiện Tại
- **Địa chỉ IP mạng nội bộ (LAN)**: `10.6.1.27`
- **Port PostgreSQL Database**: `5432`
- **Port Web Admin Server**: `8080`

---

### 2. 🔓 Mở Port Firewall Trên Máy Chủ (Đã Tự Động Xử Lý)
Đã tạo sẵn tệp `Mo_Port_Firewall.bat` để mở inbound port 5432 và 8080.
Nếu cần chạy lại, nhấp đúp vào tệp **`Mo_Port_Firewall.bat`** (Run as Administrator).

---

### 3. ⚙️ Cấu Hình Máy Khác Kết Nối Tới Database (Mạng LAN)

Trên tệp `.env` của ứng dụng ở **máy khác**, cấu hình dòng `POSTGRES_URL` như sau:

```env
POSTGRES_URL=postgresql://postgres:postgrespassword@10.6.1.27:5432/veostudio
```

- Các ứng dụng ở máy khác sẽ tự động kết nối trực tiếp tới PostgreSQL trên máy chủ `10.6.1.27`.
- Quản trị viên ở máy khác có thể truy cập Web Admin tại địa chỉ: **`http://10.6.1.27:8080/admin`**

---

### 4. 🌍 Kết Nối Qua Internet (Ngoại Vi Mạng LAN)

Nếu các máy cài App nằm ở nơi khác (khác mạng Wifi/LAN):
1. Khởi chạy Docker Admin với Cloudflare Tunnel:
   ```bash
   docker-compose -f docker-compose.admin.yml up -d
   ```
2. Mở log của container `tunnel` để lấy URL Public:
   ```bash
   docker logs veostudio_admin_tunnel
   ```
3. Bạn sẽ nhận được URL dạng: `https://xxxx.trycloudflare.com/admin` có thể truy cập từ bất kỳ đâu trên thế giới mà không cần Port Forwarding modem.
