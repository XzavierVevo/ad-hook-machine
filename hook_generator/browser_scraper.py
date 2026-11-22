"""
Browser-based scraper for Meta Ad Library using Playwright.
Bypasses API restrictions for US commercial ads.
"""

import asyncio
import re
import hashlib
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime, timedelta

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

from . import config
from .logger import bot_logger

def _has_negative_keywords(text: str, negative_keywords: List[str]) -> bool:
    """
    Check if text contains any negative keywords (anti-patterns).
    Uses word boundary matching to avoid substring matches.
    """
    if not text or not negative_keywords:
        return False
    
    text_lower = text.lower()
    for neg in negative_keywords:
        pattern = r'\b' + re.escape(neg.lower()) + r'\b'
        if re.search(pattern, text_lower):
            return True
    return False


def _has_positive_keywords(text: str, positive_keywords: List[str]) -> bool:
    """
    Check if text contains at least one positive/required keyword.
    Uses flexible matching: tries word boundary first, then falls back to substring matching
    for common word variations (e.g., "paint" matches "painting").
    """
    if not positive_keywords:
        return True
    
    if not text:
        return False
    
    text_lower = text.lower()
    for pos in positive_keywords:
        pos_lower = pos.lower()
        # First try word boundary matching (exact word)
        pattern = r'\b' + re.escape(pos_lower) + r'\b'
        if re.search(pattern, text_lower):
            return True
        # Fallback: substring matching for common variations
        # This handles cases like "paint" matching "painting", "painter", etc.
        if pos_lower in text_lower:
            return True
    return False


def _has_foreign_currency(text: str) -> bool:
    """
    Check if text contains foreign (non-US) currency symbols.
    Used to filter out ads from other countries that reach the US.
    """
    if not text:
        return False
    
    foreign_currency_patterns = [
        '₹', '€', '£', '¥', '₩', '₱', '฿', '₫', '₴', '₽',
        r'\bRs\.?\s*\d', r'\bINR\s*\d', r'\bCrore\b', r'\bLacs?\b',
    ]
    
    for pattern in foreign_currency_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


# ============================================================================
# FORCED BLOCKLIST - Always applied regardless of user keywords
# ============================================================================
ROMANCE_NOVEL_BLOCKLIST = [
    "werewolf", "werewolves", "alpha male", "luna", "mate bond", "fated mate",
    "shifter", "wolf pack", "alpha wolf", "true mate", "rejected mate",
    "billionaire", "ceo romance", "secret baby", "royal twins",
    "chapter 1", "chapter one", "read now", "read free", "unlock chapter",
    "episode 1", "novel", "fiction", "serialized",
    "pregnant", "divorced me", "betrayed", "secret heir", "forbidden love",
    "steamy", "passionate nights", "love story",
    "she said", "he said", "i said",
]


def _is_romance_novel_ad(text: str) -> bool:
    """Check if ad is a romance novel/story ad. Always blocked."""
    if not text:
        return False
    
    text_lower = text.lower()
    for term in ROMANCE_NOVEL_BLOCKLIST:
        if term in text_lower:
            return True
    
    quote_count = text.count('"') + text.count('"') + text.count('"') + text.count("'")
    if quote_count >= 4 and len(text) < 500:
        return True
    
    return False


