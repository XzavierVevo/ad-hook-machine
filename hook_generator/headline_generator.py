"""
Headline generation using Claude to transform quotes into direct-response headlines.

Cost optimizations:
- Uses tiered model selection (Opus for creative, Haiku for simple shortening)
- Tracks API costs for session monitoring
"""

import json
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

from . import api_keys
from . import config
from .rate_limiter import anthropic_limiter
from .logger import bot_logger, log_data
from .cache_manager import track_cost


def _extract_text_from_response(response: Any) -> str:
    """
    Safely extract text from Anthropic API response.
    Handles different content block types (TextBlock, ThinkingBlock, etc.)
    """
    if not response.content or len(response.content) == 0:
        return ""
    
    content_block = response.content[0]
    # Check if it's a TextBlock (has .text attribute)
    if hasattr(content_block, 'text'):
        return content_block.text
    # If it's a different block type, try to get text representation
    return str(content_block)


def _build_ragebait_section(ragebait_level: int) -> str:
    """
    Build the ragebait instructions section based on the specified level (0-10).
    Reads from config.AI_PROMPTS['ragebait'].
    """
    # Common header for all levels
    header = f"=== RAGEBAIT LEVEL: {ragebait_level}/10 | 3RD GRADE READING | MAX {config.MAX_HOOK_WORD_COUNT} WORDS ===\n"
    
    # Get ragebait prompt from config based on level
    # Clamp level to valid range
    level = max(0, min(10, ragebait_level))
    
    # Get the appropriate prompt based on level ranges
    if level <= 2:
        prompt_level = 0
    elif level <= 5:
        prompt_level = 3
    elif level <= 7:
        prompt_level = 6
    elif level <= 9:
        prompt_level = 8
    else:  # level == 10
        prompt_level = 10
    
    ragebait_prompt = config.AI_PROMPTS['ragebait'][prompt_level]
    return header + ragebait_prompt


