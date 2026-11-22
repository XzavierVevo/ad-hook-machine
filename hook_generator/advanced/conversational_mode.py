"""
Conversational Mode - Interactive chat interface for hook refinement.

This module provides a chat-based interface where users can:
- Generate hooks through conversation
- Refine specific hooks without re-running everything
- Ask questions about competitors and trends
- Export hooks when ready
"""

import json
import asyncio
from typing import Dict, Any, List, Optional

from .. import api_keys
from .. import config
from ..cache_manager import track_cost, print_session_costs
from .agent_sessions import AgentSession, get_or_create_session
from .thinking_agent import ThinkingAgent


def run_conversational_mode(
    session_id: Optional[str] = None,
    use_memory: bool = False
):
    """
    Run the conversational chat interface.
    
    Args:
        session_id: Optional session ID to restore
        use_memory: Whether to use Vertex AI Memory Bank
    """
    print("\n" + "=" * 60)
    print("  AD HOOK THINKING AGENT - Conversational Mode")
    print("=" * 60)
    
    # Get or create session
    session = get_or_create_session(session_id)
    print(f"\n[SESSION] ID: {session.session_id}")
    
    # Display welcome message
    welcome = config.AI_PROMPTS['conversational']['welcome']
    print(f"\n{welcome}")
    session.add_message('assistant', welcome)
    
    # Initialize agent
    agent = ThinkingAgent(use_memory=use_memory)
    
    # Main conversation loop
    while True:
        try:
            # Get user input
            user_input = input("\n> You: ").strip()
            
            if not user_input:
                continue
            
            # Handle special commands
            if user_input.lower() in ['quit', 'exit', 'bye']:
                print("\n[AGENT] Goodbye! Your session has been saved.")
                print_session_costs()
                break
            
            if user_input.lower() == 'help':
                _print_help()
                continue
            
            if user_input.lower() == 'export':
                _export_hooks(session)
                continue
            
            if user_input.lower() == 'preview':
                _preview_hooks(session)
                continue
            
            if user_input.lower() == 'clear':
                session.clear()
                print("[AGENT] Session cleared. Let's start fresh!")
                continue
            
            # Add user message to session
            session.add_message('user', user_input)
            
            # Process the input
            response = _process_user_input(user_input, session, agent)
            
            # Display and save response
            print(f"\n[AGENT]: {response}")
            session.add_message('assistant', response)
            
        except KeyboardInterrupt:
            print("\n\n[AGENT] Interrupted. Your session has been saved.")
            break
        except Exception as e:
            print(f"\n[ERROR] {e}")
            continue


def _process_user_input(
    user_input: str,
    session: AgentSession,
    agent: ThinkingAgent
) -> str:
    """
    Process user input and generate a response.
    
    Args:
        user_input: User's message
        session: Current session
        agent: Thinking agent instance
        
    Returns:
        Agent's response
    """
    # Parse user intent
    intent = _parse_intent(user_input, session)
    
    if intent['action'] == 'generate':
        return _handle_generate(intent, session, agent)
    
    elif intent['action'] == 'refine':
        return _handle_refine(intent, session)
    
    elif intent['action'] == 'question':
        return _handle_question(user_input, session)
    
    elif intent['action'] == 'export':
        return _handle_export(session)
    
    else:
        return _handle_general(user_input, session)


def _parse_intent(user_input: str, session: AgentSession) -> Dict[str, Any]:
    """
    Parse user intent from their message.
    
    Args:
        user_input: User's message
        session: Current session for context
        
    Returns:
        Dictionary with action and parameters
    """
    input_lower = user_input.lower()
    
    # Check for generation intent
    generation_keywords = ['generate', 'create', 'make', 'build', 'hooks for', 'ads for']
    if any(kw in input_lower for kw in generation_keywords):
        return {'action': 'generate', 'raw_input': user_input}
    
    # Check for refinement intent
    refine_keywords = ['change', 'modify', 'edit', 'update', 'more ragebait', 'less ragebait', 
                       'regenerate', 'redo', 'hook number', 'hooks number']
    if any(kw in input_lower for kw in refine_keywords):
        return {'action': 'refine', 'raw_input': user_input}
    
    # Check for question intent
    question_keywords = ['what', 'how', 'why', 'when', 'where', 'who', '?']
    if any(kw in input_lower for kw in question_keywords):
        return {'action': 'question', 'raw_input': user_input}
    
    # Check for export intent
    export_keywords = ['export', 'save', 'download', 'images']
    if any(kw in input_lower for kw in export_keywords):
        return {'action': 'export', 'raw_input': user_input}
    
    # Default to general
    return {'action': 'general', 'raw_input': user_input}


