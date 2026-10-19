# Furby audio files

Audio that ships with the repo for building DLCs. Furby Connect plays GeneralPlus A1800 `.a18` audio at 16 kHz, mono.

- **`imperial_march-16000_wav.a18`**: the Imperial March. `spooky_eyes.py` plays it on action 75-0-4-4 by default (`--song`).
- **`darkside_wav.a18`**: a clip of about 15 seconds. `spooky_eyes.py` plays it on 75-0-3-4 by default (`--sting`).
- **`toccata_in_d_minor_16khz.wav`**: the first 20 seconds of Bach's Toccata and Fugue in D Minor, public domain. The Halloween show plays 5 seconds of it; see [TOCCATA_CONVERSION.md](TOCCATA_CONVERSION.md) and [TOCCATA_EXAMPLE.md](../../TOCCATA_EXAMPLE.md).

Don't add files here: put your own audio and anything you convert in `build/`, which git ignores. CI fails if audio other than these three files is committed.

## Converting audio to .a18

On any OS, with ffmpeg installed, from the repo's folder:

```bash
uv run audioutils/encode_a18.py my_song.mp3 build/my_song.a18 --start 0:30 --duration 10
```

It reads anything ffmpeg does, resamples to 16 kHz mono, and encodes with the open-source [a1800_codec](https://github.com/John-K/a1800_codec), so no Windows DLL is needed. The Halloween show doesn't even need this step: list a WAV or MP3 in [`halloween/show.toml`](../../halloween/show.toml) and `halloween.py` converts it. The older tools that use GeneralPlus's A1800.DLL (on Windows, or through Wine on a Mac or Linux) are described in [audioutils/README.md](../../audioutils/README.md).

## Format

A `.a18` file as `encode_a18.py` writes it, and as `furby.py` reads it, is a 4-byte little-endian length (counting the 2-byte bitrate that follows), the 2-byte bitrate, then A1800 frames. Files from GeneralPlus's own tools may start with a 0x30-byte `GENERALPLUS SP` header before the length.

## Tips

1. **Keep it short.** Audio costs about 2 KB a second, and a DLC has to stay under about 350 KB to upload. A few seconds per clip is plenty, and the Furby's speaker doesn't do music any favors.
2. **Test small first.** `D.dlc_sections["AMF"].minify_audio()` cuts every stock track to 128 bytes, for faster test uploads.
3. **Play it over Bluetooth.** A DLC's audio plays only when an action is triggered over Bluetooth (`uv run porch.py --action 75,0,4,4`), not from the Furby's own reactions.
