# eduStudio Dockerfile
#
# Multi-stage build:
#   1. app-builder: Node 20 + Vite 建統一 /app 前端 (frontend/) → /web/eduapp
#   2. final:       Python 3.12 + FFmpeg + Noto CJK + 程式碼 + web/eduapp 服務
#
# U-5 (2026-08-30): legacy /ui 前端退場 — 原 web-builder stage(建 web/→dist)移除,
# 改建唯一正式前端 frontend/ (/app)。修掉「image 只有 /ui 沒有 /app」的舊缺口。
#
# 目標 image size: ~700 MB (python:3.12-slim ~150MB + ffmpeg ~80MB + fonts ~80MB
#                 + Python deps ~400MB)
#
# 用法:
#   docker build -t autosolvervideo:latest .
#   docker run --rm -p 8000:8000 \
#     -e GEMINI_API_KEY=AIza... \
#     -v $(pwd)/jobs:/app/jobs \
#     -v $(pwd)/output:/app/output \
#     -v $(pwd)/pdfs:/app/pdfs \
#     autosolvervideo:latest
#
# 已知未實測項目 (留待 iter 7+):
#   - F5 GPU passthrough (nvidia-docker / --gpus all)
#   - docker-compose.yml 整合 (next iter)
#   - YouTube OAuth client_secret*.json 怎麼 mount (架構決策, 等用戶討論)
#   - production reverse proxy (nginx)

# ============================================================
# Stage 1 — /app 前端 builder（frontend/, React 19 + Vite, base 已寫死 /app/）
# ============================================================
FROM node:20-slim AS app-builder

WORKDIR /frontend

# 先 COPY 鎖檔 + package.json, 利用 layer cache (deps 沒變不重裝)
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
RUN npm run build
# → vite.config.ts outDir 解析為 /web/eduapp (process.cwd()=/frontend 的 ../web/eduapp)


# ============================================================
# Stage 2 — final runtime
# ============================================================
FROM python:3.12-slim AS final

# 系統 deps:
# - ffmpeg: 影片合成 + hardsub (libass 走 force_style)
# - fonts-noto-cjk: CJK 渲染 (msjh.ttc 是 Windows 專屬, 不能 ship)
# - libgl1-mesa-glx + libglib2.0-0: Pillow / cairosvg 需要
# - curl: healthcheck 用
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        fonts-noto-cjk \
        fonts-noto-cjk-extra \
        libgl1 \
        libglib2.0-0 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Python deps - 先 COPY requirements 利用 layer cache
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# COPY 應用程式碼
# (.dockerignore 已排除 __pycache__ / .git / videos/ / output/ / 等 runtime 目錄)
COPY . .

# 從 app-builder 拷貝 /app build artifacts 進來 (server serve 於 /app/)
COPY --from=app-builder /web/eduapp ./web/eduapp

# 字型環境變數對齊 fonts-noto-cjk 的安裝路徑
# CJK 主字型 + 符號 fallback
ENV CLAUDE_FONT_PATH=/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc
ENV CLAUDE_FALLBACK_FONT_PATH=/usr/share/fonts/opentype/noto/NotoSansSymbols-Regular.ttf
ENV CLAUDE_MONO_FONT_PATH=/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf

# 預設不啟 F5 (需 CUDA torch + huggingface model 下載, 不在 base image 內)
# 想用 F5 走 docker-compose 加裝 + GPU passthrough
ENV TTS_PROVIDER=edge

# 中文 stdout / 紀錄不被 cp 編碼擋掉
ENV PYTHONIOENCODING=utf-8
ENV LANG=C.UTF-8

EXPOSE 8000

# Healthcheck — server /health 端點 (200 OK 即綠)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# 啟動指令 — 直接跑 server.main
# (不用 reload, production image 不該 watch 程式碼變化)
CMD ["python", "-m", "server.main"]