async def _scrape_single_date_range(
    page,
    search_term: str,
    target_count: int,
    scroll_limit: int,
    sort_mode: str,
    filter_label: str,
    positive_keywords: Optional[List[str]],
    negative_keywords: Optional[List[str]],
    seen_ids: set,
    require_offers: bool,
    include_inactive: bool = False
) -> tuple:
    """
    Internal helper: Scrape ads with a specific sort mode.
    
    Args:
        sort_mode: Sort mode for results
            - "total_impressions" for Impressions: high to low (PROVEN)
            - "relevancy_monthly_grouped" for Most recent (FRESH)
        include_inactive: If True, search both active and inactive ads
    
    Returns:
        tuple of (ads_list, ads_with_offers_count, should_retry_with_inactive)
        should_retry_with_inactive is True if we hit 20 consecutive zero-result scrolls
    """
    # Build sort parameters - match Facebook's exact parameter order
    active_status = "all" if include_inactive else "active"
    if sort_mode == "relevancy_monthly_grouped":
        # FRESH: mode comes before direction
        sort_params = f"&sort_data[mode]={sort_mode}&sort_data[direction]=desc"
    else:
        # PROVEN: direction comes before mode
        sort_params = f"&sort_data[direction]=desc&sort_data[mode]={sort_mode}"
    url = f"https://www.facebook.com/ads/library/?active_status={active_status}&ad_type=all&country=US&is_targeted_country=false&media_type=all&q={search_term}&search_type=keyword_unordered{sort_params}"
    
    if include_inactive:
        print(f"  [{filter_label}] Including INACTIVE ads in search")
    
    print(f"\n  [{filter_label}] Loading ads...")
    
    try:
        # Get config values for timeouts and scrolling
        page_load_timeout = getattr(config, 'PAGE_LOAD_TIMEOUT_MS', 30000)
        selector_timeout = getattr(config, 'SELECTOR_WAIT_TIMEOUT_MS', 8000)
        network_idle_timeout = getattr(config, 'NETWORK_IDLE_TIMEOUT_MS', 10000)
        
        await page.goto(url, wait_until="domcontentloaded", timeout=page_load_timeout)
        
        # Try multiple selectors and wait strategies for better reliability
        selectors_to_try = [
            'text="See ad detail"',
            'text="See ad details"',
            'text="Library ID"',
            'div:has-text("ID:")',
        ]
        
        found_selector = None
        selector_error = None
        
        for selector in selectors_to_try:
            try:
                await page.wait_for_selector(selector, timeout=selector_timeout)
                found_selector = selector
                break
            except Exception as e:
                selector_error = e
                continue
        
        # If no specific selector found, check if page has loaded content
        if not found_selector:
            # Wait a bit more for page to fully load
            try:
                await page.wait_for_load_state("networkidle", timeout=network_idle_timeout)
            except Exception as e:
                bot_logger.debug(f"Page load timeout, waiting additional 3 seconds: {e}")
                await asyncio.sleep(3)  # Give it a few more seconds
            
            # Check if there's any content that might be ads
            has_content = await page.evaluate("""() => {
                const bodyText = document.body.innerText || '';
                return bodyText.includes('ID:') || 
                       bodyText.includes('Library') ||
                       bodyText.includes('Started running') ||
                       document.querySelectorAll('div').length > 100;
            }""")
            
            if not has_content:
                # Check for "No results" message (try multiple possible texts)
                no_results = (
                    await page.query_selector('text="No results found"') or
                    await page.query_selector('text="No ads match your search criteria"') or
                    await page.query_selector('text="No ads match"') or
                    await page.query_selector('text="No ads"')
                )
                if no_results:
                    print(f"  [{filter_label}] No ads found for this date range")
                    return [], 0, False
                
                # Log the actual error for debugging
                error_type = type(selector_error).__name__ if selector_error else "TimeoutError"
                error_msg = str(selector_error) if selector_error else "No content detected"
                print(f"  [{filter_label}] Error waiting for results: {error_type}: {error_msg}")
                
                # Try to get page title and URL for debugging
                try:
                    page_title = await page.title()
                    page_url = page.url
                    print(f"  [{filter_label}] Page title: {page_title[:100]}")
                    print(f"  [{filter_label}] Current URL: {page_url[:150]}")
                except Exception as e:
                    bot_logger.debug(f"Could not get page info for debugging: {e}")
                    pass
                
                # Take a screenshot for debugging (save to output directory if possible)
                try:
                    from pathlib import Path
                    debug_dir = Path("output/debug_screenshots")
                    debug_dir.mkdir(parents=True, exist_ok=True)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    screenshot_path = debug_dir / f"{filter_label.lower()}_error_{timestamp}.png"
                    await page.screenshot(path=str(screenshot_path), full_page=True)
                    print(f"  [{filter_label}] Debug screenshot saved: {screenshot_path}")
                except Exception as screenshot_error:
                    print(f"  [{filter_label}] Could not save screenshot: {screenshot_error}")
                
                return [], 0, False
            else:
                # We have content but no specific selector - use fallback extraction
                print(f"  [{filter_label}] Using fallback extraction (content detected but no standard selector found)")
        else:
            print(f"  [{filter_label}] Found ads using selector: {found_selector}")
        
        # ADD DEBUGGING: Check what's actually on the page
        page_content_check = await page.evaluate("""() => {
            const bodyText = document.body.innerText || '';
            const hasId = bodyText.includes('ID:');
            const hasLibrary = bodyText.includes('Library');
            const hasSeeAdDetails = bodyText.includes('See ad details') || bodyText.includes('See ad detail');
            const divCount = document.querySelectorAll('div').length;
            const title = document.title;
            return {
                hasId: hasId,
                hasLibrary: hasLibrary,
                hasSeeAdDetails: hasSeeAdDetails,
                divCount: divCount,
                title: title,
                bodyTextLength: bodyText.length,
                url: window.location.href
            };
        }""")
        print(f"  [{filter_label}] Page check: {page_content_check}")
        
        # Also check if we're being blocked or redirected
        current_url = page.url
        if 'login' in current_url.lower() or 'facebook.com/login' in current_url:
            print(f"  [{filter_label}] WARNING: Redirected to login page!")
        if current_url != url:
            print(f"  [{filter_label}] WARNING: URL changed from {url[:100]}... to {current_url[:100]}...")
        
        ads_found = []
        ads_with_offers = 0
        batch_for_analysis = []
        scrolls = 0
        min_scrolls = max(10, int(scroll_limit * 0.5))  # Minimum 50% of scroll limit or 10, whichever is higher
        consecutive_no_new_ads = 0  # Track consecutive scrolls with no new ads
        
        while scrolls < scroll_limit:
            # Stop early if we have enough ads with offers
            # The target_count passed in is already calculated as part of the 2x total needed
            if require_offers:
                if ads_with_offers >= target_count:
                    print(f"  [{filter_label}] Found {ads_with_offers} ads with offers (target: {target_count}), stopping scroll to check uniqueness")
                    break
                # Also stop if we've reached target and done minimum scrolls with no new ads
                elif ads_with_offers >= target_count * 0.8 and scrolls >= min_scrolls:  # 80% of target
                    if consecutive_no_new_ads >= 3:  # 3 consecutive scrolls with no new ads
                        print(f"  [{filter_label}] Reached {ads_with_offers}/{target_count} ads with offers and no new ads for {consecutive_no_new_ads} scrolls, stopping")
                        break
            else:
                if len(ads_found) >= target_count and scrolls >= min_scrolls:
                    if consecutive_no_new_ads >= 3:
                        break
            
            # Extract ad cards - more flexible matching
            cards = await page.evaluate("""() => {
                const cards = [];
                // More flexible: find divs that contain ID: pattern (primary indicator of ad cards)
                const adElements = Array.from(document.querySelectorAll('div')).filter(el => {
                    const text = el.innerText || '';
                    // Primary requirement: must have ID: pattern
                    if (!text.includes('ID:')) return false;
                    
                    // Secondary indicators (at least one should be present)
                    const hasAdIndicators = 
                        text.includes('See ad detail') || 
                        text.includes('See ad details') ||
                        text.includes('Library ID') ||
                        text.includes('Started running') ||
                        text.match(/ID:\\s*\\d+/);
                    
                    return hasAdIndicators;
                });
                
                const seenIds = new Set();
                const junkPatterns = ["Open Dropdown", "Sponsored", "Active", "Inactive", "Low impression count", 
                                      "See ad detail", "See ad details", "Library ID", "Started running on", "Learn more", "Send message",
                                      "Watch more", "Download", "Visit Instagram", "Impressions:", "Platforms"];
                
                adElements.forEach(adElement => {
                    const idMatch = adElement.innerText.match(/ID:\\s*(\\d+)/);
                    if (!idMatch || seenIds.has(idMatch[1])) return;
                    
                    const adId = idMatch[1];
                    seenIds.add(adId);
                    
                    const fullText = adElement.innerText;
                    // Handle multiple possible separators
                    let contentPart = fullText;
                    
                    // Try to find content after common separators
                    const separators = ['See ad detail', 'See ad details', 'Library ID', 'ID:'];
                    for (const sep of separators) {
                        const parts = fullText.split(sep);
                        if (parts.length > 1) {
                            // Take the part after the separator, but skip if it's just the ID number
                            const afterSep = parts[parts.length - 1].trim();
                            if (afterSep && !afterSep.match(/^\\d+$/)) {
                                contentPart = afterSep;
                                break;
                            }
                        }
                    }
                    
                    // If we still have the full text, try to extract just the meaningful content
                    if (contentPart === fullText) {
                        // Remove ID: line and other metadata
                        const lines = fullText.split('\\n');
                        const meaningfulLines = lines.filter(line => {
                            return !line.match(/^ID:\\s*\\d+$/) &&
                                   !line.includes('Library ID') &&
                                   !line.match(/^Started running on/) &&
                                   line.trim().length > 3;
                        });
                        contentPart = meaningfulLines.join('\\n');
                    }
                    
                    let lines = contentPart.split('\\n').map(l => l.trim()).filter(l => l.length > 0);
                    lines = lines.filter(line => {
                        return !junkPatterns.some(junk => line.includes(junk)) &&
                               !line.match(/^ID:\\s*\\d+$/) &&
                               !line.match(/^\\d{1,2}:\\d{2}\\s*\\/\\s*\\d{1,2}:\\d{2}$/) &&
                               !line.match(/^<\\d+$/) &&
                               line.length > 3;
                    });
                    
                    let pageName = "Unknown";
                    let bodyText = "";
                    
                    if (lines.length > 0) {
                        pageName = lines[0];
                        if (pageName.length > 100) {
                            bodyText = pageName;
                            pageName = "Unknown";
                        } else {
                            bodyText = lines.slice(1).join(' ');
                        }
                    }
                    
                    if (pageName.length > 100) {
                        pageName = pageName.substring(0, 100) + "...";
                    }
                    
                    const dateMatch = fullText.match(/Started running on ([^\\n]+)/);
                    const dateText = dateMatch ? dateMatch[1].trim() : "Unknown";
                    
                    cards.push({
                        id: adId,
                        page_name: pageName,
                        body_text: bodyText,
                        date_text: dateText
                    });
                });
                
                return cards;
            }""")
            
            # Process and filter
            new_ads = []
            cards_seen_this_scroll = 0
            cards_new_this_scroll = 0
            filtered_count = 0
            filter_reasons = {
                'duplicate': 0,
                'foreign_currency': 0,
                'romance_novel': 0,
                'negative_keywords': 0,
                'missing_positive_keywords': 0
            }
            
            for card in cards:
                ad_id = card['id']
                cards_seen_this_scroll += 1
                if ad_id in seen_ids:
                    filter_reasons['duplicate'] += 1
                    filtered_count += 1  # Include duplicates in filtered count
                    continue
                cards_new_this_scroll += 1
                
                page_name = card['page_name']
                body_text = card['body_text']
                combined = f"{page_name} {body_text}"
                combined_lower = combined.lower()
                
                # Apply filters and track reasons
                filtered = False
                if _has_foreign_currency(combined):
                    filter_reasons['foreign_currency'] += 1
                    filtered = True
                elif _is_romance_novel_ad(combined):
                    filter_reasons['romance_novel'] += 1
                    filtered = True
                elif negative_keywords and _has_negative_keywords(combined_lower, negative_keywords):
                    filter_reasons['negative_keywords'] += 1
                    filtered = True
                elif positive_keywords and not _has_positive_keywords(combined_lower, positive_keywords):
                    filter_reasons['missing_positive_keywords'] += 1
                    filtered = True
                
                if filtered:
                    filtered_count += 1
                    continue
                
                ad_data = {
                    'id': ad_id,
                    'page_name': page_name,
                    'ad_snapshot_url': f"https://www.facebook.com/ads/library/?id={ad_id}",
                    'ad_creative_bodies': [body_text] if body_text else [],
                    'ad_delivery_start_time': card['date_text'],
                    'ad_type': filter_label.lower(),
                    'method': 'browser'
                }
                new_ads.append(ad_data)
                seen_ids.add(ad_id)
            
            # Log filter reasons periodically or when many cards are filtered
            # Show logging every 5 scrolls, on first scroll, or when significant filtering occurs
            if (filtered_count > 0 or cards_seen_this_scroll > 0) and (scrolls % 5 == 0 or filtered_count >= 5 or scrolls == 0):
                total_checked = cards_seen_this_scroll
                reasons_str = ", ".join([f"{reason}: {count}" for reason, count in filter_reasons.items() if count > 0])
                if reasons_str:
                    print(f"  [{filter_label}] Checked {total_checked} cards, filtered {filtered_count} - {reasons_str}")
            
            if new_ads:
                batch_for_analysis.extend(new_ads)
            
            # Analyze batch
            if len(batch_for_analysis) >= 15 or (scrolls >= scroll_limit - 1 and batch_for_analysis):
                try:
                    from .hook_analyzer import analyze_hooks_batch
                    analyzed = analyze_hooks_batch(batch_for_analysis)
                    
                    for ad in analyzed:
                        ads_found.append(ad)
                        offer = ad.get('haiku_offer', 'N/A')
                        if offer and offer.upper() != 'N/A':
                            ads_with_offers += 1
                    
                    print(f"  [{filter_label}] {ads_with_offers}/{target_count} with offers (total: {len(ads_found)})")
                    batch_for_analysis = []
                    
                except Exception as e:
                    print(f"  [{filter_label}] Haiku failed: {e}")
                    ads_found.extend(batch_for_analysis)
                    batch_for_analysis = []
            
            # Track consecutive scrolls with no new ads (after filtering)
            # Use len(new_ads) not cards_new_this_scroll because ads can be filtered out
            if len(new_ads) == 0:
                consecutive_no_new_ads += 1
                
                # Check if we should switch to include inactive ads
                zero_threshold = getattr(config, 'ZERO_SCROLL_THRESHOLD_FOR_INACTIVE', 20)
                if consecutive_no_new_ads >= zero_threshold and not include_inactive:
                    print(f"  [{filter_label}] Hit {consecutive_no_new_ads} consecutive scrolls with zero new ads")
                    print(f"  [{filter_label}] Will retry with INACTIVE ads included...")
                    # Return what we have so far, with flag to retry with inactive
                    return ads_found, ads_with_offers, True
            else:
                consecutive_no_new_ads = 0  # Reset counter when we find new ads
            
            # Log progress every 5 scrolls or when finding ads
            if scrolls % 5 == 0 or len(new_ads) > 0:
                print(f"  [{filter_label}] Scroll {scrolls}/{scroll_limit}: Found {len(new_ads)} new ads this scroll ({cards_new_this_scroll} new cards, {cards_seen_this_scroll} total cards seen, {len(seen_ids)} total seen IDs)")
            
            # Get config values for scrolling speed
            scroll_distance = getattr(config, 'SCROLL_DISTANCE_PIXELS', 6000)
            scroll_delay = getattr(config, 'SCROLL_DELAY_SECONDS', 1.0)
            
            # Clamp values to safe ranges to avoid Facebook rate limiting
            scroll_distance = max(3000, min(8000, scroll_distance))  # 3000-8000 pixels
            scroll_delay = max(0.5, min(3.0, scroll_delay))  # 0.5-3.0 seconds
            
            await page.mouse.wheel(0, scroll_distance)
            await asyncio.sleep(scroll_delay)
            scrolls += 1
        
        # Final batch
        if batch_for_analysis:
            try:
                from .hook_analyzer import analyze_hooks_batch
                analyzed = analyze_hooks_batch(batch_for_analysis)
                for ad in analyzed:
                    ads_found.append(ad)
                    offer = ad.get('haiku_offer', 'N/A')
                    if offer and offer.upper() != 'N/A':
                        ads_with_offers += 1
            except Exception as e:
                bot_logger.warning(f"Error processing batch, adding raw ads: {e}")
                ads_found.extend(batch_for_analysis)
        
        print(f"  [{filter_label}] Complete: {len(ads_found)} ads found, {ads_with_offers} with offers (ended at scroll {scrolls})")
        if len(ads_found) < target_count:
            print(f"  [{filter_label}] NOTE: Found fewer ads than target. Will continue from scroll {scrolls} on next attempt.")
        return ads_found, ads_with_offers, False
        
    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)
        print(f"  [{filter_label}] Fatal error: {error_type}: {error_msg}")
        import traceback
        print(f"  [{filter_label}] Traceback: {traceback.format_exc()}")
        return [], 0, False


