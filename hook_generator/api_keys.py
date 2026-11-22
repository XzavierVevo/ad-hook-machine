"""
API key management for the Ad Hook Generation Bot.
"""

import os
from pathlib import Path
from typing import Optional, Any, Dict

# Global API key variables
OPENAI_API_KEY: Optional[str] = None
ANTHROPIC_API_KEY: Optional[str] = None
META_ACCESS_TOKEN: Optional[str] = None
META_AD_ACCOUNT_ID: Optional[str] = None
PERPLEXITY_API_KEY: Optional[str] = None
GOOGLE_CLOUD_PROJECT: Optional[str] = None
GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None
GOOGLE_GEMINI_API_KEY: Optional[str] = None

# API clients (initialized lazily)
OPENAI_CLIENT: Optional[Any] = None
ANTHROPIC_CLIENT: Optional[Any] = None
ASYNC_OPENAI_CLIENT: Optional[Any] = None
ASYNC_ANTHROPIC_CLIENT: Optional[Any] = None
PERPLEXITY_CLIENT: Optional[Any] = None


def load_api_keys(api_keys_file: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load API keys from file or environment variables.
    
    Args:
        api_keys_file: Path to api_keys.txt file
        
    Returns:
        Dictionary of loaded API keys
    """
    global OPENAI_API_KEY, ANTHROPIC_API_KEY, META_ACCESS_TOKEN, META_AD_ACCOUNT_ID
    global PERPLEXITY_API_KEY, GOOGLE_CLOUD_PROJECT, GOOGLE_APPLICATION_CREDENTIALS
    global GOOGLE_GEMINI_API_KEY
    
    keys = {}
    
    # Try loading from file first
    if api_keys_file is None:
        from . import config
        api_keys_file = config.API_KEYS_FILE
    
    if api_keys_file.exists():
        with open(api_keys_file, 'r') as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    keys[key.strip()] = value.strip()
    
    # Override with environment variables if set
    OPENAI_API_KEY = keys.get('OPENAI_API_KEY') or os.environ.get('OPENAI_API_KEY')
    ANTHROPIC_API_KEY = keys.get('ANTHROPIC_API_KEY') or os.environ.get('ANTHROPIC_API_KEY')
    META_ACCESS_TOKEN = keys.get('META_ACCESS_TOKEN') or os.environ.get('META_ACCESS_TOKEN')
    META_AD_ACCOUNT_ID = keys.get('META_AD_ACCOUNT_ID') or os.environ.get('META_AD_ACCOUNT_ID')
    PERPLEXITY_API_KEY = keys.get('PERPLEXITY_API_KEY') or os.environ.get('PERPLEXITY_API_KEY')
    GOOGLE_CLOUD_PROJECT = keys.get('GOOGLE_CLOUD_PROJECT') or os.environ.get('GOOGLE_CLOUD_PROJECT')
    GOOGLE_APPLICATION_CREDENTIALS = keys.get('GOOGLE_APPLICATION_CREDENTIALS') or os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
    GOOGLE_GEMINI_API_KEY = keys.get('GOOGLE_GEMINI_API_KEY') or os.environ.get('GOOGLE_GEMINI_API_KEY')
    
    # Set Google credentials environment variable if specified in file
    if GOOGLE_APPLICATION_CREDENTIALS and not os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'):
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = GOOGLE_APPLICATION_CREDENTIALS
    
    return {
        'OPENAI_API_KEY': OPENAI_API_KEY,
        'ANTHROPIC_API_KEY': ANTHROPIC_API_KEY,
        'META_ACCESS_TOKEN': META_ACCESS_TOKEN,
        'META_AD_ACCOUNT_ID': META_AD_ACCOUNT_ID,
        'PERPLEXITY_API_KEY': PERPLEXITY_API_KEY,
        'GOOGLE_CLOUD_PROJECT': GOOGLE_CLOUD_PROJECT,
        'GOOGLE_APPLICATION_CREDENTIALS': GOOGLE_APPLICATION_CREDENTIALS,
        'GOOGLE_GEMINI_API_KEY': GOOGLE_GEMINI_API_KEY
    }


def initialize_clients():
    """Initialize API clients."""
    global OPENAI_CLIENT, ANTHROPIC_CLIENT, ASYNC_OPENAI_CLIENT, ASYNC_ANTHROPIC_CLIENT
    global PERPLEXITY_CLIENT
    
    # Load keys if not already loaded
    if OPENAI_API_KEY is None:
        load_api_keys()
    
    # Initialize OpenAI client
    if OPENAI_API_KEY:
        try:
            from openai import OpenAI, AsyncOpenAI
            OPENAI_CLIENT = OpenAI(api_key=OPENAI_API_KEY)
            ASYNC_OPENAI_CLIENT = AsyncOpenAI(api_key=OPENAI_API_KEY)
            print("[OK] OpenAI clients initialized")
        except Exception as e:
            print(f"[WARNING] Failed to initialize OpenAI client: {e}")
    
    # Initialize Anthropic client
    if ANTHROPIC_API_KEY:
        try:
            import anthropic
            ANTHROPIC_CLIENT = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            ASYNC_ANTHROPIC_CLIENT = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
            print("[OK] Anthropic clients initialized")
        except Exception as e:
            print(f"[WARNING] Failed to initialize Anthropic client: {e}")
    
    # Initialize Perplexity client (uses OpenAI-compatible API)
    if PERPLEXITY_API_KEY:
        try:
            from openai import OpenAI
            PERPLEXITY_CLIENT = OpenAI(
                api_key=PERPLEXITY_API_KEY,
                base_url="https://api.perplexity.ai"
            )
            print("[OK] Perplexity client initialized")
        except Exception as e:
            print(f"[WARNING] Failed to initialize Perplexity client: {e}")


def verify_keys() -> Dict[str, Any]:
    """
    Verify which API keys are configured.
    
    Returns:
        Dictionary with key names and their status (True/False)
    """
    if OPENAI_API_KEY is None:
        load_api_keys()
    
    return {
        'OPENAI_API_KEY': bool(OPENAI_API_KEY),
        'ANTHROPIC_API_KEY': bool(ANTHROPIC_API_KEY),
        'META_ACCESS_TOKEN': bool(META_ACCESS_TOKEN),
        'META_AD_ACCOUNT_ID': bool(META_AD_ACCOUNT_ID),
        'PERPLEXITY_API_KEY': bool(PERPLEXITY_API_KEY),
        'GOOGLE_CLOUD_PROJECT': bool(GOOGLE_CLOUD_PROJECT),
        'GOOGLE_GEMINI_API_KEY': bool(GOOGLE_GEMINI_API_KEY)
    }


def get_model_for_task(task: str) -> str:
    """
    Get the appropriate model for a given task based on the tiered model strategy.
    
    This implements cost optimization by using cheaper models for simpler tasks
    while reserving expensive models for complex tasks.
    
    Args:
        task: Task name (e.g., 'headline_generation', 'hook_shortening', 'ad_analysis')
        
    Returns:
        Model name string to use for the task
        
    Available tasks and their default models:
        - headline_generation: claude-opus-4-20250514 (complex creative task)
        - proven_hooks: claude-opus-4-20250514 (complex creative task)
        - hook_shortening: claude-3-5-haiku-20241022 (simple task)
        - ad_analysis: claude-3-5-haiku-20241022 (simple extraction)
        - keyword_generation: claude-3-5-haiku-20241022 (simple task)
        - vision_analysis: gemini-1.5-flash (multimodal)
        - trend_research: sonar (Perplexity)
    """
    from . import config
    
    # Get model from config, with sensible fallback
    model = config.MODEL_TIERS.get(task)
    
    if model is None:
        # Fallback based on task complexity inference
        simple_tasks = ['shortening', 'analysis', 'extraction', 'keyword']
        if any(simple in task.lower() for simple in simple_tasks):
            model = 'claude-3-5-haiku-20241022'
        else:
            model = 'claude-opus-4-20250514'
    
    return model


def get_anthropic_client_for_model(model: str):
    """
    Get the appropriate Anthropic client for a model.
    
    Args:
        model: Model name
        
    Returns:
        Anthropic client instance
    """
    if ANTHROPIC_CLIENT is None:
        initialize_clients()
    return ANTHROPIC_CLIENT


def get_batch_size(task: str) -> int:
    """
    Get the batch size for a given task.
    
    Args:
        task: Task name
        
    Returns:
        Batch size for the task
    """
    from . import config
    return config.BATCH_SIZES.get(task, 5)

