@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Перенесення ключів з .env.local на сервер (напряму з вашого ПК через gcloud, не через репозиторій)
if "%~1"=="" (set SRC=.env.local) else (set SRC=%~1)
bash deploy/push-env.sh "%SRC%"
pause
