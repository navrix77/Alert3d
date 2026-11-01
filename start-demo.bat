@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -m pip install -q -r requirements.txt
set REPLAY=1
set REPLAY_FROM_MIN=420
start "" http://localhost:8080
echo Тривога: ДЕМО на записаній ночі 29-30.10. http://localhost:8080
python -m uvicorn app.main:app --port 8080
pause
