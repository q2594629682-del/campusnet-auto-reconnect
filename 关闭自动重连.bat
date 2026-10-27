@echo off
setlocal
set "MODE_FILE=%~dp0internal\auto_login_mode.txt"
if not exist "%~dp0internal\run_hidden.vbs" goto missing

> "%MODE_FILE%" echo(off
findstr /x /c:"off" "%MODE_FILE%" >nul 2>nul
if errorlevel 1 goto failed

echo Campus Wi-Fi automatic reconnect: OFF
if /i "%~1"=="/quiet" exit /b 0
pause
exit /b 0

:missing
echo Missing internal\run_hidden.vbs. Keep this BAT beside the internal folder.
if /i "%~1"=="/quiet" exit /b 1
pause
exit /b 1

:failed
echo Failed to disable automatic reconnect.
if /i "%~1"=="/quiet" exit /b 1
pause
exit /b 1
