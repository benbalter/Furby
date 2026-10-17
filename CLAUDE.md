# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

A fork of [ctxis/Furby](https://github.com/ctxis/Furby) (Python tools for Furby Connect DLC files) that adds custom eyes, DLL-free audio tools, and a two-Furby Halloween show run from a laptop or an ESP32. The repo is **public**.

## Commands

Python 3.11+ (`halloween.py` uses `tomllib`). Dependencies are in [pyproject.toml](pyproject.toml) (Pillow, a1800-codec, bleak; ruff in the `dev` group) and locked in `uv.lock`, so `uv run <script>.py` just works; ffmpeg for audio conversion.

```sh
# All tests (CI runs exactly this on 3.11–3.13)
uv run python -m unittest test_furby -v
# One class or test
uv run python -m unittest test_furby.TestHalloween.test_build_show
# Lint and format (config in pyproject.toml)
uv run ruff check . && uv run ruff format --check .
```

- The MicroPython tests (`test_show_runs_on_micropython`, `test_compiles_for_micropython`) skip unless `micropython` is on PATH (`brew install micropython`). CI runs them in a macOS job, and also compiles the board files with `mpy-cross`.
- Tests depend on the stock DLC `dlc/dlc2/tu003410.dlc` and the `.a18` files in `audio/new_audio/`.
- `TestRealShow` builds the real [halloween/show.toml](halloween/show.toml) with placeholder tones ([tools/ci_show.py](tools/ci_show.py)) and fails on any line [emulate.py](emulate.py) finds silent or skipped. CI's `show` job runs the same build, prints emulate's report, and runs [eyecheck.py](eyecheck.py) as a warning only, until its rules match what real Furbies show. To run it locally: `uv run tools/ci_show.py && uv run emulate.py build/ci-show/show.json`.
- `TestScripts` runs `--help` on every argparse script, so a broken import fails CI even in scripts no test imports.
- CI's lint job also runs actionlint and an offline [lychee](https://github.com/lycheeverse/lychee) check of the Markdown's relative links and anchors. [Dependabot](.github/dependabot.yml) sends one grouped PR a week at most for action updates; actions use floating major tags, never SHA pins.

Halloween show pipeline:

```sh
uv run halloween.py [--skip-missing]   # halloween/show.toml → build/halloween/{pink,blue}.dlc + show.json
uv run porch.py --list | --clip pink.cackle | --scene 0   # run/test the show from a computer
uv run porch.py --rehearse [--scene N]  # play scenes on this computer's speakers; no Furbies needed
uv run preview.py [--open]               # build/preview/index.html: both Furbies in a browser, sound/eyes/lights/timing (never publish: Hasbro-derived audio)
uv run flash.py build/halloween/pink.dlc  # flash a DLC from this computer (one Furby awake, no reset needed)
uv run deploy.py [--only pink] [--no-build] [--yes] [--esp32]  # guided: build, then wake/confirm/flash each Furby in turn
uv run porch.py --check                 # play every clip once per Furby; played/skipped/no reply, sequence timings, checksums
firmware/deploy.sh                      # copy the show to an ESP32 running MicroPython (uses uvx mpremote/mpy-cross)
uv run spooky_eyes.py --theme pumpkin   # standalone eyes DLC
uv run spooky_eyes.py --preview         # build/eyes/<theme>.gif and .png for every eye theme
uv run spooky_eyes.py --probe           # numbered test animations that answer the open eye questions
uv run doctor.py [--furbies]           # check tools, Bluetooth, clips, built DLCs (and Furbies), with a fix per problem
uv run probe.py build slots            # each scene slot says its number → build/probe/slots.dlc + slots.json
uv run probe.py build motions e000-e017  # slot N says "move N" and runs only motor word N (24 slots per DLC)
uv run probe.py run slots [--reverse] [--times N] [--only 2,5]  # time each slot 20:0c → 20:0e; saves build/probe/<name>-<time>.json
uv run eyecheck.py build/halloween/*.dlc [--gif DIR] [--stale-cel prev.dlc]  # compose eyes as the Furby does; fail what won't show
uv run emulate.py [--worst] [--scene N] [--durations measured.json]  # run show.json on virtual Furbies: silent/skipped lines, pacing
```

## Architecture

**DLC model ([furby.py](furby.py)).** `dlc` parses a DLC into sections (`HEADER`, `PAL`, `SPR`, `CEL`, `XLS`, `AMF`, `APL`, `LPS`, `SEQ`, `MTR`), lets you edit them, and `build()`s them back. To find what an action plays, follow the chain: action code `(input, index, subindex, specific)` → `XLS.action_tree[...]["seq"]` → `SEQ.sequences[seq]` (entries `0x8xxx`/`0xaxxx` are eye animations; `[1]` minus `playlist_offset` is the APL playlist) → `APL.playlists` → `AMF.tracks` (A1800 audio). `spooky_eyes._actions()` and `_tracks()` wrap that lookup. Palette colours are ARGB1555 (verified).

**Eyes.** An eye frame is 128×128 pixels in 64 colours, stored as four 64×64 cels (about 3 KB each). SPR holds playlists of frames, 8 to an animation (right and left eye for each of 4 layers), so playlists 8–15 are the DLC's animation 1, eye word `0x8401`. [demo.py](demo.py) `install_eyes()` blanks its lower layers and puts custom frames on the top one (playlists 12/13); that layout has run on a Furby. `spooky_eyes.install_animations()` keeps it for animation 1 and appends a copy per extra theme (`0x8402`, …). Two things there are **inferred, not seen on a Furby**: that `0x84nn` picks DLC animation nn (from [furby-connect-eyes-extract](https://github.com/lib-fluff-so/furby-connect-eyes-extract)'s rendering of the firmware's files, which hold 156 animations; stock sequences only use `0x8003`–`0x8096`), and which field picks a frame's palette (the playlist's layer field ÷ 64, or the frame's palette word). Every frame therefore shares one palette, written to slots 4 and 5. Probes on hardware (`spooky_eyes.PROBE`, built by `--probe` into `build/eyes_probe2/`, digits on black): `eyesc` (`demo.install_eyes()`), `eyesf` (a cel repeated within a frame) showed clean digits; `eyesb`, `eyese` and `eyesh`, whose two eyes shared cels, came out garbled. Those three were also the only ones with under 16 cels, and Hasbro's own DLC shares cels between its eyes, so the cause is **inferred**: `eyesk`/`eyesl` split it. Until then each eye gets its own cels (`install_animations()`), and [eyecheck.py](eyecheck.py) fails both. `eyesi` (fixed pipeline, one animation) and `eyesj` (three animations) are untested. show.toml defaults to `one_eye_animation = true` until `eyesj` passes.

**Eye check ([eyecheck.py](eyecheck.py)).** A frame's per-quarter "palette word" (`0x10f2`, `0x14f2`, `0x18f2`) is a SunPlus PPU sprite attribute: bit 2 is H-flip, the low byte otherwise means 64×64 at 6 bpp, and bits 8–11 pick a hardware palette slot. `compose()` draws all four layers with index 0 see-through under both palette rules; `check()` fails anything that doesn't match `intended()` under either, or leaves the proven envelope (`PROVEN_*`). What probe.dlc (32 playlists) showed matches its frames and palette over an **earlier DLC's cels** (`--stale-cel`), so its CEL probably never loaded; that's inferred from a description of the photos, and whether playlist count, SPR size or file size triggers it is open. Until a probe says otherwise, keep DLCs to one animation of 38 frames.

**Hardware facts that shape the design** (from testing on a real Furby):
- A DLC only changes what plays when an action is **triggered over Bluetooth**. The Furby's own reactions (noise, petting, input 20 and so on) come from built-in memory, whatever DLC is active. So the show needs a controller that sends the triggers.
- Custom clips go on input-75 ("app video") actions. `spooky_eyes.scene_slots()` returns the 75 actions whose track and sequence no other 75 action shares, so each clip plays only where intended.
- A triggered action's sequence keeps the Furby busy until its body movement and eye delays finish, which is often long after its clip ends. Trigger it again before then and it replies `20:07` (speech playing) and runs the action **without audio**; a normal start replies `20:0c`, and the end sends `20:0e`. `Furby.play()` retries on `20:07`. Slots whose motor word is `0xc4xx` (the DLC's own routines) run 10–21 s, so `halloween.quick_slots()` skips them; the built-in `0xe0xx` movements take about 1–9 s and vary from run to run. Run alone (one motor word per sequence, one eye animation, no delays), every built-in motor word from `e000` to `e028` ran, in 0.8–10.3 s, so there are probably about 41 built-in movements. Re-measure with `probe.py` rather than one-off scripts.
- Two Furby Connects near each other sing together, and while they do neither one advertises, so nothing can find them (they seem to pair; the F2F characteristics suggest so, unverified). Power them up one at a time and let the show connect to each one first. The show guides this: `Show.waiting_for()` is the next Furby in show.json's order, `guide()` logs the instruction on each change (porch.py prints it) and the board's LED blinks N times for Furby N (`led_pattern()`). MicroPython's dicts lose key order, so the board passes `plan_order()` (read from show.json's text) as `order`.
- Uploads time out above about 350 KB (`MAX_UPLOAD`). Audio costs about 2 KB per second, and each slot stores its own copy of a clip.
- The Furby stores DLCs under 8.3 names (`____PINK.DLC`). The show tells the Furbies apart by their active DLC's name, and checks its Adler-32 checksum against `show.json`.

