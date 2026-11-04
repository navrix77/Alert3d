@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Тривога — сервер
echo Зупиняю попередній сервер (усі процеси Тривоги)...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -match 'app.main:app' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8090 " ^| findstr LISTENING') do taskkill /F /PID %%p >nul 2>&1
echo Встановлюю залежності...
python -m pip install -q -r requirements.txt
set REPLAY=
set REPLAY_FROM_MIN=
if /i not "%1"=="/silent" start "" http://localhost:8090
:run
echo Тривога працює: http://localhost:8090  (вікно можна згорнути; закрити - Ctrl+C)
python -m uvicorn app.main:app --host 0.0.0.0 --port 8090 --reload --reload-dir app
echo Сервер зупинився - перезапуск через 5 с...
timeout /t 5 /nobreak >nul
goto run
