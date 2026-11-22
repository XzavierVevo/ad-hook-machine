"""
Facebook Ad Library browser scraping for comprehensive competitor analysis.
Pulls competitor ad data, extracts hooks from videos/images, and identifies patterns to avoid.
"""

import requests
import json
import time
import base64
import tempfile
import re
import os
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib

from . import config
from . import api_keys
from .rate_limiter import openai_limiter, anthropic_limiter, run_multithreaded, meta_limiter
from .logger import bot_logger, log_data
from .browser_scraper import scrape_ads_browser, scrape_ads_with_unique_offers


# NOTE: AdRelevanceScorer class has been REMOVED and replaced with the unified
# keyword system in keyword_generator.py. The browser_scraper.py now handles
# all keyword filtering via positive_keywords and negative_keywords parameters.


def search_competitor_ads_tiered(
    search_terms: List[str],
    positive_keywords: Optional[List[str]] = None,
    negative_keywords: Optional[List[str]] = None,
    target_count: Optional[int] = None,
    max_ads: int = 30
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Search for ads using browser scraping with a single keyword.
    
    Args:
        search_terms: List of search terms (only first one is used initially)
        positive_keywords: List of positive/required keywords (at least one must match)
        negative_keywords: List of negative/exclusion keywords (none can match)
        target_count: Target number of unique qualified ads to find
    """

    results = {
        "fresh": [],       # < 1 week
        "established": [], # 1-4 weeks
        "proven": []       # > 4 weeks
    }
    
    # Use provided target_count or fall back to config
    if target_count is None:
        target_count = getattr(config, 'QUALIFIED_ADS_PER_TIMEFRAME', 15)
    
    # Pull extra to account for anti-pattern filtering
    total_target = max(int(target_count * 2.0), 30) if target_count else 30
    
    # -------------------------------------------------------------------------
    # BROWSER METHOD - Run ONCE with the primary keyword
    # -------------------------------------------------------------------------
    import asyncio
    all_raw_ads = []
    seen_ids = set()
    
    def run_async_browser(term, target, pos_kw=None, neg_kw=None, require_offers=True):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(scrape_ads_browser(
                term, target, 
                positive_keywords=pos_kw,
                negative_keywords=neg_kw,
                require_offers=require_offers,
                scroll_limit=max_ads,
                fresh_days=7,    # Ads started within last 7 days
                proven_days=30   # Ads running 30+ days
            ))
        finally:
            loop.close()

    # Use ONLY the first (primary) search term
    primary_term = search_terms[0] if search_terms else ""
    if not primary_term:
        print("[ERROR] No search term provided")
        return results
        
    try:
        from concurrent.futures import ThreadPoolExecutor
        
        # SINGLE SCRAPE: Run browser once with the primary keyword
        # Filtering is done directly in browser_scraper via positive/negative keywords
        print(f"[BROWSER] Scraping ads for: '{primary_term}'...")
        if positive_keywords:
            print(f"  [FILTER] Positive: {', '.join(positive_keywords)}")
        if negative_keywords:
            print(f"  [FILTER] Negative: {', '.join(negative_keywords[:5])}{'...' if len(negative_keywords) > 5 else ''}")
        
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                run_async_browser, 
                primary_term, 
                total_target,
                positive_keywords,
                negative_keywords,
                True  # require_offers - continue until we have enough ads with valid offers
            )
            scraped_ads = future.result()
        
        # All ads returned have already been filtered by browser_scraper
        if scraped_ads:
            for ad in scraped_ads:
                if ad['id'] not in seen_ids:
                    all_raw_ads.append(ad)
                    seen_ids.add(ad['id'])
            
            print(f"[OK] Found {len(all_raw_ads)} qualified ads (pre-filtered by browser)")
        
    except Exception as e:
        print(f"[ERROR] Browser scraping failed: {e}")
    
    # -------------------------------------------------------------------------
    # LOCAL CATEGORIZATION
    # -------------------------------------------------------------------------
    now = datetime.now()
    print(f"[INFO] Categorizing {len(all_raw_ads)} ads locally...")
    for ad in all_raw_ads:
        start_time = ad.get('ad_delivery_start_time', '')
        if not start_time: continue
        
        try:
            # Handle browser date format
            # Format: "Started running on Jan 6, 2026"
            date_match = re.search(r'on ([A-Z][a-z]{2} \d+, \d{4})', start_time)
            if date_match:
                start_dt = datetime.strptime(date_match.group(1), '%b %d, %Y')
            else:
                start_dt = now  # Fallback
                
            age_days = (now - start_dt).days
            
            if age_days >= 30:
                results["proven"].append(ad)
            elif age_days >= 7:
                results["established"].append(ad)
            else:
                results["fresh"].append(ad)
        except (ValueError, AttributeError, KeyError) as e:
            bot_logger.warning(f"Failed to categorize ad: {e}")
            continue
        except Exception as e:
            bot_logger.error(f"Unexpected error categorizing ad: {e}")
            continue

    print(f"[OK] Local sorting complete: {len(results['proven'])} Proven, {len(results['established'])} Established, {len(results['fresh'])} Fresh")
    return results


def scrape_ad_snapshot(snapshot_url: str) -> Dict[str, Any]:
    """
    Scrape an individual ad snapshot page for media content.
    
    Args:
        snapshot_url: Facebook Ad Library snapshot URL
        
    Returns:
        Dictionary with extracted media URLs and content
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        response = requests.get(snapshot_url, headers=headers, timeout=30)
        
        if response.status_code != 200:
            return {'error': f'HTTP {response.status_code}'}
        
        html = response.text
        
        # Extract video URLs (look for common patterns)
        video_urls = []
        video_patterns = [
            r'https://video[^"\']+\.mp4[^"\']*',
            r'https://scontent[^"\']+video[^"\']*',
            r'"video_url"\s*:\s*"([^"]+)"',
            r'"playable_url"\s*:\s*"([^"]+)"',
            r'"sd_src"\s*:\s*"([^"]+)"',
            r'"hd_src"\s*:\s*"([^"]+)"'
        ]
        
        for pattern in video_patterns:
            matches = re.findall(pattern, html)
            video_urls.extend(matches)
        
        # Extract image URLs
        image_urls = []
        image_patterns = [
            r'https://scontent[^"\']+\.(?:jpg|jpeg|png)[^"\']*',
            r'"image_url"\s*:\s*"([^"]+)"',
            r'"full_image"\s*:\s*"([^"]+)"'
        ]
        
        for pattern in image_patterns:
            matches = re.findall(pattern, html)
            image_urls.extend(matches)
        
        # Clean up URLs (unescape)
        video_urls = list(set([u.replace('\\/', '/').replace('\\u0025', '%') for u in video_urls if u]))
        image_urls = list(set([u.replace('\\/', '/').replace('\\u0025', '%') for u in image_urls if u]))
        
        return {
            'snapshot_url': snapshot_url,
            'video_urls': video_urls[:3],  # Limit to first 3
            'image_urls': image_urls[:5],   # Limit to first 5
            'has_video': len(video_urls) > 0,
            'has_images': len(image_urls) > 0
        }
        
    except Exception as e:
        return {'error': str(e), 'snapshot_url': snapshot_url}


def download_media(url: str, timeout: int = 30) -> Optional[bytes]:
    """
    Download media from a URL.
    
    Args:
        url: Media URL
        timeout: Request timeout
        
    Returns:
        Media bytes or None
    """
    try:
        response = requests.get(url, timeout=timeout, stream=True)
        if response.status_code == 200:
            return response.content
        return None
    except:
        return None


def extract_video_transcript(video_url: str) -> Optional[str]:
    """
    Extract transcript from a video using OpenAI Whisper.
    
    Args:
        video_url: URL to the video file
        
    Returns:
        Transcript text or None
    """
    if not api_keys.OPENAI_CLIENT:
        api_keys.initialize_clients()
    
    if not api_keys.OPENAI_CLIENT:
        return None
    
    try:
        # Download video
        video_data = download_media(video_url, timeout=60)
        if not video_data:
            return None
        
        # Save to temp file
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as f:
            f.write(video_data)
            temp_path = f.name
        
        try:
            # Transcribe with Whisper
            openai_limiter.wait()
            with open(temp_path, 'rb') as audio_file:
                response = api_keys.OPENAI_CLIENT.audio.transcriptions.create(
                    model=getattr(config, 'WHISPER_MODEL', 'whisper-1'),
                    file=audio_file,
                    response_format='text'
                )
            
            return response.strip() if response else None
            
        finally:
            # Clean up temp file
            Path(temp_path).unlink(missing_ok=True)
            
    except Exception as e:
        print(f"[WARNING] Video transcript extraction failed: {e}")
        return None


def extract_image_text(image_url: str) -> Dict[str, Any]:
    """
    Extract text and analyze image using GPT-4 Vision.
    
    Args:
        image_url: URL to the image
        
    Returns:
        Dictionary with extracted text and hook analysis
    """
    if not api_keys.OPENAI_CLIENT:
        api_keys.initialize_clients()
    
    if not api_keys.OPENAI_CLIENT:
        return {'error': 'OpenAI client not configured'}
    
    try:
        # Download image and convert to base64
        image_data = download_media(image_url, timeout=30)
        if not image_data:
            return {'error': 'Failed to download image'}
        
        base64_image = base64.b64encode(image_data).decode('utf-8')
        
        # Determine image type
        if image_url.lower().endswith('.png') or b'\x89PNG' in image_data[:10]:
            media_type = 'image/png'
        else:
            media_type = 'image/jpeg'
        
        # Use GPT-4 Vision to extract text and analyze
        openai_limiter.wait()
        response = api_keys.OPENAI_CLIENT.chat.completions.create(
            model=getattr(config, 'GPT_VISION_MODEL', 'gpt-4o'),
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": config.AI_PROMPTS['competitor_analysis']['image_analysis']
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{media_type};base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=500
        )
        
        if not response.choices or len(response.choices) == 0:
            return {'all_text': '', 'hook_text': '', 'hook_style': '', 'offer_details': '', 'visual_elements': '', 'error': 'No choices in response'}
        
        content = response.choices[0].message.content
        if content is None:
            return {'all_text': '', 'hook_text': '', 'hook_style': '', 'offer_details': '', 'visual_elements': ''}
        
        # Parse JSON response
        try:
            # Clean up response if needed
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0]
            elif '```' in content:
                content = content.split('```')[1].split('```')[0]
            
            return json.loads(content)
        except json.JSONDecodeError as e:
            bot_logger.warning(f"Failed to parse image analysis JSON: {e}")
            return {
                'all_text': content,
                'hook_text': content[:200],
                'hook_style': 'unknown',
                'parse_error': True
            }
            
    except Exception as e:
        return {'error': str(e)}


