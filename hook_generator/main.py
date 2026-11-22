#!/usr/bin/env python3
"""
Ad Hook Generation Bot - Console Edition
Main entry point for the automated hook generation workflow.

Workflow:
1. Quote Scraping (ChatGPT) - Scrape emotional quotes
2. Headline Generation (Claude) - Transform quotes to headlines
3. Image Creation (Pillow) - Generate hook images

Usage:
    python main.py
"""

import sys
import json
import os
import shutil
import argparse
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional, List

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from hook_generator import config
from hook_generator import api_keys
from hook_generator.logger import bot_logger
from hook_generator.quote_scraper import scrape_quotes
from hook_generator.headline_generator import generate_headlines, generate_proven_hooks
from hook_generator.image_generator import batch_generate_images
from hook_generator.competitor_data_puller import get_competitor_analysis, get_enhanced_competitor_analysis
from hook_generator.offer_manager import (
    load_offers_from_file,
    distribute_hooks_across_offers,
    validate_offers
)
from hook_generator.campaign_setup import (
    create_campaign_folder,
    update_campaign_status,
    build_comprehensive_metadata,
    save_comprehensive_metadata
)
from hook_generator.performance_analyzer import (
    sync_performance_history,
    get_type_specific_history,
    display_gpt_summary,
    analyze_failures
)


def safe_print(text: str):
    """Print text safely, handling Unicode characters that Windows console can't display."""
    try:
        print(text)
    except UnicodeEncodeError:
        # Replace problematic characters with ASCII equivalents
        safe_text = text.encode('ascii', 'replace').decode('ascii')
        print(safe_text)


def print_banner():
    """Print the application banner."""
    print("\n" + "=" * 60)
    print("  AD HOOK GENERATION BOT - Console Edition")
    print("  Automated Hook Generation")
    print("=" * 60 + "\n")


def print_step(step_num: int, title: str):
    """Print a step header."""
    print(f"\n{'-' * 60}")
    print(f"  STEP {step_num}: {title}")
    print(f"{'-' * 60}\n")


def get_user_input(prompt: str, default: Optional[str] = None) -> str:
    """Get user input with optional default."""
    if default:
        user_input = input(f"{prompt} [{default}]: ").strip()
        return user_input if user_input else default
    return input(f"{prompt}: ").strip()


def open_file_for_editing(file_path: Path) -> bool:
    """
    Open a file in the default system editor.
    
    Args:
        file_path: Path to the file to open
        
    Returns:
        True if successful, False otherwise
    """
    try:
        if sys.platform == "win32":
            # Windows: use os.startfile
            os.startfile(str(file_path))
        elif sys.platform == "darwin":
            # macOS: use open command
            import subprocess
            subprocess.run(["open", str(file_path)])
        else:
            # Linux: use xdg-open
            import subprocess
            subprocess.run(["xdg-open", str(file_path)])
        return True
    except Exception as e:
        print(f"[WARNING] Could not open file automatically: {e}")
        return False


def get_offer_type() -> str:
    """Get offer type from user."""
    print("Select offer type:")
    print("  1. service - Service offers (painting, home services, etc.)")
    print("  2. ecom    - E-commerce products (supplements, physical products)")
    print()
    
    while True:
        choice = get_user_input("Enter choice (1 or 2)", "1")
        if choice in ("1", "service"):
            return config.OFFER_TYPE_SERVICE
        elif choice in ("2", "ecom"):
            return config.OFFER_TYPE_ECOM
        else:
            print("Invalid choice. Please enter 1 or 2.")


def get_ragebait_level() -> int:
    """Get ragebait level from user (0-10)."""
    print("\nSelect ragebait level (0-10):")
    print("  0-2  - Direct, factual hooks with simple language")
    print("  3-5  - Mild contrarian tone, questioning")
    print("  6-7  - Strong emotional hooks, personal betrayal stories")
    print("  8-9  - Political class warfare, us vs them framing")
    print("  10   - Maximum ragebait with confrontational language")
    print()
    
    while True:
        try:
            level = int(get_user_input("Enter ragebait level (0-10)", "3"))
            if 0 <= level <= 10:
                return level
            else:
                print("Please enter a number between 0 and 10.")
        except ValueError:
            print("Please enter a valid number.")


def get_quote_count() -> int:
    """Get number of quotes to generate."""
    while True:
        try:
            count = int(get_user_input("How many hooks do you want to generate?", "10"))
            if count < 1:
                print("Please enter a positive number.")
                continue
            if count > 500:
                confirm = get_user_input(f"Generate {count} hooks? This may take a while. (y/n)", "n")
                if confirm.lower() != 'y':
                    continue
            return count
        except ValueError:
            print("Please enter a valid number.")


