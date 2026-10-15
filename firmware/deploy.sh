#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
#
# Copy the Halloween show to an ESP32 running MicroPython, over USB.
#
#   firmware/deploy.sh            # first board found
#   PORT=/dev/cu.usbmodem1101 firmware/deploy.sh
#
# Installs aioble (pinned), compiles the show engine to .mpy (faster to load,
# less RAM), copies it with main.py and show.json, and restarts the board.
# Needs uv (https://docs.astral.sh/uv/), which runs mpremote and mpy-cross
# without installing them. If the show is already running on the board, the
# watchdog reboots it about two minutes after mpremote interrupts it; this
# takes well under that. Or hold the button while plugging in (safe boot).
set -euo pipefail
cd "$(dirname "$0")/.."

AIOBLE=(aioble-core@0.4.0 aioble-central@0.3.0 aioble-client@0.3.0)
SHOW=build/halloween/show.json

if [[ ! -f $SHOW ]]; then
  echo "No $SHOW yet. Run: python halloween.py" >&2
  exit 1
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
uvx --from mpy-cross mpy-cross -o "$work/furbyshow.mpy" furbyshow.py

mpremote=(uvx mpremote connect "${PORT:-auto}")
"${mpremote[@]}" mip install "${AIOBLE[@]}"
"${mpremote[@]}" cp "$work/furbyshow.mpy" firmware/main.py "$SHOW" : + reset
echo "Deployed. The show starts in a few seconds; watch it with: uvx mpremote connect ${PORT:-auto} repl"
