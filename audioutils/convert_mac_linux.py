#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  convert_mac_linux.py
#  
#  Audio conversion script for Mac and Linux users
#  
#  This script helps convert WAV files to .a18 format on Mac/Linux
#  using Wine to run the Windows a1800.dll
#

import os
import sys
import subprocess
import tempfile

def check_dependencies():
    """Check if required dependencies are installed."""
    dependencies = {
        'wine': 'Wine (Windows compatibility layer)',
        'ffmpeg': 'FFmpeg (audio processing)'
    }
    
    missing = []
    for cmd, desc in dependencies.items():
        try:
            subprocess.check_output([cmd, '--version'], stderr=subprocess.STDOUT)
        except (subprocess.CalledProcessError, OSError):
            missing.append("%s (%s)" % (cmd, desc))
    
    return missing

def prepare_wav(input_file, output_wav):
    """
    Prepare a WAV file with the correct format for .a18 conversion.
    
    Converts to:
    - 16000 Hz sample rate
    - Mono channel
    - 16-bit PCM format
    """
    print("Preparing WAV file with correct format...")
    
    cmd = [
        'ffmpeg', '-i', input_file,
        '-ar', '16000',      # Sample rate: 16kHz
        '-ac', '1',          # Channels: Mono
        '-acodec', 'pcm_s16le',  # 16-bit PCM
        '-y',                # Overwrite output
        output_wav
    ]
    
    try:
        subprocess.check_call(cmd)
        print("WAV file prepared: %s" % output_wav)
        return True
    except subprocess.CalledProcessError as e:
        print("Error preparing WAV file: %s" % e)
        return False

def convert_with_wine(wav_file, a18_file, dll_path):
    """
    Convert WAV to .a18 using Wine and the a1800.dll
    
    Note: This requires the Windows a1800.dll from GeneralPlus Gadget utility
    """
    print("Converting to .a18 using Wine...")
    
    # Create a Python script to run under Wine
    conversion_script = """
import ctypes
from ctypes.wintypes import LPCSTR, UINT
import sys

dll_path = sys.argv[1]
wav_file = sys.argv[2]
a18_file = sys.argv[3]

a1800dll = ctypes.WinDLL(dll_path)

encproto = ctypes.WINFUNCTYPE(ctypes.c_uint, LPCSTR, LPCSTR, UINT, ctypes.POINTER(UINT), UINT)
encparamflags = ((1, 'infile'), (1, 'outfile'), (1, 'samprate', 16000), (2, 'fh'), (1,'unk', 0))
encfunc = encproto(('enc', a1800dll), encparamflags)

ret = encfunc(infile=LPCSTR(wav_file.encode('ascii')), outfile=LPCSTR(a18_file.encode('ascii')))
print("Conversion result: " + str(ret))
"""
    
    # Write temporary script
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        script_path = f.name
        f.write(conversion_script)
    
    try:
        cmd = [
            'wine', 'python', script_path,
            dll_path, wav_file, a18_file
        ]
        subprocess.check_call(cmd)
        print(".a18 file created: %s" % a18_file)
        return True
    except subprocess.CalledProcessError as e:
        print("Error during conversion: %s" % e)
        return False
    finally:
        os.unlink(script_path)

def main():
    """Main conversion workflow."""
    print("=== Furby Audio Converter for Mac/Linux ===")
    print()
    
    # Check dependencies
    missing = check_dependencies()
    if missing:
        print("ERROR: Missing required dependencies:")
        for dep in missing:
            print("  - %s" % dep)
        print()
        print("Please install them:")
        print("  Mac:   brew install wine-stable ffmpeg")
        print("  Linux: sudo apt-get install wine ffmpeg")
        print("         or: sudo yum install wine ffmpeg")
        return 1
    
    # Get input parameters
    if len(sys.argv) < 3:
        print("Usage: python convert_mac_linux.py <input_audio> <output.a18> [dll_path]")
        print()
        print("Example:")
        print("  python convert_mac_linux.py toccata.mp3 toccata_in_d_minor.a18 a1800.dll")
        print()
        print("The a1800.dll file can be extracted from GeneralPlus Gadget utility")
        return 1
    
    input_file = sys.argv[1]
    output_a18 = sys.argv[2]
    dll_path = sys.argv[3] if len(sys.argv) > 3 else 'a1800.dll'
    
    # Check if input file exists
    if not os.path.exists(input_file):
        print("ERROR: Input file not found: %s" % input_file)
        return 1
    
    # Check if DLL exists
    if not os.path.exists(dll_path):
        print("ERROR: a1800.dll not found at: %s" % dll_path)
        print()
        print("Please download GeneralPlus Gadget utility and extract a1800.dll")
        print("See: http://www.generalplus.com/")
        return 1
    
    # Step 1: Prepare WAV file
    temp_wav = tempfile.mktemp(suffix='.wav')
    try:
        if not prepare_wav(input_file, temp_wav):
            return 1
        
        # Step 2: Convert to .a18
        if not convert_with_wine(temp_wav, output_a18, dll_path):
            return 1
        
        print()
        print("SUCCESS! Audio converted to: %s" % output_a18)
        print("You can now use this file with demo_toccata.py")
        return 0
        
    finally:
        if os.path.exists(temp_wav):
            os.unlink(temp_wav)

if __name__ == '__main__':
    sys.exit(main())
