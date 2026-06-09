FROM ubuntu:22.04

# 避免安裝過程卡住
ENV DEBIAN_FRONTEND=noninteractive
ENV DISPLAY=:1

# 安裝所有必要套件 (包含 Nginx 做為內部橋接)
RUN apt-get update && apt-get install -y \
    chromium-browser \
    xvfb \
    x11vnc \
    fluxbox \
    novnc \
    websockify \
    nginx \
    python3 \
    python3-pip \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

# 安裝 Python 核心庫
RUN pip3 install --no-cache-dir flask google-api-python-client google-auth-oauthlib requests werkzeug

# 啟動主程式
CMD ["python3", "app.py"]