**Show pipeline.** [halloween/show.toml](halloween/show.toml) is the single source of truth for clips and scenes, including each voice line's words (the comment beside it).
- A fresh clone has only the Toccata clip, so `halloween.py --skip-missing` builds **0 scenes** until `build/cloned/` has the voice lines (8 scenes with those, 12 with `freesound_fetch.py`'s effects, 13 with Ghostbusters). The original lines are AI voice clones of the stock DLC's audio, so they're Hasbro-derived and can't ship; [README.md](README.md) "Set up the Halloween show" tells people to record their own or use macOS `say -o … --data-format=LEI16@16000`. That section is written for a non-technical reader with two identical Furbies; keep it step-by-step and keep its numbers in sync with the build.
- Clips are paths or tables (`path`, `start`, `seconds`, `before`, `optional`, `eyes`, `light`); see `halloween.clip_spec()`. Each clip name is stored once per DLC however many scenes use it, so repeating a line costs nothing, but an unused clip still takes up room. A scene step can join clips with `+` to play them at once (`furbyshow.step_parts()`), so anything that reads steps must split on `+`.
- Scenes marked `greeting = true` go to `plan["greetings"]` as well as `plan["scenes"]`: `trigger()` (the button, or Enter in `porch.py`) plays a greeting, and the timer plays the rest. The PIR sensor (when `PIR_PIN` is set) calls `trigger(sensor=True)`, which `[show] cooldown` ignores for that long after a greeting; button presses never wait.
- **Antenna lights.** `halloween.clip_light()` resolves each clip's light, as `{"effect", "color"}`, from `THEME_LIGHTS[eyes]`, then the Furby's `light`, then the clip's `light`; `antenna` is only the fallback colour. `halloween.envelope()` decodes the encoded `.a18` (stripping A1800.DLL's 0x30-byte `GENERALPLUS` header) into one loudness digit per 100 ms (`"0379…"`, 0 = 24 dB below the clip's peak), stored as `envelope` in show.json. `furbyshow.light_rgb()` holds the effects, which are pure functions of time, level and a seed, with deterministic noise. `Show.light_line()` runs as a task alongside each line, started after that Furby's `play()` returns, waits on an Event so `play_step`'s `finally` can stop it at once, and goes back to rest (off, or the `idle` glow during a scene). `Furby.glow()` skips unchanged colours. The light loop uses real time, not the injectable `self.sleep`, so tests with a fake sleep see only the first frame and the final off. A show.json without `light` (built before this) falls back to a steady `antenna` colour. Unverified on hardware: smooth dimming, the safe update rate, and whether a triggered sequence drives the antenna itself.
- [halloween.py](halloween.py) keeps each clip on the same quick slot from build to build via [halloween/slots.lock.json](halloween/slots.lock.json) (committed: clip names and action codes only), in `assign_slots()`. A clip keeps its slot while `show.toml` names it, even when its file is missing; a new clip takes the first free slot in `quick_slots()` order; a removed one leaves a `retired` entry so it gets its slot back if re-added. `--reshuffle` restarts the lock in sorted clip-name order, and a missing lock is seeded from the previous `build/halloween/show.json`. `build_show(lock_path=None)` (what the tests use) skips the lock, so tests never touch the committed one.
- After a build, `halloween.py` compares each DLC's Adler-32 with the previous `show.json` and says which Furbies to reflash (`changes_message()`), and prints a size budget per DLC (`dlc_budget()`, `budget_report()`): clips by AMF track bytes, eyes as CEL+SPR+PAL with a per-theme split of the cels only that theme uses, and the rest as base. The per-theme split reads `spooky_eyes`' playlist layout (flame layer at `8 + n * channels_per_anim + 4`) and falls back to a total if that changes.
- [furbyshow.py](furbyshow.py) is the transport-agnostic engine: the Furby protocol (FurBLE's GeneralPlus commands: `0x13` trigger, `0x20 0x06` keepalive, `0x72`/`0x73` DLC info), scene picking, reconnects, and the heartbeat and `playing` state.
- Each transport subclasses `furbyshow.Furby` (`connected`, `_write`, `disconnect`, feeding notifications to `on_response`) and supplies `find()`: [porch.py](porch.py) uses bleak, and [firmware/main.py](firmware/main.py) uses aioble with a watchdog, safe boot (button held at power-up), the status LED and the button.

**`furbyshow.py` and `firmware/` must run on MicroPython:**
- no `typing`, `dataclasses` or `time.monotonic` (use the `ticks_ms`/`ticks_diff` helpers);
- catch `asyncio.TimeoutError` (ruff's UP041 is disabled for these files);
- on the board, the wake event is an `asyncio.ThreadSafeFlag` so that a pin IRQ can set it.

[emulate.py](emulate.py) is a virtual Furby (`FurbyModel`) behind both a `furbyshow.Furby` subclass and a bleak-client stand-in for `flash.Flasher`, on a `VirtualTimeLoop` (a selector that jumps the clock to the next timer; `virtual_time()` points `ticks_ms` at it). Sequence length is max(audio, delay words at an assumed 10 ms, movement range); `TestEmulator` checks it flags the pre-925f386 fire-and-forget `play()`.

[test_furby.py](test_furby.py) `TestFirmware` runs `main.py` on CPython against fake `aioble`/`bluetooth`/`machine` modules.

**Audio.**
- [audioutils/encode_a18.py](audioutils/encode_a18.py) encodes with ffmpeg plus a1800-codec. Its `.a18` header is `<IH` (length, bitrate), with the length counting the 2-byte bitrate, the A1800.DLL convention.
- `extract_voice.py` decodes a DLC's clips to WAV.
- `freesound_fetch.py` fetches CC0-only effects. It reads `FREESOUND_API_KEY` from the environment (run it under `op run`).
- The older `convert*.py` scripts need the Windows-only A1800.DLL.

**Flashing.** `uv run flash.py <file>.dlc` (with only that Furby awake, or `--address`) does what [benbalter/furby-web-bluetooth](https://github.com/benbalter/furby-web-bluetooth) "Upload Custom" does, from the terminal: `0x50` announce, 20-byte FileWrite packets at 15 ms with Nordic packet acks (`0x09`) for flow control, then `0x73` checksum check, `0x60` load, `0x61` activate. It deletes the stored DLCs first with `0x74`, which replaced (on a real Furby) the tongue-and-tail reset that FurBLE needs before each upload. The show's DLCs take about 2–3½ minutes. Identical Furbies differ only by active DLC, so flash each with only it awake; flashing both with `pink.dlc` (easy in FurBLE) makes the show log "Two Furbies have pink.dlc" and drop the second. In FurBLE: serve it over http, not `file://`; reset before each upload; `?packetDelay=<ms>` slows it down.

## Conventions

- **Context's original files** keep their own style (tabs, `%` formatting) and are excluded from ruff in [pyproject.toml](pyproject.toml): `furby.py`, `demo*.py`, `minify_dlc.py`, `audioutils/convert*.py`, `extract_audio.py`. Don't reformat them.
- **New files** carry `SPDX-FileCopyrightText: 2026 Ben Balter` / `SPDX-License-Identifier: MIT` headers, with the license text in [LICENSES/MIT.txt](LICENSES/MIT.txt). Context's files have no stated license, so never add MIT headers to them.
- **Generated output goes in `build/`** (gitignored): built DLCs, extracted Furby audio, Freesound clips, and cloned Furby voices.
  - Cloned voices and DLCs built from the stock one are Hasbro-derived, so never commit or publish them.
  - CI's `no-generated-files` job fails on any audio or DLC beyond the four that came with the repo.
