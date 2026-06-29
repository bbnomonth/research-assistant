#!/usr/bin/env bash
# One-command launcher for Linux / macOS / WSL.
# Starts the FastAPI backend and the Vite dev server as background
# processes and tails their combined logs to this terminal.
#
# Stop both with Ctrl+C — both processes will be terminated cleanly.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="${PROJECT_ROOT}/backend"
FRONTEND_DIR="${PROJECT_ROOT}/frontend"
LOG_DIR="${PROJECT_ROOT}/data/logs"
mkdir -p "${LOG_DIR}"

PYTHON_BIN="${PYTHON_BIN:-python3}"

cleanup() {
  echo
  echo "Stopping backend (PID ${BACKEND_PID:-?}) and frontend (PID ${FRONTEND_PID:-?})..."
  [[ -n "${BACKEND_PID:-}" ]] && kill "${BACKEND_PID}" 2>/dev/null || true
  [[ -n "${FRONTEND_PID:-}" ]] && kill "${FRONTEND_PID}" 2>/dev/null || true
  exit 0
}
trap cleanup INT TERM

echo "[1/2] Starting backend on http://127.0.0.1:8000 ..."
( cd "${BACKEND_DIR}" && \
  "${PYTHON_BIN}" -m uvicorn research_agent.main:app \
    --app-dir src --host 127.0.0.1 --port 8000 --reload \
    >"${LOG_DIR}/backend.log" 2>&1 ) &
BACKEND_PID=$!

echo "[2/2] Starting frontend on http://127.0.0.1:5173 ..."
( cd "${FRONTEND_DIR}" && npm run dev \
    >"${LOG_DIR}/frontend.log" 2>&1 ) &
FRONTEND_PID=$!

echo
echo "Backend PID:  ${BACKEND_PID}   log: ${LOG_DIR}/backend.log"
echo "Frontend PID: ${FRONTEND_PID}  log: ${LOG_DIR}/frontend.log"
echo "Press Ctrl+C to stop both."
echo

tail -f "${LOG_DIR}/backend.log" "${LOG_DIR}/frontend.log"
