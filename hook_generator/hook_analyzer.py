"""
Hook Analyzer Module - Uses Claude Haiku to extract structured hook/offer data from ads.

This module provides fast, cost-effective analysis of scraped ad content to extract:
- The core marketing hook (the main claim/angle/value proposition)
- The offer (price, discount, or promotion if present)

Cost optimizations:
- Caching: Results are cached to avoid re-analyzing the same ad content
- Deduplication: In-memory dedup prevents redundant processing in the same session
- Smart fallback: Regex extraction is tried first for simple cases
- Batch processing: Multiple ads can be analyzed in a single API call
"""

import json
import re
from typing import Dict, List, Optional

from . import api_keys
from . import config
from .rate_limiter import anthropic_limiter
from .logger import bot_logger
from .cache_manager import (
    get_cached, set_cached, check_dedup, set_dedup, track_cost
)


def _parse_json_response(content: str) -> Optional[Dict | List]:
    """
    Robustly parse JSON from AI response, handling:
    - Code blocks with ```json
    - Multiple JSON objects/arrays (extract first)
    - Extra text before/after JSON
    - Malformed JSON with recovery attempts
    
    Returns:
        Dict, List, or None if parsing fails
    """
    if not content:
        return None
    
    # Step 1: Extract from code blocks if present
    if "```" in content:
        parts = content.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            elif part.startswith("{"):
                # Might be JSON without the json label
                pass
            else:
                continue
            
            # Try to parse this part
            try:
                # Find first { or [ and try to extract complete JSON
                json_start = part.find('{')
                if json_start == -1:
                    json_start = part.find('[')
                if json_start == -1:
                    continue
                
                # Try to extract complete JSON object/array
                json_str = part[json_start:]
                result = _extract_first_json(json_str)
                if result is not None:
                    return result
            except:
                continue
    
    # Step 2: Try to find JSON in the raw content
    json_start = content.find('{')
    if json_start == -1:
        json_start = content.find('[')
    if json_start != -1:
        json_str = content[json_start:]
        result = _extract_first_json(json_str)
        if result is not None:
            return result
    
    # Step 3: Try parsing the whole content as-is (only if no JSON was found above)
    # This is a last resort - if we got here, _extract_first_json should have worked
    # But try direct parse in case it's simple, valid JSON
    try:
        parsed = json.loads(content.strip())
        # If successful, return it (but this might fail if there's extra data)
        return parsed
    except json.JSONDecodeError as e:
        # If it's an "extra data" error, try extraction one more time
        if "Extra data" in str(e):
            result = _extract_first_json(content.strip())
            if result is not None:
                return result
        # Otherwise, give up
        pass
    except:
        pass
    
    return None


def _extract_first_json(text: str) -> Optional[Dict | List]:
    """
    Extract the first complete JSON object or array from text.
    Handles nested structures and stops at the first complete JSON.
    
    Returns:
        Dict, List, or None if extraction fails
    """
    if not text:
        return None
    
    # Find the start of JSON
    start_idx = -1
    is_array = False
    
    for i, char in enumerate(text):
        if char == '{':
            start_idx = i
            is_array = False
            break
        elif char == '[':
            start_idx = i
            is_array = True
            break
    
    if start_idx == -1:
        return None
    
    # Find the matching closing brace/bracket
    depth = 0
    in_string = False
    escape_next = False
    
    for i in range(start_idx, len(text)):
        char = text[i]
        
        if escape_next:
            escape_next = False
            continue
        
        if char == '\\':
            escape_next = True
            continue
        
        if char == '"' and not escape_next:
            in_string = not in_string
            continue
        
        if in_string:
            continue
        
        if char == '{' or char == '[':
            depth += 1
        elif char == '}' or char == ']':
            depth -= 1
            if depth == 0:
                # Found complete JSON
                json_str = text[start_idx:i + 1]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    return None
    
    return None


