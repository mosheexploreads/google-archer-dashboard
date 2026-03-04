@echo off
title Ads Dashboard

echo Killing any old server processes...
taskkill /F /IM uvicorn.exe /T >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do taskkill /F /PID %%a >nul 2>&1

echo Starting backend...
start "Backend" cmd /k "cd /d %~dp0backend && .venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload"

echo Starting frontend...
start "Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo Waiting for servers to start...
timeout /t 4 /nobreak >nul

echo Opening browser...
start http://localhost:5173

echo.
echo Dashboard is running at http://localhost:5173
echo Close the two server windows to stop.
