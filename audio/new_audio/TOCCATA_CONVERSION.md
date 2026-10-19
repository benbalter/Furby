# Toccata and Fugue in D Minor: the included file

- **`toccata_in_d_minor_16khz.wav`**: the first 20 seconds of Bach's Toccata and Fugue in D Minor (BWV 565), from a public-domain recording. 16-bit PCM WAV, 16 kHz, mono. The famous opening chords take the first 10 seconds and the flowing toccata the next 10.

The Halloween show uses it as is: [`halloween/show.toml`](../../halloween/show.toml)'s `toccata` clip cuts 5 seconds from it, and `halloween.py` converts it while building.

## Converting it to .a18

From the repo's folder, on any OS, with ffmpeg installed:

```bash
uv run audioutils/encode_a18.py audio/new_audio/toccata_in_d_minor_16khz.wav build/toccata.a18 --duration 10
```

That uses the open-source [a1800_codec](https://github.com/John-K/a1800_codec), so it needs no Windows DLL. Keep the output in `build/`: CI fails if new audio is committed. The older A1800.DLL tools (`audioutils/convert_to_a18.py` on Windows, `audioutils/convert_mac_linux.py` through Wine) still work; see [audioutils/README.md](../../audioutils/README.md).

## Using it with a Furby

[TOCCATA_EXAMPLE.md](../../TOCCATA_EXAMPLE.md) builds it into a DLC small enough to flash, flashes it, and plays it.
