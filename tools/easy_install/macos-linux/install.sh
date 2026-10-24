#!/bin/sh
# ESP32 Tailnet Gateway - Mattboxx Edition: Easy Install for macOS and Linux.
#   sh macos-linux/install.sh new    [PORT]   new device: erases everything
#   sh macos-linux/install.sh update [PORT]   configured device: keeps settings
#                                              (also moves a 2.x gateway to the
#                                              3.0 8 MB layout, settings kept)
# Needs Python 3 and esptool 5:  python3 -m pip install --user "esptool>=5,<6"
set -eu
cd "$(dirname "$0")/.."
FW=firmware

say() { printf '%s\n' "$*"; }
fail() { say ""; say "ERROR: $*"; exit 1; }

MODE=${1:-}
PORT=${2:-}
case "$MODE" in
  new|update) ;;
  *) say "Usage: sh macos-linux/install.sh new|update [PORT]"
     say "  new     first install or reset: ERASES all settings"
     say "  update  configured device: keeps Wi-Fi, tailnet identity and settings"
     exit 2 ;;
esac

# esptool 5 (hyphenated commands such as write-flash).
if command -v esptool >/dev/null 2>&1; then
  ESPTOOL="esptool"
elif command -v python3 >/dev/null 2>&1 && python3 -m esptool version >/dev/null 2>&1; then
  ESPTOOL="python3 -m esptool"
else
  fail "esptool not found. Install it once with:  python3 -m pip install --user \"esptool>=5,<6\""
fi
MAJOR=$($ESPTOOL version 2>/dev/null | sed -n 's/.*v\{0,1\}\([0-9][0-9]*\)\.[0-9][0-9]*\.[0-9].*/\1/p' | head -n 1)
[ -n "$MAJOR" ] && [ "$MAJOR" -ge 5 ] || fail "esptool 5 is required (found: ${MAJOR:-unknown}). Run: python3 -m pip install --user --upgrade \"esptool>=5,<6\""

# Checksums before anything touches the board.
if command -v sha256sum >/dev/null 2>&1; then
  sha256sum -c --quiet SHA256SUMS.txt || fail "checksum mismatch: download the package again."
elif command -v shasum >/dev/null 2>&1; then
  shasum -a 256 -c --quiet SHA256SUMS.txt || fail "checksum mismatch: download the package again."
else
  fail "no sha256sum or shasum command to verify the files."
fi
say "Package checksums verified."

# Serial port: argument, or the only USB serial port present.
if [ -z "$PORT" ]; then
  CANDIDATES=${SERIAL_CANDIDATES:-"/dev/cu.usbmodem* /dev/cu.usbserial* /dev/cu.wchusbserial* /dev/cu.SLAB_USBtoUART* /dev/ttyACM* /dev/ttyUSB*"}
  FOUND=""
  for p in $CANDIDATES; do [ -e "$p" ] && FOUND="$FOUND $p"; done
  set -- $FOUND
  if [ $# -eq 0 ]; then
    fail "no USB serial port found. Check the data cable, install the CP210x/CH34x driver if your board needs it, then hold BOOT, tap RESET, release BOOT and retry."
  elif [ $# -gt 1 ]; then
    say "Several serial ports found:$FOUND"
    fail "run again with the port, e.g.: sh macos-linux/install.sh $MODE $1"
  fi
  PORT=$1
fi
say "Using port $PORT"

# Identify the chip before writing: other chips are refused.
if ! $ESPTOOL --chip esp32s3 --port "$PORT" chip-id >/dev/null 2>&1; then
  fail "no ESP32-S3 answered on $PORT. This firmware needs an ESP32-S3; on Linux, a permission error means adding your user to the dialout (Debian/Ubuntu) or uucp (Arch) group."
fi
say "ESP32-S3 detected."

# Fixed file names without spaces: the list is split on purpose.
WRITE_ARGS="--flash-mode dio --flash-freq 80m --flash-size 8MB 0x0 $FW/bootloader.bin 0x8000 $FW/partitions.bin 0x19000 $FW/ota_data_initial.bin 0x20000 $FW/firmware.bin"
if [ "$MODE" = new ]; then
  say ""
  say "WARNING: this ERASES all Wi-Fi, tailnet identity, passwords and settings on the board."
  printf 'Type ERASE to continue: '
  read -r ANSWER || ANSWER=""
  ANSWER=$(printf '%s' "$ANSWER" | tr -d '\r')   # Git Bash / Windows terminals
  [ "$ANSWER" = "ERASE" ] || { say "Cancelled. Nothing was written."; exit 2; }
  $ESPTOOL --chip esp32s3 --port "$PORT" erase-flash || fail "erase failed. Check the cable and port, then retry."
  $ESPTOOL --chip esp32s3 --port "$PORT" --baud 460800 write-flash $WRITE_ARGS \
    || fail "write failed. Run the same command again; the board's ROM bootloader cannot be damaged."
  say ""
  say "Done. Power the board, join the Wi-Fi ESP32-Tailnet-Setup-XXXX and follow the setup page (or open http://192.168.4.1/)."
else
  $ESPTOOL --chip esp32s3 --port "$PORT" --baud 460800 write-flash $WRITE_ARGS \
    || fail "update failed. Do not erase settings to fix a cable or port problem. Check the cable, then retry."
  say ""
  say "Done. The board restarts with your settings."
fi
