"""
Campaign folder and template file setup.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from . import config
from .offer_manager import create_offers_template
from .performance_analyzer import register_campaign


def create_campaign_folder(
    campaign_name: str,
    offer_type: str
) -> Path:
    """
    Create a campaign folder with appropriate template files.
    
    Args:
        campaign_name: Name of the campaign
        offer_type: Type of offer ('service' or 'ecom')
        
    Returns:
        Path to the created campaign folder
    """
    # Sanitize campaign name for folder
    safe_name = "".join(c if c.isalnum() or c in ('-', '_', ' ') else '_' for c in campaign_name)
    safe_name = safe_name.replace(' ', '_')
    
    # Add timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = f"{safe_name}_{timestamp}"
    
    # Create folder path
    campaign_folder = config.OUTPUT_DIR / folder_name
    campaign_folder.mkdir(parents=True, exist_ok=True)
    
    # Create subfolders
    (campaign_folder / "images").mkdir(exist_ok=True)
    
    # Create appropriate template file
    if offer_type == config.OFFER_TYPE_SERVICE:
        offers_file = campaign_folder / "offers.txt"
        create_offers_template(offers_file)
        print(f"[OK] Created offers.txt template in {campaign_folder}")
    else:
        input_file = campaign_folder / "input_data.txt"
        create_ecom_template(input_file)
        print(f"[OK] Created input_data.txt template in {campaign_folder}")
    
    # Create campaign metadata
    metadata = {
        'campaign_name': campaign_name,
        'offer_type': offer_type,
        'created_at': datetime.now().isoformat(),
        'status': 'initialized'
    }
    
    metadata_file = campaign_folder / "campaign_metadata.json"
    try:
        # Ensure parent directory exists
        metadata_file.parent.mkdir(parents=True, exist_ok=True)
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2)
    except (IOError, PermissionError) as e:
        print(f"[ERROR] Failed to write campaign metadata: {e}")
        raise
    
    # Register campaign for RL tracking
    register_campaign(campaign_name, offer_type, campaign_folder)
    
    return campaign_folder


def create_ecom_template(input_file: Path) -> bool:
    """
    Create a template input_data.txt file for e-commerce offers.
    
    Args:
        input_file: Path to create the input_data.txt file
        
    Returns:
        True if successful
    """
    template = """# E-commerce Product Input Data
# Fill in the following information about your product:

# Product Name:


# Product Category:


# Main Benefits (one per line):
# -
# -
# -

# Target Audience:


# Main Pain Points (one per line):
# -
# -
# -

# Unique Selling Proposition:


# Price Point:


# Any specific claims or results:


"""
    
    try:
        with open(input_file, 'w', encoding='utf-8') as f:
            f.write(template)
        return True
    except Exception as e:
        print(f"[ERROR] Failed to create e-com template: {e}")
        return False


def update_campaign_status(
    campaign_folder: Path,
    status: str,
    additional_data: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Update campaign metadata with new status.
    
    Args:
        campaign_folder: Path to campaign folder
        status: New status string
        additional_data: Additional data to add to metadata
        
    Returns:
        True if successful
    """
    try:
        metadata_file = campaign_folder / "campaign_metadata.json"
        
        # Load existing metadata
        if metadata_file.exists():
            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
        else:
            metadata = {}
        
        # Update
        metadata['status'] = status
        metadata['updated_at'] = datetime.now().isoformat()
        
        if additional_data:
            metadata.update(additional_data)
        
        # Save
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2)
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Failed to update campaign status: {e}")
        return False


