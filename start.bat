@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Зупиняю попередній сервер на порту 8080...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8090 " ^| findstr LISTENING') do taskkill /F /PID %%p >nul 2>&1
echo Встановлюю залежності...
python -m pip install -q -r requirements.txt
set REPLAY=
set REPLAY_FROM_MIN=
start "" http://localhost:8090
echo Тривога: живий моніторинг каналів і офіційних тривог. http://localhost:8090  (закрити - Ctrl+C)
python -m uvicorn app.main:app --port 8090
pause
