#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  scale_generator.py
#  
#  Copyright 2024
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

"""
Module for generating musical scales for Furby Connect.

This module provides functionality to generate audio files for musical scales,
specifically designed for use with Furby Connect DLC files.
"""

import wave
import math
import struct
import os


class ScaleGenerator:
    """Generate audio files for musical scales."""
    
    # Standard frequencies for C major scale (C4 to C5)
    C_MAJOR_SCALE = {
        'C': 261.63,   # C4
        'D': 293.66,   # D4
        'E': 329.63,   # E4
        'F': 349.23,   # F4
        'G': 392.00,   # G4
        'A': 440.00,   # A4
        'B': 493.88,   # B4
        'C5': 523.25,  # C5 (octave)
    }
    
    # Furby uses 16kHz sample rate
    SAMPLE_RATE = 16000
    
    def __init__(self, sample_rate=SAMPLE_RATE):
        """Initialize the scale generator.
        
        Args:
            sample_rate: Audio sample rate in Hz (default: 16000 for Furby)
        """
        self.sample_rate = sample_rate
    
    def generate_tone(self, frequency, duration=0.5, amplitude=0.5):
        """Generate a sine wave tone.
        
        Args:
            frequency: Frequency in Hz
            duration: Duration in seconds
            amplitude: Amplitude (0.0 to 1.0)
            
        Returns:
            List of audio samples
        """
        samples = []
        num_samples = int(self.sample_rate * duration)
        
        for i in range(num_samples):
            # Generate sine wave
            t = float(i) / self.sample_rate
            sample = amplitude * math.sin(2 * math.pi * frequency * t)
            # Convert to 16-bit integer
            sample_int = int(sample * 32767)
            samples.append(sample_int)
        
        return samples
    
    def save_wav(self, samples, filename):
        """Save audio samples to a WAV file.
        
        Args:
            samples: List of audio samples
            filename: Output filename
        """
        with wave.open(filename, 'w') as wav_file:
            # Set parameters: mono, 16-bit
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.sample_rate)
            
            # Convert samples to bytes
            for sample in samples:
                wav_file.writeframes(struct.pack('<h', sample))
    
    def generate_c_major_scale(self, output_dir='./scale_audio', note_duration=0.5):
        """Generate WAV files for all notes in the C major scale.
        
        Args:
            output_dir: Directory to save WAV files
            note_duration: Duration of each note in seconds
            
        Returns:
            List of generated filenames
        """
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        generated_files = []
        
        # Generate each note in the scale
        for note_name, frequency in self.C_MAJOR_SCALE.items():
            filename = os.path.join(output_dir, f'note_{note_name.lower()}.wav')
            samples = self.generate_tone(frequency, note_duration)
            self.save_wav(samples, filename)
            generated_files.append(filename)
            print(f"Generated {note_name}: {filename}")
        
        return generated_files
    
    def generate_scale_sequence(self, output_file='./scale_audio/c_major_scale_sequence.wav', 
                               note_duration=0.5):
        """Generate a single WAV file with the complete C major scale sequence.
        
        Args:
            output_file: Output filename
            note_duration: Duration of each note in seconds
        """
        all_samples = []
        
        # Generate each note in order
        for note_name in ['C', 'D', 'E', 'F', 'G', 'A', 'B', 'C5']:
            frequency = self.C_MAJOR_SCALE[note_name]
            samples = self.generate_tone(frequency, note_duration)
            all_samples.extend(samples)
        
        # Create output directory if needed
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        # Save combined sequence
        self.save_wav(all_samples, output_file)
        print(f"Generated complete scale sequence: {output_file}")
        
        return output_file


def play_c_major_scale_with_dlc(dlc_obj, action_code, scale_audio_files):
    """Helper function to configure a DLC to play a C major scale.
    
    This function demonstrates how to replace audio in a Furby DLC to play
    a C major scale. Note: audio files must be in a18 format.
    
    Args:
        dlc_obj: A dlc object from furby module
        action_code: 4-tuple action code (e.g., (75, 0, 0, 0))
        scale_audio_files: List of 8 a18 audio files for the scale notes
        
    Example:
        from furby import dlc
        from scale_generator import play_c_major_scale_with_dlc
        
        D = dlc("./dlc/dlc2/tu003410.dlc")
        scale_files = [
            "./scale_audio/note_c.a18",
            "./scale_audio/note_d.a18",
            # ... etc
        ]
        play_c_major_scale_with_dlc(D, (75, 0, 0, 0), scale_files)
        D.build("./my_scale_dlc.dlc")
    """
    if len(scale_audio_files) != 8:
        raise ValueError("C major scale requires exactly 8 notes")
    
    # Use the existing replace_audio method
    dlc_obj.replace_audio(action_code, scale_audio_files)
    
    print(f"Configured action code {action_code} to play C major scale")


if __name__ == "__main__":
    # Example usage
    print("Furby C Major Scale Generator")
    print("=" * 50)
    
    generator = ScaleGenerator()
    
    # Generate individual note files
    print("\nGenerating individual note WAV files...")
    files = generator.generate_c_major_scale()
    
    # Generate complete scale sequence
    print("\nGenerating complete scale sequence...")
    sequence_file = generator.generate_scale_sequence()
    
    print("\n" + "=" * 50)
    print("WAV files generated successfully!")
    print("\nTo use these with Furby:")
    print("1. Convert WAV files to a18 format using the GeneralPlus tool")
    print("   (See audioutils/README.md for instructions)")
    print("2. Use the play_c_major_scale_with_dlc() function to add them to a DLC")
    print("3. Build and upload the DLC to your Furby Connect")
