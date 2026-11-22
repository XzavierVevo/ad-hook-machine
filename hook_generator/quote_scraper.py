"""
Quote scraping using ChatGPT to find emotional quotes from online discussions.
"""

import json
from pathlib import Path
from typing import List, Optional, Dict, Any

from . import api_keys
from . import config
from .rate_limiter import openai_limiter
from .logger import bot_logger, log_data


def scrape_quotes(
    topic: str,
    num_quotes: int,
    offer_type: str = "service",
    offers: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Use ChatGPT to generate emotional quotes related to a topic.
    
    Args:
        topic: The topic/niche to find quotes about
        num_quotes: Number of quotes to generate
        offer_type: Type of offer ('service' or 'ecom')
        offers: List of specific offers (for service type)
        
    Returns:
        List of quote dictionaries with 'quote', 'emotion', 'context'
    """
    if not api_keys.OPENAI_CLIENT:
        api_keys.initialize_clients()
    
    if not api_keys.OPENAI_CLIENT:
        raise ValueError("OpenAI API key not configured")
    
    # Build the prompt from config
    offer_context = ""
    if offers:
        offer_context = f"""
The quotes should relate to these specific service offers:
{chr(10).join(f'- {offer}' for offer in offers)}

CRITICAL: If a quote mentions a price or specific service detail, it MUST match the offers above exactly. Do not invent new price points.
"""
    
    prompt = config.AI_PROMPTS['quote_scraping'].format(
        topic=topic,
        offer_type=offer_type,
        offer_context=offer_context,
        num_quotes=num_quotes,
        max_words=config.MAX_HOOK_WORD_COUNT
    )

    try:
        openai_limiter.wait()
        response = api_keys.OPENAI_CLIENT.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert copywriter who understands customer psychology and emotional pain points."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.8,
            max_tokens=4000
        )
        
        if not response.choices or len(response.choices) == 0:
            print("[ERROR] No choices in response")
            return []
        
        content_raw = response.choices[0].message.content
        if content_raw is None:
            print("[ERROR] No content in response")
            return []
        content = content_raw.strip()
        
        # Parse JSON response
        # Handle potential markdown code blocks
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        
        quotes = json.loads(content)
        
        # Log the generated quotes
        log_data(quotes, f"Generated {len(quotes)} quotes from ChatGPT")
        
        return quotes
        
    except json.JSONDecodeError as e:
        print(f"[ERROR] Failed to parse quotes JSON: {e}")
        # Try to get content for error message (content may not be defined if error occurred before assignment)
        try:
            content_for_log = locals().get('content', 'N/A')
            if content_for_log != 'N/A':
                print(f"Raw response: {content_for_log[:500]}...")
        except (KeyError, AttributeError) as e:
            bot_logger.debug(f"Could not retrieve content for error log: {e}")
            pass
        return []
    except Exception as e:
        print(f"[ERROR] Failed to scrape quotes: {e}")
        return []


def save_quotes(quotes: List[Dict[str, Any]], output_path: Path) -> bool:
    """
    Save quotes to a JSON file.
    
    Args:
        quotes: List of quote dictionaries
        output_path: Path to save the JSON file
        
    Returns:
        True if successful
    """
    try:
        from pathlib import Path
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(quotes, f, indent=2, ensure_ascii=False)
        
        return True
    except Exception as e:
        print(f"[ERROR] Failed to save quotes: {e}")
        return False

