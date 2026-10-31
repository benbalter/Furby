#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
#
# Build build/voice_mimic/ref.wav (about 11 s): four speech-only clips from your stock DLC,
# silence trimmed, joined with short gaps, for Chatterbox to mimic. Tracks 9, 52, 64 and 88
# are plain speech, no singing or effects, which Whisper confirmed. The clips are Hasbro's
# recordings: keep ref.wav in build/ and don't share it.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
V=build/voice
OUT=build/voice_mimic
[ -f "$V/track_009.wav" ] || uv run audioutils/extract_voice.py   # decodes your stock DLC's clips (see stock_dlc.py)
mkdir -p "$OUT"
TRIM="silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.02,areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.02,areverse"
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
ffmpeg -y -loglevel error -f lavfi -i anullsrc=r=16000:cl=mono -t 0.25 "$tmp/gap.wav"
for t in 009 052 064 088; do
  ffmpeg -y -loglevel error -i "$V/track_$t.wav" -af "$TRIM" -ar 16000 -ac 1 "$tmp/seg_$t.wav"
  printf "file '%s'\nfile '%s'\n" "$tmp/seg_$t.wav" "$tmp/gap.wav" >> "$tmp/list.txt"
done
# -2 dB keeps peaks under full scale after Chatterbox resamples to 24 kHz
ffmpeg -y -loglevel error -f concat -safe 0 -i "$tmp/list.txt" -af volume=-2dB -c:a pcm_s16le "$OUT/ref.wav"
echo "$OUT/ref.wav: $(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT/ref.wav") s"