async def run_service_workflow(campaign_folder: Path, quote_count: int, cli_offers: Optional[List[str]] = None, cli_topic: Optional[str] = None, non_interactive: bool = False, ragebait_levels: Optional[List[int]] = None, template_ids: Optional[List[int]] = None, positive_keywords: Optional[List[str]] = None, negative_keywords: Optional[List[str]] = None, auto_generate_keywords: bool = True, enhanced_competitor: bool = False):
    """
    Run the workflow for service offers.
    
    Args:
        campaign_folder: Path to campaign folder
        quote_count: Number of hooks to generate
        cli_offers: Optional list of offers from CLI
        cli_topic: Optional topic from CLI
        non_interactive: Whether to run without user prompts
        ragebait_levels: List of ragebait intensity levels 0-10 (default [3]). Hooks divided among levels.
        template_ids: List of specific template IDs to use
        positive_keywords: List of positive/required keywords (max 2)
        negative_keywords: List of negative/exclusion keywords (max 5)
        auto_generate_keywords: Whether to auto-generate keywords with Claude Sonnet
        enhanced_competitor: Whether to use enhanced competitor analysis
    """
    ragebait_levels = ragebait_levels or [3]
    offers_file = campaign_folder / "offers.txt"
    
    if cli_offers:
        print(f"[INFO] Using {len(cli_offers)} offers from CLI arguments...")
        with open(offers_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(cli_offers))
        offers = cli_offers
    else:
        # Load offers
        print(f"\n[INFO] Opening {offers_file} for editing...")
        if open_file_for_editing(offers_file):
            print(f"[OK] File opened in default editor")
        else:
            print(f"[INFO] Please manually open: {offers_file}")
        print("[INFO] Add your service offers (one per line)")
        
        if not non_interactive:
            input("\nPress Enter when ready to continue...")
        
        offers = load_offers_from_file(offers_file)
    
    is_valid, message = validate_offers(offers)
    
    if not is_valid:
        print(f"[ERROR] {message}")
        return False
    
    print(f"[OK] {message}")
    for i, offer in enumerate(offers, 1):
        print(f"  {i}. {offer}")
    
    # Distribute hooks across offers
    distribution = distribute_hooks_across_offers(quote_count, offers)
    print(f"\n[INFO] Hook distribution:")
    for offer, count in distribution:
        print(f"  - {offer}: {count} hooks")
    
    # Get topic for competitor analysis
    if cli_topic:
        topic = cli_topic
    else:
        topic = get_user_input("\nEnter topic/niche for competitor analysis", "painting service")
    
    # Run the main workflow
    return await run_generation_workflow(
        campaign_folder=campaign_folder,
        topic=topic,
        quote_count=quote_count,
        offer_type=config.OFFER_TYPE_SERVICE,
        offers=offers,
        non_interactive=non_interactive,
        ragebait_levels=ragebait_levels,
        template_ids=template_ids,
        positive_keywords=positive_keywords,
        negative_keywords=negative_keywords,
        auto_generate_keywords=auto_generate_keywords,
        enhanced_competitor=enhanced_competitor
    )


async def run_ecom_workflow(campaign_folder: Path, quote_count: int, cli_topic: Optional[str] = None, non_interactive: bool = False, ragebait_levels: Optional[List[int]] = None, template_ids: Optional[List[int]] = None, positive_keywords: Optional[List[str]] = None, negative_keywords: Optional[List[str]] = None, auto_generate_keywords: bool = True, enhanced_competitor: bool = False):
    """
    Run the workflow for e-commerce offers.
    
    Args:
        campaign_folder: Path to campaign folder
        quote_count: Number of hooks to generate
        cli_topic: Optional topic from CLI
        non_interactive: Whether to run without user prompts
        ragebait_levels: List of ragebait intensity levels 0-10 (default [3]). Hooks divided among levels.
        template_ids: List of specific template IDs to use
        positive_keywords: List of positive/required keywords (max 2)
        negative_keywords: List of negative/exclusion keywords (max 5)
        auto_generate_keywords: Whether to auto-generate keywords with Claude Sonnet
        enhanced_competitor: Whether to use enhanced competitor analysis
    """
    ragebait_levels = ragebait_levels or [3]
    if not cli_topic:
        # Get product info
        input_file = campaign_folder / "input_data.txt"
        
        print(f"\n[INFO] Opening {input_file} for editing...")
        if open_file_for_editing(input_file):
            print(f"[OK] File opened in default editor")
        else:
            print(f"[INFO] Please manually open: {input_file}")
        print("[INFO] Fill in your product information")
        
        if not non_interactive:
            input("\nPress Enter when ready to continue...")
        
        # Get topic for competitor analysis
        topic = get_user_input("\nEnter product type/niche for competitor analysis")
    else:
        topic = cli_topic
    
    # Run the main workflow
    return await run_generation_workflow(
        campaign_folder=campaign_folder,
        topic=topic,
        quote_count=quote_count,
        offer_type=config.OFFER_TYPE_ECOM,
        offers=None,
        non_interactive=non_interactive,
        ragebait_levels=ragebait_levels,
        template_ids=template_ids,
        positive_keywords=positive_keywords,
        negative_keywords=negative_keywords,
        auto_generate_keywords=auto_generate_keywords,
        enhanced_competitor=enhanced_competitor
    )


