@echo off
chcp 65001 >nul
rem ================================================================
rem  NAVRYX SKY в інтернет: Google Cloud Run (europe-north1, Фінляндія)
rem  + постійне сховище (Cloud Storage) + домен sky.navryx.com.ua
rem  Потрібен Google Cloud SDK (gcloud), увійдений у ваш акаунт.
rem ================================================================
cd /d "%~dp0"
set SERVICE=navryx-sky
set REGION=europe-north1
set DOMAIN=sky.navryx.com.ua
where gcloud >nul 2>nul
if errorlevel 1 ( echo [!] Не знайдено gcloud: https://cloud.google.com/sdk/docs/install & pause & exit /b 1 )
for /f "delims=" %%p in ('gcloud config get-value project 2^>nul') do set PROJECT=%%p
if "%PROJECT%"=="" ( echo [!] Не вибрано проєкт. Виконайте:  gcloud init & pause & exit /b 1 )
set BUCKET=%PROJECT%-navryx-sky-data
echo Проєкт: %PROJECT%   Регіон: %REGION%
echo [1/4] Вмикаю сервіси (один раз)...
call gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com storage.googleapis.com --project %PROJECT%
echo [2/4] Сховище для пам'яті системи й мап доби: gs://%BUCKET%
call gcloud storage buckets describe gs://%BUCKET% --project %PROJECT% >nul 2>nul || call gcloud storage buckets create gs://%BUCKET% --project %PROJECT% --location %REGION% --uniform-bucket-level-access
echo [3/4] Збираю й розгортаю (5-10 хв)...
call gcloud run deploy %SERVICE% --project %PROJECT% --region %REGION% --source . ^
  --allow-unauthenticated --min-instances 1 --max-instances 1 --no-cpu-throttling ^
  --cpu 1 --memory 1Gi --timeout 3600 --session-affinity --execution-environment gen2 ^
  --set-env-vars LAN_TLS=0,PERSIST_DIR=/persist ^
  --add-volume name=persist,type=cloud-storage,bucket=%BUCKET% --add-volume-mount volume=persist,mount-path=/persist --quiet
if errorlevel 1 ( echo [!] Розгортання не вдалося — надішліть Claude текст помилки вище. & pause & exit /b 1 )
for /f "delims=" %%u in ('gcloud run services describe %SERVICE% --project %PROJECT% --region %REGION% --format "value(status.url)"') do set URL=%%u
echo %URL%> deploy-url.txt
echo [4/4] Домен %DOMAIN%
call gcloud beta run domain-mappings describe --domain %DOMAIN% --project %PROJECT% --region %REGION% >nul 2>nul
if errorlevel 1 (
  call gcloud beta run domain-mappings create --service %SERVICE% --domain %DOMAIN% --project %PROJECT% --region %REGION%
  if errorlevel 1 (
    echo.
    echo [i] Google ще не бачить, що navryx.com.ua ваш. Відкриється сторінка підтвердження:
    echo     додайте запропонований TXT-запис у dnshosting.org ^(хост @^), підтвердіть і запустіть цей файл ще раз.
    call gcloud domains verify navryx.com.ua
    pause & exit /b 0
  )
)
echo.
echo ================================================================
echo  Сервер працює:  %URL%
echo  Для домену додайте в dnshosting.org запис:
echo     хост: sky    тип: CNAME    дані: ghs.googlehosted.com.
echo  За 15-60 хв запрацює https://%DOMAIN%
echo ================================================================
start "" %URL%
pause