def analyze_ad_hook(ad_body: str, page_name: str) -> Dict[str, str]:
    """
    Use Claude Haiku to extract structured hook/offer from ad content.
    
    Implements cost optimization:
    1. Check in-memory dedup cache first
    2. Check persistent cache second  
    3. Try regex fallback if enabled and applicable
    4. Fall back to API call only if needed
    
    Args:
        ad_body: The ad's body text
        page_name: The advertiser's page/business name
        
    Returns:
        {
            'hook': 'The extracted marketing hook',
            'offer': 'The extracted offer/price or N/A',
            'confidence': 'high/medium/low'
        }
    """
    if not ad_body or len(ad_body.strip()) < 10:
        return {'hook': '', 'offer': 'N/A', 'confidence': 'low'}
    
    # Filter out ads that are mostly UI junk text
    junk_patterns = [
        "see ad detail", "library id", "started running", "open dropdown",
        "sponsored", "low impression count", "learn more", "send message",
        "watch more", "download", "visit instagram", "impressions:"
    ]
    ad_lower = ad_body.lower()
    junk_matches = sum(1 for pattern in junk_patterns if pattern in ad_lower)
    # If more than 30% of the content seems to be junk UI text, skip API call
    if junk_matches >= 3 or (len(ad_body) < 50 and junk_matches >= 1):
        return {'hook': '', 'offer': 'N/A', 'confidence': 'low'}
    
    # 1. Check in-memory dedup cache
    dedup_result = check_dedup(ad_body)
    if dedup_result is not None:
        return dedup_result
    
    # 2. Check persistent cache
    cache_key = f"{page_name}:{ad_body[:500]}"
    cached_result = get_cached('ad_analysis', cache_key)
    if cached_result is not None:
        set_dedup(ad_body, cached_result)  # Add to session dedup
        return cached_result
    
    # 3. Try smart fallback (regex) first if enabled
    if config.USE_REGEX_FALLBACK_FIRST:
        fallback_result = _fallback_extract(ad_body)
        
        # If regex found a good offer and text is short, use fallback
        if fallback_result['offer'] != 'N/A' and fallback_result['confidence'] != 'low':
            set_dedup(ad_body, fallback_result)
            set_cached('ad_analysis', cache_key, fallback_result)
            return fallback_result
        
        # If text is too short, use fallback (not worth API call)
        if len(ad_body) < config.MIN_TEXT_LENGTH_FOR_API:
            set_dedup(ad_body, fallback_result)
            set_cached('ad_analysis', cache_key, fallback_result)
            return fallback_result
    
    # 4. Initialize client if needed
    if not api_keys.ANTHROPIC_CLIENT:
        api_keys.initialize_clients()
    
    if not api_keys.ANTHROPIC_CLIENT:
        # Fallback: simple extraction
        result = _fallback_extract(ad_body)
        set_dedup(ad_body, result)
        return result
    
    # 5. Use API call with tiered model selection
    model = api_keys.get_model_for_task('ad_analysis')
    prompt = config.AI_PROMPTS['hook_analyzer'].format(
        page_name=page_name,
        ad_body=ad_body[:1500]
    )

    try:
        anthropic_limiter.wait()
        response = api_keys.ANTHROPIC_CLIENT.messages.create(
            model=model,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        
        # Track cost
        if hasattr(response, 'usage'):
            track_cost(model, response.usage.input_tokens, response.usage.output_tokens)
        
        # Safely extract text from response
        if response.content and len(response.content) > 0:
            content_block = response.content[0]
            if hasattr(content_block, 'text'):
                content = content_block.text.strip()
            else:
                content = str(content_block).strip()
        else:
            content = ""
        
        # Parse JSON from response using robust parser
        result = _parse_json_response(content)
        
        if result is None:
            raise ValueError("Could not parse JSON from response")
        
        # Ensure required keys exist
        if isinstance(result, dict):
            final_result = {
                'hook': result.get('hook', ''),
                'offer': result.get('offer', 'N/A'),
                'confidence': result.get('confidence', 'medium')
            }
        else:
            # If result is a list or other type, create default result
            final_result = {
                'hook': '',
                'offer': 'N/A',
                'confidence': 'low'
            }
        
        # Cache the result
        set_dedup(ad_body, final_result)
        set_cached('ad_analysis', cache_key, final_result)
        
        return final_result
        
    except Exception as e:
        error_msg = str(e)
        # Log more details for JSON parsing errors
        if "Extra data" in error_msg or "JSON" in error_msg or "json" in error_msg:
            print(f"[WARNING] Haiku analysis failed (JSON parse error): {error_msg}")
            # Log a snippet of the problematic content for debugging
            try:
                content_snippet = "N/A"
                # Try to get response from outer scope if available
                try:
                    if 'response' in locals():
                        resp = locals()['response']
                        if resp and hasattr(resp, 'content') and resp.content and len(resp.content) > 0:
                            content_block = resp.content[0]
                            if hasattr(content_block, 'text'):
                                content_snippet = content_block.text[:200]
                            else:
                                content_snippet = str(content_block)[:200]
                except:
                    pass
                print(f"[WARNING] Response snippet: {content_snippet}...")
            except:
                pass
        else:
            print(f"[WARNING] Haiku analysis failed: {error_msg}")
        result = _fallback_extract(ad_body)
        set_dedup(ad_body, result)
        return result


def _fallback_extract(ad_body: str) -> Dict[str, str]:
    """
    Fallback extraction when Claude is unavailable.
    Uses simple heuristics to extract hook and offer.
    
    Returns 'medium' confidence when a clear offer pattern is found,
    which allows the smart fallback logic to skip the API call.
    """
    # Hook: first sentence or two
    sentences = re.split(r'(?<=[.!?])\s+', ad_body)
    hook = sentences[0] if sentences else ad_body[:200]
    
    ad_lower = ad_body.lower()
    offer = "N/A"
    confidence = "low"
    
    # Priority 1: Percentage discounts (high confidence patterns)
    pct_match = re.search(r'(\d{1,2})\s*%\s*off', ad_lower)
    if pct_match:
        offer = f"{pct_match.group(1)}% OFF"
        confidence = "medium"  # Good enough to skip API
    
    # Priority 2: Free offers (high confidence patterns)
    elif re.search(r'free\s+(?:estimate|quote|consultation|trial|sample)', ad_lower):
        free_match = re.search(r'free\s+(?:estimate|quote|consultation|trial|sample)', ad_lower)
        offer = free_match.group(0).title()
        confidence = "medium"  # Good enough to skip API
    
    # Priority 3: Meaningful prices ($10+ to avoid "$1" from "1,500 homeowners")
    elif re.search(r'\$(\d{2,})', ad_body):
        price_match = re.search(r'\$(\d{2,}(?:,\d{3})*(?:\.\d{2})?)', ad_body)
        if price_match:
            offer = f"${price_match.group(1)}"
            confidence = "medium"  # Good enough to skip API
    
    # Priority 4: Generic "free" something
    elif 'free' in ad_lower:
        free_match = re.search(r'free\s+\w+', ad_lower)
        if free_match:
            offer = free_match.group(0).title()
            confidence = "low"  # Less certain, may want API
    
    return {
        'hook': hook.strip(),
        'offer': offer,
        'confidence': confidence
    }


def analyze_hooks_batch(ads: List[Dict]) -> List[Dict]:
    """
    Batch process ads with Claude Haiku analysis.
    
    Uses caching and deduplication for cost efficiency.
    
    Args:
        ads: List of ad dictionaries with 'page_name' and 'ad_creative_bodies'
        
    Returns:
        The same ads list with 'haiku_hook' and 'haiku_offer' fields added
    """
    if not ads:
        return ads
    
    analyzed_count = 0
    cache_hits = 0
    
    for ad in ads:
        page_name = ad.get('page_name', 'Unknown')
        bodies = ad.get('ad_creative_bodies', [])
        body_text = bodies[0] if bodies else ""
        
        if body_text:
            # Check if this was cached (analyze_ad_hook handles this internally)
            cache_key = f"{page_name}:{body_text[:500]}"
            was_cached = get_cached('ad_analysis', cache_key) is not None
            
            result = analyze_ad_hook(body_text, page_name)
            ad['haiku_hook'] = result.get('hook', '')
            ad['haiku_offer'] = result.get('offer', 'N/A')
            ad['haiku_confidence'] = result.get('confidence', 'low')
            analyzed_count += 1
            
            if was_cached:
                cache_hits += 1
            
            # Progress update every 10 ads
            if analyzed_count % 10 == 0:
                print(f"  [HAIKU] Analyzed {analyzed_count}/{len(ads)} ads (cache hits: {cache_hits})...")
    
    print(f"  [HAIKU] Completed {analyzed_count} ad analyses (cache hits: {cache_hits})")
    return ads


def analyze_hooks_batch_efficient(ads: List[Dict], batch_size: Optional[int] = None) -> List[Dict]:
    """
    Analyze multiple ads in a SINGLE API call for maximum efficiency.
    
    This batches multiple ads together and sends them to Claude in one request,
    dramatically reducing API call overhead (up to 90% cost savings on high volume).
    
    Args:
        ads: List of ad dictionaries with 'page_name' and 'ad_creative_bodies'
        batch_size: Number of ads per API call (default from config.BATCH_SIZES)
        
    Returns:
        The same ads list with analysis fields added
    """
    if not ads:
        return ads
    
    if batch_size is None:
        batch_size = api_keys.get_batch_size('ad_analysis')
    
    # Initialize client if needed
    if not api_keys.ANTHROPIC_CLIENT:
        api_keys.initialize_clients()
    
    if not api_keys.ANTHROPIC_CLIENT:
        # Fallback to individual analysis
        return analyze_hooks_batch(ads)
    
    # Separate ads that need API calls from those that are cached
    ads_needing_api = []
    for i, ad in enumerate(ads):
        page_name = ad.get('page_name', 'Unknown')
        bodies = ad.get('ad_creative_bodies', [])
        body_text = bodies[0] if bodies else ""
        
        if not body_text or len(body_text.strip()) < 10:
            ad['haiku_hook'] = ''
            ad['haiku_offer'] = 'N/A'
            ad['haiku_confidence'] = 'low'
            continue
        
        # Check cache first
        cache_key = f"{page_name}:{body_text[:500]}"
        cached = get_cached('ad_analysis', cache_key)
        if cached is not None:
            ad['haiku_hook'] = cached.get('hook', '')
            ad['haiku_offer'] = cached.get('offer', 'N/A')
            ad['haiku_confidence'] = cached.get('confidence', 'low')
            continue
        
        # Try regex fallback
        if config.USE_REGEX_FALLBACK_FIRST:
            fallback = _fallback_extract(body_text)
            if fallback['offer'] != 'N/A' and fallback['confidence'] != 'low':
                ad['haiku_hook'] = fallback['hook']
                ad['haiku_offer'] = fallback['offer']
                ad['haiku_confidence'] = fallback['confidence']
                set_cached('ad_analysis', cache_key, fallback)
                continue
        
        ads_needing_api.append((i, ad, page_name, body_text))
    
    print(f"  [BATCH] {len(ads) - len(ads_needing_api)} ads resolved from cache/fallback")
    
    if not ads_needing_api:
        return ads
    
    # Process in batches
    model = api_keys.get_model_for_task('ad_analysis')
    processed = 0
    
    for batch_start in range(0, len(ads_needing_api), batch_size):
        batch = ads_needing_api[batch_start:batch_start + batch_size]
        
        # Build batch prompt
        batch_prompt = """Analyze these Facebook ads and extract hooks/offers for EACH one.

Return a JSON array with one object per ad in the same order:
[
  {"ad_index": 1, "hook": "...", "offer": "...", "confidence": "high/medium/low"},
  ...
]

ADS TO ANALYZE:
"""
        for j, (_, ad, page_name, body_text) in enumerate(batch, 1):
            batch_prompt += f"\n--- AD {j} (from {page_name}) ---\n{body_text[:800]}\n"
        
        try:
            anthropic_limiter.wait()
            response = api_keys.ANTHROPIC_CLIENT.messages.create(
                model=model,
                max_tokens=1000,
                messages=[{"role": "user", "content": batch_prompt}]
            )
            
            # Track cost
            if hasattr(response, 'usage'):
                track_cost(model, response.usage.input_tokens, response.usage.output_tokens)
            
            # Safely extract text from response
            if response.content and len(response.content) > 0:
                content_block = response.content[0]
                if hasattr(content_block, 'text'):
                    content = content_block.text.strip()
                else:
                    content = str(content_block).strip()
            else:
                content = ""
            
            # Parse JSON array from response using robust parser
            parsed = _parse_json_response(content)
            
            if parsed is None:
                raise ValueError("Could not parse JSON from batch response")
            
            # Handle both single object and array responses
            if isinstance(parsed, list):
                results = parsed
            else:
                # If single object, wrap in array
                results = [parsed]
            
            # Apply results to ads
            for j, (idx, ad, page_name, body_text) in enumerate(batch):
                if j < len(results):
                    result = results[j]
                    # Ensure result is a dict before calling .get()
                    if not isinstance(result, dict):
                        bot_logger.warning(f"Expected dict but got {type(result).__name__} for ad {j}")
                        continue
                    ad['haiku_hook'] = result.get('hook', '')
                    ad['haiku_offer'] = result.get('offer', 'N/A')
                    ad['haiku_confidence'] = result.get('confidence', 'medium')
                    
                    # Cache individual result
                    cache_key = f"{page_name}:{body_text[:500]}"
                    set_cached('ad_analysis', cache_key, {
                        'hook': ad['haiku_hook'],
                        'offer': ad['haiku_offer'],
                        'confidence': ad['haiku_confidence']
                    })
                else:
                    # Fallback if result missing
                    fallback = _fallback_extract(body_text)
                    ad['haiku_hook'] = fallback['hook']
                    ad['haiku_offer'] = fallback['offer']
                    ad['haiku_confidence'] = fallback['confidence']
            
            processed += len(batch)
            print(f"  [BATCH] Processed {processed}/{len(ads_needing_api)} ads in batch API call")
            
        except Exception as e:
            print(f"[WARNING] Batch analysis failed: {e}, falling back to individual")
            for idx, ad, page_name, body_text in batch:
                result = analyze_ad_hook(body_text, page_name)
                ad['haiku_hook'] = result.get('hook', '')
                ad['haiku_offer'] = result.get('offer', 'N/A')
                ad['haiku_confidence'] = result.get('confidence', 'low')
    
    return ads


def batch_extract_hooks(ads: List[Dict], max_batch_size: int = 50, use_efficient_batch: bool = True) -> List[Dict]:
    """
    Extract hooks from a batch of ads.
    
    Args:
        ads: List of ad dictionaries
        max_batch_size: Maximum ads to process (default 50)
        use_efficient_batch: Use the efficient single-API-call batch method
        
    Returns:
        Processed ads with hook analysis
    """
    if len(ads) > max_batch_size:
        print(f"[INFO] Limiting Haiku analysis to first {max_batch_size} ads")
        ads_to_analyze = ads[:max_batch_size]
        remaining = ads[max_batch_size:]
        
        if use_efficient_batch:
            analyzed = analyze_hooks_batch_efficient(ads_to_analyze)
        else:
            analyzed = analyze_hooks_batch(ads_to_analyze)
        return analyzed + remaining
    
    if use_efficient_batch:
        return analyze_hooks_batch_efficient(ads)
    return analyze_hooks_batch(ads)


def _split_groups_by_numeric_values(offer_groups: Dict[str, List[int]], ads: List[Dict]) -> Dict[str, List[int]]:
    """
    Post-process AI groups to split any group that contains offers with different numeric values.
    
    This ensures that "10% off" and "15% off" are treated as separate offers even if the AI
    grouped them together as "Percentage Discounts".
    
    Args:
        offer_groups: Dictionary mapping canonical offer descriptions to lists of ad indices
        ads: Full list of ads
        
    Returns:
        Updated offer_groups with split groups
    """
    import re
    split_groups = {}
    
    for canonical, indices in offer_groups.items():
        # Get actual offer texts for this group
        group_offers = []
        for idx in indices:
            if idx < len(ads):
                offer = ads[idx].get('haiku_offer', '').strip()
                if offer and offer.upper() != 'N/A':
                    group_offers.append((idx, offer))
        
        if not group_offers:
            # No offers found, keep original group
            split_groups[canonical] = indices
            continue
        
        # Extract numeric values from each offer and group by value
        numeric_groups = {}  # Maps normalized value -> list of (idx, offer)
        
        for idx, offer in group_offers:
            offer_lower = offer.lower()
            grouped = False
            
            # Extract percentage (e.g., "10% off", "15% discount")
            pct_match = re.search(r'(\d+)\s*%', offer_lower)
            if pct_match:
                pct_value = pct_match.group(1)
                key = f"pct_{pct_value}"
                if key not in numeric_groups:
                    numeric_groups[key] = []
                numeric_groups[key].append((idx, offer))
                grouped = True
                continue
            
            # Extract dollar amount (e.g., "$99", "$199", "$1,000")
            price_match = re.search(r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)', offer_lower)
            if price_match:
                price_value = price_match.group(1).replace(',', '').replace('.', '')
                key = f"price_{price_value}"
                if key not in numeric_groups:
                    numeric_groups[key] = []
                numeric_groups[key].append((idx, offer))
                grouped = True
                continue
            
            # Extract age (e.g., "65+", "55+", "for seniors 65+")
            age_match = re.search(r'(\d+)\s*\+', offer_lower)
            if age_match:
                age_value = age_match.group(1)
                key = f"age_{age_value}"
                if key not in numeric_groups:
                    numeric_groups[key] = []
                numeric_groups[key].append((idx, offer))
                grouped = True
                continue
            
            # Extract quantity (e.g., "First 10 customers", "First 100 customers", "Only 5 spots")
            qty_match = re.search(r'(?:first|next|only)\s+(\d+)', offer_lower)
            if qty_match:
                qty_value = qty_match.group(1)
                key = f"qty_{qty_value}"
                if key not in numeric_groups:
                    numeric_groups[key] = []
                numeric_groups[key].append((idx, offer))
                grouped = True
                continue
            
            # Extract save amount (e.g., "Save $500", "Save $1000")
            save_match = re.search(r'save\s+\$(\d+(?:,\d{3})*)', offer_lower)
            if save_match:
                save_value = save_match.group(1).replace(',', '')
                key = f"save_{save_value}"
                if key not in numeric_groups:
                    numeric_groups[key] = []
                numeric_groups[key].append((idx, offer))
                grouped = True
                continue
            
            # No numeric value found - keep in original group
            if "no_numeric" not in numeric_groups:
                numeric_groups["no_numeric"] = []
            numeric_groups["no_numeric"].append((idx, offer))
        
        # If we found multiple numeric groups, split them
        if len(numeric_groups) > 1:
            for key, group_items in numeric_groups.items():
                # Create a more specific canonical name based on the numeric value
                sample_offer = group_items[0][1]
                if key.startswith("pct_"):
                    pct_val = key.split('_')[1]
                    new_canonical = f"{pct_val}% discount"
                elif key.startswith("price_"):
                    price_val = key.split('_')[1]
                    # Format with commas for readability
                    if len(price_val) > 3:
                        price_val = f"{int(price_val):,}"
                    new_canonical = f"${price_val} offer"
                elif key.startswith("age_"):
                    age_val = key.split('_')[1]
                    new_canonical = f"Age {age_val}+ offer"
                elif key.startswith("qty_"):
                    qty_val = key.split('_')[1]
                    new_canonical = f"Quantity {qty_val} offer"
                elif key.startswith("save_"):
                    save_val = key.split('_')[1]
                    if len(save_val) > 3:
                        save_val = f"{int(save_val):,}"
                    new_canonical = f"Save ${save_val} offer"
                else:
                    new_canonical = canonical  # Keep original for non-numeric
                
                split_groups[new_canonical] = [idx for idx, _ in group_items]
        else:
            # Only one numeric group or no numeric values - keep original
            split_groups[canonical] = indices
    
    return split_groups


def filter_unique_offers_ai(ads: List[Dict], target_count: Optional[int] = None) -> Dict[str, any]:
    """
    Use Claude Haiku to filter ads down to only those with meaningfully unique offers.
    
    This function sends offers to Haiku in batches (max 50 per batch) and asks it to identify 
    which offers are unique. If multiple ads have the same offer (e.g., 10 ads with "5% off"), 
    only ONE index will be returned for that offer.
    
    Args:
        ads: List of ad dictionaries with 'haiku_offer' already extracted
        target_count: Optional target number of unique offers to return
        
    Returns:
        Dictionary with:
        - 'unique_ads': List of ads with unique offers (one per unique offer)
        - 'total_analyzed': Total number of ads analyzed
        - 'duplicates_removed': Number of duplicate offers removed
        - 'offer_groups': Empty dict (kept for backward compatibility)
    """
    if not ads:
        return {
            'unique_ads': [],
            'total_analyzed': 0,
            'duplicates_removed': 0,
            'offer_groups': {}
        }
    
    # Filter to only ads with valid offers
    ads_with_offers = [
        (i, ad) for i, ad in enumerate(ads)
        if ad.get('haiku_offer') and ad.get('haiku_offer', '').upper() != 'N/A'
    ]
    
    if not ads_with_offers:
        print("[UNIQUE OFFERS] No ads with valid offers to filter")
        return {
            'unique_ads': [],
            'total_analyzed': len(ads),
            'duplicates_removed': 0,
            'offer_groups': {}
        }
    
    print(f"[UNIQUE OFFERS] Analyzing {len(ads_with_offers)} offers for uniqueness...")
    
    # Initialize client if needed
    if not api_keys.ANTHROPIC_CLIENT:
        api_keys.initialize_clients()
    
    if not api_keys.ANTHROPIC_CLIENT:
        # Fallback: simple string-based deduplication
        print("[UNIQUE OFFERS] No API client, using simple string dedup")
        return _fallback_unique_offers(ads, ads_with_offers)
    
    # Batch size for Haiku (max 50 offers per batch)
    BATCH_SIZE = 50
    model = api_keys.get_model_for_task('ad_analysis')
    
    # Process in batches
    all_batch_unique_indices = []
    total_batches = (len(ads_with_offers) + BATCH_SIZE - 1) // BATCH_SIZE
    
    if total_batches > 1:
        print(f"[UNIQUE OFFERS] Processing {len(ads_with_offers)} offers in {total_batches} batches (max {BATCH_SIZE} per batch)")
    
    for batch_num in range(total_batches):
        batch_start = batch_num * BATCH_SIZE
        batch_end = min(batch_start + BATCH_SIZE, len(ads_with_offers))
        batch_ads = ads_with_offers[batch_start:batch_end]
        
        if total_batches > 1:
            print(f"[UNIQUE OFFERS] Processing batch {batch_num + 1}/{total_batches} ({len(batch_ads)} offers)...")
        
        # Build the list of offers for this batch
        offer_list = []
        for idx, ad in batch_ads:
            # Get ad body text for context (first 200 chars to check relevance)
            ad_bodies = ad.get('ad_creative_bodies', [])
            ad_body = ad_bodies[0] if ad_bodies else ''
            ad_context = ad_body[:200] if ad_body else ''
            
            offer_list.append({
                'index': idx,
                'offer': ad.get('haiku_offer', ''),
                'page_name': ad.get('page_name', 'Unknown'),
                'ad_context': ad_context
            })
        
        # Build the prompt for this batch
        offers_text = "\n".join([
            f"{i+1}. [{o['index']}] Offer: \"{o['offer']}\" | Page: {o['page_name']} | Ad context: {o['ad_context'][:150] if o['ad_context'] else 'N/A'}"
            for i, o in enumerate(offer_list)
        ])
        
        prompt = f"""Analyze these Facebook ad offers and identify which ones are MEANINGFULLY UNIQUE and ACTIONABLE.

You are an elite direct-response marketing analyst. Your job is to read the ad, landing page copy, or offer description below and extract ONLY the true core offer. Return the offer as a single sentence in this exact format and tone: “A [personalized / custom / specific] [thing] to get [desired outcome]” Rules: - Do NOT summarize the ad - Do NOT include branding, hype, or marketing language - Do NOT include bullet points - Do NOT include explanations - Do NOT add adjectives unless they are required to preserve meaning - Do NOT include price unless it is free - The output must be one single sentence - It must be phrased as a tangible exchange of value You are translating marketing fluff into what the user is actually being offered.

OFFERS TO ANALYZE:
{offers_text}

Return JSON with ONLY a list of unique offer indices (only include offers that pass all validation requirements):
{{
    "unique_indices": [list of ad indices, one per unique offer]
}}

Return ONLY valid JSON, no other text."""

        try:
            anthropic_limiter.wait()
            
            response = api_keys.ANTHROPIC_CLIENT.messages.create(
                model=model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            # Track cost
            if hasattr(response, 'usage'):
                track_cost(model, response.usage.input_tokens, response.usage.output_tokens)
            
            # Extract response content
            content = ""
            if response.content and len(response.content) > 0:
                content_block = response.content[0]
                if hasattr(content_block, 'text'):
                    content = content_block.text.strip()
                else:
                    content = str(content_block).strip()
            
            # Parse JSON response
            parsed = _parse_json_response(content)
            
            if parsed is None:
                print(f"[UNIQUE OFFERS] Batch {batch_num + 1} failed to parse, using fallback for this batch")
                # Use fallback for this batch
                batch_fallback = _fallback_unique_offers(ads, batch_ads)
                all_batch_unique_indices.extend(batch_fallback.get('unique_indices', []))
                continue
            
            # Handle case where parsed might be a list instead of dict
            if isinstance(parsed, list):
                print(f"[UNIQUE OFFERS] Batch {batch_num + 1} received list instead of dict, using fallback")
                batch_fallback = _fallback_unique_offers(ads, batch_ads)
                all_batch_unique_indices.extend(batch_fallback.get('unique_indices', []))
                continue
            
            # Now we know parsed is a dict, safe to use .get()
            if not isinstance(parsed, dict):
                print(f"[UNIQUE OFFERS] Batch {batch_num + 1} unexpected response type, using fallback")
                batch_fallback = _fallback_unique_offers(ads, batch_ads)
                all_batch_unique_indices.extend(batch_fallback.get('unique_indices', []))
                continue
            
            batch_unique_indices = parsed.get('unique_indices', [])
            
            # Validate indices for this batch
            batch_valid_indices = set(idx for idx, _ in batch_ads)
            batch_unique_indices = [idx for idx in batch_unique_indices if idx in batch_valid_indices]
            
            all_batch_unique_indices.extend(batch_unique_indices)
            
        except Exception as e:
            print(f"[UNIQUE OFFERS] Batch {batch_num + 1} AI filtering failed: {e}, using fallback for this batch")
            batch_fallback = _fallback_unique_offers(ads, batch_ads)
            all_batch_unique_indices.extend(batch_fallback.get('unique_indices', []))
    
    # Now deduplicate across batches (offers might be duplicates across batches)
    # We'll use a simple approach: keep the first occurrence of each unique offer
    seen_offers = {}
    final_unique_indices = []
    
    valid_indices = set(idx for idx, _ in ads_with_offers)
    
    for idx in all_batch_unique_indices:
        if idx not in valid_indices:
            continue
        
        ad = ads[idx]
        offer = ad.get('haiku_offer', '').lower().strip()
        
        # Normalize offer for comparison
        normalized = offer
        normalized = re.sub(r'\s+', ' ', normalized)
        
        # Check if we've seen this offer before
        if normalized not in seen_offers:
            seen_offers[normalized] = idx
            final_unique_indices.append(idx)
    
    if not final_unique_indices:
        print("[UNIQUE OFFERS] No valid unique indices returned after batching, using fallback")
        return _fallback_unique_offers(ads, ads_with_offers)
    
    # Apply target_count limit if specified
    if target_count and len(final_unique_indices) > target_count:
        final_unique_indices = final_unique_indices[:target_count]
    
    # Build result - one ad per unique offer
    unique_ads = [ads[idx] for idx in final_unique_indices]
    duplicates_removed = len(ads_with_offers) - len(unique_ads)
    
    print(f"[UNIQUE OFFERS] Found {len(unique_ads)} unique offers (removed {duplicates_removed} duplicates)")
    
    # Log the actual unique offers selected
    if unique_ads:
        print(f"[UNIQUE OFFERS] Selected unique offers:")
        for i, ad in enumerate(unique_ads[:10], 1):  # Show first 10
            offer = ad.get('haiku_offer', 'N/A')
            page = ad.get('page_name', 'Unknown')
            print(f"  {i}. \"{offer}\" (from {page})")
        if len(unique_ads) > 10:
            print(f"  ... and {len(unique_ads) - 10} more unique offers")
    
    return {
        'unique_ads': unique_ads,
        'total_analyzed': len(ads),
        'duplicates_removed': duplicates_removed,
        'offer_groups': {},  # Empty for backward compatibility
        'unique_indices': final_unique_indices
    }


def _fallback_unique_offers(ads: List[Dict], ads_with_offers: List[tuple]) -> Dict[str, any]:
    """
    Fallback unique offer filtering using simple string normalization.
    
    Used when the AI is unavailable or fails.
    """
    seen_offers = {}
    unique_ads = []
    offer_groups = {}
    
    for idx, ad in ads_with_offers:
        offer = ad.get('haiku_offer', '').lower().strip()
        
        # Normalize common variations
        normalized = offer
        normalized = re.sub(r'\s+', ' ', normalized)  # Collapse whitespace
        normalized = re.sub(r'(\d+)\s*%\s*(off|discount)', r'\1% off', normalized)  # Normalize percentages
        normalized = re.sub(r'free\s+(estimate|quote|consultation)', 'free estimate', normalized)
        normalized = re.sub(r'\$(\d+)\s*(per|/)\s*(room|sq\s*ft)', r'$\1/room', normalized)
        
        if normalized not in seen_offers:
            seen_offers[normalized] = idx
            unique_ads.append(ad)
            offer_groups[normalized] = [idx]
        else:
            # Add to existing group
            if normalized in offer_groups:
                offer_groups[normalized].append(idx)
    
    duplicates_removed = len(ads_with_offers) - len(unique_ads)
    
    print(f"[UNIQUE OFFERS] Fallback: Found {len(unique_ads)} unique offers (removed {duplicates_removed} duplicates)")
    
    return {
        'unique_ads': unique_ads,
        'total_analyzed': len(ads),
        'duplicates_removed': duplicates_removed,
        'offer_groups': offer_groups,
        'unique_indices': list(seen_offers.values())
    }