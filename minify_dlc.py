#!/usr/bin/env python3
"""
Minify Furby Connect DLC files by shrinking audio tracks.

This script provides a command-line interface for reducing the size of
DLC files by truncating audio tracks to a shorter length. This is useful
for testing multiple DLC files as it drastically reduces file size for
faster uploads to Furby Connect.
"""

import argparse
import sys
from pathlib import Path

try:
    from furby import dlc
except ImportError:
    print("Error: Could not import furby module.")
    print("Make sure furby.py is in the same directory or in your Python path.")
    sys.exit(1)


def minify_dlc_file(input_path, output_path, audio_length=128):
    """
    Minify a DLC file by shrinking audio tracks.
    
    Args:
        input_path: Path to input DLC file
        output_path: Path to output minified DLC file
        audio_length: New audio length in bytes (must be multiple of 8, default: 128)
    
    Returns:
        bool: True if successful, False otherwise
    """
    print(f"Loading DLC from {input_path}...")
    
    try:
        D = dlc(str(input_path))
    except FileNotFoundError:
        print(f"Error: Input file not found: {input_path}")
        return False
    except Exception as e:
        print(f"Error: Failed to load DLC file: {e}")
        return False
    
    # Get original file size
    original_size = input_path.stat().st_size
    
    # Minify audio
    print(f"Minifying audio tracks to {audio_length} bytes...")
    D.dlc_sections["AMF"].minify_audio(audio_length)
    
    # Build the minified DLC
    print(f"Building minified DLC to {output_path}...")
    try:
        D.build(str(output_path))
    except Exception as e:
        print(f"Error: Failed to build DLC file: {e}")
        return False
    
    # Get new file size
    new_size = output_path.stat().st_size
    reduction = original_size - new_size
    reduction_pct = (reduction / original_size) * 100 if original_size > 0 else 0
    
    print(f"\nSuccess!")
    print(f"Original size: {original_size:,} bytes")
    print(f"New size:      {new_size:,} bytes")
    print(f"Reduction:     {reduction:,} bytes ({reduction_pct:.1f}%)")
    
    return True


def main():
    parser = argparse.ArgumentParser(
        description='Minify Furby Connect DLC files by shrinking audio tracks.',
        epilog='Example: python minify_dlc.py input.dlc -o output.dlc -l 128'
    )
    parser.add_argument(
        'input_file',
        help='Input DLC file path'
    )
    parser.add_argument(
        '-o', '--output',
        help='Output DLC file path (default: input filename with _minified suffix)'
    )
    parser.add_argument(
        '-l', '--length',
        type=int,
        default=128,
        help='Audio length in bytes (must be multiple of 8, default: 128)'
    )
    
    args = parser.parse_args()
    
    # Check if input file exists
    input_path = Path(args.input_file)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        sys.exit(1)
    
    # Validate audio length is multiple of 8
    if args.length % 8 != 0:
        print(f"Error: Audio length must be a multiple of 8 (got {args.length})")
        print(f"Suggested: {(args.length // 8) * 8} or {((args.length // 8) + 1) * 8}")
        sys.exit(1)
    
    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        # Create output filename with _minified suffix
        output_path = input_path.parent / f"{input_path.stem}_minified{input_path.suffix}"
    
    # Check if output file already exists
    if output_path.exists():
        response = input(f"Warning: {output_path} already exists. Overwrite? (y/n): ")
        if response.lower() != 'y':
            print("Cancelled.")
            sys.exit(0)
    
    # Minify the DLC
    success = minify_dlc_file(input_path, output_path, args.length)
    
    if success:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()
