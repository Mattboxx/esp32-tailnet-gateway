@echo off
setlocal
cd /d "%~dp0.."
title ESP32 Tailnet Gateway - install on a new device (erases everything)
echo ESP32 Tailnet Gateway - Mattboxx Edition
echo INSTALL ON A NEW DEVICE: this ERASES all Wi-Fi, tailnet identity, passwords and settings.
echo For a configured gateway use UPDATE-KEEP-SETTINGS.bat instead.
echo Optional usage: INSTALL-NEW-DEVICE.bat COM5
set "CONFIRM_ERASE="
set /p "CONFIRM_ERASE=Type ERASE to continue: "
if not "%CONFIRM_ERASE%"=="ERASE" (
  echo Cancelled. Nothing was written.
  pause
  exit /b 2
)
set "PORT_ARGS="
if not "%~1"=="" set "PORT_ARGS=--port %~1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0VERIFY-FILES.ps1"
if errorlevel 1 goto :error
windows\esptool.exe --chip esp32s3 %PORT_ARGS% chip-id >nul 2>&1
if errorlevel 1 goto :nochip
set "FACTORY="
for %%F in (firmware\*-WiFi-factory.bin) do set "FACTORY=%%F"
if "%FACTORY%"=="" goto :error
windows\esptool.exe --chip esp32s3 %PORT_ARGS% erase-flash
if errorlevel 1 goto :error
windows\esptool.exe --chip esp32s3 %PORT_ARGS% --baud 460800 write-flash 0x0 "%FACTORY%"
if errorlevel 1 goto :error
echo.
echo Done. Power the board, join the Wi-Fi ESP32-Tailnet-Setup-XXXX and follow the setup page.
echo If nothing opens, browse to http://192.168.4.1/
pause
exit /b 0
:nochip
echo No ESP32-S3 answered. This firmware needs an ESP32-S3.
echo Check the USB data cable, close serial monitors, give the COM port (e.g. INSTALL-NEW-DEVICE.bat COM5),
echo or hold BOOT, tap RESET, release BOOT and retry.
pause
exit /b 1
:error
echo Flash failed. Check the cable and COM port; close serial monitors.
echo Hold BOOT, tap RESET, release BOOT and try again.
pause
exit /b 1
