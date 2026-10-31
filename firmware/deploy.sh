#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
#
# Copy the Halloween show to an ESP32 running MicroPython, over USB.
#
#   firmware/deploy.sh            # first board found
#   PORT=/dev/cu.usbmodem1101 firmware/deploy.sh
#
# Installs aioble (pinned), compiles the show engine and the phone remote to
# .mpy (faster to load, less RAM), copies them with main.py and show.json, and
# restarts the board.
# Needs uv (https://docs.astral.sh/uv/), which runs mpremote and mpy-cross
# without installing them. If the show is already running on the board, the
# watchdog reboots it about two minutes after mpremote interrupts it; this
# takes well under that. Or hold the button while plugging in (safe boot).
set -euo pipefail
cd "$(dirname "$0")/.."

# The whole bundle, not aioble-core/-central/-client: the index has two builds
# of aioble-client 0.3.0, and the pinned one brings an older core.mpy that
# breaks central's connect ("function takes 5 positional arguments").
AIOBLE=(aioble@0.6.2)
SHOW=build/halloween/show.json

if [[ ! -f $SHOW ]]; then
  echo "No $SHOW yet. Run: uv run halloween.py" >&2
  exit 1
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
uvx --from mpy-cross mpy-cross -o "$work/furbyshow.mpy" furbyshow.py
uvx --from mpy-cross mpy-cross -o "$work/remote.mpy" firmware/remote.py

mpremote=(uvx mpremote connect "${PORT:-auto}")
"${mpremote[@]}" mip install "${AIOBLE[@]}"
# MicroPython imports a .py ahead of its .mpy, so an old hand copy would hide the new one
for stale in furbyshow.py remote.py; do
  "${mpremote[@]}" rm ":$stale" >/dev/null 2>&1 || true
done
"${mpremote[@]}" cp "$work/furbyshow.mpy" "$work/remote.mpy" firmware/main.py "$SHOW" : + reset
echo "Deployed. The show starts in a few seconds; watch it with: uv run tools/watch_board.py${PORT:+ --port $PORT}"
