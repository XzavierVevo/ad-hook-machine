"""
Advanced Mode - Thinking Agent System

This module provides an advanced, autonomous "thinking agent" that uses:
- LangGraph for decision loops and adaptive strategies
- Perplexity for real-time web research
- AI Vision for competitor ad image analysis
- Crawl4AI for product page scraping
- Vertex AI Memory Bank for persistent learning

Usage:
    python -m hook_generator.main --advanced --name "campaign" --count 20
    python -m hook_generator.main --advanced --chat
"""

from .advanced_workflow import run_advanced_workflow
from .thinking_agent import ThinkingAgent
from .conversational_mode import run_conversational_mode

__all__ = [
    'run_advanced_workflow',
    'ThinkingAgent',
    'run_conversational_mode'
]
