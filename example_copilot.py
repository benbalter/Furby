#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  example_copilot.py
#
#  Example script showing how to use the Copilot eyes functionality
#

# Example 1: Generate Copilot eyes DLC with default settings
def example_basic():
    """
    Basic usage - generate a Copilot eyes DLC with default settings
    """
    from copilot_eyes import make_copilot_eyes
    
    print("Generating Copilot eyes DLC with default settings...")
    make_copilot_eyes()
    print("Done! Your copilot_furby.dlc file is ready.")


# Example 2: Generate Copilot eyes DLC with custom output path
def example_custom_output():
    """
    Generate DLC with a custom output path
    """
    from copilot_eyes import make_copilot_eyes
    
    output_path = "./my_custom_furby.dlc"
    print("Generating Copilot eyes DLC to {}...".format(output_path))
    make_copilot_eyes(dlc_out=output_path)
    print("Done!")


# Example 3: Use custom eye images
def example_custom_eyes():
    """
    Generate DLC with your own custom eye images
    Note: Images must be 128x128 GIF with 64-color palette
    """
    from copilot_eyes import make_copilot_eyes
    
    left_eye = "./my_left_eye.gif"
    right_eye = "./my_right_eye.gif"
    output = "./my_furby.dlc"
    
    print("Generating DLC with custom eyes...")
    make_copilot_eyes(
        left_gif=left_eye,
        right_gif=right_eye,
        dlc_out=output
    )
    print("Done!")


if __name__ == "__main__":
    # Run the basic example
    example_basic()
    
    # Uncomment to try other examples:
    # example_custom_output()
    # example_custom_eyes()
