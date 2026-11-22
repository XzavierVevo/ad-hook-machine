"""
Agent Tools Registry - Defines all tools available to the thinking agent.

This module provides a registry of tools that the agent can use for:
- Facebook Ad Library search
- Real-time web research (Perplexity)
- Image analysis (Vision)
- Product scraping (Crawl4AI)
- Memory operations
"""

from typing import Dict, Any, List, Callable, Optional
from functools import wraps


# Tool registry
_tools: Dict[str, Dict[str, Any]] = {}


def register_tool(
    name: str,
    description: str,
    parameters: Optional[Dict[str, Any]] = None
):
    """
    Decorator to register a function as an agent tool.
    
    Args:
        name: Tool name
        description: Tool description for the agent
        parameters: Parameter schema
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        
        _tools[name] = {
            'function': wrapper,
            'description': description,
            'parameters': parameters or {}
        }
        
        return wrapper
    return decorator


def get_tool(name: str) -> Callable:
    """Get a tool function by name."""
    if name not in _tools:
        raise ValueError(f"Tool '{name}' not found. Available: {list(_tools.keys())}")
    return _tools[name]['function']


def get_all_tools() -> Dict[str, Dict[str, Any]]:
    """Get all registered tools."""
    return _tools.copy()


def get_tools_for_llm() -> List[Dict[str, Any]]:
    """
    Get tool definitions in a format suitable for LLM tool calling.
    
    Returns:
        List of tool definitions with name, description, and parameters
    """
    return [
        {
            'name': name,
            'description': info['description'],
            'parameters': info['parameters']
        }
        for name, info in _tools.items()
    ]


def call_tool(name: str, **kwargs) -> Any:
    """
    Call a tool by name with the given arguments.
    
    Args:
        name: Tool name
        **kwargs: Arguments to pass to the tool
        
    Returns:
        Tool result
    """
    tool_func = get_tool(name)
    return tool_func(**kwargs)


# Import and register all tools when this module is imported
def _register_all_tools():
    """Register all available tools."""
    try:
        from .facebook_tool import search_facebook_ads
        # Tool is already registered via decorator in facebook_tool.py
    except ImportError:
        pass
    
    try:
        from .perplexity_tool import research_trends, search_ragebait_angles
        # Tools are already registered via decorator
    except ImportError:
        pass
    
    try:
        from .vision_tool import analyze_ad_image, summarize_visual_patterns
        # Tools are already registered via decorator
    except ImportError:
        pass
    
    try:
        from .product_scraper import scrape_product_page, generate_offers_from_product
        # Tools are already registered via decorator
    except ImportError:
        pass
    
    try:
        from .agent_memory import recall_memory, save_memory
        # Tools are already registered via decorator
    except ImportError:
        pass


# Register tools on module import
_register_all_tools()