def _handle_generate(
    intent: Dict[str, Any],
    session: AgentSession,
    agent: ThinkingAgent
) -> str:
    """Handle hook generation request."""
    
    # Extract parameters from input
    user_input = intent['raw_input']
    
    # Try to extract topic with better context preservation
    topic = session.get_context('topic', '')
    service_context = session.get_context('service_context', '')
    
    # Look for website/service mentions (e.g., paintprofinder.com, example.net)
    import re
    website_pattern = r'\b([a-zA-Z0-9-]+\.(?:com|net|org|io|co|us|app))\b'
    website_match = re.search(website_pattern, user_input, re.IGNORECASE)
    
    if website_match:
        website = website_match.group(1)
        # Extract the full context about what the service does
        # Look for patterns like "X is for Y" or "X helps Y" or "X that does Y"
        # Also handle "with the offer that X is for Y"
        service_desc_patterns = [
            # Pattern: "offer that X is for Y" (captures everything after "for" to end of input)
            rf'offer\s+that\s+{re.escape(website)}\s+is\s+for\s+(.+)$',
            # Pattern: "X is for Y" (captures everything after "for" to end of input)
            rf'{re.escape(website)}\s+is\s+for\s+(.+)$',
            # Pattern: "X helps Y"
            rf'{re.escape(website)}\s+helps?\s+(.+)$',
            # Pattern: "X that Y"
            rf'{re.escape(website)}\s+that\s+(.+)$',
        ]
        
        for pattern in service_desc_patterns:
            desc_match = re.search(pattern, user_input, re.IGNORECASE)
            if desc_match:
                desc_text = desc_match.group(1).strip()
                # Clean up the description - remove trailing punctuation but keep the content
                desc_text = desc_text.rstrip('.,!?')
                desc_text = re.sub(r'\s+', ' ', desc_text)  # Normalize whitespace
                # If description is very long, it might include the offer - that's fine, keep it all
                service_context = f"{website} is for {desc_text}"
                # Use the service description as the topic
                topic = service_context
                break
        
        if not service_context:
            # If no description found, use the website as topic
            topic = website
    
    # If no website found, try to extract topic from "for" or other patterns
    if not topic:
        if 'for ' in user_input.lower():
            # Extract what comes after "for" but be smarter about it
            parts = user_input.lower().split('for ')
            if len(parts) > 1:
                potential_topic = parts[-1].strip()
                # Remove common trailing phrases
                potential_topic = re.sub(r'\s+(with|using|via|through|at)\s+.*$', '', potential_topic)
                potential_topic = potential_topic.rstrip('.,!?')
                
                # If it's a reasonable length and not just a single word like "price"
                if len(potential_topic.split()) > 1 or len(potential_topic) > 10:
                    topic = potential_topic
                else:
                    # Single word might be an offer/benefit, not the full topic
                    # Try to get more context from the sentence
                    # Look for the full sentence structure
                    sentences = re.split(r'[.!?]\s+', user_input)
                    for sentence in sentences:
                        if 'for ' in sentence.lower() and len(sentence.split()) > 5:
                            topic = sentence.strip()
                            break
    
    # If still no topic, check session context
    if not topic:
        topic = session.get_context('topic', '')
    
    # If we have service context, preserve it
    if service_context:
        session.update_context({'service_context': service_context})
    
    if not topic:
        return "What niche or topic would you like to generate hooks for? (e.g., 'house painting', 'weight loss', or 'paintprofinder.com is for homeowners to find painters')"
    
    # Extract count - look for "X hooks" or "X ads"
    count = 20
    import re
    # Try to match "25 hooks" or "25 ads" or just "25" followed by hooks/ads
    count_match = re.search(r'(\d+)\s*(?:hooks?|ads?)', user_input.lower())
    if count_match:
        count = int(count_match.group(1))
    else:
        # Also try to find standalone numbers that might indicate count
        numbers = re.findall(r'\b(\d+)\b', user_input)
        if numbers:
            # Take the first reasonable number (between 1 and 500)
            for num_str in numbers:
                num = int(num_str)
                if 1 <= num <= 500:
                    count = num
                    break
    
    # Extract ragebait level
    ragebait_level = session.get_context('ragebait_level', 3)
    if 'ragebait' in user_input.lower():
        # Try to find explicit number
        rb_match = re.search(r'ragebait\s*(?:level\s*)?(\d+)', user_input.lower())
        if rb_match:
            ragebait_level = int(rb_match.group(1))
        # Check for descriptive terms
        elif 'very high' in user_input.lower() or 'maximum' in user_input.lower() or 'max' in user_input.lower():
            ragebait_level = 10
        elif 'high' in user_input.lower():
            ragebait_level = 7
        elif 'medium' in user_input.lower() or 'moderate' in user_input.lower():
            ragebait_level = 5
        elif 'low' in user_input.lower() or 'minimal' in user_input.lower():
            ragebait_level = 2
    
    # Extract template IDs
    template_ids = None
    template_match = re.search(r'template\s*(\d+)', user_input.lower())
    if template_match:
        template_ids = [int(template_match.group(1))]
    
    # Save context
    session.update_context({
        'topic': topic,
        'count': count,
        'ragebait_level': ragebait_level,
        'template_ids': template_ids
    })
    
    # Build full topic description with service context if available
    full_topic = topic
    if service_context and service_context != topic:
        # If we have service context, use it to enrich the topic
        full_topic = service_context
    
    print(f"\n[AGENT] Generating {count} hooks for '{full_topic}' (ragebait: {ragebait_level})...")
    print("[AGENT] This may take a minute...")
    
    # Run the agent
    try:
        # Build a comprehensive task description
        task_description = f"Generate {count} high-converting ad hooks for {full_topic}"
        if service_context and 'offer' in user_input.lower():
            # Extract offer/benefit if mentioned
            offer_match = re.search(r'(?:offer|benefit|that|is)\s+(?:that|is|for)\s+([^.]*(?:\.[^.]*)*)', user_input, re.IGNORECASE)
            if offer_match:
                offer_text = offer_match.group(1).strip()
                task_description += f" with the offer/benefit: {offer_text}"
        
        result = agent.run(
            task=task_description,
            topic=full_topic,
            count=count,
            ragebait_level=ragebait_level,
            offer_type=session.get_context('offer_type', 'service'),
            templates=template_ids
        )
        
        # Store hooks in session
        hooks = result.get('hooks', {})
        session.set_hooks(
            unique=hooks.get('unique', []),
            proven=hooks.get('proven', [])
        )
        
        # Format response
        unique_count = len(hooks.get('unique', []))
        proven_count = len(hooks.get('proven', []))
        
        return f"""Generated {unique_count + proven_count} hooks:
- {unique_count} unique Andromeda-style hooks
- {proven_count} proven fusion hooks

Type 'preview' to see the hooks, 'export' to create images, or tell me what you'd like to change."""
        
    except Exception as e:
        return f"Sorry, I encountered an error while generating hooks: {e}"


