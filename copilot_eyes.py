#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  copilot_eyes.py
#  
#  Script to create a Furby Connect DLC with GitHub Copilot logo on eyes
#  Based on demo.py structure
#  

from furby import dlc

########################################################################
#
# This script creates a DLC with the GitHub Copilot logo appearing on
# Furby's eyes. It works with DLC TU003410.DLC and replaces the eye
# animations with custom Copilot logo images.
#
########################################################################


def make_copilot_eyes(dlc_in="./dlc/dlc2/tu003410.dlc", 
                      left_gif="./images/copilot_eyes/left.gif", 
                      right_gif="./images/copilot_eyes/right.gif", 
                      dlc_out="./copilot_furby.dlc",
                      animated=True):
    """
    Create a custom Furby DLC with Copilot logo on the eyes.
    
    Args:
        dlc_in: Path to the input DLC file
        left_gif: Path to the left eye GIF image (128x128, 64-color palette)
        right_gif: Path to the right eye GIF image (128x128, 64-color palette)
        dlc_out: Path to the output DLC file
        animated: If True, use multiple frames for animation (requires _0.gif, _1.gif etc.)
    """

    # Open the DLC and shrink audio to reduce file size
    D = dlc(dlc_in)
    D.dlc_sections["AMF"].minify_audio()

    # For animated eyes, we'll use multiple frame GIFs
    if animated:
        # Load frame 0 and frame 1 for animation
        left_gif_frame0 = left_gif.replace('.gif', '_0.gif')
        left_gif_frame1 = left_gif.replace('.gif', '_1.gif')
        right_gif_frame0 = right_gif.replace('.gif', '_0.gif')
        right_gif_frame1 = right_gif.replace('.gif', '_1.gif')
        
        # Extract palettes (use frame 0 palette for both)
        left_palette = D.dlc_sections["PAL"].extract_palette(left_gif_frame0)
        right_palette = D.dlc_sections["PAL"].extract_palette(right_gif_frame0)

        # Quarterize both frames for left eye
        left_cels_frame0 = D.dlc_sections["CEL"].quarterize(left_gif_frame0)
        left_cels_frame1 = D.dlc_sections["CEL"].quarterize(left_gif_frame1)
        
        # Quarterize both frames for right eye
        right_cels_frame0 = D.dlc_sections["CEL"].quarterize(right_gif_frame0)
        right_cels_frame1 = D.dlc_sections["CEL"].quarterize(right_gif_frame1)
        
        # Combine all cels
        all_left_cels = left_cels_frame0 + left_cels_frame1
        all_right_cels = right_cels_frame0 + right_cels_frame1
    else:
        # Extract palettes from the GIF files
        left_palette = D.dlc_sections["PAL"].extract_palette(left_gif)
        right_palette = D.dlc_sections["PAL"].extract_palette(right_gif)

        # Quarterize the GIF files (convert 128x128 to four 64x64 quarters)
        left_cels = D.dlc_sections["CEL"].quarterize(left_gif)
        right_cels = D.dlc_sections["CEL"].quarterize(right_gif)
        
        all_left_cels = left_cels
        all_right_cels = right_cels

    # Keep transparent cel at index 0
    # Move blank cel to cel 1 (currently at index 17)
    for y in range(64):
        for x in range(64):
            D.dlc_sections["CEL"].cels[1][y][x] = D.dlc_sections["CEL"].cels[17][y][x]

    # Replace cels with our Copilot logo cels
    D.dlc_sections["CEL"].cels = D.dlc_sections["CEL"].cels[:2] + all_left_cels + all_right_cels

    # Replace palettes with our new palettes
    victim_palette_L = 4  # chilli palette - used for left eye
    victim_palette_R = 5  # flame palette - used for right eye
    
    for i in range(len(D.dlc_sections["PAL"].palettes[victim_palette_L])):
        D.dlc_sections["PAL"].palettes[victim_palette_L][i] = left_palette[i]
    for i in range(len(D.dlc_sections["PAL"].palettes[victim_palette_R])):
        D.dlc_sections["PAL"].palettes[victim_palette_R][i] = right_palette[i]

    # Get existing palette offsets
    existing_palettes = set()
    for f in D.dlc_sections["SPR"].frames:
        existing_palettes.update(f[1:8:2])
    existing_palettes = sorted(list(existing_palettes))
    
    # Identify which palette is which
    eye_palette = existing_palettes[0]
    chilli_palette = existing_palettes[2]
    flame_palette = existing_palettes[4]

    # Modify sequences to use our custom animation
    # Replacing animations referenced in sequence 15 (75-0-4-4)
    D.dlc_sections["SEQ"].sequences[15][3] = 0x8401
    D.dlc_sections["SEQ"].sequences[15][4] = D.dlc_sections["SEQ"].entry_terminator
    D.dlc_sections["SEQ"].sequences[15] = D.dlc_sections["SEQ"].sequences[15][:5]

    # Replacing animations in sequence 50 (75-0-3-4)
    D.dlc_sections["SEQ"].sequences[50][3] = 0x8401
    D.dlc_sections["SEQ"].sequences[50][4] = D.dlc_sections["SEQ"].entry_terminator
    D.dlc_sections["SEQ"].sequences[50] = D.dlc_sections["SEQ"].sequences[50][:5]
    
    # Replacing animations in sequence 22 (75-0-0-3)
    D.dlc_sections["SEQ"].sequences[22][3] = 0x8401
    D.dlc_sections["SEQ"].sequences[22][4] = D.dlc_sections["SEQ"].entry_terminator
    D.dlc_sections["SEQ"].sequences[22] = D.dlc_sections["SEQ"].sequences[22][:5]

    # Replace eye frames with blank white
    for i in [8, 9]:
        for f in D.dlc_sections["SPR"].frame_playlists[i]["frame_indices"]:
            D.dlc_sections["SPR"].frames[f][0] = 1  # Blank white frame
            D.dlc_sections["SPR"].frames[f][2] = 1  # Blank white frame
            D.dlc_sections["SPR"].frames[f][4] = 1  # Blank white frame
            D.dlc_sections["SPR"].frames[f][6] = 1  # Blank white frame

            D.dlc_sections["SPR"].frames[f][1] = eye_palette
            D.dlc_sections["SPR"].frames[f][3] = eye_palette
            D.dlc_sections["SPR"].frames[f][5] = eye_palette
            D.dlc_sections["SPR"].frames[f][7] = eye_palette

    # Replace chilli frames with blank white
    for i in [10, 11]:
        for f in D.dlc_sections["SPR"].frame_playlists[i]["frame_indices"]:
            D.dlc_sections["SPR"].frames[f][0] = 1  # Blank white frame
            D.dlc_sections["SPR"].frames[f][2] = 1  # Blank white frame
            D.dlc_sections["SPR"].frames[f][4] = 1  # Blank white frame
            D.dlc_sections["SPR"].frames[f][6] = 1  # Blank white frame

            D.dlc_sections["SPR"].frames[f][1] = eye_palette
            D.dlc_sections["SPR"].frames[f][3] = eye_palette
            D.dlc_sections["SPR"].frames[f][5] = eye_palette
            D.dlc_sections["SPR"].frames[f][7] = eye_palette

    # Replace left-eye flame frames with left Copilot logo
    # First frame (quarters 2, 3, 4, 5) - frame 0 of animation
    for f in D.dlc_sections["SPR"].frame_playlists[13]["frame_indices"][:10] + D.dlc_sections["SPR"].frame_playlists[13]["frame_indices"][19:29]:
        D.dlc_sections["SPR"].frames[f][0] = 2
        D.dlc_sections["SPR"].frames[f][2] = 3
        D.dlc_sections["SPR"].frames[f][4] = 4
        D.dlc_sections["SPR"].frames[f][6] = 5

        D.dlc_sections["SPR"].frames[f][1] = chilli_palette
        D.dlc_sections["SPR"].frames[f][3] = chilli_palette
        D.dlc_sections["SPR"].frames[f][5] = chilli_palette
        D.dlc_sections["SPR"].frames[f][7] = chilli_palette

    # Second frame (quarters 6, 7, 8, 9) - frame 1 of animation for pulsing effect
    if animated:
        # Use frame 1 cels for animation
        for f in D.dlc_sections["SPR"].frame_playlists[13]["frame_indices"][10:19] + D.dlc_sections["SPR"].frame_playlists[13]["frame_indices"][29:38]:
            D.dlc_sections["SPR"].frames[f][0] = 6
            D.dlc_sections["SPR"].frames[f][2] = 7
            D.dlc_sections["SPR"].frames[f][4] = 8
            D.dlc_sections["SPR"].frames[f][6] = 9

            D.dlc_sections["SPR"].frames[f][1] = chilli_palette
            D.dlc_sections["SPR"].frames[f][3] = chilli_palette
            D.dlc_sections["SPR"].frames[f][5] = chilli_palette
            D.dlc_sections["SPR"].frames[f][7] = chilli_palette
    else:
        # Static: use same frame
        for f in D.dlc_sections["SPR"].frame_playlists[13]["frame_indices"][10:19] + D.dlc_sections["SPR"].frame_playlists[13]["frame_indices"][29:38]:
            D.dlc_sections["SPR"].frames[f][0] = 2
            D.dlc_sections["SPR"].frames[f][2] = 3
            D.dlc_sections["SPR"].frames[f][4] = 4
            D.dlc_sections["SPR"].frames[f][6] = 5

            D.dlc_sections["SPR"].frames[f][1] = chilli_palette
            D.dlc_sections["SPR"].frames[f][3] = chilli_palette
            D.dlc_sections["SPR"].frames[f][5] = chilli_palette
            D.dlc_sections["SPR"].frames[f][7] = chilli_palette

    # Replace right-eye flame frames with right Copilot logo
    # First frame (quarters 10, 11, 12, 13) - frame 0 of animation
    # Note: For animated mode, right eye cels start at index 2 + 8 (left cels) = 10
    right_cel_offset = 10 if animated else 6
    
    for f in D.dlc_sections["SPR"].frame_playlists[12]["frame_indices"][:10] + D.dlc_sections["SPR"].frame_playlists[12]["frame_indices"][19:29]:
        D.dlc_sections["SPR"].frames[f][0] = right_cel_offset
        D.dlc_sections["SPR"].frames[f][2] = right_cel_offset + 1
        D.dlc_sections["SPR"].frames[f][4] = right_cel_offset + 2
        D.dlc_sections["SPR"].frames[f][6] = right_cel_offset + 3

        D.dlc_sections["SPR"].frames[f][1] = flame_palette
        D.dlc_sections["SPR"].frames[f][3] = flame_palette
        D.dlc_sections["SPR"].frames[f][5] = flame_palette
        D.dlc_sections["SPR"].frames[f][7] = flame_palette
        
    # Second frame - frame 1 for animation or same frame for static
    if animated:
        # Use frame 1 cels for animation
        for f in D.dlc_sections["SPR"].frame_playlists[12]["frame_indices"][10:19] + D.dlc_sections["SPR"].frame_playlists[12]["frame_indices"][29:38]:
            D.dlc_sections["SPR"].frames[f][0] = right_cel_offset + 4
            D.dlc_sections["SPR"].frames[f][2] = right_cel_offset + 5
            D.dlc_sections["SPR"].frames[f][4] = right_cel_offset + 6
            D.dlc_sections["SPR"].frames[f][6] = right_cel_offset + 7

            D.dlc_sections["SPR"].frames[f][1] = flame_palette
            D.dlc_sections["SPR"].frames[f][3] = flame_palette
            D.dlc_sections["SPR"].frames[f][5] = flame_palette
            D.dlc_sections["SPR"].frames[f][7] = flame_palette
    else:
        # Static: use same frame
        for f in D.dlc_sections["SPR"].frame_playlists[12]["frame_indices"][10:19] + D.dlc_sections["SPR"].frame_playlists[12]["frame_indices"][29:38]:
            D.dlc_sections["SPR"].frames[f][0] = right_cel_offset
            D.dlc_sections["SPR"].frames[f][2] = right_cel_offset + 1
            D.dlc_sections["SPR"].frames[f][4] = right_cel_offset + 2
            D.dlc_sections["SPR"].frames[f][6] = right_cel_offset + 3

            D.dlc_sections["SPR"].frames[f][1] = flame_palette
            D.dlc_sections["SPR"].frames[f][3] = flame_palette
            D.dlc_sections["SPR"].frames[f][5] = flame_palette
            D.dlc_sections["SPR"].frames[f][7] = flame_palette

    # Build the new DLC file
    D.build(dlc_out)
    print("Successfully created Copilot eyes DLC: {}".format(dlc_out))
    return


if (__name__ == "__main__"):
    make_copilot_eyes()
