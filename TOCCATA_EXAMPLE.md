# Toccata in D Minor: an example

This walks through making a Furby Connect play the opening of Bach's Toccata and Fugue in D Minor (BWV 565), which is public domain. The repo includes the first 20 seconds as [`audio/new_audio/toccata_in_d_minor_16khz.wav`](audio/new_audio/toccata_in_d_minor_16khz.wav) (16 kHz mono), and the Halloween show already plays 5 seconds of it ([`halloween/show.toml`](halloween/show.toml)'s `toccata` clip).

## Quick start

From the repo's folder, with [uv](https://docs.astral.sh/uv/) and ffmpeg installed:

```bash
uv run audioutils/encode_a18.py audio/new_audio/toccata_in_d_minor_16khz.wav build/toccata.a18 --duration 10
uv run spooky_eyes.py --song build/toccata.a18   # build/spooky_demon.dlc, about 175 KB
cp build/spooky_demon.dlc build/toccata.dlc      # flash.py needs a name of 8 letters or fewer
uv run flash.py build/toccata.dlc                # with only this Furby awake
uv run porch.py --action 75,0,4,4                # play it, with demon eyes
```

Audio costs about 2 KB a second, and a DLC has to stay under about 350 KB to upload, so 10 seconds (20 KB) leaves plenty of room. Keep generated files in `build/`, which git ignores: CI fails if a new `.a18`, `.wav` or `.dlc` is committed.

## Doing it by hand with the `dlc` class

[`demo_toccata.py`](demo_toccata.py) shows each step with the `dlc` class from [`furby.py`](furby.py).

### 1. Load a DLC

```python
from furby import dlc
D = dlc("./dlc/dlc2/tu003410.dlc")
```

### 2. Replace the audio for some actions

An action code is a 4-tuple. Input 75 is the app's "video" actions: they play only when a phone or computer triggers them over Bluetooth, never from the Furby's own reactions to petting or noise, which come from its built-in memory whatever DLC is active.

```python
toccata = "./build/toccata.a18"
D.replace_audio((75, 0, 0, 0), [toccata])
D.replace_audio((75, 0, 0, 1), [toccata])
D.replace_audio((75, 0, 0, 3), [toccata])
```

Pass several files to play them in turn, as `create_multi_track_toccata()` does with an intro, main theme and climax:

```python
D.replace_audio((75, 0, 0, 0), ["./build/toccata_intro.a18", "./build/toccata_main.a18", "./build/toccata_climax.a18"])
```

### 3. Build it

```python
D.build("./build/toccata.dlc")
```

This DLC keeps all of the stock audio, so it comes out at about 1.2 MB, far over the roughly 350 KB that uploads without timing out. `D.dlc_sections["AMF"].minify_audio()` cuts every stock track to 128 bytes, but `make_toccata_furby(minify=True)` still comes out a little over the limit. To get something you can flash, use `spooky_eyes.py` as in the quick start: it starts from a smaller base, the same build as Context's `hacked.dlc`, and stops with an error for anything too big to upload.

### 4. Flash it and play it

```bash
uv run flash.py build/toccata.dlc
uv run porch.py --action 75,0,0,0
```

See [Flashing a DLC](README.md#flashing-a-dlc) for the browser route and options.

## Picking a snippet

`encode_a18.py` takes `--start` and `--duration`, so you can cut any recording without editing it first, as long as ffmpeg reads it:

```bash
uv run audioutils/encode_a18.py my_toccata.mp3 build/toccata_climax.a18 --start 8:00 --duration 10
```

Rough spots in a full recording: the opening at 0:00–0:15, the flowing toccata at 0:15–0:45, and the thunderous ending in the last 30 seconds. Timings vary by performer.

## Troubleshooting

- **`the Furby keeps 8.3 names, so use 8 letters or fewer`**: rename the DLC, as in the quick start.
- **`uploads time out above about 350 KB`, or an upload times out**: use a shorter snippet, or build with `spooky_eyes.py` rather than the full stock DLC.
- **The Furby doesn't play it**: trigger the action over Bluetooth (`porch.py --action`, or FurBLE's custom action box). Petting, tickling and noises play the Furby's built-in reactions, not the DLC's.
- **It sounds distorted**: `encode_a18.py` already resamples to 16 kHz mono. Try a quieter source, since the Furby's speaker clips easily.

## Related files

- [`demo_toccata.py`](demo_toccata.py): the `dlc` class version
- [`audio/new_audio/README.md`](audio/new_audio/README.md): the bundled audio files
- [`audioutils/README.md`](audioutils/README.md): the conversion tools
- [`spooky_eyes.py`](spooky_eyes.py): builds a DLC with custom eyes and a song
