# Toccata and Fugue in D Minor - Conversion Status

## Included Files

This directory contains a prepared audio file ready for conversion to .a18 format:

- **`toccata_in_d_minor_16khz.wav`** - First 30 seconds of Toccata and Fugue in D Minor
  - Format: 16-bit PCM WAV
  - Sample Rate: 16000 Hz (16 kHz)
  - Channels: Mono
  - Duration: ~30 seconds
  - Source: Public domain recording

This file is properly formatted and ready to be converted to .a18 format.

## Converting to .a18 Format

To complete the conversion to .a18 format (required for Furby), you need:

### Option 1: Windows Conversion

1. Download the [GeneralPlus Gadget utility](http://www.generalplus.com/)
2. Extract `a1800.dll` from the utility
3. Use the Windows conversion script:
   ```bash
   # Modify audioutils/convert.py to use toccata_in_d_minor_16khz.wav as input
   python audioutils/convert.py
   ```

### Option 2: Mac/Linux Conversion

1. Install Wine and FFmpeg:
   ```bash
   # Mac
   brew install wine-stable ffmpeg
   
   # Linux
   sudo apt-get install wine ffmpeg
   ```

2. Download and extract `a1800.dll` from GeneralPlus Gadget utility

3. Use the Mac/Linux conversion script:
   ```bash
   cd ../../audioutils
   python convert_mac_linux.py \
       ../audio/new_audio/toccata_in_d_minor_16khz.wav \
       ../audio/new_audio/toccata_in_d_minor.a18 \
       a1800.dll
   ```

### Why Two Steps?

The .a18 format uses a proprietary GeneralPlus codec that requires the Windows-only `a1800.dll` library. The WAV file provided here is already in the correct format (16kHz mono), so the conversion to .a18 should be straightforward once you have the DLL.

## Using with Furby

Once you have `toccata_in_d_minor.a18`, you can use it with the demo script:

```bash
cd ../..
python demo_toccata.py
```

This will create a Furby DLC file with Toccata and Fugue in D Minor!

## About the Audio

This excerpt includes the iconic opening of Bach's Toccata and Fugue in D Minor (BWV 565), featuring:
- The famous dramatic opening chords (0-10 seconds)
- The flowing toccata section (10-30 seconds)

This is one of the most recognizable pieces of classical music and creates a perfect dramatic effect for your Furby!
