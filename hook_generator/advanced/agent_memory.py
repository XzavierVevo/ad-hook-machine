"""
Agent Memory - Persistent memory system for the thinking agent.

This module provides:
- Local JSON-based memory (default)
- Vertex AI Memory Bank integration (optional, for cloud deployment)

Memory stores insights about:
- What hooks worked in past campaigns
- Which templates performed best
- Niche-specific learnings
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

from .agent_tools import register_tool
from .. import config
from .. import api_keys


# Local memory storage path
MEMORY_DIR = config.OUTPUT_DIR / "memory"
MEMORY_FILE = MEMORY_DIR / "agent_memory.json"


def _load_local_memory() -> Dict[str, Any]:
    """Load memory from local JSON file."""
    if not MEMORY_FILE.exists():
        return {'entries': [], 'niche_insights': {}}
    
    try:
        with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {'entries': [], 'niche_insights': {}}


def _save_local_memory(memory: Dict[str, Any]):
    """Save memory to local JSON file."""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    
    with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(memory, f, indent=2, ensure_ascii=False, default=str)


@register_tool(
    name="recall_memory",
    description="Recall past insights and learnings about a niche or topic from the agent's memory.",
    parameters={
        "topic": {"type": "string", "description": "The niche or topic to recall memories about"}
    }
)
def recall_memory(topic: str) -> Dict[str, Any]:
    """
    Recall memories related to a topic.
    
    Args:
        topic: Topic to recall memories for
        
    Returns:
        Dictionary with relevant memories and insights
    """
    print(f"\n[TOOL: recall_memory] Recalling insights for '{topic}'...")
    
    # Try Vertex AI Memory Bank first if configured
    if api_keys.GOOGLE_CLOUD_PROJECT:
        try:
            vertex_memory = _recall_vertex_memory(topic)
            if vertex_memory:
                return vertex_memory
        except Exception as e:
            print(f"[MEMORY] Vertex AI not available, using local: {e}")
    
    # Fall back to local memory
    memory = _load_local_memory()
    
    topic_lower = topic.lower()
    
    # Get niche-specific insights
    niche_insights = memory.get('niche_insights', {}).get(topic_lower, {})
    
    # Find related entries
    related_entries = []
    for entry in memory.get('entries', []):
        entry_niche = entry.get('niche', '').lower()
        if topic_lower in entry_niche or entry_niche in topic_lower:
            related_entries.append(entry)
    
    # Sort by timestamp (most recent first)
    related_entries.sort(
        key=lambda x: x.get('timestamp', ''),
        reverse=True
    )
    
    return {
        'success': True,
        'topic': topic,
        'niche_insights': niche_insights,
        'related_campaigns': related_entries[:10],
        'total_entries': len(related_entries),
        'what_worked': niche_insights.get('what_worked', []),
        'what_to_avoid': niche_insights.get('what_to_avoid', []),
        'best_ragebait_level': niche_insights.get('best_ragebait_level'),
        'best_templates': niche_insights.get('best_templates', [])
    }


@register_tool(
    name="save_memory",
    description="Save insights and learnings from the current campaign to memory for future use.",
    parameters={
        "topic": {"type": "string", "description": "The niche or topic"},
        "insights": {"type": "object", "description": "Insights to save (what_worked, what_to_avoid, best_ragebait_level, etc.)"}
    }
)
def save_memory(topic: str, insights: Dict[str, Any]) -> bool:
    """
    Save campaign insights to memory.
    
    Args:
        topic: Topic/niche for the insights
        insights: Dictionary with insights to save
        
    Returns:
        True if saved successfully
    """
    print(f"\n[TOOL: save_memory] Saving insights for '{topic}'...")
    
    # Try Vertex AI Memory Bank first if configured
    if api_keys.GOOGLE_CLOUD_PROJECT:
        try:
            success = _save_vertex_memory(topic, insights)
            if success:
                return True
        except Exception as e:
            print(f"[MEMORY] Vertex AI save failed, using local: {e}")
    
    # Fall back to local memory
    memory = _load_local_memory()
    
    topic_lower = topic.lower()
    
    # Add entry
    entry = {
        'niche': topic,
        'timestamp': datetime.now().isoformat(),
        **insights
    }
    memory['entries'].append(entry)
    
    # Update niche insights
    if topic_lower not in memory['niche_insights']:
        memory['niche_insights'][topic_lower] = {
            'what_worked': [],
            'what_to_avoid': [],
            'best_ragebait_level': None,
            'best_templates': []
        }
    
    niche = memory['niche_insights'][topic_lower]
    
    # Merge insights
    if insights.get('what_worked'):
        niche['what_worked'].extend(insights['what_worked'])
        niche['what_worked'] = list(set(niche['what_worked']))[:20]
    
    if insights.get('what_to_avoid'):
        niche['what_to_avoid'].extend(insights['what_to_avoid'])
        niche['what_to_avoid'] = list(set(niche['what_to_avoid']))[:20]
    
    if insights.get('best_ragebait_level') is not None:
        niche['best_ragebait_level'] = insights['best_ragebait_level']
    
    if insights.get('best_templates'):
        niche['best_templates'] = insights['best_templates']
    
    # Save
    _save_local_memory(memory)
    
    print(f"[MEMORY] Saved insights for '{topic}'")
    return True


def _recall_vertex_memory(topic: str) -> Optional[Dict[str, Any]]:
    """
    Recall memory from Vertex AI Memory Bank.
    
    This is a placeholder for Vertex AI Agent Engine integration.
    Requires google-cloud-aiplatform to be installed and configured.
    """
    try:
        from google.cloud import aiplatform
        
        # Initialize Vertex AI
        aiplatform.init(project=api_keys.GOOGLE_CLOUD_PROJECT)
        
        # This would use the Memory Bank API when available
        # For now, return None to fall back to local
        return None
        
    except ImportError:
        return None
    except Exception:
        return None


def _save_vertex_memory(topic: str, insights: Dict[str, Any]) -> bool:
    """
    Save memory to Vertex AI Memory Bank.
    
    This is a placeholder for Vertex AI Agent Engine integration.
    """
    try:
        from google.cloud import aiplatform
        
        # Initialize Vertex AI
        aiplatform.init(project=api_keys.GOOGLE_CLOUD_PROJECT)
        
        # This would use the Memory Bank API when available
        # For now, return False to fall back to local
        return False
        
    except ImportError:
        return False
    except Exception:
        return False


def get_memory_stats() -> Dict[str, Any]:
    """Get statistics about stored memory."""
    memory = _load_local_memory()
    
    return {
        'total_entries': len(memory.get('entries', [])),
        'niches_tracked': len(memory.get('niche_insights', {})),
        'niche_list': list(memory.get('niche_insights', {}).keys()),
        'storage_location': str(MEMORY_FILE)
    }


def clear_memory(topic: Optional[str] = None) -> int:
    """
    Clear memory entries.
    
    Args:
        topic: If provided, only clear entries for this topic.
               If None, clear all memory.
               
    Returns:
        Number of entries cleared
    """
    memory = _load_local_memory()
    
    if topic:
        topic_lower = topic.lower()
        original_count = len(memory.get('entries', []))
        
        # Remove matching entries
        memory['entries'] = [
            e for e in memory.get('entries', [])
            if topic_lower not in e.get('niche', '').lower()
        ]
        
        # Remove niche insights
        if topic_lower in memory.get('niche_insights', {}):
            del memory['niche_insights'][topic_lower]
        
        cleared = original_count - len(memory['entries'])
    else:
        cleared = len(memory.get('entries', []))
        memory = {'entries': [], 'niche_insights': {}}
    
    _save_local_memory(memory)
    
    return cleared
