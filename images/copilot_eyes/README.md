# GitHub Copilot Eyes for Furby Connect

This directory contains custom eye images designed to display the GitHub Copilot logo on Furby's eyes.

![Copilot Eyes Preview](preview.png)

## Files

- `left.gif` - Left eye image with Copilot logo (128x128, 64-color palette)
- `right.gif` - Right eye image with Copilot logo (128x128, 64-color palette)
- `preview.png` - Preview image showing both eyes

## Usage

To create a custom DLC with the Copilot logo on Furby's eyes, use the `copilot_eyes.py` script:

```bash
python copilot_eyes.py
```

This will generate a `copilot_furby.dlc` file that can be uploaded to your Furby Connect.

**Note**: This repository was originally written for Python 2. If you encounter compatibility issues with Python 3, you may need to use Python 2 or apply Python 2to3 conversion to the `furby.py` file.

## Image Specifications

The eye images follow the Furby Connect DLC specifications:
- **Size**: 128x128 pixels
- **Format**: GIF with indexed color palette
- **Colors**: Up to 64 colors in the palette
- **Design**: Features the GitHub Copilot hexagonal logo design in purple tones

## Customization

You can create your own eye images by following these specifications. The images will be automatically converted to the appropriate format when processed by the `copilot_eyes.py` script.
