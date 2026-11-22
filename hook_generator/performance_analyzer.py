"""
Performance analyzer for reinforcement learning.
Pulls Meta insights, calculates net profit (Reward), and segments by offer type.
"""

import json
import requests
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from . import config
from . import api_keys
from .rate_limiter import openai_limiter, anthropic_limiter, run_multithreaded, meta_limiter

def load_campaign_registry() -> Dict[str, Any]:
    """
    Load the registry of bot-created campaigns.
    """
    if not config.CAMPAIGN_REGISTRY_FILE.exists():
        return {"campaigns": []}
    
    try:
        with open(config.CAMPAIGN_REGISTRY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARNING] Failed to load campaign registry: {e}")
        return {"campaigns": []}

def register_campaign(campaign_name: str, offer_type: str, campaign_folder: Path) -> bool:
    """
    Register a bot-created campaign in the registry.
    
    Args:
        campaign_name: Name of the campaign
        offer_type: Type of offer ('service' or 'ecom')
        campaign_folder: Path to campaign folder
        
    Returns:
        True if successful
    """
    try:
        registry = load_campaign_registry()
        
        # Add campaign to registry
        campaign_entry = {
            "campaign_name": campaign_name,
            "offer_type": offer_type,
            "folder_path": str(campaign_folder),
            "registered_at": datetime.now().isoformat()
        }
        
        # Check if already registered
        existing = [c for c in registry.get("campaigns", []) if c.get("campaign_name") == campaign_name]
        if not existing:
            registry.setdefault("campaigns", []).append(campaign_entry)
            
            # Save registry
            config.PERFORMANCE_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
            with open(config.CAMPAIGN_REGISTRY_FILE, 'w', encoding='utf-8') as f:
                json.dump(registry, f, indent=2)
            
            print(f"[OK] Registered campaign: {campaign_name}")
        
        return True
    except Exception as e:
        print(f"[ERROR] Failed to register campaign: {e}")
        return False

def is_bot_created_campaign(ad_name: str, campaign_name: Optional[str] = None) -> bool:
    """
    Check if an ad belongs to a bot-created campaign.
    
    Args:
        ad_name: Name of the ad from Meta
        campaign_name: Campaign name from Meta API (preferred for matching)
        
    Returns:
        True if the ad belongs to a bot-created campaign
    """
    registry = load_campaign_registry()
    registered_campaigns = registry.get("campaigns", [])
    
    if not registered_campaigns:
        return False
    
    # Get list of registered campaign names (normalized)
    registered_names = []
    for c in registered_campaigns:
        reg_name = c.get("campaign_name", "")
        if reg_name:
            # Normalize: remove special chars, lowercase
            normalized = "".join(ch if ch.isalnum() or ch in ('-', '_', ' ') else '_' for ch in reg_name.lower())
            registered_names.append(normalized)
            # Also add original for exact match
            registered_names.append(reg_name.lower())
    
    # Primary check: match by campaign_name (most reliable)
    if campaign_name:
        campaign_name_lower = campaign_name.lower()
        campaign_name_normalized = "".join(ch if ch.isalnum() or ch in ('-', '_', ' ') else '_' for ch in campaign_name_lower)
        
        for reg_name in registered_names:
            if reg_name and (reg_name in campaign_name_lower or campaign_name_normalized in reg_name or reg_name in campaign_name_normalized):
                return True
    
    # Fallback: check if ad name contains any registered campaign name
    ad_name_lower = ad_name.lower()
    for reg_name in registered_names:
        if reg_name and len(reg_name) > 3 and reg_name in ad_name_lower:
            return True
    
    return False

