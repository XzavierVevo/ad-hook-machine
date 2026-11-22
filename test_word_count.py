#!/usr/bin/env python3
"""
Test image generation with different word counts to verify:
1. Short text (< 30 words) - stays as single paragraph
2. Long text (30+ words) - auto-splits into paragraphs
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from hook_generator.image_generator import generate_hook_image

def test_word_count_variations():
    output_dir = Path("output/word_count_test")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Test 1: Short text (25 words) - should stay as single paragraph
    short_hook = (
        "Stop paying for entire house painting when you only need "
        "two rooms done. $350 per room, finished this week with quality."
    )
    
    # Test 2: Medium text (exactly 30 words) - threshold test
    medium_hook = (
        "Why are most painters still charging by the entire house when "
        "you only need two bedrooms done? Get professional painting for "
        "$350 per room, finished this week."
    )
    
    # Test 3: Long text (45 words) - should auto-split into paragraphs
    long_hook = (
        "Stop overpaying for home painting services in your local area today. "
        "Most contractors charge for the entire house, but you only need a few rooms. "
        "Get professional quality painting for just $350 per room, finished this week "
        "with a satisfaction guarantee."
    )
    
    # Test 4: Very long text (60 words) - should definitely split
    very_long_hook = (
        "Why wait months for contractors who charge thousands for painting your entire house? "
        "You don't need every room painted - just the ones that matter most to you right now. "
        "Our professional painters will transform any room in your home for just $350 per room, "
        "completed this week with premium quality materials and a 100% satisfaction guarantee or your money back."
    )
    
    tests = [
        ("short_25_words", short_hook, 25),
        ("medium_30_words", medium_hook, 30),
        ("long_45_words", long_hook, 45),
        ("very_long_60_words", very_long_hook, 60),
    ]
    
    print("=" * 80)
    print("WORD COUNT TEST - Paragraph Splitting Logic")
    print("=" * 80)
    print("\nRule: Text with 30+ words should auto-split into 2 paragraphs")
    print("      Text with < 30 words stays as single paragraph\n")
    
    for test_name, hook_text, word_count in tests:
        actual_word_count = len(hook_text.split())
        output_path = output_dir / f"hook_{test_name}.png"
        
        print(f"\n[TEST] {test_name.upper()}")
        print(f"  Expected words: {word_count}")
        print(f"  Actual words: {actual_word_count}")
        print(f"  Text: {hook_text[:80]}...")
        print(f"  Expected behavior: {'Split into 2 paragraphs' if actual_word_count >= 30 else 'Single paragraph'}")
        
        success, message = generate_hook_image(hook_text, output_path)
        
        if success:
            print(f"  [OK] Generated: {output_path.name}")
        else:
            print(f"  [FAIL] {message}")
    
    print("\n" + "=" * 80)
    print(f"All images saved to: {output_dir.absolute()}")
    print("=" * 80)
    
    # Print summary with file paths
    print("\nGenerated files:")
    for test_name, _, word_count in tests:
        filename = f"hook_{test_name}.png"
        print(f"  - {filename} ({word_count} words)")


if __name__ == "__main__":
    test_word_count_variations()
