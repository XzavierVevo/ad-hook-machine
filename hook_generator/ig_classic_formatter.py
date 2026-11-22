"""
Instagram "Classic" style text formatting with balanced line breaking.
Implements sophisticated wrapping logic to avoid widows and ensure visual balance.

This is the SINGLE SOURCE OF TRUTH for text formatting in the image generation pipeline.
All text formatting should go through this module.
"""

from typing import List, Tuple, Optional
from dataclasses import dataclass
from . import config
import re


@dataclass
class TextLayoutSettings:
    """Settings for text layout based on content length."""
    padding_left: int
    padding_right: int
    max_text_width: int
    max_text_height: int
    chars_per_line: int
    target_rows: Optional[int]
    y_center_ratio: float
    is_long: bool


def format_text_casing(text: str) -> str:
    """
    Format text to use Sentence Case if it's all uppercase.
    Mixed case text is left as is.
    
    Args:
        text: Input text
        
    Returns:
        Text with proper casing
    """
    if text.isupper():
        text = text.lower()
        if not text:
            return ""
        return text[0].upper() + text[1:]
    return text


def format_text_simple(text: str, max_width_px: int, font_size: int) -> str:
    """
    Simple word wrapping without over-engineering.
    Respects paragraph breaks (\n\n) but otherwise just wraps naturally.
    """
    from PIL import Image, ImageDraw
    from .font_utils import get_font
    
    # Handle paragraphs
    if '\n\n' in text:
        paragraphs = text.split('\n\n')
        formatted_paragraphs = []
        for para in paragraphs:
            if para.strip():
                formatted_paragraphs.append(format_text_simple(para.strip(), max_width_px, font_size))
        return '\n\n'.join(formatted_paragraphs)
    
    # Handle explicit line breaks (if any)
    if '\n' in text and '\n\n' not in text:
        lines = text.split('\n')
        formatted_lines = []
        for line in lines:
            if line.strip():
                formatted_lines.append(format_text_simple(line.strip(), max_width_px, font_size))
        return '\n'.join(formatted_lines)

    # Simple word wrapping
    words = text.split()
    font = get_font(font_size)
    dummy_img = Image.new('RGB', (1, 1))
    draw = ImageDraw.Draw(dummy_img)
    
    lines = []
    current_line = []
    
    for word in words:
        test_line = ' '.join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=font)
        line_width = bbox[2] - bbox[0]
        
        # Apply letter spacing adjustment to width check
        if config.IG_CLASSIC_LETTER_SPACING != 0:
            num_chars = len(test_line)
            if num_chars > 1:
                spacing_adjustment = (num_chars - 1) * font_size * config.IG_CLASSIC_LETTER_SPACING
                line_width += spacing_adjustment

        if line_width <= max_width_px:
            current_line.append(word)
        else:
            if current_line:
                lines.append(' '.join(current_line))
            current_line = [word]
    
    if current_line:
        lines.append(' '.join(current_line))
    
    return '\n'.join(lines)


def get_font_size_for_text(text: str) -> int:
    """
    Determine font size based on word count only.
    Simple, predictable sizing.
    """
    word_count = len(text.split())
    
    if word_count >= 15 or '\n\n' in text:
        return config.FONT_SIZE_LONG_TEXT  # 100px (exact match)
    elif word_count >= 8:
        return config.FONT_SIZE_MEDIUM_TEXT  # 120px
    else:
        return config.FONT_SIZE_SHORT_TEXT  # 140px


@dataclass
class FormattedHeadline:
    """Result of formatting a headline for image generation."""
    formatted_text: str
    font_size: int
    settings: TextLayoutSettings


def calculate_ig_classic_font_size(text: str, formatted_text: Optional[str] = None, max_width: Optional[int] = None, max_height: Optional[int] = None) -> int:
    """
    Simplified font size calculation - forwards to new logic.
    Kept for backwards compatibility.
    """
    return get_font_size_for_text(formatted_text or text)


def format_headline_complete(headline: str) -> FormattedHeadline:
    """
    Simplified headline formatting pipeline.
    Fixed font sizes, fixed padding, simple wrapping.
    """
    # Step 1: Convert pipes to paragraph breaks for exact match style
    if '|' in headline:
        headline = headline.replace('|', '\n\n')
    
    # Step 2: Apply casing
    headline = format_text_casing(headline)
    
    # Step 3: Get fixed font size based on word count
    font_size = get_font_size_for_text(headline)
    
    # Step 4: Fixed padding
    word_count = len(headline.split())
    if word_count >= 15 or '\n\n' in headline:
        # Long text gets the 160px "exact match" padding
        max_width = config.MAX_TEXT_WIDTH_FIXED
        padding = config.PADDING_FIXED
    else:
        # Shorter text uses standard IG Classic margins
        max_width = config.IG_CLASSIC_MAX_WIDTH
        padding = config.IG_CLASSIC_PAD_X
    
    # Step 5: Simple text formatting
    formatted_text = format_text_simple(headline, max_width, font_size)
    
    # Safety Check: If text is too tall, scale down font size
    from PIL import Image, ImageDraw
    from .font_utils import get_font
    dummy_img = Image.new('RGB', (1, 1))
    draw = ImageDraw.Draw(dummy_img)
    max_allowed_height = int(config.IMAGE_HEIGHT * 0.75)
    
    while True:
        font = get_font(font_size)
        spacing = int(font_size * (config.IG_CLASSIC_LINE_HEIGHT - 1))
        bbox = draw.multiline_textbbox((0, 0), formatted_text, font=font, spacing=spacing, align='center')
        text_height = bbox[3] - bbox[1]
        
        if text_height <= max_allowed_height or font_size <= config.FONT_MIN_SIZE:
            break
            
        # Scale down and re-format
        font_size -= 5
        formatted_text = format_text_simple(headline, max_width, font_size)

    # Create simplified settings
    settings = TextLayoutSettings(
        padding_left=padding,
        padding_right=padding,
        max_text_width=max_width,
        max_text_height=config.IMAGE_HEIGHT - 100,  # Leave margin top/bottom
        chars_per_line=0,  # Not used in new system
        target_rows=None,
        y_center_ratio=0.50,
        is_long=(word_count >= 15 or '\n\n' in headline)
    )
    
    return FormattedHeadline(
        formatted_text=formatted_text,
        font_size=font_size,
        settings=settings
    )
