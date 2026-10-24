@echo off
setlocal
cd /d "%~dp0.."
title ESP32 Tailnet Gateway - install on a new device (erases everything)
echo ESP32 Tailnet Gateway - Mattboxx Edition
echo INSTALL ON A NEW DEVICE: this ERASES all Wi-Fi, tailnet identity, passwords and settings.
echo For a configured gateway use UPDATE-KEEP-SETTINGS.bat instead.
echo Optional usage: INSTALL-NEW-DEVICE.bat COM5 [en^|it^|es^|zh]
call :pick_language "%~2"
if errorlevel 1 goto :badlanguage
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
windows\esptool.exe --chip esp32s3 %PORT_ARGS% erase-flash
if errorlevel 1 goto :error
windows\esptool.exe --chip esp32s3 %PORT_ARGS% --baud 460800 write-flash --flash-mode dio --flash-freq 80m --flash-size 4MB 0x0 firmware\bootloader.bin 0x8000 firmware\partitions.bin 0x19000 firmware\ota_data_initial.bin 0x20000 "%APP%"
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
:badlanguage
pause
exit /b 2
:error
echo Flash failed. Check the cable and COM port; close serial monitors.
echo Hold BOOT, tap RESET, release BOOT and try again.
pause
exit /b 1

:pick_language
rem Web UI language: one image per language keeps the board's memory free.
set "APP=firmware\firmware.bin"
set "LANGPICK=%~1"
if not "%LANGPICK%"=="" goto :have_language
echo Web interface language:
echo   1  English (standard)
echo   2  Italiano
echo   3  Espanol
echo   4  Chinese (simplified)
set /p "LANGPICK=Choose 1-4 and press Enter [1]: "
:have_language
if "%LANGPICK%"=="" set "LANGPICK=en"
if "%LANGPICK%"=="1" set "LANGPICK=en"
if "%LANGPICK%"=="2" set "LANGPICK=it"
if "%LANGPICK%"=="3" set "LANGPICK=es"
if "%LANGPICK%"=="4" set "LANGPICK=zh"
if /i "%LANGPICK%"=="en" set "APP=firmware\firmware.bin"& goto :language_ok
if /i "%LANGPICK%"=="it" set "APP=firmware\firmware-it.bin"& goto :language_ok
if /i "%LANGPICK%"=="es" set "APP=firmware\firmware-es.bin"& goto :language_ok
if /i "%LANGPICK%"=="zh" set "APP=firmware\firmware-zh.bin"& goto :language_ok
echo Unknown language "%LANGPICK%": use en, it, es or zh.
exit /b 1
:language_ok
if not exist "%APP%" echo %APP% is missing from this package.& exit /b 1
echo Web interface language: %LANGPICK% (%APP%)
exit /b 0
