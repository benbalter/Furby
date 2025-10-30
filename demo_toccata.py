#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  demo_toccata.py
#  
#  Copyright 2017 Ed Locard (@L0C4RD)
#  
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#  
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
#  
#  

"""
Demo script for making Furby play Toccata and Fugue in D Minor by J.S. Bach

This script demonstrates how to replace Furby's audio responses with 
the famous Toccata and Fugue in D Minor. The haunting organ piece is 
perfect for giving your Furby a dramatic, theatrical personality.

REQUIREMENTS:
    - A Furby Connect DLC file (e.g., ./dlc/dlc2/tu003410.dlc)
    - Toccata audio file in .a18 format (see audio/new_audio/README.md for conversion instructions)
    - Python with Pillow library installed

USAGE:
    python demo_toccata.py

The script will create a new DLC file (toccata_furby.dlc) that can be 
uploaded to your Furby Connect.
"""

from furby import dlc
import os


def make_toccata_furby(dlc_in="./dlc/dlc2/tu003410.dlc", 
                       toccata_audio="./audio/new_audio/toccata_in_d_minor.a18",
                       dlc_out="./toccata_furby.dlc"):
    """
    Create a Furby DLC that plays Toccata in D Minor.
    
    This function takes an existing Furby Connect DLC file and replaces
    audio for specific action codes with the Toccata in D Minor audio.
    
    Args:
        dlc_in: Path to the input DLC file
        toccata_audio: Path to the Toccata audio file in .a18 format
        dlc_out: Path for the output DLC file
        
    Returns:
        None
        
    Raises:
        FileNotFoundError: If the input DLC or audio file doesn't exist
    """
    
    # Check if files exist
    if not os.path.exists(dlc_in):
        raise FileNotFoundError(f"Input DLC file not found: {dlc_in}")
    
    if not os.path.exists(toccata_audio):
        print(f"WARNING: Toccata audio file not found: {toccata_audio}")
        print("Please prepare a Toccata in D Minor audio file in .a18 format.")
        print("See audio/new_audio/README.md for instructions on audio conversion.")
        return
    
    print("Loading DLC file...")
    D = dlc(dlc_in)
    
    # Optionally minify audio to speed up testing
    print("Minifying existing audio tracks...")
    D.dlc_sections["AMF"].minify_audio()
    
    # Replace audio for action code 75-0-0-0 (button press)
    # This is a common action code triggered by user interaction
    print("Replacing audio for action code 75-0-0-0 with Toccata...")
    try:
        D.replace_audio((75, 0, 0, 0), [toccata_audio])
    except Exception as e:
        print(f"Error replacing audio for action code 75-0-0-0: {e}")
    
    # Replace audio for action code 75-0-0-1 (alternative button press)
    print("Replacing audio for action code 75-0-0-1 with Toccata...")
    try:
        D.replace_audio((75, 0, 0, 1), [toccata_audio])
    except Exception as e:
        print(f"Error replacing audio for action code 75-0-0-1: {e}")
    
    # Replace audio for action code 75-0-0-3 (another common action)
    print("Replacing audio for action code 75-0-0-3 with Toccata...")
    try:
        D.replace_audio((75, 0, 0, 3), [toccata_audio])
    except Exception as e:
        print(f"Error replacing audio for action code 75-0-0-3: {e}")
    
    # Build the new DLC file
    print(f"Building new DLC file: {dlc_out}")
    D.build(dlc_out)
    
    print("Done! Your Toccata-enabled Furby DLC is ready.")
    print(f"Upload {dlc_out} to your Furby Connect to hear it play Toccata in D Minor!")
    print("\nNOTE: Be careful when uploading custom DLCs - bad DLCs can make your Furby unhappy.")


def create_multi_track_toccata(dlc_in="./dlc/dlc2/tu003410.dlc",
                                 toccata_intro="./audio/new_audio/toccata_intro.a18",
                                 toccata_main="./audio/new_audio/toccata_main.a18", 
                                 toccata_climax="./audio/new_audio/toccata_climax.a18",
                                 dlc_out="./toccata_furby_multi.dlc"):
    """
    Create a Furby DLC with multiple segments of Toccata in D Minor.
    
    This advanced function allows you to split the Toccata into multiple
    parts and have them play at different times or as a sequence.
    
    Args:
        dlc_in: Path to the input DLC file
        toccata_intro: Path to intro section of Toccata (.a18 format)
        toccata_main: Path to main section of Toccata (.a18 format)
        toccata_climax: Path to climax section of Toccata (.a18 format)
        dlc_out: Path for the output DLC file
        
    Returns:
        None
    """
    
    # Check if files exist
    if not os.path.exists(dlc_in):
        raise FileNotFoundError(f"Input DLC file not found: {dlc_in}")
    
    audio_files = [toccata_intro, toccata_main, toccata_climax]
    missing_files = [f for f in audio_files if not os.path.exists(f)]
    
    if missing_files:
        print(f"WARNING: Audio files not found: {missing_files}")
        print("Please prepare Toccata audio segments in .a18 format.")
        print("See audio/new_audio/README.md for instructions.")
        return
    
    print("Loading DLC file...")
    D = dlc(dlc_in)
    
    print("Minifying existing audio tracks...")
    D.dlc_sections["AMF"].minify_audio()
    
    # Replace with a sequence of Toccata segments
    print("Replacing audio for action code 75-0-0-0 with Toccata segments...")
    try:
        D.replace_audio((75, 0, 0, 0), [toccata_intro, toccata_main, toccata_climax])
    except Exception as e:
        print(f"Error: {e}")
    
    # Build the new DLC file
    print(f"Building new DLC file: {dlc_out}")
    D.build(dlc_out)
    
    print("Done! Your multi-track Toccata Furby DLC is ready.")


if __name__ == "__main__":
    # Try to create the Toccata Furby
    make_toccata_furby()
    
    # Uncomment the following line to create a multi-track version instead:
    # create_multi_track_toccata()
