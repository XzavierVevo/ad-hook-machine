"""
Image generation using Pillow (PIL) for text rendering.
Optionally creates PSD files using PhotoshopAPI.

SIMPLIFIED ARCHITECTURE:
- Text formatting is handled entirely by ig_classic_formatter.py
- This module only handles image creation and rendering
"""

import os
from pathlib import Path
from typing import Optional, Tuple, List, Union
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

from . import config
from . import api_keys
from .font_utils import get_font
import platform
from .rate_limiter import run_multiprocessed
from .ig_classic_formatter import format_headline_complete, FormattedHeadline
from .templates import TemplateConfig


def create_corner_diagonal_background(width: int, height: int, start_color: str, end_color: str) -> Image.Image:
    """
    Create a background with a solid main color and lighter diagonal corners.
    Matching the style of the "Roof Replacement" example image.
    """
    # Parse colors
    def hex_to_rgb(hex_color):
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    bright_red = hex_to_rgb(start_color) # start_color is #FF0000
    dark_red = hex_to_rgb(end_color)     # end_color is #7A0000

    # Create base image with dark red
    img = Image.new('RGB', (width, height), dark_red)
    draw = ImageDraw.Draw(img)

    # Draw top-left lighter red triangle
    # Line goes from (0, 0.35*H) to (0.35*W, 0)
    draw.polygon([
        (0, 0), 
        (int(width * 0.35), 0), 
        (0, int(height * 0.35))
    ], fill=bright_red)

    # Draw bottom-right lighter red triangle
    # Line goes from (W, 0.65*H) to (0.65*W, H)
    draw.polygon([
        (width, height), 
        (int(width * 0.65), height), 
        (width, int(height * 0.65))
    ], fill=bright_red)
    
    return img


def create_vertical_gradient_background(width: int, height: int, colors: List[str]) -> Image.Image:
    """
    Create a vertical gradient background with multiple color stops.
    
    Args:
        width: Image width in pixels
        height: Image height in pixels
        colors: List of hex colors for gradient stops (top to bottom)
        
    Returns:
        PIL Image with vertical gradient
    """
    def hex_to_rgb(hex_color):
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    img = Image.new('RGB', (width, height))
    draw = ImageDraw.Draw(img)
    
    if len(colors) < 2:
        # Single color, fill solid
        if len(colors) == 0:
            # No colors provided, use default black
            img = Image.new('RGB', (width, height), (0, 0, 0))
        else:
            img = Image.new('RGB', (width, height), hex_to_rgb(colors[0]))
        return img
    
    # Divide height into segments based on color stops
    segments = len(colors) - 1
    if segments <= 0:
        # Fallback to single color if segments is invalid
        img = Image.new('RGB', (width, height), hex_to_rgb(colors[0]))
        return img
    segment_height = height / segments
    
    for seg in range(segments):
        start_color = hex_to_rgb(colors[seg])
        end_color = hex_to_rgb(colors[seg + 1])
        y_start = int(seg * segment_height)
        y_end = int((seg + 1) * segment_height)
        
        for y in range(y_start, min(y_end, height)):
            ratio = (y - y_start) / segment_height if segment_height > 0 else 0
            r = int(start_color[0] + (end_color[0] - start_color[0]) * ratio)
            g = int(start_color[1] + (end_color[1] - start_color[1]) * ratio)
            b = int(start_color[2] + (end_color[2] - start_color[2]) * ratio)
            draw.line([(0, y), (width, y)], fill=(r, g, b))
    
    return img


def create_solid_background(width: int, height: int, color: str) -> Image.Image:
    """
    Create a solid color background.
    
    Args:
        width: Image width in pixels
        height: Image height in pixels
        color: Hex color string (e.g., "#000000")
        
    Returns:
        PIL Image with solid color
    """
    def hex_to_rgb(hex_color):
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    return Image.new('RGB', (width, height), hex_to_rgb(color))


