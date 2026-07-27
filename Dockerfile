# ============================================
# Veo Studio AI PRO - Production Dockerfile
# Multi-stage build for optimized image size
# ============================================

# Stage 1: Build dependencies
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ============================================
# Stage 2: Production runtime
# ============================================
FROM python:3.12-slim AS runtime

LABEL maintainer="thaind197"
LABEL description="Veo Studio AI PRO - AI Short Video Automation & Social Publishing Server"
LABEL version="2.5.0"

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    TZ=Asia/Ho_Chi_Minh

WORKDIR /app

# Install system dependencies (FFmpeg + Playwright browser deps)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    # Playwright Chromium dependencies
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libwayland-client0 \
    # Font support for video rendering
    fonts-noto-cjk \
    fonts-liberation \
    # Utilities
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Install Playwright browsers (Chromium only for smaller image)
RUN playwright install chromium

# Copy application source code
COPY config/ ./config/
COPY core/ ./core/
COPY publishers/ ./publishers/
COPY ui/ ./ui/
COPY server.py .
COPY main.py .
COPY queue_manager.py .
COPY ui_server.py .
COPY _login_browser.py .
COPY .env.example .

# Create storage directories
RUN mkdir -p \
    storage/downloads \
    storage/generated \
    storage/final \
    storage/browser_sessions/facebook \
    storage/browser_sessions/tiktok \
    storage/browser_sessions/x

# Expose server port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/stats || exit 1

# Start FastAPI server (production mode, no reload)
CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
