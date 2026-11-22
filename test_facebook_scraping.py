#!/usr/bin/env python3
"""
Facebook Ad Library Browser Scraping Test

Scrapes competitor ads, extracts hooks and offers using Claude Haiku,
and displays/saves results. Continues scraping until target number of
ads WITH VALID OFFERS are found.

Usage:
    # Auto-generate keywords with Claude Sonnet
    python test_facebook_scraping.py --search "exterior painting" --hooks 50

    # Manual keywords  
    python test_facebook_scraping.py --search "exterior painting" --positive "paint,painting" --negative "jobs,cleaning,car,commercial,employment" --hooks 50

    # Show browser window during scraping
    python test_facebook_scraping.py --search "hvac service" --hooks 25 --no-headless
"""

import sys
import argparse
import asyncio
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from hook_generator.browser_scraper import scrape_ads_browser
from hook_generator import api_keys


def format_ad_for_output(ad: dict) -> dict:
    """
    Format a scraped ad with Haiku analysis into clean output format.
    
    Args:
        ad: Ad dictionary from browser scraper (already analyzed by Haiku)
        
    Returns:
        Formatted dictionary for display/JSON output
    """
    # Extract page name
    page_name = ad.get('page_name', 'Unknown')
    page_name = page_name.replace('\u200b', '').replace('\u200c', '').replace('\u200d', '').strip()
    if len(page_name) > 100:
        page_name = page_name[:100] + "..."
    
    # Get body text
    bodies = ad.get('ad_creative_bodies', [])
    body_text = bodies[0] if bodies else ""
    body_text = body_text.replace('\u200b', '').replace('\u200c', '').replace('\u200d', '').strip()
    
    # Get Haiku analysis (always present since Haiku is always enabled)
    hook = ad.get('haiku_hook', '')
    offer = ad.get('haiku_offer', 'N/A')
    confidence = ad.get('haiku_confidence', 'unknown')
    
    # Clean date text
    date_text = ad.get('ad_delivery_start_time', 'Unknown')
    if isinstance(date_text, str):
        date_text = date_text.replace('\u200b', '').replace('\u200c', '').replace('\u200d', '').strip()
    
    return {
        'ad_id': ad.get('id'),
        'page_name': page_name,
        'hook': hook,
        'offer': offer,
        'confidence': confidence,
        'body_snippet': body_text[:150] + '...' if len(body_text) > 150 else body_text,
        'snapshot_url': ad.get('ad_snapshot_url'),
        'date': date_text
    }