def _handle_refine(intent: Dict[str, Any], session: AgentSession) -> str:
    """Handle hook refinement request."""
    
    hooks = session.get_hooks()
    if not hooks.get('unique') and not hooks.get('proven'):
        return "You don't have any hooks to refine yet. Would you like to generate some first?"
    
    user_input = intent['raw_input']
    
    # Parse refinement request using AI
    if api_keys.ANTHROPIC_CLIENT:
        try:
            all_hooks = hooks.get('unique', []) + hooks.get('proven', [])
            hooks_text = "\n".join([
                f"{i+1}. {h.get('headline', 'N/A')}"
                for i, h in enumerate(all_hooks[:20])
            ])
            
            parse_prompt = config.AI_PROMPTS['conversational']['parse_refinement'].format(
                user_input=user_input
            )
            
            response = api_keys.ANTHROPIC_CLIENT.messages.create(
                model=api_keys.get_model_for_task('ad_analysis'),
                max_tokens=300,
                messages=[{"role": "user", "content": parse_prompt}]
            )
            
            # For now, return a helpful message
            return f"""I understand you want to refine your hooks. You currently have:
- {len(hooks.get('unique', []))} unique hooks
- {len(hooks.get('proven', []))} proven hooks

To refine, you can say things like:
- "Make hook 3 more aggressive"
- "Regenerate the last 5 hooks with ragebait level 8"
- "Change all hooks to include '$99' offer"

What would you like to change?"""
            
        except Exception as e:
            return f"I had trouble understanding your refinement request: {e}"
    
    return "I understand you want to refine hooks. Could you be more specific about which hooks and what changes?"


