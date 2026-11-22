"""
DEPRECATED: Font size calculation module.

This module is kept for backwards compatibility only.
All font size calculations should use ig_classic_formatter.calculate_ig_classic_font_size() instead.

The consolidated formatting pipeline is in ig_classic_formatter.py:
- format_headline_complete() - Full formatting pipeline
- calculate_ig_classic_font_size() - Font size calculation
"""

import warnings

from PIL import Image, ImageDraw
from typing import Optional
from . import config
from .font_utils import get_font

# Import new functions for forwarding
from .ig_classic_formatter import calculate_ig_classic_font_size, format_headline_complete


def calculate_optimal_font_size(
    headline: str,
    image_width: Optional[int] = None,
    image_height: Optional[int] = None,
    safe_zone_top: Optional[float] = None,
    safe_zone_bottom: Optional[float] = None,
    safe_zone_left: Optional[float] = None,
    safe_zone_right: Optional[float] = None,
    line_spacing_ratio: Optional[float] = None,
    formatted_text: Optional[str] = None
) -> int:
    """
    DEPRECATED: Use ig_classic_formatter.calculate_ig_classic_font_size() instead.
    
    This function is kept for backwards compatibility but will be removed in a future version.
    """
    warnings.warn(
        "calculate_optimal_font_size() is deprecated. "
        "Use ig_classic_formatter.calculate_ig_classic_font_size() instead.",
        DeprecationWarning,
        stacklevel=2
    )
    
    # Calculate max_width from safe zones if provided
    if image_width is None:
        image_width = config.IMAGE_WIDTH
    if safe_zone_left is None:
        safe_zone_left = getattr(config, 'SAFE_ZONE_SIDE_RATIO', 0.05)
    if safe_zone_right is None:
        safe_zone_right = getattr(config, 'SAFE_ZONE_SIDE_RATIO', 0.05)
    
    # Ensure safe zones are not None before calculation
    safe_zone_left_val = safe_zone_left if safe_zone_left is not None else 0.05
    safe_zone_right_val = safe_zone_right if safe_zone_right is not None else 0.05
    max_width = int(image_width * (1 - safe_zone_left_val - safe_zone_right_val))
    
    # Forward to new function
    return calculate_ig_classic_font_size(headline, formatted_text, max_width=max_width)


def estimate_text_dimensions(
    text: str,
    font_size: int,
    char_width_ratio: float = 0.6
) -> tuple:
    """
    DEPRECATED: Estimate text dimensions.
    
    This function is kept for backwards compatibility.
    For accurate measurements, use PIL's textbbox directly.
    """
    warnings.warn(
        "estimate_text_dimensions() is deprecated. "
        "Use PIL's draw.textbbox() directly for accurate measurements.",
        DeprecationWarning,
        stacklevel=2
    )
    
    try:
        dummy_img = Image.new('RGB', (1, 1))
        draw = ImageDraw.Draw(dummy_img)
        font = get_font(font_size)
        spacing = int(font_size * (config.IG_CLASSIC_LINE_HEIGHT - 1))
        bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=spacing, align='center')
        return (bbox[2] - bbox[0], bbox[3] - bbox[1])
    except Exception:
        lines = text.split('\n')
        max_line_length = max(len(line) for line in lines) if lines else 0
        num_lines = len(lines)
        
        estimated_width = int(max_line_length * font_size * char_width_ratio)
        estimated_height = int(num_lines * font_size * config.IG_CLASSIC_LINE_HEIGHT)
        
        return (estimated_width, estimated_height)