async def test_facebook_scraping(
    search_term: str, 
    target_hooks: int, 
    headless: bool = True, 
    positive_kw: list = None, 
    negative_kw: list = None
):
    """
    Test Facebook ad scraping and hook extraction.
    
    Continues scraping until we have target_hooks ads WITH valid offers.
    
    Args:
        search_term: The search term for ads
        target_hooks: Number of hooks WITH OFFERS to extract
        headless: Whether to run browser in headless mode
        positive_kw: List of positive/required keywords
        negative_kw: List of negative/exclusion keywords
    """
    print("=" * 80)
    print("FACEBOOK AD LIBRARY BROWSER SCRAPING")
    print("=" * 80)
    print(f"Search Term: {search_term}")
    print(f"Target: {target_hooks} ads WITH valid offers")
    print(f"Mode: {'Headless' if headless else 'Visible Browser'}")
    print(f"Analysis: Claude Haiku (always enabled)")
    print("=" * 80)
    
    # Initialize API keys
    print("\n[1/3] Initializing...")
    try:
        api_keys.load_api_keys()
        api_keys.initialize_clients()
    except Exception as e:
        print(f"[ERROR] API initialization failed: {e}")
        print("[INFO] API keys are required for Haiku analysis")
        return
    
    # Generate keywords if not provided
    if not positive_kw or not negative_kw:
        from hook_generator.keyword_generator import generate_keywords_with_sonnet, prompt_user_for_keywords
        
        print(f"\n[KEYWORDS] Generating filter keywords for '{search_term}'...")
        generated = generate_keywords_with_sonnet(search_term, max_positive=2, max_negative=5)
        
        approved = prompt_user_for_keywords(generated)
        while approved is None:  # User requested regeneration
            generated = generate_keywords_with_sonnet(search_term, max_positive=2, max_negative=5)
            approved = prompt_user_for_keywords(generated)
        
        if not positive_kw:
            positive_kw = approved['positive']
        if not negative_kw:
            negative_kw = approved['negative']
    
    # Display active filters
    print(f"\n[FILTERS]")
    print(f"  Positive (required): {', '.join(positive_kw)}")
    print(f"  Negative (excluded): {', '.join(negative_kw)}")
    
    # Scrape ads - continues until we have enough WITH valid offers
    # Ads without offers (N/A) are filtered out
    print(f"\n[2/3] Scraping Facebook Ad Library...")
    print(f"  Target: {target_hooks} ads with valid offers (N/A offers excluded)")
    
    ads = await scrape_ads_browser(
        search_term=search_term,
        target_count=target_hooks,
        headless=headless,
        scroll_limit=30,
        positive_keywords=positive_kw,
        negative_keywords=negative_kw,
        require_offers=True,
        fresh_days=7,    # Ads started within last 7 days
        proven_days=30   # Ads running 30+ days
    )
    
    if not ads:
        print("\n[ERROR] No relevant ads found!")
        print("Suggestions:")
        print("  - Broaden your search term")
        print("  - Adjust positive keywords (less restrictive)")
        print("  - Check that ads exist for this niche")
        return
    
    # Format results
    print(f"\n[3/3] Formatting results...")
    
    hooks_data = []
    ads_with_offers = 0
    fresh_count = 0
    proven_count = 0
    
    for ad in ads:
        formatted = format_ad_for_output(ad)
        formatted['ad_type'] = ad.get('ad_type', 'unknown')  # fresh or proven
        
        if formatted['hook'] and formatted['body_snippet'] and len(formatted['body_snippet']) > 20:
            hooks_data.append(formatted)
            if formatted['offer'] and formatted['offer'].upper() != 'N/A':
                ads_with_offers += 1
            if formatted['ad_type'] == 'fresh':
                fresh_count += 1
            elif formatted['ad_type'] == 'proven':
                proven_count += 1
    
    print(f"\n[OK] Processed {len(hooks_data)} ads ({ads_with_offers} with offers)")
    print(f"     PROVEN: {proven_count} | FRESH: {fresh_count}")
    
    # Display results
    print("\n" + "=" * 80)
    print("EXTRACTED HOOKS AND OFFERS")
    print("=" * 80)
    
    for i, hook in enumerate(hooks_data, 1):
        # Clean for terminal display
        page = hook['page_name'].encode('ascii', 'ignore').decode('ascii')
        hook_text = hook['hook'].encode('ascii', 'ignore').decode('ascii')
        offer_text = hook['offer'].encode('ascii', 'ignore').decode('ascii')
        snippet = hook['body_snippet'].encode('ascii', 'ignore').decode('ascii')
        date_text = str(hook['date']).encode('ascii', 'ignore').decode('ascii')
        
        # Show ad type and offer marker
        ad_type = hook.get('ad_type', 'unknown').upper()
        offer_marker = " [OFFER]" if offer_text.upper() != 'N/A' else ""
        
        print(f"\n[HOOK #{i}] [{ad_type}]{offer_marker}")
        print(f"  Page: {page}")
        print(f"  Hook: {hook_text}")
        print(f"  Offer: {offer_text}")
        print(f"  Snippet: {snippet}")
        print(f"  URL: {hook['snapshot_url']}")
        print(f"  Date: {date_text}")
        print("-" * 80)
    
    # Save results
    output_dir = Path("output/facebook_scraping_test")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"hooks_{search_term.replace(' ', '_')}_{timestamp}.json"
    
    # Human-readable timestamp
    now = datetime.now()
    readable_time = f"{now.month}/{now.day}/{now.strftime('%y')} {now.strftime('%I:%M %p').lstrip('0')}"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            'search_term': search_term,
            'target_hooks': target_hooks,
            'total_ads': len(hooks_data),
            'ads_with_offers': ads_with_offers,
            'breakdown': {
                'proven_ads': proven_count,
                'fresh_ads': fresh_count
            },
            'filters': {
                'positive_keywords': positive_kw,
                'negative_keywords': negative_kw
            },
            'scraped_at': readable_time,
            'scraped_at_iso': now.isoformat(),
            'hooks': hooks_data
        }, f, indent=2, ensure_ascii=False)
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"  Search Term: {search_term}")
    print(f"  Positive Keywords: {', '.join(positive_kw)}")
    print(f"  Negative Keywords: {', '.join(negative_kw)}")
    print(f"  Target: {target_hooks} ads with offers")
    print(f"  Total Ads: {len(hooks_data)}")
    print(f"    - PROVEN (30+ days): {proven_count}")
    print(f"    - FRESH (last 7 days): {fresh_count}")
    print(f"  Ads WITH Offers: {ads_with_offers}")
    print(f"  Success Rate: {ads_with_offers / target_hooks * 100:.1f}%")
    print(f"  Saved to: {output_file}")
    print("=" * 80)
    
    if ads_with_offers < target_hooks:
        shortfall = target_hooks - ads_with_offers
        print(f"\n[NOTE] Fell short by {shortfall} ads with offers")
        print("This may mean:")
        print("  - Many ads in this niche don't have explicit offers")
        print("  - Try a different search term")
        print("  - The market may not heavily use discounts/promos")
    else:
        print(f"\n[SUCCESS] Found {ads_with_offers} ads with valid offers!")