def _handle_question(user_input: str, session: AgentSession) -> str:
    """Handle user questions."""
    
    # Use AI to answer if available
    if api_keys.ANTHROPIC_CLIENT:
        try:
            context = session.get_conversation_summary()
            hooks = session.get_hooks()
            
            prompt = f"""The user is asking a question about ad hook generation.

Context from conversation:
{context}

Current hooks generated: {len(hooks.get('unique', [])) + len(hooks.get('proven', []))}

User question: {user_input}

Provide a helpful, concise answer. If the question is about their hooks or campaign, reference the context. Keep the response under 200 words."""
            
            response = api_keys.ANTHROPIC_CLIENT.messages.create(
                model=api_keys.get_model_for_task('ad_analysis'),
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}]
            )
            
            # Safely extract text from response
            if response.content and len(response.content) > 0:
                content_block = response.content[0]
                if hasattr(content_block, 'text'):
                    return content_block.text
                else:
                    return str(content_block)
            return ""
            
        except Exception as e:
            pass
    
    return "I'm not sure how to answer that. Could you rephrase your question?"


def _handle_export(session: AgentSession) -> str:
    """Handle export request."""
    
    hooks = session.get_hooks()
    total = len(hooks.get('unique', [])) + len(hooks.get('proven', []))
    
    if total == 0:
        return "You don't have any hooks to export yet. Generate some first!"
    
    return f"""Ready to export {total} hooks to images.

To export, run from command line:
python -m hook_generator.main --advanced --export-session {session.session_id}

Or type 'generate images' to create them now."""


