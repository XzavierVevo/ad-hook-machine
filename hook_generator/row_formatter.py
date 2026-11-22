"""
DEPRECATED: Legacy row formatting module.

This module is kept for backwards compatibility only.
All text formatting should use ig_classic_formatter.py instead.

The consolidated formatting pipeline is in ig_classic_formatter.py:
- format_headline_complete() - Full formatting pipeline (RECOMMENDED)
- format_ig_classic_text() - Text line breaking
- format_text_casing() - Case normalization
- prepare_text_for_formatting() - Paragraph splitting for long content
"""

import warnings
import re
from typing import Optional
from . import config

# Import new functions for forwarding
from .ig_classic_formatter import (
    format_headline_complete,
    format_text_casing as _new_format_text_casing
)


def format_text_casing(text: str) -> str:
    """
    DEPRECATED: Use ig_classic_formatter.format_text_casing() instead.
    
    Format text to use Sentence Case if it's all uppercase.
    Mixed case text is left as is.
    """
    warnings.warn(
        "row_formatter.format_text_casing() is deprecated. "
        "Use ig_classic_formatter.format_text_casing() instead.",
        DeprecationWarning,
        stacklevel=2
    )
    return _new_format_text_casing(text)


def format_headline_into_rows(headline: str, max_rows: Optional[int] = None) -> str:
    """
    DEPRECATED: Use ig_classic_formatter.format_ig_classic_text() instead.
    
    Format headline into optimal rows based on word count.
    """
    warnings.warn(
        "row_formatter.format_headline_into_rows() is deprecated. "
        "Use ig_classic_formatter.format_ig_classic_text() instead.",
        DeprecationWarning,
        stacklevel=2
    )
    
    if max_rows is None:
        max_rows = getattr(config, 'MAX_ROWS', 6)
    
    # Forward to new implementation
    # Use format_headline_complete instead
    formatted = format_headline_complete(headline)
    return formatted.formatted_text


def get_row_count(headline: str) -> int:
    """
    DEPRECATED: Get the number of rows a headline will take.
    
    Use ig_classic_formatter.format_ig_classic_text() and count lines instead.
    """
    warnings.warn(
        "row_formatter.get_row_count() is deprecated. "
        "Use ig_classic_formatter.format_ig_classic_text() and count lines instead.",
        DeprecationWarning,
        stacklevel=2
    )
    formatted = format_headline_into_rows(headline)
    return len(formatted.split('\n'))


# ============================================================================
# Legacy constants and functions below (kept for backwards compatibility)
# ============================================================================

# Special characters that should trigger a line break after them
LINE_BREAK_CHARACTERS = [
    ' - ',      # Dash with spaces (most common in ad copy)
    ' – ',      # En dash with spaces
    ' — ',      # Em dash with spaces
    '...',      # Ellipsis
    '…',        # Unicode ellipsis
    ', ',       # Comma followed by space (used in lists)
    '; ',       # Semicolon with space
    '? ',       # Question mark with space
    '! ',       # Exclamation mark with space
    ': ',       # Colon with space
    ' | ',      # Pipe with spaces
    ' / ',      # Slash with spaces
    ' • ',      # Bullet point with spaces
]

LINE_BREAK_SUFFIXES = [
    '-',        # Dash at end of word
    '–',        # En dash
    '—',        # Em dash
    ';',        # Semicolon
    '?',        # Question mark
    '!',        # Exclamation mark
    ':',        # Colon
    '.',        # Period
    ',',        # Comma
]


def split_on_special_characters(headline: str) -> list:
    """
    DEPRECATED: Split headline on special characters.
    
    The ig_classic_formatter handles this internally.
    """
    warnings.warn(
        "row_formatter.split_on_special_characters() is deprecated. "
        "Use ig_classic_formatter.format_ig_classic_text() instead.",
        DeprecationWarning,
        stacklevel=2
    )
    
    segments = [headline]
    TEMP_DELIMITER = '|||LINE_BREAK|||'
    
    for char_pattern in LINE_BREAK_CHARACTERS:
        new_segments = []
        for segment in segments:
            parts = segment.split(char_pattern)
            for i, part in enumerate(parts):
                part = part.strip()
                if not part:
                    continue
                if i < len(parts) - 1:
                    char_to_add = char_pattern.strip()
                    if char_pattern == ', ':
                        char_to_add = ','
                    new_segments.append(part + char_to_add)
                else:
                    new_segments.append(part)
        segments = new_segments if new_segments else segments
    
    for suffix_char in LINE_BREAK_SUFFIXES:
        new_segments = []
        for segment in segments:
            pattern = re.escape(suffix_char) + r'(?=\s|$)'
            modified = re.sub(pattern, suffix_char + TEMP_DELIMITER, segment)
            parts = modified.split(TEMP_DELIMITER)
            for part in parts:
                part = part.strip()
                if part:
                    new_segments.append(part)
        segments = new_segments if new_segments else segments
    
    return segments


def format_segment_into_rows(segment: str, max_chars_per_row: int) -> list:
    """
    DEPRECATED: Format a single segment into rows.
    
    Use ig_classic_formatter.format_ig_classic_text() instead.
    """
    warnings.warn(
        "row_formatter.format_segment_into_rows() is deprecated. "
        "Use ig_classic_formatter.format_ig_classic_text() instead.",
        DeprecationWarning,
        stacklevel=2
    )
    
    words = segment.split()
    if not words:
        return []
    
    rows = []
    current_row = []
    current_length = 0
    
    for word in words:
        word_length = len(word)
        space_needed = 1 if current_row else 0
        if current_length + word_length + space_needed > max_chars_per_row and current_row:
            rows.append(' '.join(current_row))
            current_row = [word]
            current_length = word_length
        else:
            current_row.append(word)
            current_length += word_length + space_needed
    
    if current_row:
        rows.append(' '.join(current_row))
    
    return rows