def analyze_hook_pattern(hook_text: str, body_text: str = "") -> Dict[str, Any]:
    """
    Analyze a hook to identify its pattern and style.
    
    Args:
        hook_text: The hook/headline text
        body_text: Optional body copy
        
    Returns:
        Dictionary with hook analysis
    """
    combined = f"{hook_text} {body_text}".lower()
    
    patterns = {
        'question_hook': any(q in combined for q in ['?', 'are you', 'do you', 'have you', 'want to', 'tired of']),
        'comparison_hook': any(c in combined for c in ['vs', 'versus', 'compared to', 'unlike', 'other', 'most', 'typical']),
        'urgency_hook': any(u in combined for u in ['limited', 'now', 'today', 'hurry', 'last chance', 'only', 'ending']),
        'price_hook': any(p in combined for p in ['$', 'free', 'save', 'discount', 'off', 'deal']),
        'timeline_hook': any(t in combined for t in ['week', 'day', 'hour', 'fast', 'quick', 'instant', 'saturday', 'tomorrow']),
        'fear_hook': any(f in combined for f in ['stop', 'avoid', 'don\'t', 'warning', 'risk', 'danger', 'mistake']),
        'social_proof_hook': any(s in combined for s in ['review', 'rated', 'trusted', 'customer', 'testimonial', 'proven']),
        'curiosity_hook': any(c in combined for c in ['secret', 'hidden', 'discover', 'revealed', 'why', 'how']),
        'benefit_hook': any(b in combined for b in ['get', 'enjoy', 'achieve', 'transform', 'upgrade', 'finally']),
        'problem_hook': any(p in combined for p in ['frustrated', 'annoyed', 'tired', 'sick of', 'struggling', 'hate'])
    }
    
    # Identify primary pattern
    detected_patterns = [p for p, v in patterns.items() if v]
    primary_pattern = detected_patterns[0] if detected_patterns else 'unknown'
    
    return {
        'hook_text': hook_text,
        'primary_pattern': primary_pattern,
        'all_patterns': detected_patterns,
        'word_count': len(hook_text.split()),
        'has_price': patterns['price_hook'],
        'has_timeline': patterns['timeline_hook'],
        'has_question': patterns['question_hook']
    }


