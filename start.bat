@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Встановлюю залежності...
python -m pip install -q -r requirements.txt
set REPLAY=
start "" http://localhost:8080
echo Тривога: живий моніторинг каналів і офіційних тривог. http://localhost:8080  (закрити - Ctrl+C)
python -m uvicorn app.main:app --port 8080
pause
