# Furby
## Python tools for handling Furby Connect DLC files

<p align="center">
	<img src="images/gifs/gif-full-padding-100.gif">
</p>

**Disclaimer: This script is pretty alpha; use at your own risk. Bad DLCs can make your Furby Connect very unhappy.**

### The original blog post can be found [here](https://www.contextis.com/blog/dont-feed-them-after-midnight-reverse-engineering-the-furby-connect)

## What this fork adds

On top of [Context's original tools](https://github.com/ctxis/Furby), this fork adds:

- **[A two-Furby Halloween show](#example-a-two-furby-halloween-show):** an evil Furby and a friendly one trade lines in short scenes, run by a hidden ESP32 or a laptop.
- **[Custom eyes](#example-spooky-halloween-eyes):** demon and jack-o'-lantern eyes, drawn in code.
- **[Audio tools that need no Windows DLL](#audio-conversion):** convert any audio to the Furby's `.a18` format, unpack a DLC's clips to WAV, and fetch public-domain sound effects.
- **[Notes on flashing your own DLC](#flashing-a-dlc).**

## Requirements

This project requires Python 3.11 or later and uses [uv](https://docs.astral.sh/uv/), which installs the dependencies listed in [`pyproject.toml`](pyproject.toml) the first time you run a script:

```bash
uv run halloween.py
```

The examples below say `python script.py`; run them as `uv run script.py`, or run `uv sync` once and activate `.venv`.

## Testing

Run the test suite to verify the installation:

```bash
python -m unittest test_furby -v
```

The test suite includes:
- DLC file loading and parsing tests
- DLC file building and roundtrip tests
- Python 3 compatibility tests (bytes handling, integer division)
- Section access and manipulation tests
- Error handling tests
- Custom eyes, the Halloween show build, and the show engine and firmware (against stand-ins for the ESP32's Bluetooth and pins)

With [MicroPython](https://micropython.org)'s Unix port installed (`brew install micropython`), the show engine is also tested under MicroPython, as it runs on the board. Lint with [ruff](https://docs.astral.sh/ruff/): `ruff check . && ruff format --check .`


## DLC Class

This class is a wrapper around the syntax used by Furby Connect DLC files. To use it, add the line `from furby import dlc` to the top of your script:

```
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from furby import dlc

def main():
    ...
    <your python here>
    ...
```

The class is most useful when instantiated with an existing Furby Connect DLC file. This can be done by passing the path to such a file when creating an instance of the class:

```
D = dlc("./dlc/dlc1/tu012700.dlc")
```

You can then access each of the various sections contained in the DLC via the `dlc_sections` dictionary:

```
# For example:
cels_section = D.dlc_sections["XLS"]
```

Each of the sections has a "main" storage object, which is either a list or a dictionary as appropriate to the section. Notable main storage objects are as follows:

```
xls_tree             = D.dlc_sections["XLS"].action_tree
colour_palettes      = D.dlc_sections["PAL"].palettes
eye_sprites          = D.dlc_sections["CEL"].cels
animation_scheduling = D.dlc_sections["SPR"].frame_playlists
composited_frames    = D.dlc_sections["SPR"].frames
audio_samples        = D.dlc_sections["AMF"].tracks
audio_playlists      = D.dlc_sections["APL"].playlists
lip_movements        = D.dlc_sections["LPS"].phrases
response_scheduling  = D.dlc_sections["SEQ"].sequences
servo_movements      = D.dlc_sections["MTR"].animations
```

For more information on what each section does and how they relate to one another, [check out our writeup](https://www.contextis.com/blog/dont-feed-them-after-midnight-reverse-engineering-the-furby-connect), which covers it in a fair amount of detail.

<p align="center">
	<img src="images/dlc_hierarchy.png">
</p>

After making modifications to a DLC, you can build it back into a new DLC file by calling the `build()` function, passing the path to the output file:

```
D.build("/tmp/new_dlc.dlc")
```



## Helper Functions

At its most basic level, the DLC class essentially breaks out the various data structures contained within a Furby DLC file into convenient Python data structures which can be handled and manipulated in a much more straightforward way. Modifying a DLC can be achieved by directly changing the content stored in each of these data structures, however we have also included several helper functions to make getting started with common tasks a much less burdensome experience.


### dump_cels(palette_index)
`dump_cels()` can be used to find and extract all the cels contained within a DLC, converting them to non-indexed 32-bit colour RGBA PNGs.

 - `palette_index` is the index of the palette to use for rendering the cels. Although individual cels require different palettes to be rendered correctly, for ease of use, this function only accepts one palette index at a time.

Here's an example:

```
# Dump cels using the 4th palette contained in the DLC.
D.dump_cels(4)

# Different cels use different palettes.
D.dump_cels(5)
D.dump_cels(3)
```

### dump_cels_monochrome()

As above, but attempts to use a monochrome palette if one is available. Useful for getting a quick overview of the cels contained within a DLC.

Here's an example:

```
# Dump cels (monochrome) has no mandatory arguments.
D.dump_cels_monochrome()
```

### replace_audio(action_code, audio_files)
`replace_audio()` can be used to change the audio files played back as part of a response to a particular action code. It works by modifying entries in the AMF section, without changing references in higher sections. As a single AMF entry might be referenced in several places, this function might not always work in exactly the way you'd expect.

 - `action_code` is a 4-tuple containing the action code whose audio response you'd like to change. For example, passing `(75,0,0,0)` will direct the function to work on the audio used as a response to action code 75-0-0-0.
 - `audio_files` is a list of paths to audio files you'd like to insert into the DLC. Note that these need to be a18-encoded.

Here's an example:
```
# Replace audio response to action code 75-0-0-0
D.replace_audio((75,0,0,0), ["my_audio_1.a18", "my_audio_2.a18", "my_audio_3.a18", "my_audio_4.a18"])

# If too many audio files are given, the function will start with the first one, and attempt to insert as many as possible into the specified response.
D.replace_audio((75,0,0,1), ["my_audio_1.a18", "my_audio_2.a18", "my_audio_3.a18", "my_audio_4.a18"])

# If too few audio files are given, the function will loop the last one as many times as it can.
D.replace_audio((75,0,0,1), ["my_audio_1.a18"])

```

### extract_palette()

`D.dlc_sections["PAL"].extract_palette()` will, if passed a .gif with a (single) 64-colour palette, extract that palette and convert it into the same format used as internal storage by the dlc class. This means you can do things like this:

```
# extract the palette from a gif
new_palette = D.dlc_sections["PAL"].extract_palette("./my_gif.gif")

# replace the nth palette in the DLC with this new palette
n = 5
D.dlc_sections["PAL"].palettes[n] = new_palette
```

### quarterize()

`D.dlc_sections["CEL"].quarterize()` will, if passed a 128x128 pixel .gif, convert that gif into a sequence of quarter-frames, in the same form as that used by the dlc class' internal storage. This means that you can do things like this:

```
# quarterize a gif
new_cels = D.dlc_sections["CEL"].quarterize("./my_gif.gif")

# replace the nth cel in the DLC with the mth of our new cels
n = 5
m = 3
D.dlc_sections["CEL"].cels[n] = new_cels[m]

# To view the quarters as they get made, just pass in a palette to render them with.
new_palette = D.dlc_sections["PAL"].extract_palette("./my_gif.gif")
new_cels = D.dlc_sections["CEL"].quarterize("./my_gif.gif", new_palette)
```

### replace_track()

`D.dlc_sections["AMF"].insert_track()` will replace one of the tracks in the AMF section with a track supplied by you. It can be used in the following way:

```
# Replace the nth audio track.
n = 9
D.dlc_sections["AMF"].replace_track(n, "mytrack.a18")
```

### minify_audio()

`D.dlc_sections["AMF"].minify_audio()` will shrink all the audio files in a DLC to a given length. This is useful if you're going to be testing multiple DLC files, as it will drastically shrink the size of your DLCs, resulting in faster uploads. You can use it like so:

```
# Shrink a DLC
D = dlc("./dlc/dlc1/tu012700.dlc")
D.dlc_sections["AMF"].minify_audio()
D.build("/tmp/minified_dlc.dlc")
```

### Minify DLC CLI Tool

A command-line tool is available to minify DLC files without writing Python code:

```bash
# Minify a DLC file (output will be input_minified.dlc)
python minify_dlc.py input.dlc

# Specify output file
python minify_dlc.py input.dlc -o output.dlc

# Customize audio length (default 128 bytes, must be multiple of 8)
python minify_dlc.py input.dlc -l 256
```

The tool will display the original and new file sizes, showing the reduction achieved.

## Audio Conversion

The easiest way, on any OS and with no DLL, is `audioutils/encode_a18.py`. It uses ffmpeg and the open-source [a1800_codec](https://github.com/John-K/a1800_codec), which was reverse engineered from GeneralPlus's A1800.DLL:

```bash
python audioutils/encode_a18.py monster_mash.mp3 monster_mash.a18 --start 0:30 --duration 25
python spooky_eyes.py --song monster_mash.a18
```

Audio costs about 2 KB a second, so keep songs short enough for the DLC to stay under about 350 KB. The older DLL-based tools below still work too.

A GitHub Actions workflow and command-line tool are available to convert audio files (MP3 or WAV) to the a18 format required by Furby Connect.

### Using the CI Workflow

1. Add your audio file (MP3 or WAV) to the repository
2. Go to the "Actions" tab in GitHub
3. Select "Convert Audio to a18" workflow
4. Click "Run workflow" and specify your audio file path
5. Download the converted a18 file from the workflow artifacts

See [.github/workflows/EXAMPLE.md](.github/workflows/EXAMPLE.md) for detailed usage instructions.

### Using the Command-Line Tool

On Windows with the a1800.dll installed:

```bash
# Convert a WAV file
python audioutils/convert_to_a18.py input.wav

# Convert an MP3 file
python audioutils/convert_to_a18.py input.mp3 -o output.a18
```

See [audioutils/README.md](audioutils/README.md) for more information.

## Example: Making Furby Play Toccata in D Minor

Want to give your Furby a dramatic, theatrical personality? Check out `demo_toccata.py` for a complete example of how to make your Furby play Bach's famous Toccata and Fugue in D Minor.

```python
from furby import dlc

# Load an existing DLC
D = dlc("./dlc/dlc2/tu003410.dlc")

# Replace audio for a button press action with Toccata
D.replace_audio((75,0,0,0), ["./audio/new_audio/toccata_in_d_minor.a18"])

# Build the new DLC
D.build("./toccata_furby.dlc")
```

For more details on preparing audio files and advanced multi-track configurations, see the `audio/new_audio/README.md` file and `demo_toccata.py` script.

## Example: Spooky Halloween eyes

`spooky_eyes.py` draws animated eyes with Pillow and builds them into a DLC with custom audio. The themes are `demon` (a pulsing slit eye), `pumpkin` (a flickering jack-o'-lantern), `storm` (a lightning strike), `bloodshot` (a darting, veined eye), `ghost` (a bobbing ghost) and `hypno` (a spinning spiral):

```bash
python spooky_eyes.py                     # demon eyes + Imperial March
python spooky_eyes.py --theme pumpkin --song my_song.a18 --sting my_scream.a18
python spooky_eyes.py --preview           # build/eyes/<theme>.gif for every theme
```

It writes `build/spooky_<theme>.dlc`, plus a preview GIF of the eyes, rendered back out of the DLC, in `build/<theme>/`. The eyes play on actions `75-0-4-4` (with the song), `75-0-3-4` (with the sting) and `75-0-0-3`.

Each theme is three keyframes played across the animation's 38 frames in its own pattern, since every keyframe costs about 12 KB. The Halloween show puts several themes in each Furby's DLC, one animation each, and its clips take turns through them (see `eyes` in [halloween/show.toml](halloween/show.toml)). Only the first animation (`0x8401`) has been seen on a Furby. To check the rest, flash `python spooky_eyes.py --probe` and trigger the actions it lists; if `75-0-3-4` doesn't show green digits, set `one_eye_animation = true` in show.toml.

The build copies Context's `hacked.dlc`, which [FurBLE](https://github.com/pdjstone/furby-web-bluetooth) ships and which is known to flash: every stock audio track is cut to 128 bytes, and apart from audio and eyes the result matches `hacked.dlc` section for section. The script refuses to write anything over about 350 KB, because bigger uploads time out.

A DLC only changes what plays when a phone or computer triggers an action over Bluetooth. The Furby's own reactions to noises, petting and so on come from its built-in memory, so they sound the same with any DLC active. To try the eyes, flash the DLC (below), then trigger `75 0 4 4` from FurBLE's custom action box.

## Flashing a DLC

From a terminal, with just one Furby awake:

```bash
uv run flash.py build/halloween/pink.dlc
```

[`flash.py`](flash.py) deletes the DLCs already on the Furby, uploads the new one (a 200 KB DLC takes a little over 2 minutes), checks the checksum the Furby stores, and activates it. The antenna turns green when it's done, or red with a reason if something failed. There's no need to reset the Furby first. `uv run flash.py --list` shows the Furbies in range and their DLCs, and `--address` picks one when more than one is awake. If uploads time out, try `--packet-delay 30`.

Or from a browser: the hosted FurBLE pages only flash their bundled DLCs, but [benbalter/furby-web-bluetooth](https://github.com/benbalter/furby-web-bluetooth) adds "Upload Custom":

1. Serve it over http (`python3 -m http.server` in its folder) and open `furble.html` in Chrome. Web Bluetooth won't load files from a `file://` page.
2. Reset the Furby: hold it upside down, hold the tongue, and pull the tail until the eyes go dark. Upload one DLC per reset.
3. Click **Connect**, choose your `.dlc`, and click **Upload Custom**. Keep the Furby still and close to the computer; a 200 KB DLC takes about 3 minutes. The antenna turns green when the DLC is active.

The Furby stores DLCs under 8.3-style names (`____PINK.DLC`), so keep file names to 8 letters or fewer. If uploads time out on your computer, add `?packetDelay=30` to the page's address to send more slowly. To remove a DLC, reset the Furby.

## Example: A two-Furby Halloween show

`halloween.py` and `porch.py` turn two Furbies into a call-and-response act: an evil Furby with demon eyes and a friendly one with jack-o'-lantern eyes, trading lines like "No feed after midnight..." and "Kah scared!".

You need two Furby Connects with their DLCs flashed, and something to run the show. That can be a computer with Bluetooth, or, with no computer on the night, an ESP32-S3 board running MicroPython on a USB power bank. The firmware targets the [FireBeetle 2 ESP32-S3](https://wiki.dfrobot.com/SKU_DFR0975_FireBeetle_2_Board_ESP32_S3) (its button and LED pins are at the top of [`firmware/main.py`](firmware/main.py)); other ESP32 boards should work with those changed. Boards with an external-antenna socket, like the FireBeetle's -U version, need the antenna attached before powering up.

1. List each Furby's clips, its antenna color while it speaks, and the scenes that string them together in [`halloween/show.toml`](halloween/show.toml). Clips can be anything ffmpeg reads, up to a few seconds each; `audioutils/freesound_fetch.py` fetches public-domain sound effects from [Freesound](https://freesound.org), and `audioutils/extract_voice.py` unpacks the Furby's own voice. The paths in `show.toml` point into `build/`, so make or fetch the clips first, or pass `--skip-missing` to build with what you have. A clip can also be a table that cuts a snippet, such as `{ path = "song.mp3", start = "0:08", seconds = 10 }`, which suits music. The bundled public-domain Toccata opening is one. Mark a clip `optional = true` to leave its scenes out until the file exists. That's how the show handles a Ghostbusters theme you supply at `build/music/ghostbusters.mp3`, since that song is copyrighted and stays out of the repo. Add `before = 0.4` to hold an extra beat before a clip, such as a punchline. Join clips with `+` in a scene step (`"pink.ghostbusters + blue.ghostbusters"`) to play them on both Furbies at once. Mark a scene `greeting = true` to save it for when someone arrives: the button (or Enter, when running from a computer) or the motion sensor plays a greeting, the timer plays the other scenes, and `cooldown` in `[show]` ignores the motion sensor for a while after each greeting. `halloween.py` warns about clips no scene uses, since they still take up room.
2. Build both DLCs: `python halloween.py` writes `build/halloween/pink.dlc`, `blue.dlc` and `show.json`. Each clip gets its own `75` action, chosen so no two actions share a track.
3. Flash `pink.dlc` to one Furby and `blue.dlc` to the other ([see above](#flashing-a-dlc)). Keep the file names: the show tells the Furbies apart by the name of their active DLC.
4. Run the show. Both ways use the same show engine, [`furbyshow.py`](furbyshow.py):
   - **From a computer:** `python porch.py`; press Enter to play a greeting. `python porch.py --clip pink.cackle` plays one clip to test.
   - **Rehearse first, with no Furbies:** `python porch.py --rehearse` plays every scene through your computer's speakers with the show's timing (`--scene 2` or `--clip pink.boo` for just one), so you can tune lines and scenes before flashing anything.
   - **From an ESP32, with no computer:** flash [MicroPython](https://micropython.org/download/ESP32_GENERIC_S3/) to the board (for the FireBeetle's 8 MB of octal PSRAM, the `SPIRAM_OCT` build), then run `firmware/deploy.sh` (needs [uv](https://docs.astral.sh/uv/)). It installs [aioble](https://github.com/micropython/micropython-lib/tree/master/micropython/bluetooth/aioble) and copies the show over. The board starts the show on power-up, keeps both Furbies awake, plays a random scene every 20 to 45 seconds, and plays a greeting right away when you press its button. To greet trick-or-treaters as they walk up, wire a PIR motion sensor (such as an HC-SR501) to a free GPIO and set `PIR_PIN` at the top of [`firmware/main.py`](firmware/main.py). Its LED stays on during a scene and blinks while a Furby is missing. A watchdog reboots it if the show ever hangs. Hold the button while plugging it in to skip the show. After changing the show, reflash both Furbies and run `deploy.sh` again; the show warns if a Furby's DLC doesn't match.

### Deploy and test in two commands

`uv run deploy.py` does steps 2 and 3 for you. It builds the show, then for each Furby asks you to wake just that one, says which DLC it has now, blinks its antenna in its show color, and flashes it once you confirm it's the right one. It refuses to put both DLCs on the same Furby, and `--esp32` copies the show to the board afterwards. Wake one Furby at a time: two identical Furbies that see each other pair up and stop showing up. `--only blue` does just one, `--no-build` flashes what's already built, and `--yes` asks nothing, for scripts.

Then run `uv run porch.py --check` and wake the Furbies, one and then the other once it connects. It plays every clip once on each Furby and uses the Furby's own replies to report which clips played, which were skipped because the Furby was still busy, and which got no reply. It also times each clip's whole sequence (movement and eyes as well as audio) and flags any that run well past their audio, since the Furby can't play its next line until the sequence ends. It checks each Furby's DLC against `show.json`, writes the timings to `build/halloween/timings.json`, and exits non-zero if anything failed.

## License

Files marked `SPDX-License-Identifier: MIT` (the Halloween show, the firmware, and the audio tools in `audioutils/` that carry that header) are available under the [MIT License](LICENSES/MIT.txt). The rest of the repository comes from [Context's original project](https://github.com/ctxis/Furby), which doesn't state a license, so those files stay under Context's terms. Hasbro owns the Furby name and the stock DLC, audio and artwork included here.

Generated audio and DLCs live in `build/`, which git ignores. Don't commit or publish voice clips cloned from the Furby, or DLCs built from the stock one.

## Contributing

We really hope you enjoy tinkering with the scripts. If you'd like to contribute, here are a few things that still need work:

 - Cataloguing the motions in the MTR section
 - Improving the `__compile__()` function of both the XLS and SPR sections to be more robust
 - Mapping which of the 75 ("app video") actions are safe to reuse beyond the ones `spooky_eyes.scene_slots()` picks

(The a18 codec is done: see [John-K/a1800_codec](https://github.com/John-K/a1800_codec).)

Enjoy - we're looking forward to seeing what you make with it!

## Further Reading
- [Reverse Engineering the Furby Connect (Context IS Blog Post)](https://www.contextis.com/blog/dont-feed-them-after-midnight-reverse-engineering-the-furby-connect)
- [Paul Stone's FurBLE Web Bluetooth Controller](https://github.com/pdjstone/furby-web-bluetooth)
- [Jeija's Bluefluff project](https://github.com/Jeija/bluefluff)
- [L0ss & Swarley's Furbhax project](https://github.com/swarley7/furbhax)
- [Igor Afanasyev's Furby audio implementation](https://github.com/iafan/Hacksby)
- [John-K's open-source A1800 codec](https://github.com/John-K/a1800_codec)
- [PyFluff, a Python port of Bluefluff](https://github.com/martinwoodward/pyfluff)
- [Extracted Furby Connect eye animations](https://github.com/lib-fluff-so/furby-connect-eyes-extract)
- [aioble, MicroPython's Bluetooth library](https://github.com/micropython/micropython-lib/tree/master/micropython/bluetooth/aioble)
