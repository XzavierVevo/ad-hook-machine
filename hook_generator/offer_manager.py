"""
Offer management for handling multiple service offers.
"""

import json
from pathlib import Path
from typing import List, Tuple, Dict, Any

from . import config
from . import api_keys
from .rate_limiter import openai_limiter


def load_offers_from_file(offers_file: Path) -> List[str]:
    """
    Load offers from a text file (one offer per line).
    
    Args:
        offers_file: Path to the offers.txt file
        
    Returns:
        List of offer strings
    """
    offers = []
    
    if not offers_file.exists():
        print(f"[WARNING] Offers file not found: {offers_file}")
        return offers
    
    try:
        with open(offers_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    offers.append(line)
    except (IOError, PermissionError, UnicodeDecodeError) as e:
        print(f"[ERROR] Failed to read offers file {offers_file}: {e}")
        return []
    
    return offers


def distribute_hooks_across_offers(
    total_hooks: int,
    offers: List[str]
) -> List[Tuple[str, int]]:
    """
    Distribute hooks evenly across multiple offers.
    
    Args:
        total_hooks: Total number of hooks to generate
        offers: List of offer strings
        
    Returns:
        List of tuples (offer, hook_count)
    """
    if not offers:
        return []
    
    num_offers = len(offers)
    base_count = total_hooks // num_offers
    remainder = total_hooks % num_offers
    
    distribution = []
    for i, offer in enumerate(offers):
        # Distribute remainder to first offers
        count = base_count + (1 if i < remainder else 0)
        distribution.append((offer, count))
    
    return distribution


def create_offers_template(offers_file: Path) -> bool:
    """
    Create a template offers.txt file.
    
    Args:
        offers_file: Path to create the offers.txt file
        
    Returns:
        True if successful
    """
    template = """# Service Offers - One per line
# Example offers for a painting service:
#
# $450 per painted room
# Room painted every 1-2 weeks
# Room painted within 1 week
# Free estimate within 24 hours
#
# Delete these comments and add your own offers below:

"""
    
    try:
        offers_file.parent.mkdir(parents=True, exist_ok=True)
        with open(offers_file, 'w', encoding='utf-8') as f:
            f.write(template)
        return True
    except Exception as e:
        print(f"[ERROR] Failed to create offers template: {e}")
        return False


def validate_offers(offers: List[str]) -> Tuple[bool, str]:
    """
    Validate that offers are properly formatted.
    
    Args:
        offers: List of offer strings
        
    Returns:
        Tuple of (is_valid, message)
    """
    if not offers:
        return False, "No offers found. Please add at least one offer to offers.txt"
    
    # Check for empty offers
    empty_count = sum(1 for o in offers if not o.strip())
    if empty_count > 0:
        return False, f"Found {empty_count} empty offers"
    
    # Check for very short offers
    short_offers = [o for o in offers if len(o) < 5]
    if short_offers:
        return False, f"Some offers are too short: {short_offers}"
    
    return True, f"Valid: {len(offers)} offers loaded"


def generate_relevance_profile(offers: List[str], offer_type: str = "service") -> Dict[str, Any]:
    """
    Generate a relevance profile from user's offers using LLM analysis.
    This profile contains search terms, target mechanisms, and anti-patterns
    for automatically filtering competitor ads.
    
    Args:
        offers: List of offer strings from offers.txt
        offer_type: Type of offer ('service' or 'ecom')
        
    Returns:
        Dictionary with:
            - primary_search_terms: Best keywords for Meta Ad Library search
            - target_mechanism: The specific "how" or unique selling proposition
            - anti_patterns: What to exclude (negative keywords)
            - service_category: General category of the service/product
            - intent: The core intent (e.g., 'customer_acquisition', 'hiring')
    """
    if not api_keys.OPENAI_CLIENT:
        api_keys.initialize_clients()
    
    if not api_keys.OPENAI_CLIENT:
        print("[WARNING] OpenAI client not available, using basic keyword extraction")
        # Fallback to basic extraction
        return _generate_basic_profile(offers)
    
    offers_text = "\n".join([f"- {offer}" for offer in offers])
    
    prompt = config.AI_PROMPTS['offer_management']['relevance_profile'].format(
        offer_type=offer_type,
        offers_text=offers_text
    )
    
    try:
        openai_limiter.wait()
        response = api_keys.OPENAI_CLIENT.chat.completions.create(
            model=getattr(config, 'INTENT_CLASSIFICATION_MODEL', 'gpt-4o-mini'),
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert at analyzing business offers and generating precise search/filter criteria. Always return valid JSON only."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.3,
            max_tokens=500
        )
        
        if not response.choices or len(response.choices) == 0:
            print("[ERROR] No choices in response for relevance profile generation")
            return _generate_basic_profile(offers)
        
        content = response.choices[0].message.content
        if content is None:
            print("[ERROR] No content in response for relevance profile generation")
            return _generate_basic_profile(offers)
        
        content = content.strip()
        
        # Clean up JSON if wrapped in markdown
        if '```json' in content:
            content = content.split('```json')[1].split('```')[0]
        elif '```' in content:
            content = content.split('```')[1].split('```')[0]
        
        profile = json.loads(content)
        
        # Validate structure
        required_keys = ['primary_search_terms', 'target_mechanism', 'anti_patterns', 'service_category']
        for key in required_keys:
            if key not in profile:
                print(f"[WARNING] Profile missing key '{key}', using fallback")
                return _generate_basic_profile(offers)
        
        # Limit anti_patterns to maximum of 5
        if len(profile['anti_patterns']) > 5:
            profile['anti_patterns'] = profile['anti_patterns'][:5]
        
        print(f"[OK] Generated relevance profile:")
        print(f"  Target mechanism: {profile['target_mechanism']}")
        print(f"  Anti-patterns: {len(profile['anti_patterns'])} exclusion rules")
        
        return profile
        
    except Exception as e:
        print(f"[WARNING] Failed to generate LLM profile: {e}")
        print("[INFO] Using basic keyword extraction fallback")
        return _generate_basic_profile(offers)


def _generate_basic_profile(offers: List[str]) -> Dict[str, Any]:
    """
    Fallback basic profile generation when LLM is unavailable.
    
    Args:
        offers: List of offer strings
        
    Returns:
        Basic profile dictionary
    """
    # Extract keywords from offers
    all_text = " ".join(offers).lower()
    
    # Common stop words
    stop_words = set(['the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'per', 'within', 'every', 'free', 'within'])
    
    # Extract meaningful words
    words = [w.strip('.,!?;:()[]{}') for w in all_text.split() if len(w) > 3 and w.lower() not in stop_words]
    
    # Get most common words (simple approach)
    from collections import Counter
    word_counts = Counter(words)
    top_words = [word for word, count in word_counts.most_common(5)]
    
    return {
        'primary_search_terms': top_words[:5] if top_words else ['service'],
        'target_mechanism': ' '.join(offers[:2])[:100],  # First two offers as mechanism
        'anti_patterns': ['hiring', 'careers', 'job', 'recruitment', 'we are hiring'],
        'service_category': 'service'
    }

