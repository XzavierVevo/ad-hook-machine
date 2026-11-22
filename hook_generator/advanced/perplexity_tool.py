"""
Perplexity Research Tool - Real-time web research for trend analysis.

This tool uses the Perplexity API (via OpenAI-compatible client) to
search the web for current trends, controversies, and insights.
"""

import json
from typing import Dict, Any, Optional
from datetime import datetime

from .agent_tools import register_tool
from .. import api_keys
from .. import config
from ..cache_manager import get_cached, set_cached, track_cost


@register_tool(
    name="research_trends",
    description="Search the web for current marketing trends, viral hooks, and competitor strategies in a given niche.",
    parameters={
        "niche": {"type": "string", "description": "The niche to research (e.g., 'house painting', 'supplements')"},
        "ragebait_level": {"type": "integer", "description": "How controversial the research should be (0-10)"}
    }
)
def research_trends(
    niche: str,
    ragebait_level: int = 3
) -> Dict[str, Any]:
    """
    Research current trends for a niche using Perplexity.
    
    Args:
        niche: The niche to research
        ragebait_level: How controversial to make the research (0-10)
        
    Returns:
        Dictionary with trend insights
    """
    print(f"\n[TOOL: research_trends] Researching trends for '{niche}'...")
    
    # Check cache first
    cache_key = f"trends:{niche}:{ragebait_level}"
    cached = get_cached('trend_research', cache_key)
    if cached:
        print(f"[TOOL] Using cached trend research")
        return cached
    
    # Check if Perplexity is available
    if not api_keys.PERPLEXITY_API_KEY:
        print(f"[TOOL WARNING] Perplexity API key not configured")
        return {
            'success': False,
            'error': 'Perplexity API key not configured',
            'trending_angles': [],
            'avoid_angles': [],
            'current_events': []
        }
    
    # Initialize client if needed
    if not api_keys.PERPLEXITY_CLIENT:
        api_keys.initialize_clients()
    
    if not api_keys.PERPLEXITY_CLIENT:
        return {
            'success': False,
            'error': 'Failed to initialize Perplexity client',
            'trending_angles': [],
            'avoid_angles': [],
            'current_events': []
        }
    
    # Build search prompt from config
    now = datetime.now()
    search_prompt = config.AI_PROMPTS['perplexity_research']['trend_search'].format(
        niche=niche,
        month=now.strftime('%B'),
        year=now.year
    )
    
    try:
        response = api_keys.PERPLEXITY_CLIENT.chat.completions.create(
            model="sonar",
            messages=[
                {"role": "user", "content": search_prompt}
            ]
        )
        
        search_results = response.choices[0].message.content
        
        # Summarize the results
        summary_prompt = config.AI_PROMPTS['perplexity_research']['summarize_research'].format(
            results=search_results
        )
        
        summary_response = api_keys.PERPLEXITY_CLIENT.chat.completions.create(
            model="sonar",
            messages=[
                {"role": "user", "content": summary_prompt}
            ]
        )
        
        summary_text_raw = summary_response.choices[0].message.content
        if summary_text_raw is None:
            return {
                'trending_angles': [],
                'avoid_angles': [],
                'current_events': [],
                'emotional_triggers': [],
                'recommended_ragebait_level': 3
            }
        summary_text = summary_text_raw
        
        # Parse the summary
        try:
            if "```" in summary_text:
                summary_text = summary_text.split("```")[1]
                if summary_text.startswith("json"):
                    summary_text = summary_text[4:]
            summary = json.loads(summary_text.strip())
        except json.JSONDecodeError:
            summary = {
                'trending_angles': [],
                'avoid_angles': [],
                'current_events': [],
                'emotional_triggers': [],
                'recommended_ragebait_level': ragebait_level,
                'raw_research': search_results
            }
        
        result = {
            'success': True,
            'niche': niche,
            'ragebait_level': ragebait_level,
            **summary,
            'raw_research': search_results
        }
        
        # Cache the result
        set_cached('trend_research', cache_key, result)
        
        return result
        
    except Exception as e:
        print(f"[TOOL ERROR] research_trends failed: {e}")
        return {
            'success': False,
            'error': str(e),
            'trending_angles': [],
            'avoid_angles': [],
            'current_events': []
        }


@register_tool(
    name="search_ragebait_angles",
    description="Search for controversial angles, complaints, and frustrations about a niche that can be used for ragebait hooks.",
    parameters={
        "niche": {"type": "string", "description": "The niche to research"}
    }
)
def search_ragebait_angles(niche: str) -> Dict[str, Any]:
    """
    Search for controversial/ragebait angles in a niche.
    
    Args:
        niche: The niche to research
        
    Returns:
        Dictionary with ragebait angle insights
    """
    print(f"\n[TOOL: search_ragebait_angles] Finding controversies for '{niche}'...")
    
    # Check cache
    cache_key = f"ragebait:{niche}"
    cached = get_cached('trend_research', cache_key)
    if cached:
        print(f"[TOOL] Using cached ragebait research")
        return cached
    
    if not api_keys.PERPLEXITY_CLIENT:
        if api_keys.PERPLEXITY_API_KEY:
            api_keys.initialize_clients()
    
    if not api_keys.PERPLEXITY_CLIENT:
        return {
            'success': False,
            'error': 'Perplexity not available',
            'controversies': [],
            'complaints': [],
            'us_vs_them': []
        }
    
    # Build ragebait search prompt
    search_prompt = config.AI_PROMPTS['perplexity_research']['ragebait_search'].format(
        niche=niche
    )
    
    try:
        response = api_keys.PERPLEXITY_CLIENT.chat.completions.create(
            model="sonar",
            messages=[
                {"role": "user", "content": search_prompt}
            ]
        )
        
        result = {
            'success': True,
            'niche': niche,
            'raw_results': response.choices[0].message.content,
            'controversies': [],
            'complaints': [],
            'us_vs_them': []
        }
        
        # Cache result
        set_cached('trend_research', cache_key, result)
        
        return result
        
    except Exception as e:
        print(f"[TOOL ERROR] search_ragebait_angles failed: {e}")
        return {
            'success': False,
            'error': str(e),
            'controversies': [],
            'complaints': [],
            'us_vs_them': []
        }
