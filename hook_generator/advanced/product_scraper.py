"""
Product Scraper Tool - Extracts product information from any URL using Crawl4AI.

This tool allows the agent to scrape product pages from:
- Shopify stores
- ClickBank product pages
- SaaS landing pages
- Any e-commerce or service page
"""

import json
from typing import Dict, Any, List, Optional

from .agent_tools import register_tool
from .. import api_keys
from .. import config
from ..cache_manager import get_cached, set_cached, track_cost


# Try to import Crawl4AI
try:
    from crawl4ai import AsyncWebCrawler
    from crawl4ai.extraction_strategy import LLMExtractionStrategy
    import asyncio
    CRAWL4AI_AVAILABLE = True
except ImportError:
    CRAWL4AI_AVAILABLE = False
    AsyncWebCrawler = None  # type: ignore
    LLMExtractionStrategy = None  # type: ignore
    asyncio = None  # type: ignore
    print("[WARNING] Crawl4AI not installed. Run: pip install crawl4ai && crawl4ai-setup")


@register_tool(
    name="scrape_product",
    description="Extract product/service information from any webpage URL including price, features, target audience, and offers.",
    parameters={
        "url": {"type": "string", "description": "The URL of the product/service page to scrape"}
    }
)
def scrape_product_page(url: str) -> Dict[str, Any]:
    """
    Scrape a product page and extract structured information.
    
    Args:
        url: URL of the product page
        
    Returns:
        Dictionary with extracted product information
    """
    print(f"\n[TOOL: scrape_product] Scraping {url}...")
    
    # Check cache
    cache_key = f"product:{url}"
    cached = get_cached('product_scrape', cache_key)
    if cached:
        print(f"[TOOL] Using cached product data")
        return cached
    
    if not CRAWL4AI_AVAILABLE:
        return {
            'success': False,
            'error': 'Crawl4AI not installed. Run: pip install crawl4ai && crawl4ai-setup',
            'url': url
        }
    
    try:
        # Check if Crawl4AI is available
        if not CRAWL4AI_AVAILABLE:
            return {
                'success': False,
                'error': 'Crawl4AI not available',
                'url': url
            }
        
        # Type guard: ensure imports are available
        if AsyncWebCrawler is None or LLMExtractionStrategy is None or asyncio is None:
            return {
                'success': False,
                'error': 'Crawl4AI modules not properly imported',
                'url': url
            }
        
        # At this point, we know AsyncWebCrawler and LLMExtractionStrategy are not None
        # Use type: ignore to tell Pyright that we've checked
        AsyncWebCrawler_cls = AsyncWebCrawler  # type: ignore
        LLMExtractionStrategy_cls = LLMExtractionStrategy  # type: ignore
        asyncio_module = asyncio  # type: ignore
        
        # Create crawler (async)
        async def _crawl_page():
            crawler = AsyncWebCrawler_cls()
            # warmup is optional, check if it exists
            warmup_method = getattr(crawler, 'warmup', None)
            if warmup_method:
                await warmup_method()
            
            # Get extraction prompt from config
            extraction_prompt = config.AI_PROMPTS['product_scraper']['extract_product_info'].format(
                url=url,
                content="{content}"  # Will be filled by crawler
            )
            
            # Create extraction strategy
            extraction_strategy = LLMExtractionStrategy_cls(
                provider="openai/gpt-4o-mini",
                api_token=api_keys.OPENAI_API_KEY,
                schema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "price": {"type": "string"},
                        "features": {"type": "array", "items": {"type": "string"}},
                        "target_audience": {"type": "string"},
                        "usp": {"type": "string"},
                        "offers": {"type": "array", "items": {"type": "string"}},
                        "confidence": {"type": "string"}
                    }
                },
                extraction_type="schema",
                instruction=extraction_prompt
            )
            
            # Crawl the page
            result = await crawler.arun(
                url=url,
                extraction_strategy=extraction_strategy,
                bypass_cache=False
            )
            return result
        
        # Run async crawl
        result = asyncio_module.run(_crawl_page())
        
        if result is not None and hasattr(result, 'success') and getattr(result, 'success', False):
            # Parse extracted content
            try:
                extracted_content = getattr(result, 'extracted_content', None)
                extracted = json.loads(extracted_content) if extracted_content else {}
            except (json.JSONDecodeError, AttributeError):
                extracted = {}
            
            html_content = getattr(result, 'html', None)
            product_data = {
                'success': True,
                'url': url,
                'name': extracted.get('name', 'Unknown Product'),
                'price': extracted.get('price', 'N/A'),
                'features': extracted.get('features', []),
                'target_audience': extracted.get('target_audience', ''),
                'usp': extracted.get('usp', ''),
                'offers': extracted.get('offers', []),
                'confidence': extracted.get('confidence', 'medium'),
                'raw_html_length': len(html_content) if html_content else 0
            }
            
            # Cache result
            set_cached('product_scrape', cache_key, product_data)
            
            return product_data
        else:
            return {
                'success': False,
                'error': 'Failed to crawl page',
                'url': url
            }
            
    except Exception as e:
        print(f"[TOOL ERROR] scrape_product failed: {e}")
        
        # Fallback: try simple requests + AI extraction
        return _fallback_scrape(url)