async def run_generation_workflow(
    campaign_folder: Path,
    topic: str,
    quote_count: int,
    offer_type: str,
    offers: Optional[List[str]] = None,
    non_interactive: bool = False,
    ragebait_levels: Optional[List[int]] = None,
    template_ids: Optional[List[int]] = None,
    positive_keywords: Optional[List[str]] = None,
    negative_keywords: Optional[List[str]] = None,
    auto_generate_keywords: bool = True,
    enhanced_competitor: bool = False
) -> bool:
    """
    Run the main generation workflow.
    
    Args:
        campaign_folder: Path to campaign folder
        topic: Topic for quote generation and competitor analysis
        quote_count: Number of hooks to generate
        offer_type: Type of offer
        offers: List of specific offers (for service type)
        non_interactive: Whether to run without user prompts
        ragebait_levels: List of ragebait intensity levels 0-10 (default [3]). Hooks divided among levels.
        template_ids: List of specific template IDs to use
        positive_keywords: List of positive/required keywords (max 2)
        negative_keywords: List of negative/exclusion keywords (max 5)
        auto_generate_keywords: Whether to auto-generate keywords with Claude Sonnet
        enhanced_competitor: Whether to use enhanced competitor analysis
        
    Returns:
        True if successful
    """
    # Initialize ragebait levels
    ragebait_levels = ragebait_levels or [3]
    # =========================================================================
    # STEP 1 & 2: Competitor Analysis & Quote Scraping (Parallel)
    # =========================================================================
    print_step(1, "COMPETITOR ANALYSIS & QUOTE SCRAPING")
    
    # Start quote scraping in background
    print(f"[INFO] Starting parallel tasks: Competitor Analysis and Quote Scraping...")
    
    # We use to_thread because these functions are currently synchronous
    # and contain blocking network calls or user interaction.
    # Note: Quote scraping is non-interactive, but competitor analysis IS interactive.
    # We run them in parallel to save time on the non-interactive parts.
    
    quote_task = asyncio.to_thread(
        scrape_quotes,
        topic=topic,
        num_quotes=quote_count,
        offer_type=offer_type,
        offers=offers
    )
    
    # Step 1: Competitor Analysis (Interactive)
    # This remains mostly sequential because of user prompts, but runs alongside quote generation.
    current_topic = topic
    extra_keywords = []
    overused_patterns = []
    phrases_to_avoid = []
    competitor_data = {}
    saved_positive_keywords = positive_keywords  # Store keywords to reuse on option 4
    saved_negative_keywords = negative_keywords
    
    while True:
        # Pass the exact quote_count as the target for competitor analysis
        # Reuse saved keywords if available (for option 4: retry with same keywords)
        if enhanced_competitor:
            print("[INFO] Using Enhanced Competitor Analysis mode")
            print("       - Analyzing personas, desires, and mechanisms")
            print("       - Identifying differentiation opportunities")
            competitor_data = get_enhanced_competitor_analysis(
                topic=current_topic, 
                offer_type=offer_type, 
                extra_keywords=extra_keywords,
                extract_media=True,
                limit=quote_count,
                offers=offers,
                non_interactive=non_interactive,
                positive_keywords=saved_positive_keywords,
                negative_keywords=saved_negative_keywords,
                auto_generate_keywords=auto_generate_keywords
            )
        else:
            competitor_data = get_competitor_analysis(
                topic=current_topic, 
                offer_type=offer_type, 
                extra_keywords=extra_keywords,
                extract_media=True,
                limit=quote_count,
                offers=offers,
                non_interactive=non_interactive,
                positive_keywords=saved_positive_keywords,
                negative_keywords=saved_negative_keywords,
                auto_generate_keywords=auto_generate_keywords
            )
        
        # Save the keywords from this run for potential reuse
        # (Keywords are included in competitor_data from the scraper)
        
        hooks_extracted = competitor_data.get('hooks_extracted', 0)
        # Get breakdown from new data structure
        breakdown = competitor_data.get('breakdown', {})
        proven_ads = breakdown.get('proven', 0)
        fresh_ads = breakdown.get('fresh', 0)
        keywords_used = competitor_data.get('relevance_keywords', [])
        insights = competitor_data.get('insights', {})
        
        if hooks_extracted > 0:
            bot_logger.info(f"Analyzed {proven_ads} proven + {fresh_ads} fresh ads, extracted {hooks_extracted} hooks")
            
            # Display hooks/offers found
            hooks = competitor_data.get('hooks', [])
            if hooks:
                print(f"\n{'-' * 60}")
                print(f"  HOOKS/OFFERS FOUND ({len(hooks)} total)")
                print(f"{'-' * 60}")
                for i, hook in enumerate(hooks[:20], 1):  # Show first 20 hooks
                    page_name = hook.get('page_name', 'Unknown')
                    hook_text = hook.get('image_hook') or hook.get('hook_text', 'N/A')
                    # Truncate long hooks for display
                    if len(hook_text) > 150:
                        hook_text = hook_text[:150] + "..."
                    safe_print(f"\n  {i}. [{page_name}]")
                    safe_print(f"     \"{hook_text}\"")
                if len(hooks) > 20:
                    print(f"\n  ... and {len(hooks) - 20} more hooks")
                print(f"\n{'-' * 60}\n")
            
            # ... (UI output for competitor analysis results) ...
            overused_patterns = competitor_data.get('overused_patterns', [])
            phrases_to_avoid = competitor_data.get('phrases_to_avoid', [])
            
            if non_interactive:
                choice = "1"
            else:
                print("\nOptions:")
                print("  1. Proceed - create UNIQUE hooks that DIFFERENTIATE from these")
                print("  2. Add extra keywords to filter")
                print("  3. Search again with different topic")
                print("  4. Search again with same keywords")
                print("  5. Skip competitor analysis")
                choice = get_user_input("Select an option (1-5)", "1")
            
            if choice == "1":
                break
            elif choice == "2":
                kws = get_user_input("Enter keywords separated by commas")
                extra_keywords.extend([k.strip() for k in kws.split(',')])
                continue
            elif choice == "3":
                current_topic = get_user_input("Enter new search topic")
                extra_keywords = []
                continue
            elif choice == "4":
                # Retry with same keywords
                continue
            else:
                break
        else:
            if non_interactive:
                choice = "3"
            else:
                print("Options:")
                print("  1. Add extra (broader) keywords")
                print("  2. Try a different search topic")
                print("  3. Skip competitor analysis")
                choice = get_user_input("Select an option (1-3)", "1")
            
            if choice == "1":
                kws = get_user_input("Enter extra keywords (comma separated)")
                extra_keywords.extend([k.strip() for k in kws.split(',')])
                continue
            elif choice == "2":
                current_topic = get_user_input("Enter new search topic")
                extra_keywords = []
                continue
            else:
                break

    # Wait for quote scraping to finish if it hasn't already
    print(f"\n[INFO] Waiting for quote scraping to complete...")
    quotes = await quote_task
    
    if not quotes:
        print("[ERROR] Failed to generate quotes")
        return False
    
    print(f"[OK] Generated {len(quotes)} quotes")
    
    # =========================================================================
    # STEP 3: Headline Generation
    # =========================================================================
    print_step(3, "HEADLINE GENERATION")
    
    # Load performance history for reinforcement learning
    perf_history = get_type_specific_history(offer_type)
    failure_analysis = ""
    if perf_history:
        top_ads = perf_history.get('top_ads', [])
        bottom_ads = perf_history.get('bottom_ads', [])
        print(f"[INFO] Applied reinforcement learning from {len(top_ads)} winning ads")
        
        # Run failure analysis if there are losers
        if bottom_ads:
            print(f"[INFO] Analyzing {len(bottom_ads)} failed ads for negative reinforcement...")
            failure_analysis = analyze_failures(perf_history)
            if failure_analysis:
                print(f"[OK] Extracted negative patterns to avoid")
        
        # Show GPT summary if available
        if top_ads:
            gpt_ads = [ad for ad in top_ads if ad.get('gpt', 0) > 0]
            if gpt_ads:
                print(f"[INFO] Found {len(gpt_ads)} ads with positive GPT (profit per transaction)")
                # Show top 3 by GPT
                sorted_by_gpt = sorted(gpt_ads, key=lambda x: x.get('gpt', 0), reverse=True)[:3]
                print(f"[TOP GPT] Best profit per transaction:")
                for ad in sorted_by_gpt:
                    gpt = ad.get('gpt', 0)
                    aov = ad.get('aov', 0)
                    cpa = ad.get('cpa', 0)
                    name = ad.get('name', 'Unknown')[:50]
                    print(f"  - {name}: GPT=${gpt:.2f} (AOV=${aov:.2f} - CPA=${cpa:.2f})")
    
    print(f"[INFO] Generating {len(quotes)} headlines using Claude...")
    if failure_analysis:
        print("[INFO] Applying negative reinforcement (avoiding failed patterns)...")
    print("[INFO] Applying competitor semantic hook differentiation...")
    
    # Extract semantic hooks from competitor data for differentiation
    semantic_hooks = []
    if competitor_data and competitor_data.get('hooks'):
        semantic_hooks = [h.get('semantic_hook') for h in competitor_data.get('hooks', []) if h.get('semantic_hook')]
        if semantic_hooks:
            print(f"[INFO] Found {len(semantic_hooks)} competitor semantic hooks to differentiate from")
            # Show sample semantic hooks
            print("[PREVIEW] Sample competitor semantic hooks:")
            for i, sh in enumerate(semantic_hooks[:3], 1):
                safe_print(f"  {i}. \"{sh[:100]}\"")
    
    # Calculate offer distribution if offers exist
    offer_distribution = None
    if offers:
        from hook_generator.offer_manager import distribute_hooks_across_offers
        offer_distribution = distribute_hooks_across_offers(quote_count, offers)
        print(f"[INFO] Offer distribution for headlines:")
        for offer, count in offer_distribution:
            print(f"  - {offer}: {count} headlines")
    
    # Calculate count per ragebait level
    num_ragebait_levels = len(ragebait_levels)
    if num_ragebait_levels == 0:
        print("[ERROR] No ragebait levels provided, using default level 3")
        ragebait_levels = [3]
        num_ragebait_levels = 1
    count_per_level = quote_count // num_ragebait_levels
    remainder = quote_count % num_ragebait_levels
    
    if num_ragebait_levels > 1:
        print(f"\n[INFO] Multi-ragebait mode: {num_ragebait_levels} levels")
        print(f"[INFO] Base count per level: {count_per_level} (remainder: {remainder})")
    
    # Generate hooks for each ragebait level
    all_headlines = []
    all_proven_headlines = []
    
    for level_idx, ragebait_level in enumerate(ragebait_levels):
        # Distribute remainder to first levels
        level_count = count_per_level + (1 if level_idx < remainder else 0)
        
        if level_count == 0:
            continue
        
        if num_ragebait_levels > 1:
            print(f"\n{'=' * 60}")
            print(f"  RAGEBAIT LEVEL {ragebait_level} ({level_count} hooks)")
            print(f"{'=' * 60}\n")
        
        # Calculate offer distribution for this level's count
        level_offer_distribution = None
        if offers:
            level_offer_distribution = distribute_hooks_across_offers(level_count, offers)
        
        # Generate unique Andromeda-style hooks using offers directly (no quotes needed)
        level_headlines = await asyncio.to_thread(
            generate_headlines,
            num_hooks=level_count,
            offers=offers,
            offer_type=offer_type,
            offer_distribution=level_offer_distribution,
            performance_history=perf_history,
            semantic_hooks=semantic_hooks,
            failure_analysis=failure_analysis,
            ragebait_level=ragebait_level,
            competitor_data=competitor_data  # Pass competitor data for enhanced gap analysis
        )
        
        if not level_headlines:
            print(f"[ERROR] Failed to generate headlines for ragebait level {ragebait_level}")
            continue
        
        # Tag each headline with its ragebait level
        for h in level_headlines:
            h['ragebait_level'] = ragebait_level
        
        all_headlines.extend(level_headlines)
        print(f"[OK] Generated {len(level_headlines)} headlines at ragebait level {ragebait_level}")
        
        # Preview some headlines
        print(f"\n[PREVIEW] Sample headlines (ragebait {ragebait_level}):")
        for i, h in enumerate(level_headlines[:3], 1):
            safe_print(f"  {i}. {h.get('headline', 'N/A')}")
        if len(level_headlines) > 3:
            print(f"  ... and {len(level_headlines) - 3} more")
        
        # =========================================================================
        # Proven Hooks Generation for this ragebait level
        # =========================================================================
        if hooks_extracted > 0 and competitor_data:
            print(f"\n[INFO] Generating {level_count} proven fusion hooks at ragebait level {ragebait_level}...")
            
            level_proven_headlines = await asyncio.to_thread(
                generate_proven_hooks,
                competitor_data=competitor_data,
                num_hooks=level_count,
                offers=offers,
                offer_type=offer_type,
                offer_distribution=level_offer_distribution,
                failure_analysis=failure_analysis,
                ragebait_level=ragebait_level
            )
            
            if level_proven_headlines:
                # Tag each proven headline with its ragebait level
                for h in level_proven_headlines:
                    h['ragebait_level'] = ragebait_level
                
                all_proven_headlines.extend(level_proven_headlines)
                print(f"[OK] Generated {len(level_proven_headlines)} proven hooks at ragebait level {ragebait_level}")
                
                # Preview some proven headlines
                print(f"\n[PREVIEW] Sample proven headlines (ragebait {ragebait_level}):")
                for i, h in enumerate(level_proven_headlines[:3], 1):
                    safe_print(f"  {i}. {h.get('headline', 'N/A')} [{h.get('proven_angle', 'N/A')}]")
                if len(level_proven_headlines) > 3:
                    print(f"  ... and {len(level_proven_headlines) - 3} more")
            else:
                print(f"[WARNING] Failed to generate proven hooks at ragebait level {ragebait_level}")
    
    # Use combined results
    headlines = all_headlines
    proven_headlines = all_proven_headlines
    
    if not headlines:
        print("[ERROR] Failed to generate any headlines")
        return False
    
    # Re-index all hooks sequentially
    for i, h in enumerate(headlines, 1):
        h['hook_index'] = i
    for i, h in enumerate(proven_headlines, 1):
        h['hook_index'] = i
    
    # Summary
    print(f"\n{'=' * 60}")
    print(f"  GENERATION SUMMARY")
    print(f"{'=' * 60}")
    print(f"[OK] Total unique headlines: {len(headlines)}")
    print(f"[OK] Total proven headlines: {len(proven_headlines)}")
    if num_ragebait_levels > 1:
        for level in ragebait_levels:
            unique_at_level = len([h for h in headlines if h.get('ragebait_level') == level])
            proven_at_level = len([h for h in proven_headlines if h.get('ragebait_level') == level])
            print(f"  - Ragebait {level}: {unique_at_level} unique, {proven_at_level} proven")
    
    # =========================================================================
    # STEP 4: Image Generation
    # =========================================================================
    print_step(4, "IMAGE GENERATION")
    
    images_dir = campaign_folder / "images"
    
    # Generate images for unique hooks
    print(f"[INFO] Generating {len(headlines)} unique hook images...")
    # Prepare metadata for unique hooks
    for h in headlines:
        h['type'] = 'unique'
    
    results = await asyncio.to_thread(
        batch_generate_images,
        headlines=headlines,
        output_dir=images_dir,
        create_psd=False,
        template_ids=template_ids
    )
    
    success_count = sum(1 for r in results if r['success'])
    print(f"\n[OK] Generated {success_count}/{len(headlines)} unique hook images")
    
    # Generate images for proven hooks (if any)
    proven_success_count = 0
    if proven_headlines:
        print(f"\n[INFO] Generating {len(proven_headlines)} proven hook images...")
        # Prepare metadata for proven hooks
        for h in proven_headlines:
            h['type'] = 'proven'
        
        proven_results = await asyncio.to_thread(
            batch_generate_images,
            headlines=proven_headlines,
            output_dir=images_dir,
            create_psd=False,
            template_ids=template_ids
        )
        
        proven_success_count = sum(1 for r in proven_results if r['success'])
        print(f"[OK] Generated {proven_success_count}/{len(proven_headlines)} proven hook images")
    
    update_campaign_status(campaign_folder, "images_complete", {
        'images_generated': success_count,
        'images_failed': len(headlines) - success_count,
        'proven_images_generated': proven_success_count if proven_headlines else 0,
        'proven_images_failed': len(proven_headlines) - proven_success_count if proven_headlines else 0
    })
    
    # =========================================================================
    # FINAL: Build and Save Comprehensive Metadata
    # =========================================================================
    # Extract campaign name from folder (format: {name}_{timestamp})
    folder_name = campaign_folder.name
    # Safely extract campaign name, handling various folder name formats
    if folder_name and '_' in folder_name:
        campaign_name_parts = folder_name.rsplit('_', 2)  # Remove timestamp parts
        campaign_name = campaign_name_parts[0] if len(campaign_name_parts) >= 3 else folder_name
    else:
        campaign_name = folder_name if folder_name else "unknown_campaign"
    
    # Build generation config for metadata
    generation_config = {
        'ragebait_levels': ragebait_levels,
        'template_ids': template_ids or [],
        'positive_keywords': positive_keywords or [],
        'negative_keywords': negative_keywords or [],
        'auto_generate_keywords': auto_generate_keywords,
        'count_requested': quote_count
    }
    
    # Build and save comprehensive metadata with all research and hook data
    analysis_type = "enhanced" if enhanced_competitor else "basic"
    comprehensive_metadata = build_comprehensive_metadata(
        campaign_name=campaign_name,
        offer_type=offer_type,
        topic=topic,
        competitor_data=competitor_data,
        trend_data=None,  # Main workflow doesn't use Perplexity directly (advanced mode does)
        unique_hooks=headlines,
        proven_hooks=proven_headlines if proven_headlines else [],
        generation_config=generation_config,
        offers=offers,
        analysis_type=analysis_type
    )
    
    save_comprehensive_metadata(campaign_folder, comprehensive_metadata)
    
    print(f"\n[OK] Workflow complete! Results saved to: {campaign_folder}")
    return True


