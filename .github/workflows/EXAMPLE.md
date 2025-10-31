# Audio Conversion Workflow Example

This document provides examples of how to use the audio conversion CI workflow.

## Overview

The workflow allows you to convert audio files (MP3 or WAV) to a18 format compatible with Furby Connect DLC files. The conversion runs on a Windows GitHub Actions runner and produces an a18 file that can be downloaded as an artifact.

## Prerequisites

Before using the workflow, you need to configure the a1800.dll. See the [audioutils README](../audioutils/README.md) for details on the different configuration options.

## Using the Workflow

### Step 1: Prepare Your Audio File

1. Add your audio file (MP3 or WAV) to the repository, typically in the `audio/` directory
2. Commit and push the file to GitHub

Example:
```bash
# Add your audio file
cp myaudio.wav audio/new_audio/

# Commit and push
git add audio/new_audio/myaudio.wav
git commit -m "Add new audio file for conversion"
git push
```

### Step 2: Run the Workflow

1. Navigate to your repository on GitHub
2. Click on the "Actions" tab
3. Select "Convert Audio to a18" from the workflows list
4. Click "Run workflow" button
5. Fill in the required inputs:
   - **audio_file_path**: `audio/new_audio/myaudio.wav`
   - **output_path** (optional): `audio/new_audio/myaudio.a18`
   - **sample_rate** (optional): `16000` (default)
6. Click the green "Run workflow" button

### Step 3: Download the Converted File

1. Wait for the workflow to complete (usually 2-5 minutes)
2. Click on the completed workflow run
3. Scroll down to the "Artifacts" section
4. Download the "converted-a18" artifact
5. Extract the ZIP file to get your a18 file

## Example Scenarios

### Convert a WAV file with default settings

**Input:**
- audio_file_path: `audio/new_audio/imperial_march-16000_wav.a18` (if using existing)
- output_path: (leave empty)
- sample_rate: (leave empty or use 16000)

This will create an a18 file in the same location with the same name.

### Convert an MP3 file with custom output path

**Input:**
- audio_file_path: `audio/mysong.mp3`
- output_path: `audio/converted/mysong_furby.a18`
- sample_rate: `16000`

This will convert the MP3 to WAV internally, then to a18, and save it to the specified path.

### Convert with custom sample rate

**Input:**
- audio_file_path: `audio/myaudio.wav`
- output_path: `audio/myaudio.a18`
- sample_rate: `8000`

This will convert the audio with a custom sample rate of 8000 Hz (though 16000 Hz is recommended for Furby).

## Local Usage

You can also use the conversion script locally on a Windows machine:

```bash
# Install dependencies
pip install pydub

# Convert a file
python audioutils/convert_to_a18.py audio/myfile.wav

# With custom output
python audioutils/convert_to_a18.py audio/myfile.mp3 -o output/converted.a18

# With custom sample rate
python audioutils/convert_to_a18.py audio/myfile.wav -s 16000
```

## Troubleshooting

### Workflow fails with "a1800.dll not found"

Make sure you've configured the a1800.dll as described in the [audioutils README](../audioutils/README.md). You need to either:
1. Store it as a GitHub secret (recommended)
2. Add it to the repository (not recommended due to licensing)
3. Host it on a secure server and update the workflow

### Audio quality issues

- Use 16000 Hz sample rate for best compatibility with Furby
- Ensure your input audio is mono (single channel)
- Use uncompressed WAV format for best results

### File not found error

- Double-check the file path is correct and relative to the repository root
- Make sure the file has been committed and pushed to GitHub
- Verify the file exists in the branch you're running the workflow from

## Integration with DLC Files

Once you have your a18 file, you can use it in your Furby DLC files:

```python
from furby import dlc

# Load a DLC
D = dlc("./dlc/dlc1/tu012700.dlc")

# Replace audio for action code 75-0-0-0
D.replace_audio((75,0,0,0), ["path/to/your/file.a18"])

# Build the modified DLC
D.build("/tmp/modified_dlc.dlc")
```

See the main [README](../README.md) for more information on working with DLC files.
