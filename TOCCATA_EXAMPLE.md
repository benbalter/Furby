# Toccata in D Minor - Example Configuration

This file demonstrates the conceptual steps for configuring a Furby to play 
Bach's Toccata and Fugue in D Minor.

## Quick Start

If you have:
- Python 2.7 installed
- A DLC file (e.g., `./dlc/dlc2/tu003410.dlc`)  
- Toccata audio in .a18 format at `./audio/new_audio/toccata_in_d_minor.a18`

Simply run:
```bash
python2 demo_toccata.py
```

## Manual Configuration Steps

### Step 1: Load the DLC
```python
from furby import dlc
D = dlc("./dlc/dlc2/tu003410.dlc")
```

### Step 2: Prepare Audio (Optional)
Minify existing audio to speed up testing:
```python
D.dlc_sections["AMF"].minify_audio()
```

### Step 3: Replace Audio for Action Codes
Action codes are 4-tuples that trigger specific Furby responses. Common ones:
- `(75, 0, 0, 0)` - Button press
- `(75, 0, 0, 1)` - Alternative button press  
- `(75, 0, 0, 3)` - Another common action

Replace audio for these actions with Toccata:
```python
toccata_file = "./audio/new_audio/toccata_in_d_minor.a18"

D.replace_audio((75, 0, 0, 0), [toccata_file])
D.replace_audio((75, 0, 0, 1), [toccata_file])
D.replace_audio((75, 0, 0, 3), [toccata_file])
```

### Step 4: Build the New DLC
```python
D.build("./toccata_furby.dlc")
```

### Step 5: Upload to Furby
Use the Furby Connect app or other tools to upload `toccata_furby.dlc` to your Furby.

## Advanced: Multi-Track Toccata

For a more dramatic experience, split Toccata into segments:

### Prepare Three Audio Files:
- `toccata_intro.a18` - The iconic opening (measures 1-15)
- `toccata_main.a18` - The main theme (measures 16-90)  
- `toccata_climax.a18` - The dramatic fugue (measures 91-end)

### Use Multi-Track Function:
```python
D.replace_audio((75, 0, 0, 0), [
    "./audio/new_audio/toccata_intro.a18",
    "./audio/new_audio/toccata_main.a18",
    "./audio/new_audio/toccata_climax.a18"
])
```

This will play all three segments in sequence when the action is triggered.

## Audio Preparation Tips

### Getting Toccata Audio:
1. Find a public domain recording of Toccata and Fugue in D Minor (BWV 565)
2. Edit to desired length (15-30 seconds recommended)
3. Convert to .a18 format:
   - **Windows**: Use `audioutils/convert.py` with a1800.dll
   - **Mac/Linux**: Use `audioutils/convert_mac_linux.py` (requires Wine and FFmpeg)
   - See `audio/new_audio/README.md` for detailed instructions

### Mac/Linux Quick Start:
```bash
# Install dependencies
brew install wine-stable ffmpeg  # Mac
# or: sudo apt-get install wine ffmpeg  # Linux

# Convert audio
cd audioutils
python convert_mac_linux.py toccata.mp3 ../audio/new_audio/toccata_in_d_minor.a18 a1800.dll
```

### Recommended Sections:
- **Opening**: 0:00-0:15 - The iconic dramatic opening
- **Main Theme**: 0:15-0:45 - The flowing toccata section
- **Fugue**: 2:30-3:00 - The complex fugue section
- **Climax**: 8:00-8:30 - The thunderous conclusion

### Audio Format Requirements:
- Format: GeneralPlus .a18 (proprietary codec)
- Sample Rate: 16000 Hz
- Channels: Mono
- Typical Size: ~20-30 KB for 15-30 seconds

## Troubleshooting

### "File not found" errors
- Ensure audio files exist at the specified paths
- Check that DLC file path is correct

### "SyntaxError: Missing parentheses in call to 'print'"
- You're running Python 3. This project requires Python 2.7
- Use `python2` command instead of `python`

### Furby doesn't play the audio
- Verify the DLC was uploaded successfully
- Try triggering different actions (button presses, tickles, etc.)
- The action codes may vary between Furby firmware versions

### Audio sounds distorted
- Ensure source audio was converted at 16kHz (not 44.1kHz or 48kHz)
- Keep audio segments under 30 seconds
- Use `minify_audio()` if testing multiple iterations

## Why Toccata?

Toccata and Fugue in D Minor (BWV 565) by Johann Sebastian Bach is one of 
the most famous organ pieces ever written. Its dramatic, haunting sound is 
often associated with horror movies and Halloween. Having your Furby play 
this piece creates a delightfully theatrical and slightly creepy effect!

The piece is also in the public domain, making it ideal for this project.

## Related Files

- `demo_toccata.py` - Complete working implementation
- `audio/new_audio/README.md` - Audio conversion instructions
- `furby.py` - Core DLC manipulation library
- `demo.py` - Example showing eye animation replacement
