"""
Test script to generate Breaking News template examples.
Creates sample ad images using the new Breaking News templates.
"""

import sys
from pathlib import Path

# Add hook_generator to path
sys.path.insert(0, str(Path(__file__).parent))

from hook_generator.image_generator import generate_hook_image
from hook_generator.templates import get_template, TEMPLATE_BREAKING_NEWS, TEMPLATE_BREAKING_NEWS_CARD


def main():
    """Generate Breaking News template examples."""
    
    # Create output directory
    output_dir = Path("output/breaking_news_examples")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Test headlines - variety of lengths similar to real ad hooks
    test_hooks = [
        # Short hooks
        "Local painters exposed for charging 3x the going rate",
        "Homeowners furious after discovering this painting trick",
        
        # Medium hooks with paragraph break
        "New law forces painters to reveal their real prices | $299 per room with no hidden fees",
        "Contractors hate this one simple trick | Get your home painted for half the price",
        
        # Longer hooks
        "I caught my painter lying to my face about the cost | Now I use this service and save thousands",
        "Big paint companies don't want you to know this | Local painters offering $350 per room, done in 3 days",
    ]
    
    print("=" * 60)
    print("GENERATING BREAKING NEWS TEMPLATE EXAMPLES")
    print("=" * 60)
    
    # Get templates
    template_dark = get_template(7)  # breaking_news
    template_card = get_template(8)  # breaking_news_card
    
    results = []
    
    # Generate examples for both templates
    for i, hook in enumerate(test_hooks, 1):
        print(f"\n[{i}/{len(test_hooks)}] Processing: {hook[:50]}...")
        
        # Template 7: Dark Breaking News
        output_path_dark = output_dir / f"breaking_news_dark_{i:02d}.png"
        success, msg = generate_hook_image(
            headline=hook,
            output_path=output_path_dark,
            template=template_dark
        )
        if success:
            print(f"  [OK] Dark template: {output_path_dark.name}")
            results.append(str(output_path_dark))
        else:
            print(f"  [FAIL] Dark template failed: {msg}")
        
        # Template 8: Card Breaking News
        output_path_card = output_dir / f"breaking_news_card_{i:02d}.png"
        success, msg = generate_hook_image(
            headline=hook,
            output_path=output_path_card,
            template=template_card
        )
        if success:
            print(f"  [OK] Card template: {output_path_card.name}")
            results.append(str(output_path_card))
        else:
            print(f"  [FAIL] Card template failed: {msg}")
    
    print("\n" + "=" * 60)
    print(f"COMPLETE! Generated {len(results)} images")
    print(f"Output directory: {output_dir.absolute()}")
    print("=" * 60)
    
    # List all generated files
    print("\nGenerated files:")
    for f in sorted(output_dir.glob("*.png")):
        print(f"  - {f.name}")
    
    return results


if __name__ == "__main__":
    main()
