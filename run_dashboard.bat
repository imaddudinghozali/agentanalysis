@echo off
setlocal
cd /d "%~dp0"

set "PYTHONPATH=.deps"
set "TRADING_STRATEGY_DB_PATH=data\trading_strategy.sqlite3"

start "Trading Strategy API" /min powershell -NoExit -ExecutionPolicy Bypass -Command "$env:PYTHONPATH='.deps'; $env:TRADING_STRATEGY_DB_PATH='data\trading_strategy.sqlite3'; uvicorn app:app --host 127.0.0.1 --port 8000"
start "Trading Strategy Dashboard" /min powershell -NoExit -ExecutionPolicy Bypass -Command "cd frontend; npm.cmd run build; if ($LASTEXITCODE -eq 0) { npm.cmd run preview -- --host 127.0.0.1 --port 4173 --strictPort }"

timeout /t 8 /nobreak >nul
start "" "http://127.0.0.1:4173"

echo Dashboard opened at http://127.0.0.1:4173
echo Keep the API and Dashboard windows running while using the app.
pause
