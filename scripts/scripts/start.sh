#!/bin/bash
set -e

echo "🚀 Starting Qingliuxue services..."

# 启动 FastAPI 后端（后台运行）
python -m uvicorn app.backend.api.main:app --host 0.0.0.0 --port 8000 &

# 等待后端启动完成
sleep 4

# 启动 Streamlit 前端（前台运行，保持容器存活）
exec python -m streamlit run app/frontend/streamlit_app.py \
    --server.port 8501 \
    --server.headless true \
    --server.address 0.0.0.0