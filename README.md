# Furby
## Python tools for handling Furby Connect DLC files

<p align="center">
	<img src="images/gifs/gif-full-padding-100.gif">
</p>

**Disclaimer: This script is pretty alpha; use at your own risk. Bad DLCs can make your Furby Connect very unhappy.**

### The original blog post can be found [here](https://www.contextis.com/blog/dont-feed-them-after-midnight-reverse-engineering-the-furby-connect)

## What this fork adds

On top of [Context's original tools](https://github.com/ctxis/Furby), this fork adds:

- **[A two-Furby Halloween show](#set-up-the-halloween-show):** an evil Furby and a friendly one trade lines in short scenes, run from a laptop or a hidden ESP32.
- **[Custom eyes](#example-spooky-halloween-eyes):** demon, jack-o'-lantern and other animated eyes, drawn in code.
- **[Audio tools that need no Windows DLL](#audio-conversion):** convert any audio to the Furby's `.a18` format, unpack a DLC's clips to WAV, and fetch public-domain sound effects.
- **[Flashing from the terminal](#flashing-a-dlc):** `flash.py` puts a DLC on a Furby over Bluetooth, no browser or reset needed.

## Set up the Halloween show

Two Furby Connects sit by the door and trade spooky lines: pink is the evil one, with demon eyes, and blue is the friendly one, with jack-o'-lantern eyes. A computer near the door runs the show over Bluetooth. Most of the setup time goes into making the voice lines.

Two words you'll see a lot:

- A **DLC** is a file of sounds, eye animations and movements that a Furby Connect keeps in its memory. The show builds one for each Furby: `pink.dlc` and `blue.dlc`.
- **Flashing** means copying a DLC onto a Furby over Bluetooth.

You need:

- Two Furby Connects, with fresh batteries. They have no on/off switch, so taking the batteries out is how you turn one off.
- A computer with Bluetooth. These steps are written for a Mac; Windows and Linux should work too (install uv and ffmpeg their own way), but haven't been tried.
- A way to record 19 short voice lines (or your computer's built-in voices, for a quick start).

### 1. Install the tools

1. Open Terminal (on a Mac, press ⌘-Space and type "Terminal").
2. Install [uv](https://docs.astral.sh/uv/), which runs the scripts and installs everything they need the first time: `curl -LsSf https://astral.sh/uv/install.sh | sh`, then close Terminal and open it again.
3. Install [ffmpeg](https://ffmpeg.org), which converts audio. With [Homebrew](https://brew.sh): `brew install ffmpeg`. If Terminal says `command not found: brew`, install Homebrew first with the one-line command on [brew.sh](https://brew.sh) (it takes a few minutes and asks for your password), then run `brew install ffmpeg`.
4. Get this repository and go into it:

   ```bash
   git clone https://github.com/benbalter/Furby.git
   cd Furby
   ```

   If your Mac offers to install its command line developer tools for `git`, say yes. Or skip git: on [the repository's page](https://github.com/benbalter/Furby), click **Code → Download ZIP**, unzip it, and `cd` into the folder it makes, `Furby-master`.
5. Check everything's in place:

   ```bash
   uv run doctor.py
   ```

   It lists each problem with a fix. Until you've made the clips and built the show (steps 2 and 3), it says those are missing; run it again any time something doesn't work.

Every command below runs from this `Furby` folder (`Furby-master` if you downloaded the ZIP).

### 2. Make the clips

A fresh copy of the repository has almost none of the show's audio: the clips live in `build/`, which git ignores. Only the Toccata opening comes with it. Each clip's file name is in [`halloween/show.toml`](halloween/show.toml), the file that describes the whole show.

**Voice lines (needed).** The show's 19 lines go in `build/cloned/`, such as `build/cloned/pink_boo.wav`. The words for each are its `text` in `show.toml` (`boo = { path = "build/cloned/pink_boo.wav", text = "Boo! Kah scare you?" }`). Without them, the show builds with no scenes, or just one if you have the sound effects. Three ways to make them:

- **Let your computer say them,** for a quick start. It won't sound like a Furby, but it lets you test everything:

  ```bash
  uv run voices.py
  ```

  This speaks every line that doesn't have a file yet, in a different voice for each Furby, and saves it where `show.toml` says. It uses a Mac's built-in voices, or [espeak-ng](https://github.com/espeak-ng/espeak-ng) on Windows and Linux. `uv run voices.py --list` shows each line and whether it has audio yet. To try other voices, run `say -v '?'` to see your Mac's, then `uv run voices.py --force --voice Whisper` (for every line), or set `voice = "Whisper"` under `[furbies.pink]` in `show.toml` (for one Furby). It never replaces a file that's already there unless you add `--force`, so you can record your own lines later, one at a time, and run it again for the rest.
- **Record them yourself.** Use any recorder (QuickTime Player, your phone's voice memos) and save each line under the name `show.toml` gives it. Any format ffmpeg reads works: if you'd rather keep `pink_boo.m4a`, change the path in `show.toml` to match. A high, squeaky voice sounds most like a Furby. Trim the silence at each end and keep each line to a few seconds, because each DLC has room for only about 350 KB and audio costs about 2 KB a second.
- **Clone a Furby's voice.** The original show's lines were made with an AI voice-cloning tool, using clips from the Furby's stock DLC as the sample voice. Those clips come from Hasbro's audio, so the cloned lines can't be shared here. `uv run audioutils/extract_voice.py` unpacks the stock clips to `build/voice/` if you want to try it yourself.

**Sound effects (optional).** The cackles, scream, moan and creaky door come from [Freesound](https://freesound.org), public-domain (CC0) sounds only. Get a free API key at <https://freesound.org/apiv2/apply>, then:

```bash
FREESOUND_API_KEY=your-key-here uv run audioutils/freesound_fetch.py "witch cackle" scream "ghost moan" "creaky door" -n 2
```

That writes the `build/sfx/` files `show.toml` names (`witch-cackle-0.wav` and so on), plus `build/sfx/credits.csv`. You'll get Freesound's top-rated sounds for each search, which may not be the ones the original show used. Listen to them and swap any you don't like. Without sound effects, the scenes that use them are left out.

**Ghostbusters (optional).** One greeting has blue ask "Who you gonna call?" and then both Furbies play the Ghostbusters theme. It's copyrighted, so bring your own copy and save it as `build/music/ghostbusters.mp3`. The show plays 6 seconds from 0:11; change `start` in `show.toml` if your copy's chorus starts elsewhere.

### 3. Build the DLCs

```bash
uv run halloween.py --skip-missing
```

This writes `build/halloween/pink.dlc`, `blue.dlc` and `show.json` (the show's script for the computer). The last line says how many scenes it made: 8 with just the voice lines, 12 with the sound effects too, and 13 with Ghostbusters. 0 or 1 scenes means the voice lines are missing or misnamed. `--skip-missing` leaves out any clip that doesn't exist yet, along with its scenes; drop it once you have them all, so a typo in a file name stops the build instead.

### 4. Rehearse on your computer

```bash
uv run porch.py --rehearse
```

This plays every scene through your computer's speakers, with the show's timing, no Furbies needed. `--scene 0` plays just the first scene (they count from 0, in the order the build kept them; a number that's too high lists them all), and `--clip pink.boo` just one line. Re-record or edit anything you don't like, then build again (step 3).

#### Preview the show on your computer

```bash
uv run preview.py --open
```

This builds `build/preview/index.html` and opens it: both Furbies side by side, playing the built show with each clip's sound as the Furby stores it, the eye animations, the antenna lights and the show's real timing (from `emulate.py`), including any wait for a Furby still busy with its last sequence. The eyes are a model of how the firmware draws them, so the real Furby may differ. If your browser won't play it from disk, run `python3 -m http.server -d build/preview` and open <http://localhost:8000>. The page holds audio decoded from DLCs built on Hasbro's, so don't commit, host or share `build/preview/`.

### 5. Flash each Furby

The two Furbies are identical, so the show tells them apart only by which DLC each one has. Flash `pink.dlc` to one and `blue.dlc` to the other, with only the one you're flashing awake, so the DLC can't go to the wrong Furby.

1. Take the batteries out of both Furbies. Put the batteries back in one of them.
2. Flash it, holding it still and close to the computer:

   ```bash
   uv run flash.py build/halloween/pink.dlc
   ```

   The first time, your Mac asks whether Terminal may use Bluetooth: click Allow. Flashing takes 2 to 3½ minutes. It deletes whatever DLCs were already on the Furby, uploads the new one, checks it arrived intact, and makes it the active DLC. The antenna turns green when it's done, or red if it failed, with the reason in Terminal.
3. Label it: a sticker or ribbon that says "pink".
4. Take its batteries out, put the batteries in the other Furby, and flash `build/halloween/blue.dlc` the same way. Label it "blue".
5. Lost track of which is which? Wake just one and run `uv run flash.py --list`: it prints the Furby's address and `active DLC: pink` (or `blue`).

If you change anything in `show.toml` later, build again: the last line says which Furbies need reflashing, if any.

### 6. Run the show

Two Furby Connects close together start singing to each other, and while they do, neither one can be found over Bluetooth. So wake them one at a time:

1. Start the show with both Furbies' batteries out:

   ```bash
   uv run porch.py
   ```

2. Do what Terminal says. It asks for one Furby at a time, in `show.toml`'s order: `Put batteries in (or wake) only the pink Furby`, then, once pink connects, `Pink is connected. Now power up blue.`, and finally `All Furbies connected`.

If a Furby drops during the show, Terminal says so (`Blue dropped. Pink is still connected; wake blue again.`), and if nobody turns up for about a minute it suggests the Furbies are singing together.

The show keeps both Furbies awake and plays a random scene every 20 to 45 seconds. Press Enter when trick-or-treaters walk up to play a greeting. Press Ctrl-C to stop. Keep the computer close to the Furbies, since Bluetooth's range is short.

To run the show without a computer on the night, an ESP32 board can do the same job; see [Running the show from an ESP32](#running-the-show-from-an-esp32).

### Give the show to a friend

Once the show is built, a friend with their own two Furbies can run it without making any clips or building anything:

```bash
uv run package.py               # writes build/furby-show.zip
uv run package.py --rehearsal   # also adds the clips, so they can run porch.py --rehearse
```

The zip holds both DLCs, `show.json` and a `README_FIRST.txt` with the steps: install uv, get this repository, unzip the bundle into it, `uv run deploy.py --no-build` to flash both Furbies, then `uv run porch.py`. It checks that the DLCs match `show.json` first, so build again if it says they don't. The DLCs are built from the Furby's stock DLC, which is Hasbro's, so send the zip privately (AirDrop, a message): never post it or commit it.

## Troubleshooting

- **`Found 2 Furbies in range` (or 0) when flashing.** `flash.py` flashes only when exactly one Furby is awake. Take the other one's batteries out, or pass `--address` with the address `uv run flash.py --list` shows. With 0, check the Furby is awake and close, and that FurBLE isn't open in a browser tab.
- **Flashing fails or times out.** Hold the Furby still, close to the computer, and try again with `--packet-delay 30` to send more slowly. If it still fails, reset the Furby (hold it upside down, hold its tongue, and pull its tail until the eyes go dark) and try again. The [browser route](#flashing-a-dlc) works too.
- **`Two Furbies have pink.dlc; flash the right DLC to one of them`.** Both got the same DLC. Reflash one of them with the other DLC, with only that one awake.
- **`If they're singing together…`, or nothing connects.** The Furbies are probably singing to each other. Take both sets of batteries out, then put them back one Furby at a time, in the order the show asks for, waiting for `Connected to …` before the next. On a Mac, also check System Settings → Privacy & Security → Bluetooth allows Terminal.
- **`pink.dlc on the Furby doesn't match this show; reflash it`.** You rebuilt after flashing. Flash both Furbies again (step 5).
- **A Furby moves its eyes but makes no sound.** It was still finishing its last movement when its line came, and a busy Furby plays a line without the audio. The show waits and tries again on its own, so this should be rare; if it gives up you'll see `skipped: pink stayed busy with its last sequence`.
- **The build stops with `pink is missing clips`.** Make those files, or build with `--skip-missing`.

## Development

This project requires Python 3.11 or later and uses [uv](https://docs.astral.sh/uv/), which installs the dependencies listed in [`pyproject.toml`](pyproject.toml) (and locked in `uv.lock`) the first time you run a script. Run every script as `uv run script.py`, or run `uv sync` once and activate `.venv`; Context's original examples below still say `python script.py`, which works the same way inside `.venv`.

### Testing

Run the test suite to verify the installation:

```bash
uv run python -m unittest test_furby -v
```

The test suite includes:
- DLC file loading and parsing tests
- DLC file building and roundtrip tests
- Python 3 compatibility tests (bytes handling, integer division)
- Section access and manipulation tests
- Error handling tests
- Custom eyes, the eye check, and the Halloween show build, including show.toml mistakes and the real show built with placeholder tones
- The show engine and firmware (against stand-ins for the ESP32's Bluetooth and pins), on virtual Furbies that model busy sequences and drops
- Flashing, deploying, `doctor.py`, `probe.py`, `voices.py`, `package.py` and the browser preview, against stand-in Furbies
- `--help` for every script, so a broken import fails even where nothing else imports it

With [MicroPython](https://micropython.org)'s Unix port installed (`brew install micropython`), the show engine is also tested under MicroPython, as it runs on the board. Lint with [ruff](https://docs.astral.sh/ruff/): `uv run ruff check . && uv run ruff format --check .`


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
uv run audioutils/encode_a18.py monster_mash.mp3 monster_mash.a18 --start 0:30 --duration 25
uv run spooky_eyes.py --song monster_mash.a18
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
uv run spooky_eyes.py                     # demon eyes + Imperial March
uv run spooky_eyes.py --theme pumpkin --song my_song.a18 --sting my_scream.a18
uv run spooky_eyes.py --preview           # build/eyes/<theme>.gif for every theme
```

It writes `build/spooky_<theme>.dlc`, plus a preview GIF of the eyes, rendered back out of the DLC, in `build/<theme>/`. The eyes play on actions `75-0-4-4` (with the song), `75-0-3-4` (with the sting) and `75-0-0-3`.

Each theme is three keyframes played across the animation's 38 frames in its own pattern, since every keyframe costs about 25 KB (12 KB for each eye's copy). The Halloween show puts several themes in each Furby's DLC, one animation each, and its clips take turns through them (see `eyes` in [halloween/show.toml](halloween/show.toml)). Test DLCs on a Furby showed garbled eyes whenever the two eyes shared cels (or had under 16 cels; the tests so far can't tell which), so each eye now gets its own copy, and the show uses one animation per Furby until a second has been seen working. `uv run spooky_eyes.py --probe` builds the test DLCs in `build/eyes_probe2/`, and `uv run eyecheck.py` checks a DLC against what has worked.

The build copies Context's `hacked.dlc`, which [FurBLE](https://github.com/pdjstone/furby-web-bluetooth) ships and which is known to flash: every stock audio track is cut to 128 bytes, and apart from audio and eyes the result matches `hacked.dlc` section for section. The script refuses to write anything over about 350 KB, because bigger uploads time out.

A DLC only changes what plays when a phone or computer triggers an action over Bluetooth. The Furby's own reactions to noises, petting and so on come from its built-in memory, so they sound the same with any DLC active. To try the eyes, flash the DLC (below), then trigger `75 0 4 4` from FurBLE's custom action box.

### Checking before flashing

`python emulate.py` runs every scene in `build/halloween/show.json` against virtual Furbies that answer like real ones (`20:0c`, `20:07` while still busy, `20:0e`, DLC info, the upload `flash.py` does), on a virtual clock, and reports lines that would go silent or be skipped and how long each scene really takes. `--worst` assumes each body movement takes its longest measured time; `--durations file.json` takes measured ones.

`python eyecheck.py build/halloween/*.dlc` composes each custom animation the way the Furby does (all four layers, flip bits, see-through pixels, both candidate palette rules) and fails a DLC that won't show as drawn, or that leaves what's been seen working on a Furby: 16 SPR playlists and a stock-sized SPR. `--gif DIR` writes what it composed, and `--stale-cel previous.dlc` shows what the Furby draws if the new cels don't load, which is how `probe.dlc` (32 playlists) came out on hardware.

## Flashing a DLC

From a terminal, with just one Furby awake (take the batteries out of any others):

```bash
uv run flash.py build/halloween/pink.dlc
```

[`flash.py`](flash.py) deletes the DLCs already on the Furby, uploads the new one, checks the checksum the Furby stores, and activates it. The show's DLCs take 2 to 3½ minutes each. The antenna turns green when it's done, or red if something failed, with the reason in the terminal. There's no need to reset the Furby first: deleting the old DLCs replaced the tongue-and-tail reset the browser route needs.

- `uv run flash.py --list` shows the Furbies in range and each one's active DLC.
- `--address <address>` picks one Furby when more than one is awake.
- `--packet-delay 30` sends more slowly, if uploads time out (the default is 15 ms between packets).
- macOS asks for Bluetooth permission for your terminal app the first time.

Or from a browser, if `flash.py` won't work for you: the hosted FurBLE pages only flash their bundled DLCs, but [benbalter/furby-web-bluetooth](https://github.com/benbalter/furby-web-bluetooth) adds "Upload Custom". It's easy to pick the wrong file there, so check which Furby got which DLC afterwards with `uv run flash.py --list`.

1. Serve it over http (`python3 -m http.server` in its folder) and open `furble.html` in Chrome. Web Bluetooth won't load files from a `file://` page.
2. Reset the Furby: hold it upside down, hold the tongue, and pull the tail until the eyes go dark. Upload one DLC per reset.
3. Click **Connect**, choose your `.dlc`, and click **Upload Custom**. Keep the Furby still and close to the computer; a 200 KB DLC takes about 3 minutes. The antenna turns green when the DLC is active.

The Furby stores DLCs under 8.3-style names (`____PINK.DLC`), so keep file names to 8 letters or fewer. If uploads time out on your computer, add `?packetDelay=30` to the page's address to send more slowly. To remove a DLC, reset the Furby.

## Customizing the Halloween show

[`halloween/show.toml`](halloween/show.toml) describes the whole show: each Furby's clips, their eyes and antenna lights (see [Antenna lights](#antenna-lights)), and the scenes that string the clips together. [`halloween.py`](halloween.py) builds a DLC per Furby from it, and [`porch.py`](porch.py) (or the ESP32) plays the scenes. Both use the same show engine, [`furbyshow.py`](furbyshow.py).

- **Clips** can be anything ffmpeg reads, up to a few seconds each. A clip can also be a table that cuts a snippet, such as `{ path = "song.mp3", start = "0:08", seconds = 10 }`, which suits music; the bundled public-domain Toccata opening is one. Add `before = 0.4` to hold an extra beat before a clip, such as a punchline. Mark a clip `optional = true` to leave its scenes out until the file exists, as the show does for the Ghostbusters theme. Each clip gets its own `75` action in the DLC, chosen so no two actions share a track.
- **Scenes** play their steps in order. Join clips with `+` in a step (`"pink.ghostbusters + blue.ghostbusters"`) to play them on both Furbies at once. Mark a scene `greeting = true` to save it for when someone arrives: Enter (or the ESP32's button or motion sensor) plays a greeting, the timer plays the other scenes, and `cooldown` in `[show]` ignores the motion sensor for a while after each greeting.
- **Eyes**: each Furby's `eyes` list names the [eye themes](#example-spooky-halloween-eyes) its clips take turns through, and a clip table's `eyes = "storm"` picks its own. Each theme costs about 79 KB of the DLC. `uv run spooky_eyes.py --preview` writes GIFs of every theme to `build/eyes/`. `[show] one_eye_animation = true` (the default: on a real Furby, a second animation garbled the eyes) shows only each Furby's first theme.
- **Room**: each DLC has to stay under about 350 KB, and audio costs about 2 KB a second. After each build, `halloween.py` prints each DLC's size against that limit, with the biggest clips and what the eyes cost (`--verbose` lists every clip); it warns past 90%, and over the limit it says which clips to cut or drop. It also warns about clips no scene uses, since they still take up room.
- **Names**: `pink` and `blue` are just names in `show.toml`, and they become the DLC file names (`pink.dlc`) that the show tells the Furbies apart by. Keep them to 8 letters or fewer.

After any change, build again. The build ends by saying which Furbies' DLCs changed since the last build (such as "Only pink.dlc changed: reflash pink and redeploy show.json"), so you reflash only those and (on an ESP32) run `deploy.sh` again; `uv run deploy.py` skips a Furby that already has its DLC. Each clip keeps its `75` action from build to build, recorded in [`halloween/slots.lock.json`](halloween/slots.lock.json): a new clip takes a free slot, and removing or renaming one moves no others. Commit the lock with `show.toml`. `uv run halloween.py --reshuffle` starts the lock again, in clip-name order. The show warns if a Furby's DLC doesn't match.

## Running the show from an ESP32

With no computer on the night, an ESP32-S3 board running MicroPython on a USB power bank can run the show instead. This is the advanced option: it needs some comfort with microcontrollers. The firmware targets the [FireBeetle 2 ESP32-S3](https://wiki.dfrobot.com/SKU_DFR0975_FireBeetle_2_Board_ESP32_S3) (its button and LED pins are at the top of [`firmware/main.py`](firmware/main.py)); other ESP32 boards should work with those changed. Boards with an external-antenna socket, like the FireBeetle's -U version, need the antenna attached before powering up.

1. Flash [MicroPython](https://micropython.org/download/ESP32_GENERIC_S3/) to the board (for the FireBeetle's 8 MB of octal PSRAM, the `SPIRAM_OCT` build).
2. Build the show (`uv run halloween.py`), then plug the board in over USB and run `firmware/deploy.sh`. It installs [aioble](https://github.com/micropython/micropython-lib/tree/master/micropython/bluetooth/aioble) and copies the show over.
3. Power the board up first, then the Furbies one at a time, following its LED (below).

The board starts the show on power-up, keeps both Furbies awake, plays a random scene every 20 to 45 seconds, and plays a greeting right away when you press its button. To greet trick-or-treaters as they walk up, wire a PIR motion sensor (such as an HC-SR501) to a free GPIO and set `PIR_PIN` at the top of [`firmware/main.py`](firmware/main.py), whose comment says which pins to avoid and how to set the sensor's jumper and dials. Its LED says which Furby to power up next, and the board prints the same messages as `porch.py` over USB:

| LED | Means |
| --- | --- |
| 1 blink, pause | Power up the first Furby in `show.toml` (pink) |
| 2 blinks, pause | The first is connected: power up the second (blue) |
| Fast flicker | Nobody has turned up for about a minute. If they're singing together, take the batteries out of one and power them up one at a time |
| Solid | A scene is playing |
| Off | Every Furby is connected, between scenes |
| 3 long blinks, over and over | The show couldn't start (the reason is on USB serial). The board restarts after about 30 seconds and tries again |

A Furby that drops mid-show gets the same blinks again. A watchdog reboots it if the show ever hangs. Hold the button while plugging it in to skip the show.

### Antenna lights

While a Furby speaks, its antenna plays a light that matches the clip's eyes and moves with the sound. `halloween.py` measures each clip's loudness ten times a second and stores it in `show.json`, and the show engine updates the antenna from it while the line plays, so a cackle flickers and a scream flashes.

| Eyes | Light |
| --- | --- |
| demon | red pulse, brighter on loud moments |
| bloodshot | deep red that follows the voice |
| storm | dim blue with white lightning flashes, more of them when loud |
| pumpkin | orange candle flicker |
| ghost | pale, slowly breathing wisp |
| hypno | cycles through the colour wheel |

Change it in [`halloween/show.toml`](halloween/show.toml) with `light` on a clip or a whole Furby: an effect (`off`, `steady`, `voice`, `candle`, `pulse`, `wisp`, `lightning`, `cycle`), an eye theme's name (`light = "ghost"`), or a table such as `light = { effect = "pulse", color = [0, 255, 0] }`. A Furby-wide `light = { color = [255, 0, 0] }` keeps one colour for all its lines, which makes it easier to tell who's talking. A Furby's `antenna` colour is only a fallback now, for lights with no colour of their own. In `[show]`, `light_hz` (default 10, at most 15) sets how often the antenna updates, and `idle_glow = 0.15` keeps each Furby in a scene glowing dimly while the other one speaks (off by default).

`python porch.py --rehearse` draws each antenna as a coloured block in the terminal while the clips play, so you can tune lights without the Furbies. On the Furbies themselves, the light runs alongside each line and never delays a trigger, and the antenna goes dark when the line ends or a scene is cut short. Not yet checked on a real Furby: whether the antenna dims smoothly or only switches colour, and whether 10 updates a second interferes with playback. If lines stutter, lower `light_hz`; if dimmed colours look wrong, use `light = "steady"`.

## Checking your setup and probing a Furby

`uv run doctor.py` checks everything the show needs and prints a ✅ or a ❌ with a one-line fix for each: Python and uv, ffmpeg, whether this computer can use Bluetooth (on a Mac, the app you run it in needs Bluetooth permission under System Settings → Privacy & Security), every clip in `show.toml`, and the built DLCs. Wake one Furby and add `--furbies` to check that it has the right DLC, then put it to sleep and do the same for the other (two awake together sing and can't be found).

[`probe.py`](probe.py) measures what a Furby does with each slot. `uv run probe.py build slots` builds a DLC where every slot says its own number, and `uv run probe.py build motions e000-e017` one where slot N says "move N" and runs just that body movement. Flash it with `flash.py`, then `uv run probe.py run slots` plays each slot in turn, times it from start to finish, and saves the table in `build/probe/`. Add `--reverse`, `--times 3` or `--only 2,5` to dig into odd ones.

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