def fetch_meta_insights(lookback_days: int = 30) -> List[Dict[str, Any]]:
    """
    Fetch ad-level insights from Meta for the specified lookback period.
    """
    if not api_keys.META_ACCESS_TOKEN:
        print("[WARNING] META_ACCESS_TOKEN not configured, cannot fetch performance data")
        return []

    # Get ad account ID from keys or config if available
    # For now, we'll try to find active ads from the 'me/adaccounts' endpoint
    base_url = f"https://graph.facebook.com/{config.FACEBOOK_GRAPH_API_VERSION}"
    
    try:
        # 1. Get Ad Account ID
        acc_url = f"{base_url}/me/adaccounts"
        acc_params = {'access_token': api_keys.META_ACCESS_TOKEN}
        acc_response = requests.get(acc_url, params=acc_params, timeout=20)
        
        if acc_response.status_code != 200:
            print(f"[ERROR] Failed to fetch ad accounts: {acc_response.text}")
            return []
            
        accounts = acc_response.json().get('data', [])
        if not accounts:
            print("[INFO] No ad accounts found for this token")
            return []
            
        # Use the first account for now
        ad_account_id = accounts[0]['id']
        
        # 2. Fetch Insights
        # We want: spend, conversions, and conversion value
        insights_url = f"{base_url}/{ad_account_id}/insights"
        
        # Calculate date range
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=lookback_days)).strftime('%Y-%m-%d')
        
        insights_params = {
            'level': 'ad',
            'fields': 'ad_id,ad_name,campaign_name,spend,actions,action_values',
            'time_range': json.dumps({'since': start_date, 'until': end_date}),
            'access_token': api_keys.META_ACCESS_TOKEN,
            'limit': 500
        }
        # Note: 'actions' field includes conversion counts like purchase, add_to_cart, etc.
        
        meta_limiter.wait(1, "Meta performance insights") # Read call (1 point)
        response = requests.get(insights_url, params=insights_params, timeout=30)
        
        # Update limiter from headers
        meta_limiter.update_from_headers(dict(response.headers), "Meta performance insights")
        
        if response.status_code != 200:
            print(f"[ERROR] Failed to fetch Meta insights: {response.text}")
            return []
        
        all_insights = response.json().get('data', [])
        
        # Filter to only bot-created campaigns
        bot_insights = []
        registry = load_campaign_registry()
        registered_campaigns = [c.get("campaign_name", "").lower() for c in registry.get("campaigns", [])]
        
        for insight in all_insights:
            ad_name = insight.get('ad_name', '')
            campaign_name = insight.get('campaign_name', '')
            
            # Check if this ad belongs to a registered campaign
            if is_bot_created_campaign(ad_name, campaign_name):
                bot_insights.append(insight)
        
        if all_insights and not bot_insights:
            print(f"[INFO] Found {len(all_insights)} ads, but none match bot-created campaigns in registry")
            print(f"[INFO] Registered campaigns: {', '.join(registered_campaigns) if registered_campaigns else 'None'}")
        elif bot_insights:
            print(f"[INFO] Filtered to {len(bot_insights)} ads from bot-created campaigns (out of {len(all_insights)} total)")
            
        return bot_insights
        
    except Exception as e:
        print(f"[ERROR] Error fetching performance data: {e}")
        return []

def calculate_reward(spend: float, revenue: float) -> float:
    """
    Calculate the RL reward (Net Profit).
    Logic: Profit = Revenue - Spend
    """
    return revenue - spend

def calculate_aov(revenue: float, conversions: int) -> float:
    """
    Calculate Average Order Value (AOV).
    Logic: AOV = Revenue / Number of Conversions
    
    Args:
        revenue: Total revenue from conversions
        conversions: Number of conversions/purchases
        
    Returns:
        AOV, or 0.0 if no conversions
    """
    if conversions == 0:
        return 0.0
    return revenue / conversions

def calculate_cpa(spend: float, conversions: int) -> float:
    """
    Calculate Cost Per Acquisition (CPA).
    Logic: CPA = Spend / Number of Conversions
    
    Args:
        spend: Total ad spend
        conversions: Number of conversions/purchases
        
    Returns:
        CPA, or 0.0 if no conversions
    """
    if conversions == 0:
        return 0.0
    return spend / conversions

def calculate_gpt(aov: float, cpa: float) -> float:
    """
    Calculate Gross Profit Per Transaction (GPT).
    Logic: GPT = AOV - CPA
    
    This represents the actual dollar profit per transaction, not a ratio.
    As the video emphasizes: "Fractions don't pay bills, money does."
    
    Args:
        aov: Average Order Value
        cpa: Cost Per Acquisition
        
    Returns:
        GPT (can be negative if CPA > AOV)
    """
    return aov - cpa

def classify_ad_pattern(ad_name: str, body_text: str = "") -> str:
    """
    Use GPT-4o-mini to classify the ad hook pattern for reinforcement learning.
    """
    if not api_keys.OPENAI_CLIENT:
        api_keys.initialize_clients()
    
    if not api_keys.OPENAI_CLIENT:
        return "unknown"

    # Common patterns for quick check to save tokens
    ad_name_lower = ad_name.lower()
    if "?" in ad_name: return "question"
    if "vs" in ad_name_lower: return "comparison"

    prompt = config.AI_PROMPTS['performance_analysis']['pattern_classification'].format(
        ad_name=ad_name,
        body_text=body_text[:500]
    )
    
    try:
        openai_limiter.wait()
        response = api_keys.OPENAI_CLIENT.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=20,
            temperature=0
        )
        category = response.choices[0].message.content.strip().lower()
        # Clean up if GPT adds extra text
        valid_categories = ['question', 'comparison', 'fear/avoidance', 'benefit/results', 'urgency/limited', 'social_proof', 'curiosity/secret', 'timeline/speed', 'price/offer', 'direct_service']
        for cat in valid_categories:
            if cat in category:
                return cat
        return "unknown"
    except:
        return "unknown"