async def _scrape_single_date_range_continuous(
    page,
    search_term: str,
    target_count: int,
    scroll_limit: int,
    sort_mode: str,
    filter_label: str,
    positive_keywords: Optional[List[str]],
    negative_keywords: Optional[List[str]],
    seen_ids: set,
    require_offers: bool,
    start_scroll: int = 0,
    include_inactive: bool = False
) -> tuple:
    """
    Continuous scraping version that can resume from a previous scroll position.
    
    Args:
        start_scroll: The scroll position to continue from (0 = start from beginning)
        include_inactive: If True, search both active and inactive ads
    
    Returns:
        tuple of (ads_list, ads_with_offers_count, final_scroll_position, should_retry_with_inactive)
    """
    # Build sort parameters - match Facebook's exact parameter order
    active_status = "all" if include_inactive else "active"
    if sort_mode == "relevancy_monthly_grouped":
        # FRESH: mode comes before direction
        sort_params = f"&sort_data[mode]={sort_mode}&sort_data[direction]=desc"
    else:
        # PROVEN: direction comes before mode
        sort_params = f"&sort_data[direction]=desc&sort_data[mode]={sort_mode}"
    url = f"https://www.facebook.com/ads/library/?active_status={active_status}&ad_type=all&country=US&is_targeted_country=false&media_type=all&q={search_term}&search_type=keyword_unordered{sort_params}"
    
    if include_inactive:
        print(f"  [{filter_label}] Including INACTIVE ads in search")
    
    print(f"\n  [{filter_label}] Loading ads... (starting from scroll {start_scroll})")
    
    try:
        # Get config values for timeouts and scrolling
        page_load_timeout = getattr(config, 'PAGE_LOAD_TIMEOUT_MS', 30000)
        selector_timeout = getattr(config, 'SELECTOR_WAIT_TIMEOUT_MS', 8000)
        network_idle_timeout = getattr(config, 'NETWORK_IDLE_TIMEOUT_MS', 10000)
        scroll_distance = getattr(config, 'SCROLL_DISTANCE_PIXELS', 6000)
        scroll_delay = getattr(config, 'SCROLL_DELAY_SECONDS', 1.0)
        
        # Clamp scroll values to safe ranges
        scroll_distance = max(3000, min(8000, scroll_distance))
        scroll_delay = max(0.5, min(3.0, scroll_delay))
        
        await page.goto(url, wait_until="domcontentloaded", timeout=page_load_timeout)
        
        # Try multiple selectors and wait strategies for better reliability
        selectors_to_try = [
            'text="See ad detail"',
            'text="See ad details"',
            'text="Library ID"',
            'div:has-text("ID:")',
        ]
        
        found_selector = None
        for selector in selectors_to_try:
            try:
                await page.wait_for_selector(selector, timeout=selector_timeout)
                found_selector = selector
                break
            except Exception:
                continue
        
        # If no specific selector found, check if page has loaded content
        if not found_selector:
            try:
                await page.wait_for_load_state("networkidle", timeout=network_idle_timeout)
            except Exception:
                await asyncio.sleep(3)
            
            # Check if there's any content
            has_content = await page.evaluate("""() => {
                const bodyText = document.body.innerText || '';
                return bodyText.includes('ID:') || 
                       bodyText.includes('Library') ||
                       bodyText.includes('Started running') ||
                       document.querySelectorAll('div').length > 100;
            }""")
            
            if not has_content:
                # Check for "No results" message
                no_results = (
                    await page.query_selector('text="No results found"') or
                    await page.query_selector('text="No ads match your search criteria"') or
                    await page.query_selector('text="No ads match"') or
                    await page.query_selector('text="No ads"')
                )
                if no_results:
                    print(f"  [{filter_label}] No ads found for this search")
                    return [], 0, start_scroll, False
                
                print(f"  [{filter_label}] Could not verify page loaded, attempting anyway...")
        else:
            print(f"  [{filter_label}] Found ads using selector: {found_selector}")
        
        # ADD DEBUGGING: Check what's actually on the page
        page_content_check = await page.evaluate("""() => {
            const bodyText = document.body.innerText || '';
            const hasId = bodyText.includes('ID:');
            const hasLibrary = bodyText.includes('Library');
            const hasSeeAdDetails = bodyText.includes('See ad details') || bodyText.includes('See ad detail');
            const divCount = document.querySelectorAll('div').length;
            const title = document.title;
            return {
                hasId: hasId,
                hasLibrary: hasLibrary,
                hasSeeAdDetails: hasSeeAdDetails,
                divCount: divCount,
                title: title,
                bodyTextLength: bodyText.length,
                url: window.location.href
            };
        }""")
        print(f"  [{filter_label}] Page check: {page_content_check}")
        
        # Also check if we're being blocked or redirected
        current_url = page.url
        if 'login' in current_url.lower() or 'facebook.com/login' in current_url:
            print(f"  [{filter_label}] WARNING: Redirected to login page!")
        if current_url != url:
            print(f"  [{filter_label}] WARNING: URL changed from {url[:100]}... to {current_url[:100]}...")
        
        # Fast-scroll to the starting position if we're resuming
        if start_scroll > 0:
            print(f"  [{filter_label}] Fast-scrolling to position {start_scroll}...")
            for catch_up_scroll in range(start_scroll):
                await page.mouse.wheel(0, scroll_distance)
                # Fast scroll - minimal delay since we're just catching up
                await asyncio.sleep(0.3)
                if catch_up_scroll % 10 == 0 and catch_up_scroll > 0:
                    print(f"  [{filter_label}] Catch-up progress: {catch_up_scroll}/{start_scroll}")
            print(f"  [{filter_label}] Reached previous position, continuing scrape...")
            # Small pause to let content load after fast scrolling
            await asyncio.sleep(1)
        
        ads_found = []
        ads_with_offers = 0
        batch_for_analysis = []
        scrolls = start_scroll  # Start counting from where we left off
        min_scrolls = max(10, int(scroll_limit * 0.5))
        consecutive_no_new_ads = 0
        
        while scrolls < scroll_limit:
            # Stop early if we have enough ads with offers
            if require_offers:
                if ads_with_offers >= target_count:
                    print(f"  [{filter_label}] Found {ads_with_offers} ads with offers (target: {target_count}), stopping scroll to check uniqueness")
                    break
                elif ads_with_offers >= target_count * 0.8 and scrolls >= min_scrolls:
                    if consecutive_no_new_ads >= 3:
                        print(f"  [{filter_label}] Reached {ads_with_offers}/{target_count} ads with offers and no new ads for {consecutive_no_new_ads} scrolls, stopping")
                        break
            else:
                if len(ads_found) >= target_count and scrolls >= min_scrolls:
                    if consecutive_no_new_ads >= 3:
                        break
            
            # Extract ad cards
            cards = await page.evaluate("""() => {
                const cards = [];
                const adElements = Array.from(document.querySelectorAll('div')).filter(el => {
                    const text = el.innerText || '';
                    if (!text.includes('ID:')) return false;
                    const hasAdIndicators = 
                        text.includes('See ad detail') || 
                        text.includes('See ad details') ||
                        text.includes('Library ID') ||
                        text.includes('Started running') ||
                        text.match(/ID:\\s*\\d+/);
                    return hasAdIndicators;
                });
                
                const seenIds = new Set();
                const junkPatterns = ["Open Dropdown", "Sponsored", "Active", "Inactive", "Low impression count", 
                                      "See ad detail", "See ad details", "Library ID", "Started running on", "Learn more", "Send message",
                                      "Watch more", "Download", "Visit Instagram", "Impressions:", "Platforms"];
                
                adElements.forEach(adElement => {
                    const idMatch = adElement.innerText.match(/ID:\\s*(\\d+)/);
                    if (!idMatch || seenIds.has(idMatch[1])) return;
                    
                    const adId = idMatch[1];
                    seenIds.add(adId);
                    
                    const fullText = adElement.innerText;
                    let contentPart = fullText;
                    
                    const separators = ['See ad detail', 'See ad details', 'Library ID', 'ID:'];
                    for (const sep of separators) {
                        const parts = fullText.split(sep);
                        if (parts.length > 1) {
                            const afterSep = parts[parts.length - 1].trim();
                            if (afterSep && !afterSep.match(/^\\d+$/)) {
                                contentPart = afterSep;
                                break;
                            }
                        }
                    }
                    
                    if (contentPart === fullText) {
                        const lines = fullText.split('\\n');
                        const meaningfulLines = lines.filter(line => {
                            return !line.match(/^ID:\\s*\\d+$/) &&
                                   !line.includes('Library ID') &&
                                   !junkPatterns.some(p => line.includes(p));
                        });
                        contentPart = meaningfulLines.join('\\n');
                    }
                    
                    const lines = contentPart.split('\\n')
                        .map(l => l.trim())
                        .filter(l => l && !junkPatterns.some(p => l.includes(p)));
                    
                    const pageName = lines[0] || '';
                    const bodyText = lines.slice(1).join(' ').trim();
                    
                    const dateMatch = fullText.match(/Started running on[:\\s]*(\\w+ \\d+, \\d{4})/i);
                    const dateText = dateMatch ? dateMatch[1] : '';
                    
                    cards.push({
                        id: adId,
                        page_name: pageName,
                        body_text: bodyText,
                        date_text: dateText
                    });
                });
                return cards;
            }""")
            
            # Apply filters
            new_ads = []
            filtered_count = 0
            cards_seen_this_scroll = 0
            cards_new_this_scroll = 0
            filter_reasons = {
                'duplicate': 0,
                'foreign_currency': 0,
                'romance_novel': 0,
                'negative_keywords': 0,
                'missing_positive_keywords': 0
            }
            
            for card in cards:
                ad_id = card['id']
                cards_seen_this_scroll += 1
                if ad_id in seen_ids:
                    filter_reasons['duplicate'] += 1
                    filtered_count += 1
                    continue
                cards_new_this_scroll += 1
                
                page_name = card['page_name']
                body_text = card['body_text']
                combined = f"{page_name} {body_text}"
                combined_lower = combined.lower()
                
                filtered = False
                if _has_foreign_currency(combined):
                    filter_reasons['foreign_currency'] += 1
                    filtered = True
                elif _is_romance_novel_ad(combined):
                    filter_reasons['romance_novel'] += 1
                    filtered = True
                elif negative_keywords and _has_negative_keywords(combined_lower, negative_keywords):
                    filter_reasons['negative_keywords'] += 1
                    filtered = True
                elif positive_keywords and not _has_positive_keywords(combined_lower, positive_keywords):
                    filter_reasons['missing_positive_keywords'] += 1
                    filtered = True
                
                if filtered:
                    filtered_count += 1
                    continue
                
                ad_data = {
                    'id': ad_id,
                    'page_name': page_name,
                    'ad_snapshot_url': f"https://www.facebook.com/ads/library/?id={ad_id}",
                    'ad_creative_bodies': [body_text] if body_text else [],
                    'ad_delivery_start_time': card['date_text'],
                    'ad_type': filter_label.lower(),
                    'method': 'browser'
                }
                new_ads.append(ad_data)
                seen_ids.add(ad_id)
            
            # Log filter reasons periodically
            if (filtered_count > 0 or cards_seen_this_scroll > 0) and (scrolls % 5 == 0 or filtered_count >= 5 or scrolls == start_scroll):
                reasons_str = ", ".join([f"{reason}: {count}" for reason, count in filter_reasons.items() if count > 0])
                if reasons_str:
                    print(f"  [{filter_label}] Checked {cards_seen_this_scroll} cards, filtered {filtered_count} - {reasons_str}")
            
            if new_ads:
                batch_for_analysis.extend(new_ads)
            
            # Analyze batch
            if len(batch_for_analysis) >= 15 or (scrolls >= scroll_limit - 1 and batch_for_analysis):
                try:
                    from .hook_analyzer import analyze_hooks_batch
                    analyzed = analyze_hooks_batch(batch_for_analysis)
                    
                    for ad in analyzed:
                        ads_found.append(ad)
                        offer = ad.get('haiku_offer', 'N/A')
                        if offer and offer.upper() != 'N/A':
                            ads_with_offers += 1
                    
                    print(f"  [{filter_label}] {ads_with_offers}/{target_count} with offers (total: {len(ads_found)})")
                    batch_for_analysis = []
                    
                except Exception as e:
                    print(f"  [{filter_label}] Haiku failed: {e}")
                    ads_found.extend(batch_for_analysis)
                    batch_for_analysis = []
            
            # Track consecutive scrolls with no new ads
            if len(new_ads) == 0:
                consecutive_no_new_ads += 1
                
                # Check if we should switch to include inactive ads
                zero_threshold = getattr(config, 'ZERO_SCROLL_THRESHOLD_FOR_INACTIVE', 20)
                if consecutive_no_new_ads >= zero_threshold and not include_inactive:
                    print(f"  [{filter_label}] Hit {consecutive_no_new_ads} consecutive scrolls with zero new ads")
                    print(f"  [{filter_label}] Will retry with INACTIVE ads included...")
                    return ads_found, ads_with_offers, scrolls, True
            else:
                consecutive_no_new_ads = 0
            
            # Log progress
            if scrolls % 5 == 0 or len(new_ads) > 0:
                print(f"  [{filter_label}] Scroll {scrolls}/{scroll_limit}: Found {len(new_ads)} new ads this scroll ({cards_new_this_scroll} new cards, {len(seen_ids)} total seen IDs)")
            
            await page.mouse.wheel(0, scroll_distance)
            await asyncio.sleep(scroll_delay)
            scrolls += 1
        
        # Final batch
        if batch_for_analysis:
            try:
                from .hook_analyzer import analyze_hooks_batch
                analyzed = analyze_hooks_batch(batch_for_analysis)
                for ad in analyzed:
                    ads_found.append(ad)
                    offer = ad.get('haiku_offer', 'N/A')
                    if offer and offer.upper() != 'N/A':
                        ads_with_offers += 1
            except Exception as e:
                bot_logger.warning(f"Error processing batch, adding raw ads: {e}")
                ads_found.extend(batch_for_analysis)
        
        final_scroll = scrolls  # Track where we ended up
        print(f"  [{filter_label}] Complete: {len(ads_found)} ads found, {ads_with_offers} with offers (ended at scroll {final_scroll})")
        if len(ads_found) < target_count:
            print(f"  [{filter_label}] NOTE: Found fewer ads than target. Will continue from scroll {final_scroll} on next attempt.")
        
        return ads_found, ads_with_offers, final_scroll, False
        
    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)
        print(f"  [{filter_label}] Fatal error: {error_type}: {error_msg}")
        import traceback
        print(f"  [{filter_label}] Traceback: {traceback.format_exc()}")
        return [], 0, start_scroll, False