async def main():
    """Main entry point."""
    bot_logger.info("Starting Ad Hook Generation Bot...")
    
    parser = argparse.ArgumentParser(description="Ad Hook Generation Bot")
    
    # Basic options
    parser.add_argument("--name", type=str, help="Campaign name")
    parser.add_argument("--topic", type=str, help="Topic/niche for competitor analysis and quotes")
    parser.add_argument("--count", type=int, help="Number of hooks to generate")
    parser.add_argument("--unique-offers", type=int, metavar="N", 
                        help="Number of unique offers to find from Facebook. "
                             "If not specified, defaults to --count. "
                             "If specified, hooks are distributed evenly across offers "
                             "(e.g., --count 1000 --unique-offers 100 = 10 hooks per offer)")
    parser.add_argument("--type", type=str, choices=["service", "ecom"], help="Offer type")
    parser.add_argument("--ragebait", type=str, metavar="LEVELS", help="Comma-separated ragebait levels 0-10 (e.g., '10,3' or '10'). Hooks are divided among levels.")
    parser.add_argument("--templates", type=str, help="Comma-separated list of template IDs to use (e.g. 1,4). If provided, each hook will be generated for EACH template.")
    parser.add_argument("--offers", type=str, help="Comma-separated list of offers (for service type). Note: In PowerShell, escape $ with backtick or use single quotes: 'for $27 get...'")
    parser.add_argument("--non-interactive", action="store_true", help="Run without user prompts")
    parser.add_argument("--positive-keywords", "-p", type=str, help="Comma-separated positive/required keywords (max 2)")
    parser.add_argument("--negative-keywords", "-n", type=str, help="Comma-separated negative/exclusion keywords (max 5)")
    parser.add_argument("--no-auto-keywords", action="store_true", help="Disable automatic keyword generation with Claude")
    parser.add_argument("--no-offer-filters", action="store_true", help="Skip generating and using filters for offers (no keyword filtering)")
    parser.add_argument("--max-ads", type=int, metavar="N", help="Maximum number of ads to scrape from Facebook Ad Library (controls scroll_limit, default: 30)")
    parser.add_argument("--enhanced-competitor", action="store_true", 
                        help="Use enhanced competitor analysis (persona/desire/mechanism gap analysis)")
    
    # Advanced mode options
    parser.add_argument("--advanced", action="store_true", help="Run in advanced thinking agent mode with LangGraph")
    parser.add_argument("--chat", action="store_true", help="Run in conversational chat mode (requires --advanced)")
    parser.add_argument("--use-memory", action="store_true", help="Use Vertex AI Memory Bank for persistent learning")
    parser.add_argument("--url", type=str, help="Product URL to scrape for offers (advanced mode)")
    parser.add_argument("--export-session", type=str, help="Export hooks from a saved session ID to images")
    
    # Cache control options
    parser.add_argument("--no-cache", action="store_true", help="Disable caching (force fresh API calls)")
    parser.add_argument("--clear-cache", nargs="?", const="all", help="Clear cache (optionally specify type: competitor_analysis, ad_analysis, trend_research, product_scrape)")
    parser.add_argument("--cache-stats", action="store_true", help="Show cache statistics and exit")
    
    args = parser.parse_args()
    
    print_banner()
    
    # Handle cache control commands first (before API initialization)
    if args.cache_stats:
        from hook_generator.cache_manager import print_cache_stats
        print_cache_stats()
        sys.exit(0)
    
    if args.clear_cache:
        from hook_generator.cache_manager import clear_cache
        if args.clear_cache == "all":
            cleared = clear_cache()
            print(f"[OK] Cleared all cache files")
        else:
            cleared = clear_cache(args.clear_cache)
            print(f"[OK] Cleared {args.clear_cache} cache")
        sys.exit(0)
    
    # Override caching if --no-cache specified
    if args.no_cache:
        config.ENABLE_CACHING = False
        print("[INFO] Caching disabled for this run")
    
    # Initialize API keys
    bot_logger.info("Loading API keys...")
    api_keys.load_api_keys()
    key_status = api_keys.verify_keys()
    
    bot_logger.info("API Status:")
    for key, available in key_status.items():
        status = "[OK]" if available else "[MISSING]"
        bot_logger.info(f"  {status} {key}")
    
    if not key_status.get('OPENAI_API_KEY'):
        bot_logger.error("OPENAI_API_KEY is required for quote generation")
        print("[INFO] Add OPENAI_API_KEY=your-key to api_keys.txt")
        sys.exit(1)
    
    if not key_status.get('ANTHROPIC_API_KEY'):
        bot_logger.error("ANTHROPIC_API_KEY is required for headline generation")
        print("[INFO] Add ANTHROPIC_API_KEY=your-key to api_keys.txt")
        sys.exit(1)
    
    # Initialize clients
    api_keys.initialize_clients()
    
    # Handle advanced mode
    if args.advanced:
        # Export session if requested
        if args.export_session:
            from hook_generator.advanced.advanced_workflow import export_session_hooks
            template_ids = None
            if args.templates:
                try:
                    template_ids = [int(tid.strip()) for tid in args.templates.split(",")]
                except ValueError:
                    print(f"[ERROR] Invalid template IDs: {args.templates}")
                    sys.exit(1)
            
            result = await export_session_hooks(args.export_session, template_ids if template_ids else None)
            if result.get('success'):
                print(f"[OK] Exported {result.get('images_generated')} images to {result.get('output_dir')}")
            else:
                print(f"[ERROR] Export failed: {result.get('error')}")
            sys.exit(0)
        
        # Conversational chat mode
        if args.chat:
            from hook_generator.advanced.conversational_mode import run_conversational_mode
            run_conversational_mode(use_memory=args.use_memory)
            sys.exit(0)
        
        # Advanced workflow mode
        if not args.name:
            args.name = get_user_input("Enter campaign name", "my_campaign") if not args.non_interactive else "advanced_campaign"
        
        if not args.topic:
            args.topic = get_user_input("Enter topic/niche", "house painting") if not args.non_interactive else "general"
        
        if not args.count:
            args.count = int(get_user_input("Number of hooks to generate", "20")) if not args.non_interactive else 20
        
        # Parse ragebait levels (supports comma-separated, e.g., "10,3,5")
        ragebait_levels = [3]  # Default
        if args.ragebait:
            try:
                ragebait_levels = [int(r.strip()) for r in args.ragebait.split(",")]
                ragebait_levels = [max(0, min(10, r)) for r in ragebait_levels]  # Clamp 0-10
                if len(ragebait_levels) > 1:
                    print(f"[INFO] Multiple ragebait levels: {ragebait_levels}")
                    print(f"[INFO] Hooks will be divided among {len(ragebait_levels)} ragebait levels")
            except ValueError:
                print(f"[ERROR] Invalid ragebait levels: {args.ragebait}. Use comma-separated integers 0-10.")
                sys.exit(1)
        
        template_ids = None
        if args.templates:
            try:
                template_ids = [int(tid.strip()) for tid in args.templates.split(",")]
            except ValueError:
                print(f"[ERROR] Invalid template IDs: {args.templates}")
                sys.exit(1)
        
        cli_offers = None
        if args.offers:
            cli_offers = [o.strip() for o in args.offers.split(",")]
            # Log parsed offers for debugging
            print(f"[INFO] Parsed {len(cli_offers)} offer(s) from --offers:")
            for i, offer in enumerate(cli_offers, 1):
                print(f"  {i}. \"{offer}\"")
                # Warn if offer seems incomplete (double spaces might indicate missing content)
                if '  ' in offer or len(offer) < 10:
                    print(f"     [WARNING] Offer {i} may be incomplete or missing content")
                    print(f"     [TIP] In PowerShell, use single quotes or escape $: 'for $27 get...' or \"for `$27 get...\"")
        
        from hook_generator.advanced.advanced_workflow import run_advanced_workflow
        
        # Parse keywords if provided
        positive_keywords = None
        negative_keywords = None
        auto_generate_keywords = not args.no_auto_keywords
        
        if args.positive_keywords:
            positive_keywords = [k.strip().lower() for k in args.positive_keywords.split(",")]
            if len(positive_keywords) > 2:
                print(f"[WARNING] Maximum 2 positive keywords allowed, truncating to first 2")
                positive_keywords = positive_keywords[:2]
            print(f"[INFO] Positive keywords: {', '.join(positive_keywords)}")
        
        if args.negative_keywords:
            negative_keywords = [k.strip().lower() for k in args.negative_keywords.split(",")]
            if len(negative_keywords) > 5:
                print(f"[WARNING] Maximum 5 negative keywords allowed, truncating to first 5")
                negative_keywords = negative_keywords[:5]
            print(f"[INFO] Negative keywords: {', '.join(negative_keywords)}")
        
        if args.no_auto_keywords:
            print(f"[INFO] Automatic keyword generation disabled")
        
        if args.no_offer_filters:
            print(f"[INFO] Offer filters disabled - no keyword filtering will be applied")
            # Clear keywords when filters are disabled
            positive_keywords = []
            negative_keywords = []
            auto_generate_keywords = False
        
        max_ads = args.max_ads if args.max_ads else 30  # Default to 30 if not specified
        if args.max_ads:
            print(f"[INFO] Maximum ads to scrape: {max_ads}")
        
        # Calculate unique offer count (defaults to count if not specified)
        unique_offer_count = getattr(args, 'unique_offers', None) or args.count
        if unique_offer_count != args.count:
            ads_per_offer = args.count // unique_offer_count
            print(f"[INFO] Unique offer mode: finding {unique_offer_count} unique offers")
            print(f"[INFO] Will generate {args.count} proven hooks ({ads_per_offer} per unique offer)")
        
        result = await run_advanced_workflow(
            campaign_name=args.name,
            topic=args.topic,
            count=args.count,
            unique_offer_count=unique_offer_count,
            offers=cli_offers,
            offer_type=args.type or "service",
            ragebait_levels=ragebait_levels,
            template_ids=template_ids,
            use_memory=args.use_memory,
            url=args.url,
            non_interactive=args.non_interactive,
            positive_keywords=positive_keywords,
            negative_keywords=negative_keywords,
            auto_generate_keywords=auto_generate_keywords,
            skip_offer_filters=args.no_offer_filters,
            max_ads=max_ads
        )
        
        if result.get('success'):
            bot_logger.info("Advanced workflow completed successfully!")
        else:
            bot_logger.error(f"Advanced workflow failed: {result.get('error')}")
            sys.exit(1)
        
        sys.exit(0)
    
    # Sync performance history from Meta (RL Feedback Loop)
    try:
        print("\n[INFO] Initializing RL Feedback Loop...")
        await asyncio.to_thread(sync_performance_history)
    except Exception as e:
        print(f"[WARNING] Performance sync failed: {e}")
        print("[INFO] Continuing with local history only.")
    
    # Get inputs from CLI or prompts
    
    # 1. Campaign name
    if args.name:
        campaign_name = args.name
    else:
        print()
        campaign_name = get_user_input("Enter campaign name", "my_campaign")
    
    # 4. Offer type
    if args.type:
        offer_type = args.type
    else:
        print()
        offer_type = get_offer_type()
    
    # 5. Quote count
    if args.count:
        quote_count = args.count
    else:
        print()
        quote_count = get_quote_count()
    
    # 6. Ragebait levels (supports comma-separated, e.g., "10,3,5")
    ragebait_levels = [3]  # Default
    if args.ragebait:
        try:
            ragebait_levels = [int(r.strip()) for r in args.ragebait.split(",")]
            ragebait_levels = [max(0, min(10, r)) for r in ragebait_levels]  # Clamp 0-10
            if len(ragebait_levels) > 1:
                print(f"[INFO] Multiple ragebait levels: {ragebait_levels}")
                print(f"[INFO] Hooks will be divided among {len(ragebait_levels)} ragebait levels")
        except ValueError:
            print(f"[ERROR] Invalid ragebait levels: {args.ragebait}. Use comma-separated integers 0-10.")
            sys.exit(1)
    elif args.non_interactive:
        ragebait_levels = [3]  # Default to level 3 in non-interactive mode
        print(f"[INFO] Using default ragebait level: {ragebait_levels[0]}")
    else:
        ragebait_levels = [get_ragebait_level()]
    
    # 7. Template selection
    template_ids = None
    if args.templates:
        try:
            template_ids = [int(tid.strip()) for tid in args.templates.split(",")]
            print(f"[INFO] Using specific templates: {template_ids}")
        except ValueError:
            print(f"[ERROR] Invalid template IDs provided: {args.templates}. Use comma-separated numbers.")
            sys.exit(1)
    
    # 8. Offers (CLI only)
    cli_offers = None
    if args.offers:
        cli_offers = [o.strip() for o in args.offers.split(",")]
        # Log parsed offers for debugging
        print(f"[INFO] Parsed {len(cli_offers)} offer(s) from --offers:")
        for i, offer in enumerate(cli_offers, 1):
            print(f"  {i}. \"{offer}\"")
            # Warn if offer seems incomplete (double spaces might indicate missing content)
            if '  ' in offer or len(offer) < 10:
                print(f"     [WARNING] Offer {i} may be incomplete or missing content")
                print(f"     [TIP] In PowerShell, use single quotes or escape $: 'for $27 get...' or \"for `$27 get...\"")
    
    # 9. Topic (CLI only)
    cli_topic = args.topic
    
    # 10. Parse keyword arguments
    positive_keywords = None
    negative_keywords = None
    auto_generate_keywords = not args.no_auto_keywords
    
    if args.positive_keywords:
        positive_keywords = [k.strip().lower() for k in args.positive_keywords.split(",")]
        # Enforce max 2 limit
        if len(positive_keywords) > 2:
            print(f"[WARNING] Maximum 2 positive keywords allowed, truncating to first 2")
            positive_keywords = positive_keywords[:2]
        print(f"[INFO] Positive keywords: {', '.join(positive_keywords)}")
    
    if args.negative_keywords:
        negative_keywords = [k.strip().lower() for k in args.negative_keywords.split(",")]
        # Enforce max 5 limit
        if len(negative_keywords) > 5:
            print(f"[WARNING] Maximum 5 negative keywords allowed, truncating to first 5")
            negative_keywords = negative_keywords[:5]
        print(f"[INFO] Negative keywords: {', '.join(negative_keywords)}")
    
    if args.no_auto_keywords:
        print(f"[INFO] Automatic keyword generation disabled")
    
    # Create campaign folder
    print(f"\n[INFO] Creating campaign folder...")
    campaign_folder = create_campaign_folder(campaign_name, offer_type)
    print(f"[OK] Created: {campaign_folder}")
    
    # Run appropriate workflow
    if offer_type == config.OFFER_TYPE_SERVICE:
        success = await run_service_workflow(
            campaign_folder, 
            quote_count, 
            cli_offers=cli_offers, 
            cli_topic=cli_topic,
            non_interactive=args.non_interactive,
            ragebait_levels=ragebait_levels,
            template_ids=template_ids,
            positive_keywords=positive_keywords,
            negative_keywords=negative_keywords,
            auto_generate_keywords=auto_generate_keywords,
            enhanced_competitor=args.enhanced_competitor
        )
    else:
        success = await run_ecom_workflow(
            campaign_folder, 
            quote_count, 
            cli_topic=cli_topic if cli_topic is not None else None,
            non_interactive=args.non_interactive,
            ragebait_levels=ragebait_levels,
            template_ids=template_ids if template_ids is not None else None,
            positive_keywords=positive_keywords if positive_keywords is not None else None,
            negative_keywords=negative_keywords if negative_keywords is not None else None,
            auto_generate_keywords=auto_generate_keywords,
            enhanced_competitor=args.enhanced_competitor
        )
    
    if success:
        bot_logger.info("Workflow completed successfully!")
    else:
        bot_logger.error("Workflow encountered errors")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