def extract_ad_hooks(
    ads: List[Dict[str, Any]],
    extract_media: bool = True,
    max_media_extractions: int = 50
) -> List[Dict[str, Any]]:
    """
    Extract hooks from a list of ads, optionally scraping media.
    Uses multithreading for media extraction and semantic hook identification.
    Only extracts media for "proven" ads (>21 days old) to save time.
    """
    print(f"[INFO] Extracting hooks from {len(ads)} ads...")
    
    def process_single_ad_hook(args):
        i, ad, extract_this_media_requested = args
        page_name = ad.get('page_name', '')
        bodies = ad.get('ad_creative_bodies') or []
        body_text = " ".join(bodies) if bodies else ""
        titles = ad.get('ad_creative_link_titles') or []
        title_text = " ".join(titles) if titles else ""
        snapshot_url = ad.get('ad_snapshot_url', '')
        start_time = ad.get('ad_delivery_start_time', '')
        
        # Calculate ad age
        age_days = 0
        if start_time:
            try:
                start_dt = datetime.fromisoformat(start_time.split('+')[0])
                age_days = (datetime.now() - start_dt).days
            except (ValueError, AttributeError, IndexError) as e:
                bot_logger.debug(f"Failed to parse ad start time '{start_time}': {e}")
                pass
        
        # Smart Media Extraction: Only run for ads older than 21 days or if specifically requested for fewer ads
        # This drastically speeds up analysis of newer ads.
        is_proven = age_days >= 21  # Ads running 21+ days are considered proven
        should_extract_media = extract_this_media_requested and is_proven
        
        # Basic hook from text
        hook_text = title_text or body_text[:200]
        
        hook_data = {
            'id': hashlib.md5(f"{page_name}{hook_text}".encode()).hexdigest()[:12],
            'page_name': page_name,
            'hook_text': hook_text,
            'body_snippet': body_text[:500] if body_text else "",
            'title': title_text,
            'snapshot_url': snapshot_url,
            'age_days': age_days,
            'extracted_at': datetime.now().isoformat(),
            'source': 'text',
            'semantic_hook': ad.get('semantic_hook') # Use pre-extracted semantic hook from alignment check
        }
        
        # Analyze the pattern
        hook_analysis = analyze_hook_pattern(hook_text, body_text)
        hook_data.update(hook_analysis)
        
        # Extract media if enabled, within limit, AND is a proven ad
        if should_extract_media and snapshot_url:
            # Scrape snapshot for media URLs
            snapshot_data = scrape_ad_snapshot(snapshot_url)
            
            if snapshot_data.get('has_video') and snapshot_data.get('video_urls'):
                # Extract video transcript
                video_urls = snapshot_data.get('video_urls', [])
                if video_urls and len(video_urls) > 0:
                    video_url = video_urls[0]
                    transcript = extract_video_transcript(video_url)
                if transcript:
                    hook_data['video_transcript'] = transcript
                    hook_data['source'] = 'video_transcript'
                    # Re-analyze with transcript
                    video_analysis = analyze_hook_pattern(transcript[:200], transcript)
                    hook_data['video_hook_pattern'] = video_analysis['primary_pattern']
                    hook_data['video_patterns'] = video_analysis['all_patterns']
                    
                    # Update semantic hook with more data from transcript if needed
                    # (Though we already have one from the alignment check)
            
            if snapshot_data.get('has_images') and snapshot_data.get('image_urls'):
                # Extract image text
                image_urls = snapshot_data.get('image_urls', [])
                if image_urls and len(image_urls) > 0:
                    image_url = image_urls[0]
                    image_analysis = extract_image_text(image_url)
                if not image_analysis.get('error'):
                    hook_data['image_text'] = image_analysis.get('all_text', '')
                    hook_data['image_hook'] = image_analysis.get('hook_text', '')
                    hook_data['image_hook_style'] = image_analysis.get('hook_style', '')
                    hook_data['image_offer'] = image_analysis.get('offer_details', '')
                    if image_analysis.get('hook_text'):
                        hook_data['source'] = 'image_ocr'
        
        return hook_data

    # Prepare arguments for multithreading
    process_args = []
    for i, ad in enumerate(ads):
        extract_this_media = extract_media and i < max_media_extractions
        process_args.append((i, ad, extract_this_media))

    # Run multithreaded
    hooks = run_multithreaded(process_single_ad_hook, process_args)
    
    # Filter out None values in case of failures
    hooks = [h for h in hooks if h is not None]
    
    media_extracted_count = min(len(ads), max_media_extractions) if extract_media else 0
    print(f"[OK] Extracted {len(hooks)} hooks ({media_extracted_count} with media analysis)")
    return hooks


def extract_literal_hooks(
    ads: List[Dict[str, Any]], 
    category: str
) -> List[Dict[str, Any]]:
    """
    Extract literal hooks from ads using multi-modal analysis prediction (Text, Vision, Script).
    Uses multithreading for faster extraction.
    """
    print(f"[INFO] Extracting literal hooks for {len(ads)} {category} ads...")
    
    def process_literal_hook(ad):
        # 1. Literal Text Hook (from bodies)
        bodies = ad.get('ad_creative_bodies', [""])
        body = bodies[0] if bodies else ""
        link_titles = ad.get('ad_creative_link_titles', [])
        headline = link_titles[0] if link_titles else ""
        
        # Split body to find the opening hook (first 2 sentences)
        sentences = re.split(r'(?<=[.!?])\s+', body)
        literal_text_hook = " ".join(sentences[:2]) if sentences else body
        
        # 2. Visual & Script Hook Prediction
        extraction = _extract_hooks_from_content(body, headline, ad.get('ad_snapshot_url'))
        
        return {
            'literal_text_hook': literal_text_hook,
            'literal_visual_hook': extraction.get('visual_hook', 'N/A'),
            'literal_script_hook': extraction.get('script_hook', 'N/A'),
            'selling_mechanism': extraction.get('selling_mechanism', 'N/A'),
            'unique_offer': extraction.get('unique_offer', 'N/A'),
            'headline': headline,
            'page_name': ad.get('page_name'),
            'category': category,
            'snapshot_url': ad.get('ad_snapshot_url'),
            'impressions': ad.get('impressions', {}).get('lower_bound', 0)
        }

    hooks = run_multithreaded(process_literal_hook, ads)
    
    # Filter out None values
    hooks = [h for h in hooks if h is not None]
    
    return hooks


def _extract_hooks_from_content(body: str, headline: str, snapshot_url: str) -> Dict[str, str]:
    """
    Uses LLMs to predict/identify the literal hook and offer from ad content.
    """
    if not api_keys.OPENAI_CLIENT or (not api_keys.ANTHROPIC_CLIENT and 'ANTHROPIC_API_KEY' in os.environ):
        api_keys.initialize_clients()
        
    result = {"visual_hook": "N/A", "script_hook": "N/A", "selling_mechanism": "N/A", "unique_offer": "N/A"}

    # 1. Use GPT-4o-mini for general extraction and Visual Hook prediction
    prompt_openai = config.AI_PROMPTS['competitor_analysis']['hook_extraction'].format(
        headline=headline,
        body=body
    )
    
    try:
        openai_limiter.wait()
        response = api_keys.OPENAI_CLIENT.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt_openai}],
            response_format={"type": "json_object"},
            max_tokens=200
        )
        content = response.choices[0].message.content
        if content is None:
            return result
        data = json.loads(content)
        result.update(data)
    except Exception:
        pass

    # 2. Use Claude for Script Hook extraction
    if api_keys.ANTHROPIC_CLIENT:
        prompt_claude = config.AI_PROMPTS['competitor_analysis']['script_extraction'].format(
            body=body
        )
        try:
            anthropic_limiter.wait()
            message = api_keys.ANTHROPIC_CLIENT.messages.create(
                model="claude-3-5-sonnet-20240620",
                max_tokens=100,
                messages=[{"role": "user", "content": prompt_claude}]
            )
            # Safely extract text from response
            if message.content and len(message.content) > 0:
                content_block = message.content[0]
                if hasattr(content_block, 'text'):
                    result["script_hook"] = content_block.text.strip()
                else:
                    result["script_hook"] = str(content_block).strip()
            else:
                result["script_hook"] = ""
        except Exception:
            pass
            
    return result