def build_comprehensive_metadata(
    campaign_name: str,
    offer_type: str,
    topic: str,
    competitor_data: Optional[Dict[str, Any]] = None,
    trend_data: Optional[Dict[str, Any]] = None,
    unique_hooks: Optional[List[Dict[str, Any]]] = None,
    proven_hooks: Optional[List[Dict[str, Any]]] = None,
    generation_config: Optional[Dict[str, Any]] = None,
    offers: Optional[List[str]] = None,
    analysis_type: str = "basic"
) -> Dict[str, Any]:
    """
    Build comprehensive campaign metadata including all research and generation data.
    
    This creates a complete record of:
    - Perplexity research (trends, angles, emotional triggers)
    - Competitor ads (hooks, offers, page names)
    - Generated hooks with reasoning
    - Configuration used for generation
    - Enhanced competitor analysis (if analysis_type == "enhanced")
    
    Args:
        campaign_name: Name of the campaign
        offer_type: Type of offer ('service' or 'ecom')
        topic: The search topic/niche
        competitor_data: Data from competitor analysis (ads, hooks, patterns)
        trend_data: Data from Perplexity research (trends, angles, triggers)
        unique_hooks: List of uniquely generated hooks
        proven_hooks: List of proven/fusion hooks
        generation_config: Configuration settings (ragebait_level, templates, keywords)
        offers: List of offers used
        analysis_type: Type of competitor analysis ("basic" or "enhanced")
        
    Returns:
        Comprehensive metadata dictionary
    """
    metadata: Dict[str, Any] = {
        'campaign_name': campaign_name,
        'offer_type': offer_type,
        'topic': topic,
        'created_at': datetime.now().isoformat(),
        'status': 'complete'
    }
    
    # Add generation configuration
    if generation_config:
        # Support both old 'ragebait_level' (int) and new 'ragebait_levels' (list) formats
        ragebait_config = generation_config.get('ragebait_levels', generation_config.get('ragebait_level'))
        if isinstance(ragebait_config, int):
            ragebait_config = [ragebait_config]
        elif ragebait_config is None:
            ragebait_config = [3]
        
        metadata['generation_config'] = {
            'ragebait_levels': ragebait_config,
            'template_ids': generation_config.get('template_ids', []),
            'positive_keywords': generation_config.get('positive_keywords', []),
            'negative_keywords': generation_config.get('negative_keywords', []),
            'auto_generate_keywords': generation_config.get('auto_generate_keywords', True)
        }
    
    # Add offers used
    if offers:
        metadata['offers'] = offers
    
    # Add Perplexity research data
    if trend_data:
        metadata['research_data'] = {
            'perplexity': {
                'success': trend_data.get('success', False),
                'niche': trend_data.get('niche', topic),
                'ragebait_level_used': trend_data.get('ragebait_level', 3),
                'trending_angles': trend_data.get('trending_angles', []),
                'avoid_angles': trend_data.get('avoid_angles', []),
                'emotional_triggers': trend_data.get('emotional_triggers', []),
                'controversies': trend_data.get('controversies', []),
                'complaints': trend_data.get('complaints', []),
                'current_events': trend_data.get('current_events', []),
                'recommended_ragebait_level': trend_data.get('recommended_ragebait_level'),
                'raw_research': trend_data.get('raw_research', '')
            }
        }
    else:
        metadata['research_data'] = {'perplexity': None}
    
    # Add generated hooks with full data (process proven hooks first to build source_ad mapping)
    generated_hooks = {
        'unique': [],
        'proven': []
    }
    
    # Build a mapping of source_ad_id to hook_index for linking competitor ads to generated hooks
    source_ad_to_hook_map = {}  # Maps source_ad_id -> list of hook_indices that used it
    
    # Process proven hooks first (to build the source_ad mapping)
    if proven_hooks:
        for i, hook in enumerate(proven_hooks, 1):
            hook_index = hook.get('hook_index', i)
            hook_entry = {
                'hook_index': hook_index,
                'headline': hook.get('headline', ''),
                'offer': hook.get('combined_offer', hook.get('offer', 'N/A')),
                'proven_angle': hook.get('proven_angle', hook.get('angle', '')),
                'source_inspiration': hook.get('source_inspiration', ''),
                'reasoning': hook.get('reasoning', 'Fused proven competitor angle with our offer'),
                # New source tracking fields
                'source_index': hook.get('source_index'),
                'source_ad_id': hook.get('source_ad_id', ''),
                'source_ad_offer': hook.get('source_ad_offer', ''),
                'source_page_name': hook.get('source_page_name', ''),
                'source_hook_text': hook.get('source_hook_text', ''),
                'competitor_offer': hook.get('competitor_offer', ''),
                'combined_offer': hook.get('combined_offer', hook.get('offer', ''))
            }
            # Include ragebait_level if present (for multi-ragebait support)
            if 'ragebait_level' in hook:
                hook_entry['ragebait_level'] = hook['ragebait_level']
            generated_hooks['proven'].append(hook_entry)
            
            # Build mapping of source_ad_id to hook_indices
            source_ad_id = hook.get('source_ad_id', '')
            if source_ad_id:
                if source_ad_id not in source_ad_to_hook_map:
                    source_ad_to_hook_map[source_ad_id] = []
                source_ad_to_hook_map[source_ad_id].append(hook_index)
    
    # Process unique hooks
    if unique_hooks:
        for i, hook in enumerate(unique_hooks, 1):
            hook_entry = {
                'hook_index': hook.get('hook_index', i),
                'headline': hook.get('headline', ''),
                'offer': hook.get('offer', 'N/A'),
                'angle': hook.get('angle', ''),
                'reasoning': hook.get('reasoning', 'Generated from research-based untargeted pain points')
            }
            # Include ragebait_level if present (for multi-ragebait support)
            if 'ragebait_level' in hook:
                hook_entry['ragebait_level'] = hook['ragebait_level']
            generated_hooks['unique'].append(hook_entry)
    
    metadata['generated_hooks'] = generated_hooks
    
    # Add competitor data (with linked_hook_ids for source tracking)
    if competitor_data:
        # Extract ads list from competitor data with linked_hook_ids
        competitor_ads = []
        for hook in competitor_data.get('hooks', []):
            ad_id = hook.get('id', '')
            ad_entry = {
                'id': ad_id,
                'page_name': hook.get('page_name', 'Unknown'),
                'hook_text': hook.get('hook_text', ''),
                'offer': hook.get('offer', 'N/A'),
                'ad_type': hook.get('ad_type', 'unknown'),
                'body_snippet': hook.get('body_snippet', '')[:300] if hook.get('body_snippet') else '',
                'snapshot_url': hook.get('snapshot_url', ''),
                'confidence': hook.get('confidence', 'medium'),
                # Link to generated hooks that used this ad as source
                'linked_hook_ids': source_ad_to_hook_map.get(ad_id, [])
            }
            competitor_ads.append(ad_entry)
        
        metadata['competitor_data'] = {
            'analysis_type': analysis_type,
            'scraped_at': competitor_data.get('scraped_at', ''),
            'scraped_at_iso': competitor_data.get('scraped_at_iso', datetime.now().isoformat()),
            'topic_searched': competitor_data.get('topic', topic),
            'ads_found': competitor_data.get('ads_found', 0),
            'hooks_extracted': competitor_data.get('hooks_extracted', len(competitor_ads)),
            'breakdown': competitor_data.get('breakdown', {'proven': 0, 'fresh': 0}),
            'filters_used': competitor_data.get('filters', {
                'positive_keywords': competitor_data.get('relevance_keywords', []),
                'negative_keywords': []
            }),
            'competitors': competitor_data.get('competitors', []),
            'insights': competitor_data.get('insights', {}),
            'patterns_to_avoid': competitor_data.get('patterns', [])[:20],  # Limit to 20 patterns
            'ads': competitor_ads,
            'source_tracking_summary': {
                'ads_used_as_source': len(source_ad_to_hook_map),
                'total_source_links': sum(len(hooks) for hooks in source_ad_to_hook_map.values())
            }
        }
        
        # Add unique offer deduplication stats if available
        unique_offer_stats = competitor_data.get('unique_offer_stats', {})
        if unique_offer_stats.get('enabled', False):
            metadata['competitor_data']['unique_offer_filtering'] = {
                'enabled': True,
                'unique_offers_found': unique_offer_stats.get('unique_count', 0),
                'total_ads_scraped': unique_offer_stats.get('total_scraped', 0),
                'duplicate_offers_removed': unique_offer_stats.get('duplicates_removed', 0),
                'target_met': unique_offer_stats.get('target_met', True),
                'offer_groups': unique_offer_stats.get('offer_groups', {})
            }
        else:
            metadata['competitor_data']['unique_offer_filtering'] = {
                'enabled': False
            }
        
        # Add enhanced analysis data if available
        if analysis_type == "enhanced":
            metadata['competitor_analysis'] = {
                'analysis_type': 'enhanced',
                'timestamp': datetime.now().isoformat()
            }
            
            # Add persona analysis
            persona_analysis = competitor_data.get('persona_analysis')
            if persona_analysis and isinstance(persona_analysis, dict):
                metadata['competitor_data']['persona_analysis'] = {
                    'common_personas': persona_analysis.get('common_personas', []),
                    'overused_personas': persona_analysis.get('overused_personas', []),
                    'underutilized_personas': persona_analysis.get('underutilized_personas', []),
                    'persona_distribution': persona_analysis.get('persona_distribution', {}),
                    'detailed': persona_analysis.get('detailed', [])
                }
            
            # Add desire/problem analysis
            desire_analysis = competitor_data.get('desire_problem_analysis')
            if desire_analysis and isinstance(desire_analysis, dict):
                metadata['competitor_data']['desire_problem_analysis'] = {
                    'common_desires': desire_analysis.get('common_desires', []),
                    'overused_desires': desire_analysis.get('overused_desires', []),
                    'underutilized_desires': desire_analysis.get('underutilized_desires', []),
                    'desire_distribution': desire_analysis.get('desire_distribution', {}),
                    'detailed': desire_analysis.get('detailed', [])
                }
            
            # Add mechanism analysis
            mechanism_analysis = competitor_data.get('mechanism_analysis')
            if mechanism_analysis and isinstance(mechanism_analysis, dict):
                metadata['competitor_data']['mechanism_analysis'] = {
                    'common_mechanisms': mechanism_analysis.get('common_mechanisms', []),
                    'overused_mechanisms': mechanism_analysis.get('overused_mechanisms', []),
                    'underutilized_mechanisms': mechanism_analysis.get('underutilized_mechanisms', []),
                    'mechanism_distribution': mechanism_analysis.get('mechanism_distribution', {}),
                    'detailed': mechanism_analysis.get('detailed', [])
                }
            
            # Add gap analysis
            gap_analysis = competitor_data.get('gap_analysis')
            if gap_analysis and isinstance(gap_analysis, dict):
                metadata['competitor_data']['gap_analysis'] = {
                    'recommended_strategies': gap_analysis.get('recommended_strategies', []),
                    'avoid_combinations': gap_analysis.get('avoid_combinations', []),
                    'overall_opportunity': gap_analysis.get('overall_opportunity', ''),
                    'recommended_personas': gap_analysis.get('recommended_personas', []),
                    'recommended_desires': gap_analysis.get('recommended_desires', []),
                    'recommended_mechanisms': gap_analysis.get('recommended_mechanisms', [])
                }
        else:
            metadata['competitor_analysis'] = {
                'analysis_type': 'basic',
                'timestamp': datetime.now().isoformat()
            }
    else:
        metadata['competitor_data'] = None
        metadata['competitor_analysis'] = {
            'analysis_type': analysis_type,
            'timestamp': datetime.now().isoformat()
        }
    
    # Add summary
    unique_count = len(unique_hooks) if unique_hooks else 0
    proven_count = len(proven_hooks) if proven_hooks else 0
    
    # Get unique offer stats if available
    unique_offer_stats = competitor_data.get('unique_offer_stats', {}) if competitor_data else {}
    
    metadata['summary'] = {
        'total_hooks': unique_count + proven_count,
        'unique_hooks': unique_count,
        'proven_hooks': proven_count,
        'competitor_ads_analyzed': len(competitor_data.get('hooks', [])) if competitor_data else 0,
        'research_available': bool(trend_data and trend_data.get('success')),
        'unique_offers_used': unique_offer_stats.get('unique_count', 0) if unique_offer_stats.get('enabled') else None,
        'unique_offer_target_met': unique_offer_stats.get('target_met', True) if unique_offer_stats.get('enabled') else None
    }
    
    return metadata


def save_comprehensive_metadata(
    campaign_folder: Path,
    metadata: Dict[str, Any]
) -> bool:
    """
    Save comprehensive metadata to the campaign folder.
    
    Args:
        campaign_folder: Path to campaign folder
        metadata: Comprehensive metadata dictionary
        
    Returns:
        True if successful
    """
    try:
        metadata_file = campaign_folder / "campaign_metadata.json"
        
        # Add final timestamp
        metadata['updated_at'] = datetime.now().isoformat()
        
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"[OK] Saved comprehensive campaign metadata to {metadata_file.name}")
        return True
        
    except Exception as e:
        print(f"[ERROR] Failed to save comprehensive metadata: {e}")
        return False