def _fallback_scrape(url: str) -> Dict[str, Any]:
    """Fallback scraping method using requests + AI."""
    try:
        import requests
        from bs4 import BeautifulSoup
        
        # Fetch page
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # Parse HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract text content
        for script in soup(["script", "style"]):
            script.decompose()
        text = soup.get_text(separator=' ', strip=True)[:5000]
        
        # Use AI to extract product info
        if api_keys.OPENAI_CLIENT:
            extraction_prompt = config.AI_PROMPTS['product_scraper']['extract_product_info'].format(
                url=url,
                content=text
            )
            
            response = api_keys.OPENAI_CLIENT.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": extraction_prompt}],
                max_tokens=500
            )
            
            result_text_raw = response.choices[0].message.content
            if result_text_raw is None:
                return {'success': False, 'error': 'No content in response', 'url': url}
            result_text = result_text_raw
            
            try:
                if "```" in result_text:
                    result_text = result_text.split("```")[1]
                    if result_text.startswith("json"):
                        result_text = result_text[4:]
                extracted = json.loads(result_text.strip())
            except json.JSONDecodeError:
                extracted = {}
            
            return {
                'success': True,
                'url': url,
                'method': 'fallback',
                **extracted
            }
        
        return {
            'success': False,
            'error': 'No AI available for extraction',
            'url': url
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'url': url
        }


@register_tool(
    name="generate_offers_from_product",
    description="Generate offer variations based on scraped product information.",
    parameters={
        "product_info": {"type": "object", "description": "Product information from scrape_product"},
        "count": {"type": "integer", "description": "Number of offer variations to generate"}
    }
)
def generate_offers_from_product(
    product_info: Dict[str, Any],
    count: int = 5
) -> List[Dict[str, str]]:
    """
    Generate offer variations from product information.
    
    Args:
        product_info: Product data from scrape_product
        count: Number of offers to generate
        
    Returns:
        List of offer dictionaries
    """
    print(f"\n[TOOL: generate_offers] Generating {count} offers...")
    
    if not api_keys.ANTHROPIC_CLIENT:
        api_keys.initialize_clients()
    
    if not api_keys.ANTHROPIC_CLIENT:
        # Return basic offers from product info
        offers = product_info.get('offers', [])
        return [{'offer': o, 'angle': 'extracted'} for o in offers[:count]]
    
    # Get generation prompt from config
    generation_prompt = config.AI_PROMPTS['product_scraper']['generate_offers'].format(
        count=count,
        product_info=json.dumps(product_info, indent=2)
    )
    
    try:
        model = api_keys.get_model_for_task('ad_analysis')
        response = api_keys.ANTHROPIC_CLIENT.messages.create(
            model=model,
            max_tokens=1000,
            messages=[{"role": "user", "content": generation_prompt}]
        )
        
        if hasattr(response, 'usage'):
            track_cost(model, response.usage.input_tokens, response.usage.output_tokens)
        
        # Safely extract text from response
        if response.content and len(response.content) > 0:
            content_block = response.content[0]
            if hasattr(content_block, 'text'):
                result_text = content_block.text
            else:
                result_text = str(content_block)
        else:
            result_text = ""
        
        try:
            if "```" in result_text:
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]
            offers = json.loads(result_text.strip())
            return offers
        except json.JSONDecodeError:
            return []
            
    except Exception as e:
        print(f"[TOOL ERROR] generate_offers failed: {e}")
        return []
