@echo off
chcp 65001 >nul
rem Віджет «Тривоги»: маленьке окреме вікно з вашим станом (сервер має бути запущений — start.bat)
set URL=http://localhost:8090/?mini=1
where msedge >nul 2>nul && (start "" msedge --app=%URL% --window-size=400,320 & exit /b)
if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" (start "" "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" --app=%URL% --window-size=400,320 & exit /b)
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" (start "" "%ProgramFiles%\Google\Chrome\Application\chrome.exe" --app=%URL% --window-size=400,320 & exit /b)
start "" %URL%
