@echo off
setlocal
cd /d "%~dp0"
title ESP32-S3 update - preserve settings
echo ESP32-S3 N16R8 - UPDATE WITHOUT ERASING NVS
echo Connect the USB data cable and close every serial monitor.
echo Existing WiFi, Tailscale identity and automation settings will be preserved.
echo For an already configured board, web OTA with firmware.bin is recommended.
echo Optional usage: UPDATE_KEEP_SETTINGS.bat COM5
pause
set "PORT_ARGS="
if not "%~1"=="" set "PORT_ARGS=--port %~1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0VERIFY_FILES.ps1"
if errorlevel 1 goto :error
esptool.exe --chip esp32s3 %PORT_ARGS% --baud 460800 write-flash --flash-mode dio --flash-freq 80m --flash-size 4MB 0x0 bootloader.bin 0x8000 partitions.bin 0x19000 ota_data_initial.bin 0x20000 firmware.bin
if errorlevel 1 goto :error
echo Flash complete. The board is restarting.
pause
exit /b 0
:error
echo Update failed. Do not erase settings to fix a cable/port problem.
echo Check the USB data cable and COM port. Hold BOOT, tap RESET, release BOOT, retry.
pause
exit /b 1
