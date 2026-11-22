"""
Universal caching system for the Ad Hook Generation Bot.

This module provides caching functionality to reduce API costs by storing
and reusing results from expensive API calls.
"""

import json
import hashlib
import functools
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Callable, Optional, Dict, List
import os

from . import config


def get_cache_path(cache_type: str, key: str) -> Path:
    """
    Get the path for a cache file.
    
    Args:
        cache_type: Type of cache (e.g., 'competitor_analysis', 'ad_analysis')
        key: Unique key for this cache entry
        
    Returns:
        Path to the cache file
    """
    cache_dir = config.CACHE_DIR / cache_type
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    # Create a safe filename from the key
    safe_key = hashlib.md5(key.encode()).hexdigest()
    return cache_dir / f"{safe_key}.json"


def is_cache_valid(cache_path: Path, cache_type: str) -> bool:
    """
    Check if a cache file is still valid (not expired).
    
    Args:
        cache_path: Path to the cache file
        cache_type: Type of cache to determine TTL
        
    Returns:
        True if cache is valid, False otherwise
    """
    if not cache_path.exists():
        return False
    
    # Get TTL for this cache type
    ttl_hours = config.CACHE_TTL_HOURS.get(cache_type, 24)
    
    # Check file modification time
    mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
    expiry_time = mtime + timedelta(hours=ttl_hours)
    
    return datetime.now() < expiry_time


def get_cached(cache_type: str, key: str) -> Optional[Any]:
    """
    Get a cached value if it exists and is valid.
    
    Args:
        cache_type: Type of cache
        key: Unique key for this cache entry
        
    Returns:
        Cached value or None if not found/expired
    """
    if not config.ENABLE_CACHING:
        return None
    
    cache_path = get_cache_path(cache_type, key)
    
    if not is_cache_valid(cache_path, cache_type):
        return None
    
    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('value')
    except (json.JSONDecodeError, IOError):
        return None


def set_cached(cache_type: str, key: str, value: Any) -> bool:
    """
    Store a value in the cache.
    
    Args:
        cache_type: Type of cache
        key: Unique key for this cache entry
        value: Value to cache (must be JSON serializable)
        
    Returns:
        True if successfully cached, False otherwise
    """
    if not config.ENABLE_CACHING:
        return False
    
    cache_path = get_cache_path(cache_type, key)
    
    try:
        data = {
            'key': key,
            'cache_type': cache_type,
            'timestamp': datetime.now().isoformat(),
            'value': value
        }
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)
        return True
    except (IOError, TypeError) as e:
        print(f"[WARNING] Failed to cache {cache_type}: {e}")
        return False