def categorize_hooks(hooks: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Categorize hooks by their pattern type.
    
    Args:
        hooks: List of extracted hook data
        
    Returns:
        Dictionary with hooks organized by pattern
    """
    categories = {}
    
    for hook in hooks:
        pattern = hook.get('primary_pattern', 'unknown')
        if pattern not in categories:
            categories[pattern] = []
        categories[pattern].append(hook)
    
    return categories


def generate_differentiation_insights(hooks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze hooks to identify overused patterns and suggest differentiation.
    
    Args:
        hooks: List of extracted hook data
        
    Returns:
        Dictionary with insights for differentiation
    """
    total = len(hooks)
    if total == 0:
        return {'error': 'No hooks to analyze'}
    
    # Count patterns
    pattern_counts = {}
    for hook in hooks:
        pattern = hook.get('primary_pattern', 'unknown')
        pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1
    
    # Sort by frequency
    sorted_patterns = sorted(pattern_counts.items(), key=lambda x: x[1], reverse=True)
    
    # Calculate percentages
    pattern_percentages = {p: (c / total) * 100 for p, c in sorted_patterns}
    
    # Identify overused patterns (>20% of ads)
    overused = [p for p, pct in pattern_percentages.items() if pct > 20]
    
    # Identify underused patterns (<10% of ads)
    underused = [p for p, pct in pattern_percentages.items() if pct < 10 and p != 'unknown']
    
    # Collect common phrases/words
    all_text = " ".join([h.get('hook_text', '') + " " + h.get('body_snippet', '') for h in hooks]).lower()
    
    # Common phrases to avoid
    common_phrases = []
    phrase_patterns = [
        r'tired of \w+',
        r'are you \w+',
        r'stop \w+',
        r'want to \w+',
        r'looking for \w+',
        r'need \w+',
        r'struggling with \w+',
        r'finally \w+'
    ]
    
    for pattern in phrase_patterns:
        matches = re.findall(pattern, all_text)
        if len(matches) > 3:
            common_phrases.extend(list(set(matches))[:3])
    
    return {
        'total_hooks_analyzed': total,
        'pattern_distribution': pattern_percentages,
        'most_common_patterns': sorted_patterns[:5],
        'overused_patterns': overused,
        'underused_patterns': underused,
        'common_phrases_to_avoid': list(set(common_phrases))[:15],
        'recommendation': f"AVOID: {', '.join(overused)} hooks. TRY: {', '.join(underused) if underused else 'unique combinations'}"
    }


def save_hooks_database(hooks: List[Dict[str, Any]], output_path: Optional[Path] = None) -> bool:
    """
    Save extracted hooks to a JSON database.
    
    Args:
        hooks: List of hook data
        output_path: Path to save database
        
    Returns:
        True if successful
    """
    if output_path is None:
        output_path = config.COMPETITOR_HOOKS_DB
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Load existing database if present
    existing_hooks = []
    if output_path.exists():
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
                existing_hooks = existing_data.get('hooks', [])
        except:
            pass
    
    # Merge with new hooks (avoid duplicates by ID)
    existing_ids = {h.get('id') for h in existing_hooks}
    new_hooks = [h for h in hooks if h.get('id') not in existing_ids]
    all_hooks = existing_hooks + new_hooks
    
    # Generate insights
    insights = generate_differentiation_insights(all_hooks)
    
    database = {
        'last_updated': datetime.now().isoformat(),
        'total_hooks': len(all_hooks),
        'new_hooks_added': len(new_hooks),
        'insights': insights,
        'hooks': all_hooks
    }
    
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(database, f, indent=2, ensure_ascii=False)
        
        print(f"[OK] Saved {len(all_hooks)} hooks to database ({len(new_hooks)} new)")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to save hooks database: {e}")
        return False


def load_hooks_database(db_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load the hooks database.
    
    Args:
        db_path: Path to database file
        
    Returns:
        Database dictionary
    """
    if db_path is None:
        db_path = config.COMPETITOR_HOOKS_DB
    
    if not db_path.exists():
        return {'hooks': [], 'insights': {}}
    
    try:
        with open(db_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {'hooks': [], 'insights': {}}


def get_competitor_analysis_cache_path(topic: str) -> Path:
    """Get the path to the cache file for a given topic."""
    topic_slug = re.sub(r'[^a-z0-9]', '_', topic.lower())
    return config.COMPETITOR_DATA_DIR / "cache" / f"analysis_{topic_slug}.json"


def save_competitor_analysis_to_cache(topic: str, data: Dict[str, Any]):
    """Save analysis data to local cache."""
    cache_path = get_competitor_analysis_cache_path(topic)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    
    cache_data = {
        'timestamp': datetime.now().isoformat(),
        'topic': topic,
        'data': data
    }
    
    try:
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[WARNING] Failed to save competitor cache: {e}")


def load_competitor_analysis_from_cache(topic: str, max_age_hours: int = 24) -> Optional[Dict[str, Any]]:
    """Load analysis data from cache if it's within the age limit."""
    cache_path = get_competitor_analysis_cache_path(topic)
    
    if not cache_path.exists():
        return None
        
    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
            
        timestamp = datetime.fromisoformat(cache_data.get('timestamp'))
        age = datetime.now() - timestamp
        
        if age.total_seconds() < max_age_hours * 3600:
            print(f"[OK] Loaded competitor analysis from cache (Age: {age.total_seconds() / 3600:.1f}h)")
            return cache_data.get('data')
    except Exception:
        pass
        
    return None


def get_competitor_analysis(
    topic: str,
    offer_type: str = "service",
    extra_keywords: Optional[List[str]] = None,
    extract_media: bool = True,
    limit: Optional[int] = None,
    relevance_profile: Optional[Dict[str, Any]] = None,
    offers: Optional[List[str]] = None,
    use_cache: bool = True,
    non_interactive: bool = False,
    positive_keywords: Optional[List[str]] = None,
    negative_keywords: Optional[List[str]] = None,
    auto_generate_keywords: bool = True,
    skip_offer_filters: bool = False,
    max_ads: int = 30
) -> Dict[str, Any]:
    """
    Perform comprehensive competitor analysis for a topic using browser scraping.
    
    Args:
        topic: The search topic (e.g., "exterior painting")
        offer_type: Type of offer ("service" or "ecom")
        extra_keywords: Additional positive keywords to include
        extract_media: Whether to extract media from ads
        limit: Maximum number of hooks to extract
        relevance_profile: Legacy profile dict (deprecated - use keywords instead)
        offers: List of offer strings for profile generation
        use_cache: Whether to use cached data (respects config.ENABLE_CACHING)
        non_interactive: Skip user confirmation prompts
        positive_keywords: Required keywords (max 2, at least one must match)
        negative_keywords: Exclusion keywords (max 5, none can match)
        auto_generate_keywords: Whether to auto-generate keywords with Claude Sonnet
        skip_offer_filters: Skip generating and using filters for offers (no keyword filtering)
        max_ads: Maximum number of ads to scrape (controls scroll_limit, default: 30)
    """
    print(f"\n[COMPETITOR ANALYSIS] Searching for: {topic}")
    
    # Check cache first if enabled
    if use_cache and config.ENABLE_CACHING:
        cached_data = load_competitor_analysis_from_cache(topic, max_age_hours=config.CACHE_TTL_HOURS.get('competitor_analysis', 24))
        if cached_data:
            print(f"[CACHE HIT] Using cached competitor analysis for '{topic}'")
            return cached_data
    
    # Use only the topic as search term
    primary_search_term = topic
    search_terms_list = [topic]
    
    # Set target_count based on limit
    target_count = limit if limit is not None else getattr(config, 'QUALIFIED_ADS_PER_TIMEFRAME', 15)
    
    # -----------------------------------------------------------------
    # KEYWORD GENERATION (New unified system)
    # -----------------------------------------------------------------
    if skip_offer_filters:
        # Skip all keyword generation and filtering
        print(f"\n[KEYWORDS] Offer filters disabled - skipping keyword generation")
        positive_keywords = []
        negative_keywords = []
    elif not positive_keywords or not negative_keywords:
        if auto_generate_keywords:
            from .keyword_generator import generate_keywords_with_sonnet, prompt_user_for_keywords
            
            print(f"\n[KEYWORDS] Generating filter keywords for '{topic}'...")
            generated = generate_keywords_with_sonnet(topic, max_positive=2, max_negative=5)
            
            if non_interactive:
                print(f"[KEYWORDS] Auto-approved: +{generated['positive']} -{generated['negative'][:3]}...")
                approved = generated
            else:
                approved = prompt_user_for_keywords(generated)
                # Handle regeneration request
                while approved is None:
                    generated = generate_keywords_with_sonnet(topic, max_positive=2, max_negative=5)
                    approved = prompt_user_for_keywords(generated)
            
            if not positive_keywords:
                positive_keywords = approved['positive']
            if not negative_keywords:
                negative_keywords = approved['negative']
        else:
            # Fallback: use topic words as positive keywords
            topic_words = [w.lower().strip() for w in topic.split() if len(w) > 2]
            if positive_keywords is None:
                positive_keywords = topic_words[:2] if topic_words else [topic.lower()]
            if negative_keywords is None:
                negative_keywords = []
    
    # Ensure lists are not None
    if positive_keywords is None:
        positive_keywords = []
    if negative_keywords is None:
        negative_keywords = []
    
    # Add extra_keywords to positive if provided (legacy support)
    # Skip if offer filters are disabled
    if not skip_offer_filters and extra_keywords:
        for kw in extra_keywords:
            if kw.lower() not in positive_keywords:
                positive_keywords.append(kw.lower())
        # Enforce max 2 limit
        positive_keywords = positive_keywords[:2]
    
    # Log active keywords (only if filters are enabled)
    if not skip_offer_filters:
        print(f"[KEYWORDS] Positive (required): {', '.join(positive_keywords)}")
        print(f"[KEYWORDS] Negative (excluded): {', '.join(negative_keywords[:5])}{'...' if len(negative_keywords) > 5 else ''}")
    
    # Build relevance_keywords list for backward compatibility
    relevance_keywords = list(positive_keywords) if positive_keywords else []
    
    # -----------------------------------------------------------------
    # RUN SCRAPER (with unique offer filtering if enabled)
    # -----------------------------------------------------------------
    require_unique = getattr(config, 'REQUIRE_UNIQUE_OFFERS', True)
    
    # Tracking variables for uniqueness stats
    unique_offer_stats = {
        'enabled': require_unique,
        'unique_count': 0,
        'total_scraped': 0,
        'duplicates_removed': 0,
        'target_met': True,
        'offer_groups': {}
    }
    
    if require_unique:
        # Use the new unique offer scraping with AI deduplication
        print(f"[INFO] Searching Ad Library for: '{primary_search_term}' (target: {target_count} UNIQUE offers)")
        
        import asyncio
        
        def run_unique_scrape():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(scrape_ads_with_unique_offers(
                    search_term=primary_search_term,
                    target_unique_count=target_count,  # This is the number of hooks requested
                    headless=True,
                    scroll_limit=max_ads,
                    positive_keywords=positive_keywords,
                    negative_keywords=negative_keywords,
                    fresh_days=7,
                    proven_days=30
                ))
            finally:
                loop.close()
        
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run_unique_scrape)
            scrape_result = future.result()
        
        # Extract results
        all_ads = scrape_result.get('ads', [])
        unique_offer_stats['unique_count'] = scrape_result.get('unique_count', 0)
        unique_offer_stats['total_scraped'] = scrape_result.get('total_scraped', 0)
        unique_offer_stats['duplicates_removed'] = scrape_result.get('duplicates_removed', 0)
        unique_offer_stats['target_met'] = scrape_result.get('target_met', False)
        unique_offer_stats['offer_groups'] = scrape_result.get('offer_groups', {})
        
        # Check if we have enough unique offers
        if not unique_offer_stats['target_met'] and not non_interactive:
            unique_found = unique_offer_stats['unique_count']
            print(f"\n{'='*60}")
            print(f"  UNIQUE OFFER SHORTFALL")
            print(f"{'='*60}")
            print(f"  Target unique offers: {target_count}")
            print(f"  Unique offers found:  {unique_found}")
            print(f"  Shortfall:            {target_count - unique_found}")
            print(f"{'='*60}")
            print(f"\nNot enough unique competitor offers were found.")
            print(f"This means proven hooks will be generated from {unique_found} different offer types.")
            
            while True:
                choice = input(f"\nProceed with {unique_found} unique offers? (y/n): ").strip().lower()
                if choice == 'y' or choice == 'yes':
                    print(f"[OK] Proceeding with {unique_found} unique offers")
                    break
                elif choice == 'n' or choice == 'no':
                    print("[ABORT] User chose not to proceed")
                    return {
                        'topic': topic,
                        'offer_type': offer_type,
                        'ads_found': 0,
                        'hooks': [],
                        'patterns': [],
                        'insights': {},
                        'relevance_keywords': relevance_keywords,
                        'unique_offer_stats': unique_offer_stats,
                        'user_aborted': True
                    }
                else:
                    print("Please enter 'y' or 'n'")
        
        # Categorize the unique ads by type
        proven_ads = [ad for ad in all_ads if ad.get('ad_type') == 'proven']
        established_ads = [ad for ad in all_ads if ad.get('ad_type') == 'established']
        fresh_ads = [ad for ad in all_ads if ad.get('ad_type') == 'fresh']
        
    else:
        # Use original scraping without unique offer filtering
        print(f"[INFO] Searching Ad Library for: '{primary_search_term}' (target: {target_count} hooks)")
        tiered_results = search_competitor_ads_tiered(
            [primary_search_term], 
            positive_keywords=positive_keywords,
            negative_keywords=negative_keywords,
            target_count=target_count,
            max_ads=max_ads
        )
        
        # Get ads by category (browser scraper already did Haiku analysis)
        proven_ads = tiered_results.get("proven", [])
        established_ads = tiered_results.get("established", [])
        fresh_ads = tiered_results.get("fresh", [])
    
    if not proven_ads and not established_ads and not fresh_ads:
        print("[INFO] No qualified competitor ads found")
        return {
            'topic': topic,
            'offer_type': offer_type,
            'ads_found': 0,
            'hooks': [],
            'patterns': [],
            'insights': {},
            'relevance_keywords': relevance_keywords
        }

    # =========================================================================
    # USE HAIKU RESULTS DIRECTLY (same as test script)
    # Browser scraper already analyzed all ads with Claude Haiku and filtered
    # out ads without valid offers. We just format them here.
    # =========================================================================
    
    print(f"[INFO] Processing {len(proven_ads)} proven, {len(established_ads)} established, {len(fresh_ads)} fresh Haiku-analyzed ads...")
    
    # Build hooks list directly from Haiku analysis (NO redundant extraction!)
    def build_hook_from_ad(ad):
        """Helper to build hook data from ad."""
        haiku_hook = ad.get('haiku_hook', '')
        haiku_offer = ad.get('haiku_offer', 'N/A')
        
        # Get body text
        bodies = ad.get('ad_creative_bodies', [])
        body_text = bodies[0] if bodies else ""
        
        # Build hook data (matching format expected by headline generator)
        return {
            'id': ad.get('id', ''),
            'page_name': ad.get('page_name', 'Unknown'),
            'hook_text': haiku_hook,  # Use Haiku-extracted hook
            'offer': haiku_offer,      # Use Haiku-extracted offer
            'body_snippet': body_text[:500] if body_text else "",
            'snapshot_url': ad.get('ad_snapshot_url', ''),
            'ad_type': ad.get('ad_type', 'unknown'),  # fresh or proven
            'date': ad.get('ad_delivery_start_time', ''),
            'confidence': ad.get('haiku_confidence', 'medium')
        }
    
    # Build hooks from each category
    proven_hooks = [build_hook_from_ad(ad) for ad in proven_ads]
    established_hooks = [build_hook_from_ad(ad) for ad in established_ads]
    fresh_hooks = [build_hook_from_ad(ad) for ad in fresh_ads]
    
    # Select hooks ensuring at least 25% are fresh (if fresh ads available)
    # Priority: proven > established > fresh, but ensure minimum fresh representation
    hooks = []
    
    if fresh_ads:
        # Calculate minimum fresh count (25% of target, rounded up)
        min_fresh_count = max(1, int(target_count * 0.25))
        # Don't exceed available fresh ads
        fresh_count = min(min_fresh_count, len(fresh_hooks))
        
        # Calculate remaining slots for proven/established
        remaining_slots = target_count - fresh_count
        
        # Fill with proven first (priority), then established, then remaining fresh
        proven_count = min(remaining_slots, len(proven_hooks))
        established_count = min(remaining_slots - proven_count, len(established_hooks))
        # Add any remaining slots to fresh if available
        if proven_count + established_count < remaining_slots:
            additional_fresh = min(remaining_slots - proven_count - established_count, len(fresh_hooks) - fresh_count)
            fresh_count += additional_fresh
        
        # Build final hooks list: proven first, then established, then fresh
        hooks.extend(proven_hooks[:proven_count])
        hooks.extend(established_hooks[:established_count])
        hooks.extend(fresh_hooks[:fresh_count])
        
        print(f"[INFO] Selected {proven_count} proven, {established_count} established, {fresh_count} fresh ads (target: {target_count})")
    else:
        # No fresh ads available - use proven and established only
        hooks.extend(proven_hooks[:target_count])
        remaining = target_count - len(hooks)
        if remaining > 0:
            hooks.extend(established_hooks[:remaining])
        print(f"[INFO] No fresh ads available. Selected {len([h for h in hooks if h.get('ad_type') == 'proven'])} proven, {len([h for h in hooks if h.get('ad_type') == 'established'])} established ads (target: {target_count})")
    
    print(f"[OK] {len(hooks)} hooks ready (all with valid offers from Haiku analysis)")
    
    # Build patterns list for headline generator (for avoidance)
    patterns_for_avoidance = []
    for hook in hooks:
        hook_text = hook.get('hook_text', '')
        if hook_text:
            ad_type = hook.get('ad_type', 'unknown').upper()
            pattern_str = f"[{ad_type}] {hook['page_name']}: \"{hook_text[:150]}\""
            patterns_for_avoidance.append(pattern_str)
    
    # Build literal hook bank (same data, different format for compatibility)
    literal_hook_bank = [
        {
            'literal_text_hook': h.get('hook_text', ''),
            'unique_offer': h.get('offer', 'N/A'),
            'page_name': h.get('page_name', ''),
            'snapshot_url': h.get('snapshot_url', ''),
            'ad_type': h.get('ad_type', '')
        }
        for h in hooks
    ]
    
    # Simple categorization by ad type
    categories = {
        'proven': [h for h in hooks if h.get('ad_type') == 'proven'],
        'fresh': [h for h in hooks if h.get('ad_type') == 'fresh']
    }
    
    # Generate basic insights
    proven_count = len(categories.get('proven', []))
    fresh_count = len(categories.get('fresh', []))
    insights = {
        'total_hooks': len(hooks),
        'proven_hooks': proven_count,
        'fresh_hooks': fresh_count,
        'pattern_distribution': {
            'proven': (proven_count / len(hooks) * 100) if hooks else 0,
            'fresh': (fresh_count / len(hooks) * 100) if hooks else 0
        }
    }
    
    print(f"[OK] Analysis complete:")
    print(f"     PROVEN: {proven_count} | FRESH: {fresh_count}")
    
    # Generate human-readable timestamp
    now = datetime.now()
    readable_time = f"{now.month}/{now.day}/{now.strftime('%y')} {now.strftime('%I:%M %p').lstrip('0')}"
    
    competitor_data = {
        'topic': topic,
        'offer_type': offer_type,
        'scraped_at': readable_time,
        'scraped_at_iso': now.isoformat(),
        'filters': {
            'positive_keywords': positive_keywords,
            'negative_keywords': negative_keywords
        },
        'ads_found': len(proven_ads) + len(established_ads) + len(fresh_ads),
        'hooks_extracted': len(hooks),
        'breakdown': {
            'proven': proven_count,
            'fresh': fresh_count
        },
        'hooks': hooks,
        'literal_hook_bank': literal_hook_bank,
        'categories': categories,
        'insights': insights,
        'patterns': patterns_for_avoidance,
        'competitors': list(set([h['page_name'] for h in hooks[:20]])),
        'relevance_keywords': relevance_keywords,
        'unique_offer_stats': unique_offer_stats
    }

    # Log the complete analysis data for debugging
    log_data(competitor_data, f"Competitor analysis complete for '{topic}'")
    
    # Save to cache if enabled (respects config.ENABLE_CACHING)
    if config.ENABLE_CACHING:
        save_competitor_analysis_to_cache(topic, competitor_data)
        print(f"[CACHE] Saved competitor analysis for '{topic}'")
    
    return competitor_data


def filter_by_offer_type(
    analysis: Dict[str, Any],
    offer_type: str
) -> Dict[str, Any]:
    """
    Filter competitor analysis by offer type.
    """
    analysis['filtered_offer_type'] = offer_type
    return analysis


def _extract_personas_desires_mechanisms(hooks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Use Claude to extract personas, desires/problems, and mechanisms from competitor ads.
    
    Args:
        hooks: List of hooks with hook_text, offer, body_snippet
        
    Returns:
        Dictionary with extracted analysis data
    """
    if not api_keys.ANTHROPIC_CLIENT:
        api_keys.initialize_clients()
    
    if not api_keys.ANTHROPIC_CLIENT:
        return {'error': 'Anthropic client not configured'}
    
    # Prepare ad data for analysis
    ad_summaries = []
    for i, hook in enumerate(hooks[:30], 1):  # Limit to 30 ads to stay within context
        ad_summary = f"""
Ad {i}:
- Hook: {hook.get('hook_text', '')[:200]}
- Offer: {hook.get('offer', 'N/A')}
- Body: {hook.get('body_snippet', '')[:300]}
"""
        ad_summaries.append(ad_summary)
    
    prompt = f"""Analyze these competitor ads and extract PERSONAS, DESIRES/PROBLEMS, and MECHANISMS.

COMPETITOR ADS:
{''.join(ad_summaries)}

For each category, identify:
1. PERSONAS: Who are these ads speaking to? (e.g., "budget-conscious homeowner", "busy professional", "first-time buyer")
2. DESIRES/PROBLEMS: What desires or problems do these ads address? (e.g., "save money", "save time", "look professional")  
3. MECHANISMS: What mechanisms/methods do they use to solve the problem? (e.g., "free quotes", "price match guarantee", "same-day service")

Count how many ads use each. Identify which are OVERUSED (>30% of ads) and which are UNDERUTILIZED (<10%).

Return JSON:
{{
    "personas": {{
        "identified": [
            {{"persona": "description", "count": N, "example_ad": "hook snippet"}},
            ...
        ],
        "overused": ["persona1", "persona2"],
        "underutilized": ["persona3", "persona4"]
    }},
    "desires_problems": {{
        "identified": [
            {{"desire": "description", "count": N, "example_ad": "hook snippet"}},
            ...
        ],
        "overused": ["desire1"],
        "underutilized": ["desire2", "desire3"]
    }},
    "mechanisms": {{
        "identified": [
            {{"mechanism": "description", "count": N, "example_ad": "hook snippet"}},
            ...
        ],
        "overused": ["mechanism1"],
        "underutilized": ["mechanism2", "mechanism3"]
    }}
}}"""

    try:
        anthropic_limiter.wait()
        message = api_keys.ANTHROPIC_CLIENT.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        # Extract text from response
        content = ""
        if message.content and len(message.content) > 0:
            content_block = message.content[0]
            if hasattr(content_block, 'text'):
                content = content_block.text.strip()
            else:
                content = str(content_block).strip()
        
        # Parse JSON
        if '```json' in content:
            content = content.split('```json')[1].split('```')[0]
        elif '```' in content:
            content = content.split('```')[1].split('```')[0]
        
        return json.loads(content)
        
    except Exception as e:
        print(f"[WARNING] Enhanced analysis extraction failed: {e}")
        return {
            'personas': {'identified': [], 'overused': [], 'underutilized': []},
            'desires_problems': {'identified': [], 'overused': [], 'underutilized': []},
            'mechanisms': {'identified': [], 'overused': [], 'underutilized': []}
        }


def _generate_gap_analysis(
    extraction: Dict[str, Any],
    topic: str,
    offer_type: str
) -> Dict[str, Any]:
    """
    Generate gap analysis recommendations based on extracted data.
    
    Args:
        extraction: Output from _extract_personas_desires_mechanisms
        topic: The search topic
        offer_type: Type of offer
        
    Returns:
        Gap analysis with recommendations
    """
    if not api_keys.ANTHROPIC_CLIENT:
        api_keys.initialize_clients()
    
    if not api_keys.ANTHROPIC_CLIENT:
        return {'error': 'Anthropic client not configured'}
    
    # Get underutilized items
    underutilized_personas = extraction.get('personas', {}).get('underutilized', [])
    underutilized_desires = extraction.get('desires_problems', {}).get('underutilized', [])
    underutilized_mechanisms = extraction.get('mechanisms', {}).get('underutilized', [])
    
    # Get overused items  
    overused_personas = extraction.get('personas', {}).get('overused', [])
    overused_desires = extraction.get('desires_problems', {}).get('overused', [])
    overused_mechanisms = extraction.get('mechanisms', {}).get('overused', [])
    
    prompt = f"""You are a marketing strategist. Based on competitor analysis for "{topic}" ({offer_type}):

OVERUSED (competitors are saturating these):
- Personas: {', '.join(overused_personas) if overused_personas else 'None identified'}
- Desires: {', '.join(overused_desires) if overused_desires else 'None identified'}
- Mechanisms: {', '.join(overused_mechanisms) if overused_mechanisms else 'None identified'}

UNDERUTILIZED (opportunity gaps):
- Personas: {', '.join(underutilized_personas) if underutilized_personas else 'None identified'}
- Desires: {', '.join(underutilized_desires) if underutilized_desires else 'None identified'}
- Mechanisms: {', '.join(underutilized_mechanisms) if underutilized_mechanisms else 'None identified'}

Generate 3 specific DIFFERENTIATION STRATEGIES that:
1. Target a DIFFERENT persona than competitors
2. Address a DIFFERENT desire/problem than competitors
3. Use a DIFFERENT mechanism than competitors

For each strategy, provide:
- Target persona (specific, not generic)
- Desire/problem addressed
- Mechanism to use
- Sample hook angle

Return JSON:
{{
    "recommended_strategies": [
        {{
            "strategy_name": "Name",
            "target_persona": "Specific persona description",
            "desire_problem": "The desire or problem to address",
            "mechanism": "The mechanism to use",
            "sample_hook_angle": "A hook angle that combines these",
            "differentiation_reason": "Why this differentiates from competitors"
        }},
        ...
    ],
    "avoid_combinations": [
        "persona + desire + mechanism to avoid (too crowded)"
    ],
    "overall_opportunity": "One sentence summary of the biggest opportunity"
}}"""

    try:
        anthropic_limiter.wait()
        message = api_keys.ANTHROPIC_CLIENT.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}]
        )
        
        # Extract text from response
        content = ""
        if message.content and len(message.content) > 0:
            content_block = message.content[0]
            if hasattr(content_block, 'text'):
                content = content_block.text.strip()
            else:
                content = str(content_block).strip()
        
        # Parse JSON
        if '```json' in content:
            content = content.split('```json')[1].split('```')[0]
        elif '```' in content:
            content = content.split('```')[1].split('```')[0]
        
        return json.loads(content)
        
    except Exception as e:
        print(f"[WARNING] Gap analysis generation failed: {e}")
        return {
            'recommended_strategies': [],
            'avoid_combinations': [],
            'overall_opportunity': 'Unable to generate gap analysis'
        }


def get_enhanced_competitor_analysis(
    topic: str,
    offer_type: str = "service",
    extra_keywords: Optional[List[str]] = None,
    extract_media: bool = True,
    limit: Optional[int] = None,
    relevance_profile: Optional[Dict[str, Any]] = None,
    offers: Optional[List[str]] = None,
    use_cache: bool = True,
    non_interactive: bool = False,
    positive_keywords: Optional[List[str]] = None,
    negative_keywords: Optional[List[str]] = None,
    auto_generate_keywords: bool = True,
    skip_offer_filters: bool = False,
    max_ads: int = 30
) -> Dict[str, Any]:
    """
    Perform ENHANCED competitor analysis with persona/desire/mechanism gap analysis.
    
    This extends get_competitor_analysis() by:
    1. Sorting ads by longest running first (most proven)
    2. Extracting personas that competitors are speaking to
    3. Extracting desires/problems that competitors address
    4. Extracting mechanisms competitors use
    5. Performing gap analysis to find differentiation opportunities
    
    Args:
        topic: The search topic (e.g., "exterior painting")
        offer_type: Type of offer ("service" or "ecom")
        extra_keywords: Additional positive keywords to include
        extract_media: Whether to extract media from ads
        limit: Maximum number of hooks to extract
        relevance_profile: Legacy profile dict (deprecated)
        offers: List of offer strings
        use_cache: Whether to use cached data
        non_interactive: Skip user confirmation prompts
        positive_keywords: Required keywords (max 2)
        negative_keywords: Exclusion keywords (max 5)
        auto_generate_keywords: Whether to auto-generate keywords
        skip_offer_filters: Skip generating and using filters for offers (no keyword filtering)
        max_ads: Maximum number of ads to scrape (controls scroll_limit, default: 30)
        
    Returns:
        Enhanced competitor analysis data with gap analysis
    """
    print(f"\n{'='*60}")
    print(f"  ENHANCED COMPETITOR ANALYSIS")
    print(f"{'='*60}")
    
    # Step 1: Get basic competitor data using existing function
    print(f"\n[ENHANCED ANALYSIS] Step 1/5: Scraping competitor ads...")
    basic_data = get_competitor_analysis(
        topic=topic,
        offer_type=offer_type,
        extra_keywords=extra_keywords,
        extract_media=extract_media,
        limit=limit,
        relevance_profile=relevance_profile,
        offers=offers,
        use_cache=use_cache,
        non_interactive=non_interactive,
        positive_keywords=positive_keywords,
        negative_keywords=negative_keywords,
        auto_generate_keywords=auto_generate_keywords,
        skip_offer_filters=skip_offer_filters,
        max_ads=max_ads
    )
    
    hooks = basic_data.get('hooks', [])
    
    if not hooks:
        print("[WARNING] No competitor hooks found, returning basic data")
        basic_data['analysis_type'] = 'enhanced'
        basic_data['enhanced_analysis_failed'] = True
        return basic_data
    
    # Step 2: Sort by longest running (age_days descending)
    print(f"\n[ENHANCED ANALYSIS] Step 2/5: Sorting by longest running ads...")
    
    # Add age_days to hooks if not present (from ad_type)
    for hook in hooks:
        if hook.get('ad_type') == 'proven':
            hook['age_days'] = 30  # Proven = 30+ days
        elif hook.get('ad_type') == 'established':
            hook['age_days'] = 14  # Established = 7-30 days  
        else:
            hook['age_days'] = 3   # Fresh = <7 days
    
    sorted_hooks = sorted(hooks, key=lambda x: x.get('age_days', 0) if isinstance(x, dict) else 0, reverse=True)
    if sorted_hooks and len(sorted_hooks) > 0 and isinstance(sorted_hooks[0], dict):
        print(f"[OK] Sorted {len(sorted_hooks)} ads (oldest first: {sorted_hooks[0].get('age_days', 0)} days)")
    else:
        print(f"[OK] Sorted {len(sorted_hooks)} ads")
    
    # Step 3-4: Extract personas, desires, and mechanisms
    print(f"\n[ENHANCED ANALYSIS] Step 3/5: Extracting personas from competitor ads...")
    print(f"[ENHANCED ANALYSIS] Step 4/5: Analyzing desires and mechanisms...")
    
    extraction = _extract_personas_desires_mechanisms(sorted_hooks)
    
    personas = extraction.get('personas', {})
    desires = extraction.get('desires_problems', {})
    mechanisms = extraction.get('mechanisms', {})
    
    print(f"[OK] Found {len(personas.get('identified', []))} personas, "
          f"{len(desires.get('identified', []))} desires, "
          f"{len(mechanisms.get('identified', []))} mechanisms")
    
    if personas.get('overused'):
        print(f"[OVERUSED] Personas: {', '.join(personas['overused'][:3])}")
    if desires.get('overused'):
        print(f"[OVERUSED] Desires: {', '.join(desires['overused'][:3])}")
    if mechanisms.get('overused'):
        print(f"[OVERUSED] Mechanisms: {', '.join(mechanisms['overused'][:3])}")
    
    # Step 5: Gap analysis
    print(f"\n[ENHANCED ANALYSIS] Step 5/5: Performing gap analysis...")
    
    gap_analysis = _generate_gap_analysis(extraction, topic, offer_type)
    
    strategies = gap_analysis.get('recommended_strategies', [])
    if strategies:
        print(f"\n[GAP ANALYSIS] Found {len(strategies)} differentiation strategies:")
        for i, strategy in enumerate(strategies, 1):
            print(f"  {i}. {strategy.get('strategy_name', 'Unnamed')}")
            print(f"     -> Target: {strategy.get('target_persona', 'N/A')[:50]}")
            print(f"     -> Hook angle: {strategy.get('sample_hook_angle', 'N/A')[:60]}")
    
    if gap_analysis.get('overall_opportunity'):
        print(f"\n[OPPORTUNITY] {gap_analysis['overall_opportunity']}")
    
    # Build enhanced data structure
    enhanced_data = {
        **basic_data,
        'analysis_type': 'enhanced',
        'hooks': sorted_hooks,  # Use sorted hooks
        'persona_analysis': {
            'common_personas': [p.get('persona') for p in personas.get('identified', [])],
            'persona_distribution': {p.get('persona'): p.get('count', 0) for p in personas.get('identified', [])},
            'overused_personas': personas.get('overused', []),
            'underutilized_personas': personas.get('underutilized', []),
            'detailed': personas.get('identified', [])
        },
        'desire_problem_analysis': {
            'common_desires': [d.get('desire') for d in desires.get('identified', [])],
            'desire_distribution': {d.get('desire'): d.get('count', 0) for d in desires.get('identified', [])},
            'overused_desires': desires.get('overused', []),
            'underutilized_desires': desires.get('underutilized', []),
            'detailed': desires.get('identified', [])
        },
        'mechanism_analysis': {
            'common_mechanisms': [m.get('mechanism') for m in mechanisms.get('identified', [])],
            'mechanism_distribution': {m.get('mechanism'): m.get('count', 0) for m in mechanisms.get('identified', [])},
            'overused_mechanisms': mechanisms.get('overused', []),
            'underutilized_mechanisms': mechanisms.get('underutilized', []),
            'detailed': mechanisms.get('identified', [])
        },
        'gap_analysis': {
            'recommended_strategies': gap_analysis.get('recommended_strategies', []),
            'avoid_combinations': gap_analysis.get('avoid_combinations', []),
            'overall_opportunity': gap_analysis.get('overall_opportunity', ''),
            'recommended_personas': personas.get('underutilized', []),
            'recommended_desires': desires.get('underutilized', []),
            'recommended_mechanisms': mechanisms.get('underutilized', [])
        }
    }
    
    print(f"\n{'='*60}")
    print(f"  ENHANCED ANALYSIS COMPLETE")
    print(f"{'='*60}\n")
    
    return enhanced_data
