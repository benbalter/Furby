#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
#
# The pipeline: sample clips -> candidate refs -> best-of-N Chatterbox takes -> the most
# Furby-like take per line that Whisper hears right -> up a semitone -> build/cloned/.
#   ./run2.sh            # full run (resumable: existing takes and scores are reused)
#   ./run2.sh --regrid   # also redo the Furby-ize settings grid (else reuse furbyize.json)
#   ./run2.sh --fresh    # delete takes2/ and work2/ first and regenerate everything
# Outputs: build/cloned/<name>.wav, build/cloned/preview/<name>.wav, build/cloned/index.csv,
#          build/cloned/ab_compare.wav + .txt, build/voice_mimic/work2/report.txt.
# Everything it makes is built from Hasbro's recordings: keep it in build/ and don't publish it.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
DATA="$ROOT/build/voice_mimic"
cd "$HERE"
SCORE=(uv run --quiet --no-project --python 3.11 --with resemblyzer --with praat-parselmouth
       --with mlx-whisper --with a1800-codec --with 'setuptools<80' python)
TTS=(uv run --quiet --no-project --python 3.11 --with chatterbox-tts --with 'setuptools<80' python)
quiet() { grep -vE 'Warning|warn|deprecat|Sampling|LoRACompatible|sdpa|self.gen|outside normalized|^$' || true; }

if [[ " $* " == *" --fresh "* ]]; then rm -rf "$DATA/takes2" "$DATA/work2"; fi
mkdir -p "$DATA"
if [ -d "$ROOT/build/cloned" ] && [ ! -d "$ROOT/build/cloned_v1" ]; then
  cp -R "$ROOT/build/cloned" "$ROOT/build/cloned_v1"   # keep the previous lines for A/B; never overwritten
fi
[ -f "$DATA/ref.wav" ] || ./make_ref.sh                                        # the first ref, a baseline candidate
[ -f "$DATA/voice_transcripts.csv" ] || "${SCORE[@]}" transcribe.py           # Whisper every stock clip
[ -f "$DATA/clips.csv" ] || "${SCORE[@]}" analyze.py                           # pitch + similarity ranking
uv run --quiet --no-project --python 3.11 python refs.py                                                             # candidate refs
"${TTS[@]}" gen2.py --turbo 2>&1 | quiet                                       # about 4 s a take on Apple silicon
"${SCORE[@]}" best.py "$@" 2>&1 | grep -vE 'Fetching|Warn'
