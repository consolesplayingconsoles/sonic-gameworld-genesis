#!/usr/bin/env bash
# Convert Sonic the Hedgehog's Gameworld (Sega Pico) into a Mega Drive ROM.
# Patches the page sensor, the console string and the header checksum; input
# and sound are deliberately untouched (see FINDINGS.md).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

[ -f "$HERE/.env" ] || { echo "[ERROR] no .env: copy .env.sample to .env and fill PICO_ROM"; exit 1; }
set -a; . "$HERE/.env"; set +a

: "${PICO_ROM:?[ERROR] PICO_ROM is empty: point it at the Pico dump to patch}"
[ -f "$PICO_ROM" ] || { echo "[ERROR] PICO_ROM does not exist: $PICO_ROM"; exit 1; }
PAGE="${PAGE:-0}"

BUILD="$HERE/build"; mkdir -p "$BUILD" "$HERE/rom"

# The dumps are distributed zipped; take the single entry out so the patcher
# and the IPS both work off the same raw bytes.
SRC="$PICO_ROM"
case "$PICO_ROM" in
  *.zip)
    rm -rf "$BUILD/src"; mkdir -p "$BUILD/src"
    unzip -o -q "$PICO_ROM" -d "$BUILD/src"
    SRC="$(find "$BUILD/src" -type f | head -1)"
    [ -n "$SRC" ] || { echo "[ERROR] $PICO_ROM is empty"; exit 1; }
    ;;
esac

python3 "$HERE/patch.py" "$SRC" "$BUILD/patched.bin" --page "$PAGE"

# The ROM is named by the project naming convention (pluto/api/rom_name.py), the same
# name it is published and sent under, so it is never renamed on the way.
ROOT="$HERE"; until [ -f "$ROOT/pluto/api/rom_name.py" ]; do ROOT="$(dirname "$ROOT")"; [ "$ROOT" = / ] && { echo "[ERROR] pluto/api/rom_name.py not found above $HERE"; exit 1; }; done
ROM="$HERE/rom/$(python3 "$ROOT/pluto/api/rom_name.py" "$HERE" .bin)"
cp "$BUILD/patched.bin" "$ROM"

# The release artifact is the patch, next to the ROM but shipped on its own.
python3 "$HERE/ips.py" "$SRC" "$ROM" "${ROM%.bin}.ips"

echo "built: $ROM ($(wc -c < "$ROM") bytes), page $PAGE"
echo "##OUTPUT:$ROM"
