#!/usr/bin/env python3
"""
Quick script to generate example hooks for a residential home painter.
"""

import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from hook_generator import config
from hook_generator import api_keys
from hook_generator.quote_scraper import scrape_quotes, save_quotes
from hook_generator.headline_generator import generate_headlines, save_headlines
from hook_generator.image_generator import batch_generate_images
from hook_generator.competitor_data_puller import get_competitor_analysis
from hook_generator.offer_manager import (
    load_offers_from_file,
    distribute_hooks_across_offers,
    validate_offers
)
from hook_generator.campaign_setup import (
    create_campaign_folder,
    update_campaign_status
)


def generate_painter_hooks() -> bool:
    """Generate 10 example hooks for residential home painter."""
    
    print("=" * 60)
    print("  GENERATING EXAMPLE HOOKS FOR RESIDENTIAL HOME PAINTER")
    print("=" * 60)
    
    # Initialize API keys
    print("\n[INFO] Loading API keys...")
    api_keys.load_api_keys()
    key_status = api_keys.verify_keys()
    
    print("\n[API Status]")
    for key, available in key_status.items():
        status = "[OK]" if available else "[MISSING]"
        print(f"  {status} {key}")
    
    if not key_status.get('OPENAI_API_KEY'):
        print("\n[ERROR] OPENAI_API_KEY is required for quote generation")
        return False
    
    if not key_status.get('ANTHROPIC_API_KEY'):
        print("\n[ERROR] ANTHROPIC_API_KEY is required for headline generation")
        return False
    
    # Initialize clients
    api_keys.initialize_clients()
    
    # Setup
    campaign_name = "example_residential_painter"
    quote_count = 10
    topic = "residential home painting"
    offer_type = config.OFFER_TYPE_SERVICE
    
    # Create campaign folder
    print(f"\n[INFO] Creating campaign folder...")
    campaign_folder = create_campaign_folder(campaign_name, offer_type)
    print(f"[OK] Created: {campaign_folder}")
    
    # Create offers.txt with correct example painting offers
    offers_file = campaign_folder / "offers.txt"
    example_offers = [
        "Fresh Paint in Every Room by Saturday for $350 Each",
        "Professional Interior Painting in 3 Days for $450 per Room",
        "Full Kitchen Cabinet Painting for $2,500",
        "Room Painted and Ready in 48 Hours for $400"
    ]
    
    with open(offers_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(example_offers))
    
    print(f"[OK] Created offers.txt with {len(example_offers)} example offers")
    
    # Load offers
    offers = load_offers_from_file(offers_file)
    is_valid, message = validate_offers(offers)
    
    if not is_valid:
        print(f"[ERROR] {message}")
        return False
    
    print(f"[OK] {message}")
    for i, offer in enumerate(offers, 1):
        print(f"  {i}. {offer}")
    
    # Distribute hooks across offers
    distribution = distribute_hooks_across_offers(quote_count, offers)
    print(f"\n[INFO] Hook distribution:")
    for offer, count in distribution:
        print(f"  - {offer}: {count} hooks")
    
    # =========================================================================
    # STEP 1: Competitor Analysis
    # =========================================================================
    print("\n" + "-" * 60)
    print("  STEP 1: COMPETITOR ANALYSIS")
    print("-" * 60 + "\n")
    
    # Use enhanced competitor analysis with media extraction
    competitor_data = get_competitor_analysis(
        topic=topic, 
        offer_type=offer_type,
        extract_media=True,  # Extract video transcripts and image text
        limit=250  # Pull more ads for comprehensive analysis
    )
    competitor_patterns = competitor_data.get('patterns', [])
    overused_patterns = competitor_data.get('overused_patterns', [])
    phrases_to_avoid = competitor_data.get('phrases_to_avoid', [])
    insights = competitor_data.get('insights', {})
    
    if competitor_patterns:
        print(f"[OK] Found {len(competitor_patterns)} competitor hooks to differentiate from:")
        for i, pattern in enumerate(competitor_patterns[:10], 1):
            print(f"  {i}. {pattern}")
        if len(competitor_patterns) > 10:
            print(f"  ... and {len(competitor_patterns) - 10} more")
        
        if overused_patterns:
            print(f"\n[WARNING] Overused patterns to AVOID: {', '.join(overused_patterns)}")
        
        if phrases_to_avoid:
            print(f"[WARNING] Common phrases to AVOID: {', '.join(phrases_to_avoid[:5])}")
        
        if insights.get('recommendation'):
            print(f"\n[INSIGHT] {insights['recommendation']}")
    else:
        print("[INFO] No competitor data found (will generate without pattern avoidance)")
    
    update_campaign_status(campaign_folder, "competitor_analysis_complete", {
        'competitor_analysis': competitor_data
    })
    
    # =========================================================================
    # STEP 2: Quote Scraping
    # =========================================================================
    print("\n" + "-" * 60)
    print("  STEP 2: QUOTE SCRAPING")
    print("-" * 60 + "\n")
    
    print(f"[INFO] Generating {quote_count} emotional quotes using ChatGPT...")
    
    quotes = scrape_quotes(
        topic=topic,
        num_quotes=quote_count,
        offer_type=offer_type,
        offers=offers
    )
    
    if not quotes:
        print("[ERROR] Failed to generate quotes")
        return False
    
    print(f"[OK] Generated {len(quotes)} quotes")
    
    # Save quotes
    quotes_file = campaign_folder / "quotes" / f"quotes_{datetime.now().strftime('%H%M%S')}.json"
    save_quotes(quotes, quotes_file)
    print(f"[OK] Saved quotes to {quotes_file}")
    
    update_campaign_status(campaign_folder, "quotes_complete", {
        'quotes_count': len(quotes)
    })
    
    # =========================================================================
    # STEP 3: Headline Generation
    # =========================================================================
    print("\n" + "-" * 60)
    print("  STEP 3: HEADLINE GENERATION")
    print("-" * 60 + "\n")
    
    print(f"[INFO] Generating {len(quotes)} headlines using Claude...")
    print("[INFO] Applying competitor pattern avoidance...")
    print("[INFO] Using DIRECT service-based communication (no storytelling)...")
    
    # Calculate offer distribution (reuse the distribution already calculated)
    offer_distribution = distribution
    print(f"[INFO] Offer distribution for headlines:")
    for offer, count in offer_distribution:
        print(f"  - {offer}: {count} headlines")
    
    headlines = generate_headlines(
        num_hooks=len(quotes),
        offers=offers,
        offer_type=offer_type,
        offer_distribution=offer_distribution
    )
    
    if not headlines:
        print("[ERROR] Failed to generate headlines")
        return False
    
    print(f"[OK] Generated {len(headlines)} headlines")
    
    # Preview all headlines
    print("\n[PREVIEW] Generated headlines:")
    for i, h in enumerate(headlines, 1):
        print(f"  {i}. {h.get('headline', 'N/A')}")
    
    # Save headlines
    headlines_file = campaign_folder / "headlines" / f"headlines_{datetime.now().strftime('%H%M%S')}.json"
    save_headlines(headlines, headlines_file)
    print(f"\n[OK] Saved headlines to {headlines_file}")
    
    update_campaign_status(campaign_folder, "headlines_complete", {
        'headlines_count': len(headlines)
    })
    
    # =========================================================================
    # STEP 4: Image Generation
    # =========================================================================
    print("\n" + "-" * 60)
    print("  STEP 4: IMAGE GENERATION")
    print("-" * 60 + "\n")
    
    print(f"[INFO] Generating {len(headlines)} hook images...")
    
    images_dir = campaign_folder / "images"
    headline_texts = [h.get('headline', '') for h in headlines]
    
    results = batch_generate_images(
        headlines=headline_texts,
        output_dir=images_dir,
        create_psd=False
    )
    
    success_count = sum(1 for r in results if r['success'])
    print(f"\n[OK] Generated {success_count}/{len(headlines)} images")
    
    update_campaign_status(campaign_folder, "images_complete", {
        'images_generated': success_count,
        'images_failed': len(headlines) - success_count
    })
    
    update_campaign_status(campaign_folder, "complete")
    
    # =========================================================================
    # COMPLETE
    # =========================================================================
    print("\n" + "=" * 60)
    print("  GENERATION COMPLETE!")
    print("=" * 60)
    print(f"\n[OK] Campaign folder: {campaign_folder}")
    print(f"[OK] Quotes generated: {len(quotes)}")
    print(f"[OK] Headlines generated: {len(headlines)}")
    print(f"[OK] Images generated: {success_count}")
    print(f"\n[INFO] All files saved to: {campaign_folder}")
    print(f"\n[INFO] View images in: {images_dir}")
    
    return True


if __name__ == "__main__":
    success = generate_painter_hooks()
    sys.exit(0 if success else 1)

