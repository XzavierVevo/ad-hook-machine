"""
Agent Sessions - Conversational session management for the thinking agent.

This module provides:
- Session state management
- Conversation history tracking
- Context preservation across turns
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
import uuid

from .. import config


# Session storage
SESSIONS_DIR = config.OUTPUT_DIR / "sessions"


class AgentSession:
    """
    Manages a conversational session with the thinking agent.
    
    Sessions preserve:
    - Conversation history
    - Generated hooks
    - User preferences
    - Context from previous turns
    """
    
    def __init__(self, session_id: Optional[str] = None):
        """
        Initialize or restore a session.
        
        Args:
            session_id: Existing session ID to restore, or None to create new
        """
        self.session_id = session_id or str(uuid.uuid4())[:8]
        self.session_file = SESSIONS_DIR / f"{self.session_id}.json"
        
        # Session state
        self.messages: List[Dict[str, str]] = []
        self.hooks: Dict[str, List[Dict]] = {'unique': [], 'proven': []}
        self.context: Dict[str, Any] = {}
        self.created_at: str = datetime.now().isoformat()
        self.updated_at: str = self.created_at
        
        # Try to restore existing session
        if self.session_file.exists():
            self._load()
        else:
            self._save()
    
    def _load(self):
        """Load session from file."""
        try:
            with open(self.session_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.messages = data.get('messages', [])
            self.hooks = data.get('hooks', {'unique': [], 'proven': []})
            self.context = data.get('context', {})
            self.created_at = data.get('created_at', self.created_at)
            self.updated_at = data.get('updated_at', self.updated_at)
            
        except (json.JSONDecodeError, IOError):
            pass
    
    def _save(self):
        """Save session to file."""
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        
        data = {
            'session_id': self.session_id,
            'messages': self.messages,
            'hooks': self.hooks,
            'context': self.context,
            'created_at': self.created_at,
            'updated_at': datetime.now().isoformat()
        }
        
        with open(self.session_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    
    def add_message(self, role: str, content: str):
        """
        Add a message to the conversation history.
        
        Args:
            role: 'user' or 'assistant'
            content: Message content
        """
        self.messages.append({
            'role': role,
            'content': content,
            'timestamp': datetime.now().isoformat()
        })
        self._save()
    
    def set_hooks(self, unique: Optional[List[Dict]] = None, proven: Optional[List[Dict]] = None):
        """
        Store generated hooks in the session.
        
        Args:
            unique: List of unique hooks
            proven: List of proven fusion hooks
        """
        if unique is not None:
            self.hooks['unique'] = unique
        if proven is not None:
            self.hooks['proven'] = proven
        self._save()
    
    def get_hooks(self) -> Dict[str, List[Dict]]:
        """Get all hooks from the session."""
        return self.hooks
    
    def set_context(self, key: str, value: Any):
        """Set a context value."""
        self.context[key] = value
        self._save()
    
    def get_context(self, key: str, default: Any = None) -> Any:
        """Get a context value."""
        return self.context.get(key, default)
    
    def update_context(self, updates: Dict[str, Any]):
        """Update multiple context values."""
        self.context.update(updates)
        self._save()
    
    def get_conversation_summary(self) -> str:
        """Get a summary of the conversation for context."""
        if not self.messages:
            return "No conversation history."
        
        # Get last 5 exchanges
        recent = self.messages[-10:]
        
        summary_parts = []
        for msg in recent:
            role = msg['role'].capitalize()
            content = msg['content'][:200] + '...' if len(msg['content']) > 200 else msg['content']
            summary_parts.append(f"{role}: {content}")
        
        return "\n".join(summary_parts)
    
    def clear(self):
        """Clear the session state."""
        self.messages = []
        self.hooks = {'unique': [], 'proven': []}
        self.context = {}
        self._save()
    
    def to_dict(self) -> Dict[str, Any]:
        """Export session as dictionary."""
        return {
            'session_id': self.session_id,
            'messages': self.messages,
            'hooks': self.hooks,
            'context': self.context,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


def list_sessions() -> List[Dict[str, Any]]:
    """
    List all available sessions.
    
    Returns:
        List of session summaries
    """
    if not SESSIONS_DIR.exists():
        return []
    
    sessions = []
    for session_file in SESSIONS_DIR.glob("*.json"):
        try:
            with open(session_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            sessions.append({
                'session_id': data.get('session_id', session_file.stem),
                'created_at': data.get('created_at'),
                'updated_at': data.get('updated_at'),
                'message_count': len(data.get('messages', [])),
                'hook_count': len(data.get('hooks', {}).get('unique', [])) + len(data.get('hooks', {}).get('proven', []))
            })
        except (json.JSONDecodeError, IOError):
            continue
    
    # Sort by updated_at (most recent first)
    sessions.sort(key=lambda x: x.get('updated_at', ''), reverse=True)
    
    return sessions


def delete_session(session_id: str) -> bool:
    """
    Delete a session.
    
    Args:
        session_id: Session ID to delete
        
    Returns:
        True if deleted, False if not found
    """
    session_file = SESSIONS_DIR / f"{session_id}.json"
    
    if session_file.exists():
        session_file.unlink()
        return True
    
    return False


def get_or_create_session(session_id: Optional[str] = None) -> AgentSession:
    """
    Get an existing session or create a new one.
    
    Args:
        session_id: Optional session ID to restore
        
    Returns:
        AgentSession instance
    """
    return AgentSession(session_id)