def _handle_general(user_input: str, session: AgentSession) -> str:
    """Handle general conversation."""
    
    # Simple responses for common inputs
    greetings = ['hi', 'hello', 'hey', 'yo']
    if user_input.lower() in greetings:
        return "Hello! I'm ready to help you create high-converting ad hooks. What niche would you like to target?"
    
    thanks = ['thanks', 'thank you', 'thx']
    if any(t in user_input.lower() for t in thanks):
        return "You're welcome! Let me know if you need anything else."
    
    # Check if user is providing context about their service/website
    import re
    website_pattern = r'\b([a-zA-Z0-9-]+\.(?:com|net|org|io|co|us|app))\b'
    website_match = re.search(website_pattern, user_input, re.IGNORECASE)
    
    if website_match:
        website = website_match.group(1)
        # Try to extract service description
        service_desc_patterns = [
            rf'{re.escape(website)}\s+(?:is|its|it\'s)\s+(?:a\s+)?(?:site|website|service|platform|tool|app)\s+that\s+([^.]*(?:\.[^.]*)*)',
            rf'{re.escape(website)}\s+(?:is|its|it\'s)\s+for\s+([^.]*(?:\.[^.]*)*)',
            rf'{re.escape(website)}\s+helps?\s+([^.]*(?:\.[^.]*)*)',
        ]
        
        service_context = None
        for pattern in service_desc_patterns:
            desc_match = re.search(pattern, user_input, re.IGNORECASE)
            if desc_match:
                service_context = f"{website} - {desc_match.group(1).strip()}"
                break
        
        if service_context:
            # Save the service context
            session.update_context({
                'service_context': service_context,
                'topic': service_context
            })
            return f"Got it! I've saved the context: {service_context}. Would you like me to generate hooks for this service? (e.g., 'generate 20 hooks' or 'regenerate hooks with offer X')"
        else:
            # Website mentioned but no clear description
            session.update_context({
                'topic': website
            })
            return f"I see you mentioned {website}. What would you like me to do? Generate hooks for it, or provide more details about what the service does?"
    
    # Check if user is correcting/clarifying previous hooks
    correction_keywords = ['not right', "aren't right", "don't work", "won't work", "wrong", "incorrect", "these aren't"]
    if any(kw in user_input.lower() for kw in correction_keywords):
        return "I understand these hooks aren't quite right. Could you tell me more about what you need? For example:\n- What service or website are these hooks for?\n- What should the offer or benefit be?\n- What's the target audience?\n\nOr say 'regenerate hooks with [your requirements]' to create new ones."
    
    return "I'm not sure what you mean. Type 'help' for available commands, or tell me what niche you want to generate hooks for."


def _preview_hooks(session: AgentSession):
    """Preview hooks in the session."""
    hooks = session.get_hooks()
    
    unique = hooks.get('unique', [])
    proven = hooks.get('proven', [])
    
    if not unique and not proven:
        print("\n[AGENT] No hooks to preview. Generate some first!")
        return
    
    print("\n" + "-" * 60)
    print("  HOOK PREVIEW")
    print("-" * 60)
    
    if unique:
        print(f"\n  UNIQUE HOOKS ({len(unique)}):")
        for i, h in enumerate(unique, 1):
            headline = h.get('headline', 'N/A')
            # Handle hooks that might have both headline and offer separated by |
            if '|' in headline:
                parts = headline.split('|', 1)
                print(f"  {i}. {parts[0].strip()}")
                if len(parts) > 1 and parts[1].strip():
                    print(f"      Offer: {parts[1].strip()}")
            else:
                print(f"  {i}. {headline}")
    
    if proven:
        print(f"\n  PROVEN FUSION HOOKS ({len(proven)}):")
        for i, h in enumerate(proven, 1):
            headline = h.get('headline', 'N/A')
            # Handle hooks that might have both headline and offer separated by |
            if '|' in headline:
                parts = headline.split('|', 1)
                print(f"  {i}. {parts[0].strip()}")
                if len(parts) > 1 and parts[1].strip():
                    print(f"      Offer: {parts[1].strip()}")
            else:
                print(f"  {i}. {headline}")
    
    print("-" * 60)


def _export_hooks(session: AgentSession):
    """Export hooks to images."""
    hooks = session.get_hooks()
    total = len(hooks.get('unique', [])) + len(hooks.get('proven', []))
    
    if total == 0:
        print("\n[AGENT] No hooks to export. Generate some first!")
        return
    
    print(f"\n[AGENT] Exporting {total} hooks to images...")
    print(f"[INFO] Session ID: {session.session_id}")
    print(f"[INFO] Run: python -m hook_generator.main --advanced --export-session {session.session_id}")


def _print_help():
    """Print help information."""
    print("""
Available Commands:
  generate [topic]  - Generate hooks for a niche
  preview          - Preview current hooks
  export           - Export hooks to images
  refine           - Modify existing hooks
  clear            - Clear session and start over
  help             - Show this help
  quit/exit        - Save and exit

Examples:
  "Generate 20 hooks for house painting"
  "Make the hooks more aggressive (ragebait 7)"
  "Regenerate hooks 5-10 with different angles"
  "What competitors are doing in this niche?"
""")
