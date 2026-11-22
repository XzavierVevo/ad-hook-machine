"""
Facebook Ad Library Tool - Wraps browser_scraper.py as an agent tool.

This tool allows the thinking agent to search the Meta Ad Library
for competitor ads.
"""

from typing import Dict, Any, List, Optional

from .agent_tools import register_tool
from ..competitor_data_puller import get_competitor_analysis
from ..cache_manager import get_cached, set_cached


@register_tool(
    name="search_facebook_ads",
    description="Search the Meta Ad Library for competitor ads in a given niche/topic. Returns hooks, offers, and patterns from active ads.",
    parameters={
        "topic": {"type": "string", "description": "The niche or topic to search for (e.g., 'house painting', 'weight loss supplements')"},
        "offers": {"type": "array", "description": "Optional list of our offers for relevance filtering"},
        "limit": {"type": "integer", "description": "Maximum number of ads to analyze (default: 20)"},
        "non_interactive": {"type": "boolean", "description": "Skip user prompts (default: True for agent use)"},
        "positive_keywords": {"type": "array", "description": "Optional list of positive/required keywords (max 2)"},
        "negative_keywords": {"type": "array", "description": "Optional list of negative/exclusion keywords (max 5)"}
    }
)
def search_facebook_ads(
    topic: str,
    offers: Optional[List[str]] = None,
    limit: int = 20,
    non_interactive: bool = True,
    use_cache: bool = True,
    positive_keywords: Optional[List[str]] = None,
    negative_keywords: Optional[List[str]] = None,
    auto_generate_keywords: bool = True,
    skip_offer_filters: bool = False,
    max_ads: int = 30
) -> Dict[str, Any]:
    """
    Search Facebook Ad Library for competitor ads.
    
    This wraps the existing competitor_data_puller.get_competitor_analysis
    function to make it available as an agent tool.
    
    Args:
        topic: Search topic/niche
        offers: Our offers for relevance filtering
        limit: Maximum ads to analyze
        non_interactive: Skip user prompts
        use_cache: Whether to use cached results
        positive_keywords: List of positive/required keywords (max 2)
        negative_keywords: List of negative/exclusion keywords (max 5)
        auto_generate_keywords: Whether to auto-generate keywords with Claude
        skip_offer_filters: Skip generating and using filters for offers
        max_ads: Maximum number of ads to scrape (controls scroll_limit, default: 30)
        
    Returns:
        Dictionary with competitor analysis results including:
        - hooks: List of extracted hooks with offers
        - patterns: Common patterns found
        - insights: Analysis insights
    """
    print(f"\n[TOOL: search_facebook_ads] Searching for '{topic}'...")
    
    try:
        # Call the existing competitor analysis function
        result = get_competitor_analysis(
            topic=topic,
            offer_type="service",
            offers=offers if offers is not None else [],
            limit=limit,
            non_interactive=non_interactive,
            use_cache=use_cache,
            positive_keywords=positive_keywords,
            negative_keywords=negative_keywords,
            auto_generate_keywords=auto_generate_keywords,
            skip_offer_filters=skip_offer_filters,
            max_ads=max_ads
        )
        
        # Format result for agent consumption
        hooks = result.get('hooks', [])
        
        return {
            'success': True,
            'ad_count': len(hooks),
            'hooks': hooks,
            'breakdown': result.get('breakdown', {}),
            'patterns': result.get('patterns', {}),
            'insights': result.get('insights', {}),
            'overused_patterns': result.get('overused_patterns', []),
            'competitors': result.get('competitors', [])
        }
        
    except Exception as e:
        print(f"[TOOL ERROR] search_facebook_ads failed: {e}")
        return {
            'success': False,
            'error': str(e),
            'ad_count': 0,
            'hooks': []
        }


def get_competitor_hooks_for_fusion(
    topic: str,
    min_hooks: int = 10,
    max_iterations: int = 3
) -> List[Dict]:
    """
    Get competitor hooks specifically for fusion with our offers.
    
    This function will iteratively broaden the search if not enough
    hooks are found.
    
    Args:
        topic: Search topic
        min_hooks: Minimum hooks required
        max_iterations: Maximum search iterations
        
    Returns:
        List of hooks suitable for fusion
    """
    hooks = []
    current_topic = topic
    
    for i in range(max_iterations):
        result = search_facebook_ads(
            topic=current_topic,
            limit=50,
            non_interactive=True
        )
        
        if result.get('success'):
            hooks.extend(result.get('hooks', []))
            
            # Filter for hooks with valid offers
            hooks_with_offers = [
                h for h in hooks 
                if h.get('offer') and h.get('offer') != 'N/A'
            ]
            
            if len(hooks_with_offers) >= min_hooks:
                return hooks_with_offers[:50]
        
        # Broaden search for next iteration
        if ' ' in current_topic:
            current_topic = current_topic.split()[0]
        else:
            current_topic = f"{current_topic} services"
    
    return hooks[:50]
