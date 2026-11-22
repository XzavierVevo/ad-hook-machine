import os
from pathlib import Path
from PIL import ImageFont
from . import config

# Cache the font path to avoid repeated lookups and messages
_font_path_cache = None
_font_logged = False

def get_font(font_size: int) -> ImageFont.FreeTypeFont:
    """
    Load font from the resources/font/ folder.
    Uses the first .ttf or .otf font file found in the folder.
    No fallbacks - if no font is found, raise an error.
    """
    global _font_path_cache, _font_logged
    
    # Use cached font path if available
    if _font_path_cache is not None:
        try:
            return ImageFont.truetype(str(_font_path_cache), size=font_size)
        except Exception as e:
            raise RuntimeError(
                f"Failed to load font: {_font_path_cache.name}\n"
                f"Path: {_font_path_cache}\n"
                f"Error: {e}"
            )
    
    # Look for font in resources/font/ folder
    font_folder = config.RESOURCES_DIR / "font"
    
    if not font_folder.exists():
        raise FileNotFoundError(
            f"FONT FOLDER NOT FOUND: {font_folder}\n"
            f"Please create a 'font' folder in the resources directory and add a font file.\n"
            f"Expected location: {font_folder}"
        )
    
    # Find any .ttf or .otf file in the font folder
    font_files = list(font_folder.glob("*.ttf")) + list(font_folder.glob("*.otf"))
    
    if not font_files:
        raise FileNotFoundError(
            f"NO FONT FILES FOUND in {font_folder}\n"
            f"Please add a .ttf or .otf font file to the font folder.\n"
            f"The first font file found will be used for all templates."
        )
    
    # Use the first font file found (sorted alphabetically for consistency)
    font_path = sorted(font_files)[0]
    _font_path_cache = font_path
    
    # Only print font info once
    if not _font_logged:
        print(f"[INFO] Using font: {font_path.name}")
        _font_logged = True
    
    try:
        return ImageFont.truetype(str(font_path), size=font_size)
    except Exception as e:
        raise RuntimeError(
            f"Failed to load font: {font_path.name}\n"
            f"Path: {font_path}\n"
            f"Error: {e}"
        )

