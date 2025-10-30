#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  play_scale_demo.py
#  
#  Example script demonstrating how to make Furby play a C major scale
#  

from furby import dlc
from scale_generator import ScaleGenerator, play_c_major_scale_with_dlc
import os


def demo_generate_scale_audio():
    """Generate WAV files for the C major scale."""
    print("Step 1: Generating C major scale audio files")
    print("-" * 50)
    
    generator = ScaleGenerator()
    
    # Generate individual notes
    note_files = generator.generate_c_major_scale(
        output_dir='./scale_audio',
        note_duration=0.5  # Half second per note
    )
    
    # Also generate a complete sequence
    sequence_file = generator.generate_scale_sequence(
        output_file='./scale_audio/c_major_scale_sequence.wav',
        note_duration=0.5
    )
    
    print("\nGenerated files:")
    for f in note_files:
        print(f"  - {f}")
    print(f"  - {sequence_file}")
    
    return note_files


def demo_with_existing_dlc():
    """
    Example showing how to add C major scale to an existing DLC.
    
    Note: This example assumes you have already converted the WAV files
    to a18 format using the GeneralPlus audio tool. See audioutils/README.md
    for conversion instructions.
    """
    print("\n\nStep 2: Adding scale to Furby DLC")
    print("-" * 50)
    print("Note: This requires a18-formatted audio files.")
    print("See audioutils/README.md for WAV to a18 conversion instructions.")
    
    # Check if DLC exists
    dlc_path = "./dlc/dlc2/tu003410.dlc"
    if not os.path.exists(dlc_path):
        print(f"DLC file not found: {dlc_path}")
        print("Please provide a valid DLC file path.")
        return
    
    print(f"\nLoading DLC: {dlc_path}")
    D = dlc(dlc_path)
    
    # Example: If you had a18 files, you would use them like this:
    scale_a18_files = [
        "./scale_audio/note_c.a18",
        "./scale_audio/note_d.a18",
        "./scale_audio/note_e.a18",
        "./scale_audio/note_f.a18",
        "./scale_audio/note_g.a18",
        "./scale_audio/note_a.a18",
        "./scale_audio/note_b.a18",
        "./scale_audio/note_c5.a18",
    ]
    
    # Check if a18 files exist
    if all(os.path.exists(f) for f in scale_a18_files):
        print("\nConfiguring Furby to play C major scale...")
        
        # Replace audio for action code 75-0-0-0
        # (This is just an example action code - you can use any valid action code)
        action_code = (75, 0, 0, 0)
        
        play_c_major_scale_with_dlc(D, action_code, scale_a18_files)
        
        # Build the new DLC
        output_dlc = "./furby_scale.dlc"
        D.build(output_dlc)
        print(f"\nNew DLC created: {output_dlc}")
        print("Upload this to your Furby Connect to hear the scale!")
    else:
        print("\na18 files not found. To complete this example:")
        print("1. Convert the generated WAV files to a18 format")
        print("2. Run this script again")


def create_scale_instructions():
    """Print detailed instructions for users."""
    print("\n\n" + "=" * 70)
    print("HOW TO MAKE FURBY PLAY A C MAJOR SCALE")
    print("=" * 70)
    
    print("""
This repository now includes tools to make your Furby Connect play a C major
scale! Here's how:

STEP 1: Generate Audio Files
-----------------------------
Run this script to generate WAV files for each note:

    python play_scale_demo.py

This creates 8 WAV files (C, D, E, F, G, A, B, C) in the scale_audio/ directory.


STEP 2: Convert to a18 Format
------------------------------
Furby uses a proprietary GeneralPlus a18 audio format. You need to convert
the WAV files:

1. Download the GeneralPlus Gadget utility from:
   http://www.generalplus.com/1LVlangLNxxSVyySNservice_n_support_d

2. Extract the a1800.dll file

3. Use the conversion script (Windows only):
   python audioutils/convert.py

   Or use the GeneralPlus tool GUI to convert each WAV file to a18.


STEP 3: Create Modified DLC
----------------------------
Use the provided function to add the scale to your DLC:

    from furby import dlc
    from scale_generator import play_c_major_scale_with_dlc
    
    D = dlc("./dlc/dlc2/tu003410.dlc")
    
    scale_files = [
        "./scale_audio/note_c.a18",
        "./scale_audio/note_d.a18",
        "./scale_audio/note_e.a18",
        "./scale_audio/note_f.a18",
        "./scale_audio/note_g.a18",
        "./scale_audio/note_a.a18",
        "./scale_audio/note_b.a18",
        "./scale_audio/note_c5.a18",
    ]
    
    play_c_major_scale_with_dlc(D, (75, 0, 0, 0), scale_files)
    D.build("./furby_scale.dlc")


STEP 4: Upload to Furby
------------------------
Use the Furby Connect app or web bluetooth tools to upload the new DLC
to your Furby Connect.

For more information on DLC structure and modification, see the main README.md
""")
    print("=" * 70)


if __name__ == "__main__":
    print("Furby C Major Scale Demo")
    print("=" * 70)
    
    # Generate the audio files
    demo_generate_scale_audio()
    
    # Show how to use with DLC (if files exist)
    demo_with_existing_dlc()
    
    # Print full instructions
    create_scale_instructions()
