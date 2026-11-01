@echo off
chcp 65001 >nul
rem ================================================================
rem  «Тривога» в інтернет: Google Cloud Run (europe-central2, Варшава)
rem  Потрібен Google Cloud SDK (gcloud) — той самий, що для «Комори».
rem ================================================================
cd /d "%~dp0"
where gcloud >nul 2>nul
if errorlevel 1 (
  echo [!] Не знайдено gcloud. Встановіть: https://cloud.google.com/sdk/docs/install  і запустіть цей файл ще раз.
  pause & exit /b 1
)
for /f "delims=" %%p in ('gcloud config get-value project 2^>nul') do set PROJECT=%%p
if "%PROJECT%"=="" (
  echo [!] Не вибрано проєкт Google Cloud. Виконайте:  gcloud init
  pause & exit /b 1
)
echo Проєкт: %PROJECT%
echo Вмикаю потрібні сервіси (один раз)...
call gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com --project %PROJECT%
echo Збираю й розгортаю (5-10 хв)...
call gcloud run deploy tryvoga --project %PROJECT% --region europe-central2 --source . ^
  --allow-unauthenticated --min-instances 1 --max-instances 1 --no-cpu-throttling ^
  --cpu 1 --memory 1Gi --timeout 3600 --session-affinity --quiet
if errorlevel 1 ( echo [!] Розгортання не вдалося — надішліть Claude текст помилки вище. & pause & exit /b 1 )
for /f "delims=" %%u in ('gcloud run services describe tryvoga --project %PROJECT% --region europe-central2 --format "value(status.url)"') do set URL=%%u
echo.
echo ================================================================
echo  Готово:  %URL%
echo  Відкрийте на телефоні, або вкажіть цю адресу в налаштуваннях застосунку.
echo ================================================================
echo %URL%> deploy-url.txt
start "" %URL%
pause
