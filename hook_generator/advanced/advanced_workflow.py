"""
Advanced Workflow - Main entry point for --advanced mode.

This module orchestrates the advanced thinking agent workflow, providing:
- LangGraph-based decision loops
- Multi-source research (Facebook + Perplexity + Vision)
- Memory-enhanced generation
- Cost tracking and optimization
"""

import asyncio
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

from .. import config
from .. import api_keys
from ..campaign_setup import (
    create_campaign_folder, 
    update_campaign_status,
    build_comprehensive_metadata,
    save_comprehensive_metadata
)
from ..image_generator import batch_generate_images
from ..cache_manager import (
    print_cache_stats, print_session_costs, reset_session_costs, clear_dedup_cache
)
from .thinking_agent import ThinkingAgent, LANGGRAPH_AVAILABLE
from .agent_sessions import get_or_create_session


async def run_advanced_workflow(
    campaign_name: str,
    topic: str,
    count: int = 20,
    unique_offer_count: Optional[int] = None,
    offers: Optional[List[str]] = None,
    offer_type: str = "service",
    ragebait_levels: Optional[List[int]] = None,
    template_ids: Optional[List[int]] = None,
    use_memory: bool = False,
    url: Optional[str] = None,
    non_interactive: bool = False,
    positive_keywords: Optional[List[str]] = None,
    negative_keywords: Optional[List[str]] = None,
    auto_generate_keywords: bool = True,
    skip_offer_filters: bool = False,
    max_ads: int = 30
) -> Dict[str, Any]:
    """
    Run the advanced thinking agent workflow.
    
    Args:
        campaign_name: Name for the campaign
        topic: Niche/topic to target
        count: Number of hooks to generate
        unique_offer_count: Number of unique offers to find (defaults to count).
                           If different from count, hooks are distributed across offers.
        offers: List of offers
        offer_type: Type of offer ('service' or 'ecom')
        ragebait_levels: List of ragebait intensities (0-10). Hooks divided among levels. Default [3].
        template_ids: Specific template IDs to use
        use_memory: Whether to use Vertex AI Memory Bank
        url: Optional product URL to scrape for offers
        non_interactive: Skip user prompts
        positive_keywords: List of positive/required keywords (max 2)
        negative_keywords: List of negative/exclusion keywords (max 5)
        auto_generate_keywords: Whether to auto-generate keywords with Claude
        skip_offer_filters: Skip generating and using filters for offers
        max_ads: Maximum number of ads to scrape (controls scroll_limit, default: 30)
        
    Returns:
        Dictionary with workflow results
    """
    # Initialize ragebait levels and unique offer count
    ragebait_levels = ragebait_levels or [3]
    unique_offer_count = unique_offer_count or count  # Default to count if not specified
    
    print("\n" + "=" * 60)
    print("  AD HOOK GENERATION - Advanced Mode (Thinking Agent)")
    print("=" * 60)
    
    # Reset session tracking
    reset_session_costs()
    clear_dedup_cache()
    
    # Check LangGraph availability
    if not LANGGRAPH_AVAILABLE:
        print("\n[ERROR] LangGraph is required for advanced mode.")
        print("[INFO] Install with: pip install langgraph langchain-core")
        return {'success': False, 'error': 'LangGraph not installed'}
    
    # Create campaign folder
    print(f"\n[INFO] Creating campaign folder...")
    campaign_folder = create_campaign_folder(campaign_name, offer_type)
    print(f"[OK] Created: {campaign_folder}")
    
    # If URL provided, scrape for offers
    if url:
        print(f"\n[INFO] Scraping product page: {url}")
        from .product_scraper import scrape_product_page, generate_offers_from_product
        
        product_info = scrape_product_page(url)
        if product_info.get('success'):
            print(f"[OK] Extracted product info: {product_info.get('name', 'Unknown')}")
            
            # Generate offers if not provided
            if not offers:
                generated_offers = generate_offers_from_product(product_info, count=3)
                offers = [o.get('offer', '') for o in generated_offers if o.get('offer')]
                
                if offers:
                    print(f"[OK] Generated {len(offers)} offers from product page")
                    for i, offer in enumerate(offers, 1):
                        print(f"  {i}. {offer}")
    
    # Save offers to file
    if offers:
        offers_file = campaign_folder / "offers.txt"
        # Log offers before writing for debugging
        print(f"[INFO] Writing {len(offers)} offer(s) to {offers_file}:")
        for i, offer in enumerate(offers, 1):
            print(f"  {i}. \"{offer}\"")
            # Check for potential issues (double spaces, very short offers)
            if '  ' in offer:
                print(f"     [WARNING] Offer {i} contains double spaces - may be missing content")
            if len(offer) < 10:
                print(f"     [WARNING] Offer {i} is very short - may be incomplete")
        
        with open(offers_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(offers))
        print(f"[OK] Saved {len(offers)} offers to {offers_file}")
        
        # Verify file was written correctly
        try:
            with open(offers_file, 'r', encoding='utf-8') as f:
                written_offers = [line.strip() for line in f if line.strip()]
            if written_offers != offers:
                print(f"[WARNING] Offers written to file don't match input!")
                print(f"  Input: {offers}")
                print(f"  Written: {written_offers}")
        except Exception as e:
            print(f"[WARNING] Could not verify offers file: {e}")
    
    # Initialize thinking agent
    print(f"\n[INFO] Initializing Thinking Agent...")
    agent = ThinkingAgent(
        min_ads=10,
        max_iterations=3,
        use_memory=use_memory
    )
    print(f"[OK] Agent ready (use_memory={use_memory})")
    
    # Run the agent
    print(f"\n[INFO] Running thinking agent for '{topic}'...")
    
    # Calculate count per ragebait level
    num_ragebait_levels = len(ragebait_levels)
    count_per_level = count // num_ragebait_levels
    remainder = count % num_ragebait_levels
    
    if num_ragebait_levels > 1:
        print(f"[INFO] Multi-ragebait mode: {num_ragebait_levels} levels - {ragebait_levels}")
        print(f"[INFO] Target: {count} hooks total ({count_per_level} per level, +{remainder} remainder)")
    else:
        print(f"[INFO] Target: {count} hooks, ragebait level {ragebait_levels[0]}")
    
    # Log unique offer mode
    if unique_offer_count != count:
        ads_per_offer = count // unique_offer_count
        print(f"[INFO] Finding {unique_offer_count} unique offers ({ads_per_offer} hooks per offer)")
    else:
        print(f"[INFO] Finding up to {unique_offer_count} unique offers")
    
    if positive_keywords:
        print(f"[INFO] Positive keywords: {', '.join(positive_keywords)}")
    if negative_keywords:
        print(f"[INFO] Negative keywords: {', '.join(negative_keywords)}")
    
    try:
        # Call agent.run() ONCE with all ragebait levels and total count
        # The agent will gather data once, then generate hooks for all levels
        result = agent.run(
            task=f"Generate {count} high-converting ad hooks for {topic}",
            topic=topic,
            offers=offers,
            count=count,  # Total count - agent will divide across ragebait levels
            unique_offer_count=unique_offer_count,  # How many unique offers to find
            ragebait_level=ragebait_levels,  # Pass as list
            offer_type=offer_type,
            templates=template_ids,
            positive_keywords=positive_keywords,
            negative_keywords=negative_keywords,
            auto_generate_keywords=auto_generate_keywords,
            skip_offer_filters=skip_offer_filters,
            max_ads=max_ads
        )
        
        # Extract hooks (already tagged with ragebait levels by the agent)
        hooks = result.get('hooks', {})
        unique_hooks = hooks.get('unique', [])
        proven_hooks = hooks.get('proven', [])
        
        # Re-index all hooks sequentially
        for i, h in enumerate(unique_hooks, 1):
            h['hook_index'] = i
        for i, h in enumerate(proven_hooks, 1):
            h['hook_index'] = i
        
        total_hooks = len(unique_hooks) + len(proven_hooks)
        print(f"\n[OK] Generated {total_hooks} total hooks:")
        print(f"  - Unique: {len(unique_hooks)}")
        print(f"  - Proven: {len(proven_hooks)}")
        
        if num_ragebait_levels > 1:
            for level in ragebait_levels:
                unique_at_level = len([h for h in unique_hooks if h.get('ragebait_level') == level])
                proven_at_level = len([h for h in proven_hooks if h.get('ragebait_level') == level])
                print(f"  - Ragebait {level}: {unique_at_level} unique, {proven_at_level} proven")
        
        if total_hooks == 0:
            print("[ERROR] No hooks generated")
            return {'success': False, 'error': 'No hooks generated'}
        
        # Update campaign status
        update_campaign_status(campaign_folder, "hooks_generated", {
            'unique_hooks': len(unique_hooks),
            'proven_hooks': len(proven_hooks)
        })
        
    except Exception as e:
        print(f"[ERROR] Agent failed: {e}")
        return {'success': False, 'error': str(e)}
    
    # Generate images
    print(f"\n[INFO] Generating hook images...")
    images_dir = campaign_folder / "images"
    
    # Unique hooks
    if unique_hooks:
        print(f"[INFO] Generating {len(unique_hooks)} unique hook images...")
        # Prepare metadata for unique hooks
        for h in unique_hooks:
            h['type'] = 'unique'
        
        unique_results = await asyncio.to_thread(
            batch_generate_images,
            headlines=unique_hooks,
            output_dir=images_dir,
            create_psd=False,
            template_ids=template_ids
        )
        
        unique_success = sum(1 for r in unique_results if r['success'])
        print(f"[OK] Generated {unique_success}/{len(unique_hooks)} unique hook images")
    
    # Proven hooks
    if proven_hooks:
        print(f"[INFO] Generating {len(proven_hooks)} proven hook images...")
        # Prepare metadata for proven hooks
        for h in proven_hooks:
            h['type'] = 'proven'
        
        proven_results = await asyncio.to_thread(
            batch_generate_images,
            headlines=proven_hooks,
            output_dir=images_dir,
            create_psd=False,
            template_ids=template_ids
        )
        
        proven_success = sum(1 for r in proven_results if r['success'])
        print(f"[OK] Generated {proven_success}/{len(proven_hooks)} proven hook images")
    
    # Extract competitor and trend data from agent result
    competitor_data = result.get('competitor_data')
    trend_data = result.get('trend_data')
    
    # Build generation config for metadata
    generation_config = {
        'ragebait_levels': ragebait_levels,
        'template_ids': template_ids or [],
        'positive_keywords': positive_keywords or [],
        'negative_keywords': negative_keywords or [],
        'auto_generate_keywords': auto_generate_keywords,
        'count_requested': count,
        'use_memory': use_memory
    }
    
    # Build and save comprehensive metadata
    comprehensive_metadata = build_comprehensive_metadata(
        campaign_name=campaign_name,
        offer_type=offer_type,
        topic=topic,
        competitor_data=competitor_data,
        trend_data=trend_data,
        unique_hooks=unique_hooks,
        proven_hooks=proven_hooks,
        generation_config=generation_config,
        offers=offers
    )
    
    save_comprehensive_metadata(campaign_folder, comprehensive_metadata)
    
    # Print cost summary
    print_session_costs()
    
    print(f"\n[OK] Advanced workflow complete!")
    print(f"[INFO] Results saved to: {campaign_folder}")
    
    return {
        'success': True,
        'campaign_folder': str(campaign_folder),
        'unique_hooks': len(unique_hooks),
        'proven_hooks': len(proven_hooks),
        'total_hooks': total_hooks,
        'competitor_data': competitor_data,
        'trend_data': trend_data
    }


