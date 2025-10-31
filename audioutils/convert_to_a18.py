#!/usr/bin/env python3
"""
Convert audio files (MP3 or WAV) to a18 format for Furby Connect.

This script uses the GeneralPlus a1800.dll to convert audio files.
It supports both MP3 and WAV input files, converting them to the
a18 format compatible with Furby Connect DLC files.

Requirements:
- Windows OS (for a1800.dll)
- a1800.dll from GeneralPlus Gadget utility
- pydub (for MP3 conversion)
"""

import argparse
import ctypes
from ctypes.wintypes import LPCSTR, UINT
import os
import sys
from pathlib import Path

# Default sample rate for Furby Connect audio
DEFAULT_SAMPLE_RATE = 16000

def load_a1800_dll(dll_path='a1800.dll'):
    """Load the a1800.dll and set up conversion functions."""
    try:
        a1800dll = ctypes.WinDLL(dll_path)
    except OSError as e:
        print(f"Error: Could not load {dll_path}")
        print(f"Make sure the a1800.dll file is in the current directory or specify its path.")
        print(f"Download it from the GeneralPlus Gadget utility.")
        sys.exit(1)
    
    # Set up the encoding function
    encproto = ctypes.WINFUNCTYPE(ctypes.c_uint, LPCSTR, LPCSTR, UINT, ctypes.POINTER(UINT), UINT)
    encparamflags = ((1, 'infile'), (1, 'outfile'), (1, 'samprate', DEFAULT_SAMPLE_RATE), (2, 'fh'), (1,'unk', 0))
    encfunc = encproto(('enc', a1800dll), encparamflags)
    
    # Set up the decoding function
    decproto = ctypes.WINFUNCTYPE(ctypes.c_uint, LPCSTR, LPCSTR, ctypes.POINTER(UINT), UINT, UINT)
    decparamflags = ((1, 'infile'), (1, 'outfile'), (2, 'fp'), (1, 'unk1', DEFAULT_SAMPLE_RATE), (1,'unk2', 0))
    decfunc = decproto(('dec', a1800dll), decparamflags)
    
    return encfunc, decfunc

def convert_mp3_to_wav(mp3_path, wav_path, sample_rate=DEFAULT_SAMPLE_RATE):
    """Convert MP3 to WAV using pydub."""
    try:
        from pydub import AudioSegment
    except ImportError:
        print("Error: pydub is required for MP3 conversion.")
        print("Install it with: pip install pydub")
        print("You may also need ffmpeg installed.")
        sys.exit(1)
    
    print(f"Converting {mp3_path} to WAV...")
    audio = AudioSegment.from_mp3(mp3_path)
    
    # Convert to mono, set sample rate
    audio = audio.set_channels(1)
    audio = audio.set_frame_rate(sample_rate)
    
    # Export as WAV
    audio.export(wav_path, format='wav')
    print(f"Converted to {wav_path}")
    
    return wav_path

def ensure_wav_format(input_path, sample_rate=DEFAULT_SAMPLE_RATE):
    """Ensure the input file is in WAV format with correct settings."""
    input_path = Path(input_path)
    
    if input_path.suffix.lower() == '.mp3':
        # Convert MP3 to WAV
        wav_path = input_path.with_suffix('.wav')
        return convert_mp3_to_wav(str(input_path), str(wav_path), sample_rate)
    elif input_path.suffix.lower() == '.wav':
        # Already WAV, but we might want to verify/convert sample rate
        # For now, just use it as-is
        return str(input_path)
    else:
        print(f"Error: Unsupported file format: {input_path.suffix}")
        print("Supported formats: .mp3, .wav")
        sys.exit(1)

def convert_wav_to_a18(wav_path, a18_path, encfunc, sample_rate=DEFAULT_SAMPLE_RATE):
    """Convert WAV to a18 using the a1800.dll."""
    print(f"Converting {wav_path} to a18...")
    
    wav_path_bytes = str(wav_path).encode('ascii')
    a18_path_bytes = str(a18_path).encode('ascii')
    
    ret = encfunc(
        infile=LPCSTR(wav_path_bytes),
        outfile=LPCSTR(a18_path_bytes),
        samprate=sample_rate
    )
    
    if ret == 0:
        print(f"Successfully converted to {a18_path}")
        return True
    else:
        print(f"Error: Conversion failed with return code {ret}")
        return False

def main():
    parser = argparse.ArgumentParser(
        description='Convert audio files (MP3 or WAV) to a18 format for Furby Connect.'
    )
    parser.add_argument(
        'input_file',
        help='Input audio file (MP3 or WAV)'
    )
    parser.add_argument(
        '-o', '--output',
        help='Output a18 file path (default: same as input with .a18 extension)'
    )
    parser.add_argument(
        '-d', '--dll-path',
        default='a1800.dll',
        help='Path to a1800.dll (default: a1800.dll in current directory)'
    )
    parser.add_argument(
        '-s', '--sample-rate',
        type=int,
        default=DEFAULT_SAMPLE_RATE,
        help=f'Sample rate for conversion (default: {DEFAULT_SAMPLE_RATE})'
    )
    
    args = parser.parse_args()
    
    # Check if input file exists
    input_path = Path(args.input_file)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        sys.exit(1)
    
    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.with_suffix('.a18')
    
    # Load the DLL
    encfunc, decfunc = load_a1800_dll(args.dll_path)
    
    # Ensure we have a WAV file
    wav_path = ensure_wav_format(input_path, args.sample_rate)
    
    # Convert to a18
    success = convert_wav_to_a18(wav_path, output_path, encfunc, args.sample_rate)
    
    # Clean up temporary WAV if we created one from MP3
    if input_path.suffix.lower() == '.mp3' and Path(wav_path) != input_path:
        try:
            os.remove(wav_path)
            print(f"Cleaned up temporary file: {wav_path}")
        except OSError:
            # Failed to clean up, but not critical
            pass
    
    if success:
        print("\nConversion complete!")
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()