async def scrape_ads_browser(
    search_term: str,
    target_count: int = 100,
    headless: bool = True,
    scroll_limit: int = 30,
    positive_keywords: Optional[List[str]] = None,
    negative_keywords: Optional[List[str]] = None,
    require_offers: bool = True,
    fresh_days: int = 7,
    proven_days: int = 30
) -> List[Dict[str, Any]]:
    """
    Scrape ads from Meta Ad Library - BOTH fresh and proven ads.
    
    Performs TWO scrapes using Facebook's sort options:
    1. PROVEN ads (sorted by "Impressions: high to low") - high-performing ads
    2. FRESH ads (sorted by "Most recent") - newest campaigns
    
    Args:
        search_term: The term to search for
        target_count: Total number of ads WITH VALID OFFERS to find
        headless: Whether to run browser in headless mode
        scroll_limit: Max scrolls per sort mode (default 30)
        positive_keywords: Required keywords (at least one must match)
        negative_keywords: Exclusion keywords (none can match)
        require_offers: Continue until target_count have valid offers
        fresh_days: Unused (kept for backward compatibility)
        proven_days: Unused (kept for backward compatibility)
        
    Returns:
        List of ad dictionaries with Haiku analysis and ad_type (fresh/proven)
    """
    if not PLAYWRIGHT_AVAILABLE:
        print("[ERROR] Playwright not installed. Run: pip install playwright && playwright install chromium")
        return []
    
    # Split target: 60% proven, 40% fresh
    proven_target = int(target_count * 0.6)
    fresh_target = target_count - proven_target
    
    print(f"[BROWSER] Scraping '{search_term}' - BOTH fresh and proven ads")
    print(f"=" * 60)
    print(f"  PROVEN: Target {proven_target} ads (sorted by Impressions: high to low)")
    print(f"  FRESH:  Target {fresh_target} ads (sorted by Most recent)")
    print(f"  TOTAL:  Target {target_count} ads with valid offers")
    print(f"=" * 60)
    
    all_ads = []
    seen_ids = set()
    total_with_offers = 0
    
    if not PLAYWRIGHT_AVAILABLE:
        print("[ERROR] Playwright not available")
        return []
    
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = await context.new_page()
        
        try:
            # SCRAPE 1: PROVEN ADS (sorted by Impressions: high to low)
            proven_ads, proven_offers, proven_retry_inactive = await _scrape_single_date_range(
                page, search_term, proven_target, scroll_limit,
                "total_impressions", "PROVEN",
                positive_keywords, negative_keywords, seen_ids, require_offers,
                include_inactive=False
            )
            all_ads.extend(proven_ads)
            total_with_offers += proven_offers
            
            # Retry PROVEN with inactive ads if threshold was hit
            if proven_retry_inactive:
                print(f"\n  [PROVEN] Retrying with INACTIVE ads included...")
                proven_ads_inactive, proven_offers_inactive, _ = await _scrape_single_date_range(
                    page, search_term, proven_target, scroll_limit,
                    "total_impressions", "PROVEN",
                    positive_keywords, negative_keywords, seen_ids, require_offers,
                    include_inactive=True
                )
                all_ads.extend(proven_ads_inactive)
                total_with_offers += proven_offers_inactive
            
            # SCRAPE 2: FRESH ADS (sorted by Most recent)
            fresh_ads, fresh_offers, fresh_retry_inactive = await _scrape_single_date_range(
                page, search_term, fresh_target, scroll_limit,
                "relevancy_monthly_grouped", "FRESH",
                positive_keywords, negative_keywords, seen_ids, require_offers,
                include_inactive=False
            )
            all_ads.extend(fresh_ads)
            total_with_offers += fresh_offers
            
            # Retry FRESH with inactive ads if threshold was hit
            if fresh_retry_inactive:
                print(f"\n  [FRESH] Retrying with INACTIVE ads included...")
                fresh_ads_inactive, fresh_offers_inactive, _ = await _scrape_single_date_range(
                    page, search_term, fresh_target, scroll_limit,
                    "relevancy_monthly_grouped", "FRESH",
                    positive_keywords, negative_keywords, seen_ids, require_offers,
                    include_inactive=True
                )
                all_ads.extend(fresh_ads_inactive)
                total_with_offers += fresh_offers_inactive
            
        finally:
            await browser.close()
    
    # Filter out ads with N/A offers if require_offers is True
    if require_offers:
        ads_with_valid_offers = [
            ad for ad in all_ads 
            if ad.get('haiku_offer') and ad.get('haiku_offer', '').upper() != 'N/A'
        ]
        # Keep some N/A ads as backup if we don't have enough
        ads_without_offers = [
            ad for ad in all_ads 
            if not ad.get('haiku_offer') or ad.get('haiku_offer', '').upper() == 'N/A'
        ]
        
        # Prioritize ads with offers, fill remaining with N/A ads if needed
        if len(ads_with_valid_offers) >= target_count:
            final_ads = ads_with_valid_offers[:target_count]
        else:
            # Not enough ads with offers - use what we have
            final_ads = ads_with_valid_offers
            print(f"  [NOTE] Only found {len(ads_with_valid_offers)} ads with valid offers (target: {target_count})")
    else:
        final_ads = all_ads
    
    # Summary
    proven_count = len([a for a in final_ads if a.get('ad_type') == 'proven'])
    fresh_count = len([a for a in final_ads if a.get('ad_type') == 'fresh'])
    offers_count = len([a for a in final_ads if a.get('haiku_offer') and a.get('haiku_offer', '').upper() != 'N/A'])
    
    print(f"\n[COMPLETE] Scraping finished:")
    print(f"  PROVEN ads: {proven_count}")
    print(f"  FRESH ads:  {fresh_count}")
    print(f"  TOTAL:      {len(final_ads)} (ALL have valid offers)")
    
    return final_ads


