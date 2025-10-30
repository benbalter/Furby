# Furby Audio Files

This directory contains audio files in the GeneralPlus .a18 format for use with Furby Connect DLC files.

## Existing Audio Files

- **imperial_march-16000_wav.a18** - The Imperial March from Star Wars
- **darkside_wav.a18** - Dark Side themed audio

## Adding Toccata in D Minor

**NEW: A pre-prepared WAV file is now included!** See `TOCCATA_CONVERSION.md` for details on converting the included `toccata_in_d_minor_16khz.wav` file to .a18 format.

To add Bach's Toccata and Fugue in D Minor to your Furby, you'll need to prepare the audio file in .a18 format.

### Option 1: Use the Included WAV File (Easiest!)

This directory now includes `toccata_in_d_minor_16khz.wav` - a properly formatted WAV file extracted from the full Toccata recording. See `TOCCATA_CONVERSION.md` for conversion instructions.

### Option 2: Find an Existing .a18 File

If you can find a pre-converted .a18 file of Toccata in D Minor (16kHz sample rate), simply place it in this directory with the filename:
```
toccata_in_d_minor.a18
```

### Option 3: Convert from WAV

To convert a WAV file to .a18 format, you'll need:

1. **Source Audio**: Obtain a recording of Toccata and Fugue in D Minor by J.S. Bach in WAV format
   - Recommended: Keep it under 30 seconds for Furby compatibility
   - Sample rate: 16000 Hz (16 kHz)
   - Mono channel (not stereo)

2. **Choose your conversion method based on your OS:**

#### Windows

1. Download the [GeneralPlus Gadget utility](http://www.generalplus.com/)
2. Extract the `a1800.dll` file from the utility
3. Use the conversion script:
   ```bash
   python ../audioutils/convert.py
   ```
   Note: You'll need to modify the script to point to your specific WAV file

#### Mac/Linux

We provide a conversion script that uses Wine to run the Windows DLL:

1. **Install dependencies:**
   ```bash
   # Mac (using Homebrew)
   brew install wine-stable ffmpeg
   
   # Ubuntu/Debian
   sudo apt-get install wine ffmpeg
   
   # Fedora/RHEL
   sudo yum install wine ffmpeg
   ```

2. **Get the a1800.dll:**
   - Download [GeneralPlus Gadget utility](http://www.generalplus.com/) (Windows version)
   - Extract `a1800.dll` from the archive
   - Place it in the `audioutils` directory

3. **Convert your audio:**
   ```bash
   cd audioutils
   python convert_mac_linux.py /path/to/toccata.mp3 ../audio/new_audio/toccata_in_d_minor.a18 a1800.dll
   ```
   
   The script will:
   - Convert your audio to the correct format (16kHz mono WAV)
   - Use Wine to run the Windows DLL for .a18 encoding
   - Output the .a18 file ready for use

**Alternative for Mac/Linux (without Wine):**

If you can't get Wine working, you can:
1. Use an existing .a18 file from the `audio/new_audio/` directory as a template
2. Or run the conversion on a Windows machine/VM
3. Or ask someone with Windows to convert the file for you

### Option 3: Use Multiple Segments

For a more dramatic effect, you can split Toccata into multiple segments:

- `toccata_intro.a18` - The iconic opening notes
- `toccata_main.a18` - The main theme
- `toccata_climax.a18` - The dramatic conclusion

Then use the `create_multi_track_toccata()` function in `demo_toccata.py`.

## Audio Format Specifications

GeneralPlus .a18 files for Furby Connect should have:
- **Sample Rate**: 16000 Hz (16 kHz)
- **Channels**: Mono
- **Format**: GeneralPlus SP codec
- **File Structure**: 
  - Optional header: `\x00\xff\x00\xffGENERALPLUS SP\x00\x00` (at offset 0x00)
  - Length field: 4-byte little-endian integer (at offset 0x30 if header present, else 0x00)
  - Audio data: GeneralPlus compressed audio

## Tips for Audio Preparation

1. **Keep it short**: Furby has limited memory. Aim for 15-30 second clips.
2. **Test incrementally**: Start with a single track before creating complex multi-track DLCs.
3. **Use minify_audio()**: The demo scripts include this function to shrink audio for faster testing.
4. **Backup original DLCs**: Always keep a backup before uploading custom DLCs to your Furby.

## Example Usage

Once you have `toccata_in_d_minor.a18` in this directory, run:

```bash
python demo_toccata.py
```

This will create `toccata_furby.dlc` which you can upload to your Furby Connect.

## Need Help?

For more information on Furby Connect DLC structure and audio handling, see:
- Main project README.md
- [Context IS Blog Post](https://www.contextis.com/blog/dont-feed-them-after-midnight-reverse-engineering-the-furby-connect)
- The audioutils directory for conversion scripts
