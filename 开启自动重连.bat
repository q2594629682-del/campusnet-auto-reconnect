@echo off
setlocal
set "MODE_FILE=%~dp0internal\auto_login_mode.txt"
if not exist "%~dp0internal\run_hidden.vbs" goto missing

> "%MODE_FILE%" echo(on
findstr /x /c:"on" "%MODE_FILE%" >nul 2>nul
if errorlevel 1 goto failed

echo Campus Wi-Fi automatic reconnect: ON
echo The hidden task will check every 5 minutes.
if /i "%~1"=="/quiet" exit /b 0
pause
exit /b 0

:missing
echo Missing internal\run_hidden.vbs. Keep this BAT beside the internal folder.
if /i "%~1"=="/quiet" exit /b 1
pause
exit /b 1

:failed
echo Failed to enable automatic reconnect.
if /i "%~1"=="/quiet" exit /b 1
pause
exit /b 1
