@echo off
chcp 65001 >nul
rem ================================================================
rem  NAVRYX SKY в інтернет: віртуальна машина Google Compute Engine
rem  e2-small, europe-north1 (Фінляндія), Ubuntu 24.04, HTTPS (Caddy)
rem  домен sky.navryx.com.ua. Далі сервер сам оновлюється з GitHub.
rem  Потрібен Google Cloud SDK (gcloud), увійдений у ваш акаунт.
rem ================================================================
cd /d "%~dp0"
set VM=navryx-sky
set ZONE=europe-north1-a
set REGION=europe-north1
set DOMAIN=sky.navryx.com.ua
where gcloud >nul 2>nul
if errorlevel 1 ( echo [!] Не знайдено gcloud. Встановіть: https://cloud.google.com/sdk/docs/install і запустіть цей файл ще раз. & pause & exit /b 1 )
for /f "delims=" %%p in ('gcloud config get-value project 2^>nul') do set PROJECT=%%p
if "%PROJECT%"=="" ( echo [!] Не вибрано проєкт. Виконайте:  gcloud init & pause & exit /b 1 )
echo Проєкт: %PROJECT%   Зона: %ZONE%
echo [1/4] Вмикаю Compute Engine (один раз, до 1 хв)...
call gcloud services enable compute.googleapis.com --project %PROJECT%
if errorlevel 1 ( echo [!] Не вдалося. Можливо, у проєкті не підключено оплату: https://console.cloud.google.com/billing & pause & exit /b 1 )
echo [2/4] Постійна IP-адреса
call gcloud compute addresses describe %VM%-ip --region %REGION% --project %PROJECT% >nul 2>nul || call gcloud compute addresses create %VM%-ip --region %REGION% --project %PROJECT%
for /f "delims=" %%a in ('gcloud compute addresses describe %VM%-ip --region %REGION% --project %PROJECT% --format "value(address)"') do set IP=%%a
echo [3/4] Дозволяю вхід на 80/443 (лише для цієї машини)
call gcloud compute firewall-rules describe %VM%-web --project %PROJECT% >nul 2>nul || call gcloud compute firewall-rules create %VM%-web --project %PROJECT% --allow tcp:80,tcp:443 --target-tags %VM% --description "NAVRYX SKY web"
echo [4/4] Віртуальна машина
call gcloud compute instances describe %VM% --zone %ZONE% --project %PROJECT% >nul 2>nul
if errorlevel 1 (
  call gcloud compute instances create %VM% --project %PROJECT% --zone %ZONE% --machine-type e2-small ^
    --image-family ubuntu-2404-lts-amd64 --image-project ubuntu-os-cloud --boot-disk-size 20GB --boot-disk-type pd-balanced ^
    --address %IP% --tags %VM% --metadata domain=%DOMAIN% --metadata-from-file startup-script=deploy\vm-setup.sh
  if errorlevel 1 ( echo [!] Машину не створено — надішліть Claude текст помилки вище. & pause & exit /b 1 )
) else (
  echo Машина вже є — оновлюю скрипт запуску й перезапускаю його
  call gcloud compute instances add-metadata %VM% --zone %ZONE% --project %PROJECT% --metadata domain=%DOMAIN% --metadata-from-file startup-script=deploy\vm-setup.sh
  call gcloud compute ssh %VM% --zone %ZONE% --project %PROJECT% --command "sudo google_metadata_script_runner startup"
)
echo %IP%> deploy-ip.txt
echo.
echo ================================================================
echo  Машина створена. Перше встановлення триває 5-10 хв.
echo  Перевірка (через 10 хв):   http://%IP%
echo.
echo  Для домену додайте в dnshosting.org запис:
echo     хост: sky    тип: A    дані: %IP%
echo  За 15-60 хв запрацює https://%DOMAIN%  (сертифікат ставиться сам)
echo ================================================================
pause
