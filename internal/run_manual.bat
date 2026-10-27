@echo off
setlocal
cd /d "%~dp0"

echo Reconnecting to campus Wi-Fi. This may take a minute...
where py.exe >nul 2>nul
if not errorlevel 1 (
py -3 "%~dp0campus_wifi_auto_login_once.py" --manual
) else (
    python "%~dp0campus_wifi_auto_login_once.py" --manual
)
if errorlevel 1 (
    echo Reconnection failed. See %USERPROFILE%\campus_wifi_auto_login_logs\keeper_once.log
) else (
    echo Reconnection completed successfully.
)
pause
