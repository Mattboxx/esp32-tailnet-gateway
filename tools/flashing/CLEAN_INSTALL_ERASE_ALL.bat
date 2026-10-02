@echo off
setlocal
cd /d "%~dp0"
title ESP32-S3 clean install - erase all settings
echo WARNING: THIS ERASES ALL WIFI, TAILSCALE IDENTITY, PASSWORDS AND AUTOMATION SETTINGS.
echo Use UPDATE_KEEP_SETTINGS.bat for an existing installation instead.
set "CONFIRM_ERASE="
set /p "CONFIRM_ERASE=Type YES to erase this ESP32-S3: "
if /I not "%CONFIRM_ERASE%"=="YES" exit /b 2
set "PORT_ARGS="
if not "%~1"=="" set "PORT_ARGS=--port %~1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0VERIFY_FILES.ps1"
if errorlevel 1 goto :error
esptool.exe --chip esp32s3 %PORT_ARGS% erase-flash
if errorlevel 1 goto :error
esptool.exe --chip esp32s3 %PORT_ARGS% --baud 460800 write-flash 0x0 firmware-factory.bin
if errorlevel 1 goto :error
echo Flash complete. Connect to the ESP access point and open http://192.168.4.1/
pause
exit /b 0
:error
echo Flash failed. Check the cable and COM port; close serial monitors.
echo Hold BOOT, tap RESET, release BOOT and try again.
pause
exit /b 1
