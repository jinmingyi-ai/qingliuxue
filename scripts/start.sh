#!/usr/bin/env bash
set -euo pipefail

API_PORT="${API_PORT:-8000}"
STREAMLIT_PORT="${PORT:-8501}"

uvicorn app.backend.api.main:app --host 0.0.0.0 --port "${API_PORT}" &
API_PID="$!"

streamlit run app/frontend/streamlit_app.py \
  --server.address 0.0.0.0 \
  --server.port "${STREAMLIT_PORT}" \
  --server.headless true \
  --browser.gatherUsageStats false

kill "${API_PID}" 2>/dev/null || true

