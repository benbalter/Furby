#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
#
# Copy the show's log off an ESP32, over USB, e.g. the morning after a night on
# battery.
#
#   firmware/getlog.sh            # first board found
#   PORT=/dev/cu.usbmodem1101 firmware/getlog.sh
#
# Saves log.txt (and log.txt.old, if the log has rolled over) to
# build/board-log/, named by the time they were copied so a later copy doesn't
# overwrite them, and prints the end of the log. Copying stops the show, so the
# board restarts afterwards; power the Furbies up one at a time again, as its
# LED says.
set -euo pipefail
cd "$(dirname "$0")/.."

out=build/board-log
stamp=$(date +%Y%m%d-%H%M%S)
mkdir -p "$out"

mpremote=(uvx mpremote connect "${PORT:-auto}")
"${mpremote[@]}" cp :log.txt "$out/log-$stamp.txt"
# Only there once the log has passed LOG_MAX (firmware/main.py)
if "${mpremote[@]}" cp :log.txt.old "$out/log-$stamp.old.txt" 2>/dev/null; then
  echo "Also saved the older log: $out/log-$stamp.old.txt"
fi
"${mpremote[@]}" reset

echo
tail -n 20 "$out/log-$stamp.txt"
echo
echo "Saved $out/log-$stamp.txt. The board is restarting the show: power up the Furbies one at a time."
