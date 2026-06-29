@echo off
REM One-command launcher for Windows PowerShell / cmd.
REM Starts the FastAPI backend and the Vite dev server in two new
REM terminal windows so you can interact with both at once.

setlocal

set "PYTHON_EXE=%PYTHON_EXE%"
if "%PYTHON_EXE%"=="" set "PYTHON_EXE=python"

set "PROJECT_ROOT=%~dp0"
set "BACKEND_DIR=%PROJECT_ROOT%backend"
set "FRONTEND_DIR=%PROJECT_ROOT%frontend"

echo Starting backend in a new window...
start "research-agent-backend" cmd /k "cd /d ""%BACKEND_DIR%"" && ""%PYTHON_EXE%"" -m uvicorn research_agent.main:app --app-dir src --host 127.0.0.1 --port 8000 --reload"

echo Starting frontend in a new window...
start "research-agent-frontend" cmd /k "cd /d ""%FRONTEND_DIR%"" && npm run dev"

echo Done. Backend: http://127.0.0.1:8000  Frontend: http://127.0.0.1:5173
endlocal
