"""
Template definitions for ad image generation.
Each template defines background style, colors, text color, and alignment.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class TemplateConfig:
    """Configuration for an ad image template."""
    id: int
    name: str
    background_type: str  # "solid", "gradient", "diagonal"
    background_colors: List[str]  # Hex colors for background
    text_color: str  # Hex color for text
    text_align: str  # "center" or "left"
    font_size_multiplier: float = 1.0  # 1.0 = default, higher = larger font
    description: str = ""  # Human-readable description
    # Safe zone settings (as ratio of image dimension)
    # Default: Top=40px, Bottom=40px, Left=52px, Right=52px (for 1080x1080 image)
    safe_zone_top: float = 40.0 / 1080.0  # 40px top padding
    safe_zone_bottom: float = 40.0 / 1080.0  # 40px bottom padding
    safe_zone_left: float = 52.0 / 1080.0  # 52px left padding
    safe_zone_right: float = 52.0 / 1080.0  # 52px right padding
    # Row formatting settings
    max_chars_per_row: int = 0  # 0 = use default logic, >0 = override
    max_rows: int = 0  # 0 = use default (6), >0 = override
    line_spacing_ratio: float = 82.0 / 68.0  # Line height 82px / font size 68px = 1.2059


# Template 0: Red Diagonal (existing style)
TEMPLATE_RED_DIAGONAL = TemplateConfig(
    id=0,
    name="red_diagonal",
    background_type="diagonal",
    background_colors=["#FF0000", "#d80100"],  # Bright red corners, dark red center
    text_color="#FFFFFF",
    text_align="center",
    font_size_multiplier=1.0,
    description="Red background with bright diagonal corners"
)

# Template 1: Cool Gradient (Pink → Blue → Cyan)
TEMPLATE_COOL_GRADIENT = TemplateConfig(
    id=1,
    name="cool_gradient",
    background_type="gradient",
    background_colors=["#E91E8C", "#6B5BFF", "#00D4FF"],  # Pink → Blue → Cyan
    text_color="#FFFFFF",
    text_align="center",
    font_size_multiplier=1.0,
    description="Vertical gradient from pink through blue to cyan"
)

# Template 2: Solid Black
TEMPLATE_SOLID_BLACK = TemplateConfig(
    id=2,
    name="solid_black",
    background_type="solid",
    background_colors=["#000000"],
    text_color="#FFFFFF",
    text_align="center",
    font_size_multiplier=1.0,
    description="Pure black background with white text"
)

# Template 3: Warm Gradient (Blue → Purple → Red/Magenta)
TEMPLATE_WARM_GRADIENT = TemplateConfig(
    id=3,
    name="warm_gradient",
    background_type="gradient",
    background_colors=["#3B82F6", "#8B5CF6", "#EC4899"],  # Blue → Purple → Magenta
    text_color="#FFFFFF",
    text_align="center",
    font_size_multiplier=1.0,
    description="Vertical gradient from blue through purple to magenta"
)

# Template 4: Solid Yellow (left-aligned, black text, large font filling frame)
# Matches the ClickBank-style reference with text filling most of the image
TEMPLATE_SOLID_YELLOW = TemplateConfig(
    id=4,
    name="solid_yellow",
    background_type="solid",
    background_colors=["#FFE500"],
    text_color="#000000",
    text_align="left",
    font_size_multiplier=2.2,  # Much larger font to fill the frame
    description="Bright yellow background with left-aligned black text",
    # Minimal safe zones to let text fill the frame
    safe_zone_top=0.12,
    safe_zone_bottom=0.12,
    safe_zone_left=0.06,
    safe_zone_right=0.06,
    # Row formatting for large text
    max_chars_per_row=18,  # Shorter rows = bigger text per line
    max_rows=8,  # Allow more rows
    line_spacing_ratio=1.15
)

# Template 5: Solid White (inverse of black)
TEMPLATE_SOLID_WHITE = TemplateConfig(
    id=5,
    name="solid_white",
    background_type="solid",
    background_colors=["#FFFFFF"],
    text_color="#000000",
    text_align="center",
    font_size_multiplier=1.0,
    description="Pure white background with black text"
)

# Template 6: Orange Gradient (Orange → Red → Pink)
TEMPLATE_ORANGE_GRADIENT = TemplateConfig(
    id=6,
    name="orange_gradient",
    background_type="gradient",
    background_colors=["#FF6B35", "#FF4757", "#FF6B9D"],  # Orange → Red → Pink
    text_color="#FFFFFF",
    text_align="center",
    font_size_multiplier=1.0,
    description="Vertical gradient from orange through red to pink"
)

# Template 7: Breaking News (Dark background with red banner)
TEMPLATE_BREAKING_NEWS = TemplateConfig(
    id=7,
    name="breaking_news",
    background_type="breaking_news",  # Special type - handled in image_generator
    background_colors=["#0A0A0A", "#E60000"],  # Dark BG, Red banner
    text_color="#FFFFFF",
    text_align="center",
    font_size_multiplier=0.85,  # Slightly smaller to fit below banner
    description="Breaking news style with red banner at top",
    safe_zone_top=0.25,  # Extra top padding for banner
    safe_zone_bottom=0.08,
    safe_zone_left=0.07,
    safe_zone_right=0.07,
    line_spacing_ratio=1.12
)

# Template 8: Breaking News White Card (News style with white content card)
TEMPLATE_BREAKING_NEWS_CARD = TemplateConfig(
    id=8,
    name="breaking_news_card",
    background_type="breaking_news_card",  # Special type - handled in image_generator
    background_colors=["#1A1A1A", "#E60000", "#FFFFFF"],  # Dark BG, Red banner, White card
    text_color="#000000",  # Black text on white card
    text_align="center",
    font_size_multiplier=0.80,
    description="Breaking news with white card overlay for headline",
    safe_zone_top=0.38,  # Text starts in the white card area
    safe_zone_bottom=0.12,
    safe_zone_left=0.08,
    safe_zone_right=0.08,
    line_spacing_ratio=1.10
)

# Template 9: Messaging Interface (Mobile messaging style)
TEMPLATE_MESSAGING = TemplateConfig(
    id=9,
    name="messaging",
    background_type="messaging",  # Special type - handled in image_generator
    background_colors=["#E5E5E5", "#FFFFFF"],  # Light grey BG, White message bubble
    text_color="#1d1d1d",  # Dark grey to match "Reply" text color
    text_align="left",
    font_size_multiplier=0.30,  # Much smaller font to fit text in message bubble (30% of normal size)
    description="Mobile messaging interface style with message bubble",
    safe_zone_top=0.18,  # Space for reactions and message bubble positioning
    safe_zone_bottom=0.22,  # Space for context menu
    safe_zone_left=0.06,
    safe_zone_right=0.06,
    line_spacing_ratio=1.20,  # Tighter spacing for more text
    max_chars_per_row=50  # Allow longer lines for messaging style
)


# Registry of all templates
TEMPLATES: List[TemplateConfig] = [
    TEMPLATE_RED_DIAGONAL,
    TEMPLATE_COOL_GRADIENT,
    TEMPLATE_SOLID_BLACK,
    TEMPLATE_WARM_GRADIENT,
    TEMPLATE_SOLID_YELLOW,
    TEMPLATE_SOLID_WHITE,
    TEMPLATE_ORANGE_GRADIENT,
    TEMPLATE_BREAKING_NEWS,
    TEMPLATE_BREAKING_NEWS_CARD,
    TEMPLATE_MESSAGING,
]


def get_template(template_id: int) -> Optional[TemplateConfig]:
    """Get a template by its ID."""
    for template in TEMPLATES:
        if template.id == template_id:
            return template
    return None


def get_template_by_name(name: str) -> Optional[TemplateConfig]:
    """Get a template by its name."""
    for template in TEMPLATES:
        if template.name == name:
            return template
    return None


def get_all_templates() -> List[TemplateConfig]:
    """Get all available templates."""
    return TEMPLATES.copy()


def list_templates() -> str:
    """Return a formatted string listing all templates."""
    lines = ["Available Templates:", "=" * 40]
    for t in TEMPLATES:
        lines.append(f"  {t.id}: {t.name}")
        lines.append(f"      {t.description}")
        lines.append(f"      Background: {t.background_type}, Text: {t.text_align}")
        lines.append("")
    return "\n".join(lines)
