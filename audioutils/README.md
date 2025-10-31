# Audio Utils

This directory contains utilities for working with Furby Connect audio files in the a18 format.

## Requirements

- **a1800.dll**: Download the [GeneralPlus Gadget utility](http://www.generalplus.com/1LVlangLNxxSVyySNservice_n_support_d) and extract the a1800.dll file from it
- **Python 3.8+** with the following packages:
  - `pydub` (for MP3 support): `pip install pydub`
  - `Pillow` (already in requirements.txt)
- **ffmpeg** (for MP3 conversion): Required by pydub for MP3 support
- **Windows OS**: The a1800.dll only works on Windows

## Scripts

### convert_to_a18.py

**NEW**: Convert audio files (MP3 or WAV) to a18 format for Furby Connect.

This script provides a command-line interface for converting audio files to the a18 format used by Furby Connect DLC files.

**Usage:**
```bash
# Convert a WAV file
python convert_to_a18.py input.wav

# Convert an MP3 file
python convert_to_a18.py input.mp3

# Specify output path
python convert_to_a18.py input.wav -o output/myaudio.a18

# Specify custom sample rate (default is 16000)
python convert_to_a18.py input.wav -s 16000

# Specify DLL path if not in current directory
python convert_to_a18.py input.wav -d path/to/a1800.dll
```

**Features:**
- Accepts both MP3 and WAV input files
- Automatically converts MP3 to WAV before encoding to a18
- Configurable sample rate (default: 16000 Hz, recommended for Furby)
- Command-line interface for easy automation

### extract_audio.py

Extracts the GeneralPlus a18-encoded audio files from a DLC file.

**Note**: This is a rough script that requires customization of file/directory names.

### convert.py

**DEPRECATED**: Use `convert_to_a18.py` instead.

Converts a directory of a18 files to WAV format using Python's ctypes to call the a1800 DLL.

**Note**: This script requires customization and only supports batch conversion from a18 to WAV.

## GitHub Actions Workflow

A CI workflow is available to convert audio files automatically using GitHub Actions.

**Workflow: `convert-audio.yml`**

This workflow runs on a Windows runner and can convert MP3 or WAV files to a18 format.

**To use the workflow:**

1. Go to the "Actions" tab in your GitHub repository
2. Select "Convert Audio to a18" workflow
3. Click "Run workflow"
4. Fill in the inputs:
   - **audio_file_path**: Path to your audio file in the repository (e.g., `audio/new_audio/myfile.wav`)
   - **output_path** (optional): Where to save the a18 file
   - **sample_rate** (optional): Sample rate for conversion (default: 16000)
5. Click "Run workflow"
6. Once complete, download the converted a18 file from the workflow artifacts

**Setting up the a1800.dll for CI:**

The workflow requires the a1800.dll to function. You have several options:

1. **Store as a GitHub secret** (recommended):
   - Convert the DLL to base64: `certutil -encode a1800.dll a1800.dll.b64` (Windows) or `base64 a1800.dll > a1800.dll.b64` (Linux/Mac)
   - Create a repository secret named `A1800_DLL_BASE64` with the base64 content
   - Uncomment the secret decoding section in the workflow

2. **Store in the repository** (not recommended due to licensing):
   - Place the DLL in the `audioutils/` directory
   - The workflow will automatically detect and use it

3. **Download from a secure location**:
   - Host the DLL on a secure server you control
   - Update the workflow to download from your URL

## Sample Rate Information

Furby Connect audio files typically use a sample rate of 16000 Hz (16 kHz). When converting audio files, the script defaults to this sample rate. If you need a different sample rate, you can specify it using the `-s` flag.

## Troubleshooting

**"Could not load a1800.dll"**: Make sure the a1800.dll file is in the same directory as the script, or specify its path with the `-d` flag.

**"pydub is required for MP3 conversion"**: Install pydub with `pip install pydub` and ensure ffmpeg is installed on your system.

**MP3 conversion fails**: Make sure ffmpeg is installed and accessible in your PATH. On Windows, you can install it with `choco install ffmpeg`.

**Conversion fails with return code != 0**: Check that your input WAV file is in a compatible format (preferably mono, 16000 Hz sample rate, 16-bit PCM).