async def export_session_hooks(
    session_id: str,
    template_ids: Optional[List[int]] = None,
    output_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Export hooks from a saved session to images.
    
    Args:
        session_id: Session ID to export
        template_ids: Specific template IDs to use
        output_dir: Output directory (creates new campaign folder if None)
        
    Returns:
        Dictionary with export results
    """
    from .agent_sessions import AgentSession
    
    print(f"\n[INFO] Loading session: {session_id}")
    session = AgentSession(session_id)
    
    hooks = session.get_hooks()
    unique_hooks = hooks.get('unique', [])
    proven_hooks = hooks.get('proven', [])
    
    total = len(unique_hooks) + len(proven_hooks)
    
    if total == 0:
        print("[ERROR] No hooks in session to export")
        return {'success': False, 'error': 'No hooks in session'}
    
    print(f"[OK] Found {total} hooks ({len(unique_hooks)} unique, {len(proven_hooks)} proven)")
    
    # Create output directory
    if output_dir is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = config.OUTPUT_DIR / f"session_export_{session_id}_{timestamp}"
    
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    images_dir = output_dir / "images"
    images_dir.mkdir(exist_ok=True)
    
    # Generate images
    all_hooks = unique_hooks + proven_hooks
    all_texts = [h.get('headline', '') for h in all_hooks]
    
    print(f"[INFO] Generating {len(all_texts)} images...")
    
    results = await asyncio.to_thread(
        batch_generate_images,
        headlines=all_texts,
        output_dir=images_dir,
        create_psd=False,
        template_ids=template_ids
    )
    
    success_count = sum(1 for r in results if r['success'])
    print(f"[OK] Generated {success_count}/{len(all_texts)} images")
    print(f"[INFO] Output: {output_dir}")
    
    return {
        'success': True,
        'output_dir': str(output_dir),
        'images_generated': success_count,
        'total_hooks': total
    }