def create_breaking_news_background(width: int, height: int, bg_color: str, banner_color: str) -> Image.Image:
    """
    Create a Breaking News style background with a red banner at the top.
    
    Args:
        width: Image width in pixels
        height: Image height in pixels
        bg_color: Hex color for background (e.g., "#0A0A0A")
        banner_color: Hex color for banner (e.g., "#E60000")
        
    Returns:
        PIL Image with breaking news style background
    """
    def hex_to_rgb(hex_color):
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    # Create dark background
    img = Image.new('RGB', (width, height), hex_to_rgb(bg_color))
    draw = ImageDraw.Draw(img)
    
    # Banner settings
    banner_text = "BREAKING NEWS"
    banner_font_size = 52
    banner_padding_x = 35
    banner_padding_y = 14
    banner_y_position = int(height * 0.10)  # 10% from top
    
    # Load font for banner
    banner_font = get_font(banner_font_size)
    
    # Measure banner text
    bbox = draw.textbbox((0, 0), banner_text, font=banner_font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    # Calculate banner rectangle (centered)
    banner_width = text_width + (banner_padding_x * 2)
    banner_height = text_height + (banner_padding_y * 2)
    banner_x = (width - banner_width) // 2
    
    # Draw red banner rectangle
    draw.rectangle(
        [banner_x, banner_y_position, banner_x + banner_width, banner_y_position + banner_height],
        fill=hex_to_rgb(banner_color)
    )
    
    # Draw banner text (centered in banner)
    text_x = banner_x + banner_padding_x
    text_y = banner_y_position + banner_padding_y - bbox[1]
    draw.text((text_x, text_y), banner_text, fill=(255, 255, 255), font=banner_font)
    
    return img


def get_system_font(font_size: int) -> Union[ImageFont.FreeTypeFont, ImageFont.ImageFont]:
    """Get a system font that looks like messaging apps (SF Pro, Segoe UI, etc.)"""
    system = platform.system()
    font_paths = []
    
    if system == "Windows":
        # Try Segoe UI Semibold/Bold first for heavier weight (matches iOS messaging style)
        font_paths = [
            "C:/Windows/Fonts/seguisb.ttf",   # Segoe UI Semibold - best match
            "C:/Windows/Fonts/segoeuib.ttf",  # Segoe UI Bold
            "C:/Windows/Fonts/segoeui.ttf",   # Segoe UI Regular (fallback)
        ]
    elif system == "Darwin":  # macOS
        # Try SF Pro Semibold/Medium first
        font_paths = [
            "/System/Library/Fonts/Supplemental/SF-Pro-Text-Semibold.otf",
            "/System/Library/Fonts/Supplemental/SF-Pro-Text-Medium.otf",
            "/System/Library/Fonts/Supplemental/SF-Pro-Text-Regular.otf",
            "/Library/Fonts/Helvetica.ttc",
        ]
    else:  # Linux
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    
    # Try to load system font
    for font_path in font_paths:
        try:
            path_obj = Path(font_path)
            if path_obj.exists():
                return ImageFont.truetype(str(path_obj), size=font_size)
        except Exception:
            continue
    
    # Try PIL's default font as last resort
    try:
        return ImageFont.load_default()
    except:
        # Final fallback to default font
        return get_font(font_size)

def draw_rounded_rectangle(draw, xy, radius, fill):
    """Draw a rounded rectangle using ImageDraw."""
    x1, y1, x2, y2 = xy
    # Draw main rectangle
    draw.rectangle([x1 + radius, y1, x2 - radius, y2], fill=fill)
    draw.rectangle([x1, y1 + radius, x2, y2 - radius], fill=fill)
    # Draw corner circles
    draw.ellipse([x1, y1, x1 + radius * 2, y1 + radius * 2], fill=fill)
    draw.ellipse([x2 - radius * 2, y1, x2, y1 + radius * 2], fill=fill)
    draw.ellipse([x1, y2 - radius * 2, x1 + radius * 2, y2], fill=fill)
    draw.ellipse([x2 - radius * 2, y2 - radius * 2, x2, y2], fill=fill)

def create_messaging_background(width: int, height: int, bg_color: str, bubble_color: str) -> Image.Image:
    """
    Create a messaging interface style background with message bubble.
    Mimics mobile messaging apps like iMessage, WhatsApp, etc.
    Matches the exact style from the reference image.
    
    Args:
        width: Image width in pixels
        height: Image height in pixels
        bg_color: Hex color for background (e.g., "#E5E5E5")
        bubble_color: Hex color for message bubble (e.g., "#FFFFFF")
        
    Returns:
        PIL Image with messaging interface style background
    """
    def hex_to_rgb(hex_color):
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    # Create light grey background - exact color from reference
    bg_rgb = hex_to_rgb(bg_color)
    img = Image.new('RGB', (width, height), bg_rgb)
    draw = ImageDraw.Draw(img)
    
    # Message bubble settings - positioned to match reference
    bubble_margin_x = int(width * 0.06)  # Slightly less margin
    bubble_margin_top = int(height * 0.18)  # Space for reactions
    bubble_margin_bottom = int(height * 0.22)  # Space for context menu
    bubble_width = width - (bubble_margin_x * 2)
    bubble_height = height - bubble_margin_top - bubble_margin_bottom
    bubble_x = bubble_margin_x
    bubble_y = bubble_margin_top
    bubble_radius = 18  # Rounded corner radius
    
    # Draw rounded rectangle for message bubble
    bubble_rgb = hex_to_rgb(bubble_color)
    draw_rounded_rectangle(
        draw,
        [bubble_x, bubble_y, bubble_x + bubble_width, bubble_y + bubble_height],
        bubble_radius,
        bubble_rgb
    )
    
    # Draw reaction icons above message - exact positioning
    reaction_y = bubble_y - 32
    reaction_spacing = 38
    reaction_start_x = bubble_x + 18
    
    # Reaction icons: heart, thumbs up, thumbs down, HA HA, !! (blue), question
    circle_size = 26
    
    # Heart icon (grey circle, red heart emoji or symbol)
    rx1 = reaction_start_x
    draw.ellipse([rx1 - circle_size//2, reaction_y - circle_size//2, 
                  rx1 + circle_size//2, reaction_y + circle_size//2],
                 fill=(180, 180, 180))
    # Draw heart shape
    heart_size = 12
    heart_points = [
        (rx1, reaction_y - heart_size//3),
        (rx1 - heart_size//2, reaction_y - heart_size//2),
        (rx1 - heart_size//3, reaction_y),
        (rx1, reaction_y + heart_size//3),
        (rx1 + heart_size//3, reaction_y),
        (rx1 + heart_size//2, reaction_y - heart_size//2),
    ]
    draw.polygon(heart_points, fill=(255, 0, 0))
    
    # Thumbs up icon
    rx2 = reaction_start_x + reaction_spacing
    draw.ellipse([rx2 - circle_size//2, reaction_y - circle_size//2, 
                  rx2 + circle_size//2, reaction_y + circle_size//2],
                 fill=(180, 180, 180))
    
    # Thumbs down icon
    rx3 = reaction_start_x + reaction_spacing * 2
    draw.ellipse([rx3 - circle_size//2, reaction_y - circle_size//2, 
                  rx3 + circle_size//2, reaction_y + circle_size//2],
                 fill=(180, 180, 180))
    
    # HA HA text icon
    rx4 = reaction_start_x + reaction_spacing * 3
    draw.ellipse([rx4 - circle_size//2, reaction_y - circle_size//2, 
                  rx4 + circle_size//2, reaction_y + circle_size//2],
                 fill=(180, 180, 180))
    haha_font = get_font(10)
    haha_bbox = draw.textbbox((0, 0), "HA HA", font=haha_font)
    haha_w = haha_bbox[2] - haha_bbox[0]
    haha_h = haha_bbox[3] - haha_bbox[1]
    draw.text((rx4 - haha_w//2, reaction_y - haha_h//2 - haha_bbox[1]), 
              "HA HA", fill=(0, 0, 0), font=haha_font)
    
    # Blue !! icon (highlighted)
    rx5 = reaction_start_x + reaction_spacing * 4
    draw.ellipse([rx5 - circle_size//2, reaction_y - circle_size//2, 
                  rx5 + circle_size//2, reaction_y + circle_size//2],
                 fill=(0, 122, 255))  # iOS blue
    exclam_font = get_font(11)
    exclam_bbox = draw.textbbox((0, 0), "!!", font=exclam_font)
    exclam_w = exclam_bbox[2] - exclam_bbox[0]
    exclam_h = exclam_bbox[3] - exclam_bbox[1]
    draw.text((rx5 - exclam_w//2, reaction_y - exclam_h//2 - exclam_bbox[1]), 
              "!!", fill=(255, 255, 255), font=exclam_font)
    
    # Question mark icon
    rx6 = reaction_start_x + reaction_spacing * 5
    draw.ellipse([rx6 - circle_size//2, reaction_y - circle_size//2, 
                  rx6 + circle_size//2, reaction_y + circle_size//2],
                 fill=(180, 180, 180))
    q_font = get_font(14)
    q_bbox = draw.textbbox((0, 0), "?", font=q_font)
    q_w = q_bbox[2] - q_bbox[0]
    q_h = q_bbox[3] - q_bbox[1]
    draw.text((rx6 - q_w//2, reaction_y - q_h//2 - q_bbox[1]), 
              "?", fill=(0, 0, 0), font=q_font)
    
    # Draw context menu below message
    menu_y = bubble_y + bubble_height + 12
    menu_width = 180
    menu_height = 130
    menu_x = bubble_x + 15
    menu_radius = 10
    
    # Draw rounded rectangle for menu
    draw_rounded_rectangle(
        draw,
        [menu_x, menu_y, menu_x + menu_width, menu_y + menu_height],
        menu_radius,
        bubble_rgb
    )
    
    # Draw menu items with icons
    menu_font = get_font(17)
    menu_items = [
        ("Reply", 12),
        ("Copy", 12),
        ("Translate", 12),
        ("More...", 12)
    ]
    menu_item_height = 32
    icon_size = 20
    
    for i, (item_text, icon_offset) in enumerate(menu_items):
        item_y = menu_y + (i * menu_item_height) + 8
        
        # Draw icon (simplified as small shapes)
        icon_x = menu_x + icon_offset
        icon_y = item_y + 2
        
        if item_text == "Reply":
            # Curved arrow pointing left
            arrow_points = [
                (icon_x + icon_size//2, icon_y),
                (icon_x, icon_y + icon_size//4),
                (icon_x + icon_size//4, icon_y + icon_size//2),
                (icon_x + icon_size//2, icon_y + icon_size//4),
            ]
            draw.polygon(arrow_points, fill=(0, 0, 0))
        elif item_text == "Copy":
            # Two overlapping rectangles
            draw.rectangle([icon_x, icon_y, icon_x + icon_size//2, icon_y + icon_size//2], 
                          outline=(0, 0, 0), width=2)
            draw.rectangle([icon_x + icon_size//4, icon_y + icon_size//4, 
                          icon_x + icon_size//2 + icon_size//4, icon_y + icon_size//2 + icon_size//4], 
                          outline=(0, 0, 0), width=2)
        elif item_text == "Translate":
            # A with speech bubble
            draw.text((icon_x, icon_y), "A", fill=(0, 0, 0), font=get_font(14))
            # Small circle for speech bubble
            draw.ellipse([icon_x + 10, icon_y + 2, icon_x + 16, icon_y + 8], fill=(0, 0, 0))
        elif item_text == "More...":
            # Three dots
            for dot in range(3):
                dot_x = icon_x + dot * 6
                draw.ellipse([dot_x, icon_y + icon_size//2, dot_x + 4, icon_y + icon_size//2 + 4], 
                           fill=(0, 0, 0))
        
        # Draw menu item text
        text_x = menu_x + 40
        draw.text((text_x, item_y), item_text, fill=(0, 0, 0), font=menu_font)
    
    return img


def create_breaking_news_card_background(width: int, height: int, bg_color: str, banner_color: str, card_color: str) -> Image.Image:
    """
    Create a Breaking News style background with red banner and white card overlay.
    Similar to professional news graphics.
    
    Args:
        width: Image width in pixels
        height: Image height in pixels
        bg_color: Hex color for background
        banner_color: Hex color for banner
        card_color: Hex color for content card
        
    Returns:
        PIL Image with breaking news card style background
    """
    def hex_to_rgb(hex_color):
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    # Create dark background
    img = Image.new('RGB', (width, height), hex_to_rgb(bg_color))
    draw = ImageDraw.Draw(img)
    
    # Banner settings
    banner_text = "BREAKING NEWS"
    banner_font_size = 46
    banner_padding_x = 30
    banner_padding_y = 12
    banner_y_position = int(height * 0.22)  # Position above the card
    
    # Load font for banner
    banner_font = get_font(banner_font_size)
    
    # Measure banner text
    bbox = draw.textbbox((0, 0), banner_text, font=banner_font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    # Calculate banner rectangle
    banner_width = text_width + (banner_padding_x * 2)
    banner_height = text_height + (banner_padding_y * 2)
    banner_x = int(width * 0.08)  # Left aligned with card
    
    # Draw white card (starts below banner, covers bottom portion)
    card_top = banner_y_position + banner_height - 5  # Slight overlap
    card_margin = int(width * 0.05)
    
    # Card with angled bottom-right corner (decorative notch)
    notch_size = 70
    card_points = [
        (card_margin, card_top),  # Top left
        (width - card_margin, card_top),  # Top right
        (width - card_margin, height - card_margin - notch_size),  # Before notch
        (width - card_margin - notch_size, height - card_margin),  # Notch corner
        (card_margin, height - card_margin),  # Bottom left
    ]
    draw.polygon(card_points, fill=hex_to_rgb(card_color))
    
    # Draw red banner rectangle (on top of card edge)
    draw.rectangle(
        [banner_x, banner_y_position, banner_x + banner_width, banner_y_position + banner_height],
        fill=hex_to_rgb(banner_color)
    )
    
    # Draw banner text
    text_x = banner_x + banner_padding_x
    text_y = banner_y_position + banner_padding_y - bbox[1]
    draw.text((text_x, text_y), banner_text, fill=(255, 255, 255), font=banner_font)
    
    # Add subtle decorative elements
    # Small arrow indicator in bottom right
    arrow_x = width - card_margin - notch_size - 30
    arrow_y = height - card_margin - 50
    arrow_size = 20
    draw.polygon([
        (arrow_x, arrow_y),
        (arrow_x + arrow_size, arrow_y + arrow_size // 2),
        (arrow_x, arrow_y + arrow_size)
    ], fill=hex_to_rgb(banner_color))
    
    return img


def add_letter_spacing(text: str, spacing_ratio: float, font_size: int) -> str:
    """
    Add extra spacing between letters by inserting thin spaces.
    
    Args:
        text: Original text
        spacing_ratio: Extra spacing as ratio of font size
        font_size: Current font size
        
    Returns:
        Text with spacing characters inserted
    """
    if spacing_ratio <= 0:
        return text
    
    # For each line, add spacing between characters (but not spaces)
    lines = text.split('\n')
    spaced_lines = []
    
    for line in lines:
        # Add a thin space between each character
        spaced_line = '\u200A'.join(line)  # Hair space (thinnest Unicode space)
        spaced_lines.append(spaced_line)
    
    return '\n'.join(spaced_lines)


def draw_text_with_letter_spacing(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    font_size: int,
    center_x: float,
    start_y: float,
    fill: str,
    stroke_width: int,
    letter_spacing: float,
    line_spacing_ratio: float,
    stroke_fill: Optional[str] = None,
    text_align: str = "center",
    left_padding: float = 0
):
    """
    Draw multiline text with custom letter spacing and alignment.
    
    Args:
        draw: ImageDraw object
        text: Multiline text to draw
        font: Font to use
        font_size: Font size in pixels
        center_x: X coordinate for center alignment
        start_y: Y coordinate for top of text block
        fill: Text fill color
        stroke_width: Stroke width in pixels
        stroke_fill: Stroke color
        letter_spacing: Extra spacing between letters in pixels
        line_spacing_ratio: Line height as ratio of font size
        text_align: "center" or "left"
        left_padding: Left padding for left-aligned text
    """
    lines = text.split('\n')
    line_height = font_size * line_spacing_ratio
    
    for i, line in enumerate(lines):
        y = start_y + (i * line_height)
        
        # For Instagram Classic, letter spacing is minimal (-2%)
        # Use PIL's built-in rendering for clean text without character-by-character issues
        bbox = draw.textbbox((0, 0), line, font=font)
        line_width = bbox[2] - bbox[0]
        
        if text_align == "left":
            x = left_padding
        else:
            x = center_x - (line_width / 2)
        
        draw.text(
            (x, y),
            line,
            fill=fill,
            font=font,
            stroke_width=stroke_width,
            stroke_fill=stroke_fill if stroke_fill is not None else "#000000"
        )


def generate_hook_image(
    headline: str,
    output_path: Path,
    create_psd: bool = False,
    background_path: Optional[Path] = None,
    template: Optional['TemplateConfig'] = None,
    use_emoji: bool = False
) -> Tuple[bool, str]:
    """
    Generate a hook image with background (image or gradient) and bold text.
    
    Uses the consolidated formatting from ig_classic_formatter.py for all
    text processing. This function only handles image creation and rendering.
    
    Args:
        headline: The headline text
        output_path: Path to save the PNG file
        create_psd: Whether to also create a PSD file
        background_path: Optional path to a background image
        template: Optional TemplateConfig for styling (if None, uses default red diagonal)
        use_emoji: Whether to render emojis in the text
        
    Returns:
        Tuple of (success, message)
    """
    try:
        # Get text color from template or use default
        text_color = template.text_color if template else config.TEXT_COLOR
        
        # For messaging template, prepend the Glossier-style text (only if we have text)
        if template and template.background_type == "messaging" and headline.strip():
            headline = f"Have you shopped Glossier's sale yet? - {headline}"
        
        # Skip text rendering if headline is empty (just use background image)
        skip_text = not headline.strip()
        
        if not skip_text:
            # For messaging template, calculate bubble dimensions first to determine max width and height
            if template and template.background_type == "messaging":
                # Bubble extends from ~4% to ~88% horizontally, and ~17% to ~44% vertically
                # The bubble ends BEFORE the menu (Reply, Copy, etc.) starts
                bubble_left = int(config.IMAGE_WIDTH * 0.04)
                bubble_right = int(config.IMAGE_WIDTH * 0.88)
                bubble_top = int(config.IMAGE_HEIGHT * 0.17)   # Decreased top padding by 1%
                bubble_bottom = int(config.IMAGE_HEIGHT * 0.44)
                
                text_padding_x = 20  # Horizontal padding inside bubble
                text_padding_y = 15  # Vertical padding inside bubble
                messaging_max_width = bubble_right - bubble_left - (text_padding_x * 2)
                messaging_max_height = bubble_bottom - bubble_top - (text_padding_y * 2)
                
                # Start with initial formatting to get text structure
                result = format_headline_complete(headline)
                from .ig_classic_formatter import format_text_simple
                
                # Helper function to get messaging font (Segoe UI Semibold)
                def get_messaging_font(size):
                    try:
                        return ImageFont.truetype("C:/Windows/Fonts/seguisb.ttf", size=size)
                    except:
                        try:
                            return ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", size=size)
                        except:
                            return get_font(size)
                
                # Auto-calculate font size to fill the bubble (not too big, not too small)
                # Start with a medium font size and find the best fit
                min_font_size = 18  # Minimum readable size
                max_font_size = 45  # Maximum size
                
                # Binary search for optimal font size
                low_font = min_font_size
                high_font = max_font_size
                best_font_size = min_font_size
                best_formatted_text = ""
                
                while low_font <= high_font:
                    mid_font = (low_font + high_font) // 2
                    
                    # Format text with current font size
                    test_formatted = format_text_simple(headline, messaging_max_width, mid_font)
                    
                    # Measure text height using the same font we'll render with (Segoe UI Semibold)
                    dummy_img = Image.new('RGB', (1, 1))
                    dummy_draw = ImageDraw.Draw(dummy_img)
                    test_font = get_messaging_font(mid_font)
                    spacing = int(mid_font * (config.IG_CLASSIC_LINE_HEIGHT - 1))
                    test_bbox = dummy_draw.multiline_textbbox(
                        (0, 0), test_formatted, font=test_font, 
                        spacing=spacing, align='left'
                    )
                    test_height = test_bbox[3] - test_bbox[1]
                    
                    # Check if it fits within the bubble (use 95% to leave small margin)
                    if test_height <= messaging_max_height * 0.95:
                        # It fits, save this and try larger
                        best_font_size = mid_font
                        best_formatted_text = test_formatted
                        low_font = mid_font + 1
                    else:
                        # Too big, try smaller
                        high_font = mid_font - 1
                
                # Use the best fit
                if best_formatted_text:
                    formatted_text = best_formatted_text
                    font_size = best_font_size
                else:
                    # Fallback
                    font_size = min_font_size
                    formatted_text = format_text_simple(headline, messaging_max_width, font_size)
                settings = result.settings
                settings.max_text_width = messaging_max_width
            else:
                # Use consolidated formatting pipeline (single source of truth)
                result = format_headline_complete(headline)
                formatted_text = result.formatted_text
                font_size = result.font_size
                # Apply template font_size_multiplier if available
                if template and hasattr(template, 'font_size_multiplier'):
                    font_size = int(font_size * template.font_size_multiplier)
                settings = result.settings
        else:
            # Dummy values when skipping text - create a proper settings object
            from .ig_classic_formatter import TextLayoutSettings
            formatted_text = ""
            font_size = 50
            settings = TextLayoutSettings(
                padding_left=0,
                padding_right=0,
                max_text_width=0,
                max_text_height=0,
                chars_per_line=0,
                target_rows=None,
                y_center_ratio=0.5,
                is_long=False
            )
        
        # IG Classic settings
        line_spacing_ratio = config.IG_CLASSIC_LINE_HEIGHT
        
        # Create background
        if background_path and background_path.exists():
            try:
                img = Image.open(background_path).convert('RGB')
                img = img.resize((config.IMAGE_WIDTH, config.IMAGE_HEIGHT), Image.Resampling.LANCZOS)
                # Don't add overlay for messaging template - use image as-is
                if not (template and template.background_type == "messaging"):
                    overlay = Image.new('RGBA', img.size, (0, 0, 0, 100))
                    img = Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')
            except Exception as e:
                print(f"[WARNING] Failed to load background {background_path}: {e}")
                img = _create_template_background(template)
        else:
            img = _create_template_background(template)
            
        # Only render text if we have text to render
        if not skip_text:
            draw = ImageDraw.Draw(img)
            
            # Load font - use system font for messaging template (semibold for heavier weight)
            if template and template.background_type == "messaging":
                # Try to load Segoe UI Semibold directly for heavier weight matching "Reply" text
                try:
                    # First try Segoe UI Semibold
                    font = ImageFont.truetype("C:/Windows/Fonts/seguisb.ttf", size=font_size)
                except:
                    try:
                        # Then try Segoe UI Bold
                        font = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", size=font_size)
                    except:
                        try:
                            # Then try regular Segoe UI
                            font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", size=font_size)
                        except:
                            # Fallback to default font
                            font = get_font(font_size)
            else:
                font = get_font(font_size)
            
            # Calculate spacing
            spacing = int(font_size * (line_spacing_ratio - 1))
            
            # Get text alignment from template
            text_align = template.text_align if template else "center"
            
            # Get text bounding box for positioning
            align_mode = 'left' if text_align == "left" else 'center'
            bbox = draw.multiline_textbbox((0, 0), formatted_text, font=font, spacing=spacing, align=align_mode)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            
            # For messaging template, position text inside the bubble
            if template and template.background_type == "messaging":
                # Position text to match the actual bubble location in phone template (1).png
                # Bubble extends from ~4% to ~88% horizontally, and ~17% to ~44% vertically
                bubble_left = int(config.IMAGE_WIDTH * 0.04)
                bubble_right = int(config.IMAGE_WIDTH * 0.88)
                bubble_top = int(config.IMAGE_HEIGHT * 0.17)   # Decreased top padding by 1%
                bubble_bottom = int(config.IMAGE_HEIGHT * 0.44)
                
                # Minimal padding to maximize text space
                text_padding_x = 15  # Reduced horizontal padding (was 25)
                text_padding_y = 15  # Vertical padding
                
                # Position text starting from top-left of bubble content area
                text_start_y = bubble_top + text_padding_y
                draw_y = text_start_y - bbox[1]
                left_padding = bubble_left + text_padding_x
            else:
                # Use fixed vertical center from settings (0.50 for exact match)
                y_center = config.IMAGE_HEIGHT * settings.y_center_ratio
                
                # Place text block center at calculated height
                target_bbox_y = y_center - (text_height / 2)
                
                # Offset for draw position
                draw_y = target_bbox_y - bbox[1]
                left_padding = settings.padding_left
            
            # Letter spacing
            letter_spacing_px = font_size * config.IG_CLASSIC_LETTER_SPACING
            
            # Render text
            if use_emoji:
                try:
                    from pilmoji import Pilmoji
                    with Pilmoji(img) as pilmoji:
                        lines = formatted_text.split('\n')
                        line_height = font_size * line_spacing_ratio
                        for i, line in enumerate(lines):
                            line_bbox = draw.textbbox((0, 0), line, font=font)
                            line_width = line_bbox[2] - line_bbox[0]
                            if text_align == "left":
                                x = int(left_padding)
                            else:
                                x = int((config.IMAGE_WIDTH - line_width) / 2)
                            y = int(draw_y + bbox[1] + (i * line_height))
                            pilmoji.text((x, y), line, font=font, fill=text_color)
                except ImportError:
                    print("[WARNING] pilmoji not installed, emojis may not render correctly")
                    draw_text_with_letter_spacing(
                        draw=draw,
                        text=formatted_text,
                        font=font,
                        font_size=font_size,
                        center_x=config.IMAGE_WIDTH / 2,
                        start_y=draw_y + bbox[1],
                        fill=text_color,
                        stroke_width=0,
                        stroke_fill="#000000",
                        letter_spacing=letter_spacing_px,
                        line_spacing_ratio=line_spacing_ratio,
                        text_align=text_align,
                        left_padding=left_padding
                    )
            else:
                draw_text_with_letter_spacing(
                    draw=draw,
                    text=formatted_text,
                    font=font,
                    font_size=font_size,
                    center_x=config.IMAGE_WIDTH / 2,
                    start_y=draw_y + bbox[1],
                    fill=text_color,
                    stroke_width=0,
                    stroke_fill=None,
                    letter_spacing=letter_spacing_px,
                    line_spacing_ratio=line_spacing_ratio,
                    text_align=text_align,
                    left_padding=left_padding
                )
        
        # Ensure output directory exists
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
        except (OSError, PermissionError) as e:
            return False, f"Failed to create output directory: {e}"
        
        # Save as PNG
        img.save(str(output_path), 'PNG')
        
        # Optionally create PSD
        if create_psd:
            psd_path = output_path.with_suffix('.psd')
            create_psd_from_image(img, psd_path)
        
        return True, f"Image saved: {output_path}"
        
    except Exception as e:
        import traceback
        return False, f"Error generating image: {e}\n{traceback.format_exc()}"


def _create_template_background(template: Optional['TemplateConfig'] = None) -> Image.Image:
    """
    Create background image based on template configuration.
    
    Args:
        template: TemplateConfig object, or None for default
        
    Returns:
        PIL Image with appropriate background
    """
    width = config.IMAGE_WIDTH
    height = config.IMAGE_HEIGHT
    
    if template is None:
        # Default: red diagonal background
        return create_corner_diagonal_background(
            width, height,
            config.GRADIENT_START,
            config.GRADIENT_END
        )
    
    bg_type = template.background_type
    colors = template.background_colors
    
    if bg_type == "diagonal":
        # Red diagonal with corners
        return create_corner_diagonal_background(
            width, height,
            colors[0] if len(colors) > 0 else "#FF0000",
            colors[1] if len(colors) > 1 else "#d80100"
        )
    elif bg_type == "gradient":
        # Vertical gradient with multiple stops
        return create_vertical_gradient_background(width, height, colors)
    elif bg_type == "solid":
        # Solid color
        return create_solid_background(width, height, colors[0] if colors else "#000000")
    elif bg_type == "breaking_news":
        # Breaking news style with red banner
        return create_breaking_news_background(
            width, height,
            colors[0] if len(colors) > 0 else "#0A0A0A",  # BG color
            colors[1] if len(colors) > 1 else "#E60000"   # Banner color
        )
    elif bg_type == "breaking_news_card":
        # Breaking news with white card overlay
        return create_breaking_news_card_background(
            width, height,
            colors[0] if len(colors) > 0 else "#1A1A1A",  # BG color
            colors[1] if len(colors) > 1 else "#E60000",  # Banner color
            colors[2] if len(colors) > 2 else "#FFFFFF"   # Card color
        )
    elif bg_type == "messaging":
        # Messaging interface style
        return create_messaging_background(
            width, height,
            colors[0] if len(colors) > 0 else "#E5E5E5",  # BG color
            colors[1] if len(colors) > 1 else "#FFFFFF"   # Bubble color
        )
    else:
        # Fallback to default
        return create_corner_diagonal_background(
            width, height,
            config.GRADIENT_START,
            config.GRADIENT_END
        )


def create_psd_from_image(img: Image.Image, psd_path: Path) -> bool:
    """
    Create a PSD file from a Pillow image using PhotoshopAPI.
    
    Args:
        img: Pillow Image object
        psd_path: Path to save the PSD file
        
    Returns:
        True if successful, False otherwise
    """
    try:
        import numpy as np
        
        # Try to import PhotoshopAPI
        try:
            import photoshopapi as psapi
        except ImportError:
            print("[WARNING] PhotoshopAPI not installed, skipping PSD creation")
            return False
        
        # Convert to numpy array
        img_array = np.array(img)
        
        # Create channel map
        channel_map = {
            psapi.enum.ChannelID.Red: img_array[:, :, 0].flatten(),
            psapi.enum.ChannelID.Green: img_array[:, :, 1].flatten(),
            psapi.enum.ChannelID.Blue: img_array[:, :, 2].flatten()
        }
        
        # Create LayeredFile
        document = psapi.LayeredFile_8bit(
            psapi.enum.ColorMode.rgb,
            config.IMAGE_WIDTH,
            config.IMAGE_HEIGHT
        )
        
        # Create ImageLayer
        text_layer = psapi.ImageLayer_8bit(
            channel_map,
            "Hook Text",
            width=config.IMAGE_WIDTH,
            height=config.IMAGE_HEIGHT
        )
        document.add_layer(text_layer)
        
        # Save PSD
        document.write(str(psd_path))
        
        return True
        
    except Exception as e:
        print(f"[WARNING] Failed to create PSD: {e}")
        return False


def _process_headline_task(args):
    """Worker function for batch image generation."""
    i, hook_data, output_dir, create_psd, background_path, template_id = args
    
    # Extract metadata for filename
    if isinstance(hook_data, dict):
        headline = hook_data.get('headline', '')
        rb = hook_data.get('ragebait_level', '3')
        htype = hook_data.get('type', 'unique')
        hook_idx = hook_data.get('hook_index', i)
        
        # Construction: rb{level}_{type}_{id_or_index}
        if htype == 'proven' and hook_data.get('source_ad_id'):
            # For proven hooks, use the source ad ID as requested
            source_id = hook_data.get('source_ad_id')
            base_name = f"rb{rb}_proven_{source_id}"
        else:
            # For unique or proven without source_id, use index
            base_name = f"rb{rb}_{htype}_{hook_idx:03d}"
    else:
        # Backward compatibility for simple strings
        headline = hook_data
        base_name = f"hook_{i:03d}"
    
    # If template_id is provided, include it in filename to avoid overwrites
    if template_id is not None:
        filename = f"{base_name}_temp{template_id}.png"
    else:
        filename = f"{base_name}.png"
        
    output_path = output_dir / filename
    
    # Get template object if ID provided
    template = None
    if template_id is not None:
        from .templates import get_template
        template = get_template(template_id)
    
    success, message = generate_hook_image(headline, output_path, create_psd, background_path, template=template)
    
    if success:
        print(f"  [{i}] Generated: {filename}")
    else:
        print(f"  [{i}] FAILED: {message}")
        
    return {
        'index': i,
        'headline': headline,
        'success': success,
        'path': str(output_path) if success else None,
        'message': message,
        'template_id': template_id,
        'filename': filename
    }


def batch_generate_images(
    headlines: list,
    output_dir: Path,
    create_psd: bool = False,
    background_path: Optional[Path] = None,
    template_ids: Optional[List[int]] = None
) -> list:
    """
    Generate images for multiple headlines in parallel.
    
    Args:
        headlines: List of headline strings OR List of hook dictionaries with metadata
        output_dir: Directory to save images
        create_psd: Whether to create PSD files
        background_path: Path to background image
        template_ids: Optional list of template IDs to use for EACH headline
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Prepare arguments for multiprocessing
    process_args = []
    
    if template_ids:
        # Generate EACH headline for EACH template
        for i, hook_data in enumerate(headlines, 1):
            for tid in template_ids:
                process_args.append((i, hook_data, output_dir, create_psd, background_path, tid))
    else:
        # Standard behavior: one image per headline (uses logic in generate_hook_image)
        for i, hook_data in enumerate(headlines, 1):
            process_args.append((i, hook_data, output_dir, create_psd, background_path, None))
    
    # Run multiprocessed (PIL image generation is CPU intensive)
    results = run_multiprocessed(_process_headline_task, process_args)
    
    # Filter out None values
    results = [r for r in results if r is not None]
    
    return results