def process_and_segment_performance(insights: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Process raw insights, calculate rewards, and segment by offer type.
    Uses campaign registry to determine offer type from campaign metadata.
    """
    # Initialize history structure
    history = {
        config.OFFER_TYPE_SERVICE: {"patterns": {}, "top_ads": [], "all_ads_temp": []},
        config.OFFER_TYPE_ECOM: {"patterns": {}, "top_ads": [], "all_ads_temp": []}
    }
    
    registry = load_campaign_registry()
    registered_campaigns = {c.get("campaign_name", "").lower(): c for c in registry.get("campaigns", [])}
    
    def process_single_ad_performance(ad):
        ad_name = ad.get('ad_name', '')
        campaign_name = ad.get('campaign_name', '')
        spend = float(ad.get('spend', 0))
        
        # Extract conversion count from actions
        conversions = 0
        actions = ad.get('actions', [])
        for action in actions:
            action_type = action.get('action_type', '')
            if action_type in ['purchase', 'offsite_conversion.fb_pixel_purchase', 'omni_purchase', 'lead', 'offsite_conversion.fb_pixel_lead']:
                conversions += int(action.get('value', 0))
        
        # Determine offer type from registry
        offer_type = config.OFFER_TYPE_SERVICE  # Default
        campaign_name_lower = campaign_name.lower() if campaign_name else ""
        
        for reg_name, reg_data in registered_campaigns.items():
            if reg_name and reg_name in campaign_name_lower:
                offer_type = reg_data.get("offer_type", config.OFFER_TYPE_SERVICE)
                break
        
        # Extract revenue from actions/action_values
        revenue = 0.0
        action_values = ad.get('action_values', [])
        for av in action_values:
            if av.get('action_type') in ['purchase', 'offsite_conversion.fb_pixel_purchase', 'omni_purchase']:
                revenue += float(av.get('value', 0))
        
        # For service campaigns, if revenue is 0 but we have conversions (leads), apply LEAD_VALUE
        if offer_type == config.OFFER_TYPE_SERVICE and revenue == 0 and conversions > 0:
            revenue = conversions * getattr(config, 'LEAD_VALUE', 50.0)
        
        # Calculate metrics
        profit = calculate_reward(spend, revenue)
        aov = calculate_aov(revenue, conversions)
        cpa = calculate_cpa(spend, conversions)
        gpt = calculate_gpt(aov, cpa)
        
        # Enhanced pattern extraction using LLM
        # print(f"[RL] Classifying pattern for: {ad_name[:40]}...") # Too noisy for parallel
        pattern = classify_ad_pattern(ad_name, ad.get('ad_creative_bodies', [""])[0])
        
        return {
            "offer_type": offer_type,
            "pattern": pattern,
            "profit": profit,
            "spend": spend,
            "revenue": revenue,
            "conversions": conversions,
            "ad_stats": {
                "name": ad_name,
                "profit": profit,
                "roi": (revenue / spend) if spend > 0 else 0,
                "roas": (revenue / spend) if spend > 0 else 0,
                "spend": spend,
                "revenue": revenue,
                "conversions": conversions,
                "impressions": int(ad.get('impressions', 0)),
                "aov": aov,
                "cpa": cpa,
                "gpt": gpt,
                "pattern": pattern
            }
        }

    print(f"[RL] Processing {len(insights)} ads in parallel...")
    results = run_multithreaded(process_single_ad_performance, insights)
    
    for res in results:
        if res is None: continue
        
        offer_type = res["offer_type"]
        pattern = res["pattern"]
        profit = res["profit"]
        spend = res["spend"]
        revenue = res["revenue"]
        conversions = res["conversions"]
        ad_stats = res["ad_stats"]
        
        # Update pattern stats
        if pattern not in history[offer_type]["patterns"]:
            history[offer_type]["patterns"][pattern] = {
                "total_profit": 0.0, 
                "total_spend": 0.0, 
                "total_revenue": 0.0,
                "total_conversions": 0,
                "count": 0
            }
            
        history[offer_type]["patterns"][pattern]["total_profit"] += profit
        history[offer_type]["patterns"][pattern]["total_spend"] += spend
        history[offer_type]["patterns"][pattern]["total_revenue"] += revenue
        history[offer_type]["patterns"][pattern]["total_conversions"] += conversions
        history[offer_type]["patterns"][pattern]["count"] += 1
        
        # Keep track of top performing ads
        history[offer_type]["top_ads"].append(ad_stats)
        history[offer_type]["all_ads_temp"].append(ad_stats)

    # Sort top ads by profit (but also calculate aggregate GPT metrics for patterns)
    for o_type in history:
        # Calculate aggregate GPT metrics for each pattern
        for pattern_name, pattern_data in history[o_type]["patterns"].items():
            total_revenue = pattern_data.get("total_revenue", 0.0)
            total_conversions = pattern_data.get("total_conversions", 0)
            total_spend = pattern_data.get("total_spend", 0.0)
            
            if total_conversions > 0:
                pattern_aov = calculate_aov(total_revenue, total_conversions)
                pattern_cpa = calculate_cpa(total_spend, total_conversions)
                pattern_gpt = calculate_gpt(pattern_aov, pattern_cpa)
                
                pattern_data["aov"] = pattern_aov
                pattern_data["cpa"] = pattern_cpa
                pattern_data["gpt"] = pattern_gpt
                pattern_data["roas"] = (total_revenue / total_spend) if total_spend > 0 else 0.0
            else:
                pattern_data["aov"] = 0.0
                pattern_data["cpa"] = 0.0
                pattern_data["gpt"] = 0.0
                pattern_data["roas"] = 0.0
        
        # Sort top ads by profit (could also sort by GPT if desired)
        history[o_type]["top_ads"].sort(key=lambda x: x['profit'], reverse=True)
        history[o_type]["top_ads"] = history[o_type]["top_ads"][:10] # Keep top 10
        
        # Identify bottom ads (losers) - met minimum threshold but zero or low conversions
        # Minimum threshold: $100 spend or 5000 impressions
        all_ads = history[o_type].pop("all_ads_temp", []) 
        losers = [ad for ad in all_ads if (ad.get('spend', 0) >= 100 or ad.get('impressions', 0) >= 5000) and ad.get('conversions', 0) == 0]
        history[o_type]["bottom_ads"] = sorted(losers, key=lambda x: x.get('spend', 0), reverse=True)[:10]

    return history

def analyze_failures(history: Dict[str, Any]) -> str:
    """
    Use Claude to analyze losers and extract negative patterns.
    """
    bottom_ads = history.get('bottom_ads', [])
    if not bottom_ads:
        return ""

    if not api_keys.ANTHROPIC_CLIENT:
        api_keys.initialize_clients()
    
    if not api_keys.ANTHROPIC_CLIENT:
        return ""

    # Build analysis prompt
    losers_text = "\n".join([
        f"- Hook: {ad.get('name', 'N/A')}\n  Spend: {format_currency(ad.get('spend', 0))}\n  Impressions: {ad.get('impressions', 0)}"
        for ad in bottom_ads
    ])

    winners = history.get('top_ads', [])
    winners_text = "\n".join([
        f"- Hook: {ad.get('name', 'N/A')}"
        for ad in winners[:5]
    ])

    prompt = config.AI_PROMPTS['performance_analysis']['failure_analysis'].format(
        losers_text=losers_text,
        winners_text=winners_text
    )

    try:
        anthropic_limiter.wait()
        response = api_keys.ANTHROPIC_CLIENT.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        # Safely extract text from response
        if response.content and len(response.content) > 0:
            content_block = response.content[0]
            if hasattr(content_block, 'text'):
                return content_block.text
        return ""
    except Exception as e:
        print(f"[ERROR] Failure analysis failed: {e}")
        return ""

def format_currency(value: float) -> str:
    """
    Format a currency value for display.
    
    Args:
        value: Currency amount
        
    Returns:
        Formatted string like "$15.50" or "-$5.00"
    """
    if value >= 0:
        return f"${value:.2f}"
    else:
        return f"-${abs(value):.2f}"

def display_gpt_summary(history: Dict[str, Any], offer_type: Optional[str] = None):
    """
    Display GPT metrics summary for performance history.
    
    Args:
        history: Performance history dictionary
        offer_type: Optional offer type to filter (if None, shows all)
    """
    types_to_show = [offer_type] if offer_type else [config.OFFER_TYPE_SERVICE, config.OFFER_TYPE_ECOM]
    
    for o_type in types_to_show:
        if o_type not in history:
            continue
            
        data = history[o_type]
        top_ads = data.get("top_ads", [])
        patterns = data.get("patterns", {})
        
        if not top_ads:
            continue
            
        print(f"\n{'='*60}")
        print(f"GPT METRICS SUMMARY - {o_type.upper()}")
        print(f"{'='*60}")
        
        # Show top ads with GPT
        print(f"\n[TOP ADS BY PROFIT]")
        print(f"{'Ad Name':<40} {'GPT':<10} {'AOV':<10} {'CPA':<10} {'ROAS':<8} {'Profit':<12}")
        print("-" * 90)
        
        for ad in top_ads[:5]:  # Show top 5
            name = ad.get("name", "Unknown")[:38]
            gpt = format_currency(ad.get("gpt", 0))
            aov = format_currency(ad.get("aov", 0))
            cpa = format_currency(ad.get("cpa", 0))
            roas = f"{ad.get('roas', 0):.2f}x"
            profit = format_currency(ad.get("profit", 0))
            
            print(f"{name:<40} {gpt:<10} {aov:<10} {cpa:<10} {roas:<8} {profit:<12}")
        
        # Show pattern GPT metrics
        if patterns:
            print(f"\n[PATTERN GPT METRICS]")
            print(f"{'Pattern':<20} {'GPT':<10} {'AOV':<10} {'CPA':<10} {'ROAS':<8} {'Conversions':<12}")
            print("-" * 80)
            
            # Sort patterns by GPT
            sorted_patterns = sorted(
                patterns.items(), 
                key=lambda x: x[1].get("gpt", 0) if isinstance(x[1], dict) else 0, 
                reverse=True
            )
            
            for pattern_name, pattern_data in sorted_patterns:
                gpt = format_currency(pattern_data.get("gpt", 0))
                aov = format_currency(pattern_data.get("aov", 0))
                cpa = format_currency(pattern_data.get("cpa", 0))
                roas = f"{pattern_data.get('roas', 0):.2f}x"
                conversions = pattern_data.get("total_conversions", 0)
                
                print(f"{pattern_name:<20} {gpt:<10} {aov:<10} {cpa:<10} {roas:<8} {conversions:<12}")

def sync_performance_history():
    """
    Full workflow to sync performance from Meta to local history.
    """
    print(f"[INFO] Syncing performance data from Meta (Lookback: {config.PERFORMANCE_LOOKBACK_DAYS} days)...")
    
    insights = fetch_meta_insights(config.PERFORMANCE_LOOKBACK_DAYS)
    if not insights:
        print("[INFO] No new performance data found.")
        return False
        
    history = process_and_segment_performance(insights)
    
    # Save to file
    config.PERFORMANCE_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    with open(config.PERFORMANCE_HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump({
            "last_updated": datetime.now().isoformat(),
            "data": history
        }, f, indent=2)
        
    print(f"[OK] Performance history synced to {config.PERFORMANCE_HISTORY_FILE}")
    
    # Display GPT summary
    display_gpt_summary(history)
    
    return True

def get_type_specific_history(offer_type: str) -> Dict[str, Any]:
    """
    Load performance history for a specific offer type.
    """
    if not config.PERFORMANCE_HISTORY_FILE.exists():
        return {}
        
    try:
        with open(config.PERFORMANCE_HISTORY_FILE, 'r', encoding='utf-8') as f:
            full_history = json.load(f)
            return full_history.get("data", {}).get(offer_type, {})
    except Exception as e:
        print(f"[ERROR] Failed to load performance history: {e}")
        return {}

def get_gpt_metrics(offer_type: Optional[str] = None) -> Dict[str, Any]:
    """
    Get GPT metrics summary for analysis.
    
    Args:
        offer_type: Optional offer type filter
        
    Returns:
        Dictionary with GPT metrics summary
    """
    if not config.PERFORMANCE_HISTORY_FILE.exists():
        return {}
    
    try:
        with open(config.PERFORMANCE_HISTORY_FILE, 'r', encoding='utf-8') as f:
            full_history = json.load(f)
            history_data = full_history.get("data", {})
            
            if offer_type:
                return {
                    "offer_type": offer_type,
                    "data": history_data.get(offer_type, {})
                }
            else:
                return {
                    "all_types": history_data
                }
    except Exception as e:
        print(f"[ERROR] Failed to load GPT metrics: {e}")
        return {}