def cached_api_call(cache_type: str, key_func: Optional[Callable[..., str]] = None):
    """
    Decorator to cache API call results.
    
    Args:
        cache_type: Type of cache
        key_func: Function to generate cache key from arguments.
                  If None, uses str(args) + str(kwargs)
    
    Usage:
        @cached_api_call('competitor_analysis', lambda topic, **kw: topic)
        def get_competitor_analysis(topic, **kwargs):
            # expensive API call
            return result
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Skip caching if disabled
            if not config.ENABLE_CACHING:
                return func(*args, **kwargs)
            
            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = f"{str(args)}_{str(sorted(kwargs.items()))}"
            
            # Try to get cached result
            cached_result = get_cached(cache_type, cache_key)
            if cached_result is not None:
                print(f"[CACHE HIT] {cache_type}: {cache_key[:50]}...")
                return cached_result
            
            print(f"[CACHE MISS] {cache_type}: {cache_key[:50]}...")
            
            # Call the actual function
            result = func(*args, **kwargs)
            
            # Cache the result
            if result is not None:
                set_cached(cache_type, cache_key, result)
            
            return result
        
        return wrapper
    return decorator


def clear_cache(cache_type: Optional[str] = None) -> int:
    """
    Clear cache files.
    
    Args:
        cache_type: Type of cache to clear. If None, clears all caches.
        
    Returns:
        Number of files deleted
    """
    deleted = 0
    
    if cache_type:
        cache_dir = config.CACHE_DIR / cache_type
        if cache_dir.exists():
            for cache_file in cache_dir.glob("*.json"):
                cache_file.unlink()
                deleted += 1
            print(f"[CACHE] Cleared {deleted} {cache_type} cache files")
    else:
        if config.CACHE_DIR.exists():
            for subdir in config.CACHE_DIR.iterdir():
                if subdir.is_dir():
                    for cache_file in subdir.glob("*.json"):
                        cache_file.unlink()
                        deleted += 1
            print(f"[CACHE] Cleared {deleted} total cache files")
    
    return deleted


def get_cache_stats() -> Dict[str, Any]:
    """
    Get statistics about the cache.
    
    Returns:
        Dictionary with cache statistics
    """
    stats = {
        'enabled': config.ENABLE_CACHING,
        'cache_dir': str(config.CACHE_DIR),
        'types': {},
        'total_files': 0,
        'total_size_bytes': 0
    }
    
    if not config.CACHE_DIR.exists():
        return stats
    
    for cache_type in config.CACHE_TTL_HOURS.keys():
        cache_dir = config.CACHE_DIR / cache_type
        if cache_dir.exists():
            files = list(cache_dir.glob("*.json"))
            size = sum(f.stat().st_size for f in files)
            valid = sum(1 for f in files if is_cache_valid(f, cache_type))
            
            stats['types'][cache_type] = {
                'files': len(files),
                'valid': valid,
                'expired': len(files) - valid,
                'size_bytes': size,
                'ttl_hours': config.CACHE_TTL_HOURS.get(cache_type, 24)
            }
            stats['total_files'] += len(files)
            stats['total_size_bytes'] += size
    
    return stats


def print_cache_stats():
    """Print cache statistics in a human-readable format."""
    stats = get_cache_stats()
    
    print("\n" + "=" * 60)
    print("  CACHE STATISTICS")
    print("=" * 60)
    print(f"  Status: {'ENABLED' if stats['enabled'] else 'DISABLED'}")
    print(f"  Location: {stats['cache_dir']}")
    print(f"  Total Files: {stats['total_files']}")
    print(f"  Total Size: {stats['total_size_bytes'] / 1024:.1f} KB")
    print()
    
    if stats['types']:
        print("  By Type:")
        print("  " + "-" * 56)
        for cache_type, info in stats['types'].items():
            print(f"    {cache_type}:")
            print(f"      Files: {info['files']} ({info['valid']} valid, {info['expired']} expired)")
            print(f"      Size: {info['size_bytes'] / 1024:.1f} KB")
            print(f"      TTL: {info['ttl_hours']} hours")
    else:
        print("  No cached data found.")
    
    print("=" * 60 + "\n")


# In-memory deduplication cache for session
_dedup_cache: Dict[str, Any] = {}


def get_content_hash(content: str) -> str:
    """Generate a short hash for content deduplication."""
    return hashlib.md5(content.encode()).hexdigest()[:16]


def check_dedup(content: str) -> Optional[Any]:
    """
    Check if content has already been processed this session.
    
    Args:
        content: Content to check
        
    Returns:
        Cached result if found, None otherwise
    """
    if not config.ENABLE_DEDUPLICATION:
        return None
    
    content_hash = get_content_hash(content)
    return _dedup_cache.get(content_hash)


def set_dedup(content: str, result: Any):
    """
    Store result for content deduplication.
    
    Args:
        content: Original content
        result: Result to cache
    """
    if not config.ENABLE_DEDUPLICATION:
        return
    
    content_hash = get_content_hash(content)
    _dedup_cache[content_hash] = result


def clear_dedup_cache():
    """Clear the in-memory deduplication cache."""
    global _dedup_cache
    _dedup_cache = {}


# Cost tracking
_session_costs: Dict[str, float] = {}


def track_cost(model: str, input_tokens: int, output_tokens: int):
    """
    Track API costs for the session.
    
    Args:
        model: Model name
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
    """
    if not config.ENABLE_COST_TRACKING:
        return
    
    # Get cost per 1M tokens for this model
    cost_per_1m = config.MODEL_COSTS_PER_1M_TOKENS.get(model, 1.0)
    
    # Calculate cost (input and output typically same price for simplicity)
    total_tokens = input_tokens + output_tokens
    cost = (total_tokens / 1_000_000) * cost_per_1m
    
    if model not in _session_costs:
        _session_costs[model] = 0.0
    _session_costs[model] += cost


def get_session_costs() -> Dict[str, Any]:
    """Get cost tracking data for the session."""
    total = sum(_session_costs.values())
    return {
        'by_model': _session_costs.copy(),
        'total_usd': total
    }


def print_session_costs():
    """Print session costs in a human-readable format."""
    if not config.ENABLE_COST_TRACKING:
        print("[COST TRACKING] Disabled")
        return
    
    costs = get_session_costs()
    
    print("\n" + "=" * 60)
    print("  SESSION API COSTS (Estimated)")
    print("=" * 60)
    
    for model, cost in costs['by_model'].items():
        print(f"  {model}: ${cost:.4f}")
    
    print("  " + "-" * 56)
    print(f"  TOTAL: ${costs['total_usd']:.4f}")
    print("=" * 60 + "\n")


def reset_session_costs():
    """Reset session cost tracking."""
    global _session_costs
    _session_costs = {}
