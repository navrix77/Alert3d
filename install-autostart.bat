@echo off
chcp 65001 >nul
rem Автозапуск «Тривоги» під час входу в Windows (згорнутим вікном, без відкриття браузера)
set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
> "%STARTUP%\Tryvoga.vbs" echo CreateObject("WScript.Shell").Run """%~dp0start.bat"" /silent", 7, False
echo Готово: Тривога запускатиметься сама під час входу в Windows.
echo Щоб вимкнути - видаліть "%STARTUP%\Tryvoga.vbs"
echo Запускаю зараз...
start "" /min "%~dp0start.bat"
pause