def main():
    parser = argparse.ArgumentParser(
        description="Scrape Facebook ads and extract hooks/offers with Claude Haiku",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Auto-generate keywords with Claude Sonnet
  python test_facebook_scraping.py --search "exterior painting" --hooks 50

  # Manual keywords
  python test_facebook_scraping.py --search "exterior painting" --positive "paint,painting" --negative "jobs,cleaning,car,commercial,employment" --hooks 50

  # Show browser window during scraping
  python test_facebook_scraping.py --search "hvac service" --hooks 25 --no-headless
        """
    )
    
    parser.add_argument(
        '--search', '-s',
        type=str,
        required=True,
        help='Search term for Facebook ads (e.g., "exterior painting")'
    )
    
    parser.add_argument(
        '--hooks', '-n',
        type=int,
        default=50,
        help='Target number of ads WITH offers (default: 50)'
    )
    
    parser.add_argument(
        '--positive', '-p',
        type=str,
        help='Comma-separated positive/required keywords (max 2)'
    )
    
    parser.add_argument(
        '--negative', '-neg',
        type=str,
        help='Comma-separated negative/exclusion keywords (max 5)'
    )
    
    parser.add_argument(
        '--no-headless',
        action='store_true',
        help='Show browser window during scraping (useful for debugging)'
    )
    
    args = parser.parse_args()
    
    # Validate hooks count
    if args.hooks < 1 or args.hooks > 500:
        parser.error("--hooks must be between 1 and 500")
    
    # Parse keywords
    positive_kw = None
    negative_kw = None
    
    if args.positive:
        positive_kw = [k.strip().lower() for k in args.positive.split(",")]
        if len(positive_kw) > 2:
            print(f"[WARNING] Maximum 2 positive keywords, using first 2")
            positive_kw = positive_kw[:2]
    
    if args.negative:
        negative_kw = [k.strip().lower() for k in args.negative.split(",")]
        if len(negative_kw) > 5:
            print(f"[WARNING] Maximum 5 negative keywords, using first 5")
            negative_kw = negative_kw[:5]
    
    # Run scraper
    asyncio.run(test_facebook_scraping(
        search_term=args.search,
        target_hooks=args.hooks,
        headless=not args.no_headless,
        positive_kw=positive_kw,
        negative_kw=negative_kw
    ))


if __name__ == "__main__":
    main()
