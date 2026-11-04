@echo off
chcp 65001 >nul
rem Дозволяє телефонам у домашній мережі відкривати NAVRYX SKY (порти 8090 і 8443). Запускати ПРАВОЮ КНОПКОЮ -> "Запуск від імені адміністратора".
net session >nul 2>&1 || (echo Потрібні права адміністратора: правий клік -^> Запуск від імені адміністратора & pause & exit /b 1)
powershell -NoProfile -Command "Remove-NetFirewallRule -DisplayName NAVRYX SKY -ErrorAction SilentlyContinue; New-NetFirewallRule -DisplayName NAVRYX SKY -Direction Inbound -Protocol TCP -LocalPort 8090,8443 -Action Allow -Profile Any | Out-Null; Get-NetConnectionProfile | Format-Table Name,NetworkCategory,IPv4Connectivity -AutoSize"
echo Готово: порти 8090 і 8443 відкриті для домашньої мережі.
pause