def generate_headlines(
    num_hooks: int,
    offers: Optional[List[str]] = None,
    offer_type: str = "service",
    offer_distribution: Optional[List[Tuple[str, int]]] = None,
    performance_history: Optional[Dict[str, Any]] = None,
    semantic_hooks: Optional[List[str]] = None,
    failure_analysis: str = "",
    trend_data: Optional[Dict[str, Any]] = None,
    ragebait_level: int = 3,
    competitor_data: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Generate unique ad hooks using Andromeda-style creative strategy with Claude Opus.
    
    Uses Meta's Andromeda ad architecture principles to create signal-rich static image
    hook concepts optimized for the "creative-as-targeting" paradigm.
    
    When trend_data is provided (from Perplexity research), this function finds untargeted
    pain points that competitors are NOT addressing and creates hooks to attack those gaps.
    The intensity of the hooks is scaled based on ragebait_level.
    
    When competitor_data includes enhanced analysis (analysis_type == 'enhanced'), the function
    uses gap analysis recommendations to target underutilized personas, desires, and mechanisms.
    
    Args:
        num_hooks: Number of hooks to generate (from command line)
        offers: List of specific offers to communicate
        offer_type: Type of offer ('service' or 'ecom')
        offer_distribution: Distribution of offers across hooks
        performance_history: Type-specific performance data (patterns and top ads)
        semantic_hooks: List of semantic hooks (actual claims/angles) from competitors to avoid
        failure_analysis: Negative reinforcement analysis from failed ads
        trend_data: Perplexity research data containing untargeted pain points, controversies, etc.
        ragebait_level: Ragebait intensity level 0-10 (default 3) - controls how extreme hooks are
        competitor_data: Competitor analysis data (may include enhanced gap analysis)
        
    Returns:
        List of headline dictionaries with 'headline', 'offer', 'angle'
    """
    if not api_keys.ANTHROPIC_CLIENT:
        api_keys.initialize_clients()
    
    if not api_keys.ANTHROPIC_CLIENT:
        raise ValueError("Anthropic API key not configured")
    
    # Build performance reinforcement section
    performance_section = ""
    if performance_history:
        top_ads = performance_history.get('top_ads', [])
        patterns = performance_history.get('patterns', {})
        
        if top_ads or patterns:
            performance_section = f"\n=== OUR HISTORICAL PERFORMANCE (REINFORCEMENT LEARNING) ===\n"
            performance_section += f"The following data shows what has actually generated the MOST TOTAL PROFIT for {offer_type.upper()} offers.\n"
            performance_section += "PRIORITIZE scaling these successful patterns and angles.\n\n"
            
            if patterns:
                performance_section += "PROVEN PROFITABLE PATTERNS (Sorted by GPT - Gross Profit Per Transaction):\n"
                sorted_patterns = sorted(patterns.items(), key=lambda x: x[1].get('gpt', 0) if isinstance(x[1], dict) else 0, reverse=True)
                for p_name, stats in sorted_patterns:
                    gpt = stats.get('gpt', 0)
                    aov = stats.get('aov', 0)
                    cpa = stats.get('cpa', 0)
                    conversions = stats.get('total_conversions', 0)
                    if gpt > 0:
                        performance_section += f"- {p_name.upper()}: GPT=${gpt:.2f} | {conversions} sales\n"
            
            if top_ads:
                performance_section += "\nTOP PROFITABLE ADS:\n"
                sorted_ads = sorted(top_ads[:10], key=lambda x: x.get('gpt', x.get('profit', 0)), reverse=True)
                for ad in sorted_ads[:5]:
                    name = ad.get('name', 'N/A')
                    gpt = ad.get('gpt', 0)
                    if gpt > 0:
                        performance_section += f"- \"{name}\" | GPT=${gpt:.2f}\n"

    # Add failure analysis section
    if failure_analysis:
        performance_section += f"\n=== NEGATIVE REINFORCEMENT (FAILED PATTERNS TO AVOID) ===\n"
        performance_section += f"{failure_analysis}\n"

    # Build competitor avoidance section
    competitor_section = ""
    if semantic_hooks:
        semantic_list = '\n'.join(f'- "{sh}"' for sh in semantic_hooks[:50])
        competitor_section = f"""
=== COMPETITOR HOOKS TO AVOID (SEMANTIC DIFFERENTIATION) ===
These are competitor claims/angles - create COMPLETELY DIFFERENT approaches:
{semantic_list}

YOUR MISSION: Be semantically orthogonal. If they use ROI angle, use speed/status/health. 
The OFFER stays exact, only the ANGLE must be unique.
"""
    
    # Build research-based gap analysis section (for unique hooks targeting untargeted pain points)
    research_section = ""
    if trend_data and trend_data.get('success'):
        research_section = f"\n=== REAL-TIME MARKET RESEARCH - FIND UNTARGETED PAIN POINTS ===\n"
        research_section += "MISSION: Use this research to find pain points that competitors are NOT targeting.\n"
        research_section += "Create hooks that attack these untargeted gaps with intensity based on ragebait_level {ragebait_level}/10.\n\n"
        
        trending_angles = trend_data.get('trending_angles', [])
        avoid_angles = trend_data.get('avoid_angles', [])
        emotional_triggers = trend_data.get('emotional_triggers', [])
        controversies = trend_data.get('controversies', [])
        complaints = trend_data.get('complaints', [])
        raw_research = trend_data.get('raw_research', '')
        
        if trending_angles:
            research_section += f"TRENDING ANGLES (what's working now):\n"
            for angle in trending_angles[:10]:
                research_section += f"- {angle}\n"
            research_section += "\n"
        
        if avoid_angles:
            research_section += f"OVERSATURATED ANGLES (avoid these - everyone is using them):\n"
            for angle in avoid_angles[:10]:
                research_section += f"- {angle}\n"
            research_section += "\n"
        
        if emotional_triggers:
            research_section += f"EMOTIONAL TRIGGERS (untargeted pain points to exploit):\n"
            for trigger in emotional_triggers[:15]:
                research_section += f"- {trigger}\n"
            research_section += "\n"
        
        if controversies:
            research_section += f"CURRENT CONTROVERSIES (ragebait opportunities):\n"
            for controversy in controversies[:10]:
                research_section += f"- {controversy}\n"
            research_section += "\n"
        
        if complaints:
            research_section += f"CUSTOMER COMPLAINTS (untargeted frustrations):\n"
            for complaint in complaints[:10]:
                research_section += f"- {complaint}\n"
            research_section += "\n"
        
        if raw_research:
            # Include a summary of raw research (truncated)
            research_summary = raw_research[:1500] if len(raw_research) > 1500 else raw_research
            research_section += f"DETAILED RESEARCH INSIGHTS:\n{research_summary}\n"
            if len(raw_research) > 1500:
                research_section += "...\n"
        
        research_section += "\nSTRATEGY:\n"
        research_section += f"- Ragebait Level {ragebait_level}/10: "
        if ragebait_level <= 2:
            research_section += "Use subtle, factual pain points. No controversy.\n"
        elif ragebait_level <= 5:
            research_section += "Use contrarian angles. Question norms. Challenge assumptions.\n"
        elif ragebait_level <= 7:
            research_section += "Use personal betrayal stories. Righteous anger at villains.\n"
        elif ragebait_level <= 9:
            research_section += "Use political class warfare. Rigged system vs working families.\n"
        else:
            research_section += "MAXIMUM INTENSITY. Use highly controversial political/social framing. Explicit us vs them.\n"
        
        research_section += "- Find pain points from research that NO competitors are targeting\n"
        research_section += "- Create hooks that directly attack these untargeted gaps\n"
        research_section += "- Match the intensity to ragebait_level (higher = more extreme)\n"
    
    # Build enhanced gap analysis section (if enhanced competitor analysis was used)
    gap_analysis_section = ""
    if competitor_data and competitor_data.get('analysis_type') == 'enhanced':
        gap_analysis = competitor_data.get('gap_analysis', {})
        persona_analysis = competitor_data.get('persona_analysis', {})
        desire_analysis = competitor_data.get('desire_problem_analysis', {})
        mechanism_analysis = competitor_data.get('mechanism_analysis', {})
        
        if gap_analysis or persona_analysis or desire_analysis or mechanism_analysis:
            gap_analysis_section = "\n=== ENHANCED GAP ANALYSIS (DIFFERENTIATION OPPORTUNITIES) ===\n"
            gap_analysis_section += "Use this analysis to create hooks that DIFFERENTIATE from competitors.\n\n"
            
            # Add underutilized personas
            underutilized_personas = persona_analysis.get('underutilized_personas', [])
            if underutilized_personas:
                gap_analysis_section += f"TARGET THESE UNDERUTILIZED PERSONAS (competitors are NOT speaking to them):\n"
                for persona in underutilized_personas[:5]:
                    gap_analysis_section += f"- {persona}\n"
                gap_analysis_section += "\n"
            
            # Add underutilized desires
            underutilized_desires = desire_analysis.get('underutilized_desires', [])
            if underutilized_desires:
                gap_analysis_section += f"ADDRESS THESE UNDERUTILIZED DESIRES/PROBLEMS (competitors are NOT addressing them):\n"
                for desire in underutilized_desires[:5]:
                    gap_analysis_section += f"- {desire}\n"
                gap_analysis_section += "\n"
            
            # Add underutilized mechanisms
            underutilized_mechanisms = mechanism_analysis.get('underutilized_mechanisms', [])
            if underutilized_mechanisms:
                gap_analysis_section += f"USE THESE UNDERUTILIZED MECHANISMS (competitors are NOT using them):\n"
                for mechanism in underutilized_mechanisms[:5]:
                    gap_analysis_section += f"- {mechanism}\n"
                gap_analysis_section += "\n"
            
            # Add recommended strategies
            strategies = gap_analysis.get('recommended_strategies', [])
            if strategies:
                gap_analysis_section += f"RECOMMENDED DIFFERENTIATION STRATEGIES:\n"
                for i, strategy in enumerate(strategies[:3], 1):
                    gap_analysis_section += f"{i}. {strategy.get('strategy_name', 'Strategy')}\n"
                    gap_analysis_section += f"   - Target: {strategy.get('target_persona', 'N/A')}\n"
                    gap_analysis_section += f"   - Problem: {strategy.get('desire_problem', 'N/A')}\n"
                    gap_analysis_section += f"   - Mechanism: {strategy.get('mechanism', 'N/A')}\n"
                    gap_analysis_section += f"   - Hook angle: {strategy.get('sample_hook_angle', 'N/A')}\n\n"
            
            # Add overall opportunity
            opportunity = gap_analysis.get('overall_opportunity', '')
            if opportunity:
                gap_analysis_section += f"BIGGEST OPPORTUNITY: {opportunity}\n\n"
            
            gap_analysis_section += "MISSION: Create hooks that use these gaps to stand out from competitors.\n"
            
            # Print feedback about enhanced analysis being used
            print(f"[ENHANCED] Using gap analysis for hook differentiation:")
            if underutilized_personas:
                print(f"  - Targeting {len(underutilized_personas)} underutilized personas")
            if underutilized_desires:
                print(f"  - Addressing {len(underutilized_desires)} underutilized desires")
            if underutilized_mechanisms:
                print(f"  - Using {len(underutilized_mechanisms)} underutilized mechanisms")
    
    # Build offers section with explicit assignment
    offers_section = ""
    if offers:
        offers_list = '\n'.join(f'- {offer}' for offer in offers)
        
        # Build explicit offer assignment if distribution is provided
        assignment_section = ""
        if offer_distribution:
            assignment_lines = []
            hook_idx = 1
            for offer, count in offer_distribution:
                if count > 0:
                    hook_range = f"Hooks {hook_idx}-{hook_idx + count - 1}" if count > 1 else f"Hook {hook_idx}"
                    assignment_lines.append(f"{hook_range}: MUST use EXACTLY: \"{offer}\"")
                    hook_idx += count
            assignment_section = "\nOFFER ASSIGNMENTS:\n" + "\n".join(assignment_lines) + "\n"
        
        offers_section = f"""
=== OFFER CONTEXT ===
{offers_list}
{assignment_section}
CRITICAL: Use EXACT prices and service descriptions. NEVER invent or change offer details.
"""
    
    # Build ragebait section based on level
    ragebait_section = _build_ragebait_section(ragebait_level)
    
    # Build the Andromeda-style prompt from config
    prompt = config.AI_PROMPTS['headline_generation']['main'].format(
        num_hooks=num_hooks,
        max_words=config.MAX_HOOK_WORD_COUNT,
        ragebait_section=ragebait_section,
        performance_section=performance_section,
        competitor_section=competitor_section,
        research_section=research_section,  # Add research section for gap targeting
        offers_section=offers_section,
        gap_analysis_section=gap_analysis_section  # Add enhanced gap analysis when available
    )

    # Use tiered model selection for headline generation
    model = api_keys.get_model_for_task('headline_generation')
    print(f"[INFO] Generating {num_hooks} unique Andromeda-style hooks with {model}...")
    
    try:
        anthropic_limiter.wait()
        
        # Use streaming to handle long-running operations (>10 min timeout)
        content = ""
        input_tokens = 0
        output_tokens = 0
        stop_reason = None
        
        with api_keys.ANTHROPIC_CLIENT.messages.stream(
            model=model,
            max_tokens=8192,
            messages=[
                {"role": "user", "content": prompt}
            ]
        ) as stream:
            for text in stream.text_stream:
                content += text
            
            # Get final message for usage stats
            final_message = stream.get_final_message()
            input_tokens = 0
            output_tokens = 0
            stop_reason = None
            if final_message:
                if hasattr(final_message, 'usage') and final_message.usage:
                    input_tokens = getattr(final_message.usage, 'input_tokens', 0)
                    output_tokens = getattr(final_message.usage, 'output_tokens', 0)
                stop_reason = getattr(final_message, 'stop_reason', None)
        
        # Track API cost
        if input_tokens > 0 or output_tokens > 0:
            track_cost(model, input_tokens, output_tokens)
        
        content = content.strip()
        
        # Check if response was truncated
        if stop_reason == "max_tokens":
            print(f"[WARNING] Claude response was truncated (hit max_tokens). JSON parsing might fail.")
        
        # Parse JSON response
        cleaned_content = content
        if cleaned_content.startswith("```"):
            cleaned_content = cleaned_content.split("```")[1]
            if cleaned_content.startswith("json"):
                cleaned_content = cleaned_content[4:]
        
        try:
            all_headlines = json.loads(cleaned_content)
            
            # Check for word count violations (just log, don't use AI to shorten)
            for h in all_headlines:
                headline_text = h.get('headline', '')
                word_count = len(headline_text.split())
                
                if word_count > config.MAX_HOOK_WORD_COUNT:
                    print(f"[WARNING] Headline is {word_count} words (max {config.MAX_HOOK_WORD_COUNT}), keeping as-is")
            
            # Log the total generated headlines
            if all_headlines:
                log_data(all_headlines, f"Generated {len(all_headlines)} Andromeda-style headlines from Claude Opus")
            
            return all_headlines
            
        except json.JSONDecodeError as e:
            print(f"[ERROR] Failed to parse headlines JSON: {e}")
            print(f"Full response length: {len(content)} characters")
            print(f"Last 200 characters of response: ...{content[-200:]}")
            # Try recovery
            if content.strip().endswith('}'):
                try:
                    all_headlines = json.loads(cleaned_content + ']')
                    return all_headlines
                except json.JSONDecodeError:
                    pass
            return []
                
    except Exception as e:
        print(f"[ERROR] Failed to generate headlines: {e}")
        return []


def extract_proven_angles(competitor_hooks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Extract proven angles/patterns from competitor hooks (prioritizing older, proven ads).
    
    Args:
        competitor_hooks: List of competitor hook dictionaries
        
    Returns:
        Dictionary with proven angles and their characteristics
    """
    proven_angles = {
        'financing': [],
        'urgency': [],
        'timeline': [],
        'price': [],
        'guarantee': [],
        'social_proof': []
    }
    
    # Filter for proven hooks (28+ days old)
    proven_hooks = [h for h in competitor_hooks if h.get('age_days', 0) >= 28]
    
    # If we don't have enough 28+ day hooks, include 14-28 day ones
    if len(proven_hooks) < 10:
        additional_proven = [h for h in competitor_hooks if 14 <= h.get('age_days', 0) < 28]
        proven_hooks.extend(additional_proven[:20])
    
    # Extract text for analysis
    for hook in proven_hooks:
        hook_text = hook.get('image_hook') or hook.get('hook_text', '').lower()
        body_text = hook.get('body_snippet', '').lower()
        combined_text = f"{hook_text} {body_text}"
        
        # Detect financing angle
        if any(term in combined_text for term in ['financing', 'finance', 'weekly payment', 'monthly payment', 
                                                   'payment plan', 'afford', 'low as', 'per week', 'per month', 
                                                   '$/week', '$/month']):
            proven_angles['financing'].append({
                'hook_text': hook.get('image_hook') or hook.get('hook_text', ''),
                'pattern': hook.get('primary_pattern', 'unknown'),
                'age_days': hook.get('age_days', 0)
            })
        
        # Detect urgency angle
        if any(term in combined_text for term in ['limited', 'now', 'today', 'hurry', 'only', 'ending', 'expire']):
            proven_angles['urgency'].append({
                'hook_text': hook.get('image_hook') or hook.get('hook_text', ''),
                'pattern': hook.get('primary_pattern', 'unknown'),
                'age_days': hook.get('age_days', 0)
            })
        
        # Detect timeline angle
        if any(term in combined_text for term in ['week', 'day', 'hour', 'fast', 'quick', 'instant', 'saturday', 
                                                   'tomorrow', 'done by', 'completed', 'finished']):
            proven_angles['timeline'].append({
                'hook_text': hook.get('image_hook') or hook.get('hook_text', ''),
                'pattern': hook.get('primary_pattern', 'unknown'),
                'age_days': hook.get('age_days', 0)
            })
        
        # Detect price angle
        if any(term in combined_text for term in ['$', 'free', 'save', 'discount', 'off', 'deal', 'starting at']):
            proven_angles['price'].append({
                'hook_text': hook.get('image_hook') or hook.get('hook_text', ''),
                'pattern': hook.get('primary_pattern', 'unknown'),
                'age_days': hook.get('age_days', 0)
            })
        
        # Detect guarantee angle
        if any(term in combined_text for term in ['guarantee', 'guaranteed', 'warranty', 'promise', 'assurance']):
            proven_angles['guarantee'].append({
                'hook_text': hook.get('image_hook') or hook.get('hook_text', ''),
                'pattern': hook.get('primary_pattern', 'unknown'),
                'age_days': hook.get('age_days', 0)
            })
        
        # Detect social proof angle
        if any(term in combined_text for term in ['review', 'rated', 'trusted', 'customer', 'testimonial', 
                                                   'proven', 'experienced', 'years']):
            proven_angles['social_proof'].append({
                'hook_text': hook.get('image_hook') or hook.get('hook_text', ''),
                'pattern': hook.get('primary_pattern', 'unknown'),
                'age_days': hook.get('age_days', 0)
            })
    
    # Count angles and identify most proven ones
    angle_counts = {k: len(v) for k, v in proven_angles.items()}
    sorted_angles = sorted(angle_counts.items(), key=lambda x: x[1], reverse=True)
    
    # Get top 3 proven angles
    top_angles = [angle for angle, count in sorted_angles[:3] if count > 0]
    
    return {
        'angles': proven_angles,
        'angle_counts': angle_counts,
        'top_proven_angles': top_angles,
        'proven_hooks_count': len(proven_hooks)
    }


def generate_proven_hooks(
    competitor_data: Dict[str, Any],
    num_hooks: int,
    offers: Optional[List[str]] = None,
    offer_type: str = "service",
    offer_distribution: Optional[List[Tuple[str, int]]] = None,
    failure_analysis: str = "",
    ragebait_level: int = 3,
    hooks_per_source_offer: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Generate hooks by FUSING proven competitor hooks/offers with our offers using Andromeda strategy.
    
    Uses Meta's Andromeda ad architecture to fuse winning competitor angles with our exact
    offer details, creating signal-rich static image hook concepts.
    
    Args:
        competitor_data: Dictionary with competitor analysis results (from get_competitor_analysis)
        num_hooks: Number of proven hooks to generate (from command line)
        offers: List of specific offers to communicate
        offer_type: Type of offer ('service' or 'ecom')
        offer_distribution: Distribution of offers across hooks
        failure_analysis: Negative reinforcement analysis from failed ads
        ragebait_level: Ragebait intensity level 0-10 (default 3)
        hooks_per_source_offer: If specified, ensures each competitor source offer is used 
                                exactly this many times (for even distribution across ragebait levels)
        
    Returns:
        List of headline dictionaries with 'headline', 'offer', 'angle', 'source_ad_id', 'source_ad_offer'
    """
    if not api_keys.ANTHROPIC_CLIENT:
        api_keys.initialize_clients()
    
    if not api_keys.ANTHROPIC_CLIENT:
        raise ValueError("Anthropic API key not configured")
    
    # Extract competitor hooks (with Haiku-analyzed hook and offer)
    competitor_hooks = competitor_data.get('hooks', [])
    if not competitor_hooks:
        print("[WARNING] No competitor hooks available for proven hooks generation")
        return []
    
    # Filter for hooks that have valid offers (already filtered by browser_scraper)
    hooks_with_offers = [h for h in competitor_hooks if h.get('offer') and h.get('offer') != 'N/A']
    
    if not hooks_with_offers:
        print("[WARNING] No competitor hooks with valid offers available")
        # Fall back to all hooks if none have offers
        hooks_with_offers = competitor_hooks
    
    print(f"[INFO] Found {len(hooks_with_offers)} competitor hooks with valid offers")
    
    # Debug: Check what ad_types we have
    ad_type_counts = {}
    for h in hooks_with_offers:
        ad_type = h.get('ad_type', 'MISSING')
        ad_type_counts[ad_type] = ad_type_counts.get(ad_type, 0) + 1
    
    print(f"[DEBUG] Hook ad_type distribution: {ad_type_counts}")
    print(f"[DEBUG] Sample hook ad_types: {[h.get('ad_type', 'MISSING') for h in hooks_with_offers[:5]]}")
    print(f"[DEBUG] Sample hook age_days: {[h.get('age_days', 'MISSING') for h in hooks_with_offers[:5]]}")
    
    # Separate proven (30+ days) and fresh (7 days) hooks
    # Check ad_type first (set by browser_scraper), then fall back to age_days
    # A hook is proven if: ad_type == 'proven' OR (age_days >= 28 AND ad_type != 'fresh')
    proven_hooks = [
        h for h in hooks_with_offers 
        if h.get('ad_type') == 'proven' or (h.get('age_days', 0) >= 28 and h.get('ad_type') != 'fresh')
    ]
    # A hook is fresh if: ad_type == 'fresh' OR (age_days <= 7 AND ad_type != 'proven')
    fresh_hooks = [
        h for h in hooks_with_offers 
        if h.get('ad_type') == 'fresh' or (h.get('age_days', 0) <= 7 and h.get('ad_type') != 'proven')
    ]
    
    # Debug logging
    proven_by_ad_type = len([h for h in hooks_with_offers if h.get('ad_type') == 'proven'])
    proven_by_age = len([h for h in hooks_with_offers if h.get('age_days', 0) >= 28])
    print(f"[DEBUG] Proven hooks found: {len(proven_hooks)} (by ad_type='proven': {proven_by_ad_type}, by age_days>=28: {proven_by_age})")
    print(f"[DEBUG] Fresh hooks found: {len(fresh_hooks)}")
    
    if not proven_hooks:
        print("[WARNING] No proven hooks found! This will cause proven hooks generation to fail.")
        print("[WARNING] Check that hooks have 'ad_type'='proven' or 'age_days'>=28")
        # Fallback: if we have hooks with offers but no proven ones, use all of them
        # This ensures we can still generate hooks even if classification failed
        if hooks_with_offers:
            print(f"[FALLBACK] Using all {len(hooks_with_offers)} hooks with offers as proven hooks (classification may have failed)")
            proven_hooks = hooks_with_offers[:min(30, len(hooks_with_offers))]
        else:
            print("[ERROR] No hooks with offers available. Cannot generate proven hooks.")
            return []
    
    # Build a unified index mapping for all competitor hooks
    # This maps 1-based index to the original hook data for source tracking
    all_indexed_hooks = []
    source_index_map = {}  # Maps 1-based index to original hook data
    
    # Add proven hooks first
    for h in proven_hooks[:30]:
        idx = len(all_indexed_hooks) + 1
        source_index_map[idx] = h
        all_indexed_hooks.append((idx, h, 'proven'))
    
    # Add fresh hooks
    for h in fresh_hooks[:20]:
        idx = len(all_indexed_hooks) + 1
        source_index_map[idx] = h
        all_indexed_hooks.append((idx, h, 'fresh'))
    
    # Build competitor hooks section for prompt - showing both hook and offer with unified indices
    competitor_hooks_section = "\n=== COMPETITOR HOOKS WITH OFFERS (PROVEN PERFORMERS) ===\n"
    competitor_hooks_section += "These are REAL hooks and offers from competitor ads. FUSE their winning angles with OUR offers.\n"
    competitor_hooks_section += "IMPORTANT: Use the SOURCE INDEX number to track which competitor ad you used.\n\n"
    
    # Group by type but maintain unified indices
    proven_indexed = [(idx, h) for idx, h, ad_type in all_indexed_hooks if ad_type == 'proven']
    fresh_indexed = [(idx, h) for idx, h, ad_type in all_indexed_hooks if ad_type == 'fresh']
    
    if proven_indexed:
        competitor_hooks_section += "PROVEN ADS (30+ days old - battle-tested winners):\n"
        for idx, h in proven_indexed:
            hook_text = h.get('hook_text') or h.get('haiku_hook') or h.get('image_hook', '')
            offer_text = h.get('offer') or h.get('haiku_offer', 'N/A')
            age = h.get('age_days', 30)
            ad_id = h.get('id', 'unknown')
            competitor_hooks_section += f"SOURCE INDEX {idx}. [ID: {ad_id}] [{age} days] HOOK: \"{hook_text}\"\n   OFFER: \"{offer_text}\"\n\n"
    
    if fresh_indexed:
        competitor_hooks_section += "\nFRESH ADS (last 7 days - emerging trends):\n"
        for idx, h in fresh_indexed:
            hook_text = h.get('hook_text') or h.get('haiku_hook') or h.get('image_hook', '')
            offer_text = h.get('offer') or h.get('haiku_offer', 'N/A')
            ad_id = h.get('id', 'unknown')
            competitor_hooks_section += f"SOURCE INDEX {idx}. [ID: {ad_id}] HOOK: \"{hook_text}\"\n   OFFER: \"{offer_text}\"\n\n"
    
    # Build source offer distribution section if hooks_per_source_offer is specified
    source_distribution_section = ""
    if hooks_per_source_offer and hooks_per_source_offer > 0 and all_indexed_hooks:
        total_sources = len(all_indexed_hooks)
        source_distribution_section = "\n=== SOURCE OFFER DISTRIBUTION (MANDATORY) ===\n"
        source_distribution_section += f"You MUST use each source offer EXACTLY {hooks_per_source_offer} times.\n"
        source_distribution_section += f"Total hooks to generate: {num_hooks}\n"
        source_distribution_section += f"Total source offers: {total_sources}\n"
        source_distribution_section += f"Hooks per source: {hooks_per_source_offer}\n\n"
        source_distribution_section += "ASSIGNMENT (follow this exactly):\n"
        
        hook_idx = 1
        for source_idx, hook_data, ad_type in all_indexed_hooks:
            if hook_idx > num_hooks:
                break
            end_idx = min(hook_idx + hooks_per_source_offer - 1, num_hooks)
            offer_text = hook_data.get('offer') or hook_data.get('haiku_offer', 'N/A')
            if end_idx >= hook_idx:
                hook_range = f"Hooks {hook_idx}-{end_idx}" if end_idx > hook_idx else f"Hook {hook_idx}"
                source_distribution_section += f"  {hook_range}: Use SOURCE INDEX {source_idx} (\"{offer_text[:50]}...\")\n"
                hook_idx = end_idx + 1
        
        source_distribution_section += "\nThis ensures even distribution of offers. DO NOT deviate from this assignment.\n"
        
        # Add to competitor hooks section
        competitor_hooks_section += source_distribution_section
        
        print(f"[INFO] Source offer distribution: {hooks_per_source_offer} hooks per source offer")
    
    # Prepare failure context
    failure_context = ""
    if failure_analysis:
        failure_context = f"\n=== NEGATIVE REINFORCEMENT (FAILED PATTERNS TO AVOID) ===\n{failure_analysis}\n"
    
    # Build offers section
    offers_section = ""
    if offers:
        offers_list = '\n'.join(f'- {offer}' for offer in offers)
        
        # Build explicit offer assignment if distribution is provided
        assignment_section = ""
        if offer_distribution:
            assignment_lines = []
            hook_idx = 1
            for offer, count in offer_distribution:
                if count > 0:
                    hook_range = f"Hooks {hook_idx}-{hook_idx + count - 1}" if count > 1 else f"Hook {hook_idx}"
                    assignment_lines.append(f"{hook_range}: MUST use EXACTLY: \"{offer}\"")
                    hook_idx += count
            assignment_section = "\nOFFER ASSIGNMENTS:\n" + "\n".join(assignment_lines) + "\n"
        
        offers_section = f"""
=== OUR OFFERS (USE THESE EXACT DETAILS) ===
{offers_list}
{assignment_section}
{failure_context}
"""
    
    # Build ragebait section
    ragebait_section = _build_ragebait_section(ragebait_level)
    
    # Build enhanced gap analysis section (if enhanced competitor analysis was used)
    gap_analysis_section = ""
    if competitor_data.get('analysis_type') == 'enhanced':
        gap_analysis = competitor_data.get('gap_analysis', {})
        persona_analysis = competitor_data.get('persona_analysis', {})
        desire_analysis = competitor_data.get('desire_problem_analysis', {})
        mechanism_analysis = competitor_data.get('mechanism_analysis', {})
        
        if gap_analysis or persona_analysis or desire_analysis or mechanism_analysis:
            gap_analysis_section = "\n=== ENHANCED GAP ANALYSIS (DIFFERENTIATION WHILE FUSING) ===\n"
            gap_analysis_section += "While fusing competitor angles with our offer, DIFFERENTIATE using these gaps:\n\n"
            
            # Add underutilized personas
            underutilized_personas = persona_analysis.get('underutilized_personas', [])
            if underutilized_personas:
                gap_analysis_section += f"TARGET UNDERUTILIZED PERSONAS:\n"
                for persona in underutilized_personas[:3]:
                    gap_analysis_section += f"- {persona}\n"
                gap_analysis_section += "\n"
            
            # Add underutilized desires
            underutilized_desires = desire_analysis.get('underutilized_desires', [])
            if underutilized_desires:
                gap_analysis_section += f"ADDRESS UNDERUTILIZED DESIRES:\n"
                for desire in underutilized_desires[:3]:
                    gap_analysis_section += f"- {desire}\n"
                gap_analysis_section += "\n"
            
            # Add underutilized mechanisms
            underutilized_mechanisms = mechanism_analysis.get('underutilized_mechanisms', [])
            if underutilized_mechanisms:
                gap_analysis_section += f"USE UNDERUTILIZED MECHANISMS:\n"
                for mechanism in underutilized_mechanisms[:3]:
                    gap_analysis_section += f"- {mechanism}\n"
                gap_analysis_section += "\n"
            
            # Add recommended strategies
            strategies = gap_analysis.get('recommended_strategies', [])
            if strategies:
                gap_analysis_section += f"DIFFERENTIATION STRATEGY HINTS:\n"
                for strategy in strategies[:2]:
                    gap_analysis_section += f"- {strategy.get('sample_hook_angle', 'N/A')}\n"
                gap_analysis_section += "\n"
            
            gap_analysis_section += "MISSION: Fuse competitor angles BUT target different personas/desires where possible.\n"
            
            # Print feedback about enhanced analysis being used for proven hooks
            print(f"[ENHANCED] Applying gap analysis to proven hook fusion:")
            if underutilized_personas:
                print(f"  - Targeting {len(underutilized_personas)} underutilized personas")
            if underutilized_desires:
                print(f"  - Addressing {len(underutilized_desires)} underutilized desires")
            if underutilized_mechanisms:
                print(f"  - Using {len(underutilized_mechanisms)} underutilized mechanisms")
    
    # Build the Andromeda-style fusion prompt from config
    prompt = config.AI_PROMPTS['headline_generation']['proven_fusion'].format(
        num_hooks=num_hooks,
        max_words=config.MAX_HOOK_WORD_COUNT,
        competitor_hooks_section=competitor_hooks_section,
        offers_section=offers_section,
        ragebait_section=ragebait_section,
        gap_analysis_section=gap_analysis_section
    )

    # Use tiered model selection for proven hooks generation
    model = api_keys.get_model_for_task('proven_hooks')
    
    # BATCHING: Split large requests to avoid truncation
    # Each hook in JSON is ~300-400 characters, so 40 hooks ≈ 12-16k characters
    # With max_tokens=16384, we can safely generate ~40 hooks per batch
    BATCH_SIZE = 40
    
    if num_hooks > BATCH_SIZE:
        print(f"[INFO] Splitting {num_hooks} hooks into batches of {BATCH_SIZE} to avoid truncation...")
        
        all_headlines = []
        num_batches = (num_hooks + BATCH_SIZE - 1) // BATCH_SIZE  # Ceiling division
        
        for batch_idx in range(num_batches):
            batch_start = batch_idx * BATCH_SIZE
            batch_count = min(BATCH_SIZE, num_hooks - batch_start)
            batch_hook_start_idx = batch_start + 1  # 1-indexed
            
            print(f"[INFO] Batch {batch_idx + 1}/{num_batches}: Generating hooks {batch_hook_start_idx}-{batch_hook_start_idx + batch_count - 1}...")
            
            # Build batch-specific prompt with adjusted hook indices
            batch_prompt = config.AI_PROMPTS['headline_generation']['proven_fusion'].format(
                num_hooks=batch_count,
                max_words=config.MAX_HOOK_WORD_COUNT,
                competitor_hooks_section=competitor_hooks_section,
                offers_section=offers_section,
                ragebait_section=ragebait_section,
                gap_analysis_section=gap_analysis_section
            )
            # Add instruction to start hook_index at the right number
            batch_prompt += f"\n\nIMPORTANT: Start hook_index numbering at {batch_hook_start_idx} (not 1)."
            
            batch_headlines = _generate_proven_hooks_batch(
                prompt=batch_prompt,
                model=model,
                source_index_map=source_index_map,
                offers=offers,
                offer_distribution=offer_distribution,
                num_hooks=num_hooks,  # Total for offer distribution calculation
                batch_start_idx=batch_hook_start_idx
            )
            
            if batch_headlines:
                all_headlines.extend(batch_headlines)
                print(f"[OK] Batch {batch_idx + 1}: Generated {len(batch_headlines)} hooks")
            else:
                print(f"[WARNING] Batch {batch_idx + 1}: Failed to generate hooks")
        
        # Sort by hook_index to ensure correct order
        all_headlines = sorted(all_headlines, key=lambda x: x.get('hook_index', 0))
        
        if all_headlines:
            log_data(all_headlines, f"Generated {len(all_headlines)} Andromeda-style fusion hooks from Claude Opus (batched)")
            print(f"[INFO] Source tracking: {sum(1 for h in all_headlines if h.get('source_ad_id'))} hooks linked to source ads")
        
        return all_headlines
    
    # Single batch for smaller requests
    print(f"[INFO] Generating {num_hooks} Andromeda-style fusion hooks with {model}...")
    
    return _generate_proven_hooks_batch(
        prompt=prompt,
        model=model,
        source_index_map=source_index_map,
        offers=offers,
        offer_distribution=offer_distribution,
        num_hooks=num_hooks,
        batch_start_idx=1
    )


def _generate_proven_hooks_batch(
    prompt: str,
    model: str,
    source_index_map: Dict[int, Dict],
    offers: Optional[List[str]],
    offer_distribution: Optional[List[Tuple[str, int]]],
    num_hooks: int,
    batch_start_idx: int = 1,
    max_retries: int = 2
) -> List[Dict]:
    """
    Generate a single batch of proven hooks with retry logic for truncation.
    
    Args:
        prompt: The generation prompt
        model: Claude model to use
        source_index_map: Mapping of source indices to ad data
        offers: List of offers
        offer_distribution: Distribution of offers across hooks
        num_hooks: Total number of hooks (for offer distribution)
        batch_start_idx: Starting hook index for this batch
        max_retries: Number of retries on truncation
        
    Returns:
        List of generated hooks
    """
    for attempt in range(max_retries + 1):
        try:
            anthropic_limiter.wait()
            
            # Use streaming to handle long-running operations (>10 min timeout)
            content = ""
            input_tokens = 0
            output_tokens = 0
            stop_reason = None
            
            with api_keys.ANTHROPIC_CLIENT.messages.stream(
                model=model,
                max_tokens=16384,  # Increased from 8192 to handle larger responses
                messages=[
                    {"role": "user", "content": prompt}
                ]
            ) as stream:
                for text in stream.text_stream:
                    content += text
                
                # Get final message for usage stats
                final_message = stream.get_final_message()
                input_tokens = 0
                output_tokens = 0
                stop_reason = None
                if final_message:
                    if hasattr(final_message, 'usage') and final_message.usage:
                        input_tokens = getattr(final_message.usage, 'input_tokens', 0)
                        output_tokens = getattr(final_message.usage, 'output_tokens', 0)
                    stop_reason = getattr(final_message, 'stop_reason', None)
            
            # Track API cost
            if input_tokens > 0 or output_tokens > 0:
                track_cost(model, input_tokens, output_tokens)
            
            content = content.strip()
            
            # Check if response was truncated
            if stop_reason == "max_tokens":
                if attempt < max_retries:
                    print(f"[WARNING] Response truncated (attempt {attempt + 1}/{max_retries + 1}), retrying...")
                    continue
                else:
                    print(f"[ERROR] Response still truncated after {max_retries + 1} attempts. Attempting partial parse...")
                    # Try to salvage partial JSON by finding complete hooks
                    content = _try_salvage_truncated_json(content)
                
            # Parse JSON response
            cleaned_content = content
            if cleaned_content.startswith("```"):
                cleaned_content = cleaned_content.split("```")[1]
                if cleaned_content.startswith("json"):
                    cleaned_content = cleaned_content[4:]
            
            try:
                headlines = json.loads(cleaned_content)
                
                # Build mapping from hook_index to our_offer based on offer_distribution
                hook_index_to_offer = {}
                if offer_distribution:
                    current_idx = 1
                    for offer, count in offer_distribution:
                        for i in range(count):
                            hook_index_to_offer[current_idx] = offer
                            current_idx += 1
                elif offers:
                    for i in range(num_hooks):
                        hook_index_to_offer[i + 1] = offers[i % len(offers)]
                
                # Process headlines and enrich with source ad information
                final_headlines = []
                for h in headlines:
                    headline_text = h.get('headline', '')
                    word_count = len(headline_text.split())
                    
                    if word_count > config.MAX_HOOK_WORD_COUNT:
                        print(f"[WARNING] Fusion hook is {word_count} words (max {config.MAX_HOOK_WORD_COUNT}), keeping as-is")
                    
                    hook_idx = h.get('hook_index', len(final_headlines) + batch_start_idx)
                    our_assigned_offer = hook_index_to_offer.get(hook_idx, offers[0] if offers and len(offers) > 0 else '')
                    
                    # Enrich headline with source ad information
                    source_idx = h.get('source_index')
                    if source_idx and source_idx in source_index_map:
                        source_ad = source_index_map[source_idx]
                        h['source_ad_id'] = source_ad.get('id', '')
                        h['source_ad_offer'] = source_ad.get('offer', '')
                        h['source_page_name'] = source_ad.get('page_name', '')
                        h['source_hook_text'] = source_ad.get('hook_text', '') or source_ad.get('haiku_hook', '') or source_ad.get('image_hook', '')
                        h['source_snapshot_url'] = source_ad.get('snapshot_url', '')
                        
                        competitor_offer = source_ad.get('offer', '')
                        if competitor_offer and our_assigned_offer:
                            h['combined_offer'] = f"{competitor_offer} and {our_assigned_offer}"
                        elif competitor_offer:
                            h['combined_offer'] = competitor_offer
                        elif our_assigned_offer:
                            h['combined_offer'] = our_assigned_offer
                        else:
                            h['combined_offer'] = h.get('offer', '')
                        
                        h['competitor_offer'] = competitor_offer
                        h['our_offer'] = our_assigned_offer
                    else:
                        h['source_ad_id'] = ''
                        h['source_ad_offer'] = ''
                        h['source_page_name'] = ''
                        h['source_hook_text'] = ''
                        h['source_snapshot_url'] = ''
                        h['competitor_offer'] = ''
                        h['combined_offer'] = our_assigned_offer
                        h['our_offer'] = our_assigned_offer
                    
                    final_headlines.append(h)
                
                return final_headlines
                
            except json.JSONDecodeError as e:
                if attempt < max_retries:
                    print(f"[WARNING] JSON parse failed (attempt {attempt + 1}): {e}. Retrying...")
                    continue
                print(f"[ERROR] Failed to parse fusion hooks JSON: {e}")
                print(f"Full response length: {len(content)} characters")
                print(f"Last 200 characters of response: ...{content[-200:]}")
                return []
                
        except Exception as e:
            print(f"[ERROR] Failed to generate fusion hooks: {e}")
            return []
    
    return []


def _try_salvage_truncated_json(content: str) -> str:
    """
    Attempt to salvage a truncated JSON array by finding the last complete object.
    
    Args:
        content: Potentially truncated JSON string
        
    Returns:
        Repaired JSON string if possible, otherwise original
    """
    # Find the last complete JSON object (ends with })
    # and close the array
    try:
        # Look for the last complete object before truncation
        last_complete_obj = content.rfind('},')
        if last_complete_obj > 0:
            # Take everything up to and including the last complete object
            salvaged = content[:last_complete_obj + 1]
            # Close the array
            salvaged += ']'
            # Try to parse to verify it's valid
            json.loads(salvaged)
            print(f"[INFO] Salvaged {salvaged.count('hook_index')} complete hooks from truncated response")
            return salvaged
    except json.JSONDecodeError as e:
        bot_logger.debug(f"Failed to salvage JSON from truncated response: {e}")
        pass
    
    # Try another approach: find last }
    try:
        last_brace = content.rfind('}')
        if last_brace > 0:
            salvaged = content[:last_brace + 1] + ']'
            json.loads(salvaged)
            print(f"[INFO] Salvaged partial hooks from truncated response")
            return salvaged
    except json.JSONDecodeError as e:
        bot_logger.debug(f"Failed to salvage JSON using alternative method: {e}")
        pass
    
    return content


def save_headlines(headlines: List[Dict[str, Any]], output_path: Path) -> bool:
    """
    Save headlines to a JSON file.
    
    Args:
        headlines: List of headline dictionaries
        output_path: Path to save the JSON file
        
    Returns:
        True if successful
    """
    try:
        from pathlib import Path
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(headlines, f, indent=2, ensure_ascii=False)
        
        return True
    except Exception as e:
        print(f"[ERROR] Failed to save headlines: {e}")
        return False

