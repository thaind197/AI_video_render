# Sử dụng hình ảnh Playwright Python chính thức đã tích hợp sẵn Chromium
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

# Thiết lập thư mục làm việc
WORKDIR /app

# Cài đặt FFmpeg và phông chữ hỗ trợ CJK / tiếng Việt
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-noto-cjk \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Copy file requirements và cài đặt Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy mã nguồn ứng dụng
COPY . .

# Tạo các thư mục lưu trữ dữ liệu
RUN mkdir -p storage/browser_sessions storage/logs storage/generated storage/downloads

# Expose port 8000 của ứng dụng
EXPOSE 8000

# Khởi chạy server FastAPI
CMD ["python", "server.py"]
