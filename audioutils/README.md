# Audio Utils

**WARNING**: These scripts are very rough. You'll need to customise the file/directory names to make them work. 

You'll also need to download the [GeneralPlus Gadget utility](http://www.generalplus.com/1LVlangLNxxSVyySNservice_n_support_d) and extract the a1800.dll file from it. 

## Scripts

 - **`extract_audio.py`** - extracts the GeneralPlus a18-encoded audio files from the DLC file
 - **`convert.py`** - converts a directory of a18 files to wav, using Python's ctypes to call into the a1800 DLL. **Windows only.**
 - **`convert_mac_linux.py`** - converts audio files (mp3, wav, etc.) to a18 format on Mac/Linux using Wine and FFmpeg

## Mac/Linux Conversion

For Mac and Linux users, use `convert_mac_linux.py`:

### Requirements
```bash
# Mac (using Homebrew)
brew install wine-stable ffmpeg

# Ubuntu/Debian
sudo apt-get install wine ffmpeg

# Fedora/RHEL
sudo yum install wine ffmpeg
```

### Usage
```bash
python convert_mac_linux.py <input_audio> <output.a18> [dll_path]
```

Example:
```bash
python convert_mac_linux.py toccata.mp3 ../audio/new_audio/toccata_in_d_minor.a18 a1800.dll
```

The script will:
1. Convert your audio to 16kHz mono WAV format using FFmpeg
2. Use Wine to run the Windows a1800.dll for .a18 encoding
3. Output the .a18 file ready for use with Furby DLC files