async def scrape_ads_with_unique_offers(
    search_term: str,
    target_unique_count: int = 50,
    headless: bool = True,
    scroll_limit: int = 30,
    positive_keywords: Optional[List[str]] = None,
    negative_keywords: Optional[List[str]] = None,
    fresh_days: int = 7,
    proven_days: int = 30
) -> Dict[str, Any]:
    """
    Scrape ads with AI-based unique offer filtering and retry logic.
    
    This function wraps scrape_ads_browser and adds:
    1. AI-based filtering to keep only meaningfully unique offers
    2. Retry logic to rescrape if not enough unique offers are found
    3. Persistent seen_ids across retries to avoid re-scraping the same ads
    
    Uses sort-based scraping:
    - PROVEN: sorted by "Impressions: high to low"
    - FRESH: sorted by "Most recent"
    
    Args:
        search_term: The term to search for
        target_unique_count: Target number of ads with UNIQUE offers
        headless: Whether to run browser in headless mode
        scroll_limit: Base max scrolls per sort mode
        positive_keywords: Required keywords
        negative_keywords: Exclusion keywords
        fresh_days: Unused (kept for backward compatibility)
        proven_days: Unused (kept for backward compatibility)
        
    Returns:
        Dictionary with:
        - 'ads': List of ads with unique offers
        - 'unique_count': Number of unique offers found
        - 'total_scraped': Total ads scraped across all attempts
        - 'duplicates_removed': Number of duplicate offers filtered
        - 'attempts': Number of scraping attempts made
        - 'target_met': Whether target_unique_count was achieved
        - 'offer_groups': Empty dict (kept for backward compatibility)
    """
    if not PLAYWRIGHT_AVAILABLE:
        print("[ERROR] Playwright not installed")
        return {
            'ads': [],
            'unique_count': 0,
            'total_scraped': 0,
            'duplicates_removed': 0,
            'attempts': 0,
            'target_met': False,
            'offer_groups': {}
        }
    
    # Check if unique offer filtering is enabled
    require_unique = getattr(config, 'REQUIRE_UNIQUE_OFFERS', True)
    max_retries = getattr(config, 'MAX_OFFER_DEDUPLICATION_RETRIES', 3)
    scroll_multiplier = getattr(config, 'OFFER_DEDUP_RETRY_SCROLL_MULTIPLIER', 1.5)
    scrape_multiplier = getattr(config, 'OFFER_DEDUP_SCRAPE_MULTIPLIER', 2.0)
    
    if not require_unique:
        # Just do a normal scrape without uniqueness filtering
        ads = await scrape_ads_browser(
            search_term=search_term,
            target_count=target_unique_count,
            headless=headless,
            scroll_limit=scroll_limit,
            positive_keywords=positive_keywords,
            negative_keywords=negative_keywords,
            require_offers=True,
            fresh_days=fresh_days,
            proven_days=proven_days
        )
        return {
            'ads': ads,
            'unique_count': len(ads),
            'total_scraped': len(ads),
            'duplicates_removed': 0,
            'attempts': 1,
            'target_met': len(ads) >= target_unique_count,
            'offer_groups': {}
        }
    
    print(f"\n{'='*60}")
    print(f"  UNIQUE OFFER SCRAPING")
    print(f"{'='*60}")
    print(f"  Target: {target_unique_count} UNIQUE offers")
    print(f"  Max retries: {max_retries}")
    print(f"  Scroll multiplier: 2x (doubles each retry)")
    print(f"{'='*60}\n")
    
    # Persistent state across retries
    global_seen_ids: set = set()
    all_unique_ads: List[Dict] = []
    total_scraped = 0
    total_duplicates_removed = 0
    
    from .hook_analyzer import filter_unique_offers_ai
    
    # Track scroll positions across retries (to continue where we left off)
    proven_scroll_position = 0
    fresh_scroll_position = 0
    
    # Track whether we've switched to include inactive ads
    proven_include_inactive = False
    fresh_include_inactive = False
    
    # Current scroll limit starts at base and doubles each retry
    current_scroll_limit = scroll_limit
    
    # Track which attempt we're on (for final logging)
    attempt = 0
    
    from playwright.async_api import async_playwright
    
    # Keep browser open across all retries for efficiency
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = await context.new_page()
        
        try:
            for attempt in range(1, max_retries + 1):
                # Calculate how many more unique offers we need
                needed = target_unique_count - len(all_unique_ads)
                if needed <= 0:
                    break
                
                # Calculate total ads with offers needed: 2x the unique count (for uniqueness filtering)
                total_ads_needed = needed * 2
                
                # Scrape target increases with each attempt
                scrape_target = int(total_ads_needed * (scrape_multiplier ** (attempt - 1)))
                
                # Double the scroll limit on each retry (starting from attempt 2)
                if attempt > 1:
                    current_scroll_limit = current_scroll_limit * 2
                
                print(f"\n[ATTEMPT {attempt}/{max_retries}] Scraping for {needed} more unique offers...")
                print(f"  Total ads with offers needed: {total_ads_needed} (2x {needed} for uniqueness filtering)")
                print(f"  Scrape target: {scrape_target} ads")
                print(f"  Already seen: {len(global_seen_ids)} ad IDs")
                print(f"  Scroll limit: {current_scroll_limit} scrolls")
                print(f"  Starting positions: PROVEN={proven_scroll_position}, FRESH={fresh_scroll_position}")
                
                # Split target: 60% proven, 40% fresh
                proven_target = int(scrape_target * 0.6)
                fresh_target = scrape_target - proven_target
                
                # PROVEN: sorted by Impressions: high to low
                # Continue from last scroll position
                proven_ads, _, proven_scroll_position, proven_retry_inactive = await _scrape_single_date_range_continuous(
                    page, search_term, proven_target, current_scroll_limit,
                    "total_impressions", "PROVEN",
                    positive_keywords, negative_keywords, global_seen_ids, True,
                    start_scroll=proven_scroll_position,
                    include_inactive=proven_include_inactive
                )
                
                # Retry PROVEN with inactive ads if threshold was hit
                if proven_retry_inactive and not proven_include_inactive:
                    proven_include_inactive = True
                    print(f"\n  [PROVEN] Retrying with INACTIVE ads included...")
                    proven_ads_inactive, _, proven_scroll_position, _ = await _scrape_single_date_range_continuous(
                        page, search_term, proven_target, current_scroll_limit,
                        "total_impressions", "PROVEN",
                        positive_keywords, negative_keywords, global_seen_ids, True,
                        start_scroll=0,  # Start fresh for inactive ads
                        include_inactive=True
                    )
                    proven_ads.extend(proven_ads_inactive)
                
                # FRESH: sorted by Most recent
                # Continue from last scroll position
                fresh_ads, _, fresh_scroll_position, fresh_retry_inactive = await _scrape_single_date_range_continuous(
                    page, search_term, fresh_target, current_scroll_limit,
                    "relevancy_monthly_grouped", "FRESH",
                    positive_keywords, negative_keywords, global_seen_ids, True,
                    start_scroll=fresh_scroll_position,
                    include_inactive=fresh_include_inactive
                )
                
                # Retry FRESH with inactive ads if threshold was hit
                if fresh_retry_inactive and not fresh_include_inactive:
                    fresh_include_inactive = True
                    print(f"\n  [FRESH] Retrying with INACTIVE ads included...")
                    fresh_ads_inactive, _, fresh_scroll_position, _ = await _scrape_single_date_range_continuous(
                        page, search_term, fresh_target, current_scroll_limit,
                        "relevancy_monthly_grouped", "FRESH",
                        positive_keywords, negative_keywords, global_seen_ids, True,
                        start_scroll=0,  # Start fresh for inactive ads
                        include_inactive=True
                    )
                    fresh_ads.extend(fresh_ads_inactive)
                
                # Combine new ads
                new_ads = proven_ads + fresh_ads
                
                # Filter to only ads with valid offers
                new_ads_with_offers = [
                    ad for ad in new_ads
                    if ad.get('haiku_offer') and ad.get('haiku_offer', '').upper() != 'N/A'
                ]
                
                total_scraped += len(new_ads)
                
                if not new_ads_with_offers:
                    print(f"  [ATTEMPT {attempt}] No new ads with offers found")
                    continue
                
                print(f"  [ATTEMPT {attempt}] Found {len(new_ads_with_offers)} new ads with offers")
                
                # Use AI to filter for unique offers only
                filter_result = filter_unique_offers_ai(new_ads_with_offers)
                
                new_unique_ads = filter_result.get('unique_ads', [])
                new_duplicates = filter_result.get('duplicates_removed', 0)
                
                # Add all AI-determined unique ads to our collection
                all_unique_ads.extend(new_unique_ads)
                total_duplicates_removed += new_duplicates
                
                print(f"  [ATTEMPT {attempt}] New unique offers found: {len(new_unique_ads)}")
                print(f"  [ATTEMPT {attempt}] Total unique offers: {len(all_unique_ads)}")
                
                if len(all_unique_ads) >= target_unique_count:
                    print(f"\n[SUCCESS] Target reached: {len(all_unique_ads)}/{target_unique_count} unique offers")
                    break
        finally:
            await browser.close()
    
    # Final result
    target_met = len(all_unique_ads) >= target_unique_count
    
    print(f"\n{'='*60}")
    print(f"  UNIQUE OFFER SCRAPING COMPLETE")
    print(f"{'='*60}")
    print(f"  Unique offers found: {len(all_unique_ads)}/{target_unique_count}")
    print(f"  Total ads scraped: {total_scraped}")
    print(f"  Duplicates removed: {total_duplicates_removed}")
    print(f"  Attempts used: {attempt}/{max_retries}")
    print(f"  Target met: {'YES' if target_met else 'NO'}")
    print(f"{'='*60}\n")
    
    return {
        'ads': all_unique_ads,
        'unique_count': len(all_unique_ads),
        'total_scraped': total_scraped,
        'duplicates_removed': total_duplicates_removed,
        'attempts': attempt,
        'target_met': target_met,
        'offer_groups': {}  # Empty for backward compatibility (no longer using groups)
    }
