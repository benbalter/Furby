# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

A fork of [ctxis/Furby](https://github.com/ctxis/Furby) (Python tools for Furby Connect DLC files) that adds custom eyes, DLL-free audio tools, and a two-Furby Halloween show run from a laptop or an ESP32. The repo is **public**.

## Commands

Python 3.11+ (`halloween.py` uses `tomllib`). Dependencies: [requirements.txt](requirements.txt) (Pillow, a1800-codec); ffmpeg for audio conversion.

```sh
# All tests (CI runs exactly this on 3.11–3.13)
uv run --no-project --python 3.12 --with pillow --with a1800-codec python -m unittest test_furby -v
# One class or test
uv run --no-project --python 3.12 --with pillow --with a1800-codec python -m unittest test_furby.TestHalloween.test_build_show
# Lint and format (config in pyproject.toml)
uvx ruff check . && uvx ruff format --check .
```

- The MicroPython tests (`test_show_runs_on_micropython`, `test_compiles_for_micropython`) skip unless `micropython` is on PATH (`brew install micropython`). CI runs them in a macOS job, and also compiles the board files with `mpy-cross`.
- Tests depend on the stock DLC `dlc/dlc2/tu003410.dlc` and the `.a18` files in `audio/new_audio/`.

Halloween show pipeline:

```sh
python halloween.py [--skip-missing]   # halloween/show.toml → build/halloween/{pink,blue}.dlc + show.json
python porch.py --list | --clip pink.cackle | --scene 0   # run/test the show from a computer (needs bleak)
firmware/deploy.sh                      # copy the show to an ESP32 running MicroPython (uses uvx mpremote/mpy-cross)
python spooky_eyes.py --theme pumpkin   # standalone eyes DLC
```

## Architecture

**DLC model ([furby.py](furby.py)).** `dlc` parses a DLC into sections (`HEADER`, `PAL`, `SPR`, `CEL`, `XLS`, `AMF`, `APL`, `LPS`, `SEQ`, `MTR`), lets you edit them, and `build()`s them back. To find what an action plays, follow the chain: action code `(input, index, subindex, specific)` → `XLS.action_tree[...]["seq"]` → `SEQ.sequences[seq]` (entries `0x8xxx`/`0xaxxx` are eye animations; `[1]` minus `playlist_offset` is the APL playlist) → `APL.playlists` → `AMF.tracks` (A1800 audio). `spooky_eyes._actions()` and `_tracks()` wrap that lookup. Eyes are 128×128, 64-colour, 2-frame GIFs, split into quarter cels; [demo.py](demo.py) `install_eyes()` puts them on palettes 4/5 and points sequences at `0x8401`. Palette colours are ARGB1555 (verified).

**Hardware facts that shape the design** (from testing on a real Furby):
- A DLC only changes what plays when an action is **triggered over Bluetooth**. The Furby's own reactions (noise, petting, input 20 and so on) come from built-in memory, whatever DLC is active. So the show needs a controller that sends the triggers.
- Custom clips go on input-75 ("app video") actions. `spooky_eyes.scene_slots()` returns the 75 actions whose track and sequence no other 75 action shares, so each clip plays only where intended.
- Uploads time out above about 350 KB (`MAX_UPLOAD`). Audio costs about 2 KB per second, and each slot stores its own copy of a clip.
- The Furby stores DLCs under 8.3 names (`____PINK.DLC`). The show tells the Furbies apart by their active DLC's name, and checks its Adler-32 checksum against `show.json`.

**Show pipeline.** [halloween/show.toml](halloween/show.toml) is the single source of truth for clips and scenes.
- [halloween.py](halloween.py) assigns clips to scene slots **in sorted clip-name order**. Adding or renaming a clip can therefore move other clips to different actions, so after any change, rebuild, reflash both Furbies and redeploy `show.json` together.
- [furbyshow.py](furbyshow.py) is the transport-agnostic engine: the Furby protocol (FurBLE's GeneralPlus commands: `0x13` trigger, `0x20 0x06` keepalive, `0x72`/`0x73` DLC info), scene picking, reconnects, and the heartbeat and `playing` state.
- Each transport subclasses `furbyshow.Furby` (`connected`, `_write`, `disconnect`, feeding notifications to `on_response`) and supplies `find()`: [porch.py](porch.py) uses bleak, and [firmware/main.py](firmware/main.py) uses aioble with a watchdog, safe boot (button held at power-up), the status LED and the button.

**`furbyshow.py` and `firmware/` must run on MicroPython:**
- no `typing`, `dataclasses` or `time.monotonic` (use the `ticks_ms`/`ticks_diff` helpers);
- catch `asyncio.TimeoutError` (ruff's UP041 is disabled for these files);
- on the board, the wake event is an `asyncio.ThreadSafeFlag` so that a pin IRQ can set it.

[test_furby.py](test_furby.py) `TestFirmware` runs `main.py` on CPython against fake `aioble`/`bluetooth`/`machine` modules.

**Audio.**
- [audioutils/encode_a18.py](audioutils/encode_a18.py) encodes with ffmpeg plus a1800-codec. Its `.a18` header is `<IH` (length, bitrate), with the length counting the 2-byte bitrate, the A1800.DLL convention.
- `extract_voice.py` decodes a DLC's clips to WAV.
- `freesound_fetch.py` fetches CC0-only effects. It reads `FREESOUND_API_KEY` from the environment (run it under `op run`).
- The older `convert*.py` scripts need the Windows-only A1800.DLL.

**Flashing** uses [benbalter/furby-web-bluetooth](https://github.com/benbalter/furby-web-bluetooth) "Upload Custom":
- serve it over http, not `file://`;
- reset the Furby before each upload, one upload per reset;
- `?packetDelay=<ms>` slows the upload if the Furby times out.

## Conventions

- **Context's original files** keep their own style (tabs, `%` formatting) and are excluded from ruff in [pyproject.toml](pyproject.toml): `furby.py`, `demo*.py`, `minify_dlc.py`, `audioutils/convert*.py`, `extract_audio.py`. Don't reformat them.
- **New files** carry `SPDX-FileCopyrightText: 2026 Ben Balter` / `SPDX-License-Identifier: MIT` headers, with the license text in [LICENSES/MIT.txt](LICENSES/MIT.txt). Context's files have no stated license, so never add MIT headers to them.
- **Generated output goes in `build/`** (gitignored): built DLCs, extracted Furby audio, Freesound clips, and cloned Furby voices.
  - Cloned voices and DLCs built from the stock one are Hasbro-derived, so never commit or publish them.
  - CI's `no-generated-files` job fails on any audio or DLC beyond the four that came with the repo.
