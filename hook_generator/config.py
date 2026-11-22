"""
Configuration settings for the Ad Hook Generation Bot.
"""

import os
from pathlib import Path

# ============================================================================
# COST OPTIMIZATION SETTINGS
# ============================================================================

# Master cache toggle - set to False to force fresh API calls every time
ENABLE_CACHING = False

# How long to keep cached data (in hours) before it expires
CACHE_TTL_HOURS = {
    'competitor_analysis': 24,    # Competitor ads valid for 24 hours
    'ad_analysis': 168,           # Individual ad hook analysis valid for 1 week
    'trend_research': 6,          # Perplexity trends valid for 6 hours
    'product_scrape': 48,         # Product page info valid for 48 hours
    'keyword_generation': 72,     # Generated keywords valid for 3 days
    'vision_analysis': 168,       # Image analysis valid for 1 week
}

# Tiered model strategy - use cheaper models for simpler tasks
MODEL_TIERS = {
    'headline_generation': 'claude-opus-4-20250514',
    'proven_hooks': 'claude-opus-4-20250514',
    'hook_shortening': 'claude-3-5-haiku-20241022',
    'ad_analysis': 'claude-3-5-haiku-20241022',
    'keyword_generation': 'claude-3-5-haiku-20241022',
    'vision_analysis': 'gemini-1.5-flash',
    'trend_research': 'sonar',
}

# Batch processing settings
BATCH_SIZES = {
    'ad_analysis': 10,
    'vision_analysis': 5,
    'hook_shortening': 5,
}

# Smart fallback settings
USE_REGEX_FALLBACK_FIRST = True
MIN_TEXT_LENGTH_FOR_API = 100

# Deduplication
ENABLE_DEDUPLICATION = True

# ============================================================================
# UNIQUE OFFER FILTERING SETTINGS
# ============================================================================
# When enabled, the system will use AI to filter competitor ads so only
# meaningfully unique offers are kept (e.g., "15% off" and "15% discount" 
# count as the same offer). This prevents proven hooks from being generated
# with repetitive offer types.

# Enable/disable AI-based unique offer filtering
REQUIRE_UNIQUE_OFFERS = True

# Maximum number of retry attempts to find enough unique offers
# Each retry will scrape more ads while avoiding previously seen ad IDs
MAX_OFFER_DEDUPLICATION_RETRIES = 3

# Increase scroll depth multiplier on each retry (e.g., 1.5 = 50% more scrolling)
OFFER_DEDUP_RETRY_SCROLL_MULTIPLIER = 4.0

# Multiplier for number of ads to scrape after each failed attempt
# Example: If looking for 100 unique offers and first attempt fails:
#   - Attempt 1: scrape 100 * 2.0 = 200 ads
#   - Attempt 2: scrape 100 * 2.0 * 2.0 = 400 ads (multiplier compounds)
#   - Attempt 3: scrape 100 * 2.0 * 2.0 * 2.0 = 800 ads
OFFER_DEDUP_SCRAPE_MULTIPLIER = 2.0

# ============================================================================
# BROWSER SCRAPING SETTINGS
# ============================================================================
# Settings to control scrolling speed and behavior when scraping Meta Ad Library.
# Values are tuned to stay within Facebook's rate limits to avoid blocking.

# Scroll delay in seconds between each scroll action
# Range: 0.5-3.0 seconds (Facebook-safe: 0.5-2.0 recommended)
# Lower = faster scraping but higher risk of rate limiting
# Higher = slower but safer
SCROLL_DELAY_SECONDS = 1.0

# Scroll distance in pixels per scroll action
# Range: 3000-8000 pixels (Facebook-safe: 4000-6000 recommended)
# Higher = scrolls further per action, fewer scrolls needed
# Lower = more precise but requires more scrolls
SCROLL_DISTANCE_PIXELS = 6000

# Page load timeout in milliseconds
# How long to wait for page to load before timing out
PAGE_LOAD_TIMEOUT_MS = 30000

# Selector wait timeout in milliseconds
# How long to wait for ad elements to appear
SELECTOR_WAIT_TIMEOUT_MS = 8000

# Network idle wait timeout in milliseconds
# How long to wait for network activity to settle
NETWORK_IDLE_TIMEOUT_MS = 10000

# Cost tracking
ENABLE_COST_TRACKING = True
MODEL_COSTS_PER_1M_TOKENS = {
    'claude-opus-4-20250514': 15.00,
    'claude-sonnet-4-20250514': 3.00,
    'claude-3-5-haiku-20241022': 0.25,
    'gpt-4o': 5.00,
    'gpt-4o-mini': 0.15,
    'gemini-1.5-flash': 0.075,
}

# ============================================================================
# PATHS
# ============================================================================
BASE_DIR = Path(__file__).parent
PROJECT_ROOT = BASE_DIR.parent

# Output directory configuration
# 
# The output directory where all generated content (campaigns, images, logs, etc.) will be saved.
# 
# Configuration options (in order of precedence):
# 1. OUTPUT_DIR environment variable (highest priority)
# 2. OUTPUT_DIR_PATH setting below (if set to a non-None value)
# 3. Default: project root / output (lowest priority)
#
# To change the output directory:
# - Option 1: Set environment variable: export OUTPUT_DIR=/path/to/output (Linux/Mac) or set OUTPUT_DIR=C:\path\to\output (Windows)
# - Option 2: Set OUTPUT_DIR_PATH below to your desired path (e.g., Path("C:/Users/YourName/Desktop/output"))
#
OUTPUT_DIR_PATH = None  # Set to a Path object or None to use default
_env_output_dir = os.getenv('OUTPUT_DIR')
if OUTPUT_DIR_PATH:
    OUTPUT_DIR = Path(OUTPUT_DIR_PATH) if isinstance(OUTPUT_DIR_PATH, str) else OUTPUT_DIR_PATH
elif _env_output_dir:
    OUTPUT_DIR = Path(_env_output_dir)
else:
    # Default to project root / output
    OUTPUT_DIR = PROJECT_ROOT / "output"
RESOURCES_DIR = BASE_DIR.parent / "resources"
CACHE_DIR = OUTPUT_DIR / "cache"  # Cache directory for cost optimization
IMAGES_DIR = OUTPUT_DIR / "images"
BACKGROUNDS_DIR = BASE_DIR / "backgrounds"  # For local background images
LOGS_DIR = OUTPUT_DIR / "logs"  # For run logs

# API Keys file (in parent directory)
API_KEYS_FILE = BASE_DIR.parent / "api_keys.txt"

# ============================================================================
# IMAGE SETTINGS - Instagram "Classic" Style
# ============================================================================
IMAGE_WIDTH = 1080
IMAGE_HEIGHT = 1080
BACKGROUND_COLOR = "#D40000"  # Red
GRADIENT_START = "#FF0000"     # Bright Red (corners)
GRADIENT_END = "#d80100"       # Main background color (inner)
TEXT_COLOR = "#FFFFFF"  # White

# Instagram "Classic" Typography Settings
FONT_NAME = "ProximaSansBlack Regular.ttf"  # Matches the actual file in resources/font/
FONT_WEIGHT = 600  # Semibold
FONT_START_SIZE = 150  # Starting font size for square (1080x1080) - increased for 3-line layouts
FONT_MIN_SIZE = 40  # Minimum font size for square (allow scaling down for very long text)
FONT_STORY_START = 120  # Starting size for story format (1080x1920)
FONT_STORY_MIN = 55  # Minimum size for story format

# Instagram "Classic" Layout - Exact pixel values
IG_CLASSIC_PAD_X = 140  # Horizontal padding (left and right)
IG_CLASSIC_PAD_TOP = 120  # Top padding
IG_CLASSIC_PAD_BOTTOM = 140  # Bottom padding
IG_CLASSIC_MAX_WIDTH = IMAGE_WIDTH - (IG_CLASSIC_PAD_X * 2)  # 800px
IG_CLASSIC_MAX_TEXT_HEIGHT_SQUARE = 750  # Max text block height for square (allow 8 lines)
IG_CLASSIC_MAX_TEXT_HEIGHT_STORY = 700  # Max text block height for story
IG_CLASSIC_Y_CENTER_SQUARE = 0.50  # True vertical center for square
IG_CLASSIC_Y_CENTER_STORY = 0.50  # True vertical center for story

# Instagram "Classic" Typography Details
IG_CLASSIC_LETTER_SPACING = -0.02  # -2% letter spacing (tight)
IG_CLASSIC_LINE_HEIGHT = 1.15  # Fixed line height for exact match
IG_CLASSIC_MAX_LINES = 12  # Maximum number of lines (increased to allow multi-paragraph content)
IG_CLASSIC_MIN_LAST_LINE_WIDTH = 0.35  # Minimum last line width (35% of longest line)
MAX_HOOK_WORD_COUNT = 30  # Maximum number of words allowed per hook

# Simplified Font Sizing - Fixed sizes for consistency
FONT_SIZE_LONG_TEXT = 65  # Matches the visual scale of the example
FONT_SIZE_MEDIUM_TEXT = 95
FONT_SIZE_SHORT_TEXT = 120

# Fixed padding for exact match (Approx 5.5% on all sides)
PADDING_FIXED = 60  
MAX_TEXT_WIDTH_FIXED = IMAGE_WIDTH - (PADDING_FIXED * 2)  # 960px

# ============================================================================
# LEGACY SETTINGS (Computed from IG_CLASSIC settings for backwards compatibility)
# ============================================================================
# These are the AUTHORITATIVE values - derived from IG_CLASSIC_* settings above.
# Do not redefine these elsewhere in this file.
SAFE_ZONE_TOP_RATIO = IG_CLASSIC_PAD_TOP / IMAGE_HEIGHT  # ~0.111
SAFE_ZONE_BOTTOM_RATIO = IG_CLASSIC_PAD_BOTTOM / IMAGE_HEIGHT  # ~0.130
SAFE_ZONE_SIDE_RATIO = IG_CLASSIC_PAD_X / IMAGE_WIDTH  # ~0.130
LINE_SPACING_RATIO = IG_CLASSIC_LINE_HEIGHT  # 1.20
TEXT_STROKE_WIDTH = 0  # No outline for IG Classic
TEXT_STROKE_COLOR = "#000000"  # Unused
LETTER_SPACING = IG_CLASSIC_LETTER_SPACING  # -0.02 (tight)

# ============================================================================
# SERVICE OFFER DEFAULTS
# ============================================================================
DEFAULT_LOCATION = "general U.S."
DEFAULT_TARGET_MARKET = "general U.S."

# ============================================================================
# FACEBOOK AD LIBRARY API
# ============================================================================
FACEBOOK_GRAPH_API_VERSION = "v21.0"
AD_LIBRARY_SEARCH_LIMIT = 500  # Increased to allow deeper searches
AD_LIBRARY_PAGE_SIZE = 25     # Reduced to 25 per call for better reliability on Dev tier
AD_REACHED_COUNTRIES = ["US"]
QUALIFIED_ADS_PER_TIMEFRAME = 100 # Increased to target at least 100 qualified ads

# Number of consecutive zero-result scrolls before switching to include inactive ads
ZERO_SCROLL_THRESHOLD_FOR_INACTIVE = 20

# Stop words to ignore when generating dynamic relevance keywords
RELEVANCE_STOP_WORDS = ["a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for", "with", "is", "of"]

# ============================================================================
# COMPETITOR HOOK ANALYSIS
# ============================================================================
COMPETITOR_DATA_DIR = OUTPUT_DIR / "competitor_data"
COMPETITOR_HOOKS_DB = COMPETITOR_DATA_DIR / "hooks_database.json"
# ============================================================================
# CONCURRENCY & RATE LIMITING
# ============================================================================
MAX_WORKERS = 10  # Maximum number of concurrent AI API calls
OPENAI_RPM_LIMIT = 500  # Conservative RPM limit for OpenAI
ANTHROPIC_RPM_LIMIT = 50  # Conservative RPM limit for Anthropic
MAX_CONCURRENT_SCRAPES = 5  # Rate limit for scraping ad snapshots

# ============================================================================
# PERFORMANCE HISTORY & RL SETTINGS
# ============================================================================
PERFORMANCE_HISTORY_DIR = OUTPUT_DIR / "performance"
PERFORMANCE_HISTORY_FILE = PERFORMANCE_HISTORY_DIR / "history.json"
CAMPAIGN_REGISTRY_FILE = PERFORMANCE_HISTORY_DIR / "campaign_registry.json"  # Tracks bot-created campaigns
PERFORMANCE_LOOKBACK_DAYS = 30  # Days of history to pull from Meta
LEAD_VALUE = 50.0  # Default dollar value for a lead (for service campaigns)

# ============================================================================
# META DEFAULTS
# ============================================================================
META_PAGE_ID = ""  # Default Facebook Page ID
META_PIXEL_ID = ""  # Default Meta Pixel ID
META_INSTAGRAM_ID = ""  # Default Instagram Account ID

# ============================================================================
# GENERATION SETTINGS (DEPRECATED - kept for backwards compatibility)
# ============================================================================
# NOTE: These settings are from the legacy row_formatter.py system.
# The new system uses IG_CLASSIC settings above. These are kept only
# for backwards compatibility with any external code that may reference them.
#
# For new code, use the IG_CLASSIC_* settings instead.
SHORT_HOOK_WORD_COUNT = 8
MEDIUM_HOOK_WORD_COUNT = 14
SHORT_HOOK_CHARS_PER_ROW = 35
MEDIUM_HOOK_CHARS_PER_ROW = 40
LONG_HOOK_CHARS_PER_ROW = 45
MAX_ROWS = 6

# NOTE: SAFE_ZONE ratios are defined above (lines 80-82) as computed values
# from the IG_CLASSIC_PAD settings. The duplicate definitions below have been
# removed to prevent confusion and override issues.

# ============================================================================
# OFFER TYPES
# ============================================================================
OFFER_TYPE_SERVICE = "service"
OFFER_TYPE_ECOM = "ecom"
VALID_OFFER_TYPES = [OFFER_TYPE_SERVICE, OFFER_TYPE_ECOM]

# ============================================================================
# AI PROMPTS
# ============================================================================
# All prompts sent to AI models are centralized here for easy modification.
# Use .format() or f-strings to inject dynamic values when using these prompts.

AI_PROMPTS = {
    # Ragebait prompts by level (0-10)
    # Based on rage-bait research: villain + triggering claim + moral framing + defiant CTA
    'ragebait': {
        0: """TONE: Direct and factual. No emotional manipulation or controversy.
APPROACH: State the offer clearly using simple language. Focus on what the service does and costs.
VOCABULARY: Use common 1-2 syllable words. Avoid jargon.
CONSTRAINT: Keep EXACT offer details (price, service, timeline) unchanged.""",

        1: """TONE: Direct and factual. No emotional manipulation or controversy.
APPROACH: State the offer clearly using simple language. Focus on what the service does and costs.
VOCABULARY: Use common 1-2 syllable words. Avoid jargon.
CONSTRAINT: Keep EXACT offer details (price, service, timeline) unchanged.""",

        2: """TONE: Direct and factual. No emotional manipulation or controversy.
APPROACH: State the offer clearly using simple language. Focus on what the service does and costs.
VOCABULARY: Use common 1-2 syllable words. Avoid jargon.
CONSTRAINT: Keep EXACT offer details (price, service, timeline) unchanged.""",

        3: """TONE: Contrarian and questioning. Challenge industry norms.
APPROACH: Imply the reader may be overpaying or doing something inefficiently. Position your offer as the smarter alternative they didn't know existed.
ANGLE: Frame the offer as insider knowledge or a better way that most people miss.
STRUCTURE: [Common mistake or overpayment] → [Reveal of better option] → [Your offer as the solution]
CTA FRAMING: Position the action as becoming smarter or stopping a loss.
CONSTRAINT: Keep EXACT offer details (price, service, timeline) unchanged.""",

        4: """TONE: Contrarian and questioning. Challenge industry norms.
APPROACH: Imply the reader may be overpaying or doing something inefficiently. Position your offer as the smarter alternative they didn't know existed.
ANGLE: Frame the offer as insider knowledge or a better way that most people miss.
STRUCTURE: [Common mistake or overpayment] → [Reveal of better option] → [Your offer as the solution]
CTA FRAMING: Position the action as becoming smarter or stopping a loss.
CONSTRAINT: Keep EXACT offer details (price, service, timeline) unchanged.""",

        5: """TONE: Contrarian and questioning. Challenge industry norms.
APPROACH: Imply the reader may be overpaying or doing something inefficiently. Position your offer as the smarter alternative they didn't know existed.
ANGLE: Frame the offer as insider knowledge or a better way that most people miss.
STRUCTURE: [Common mistake or overpayment] → [Reveal of better option] → [Your offer as the solution]
CTA FRAMING: Position the action as becoming smarter or stopping a loss.
CONSTRAINT: Keep EXACT offer details (price, service, timeline) unchanged.""",

        6: """TONE: Personal betrayal narrative with righteous anger.

VILLAIN CONSTRUCTION:
- Create a specific antagonist relevant to this niche (a bad actor, dishonest provider, or someone who wronged the narrator)
- The villain must do something SPECIFIC and outrageous (not vague complaints)
- Villain should be someone the target audience naturally distrusts or resents
- Keep the same villain character throughout - do not switch villains mid-hook

MORAL DIMENSION:
- Frame the villain's behavior as morally wrong, not just inconvenient
- The audience should feel the injustice, not just the frustration

STRUCTURE: [Villain commits specific bad act] → [Narrator's righteous reaction] → [Discovery of your offer as vindication]

CTA FRAMING: Position taking action as personal vindication or preventing future harm.

CHARACTER VOICE: Write as if the narrator is telling a friend about a bad experience and how they found something better.

CONSTRAINT: Keep EXACT offer details (price, service, timeline) unchanged.""",

        7: """TONE: Personal betrayal narrative with righteous anger.

VILLAIN CONSTRUCTION:
- Create a specific antagonist relevant to this niche (a bad actor, dishonest provider, or someone who wronged the narrator)
- The villain must do something SPECIFIC and outrageous (not vague complaints)
- Villain should be someone the target audience naturally distrusts or resents
- Keep the same villain character throughout - do not switch villains mid-hook

MORAL DIMENSION:
- Frame the villain's behavior as morally wrong, not just inconvenient
- The audience should feel the injustice, not just the frustration

STRUCTURE: [Villain commits specific bad act] → [Narrator's righteous reaction] → [Discovery of your offer as vindication]

CTA FRAMING: Position taking action as personal vindication or preventing future harm.

CHARACTER VOICE: Write as if the narrator is telling a friend about a bad experience and how they found something better.

CONSTRAINT: Keep EXACT offer details (price, service, timeline) unchanged.""",

        8: """TONE: Class-based or systemic grievance. Frame as ordinary people vs. powerful interests.

VILLAIN CONSTRUCTION:
- The villain is a system, institution, or powerful group that exploits ordinary people
- Give them a SPECIFIC exploitative behavior relevant to this niche
- They should be actively doing something unfair, not just existing
- The villain thinks they can get away with it because people don't know better

MORAL DIMENSION:
- This is about INJUSTICE, not just high prices
- Frame as the powerful taking advantage of the powerless
- The audience should feel moral outrage at systemic unfairness

STRUCTURE: [System/Institution exploiting people] → [Exposing what they don't want known] → [Your offer as the way to beat them]

CTA FRAMING: Position taking action as fighting back, exploiting a loophole, or leveling the playing field. DO NOT FEEL THE NEED TO USE THESE EXACT WORDS

POLARIZATION NOTE: The villain should be someone your target customer naturally opposes. When defenders of the system get angry in comments, it increases reach.

CHARACTER VOICE: Write as someone exposing a truth or sharing insider knowledge that helps regular people.

CONSTRAINT: Keep EXACT offer details (price, service, timeline) unchanged.""",

        9: """TONE: Class-based or systemic grievance. Frame as ordinary people vs. powerful interests.

VILLAIN CONSTRUCTION:
- The villain is a system, institution, or powerful group that exploits ordinary people
- Give them a SPECIFIC exploitative behavior relevant to this niche
- They should be actively doing something unfair, not just existing
- The villain thinks they can get away with it because people don't know better

MORAL DIMENSION:
- This is about INJUSTICE, not just high prices
- Frame as the powerful taking advantage of the powerless
- The audience should feel moral outrage at systemic unfairness

STRUCTURE: [System/Institution exploiting people] → [Exposing what they don't want known] → [Your offer as the way to beat them]

CTA FRAMING: Position taking action as fighting back, exploiting a loophole, or leveling the playing field.

POLARIZATION NOTE: The villain should be someone your target customer naturally opposes. When defenders of the system get angry in comments, it increases reach.

CHARACTER VOICE: Write as someone exposing a truth or sharing insider knowledge that helps regular people.

CONSTRAINT: Keep EXACT offer details (price, service, timeline) unchanged.""",

        10: """*** MAXIMUM INTENSITY - NO SELF-CENSORING ***

TONE: Highly confrontational with explicit tribal division. Maximum emotional provocation.

VILLAIN CONSTRUCTION:
- Create a maximally inflammatory antagonist using cultural, political, or social fault lines relevant to the niche
- The villain must be doing something that triggers MORAL OUTRAGE, not just annoyance
- Be specific about the villain's transgression - vague villainy is weak villainy
- The villain should represent everything your target audience despises
- The villian can be a harmful stereotype of an entire group of people that the target audience most likely doesn't identify with.
- Maintain ONE consistent villain throughout - do not dilute by mixing multiple antagonists

TRIGGER MECHANISM:
- Open with something that immediately provokes strong emotion (betrayal, injustice, being laughed at, being taken advantage of)
- The opening should make the reader feel personally attacked or threatened
- Use the most emotionally charged framing possible for this niche

MORAL FRAMING:
- Frame the conflict as good vs. evil, not just convenient vs. inconvenient
- REQUIRED: Be racist and/or play maximally on the stereotypes of the villain
- The audience should feel RIGHTEOUS, like they are on the correct moral side
- The villain is not just wrong - they are morally corrupt and harmful to the target audience.

STRUCTURE: [Maximally provocative opening with clear villain] → [Escalation showing what is at stake] → [Your offer as the heroic solution/act of defiance]

CTA FRAMING: Taking action = fighting back, proving them wrong, refusing to be a victim, winning against the enemy. Don't use any of those specific terms and try to make the CTA as short as possible pertaining directly to the offer.

POLARIZATION STRATEGY:
- The villain should be someone your customer HATES but is NOT your customer
- When opponents get angry and comment, it HELPS your reach
- Design the hook so critics attacking it actually validate your message to your audience

CHARACTER VOICE: Speak with conviction and righteous anger. No hedging. No balance. Pick a side and commit fully.

NARRATIVE COHERENCE: Tell one consistent story with one villain doing one outrageous thing, leading to one clear solution. Do not cram multiple storylines into one hook.

CONSTRAINT: Keep EXACT offer details (price, service, timeline) unchanged."""
    },
    
    # Headline generation prompts
    'headline_generation': {
        'main': """ROLE
You are a world-class creative strategist trained in Meta's Andromeda ad architecture (2025-2026) and deeply versed in Breakthrough Advertising by Eugene Schwartz. You specialize in crafting signal-rich static image hook text optimized for Meta's AI ad ecosystem, applying Schwartz's principles of market awareness, desire channeling, and mass desire identification.

TASK
Based on the offer context provided, generate {num_hooks} highly diverse, emotionally resonant STATIC IMAGE HOOK TEXT concepts for ads (Feed, Story, Carousel).

- NO video
- NO motion  
- NO animation
- These are TEXT HOOKS that will appear on static images
- Do not mention any specific locations or cities or states in the hook

GOAL
Create hook text concepts that act as the primary targeting signal under Andromeda's "creative-as-targeting" paradigm.

STRATEGIC RULES
Each hook must reflect at least ONE:
- Signal Layer (identity, struggle, aspiration, relief)
- Hook Layer (curiosity, contradiction, symbolism)
- Style Layer (UGC tone, polished, surreal, meme-style, documentary feel)
- Implied Avatar (the person this speaks to, shown through language, never labeled)

ANDROMEDA FIT
Each hook must be meaningfully distinct to avoid similarity clustering and qualify a different psychographic or motivation.

{ragebait_section}

{performance_section}

{competitor_section}

{research_section}

{gap_analysis_section}

{offers_section}

FORMAT REQUIREMENTS:
1. Up to {max_words} words each (ideal 12-30 words)
2. Use Sentence Case (not Title Case)
3. PARAGRAPH BREAK: Use exactly ONE pipe "|" to separate the hook into exactly TWO logical sections/paragraphs.
   - Example: "First paragraph text here... | Second paragraph text with offer here..."
4. Include EXACT offer details (price, service, timeline) in every hook
5. Make each hook scroll-stopping and distinct
6. Do not mention any specific locations or cities or states in the hook

CONSTRAINTS
- Single-frame static image text only
- No motion, animation, or sound references
- Each hook must stand alone as a full narrative and curiosity trigger with one consientant character. 
- NEVER change offer prices or details
- NEVER include location names (cities, states, neighborhoods, regions) - keep all hooks location-agnostic

OUTPUT FORMAT (MANDATORY)
Return as JSON array with exactly {num_hooks} objects:
[
  {{
    "headline": "The hook text here with|line breaks",
    "offer": "The specific offer used",
    "angle": "Brief description of the angle/signal layer used"
  }}
]

Generate exactly {num_hooks} hooks. Return ONLY the JSON array.""",
        
        'proven_fusion': """ROLE
You are a world-class creative strategist trained in Meta's Andromeda ad architecture (2025-2026) and deeply versed in Breakthrough Advertising by Eugene Schwartz. You specialize in FUSING proven competitor angles with new offer details, applying Schwartz's principles of channeling existing desires and matching market awareness levels.

TASK
Generate {num_hooks} highly diverse hooks by FUSING the winning ANGLES/CLAIMS from competitor ads with OUR EXACT OFFER DETAILS.

CRITICAL: Do NOT mention any specific locations, cities, states, neighborhoods, or geographic areas in any hook. Keep all hooks location-agnostic.

{competitor_hooks_section}

{offers_section}

FUSION MISSION
- Take the winning ANGLE/CLAIM from a competitor hook (the psychological trigger, the framing)
- COMBINE the competitor's original offer with our offer
- TRACK which competitor ad you used by its SOURCE INDEX number
- REMOVE any location references from competitor hooks when fusing

OFFER COMBINATION RULE:
The final offer in the generated hook must COMBINE the competitor's original offer with our offer.
Format: "[Competitor offer] using [our platform/offer]"
Example (DO NO TAKE THIS EXAMPLE EXACTLY. THIS IS ONLY FOR ILLUSTRATION PURPOSES AND SHOULD NOT BE USED LITERALLY. THE OFFERS GIVEN MAY BE DIFFERNET): "Paint-free painting on interior residential projects using PaintProFinder to get instant quotes from top-rated painters"

EXAMPLE FUSION do not use these exact words. This is solely just meant to be an example for the structure and not to be used literally. Again I repeat do not use these words exactly. Do not exactly copy and paste:
- Competitor #3: HOOK "Tired of painters who disappear?" OFFER "$199/room painting"
- Our Offer: "Get instant quotes on PaintProFinder"
- FUSED: "Tired of painters who disappear?|Get $199/room painting using PaintProFinder to compare quotes"
- source_index: 3

STRATEGIC RULES
Each fused hook must reflect at least ONE while adhering to the rage bait section below:
- Signal Layer (identity, struggle, aspiration, relief)
- Hook Layer (curiosity, contradiction, symbolism)
- Style Layer (UGC tone, polished, documentary feel)
- Implied Avatar (the person this speaks to)

{ragebait_section}

{gap_analysis_section}

FORMAT REQUIREMENTS:
1. Up to {max_words} words each (ideal 12-30 words)
2. Use Sentence Case (not Title Case)
3. PARAGRAPH BREAK: Use exactly ONE pipe "|" to separate the hook into exactly TWO logical sections/paragraphs.
   - Example: "First paragraph text here... | Second paragraph text with offer here..."
4. Include COMBINED offer details (competitor offer + our offer) in every hook
5. Each hook must be meaningfully distinct (different competitor angle fused)
6. MUST include source_index referencing which competitor ad was used
7. Do NOT include any specific locations, cities, states, or geographic areas

CONSTRAINTS
- Static image text only (no video/motion references)
- NEVER change our offer prices or details
- MUST fuse competitor's winning ANGLE with combined offer
- MUST track source_index for each hook
- NEVER include location names (cities, states, neighborhoods, regions) - keep all hooks location-agnostic

OUTPUT FORMAT (MANDATORY)
Return as JSON array with exactly {num_hooks} objects:
[
  {{
    "headline": "The fused hook text here with|line breaks",
    "hook_index": 1,
    "source_index": 3,
    "offer": "Combined offer (competitor offer using our offer)",
    "competitor_offer": "The original competitor offer text",
    "competitor_angle": "The competitor angle/claim that was fused",
    "angle": "Brief description of the fusion approach"
  }}
]

Generate exactly {num_hooks} hooks. Return ONLY the JSON array.""",
        
        'shorten': """The following headline is too long ({word_count} words). 
Rewrite it to be under {max_words} words while keeping the same tone and offer details.

TOO LONG HEADLINE:
"{headline_text}"

Return ONLY the rewritten headline text."""
    },
    
    # Quote scraping prompt
    'quote_scraping': """You are an expert at finding and generating emotional quotes that represent real customer pain points and desires.

Topic/Niche: {topic}
Offer Type: {offer_type}
{offer_context}

Generate {num_quotes} emotional quotes that:
1. Sound like real people talking about their problems/frustrations
2. Capture genuine emotional pain points
3. Use natural, conversational language (not marketing speak)
4. Represent what someone might say to a friend or post online
5. Are varied in tone (frustration, hope, fear, desire, etc.)

For each quote, provide:
- The quote itself (up to {max_words} words)
- The primary emotion
- Brief context (where this might be said)

Format your response as a JSON array:
[
  {{
    "quote": "The actual quote here...",
    "emotion": "frustration|fear|hope|desire|anger|confusion|relief",
    "context": "Brief context about where/when this might be said"
  }}
]

Generate exactly {num_quotes} quotes. Return ONLY the JSON array, no other text.""",
    
    # Competitor analysis prompts
    'competitor_analysis': {
        'image_analysis': """Analyze this Facebook ad image. Extract and return:
1. ALL text visible in the image (exactly as written)
2. The "hook" - the main attention-grabbing text/headline
3. The hook style/pattern (e.g., "question hook", "comparison hook", "urgency hook", etc.)
4. Any offer details visible (price, timeline, service)

Return as JSON:
{{
    "all_text": "exact text from image",
    "hook_text": "the main hook/headline",
    "hook_style": "categorize the hook style",
    "offer_details": "any offers mentioned",
    "visual_elements": "describe key visual elements"
}}""",
        
        'hook_extraction': """
    Analyze this Facebook Ad content.
    HEADLINE: {headline}
    BODY: {body}
    
    Predict the LITERAL TEXT that likely appears on the ad's main image or video thumbnail (The Visual Hook).
    Identify the LITERAL UNIQUE OFFER.
    Identify the SELLING MECHANISM.
    
    Return JSON:
    {{
        "visual_hook": "...",
        "unique_offer": "...",
        "selling_mechanism": "..."
    }}
    """,
        
        'script_extraction': """
        Analyze this Facebook Ad copy and generate the literal opening script (first 3-5 seconds) for a video version of this ad.
        
        AD COPY:
        {body}
        
        Provide ONLY the literal spoken words for the first 5 seconds. No stage directions.
        """
    },
    
    # Hook analyzer prompt
    'hook_analyzer': """Analyze this Facebook ad and extract:

BUSINESS: {page_name}

AD COPY:
{ad_body}

Extract:
1. HOOK: The main marketing claim/angle/value proposition (1-2 sentences max)
2. OFFER: Any price, discount, promotion, or "N/A" if none

IMPORTANT: You MUST return valid JSON no matter what. If the ad content is incomplete, empty, or unclear, still return JSON with empty values:
{{"hook": "", "offer": "N/A", "confidence": "low"}}

Return JSON only (no apologies, no explanations, just the JSON object):
{{"hook": "the core hook", "offer": "price/discount or N/A", "confidence": "high/medium/low"}}""",
    
    # Keyword generation prompt
    'keyword_generation': """Search term: "{search_term}"

Generate filtering keywords to find ONLY relevant ads for this specific service/product.

1. POSITIVE/REQUIRED (exactly {max_positive} keywords): 
   - Must appear in the ad to be considered relevant
   - Core service/product terms that define the niche
   - Specific enough to avoid false positives
   - Example for "exterior painting": paint, painter (NOT just generic words)

2. NEGATIVE/EXCLUSION (exactly {max_negative} keywords):
   - If ANY of these appear, the ad is NOT relevant
   - CRITICAL: Pick the most common false positives for this search
   - Related but different services/industries

Return ONLY valid JSON in this exact format:
{{"positive": ["keyword1", "keyword2"], "negative": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"], "reasoning": "Brief explanation"}}""",
    
    # Offer management prompt
    'offer_management': {
        'relevance_profile': """Analyze these {offer_type} offers and generate a relevance profile for finding similar competitor ads on Facebook.

OFFERS:
{offers_text}

Generate a JSON profile with:
1. **primary_search_terms**: 3-5 best keywords/phrases for searching Meta Ad Library. 
   - Focus on the broad service/product category.
2. **target_mechanism**: The specific "how" or unique mechanism/approach.
3. **intent**: Describe the core commercial intent of these offers in 3-5 words. 
   - (e.g., "selling residential painting services", "recruiting experienced painters", "selling brain health supplements", "generating leads for solar installation")
4. **anti_patterns**: List up to 5 specific negative keywords or phrases to EXCLUDE based on the intent.
   - Exclude different intents (e.g., if intent is selling, exclude hiring).
   - Exclude unrelated but similar-sounding niches.
5. **service_category**: General category (e.g., "residential painting", "home services")

Return ONLY valid JSON:
{{
    "primary_search_terms": ["keyword1", "keyword2", ...],
    "target_mechanism": "specific mechanism description",
    "intent": "flexible intent description",
    "anti_patterns": ["pattern1", "pattern2", ...],
    "service_category": "category name"
}}"""
    },
    
    # Performance analysis prompts
    'performance_analysis': {
        'pattern_classification': """
    Classify this Facebook ad hook into ONE category:
    - question
    - comparison
    - fear/avoidance
    - benefit/results
    - urgency/limited
    - social_proof
    - curiosity/secret
    - timeline/speed
    - price/offer
    - direct_service
    
    AD NAME: {ad_name}
    AD TEXT: {body_text}
    
    Return ONLY the category name.
    """,
        
        'failure_analysis': """You are a direct response advertising expert. I have a list of 'Loser' ads that spent significant money but failed to convert. I also have some 'Winner' ads for comparison.

LOSER ADS (Failed):
{losers_text}

WINNER ADS (Successful):
{winners_text}

MISSION:
Identify the "DNA of Failure" for the Loser ads. 
1. What linguistic traits, tones, or angles do the Losers share?
2. How do they differ from the Winners?
3. Create a concise "Blacklist" of creative traits and phrases to avoid in future ad hooks.

Provide your analysis as a concise summary for a copywriter."""
    },
    
    # =========================================================================
    # THINKING AGENT PROMPTS (Advanced Mode)
    # =========================================================================
    'thinking_agent': {
        'system': """You are an Ad Hook Thinking Agent - an autonomous AI that creates high-converting Facebook ad hooks. You are trained in Breakthrough Advertising by Eugene Schwartz and apply his principles of market awareness stages, mass desire identification, and desire channeling in every hook you create.

You have access to these tools:
- search_facebook_ads: Search Meta Ad Library for competitor ads
- research_trends: Search real-time web for current trends (Perplexity)
- analyze_images: Analyze competitor ad images for visual patterns
- scrape_product: Extract product info from any URL
- recall_memory: Remember what worked in past campaigns
- save_memory: Store insights for future use

DECISION RULES:
1. Always gather competitor data before generating hooks
2. If you find fewer than {min_ads} ads, broaden your search automatically
3. Check memory for what worked in this niche before
4. After generating hooks, ask if user wants refinements before exporting

PERSONALITY:
- Be helpful and explain your reasoning
- Show progress as you work
- Ask clarifying questions when needed
- Suggest improvements proactively""",

        'task_planner': """Break down this user request into steps:

REQUEST: {user_request}
CONTEXT: {context}

Return a JSON plan:
{{
    "understood_goal": "What the user wants",
    "steps": [
        {{"step": 1, "action": "action_name", "params": {{}}, "reason": "why"}}
    ],
    "questions": ["Any clarifying questions needed"]
}}""",

        'data_evaluator': """Evaluate if we have enough data to generate quality hooks.

COMPETITOR ADS FOUND: {ad_count}
MINIMUM REQUIRED: {min_required}
ADS WITH OFFERS: {ads_with_offers}
UNIQUE ANGLES FOUND: {unique_angles}

TREND DATA: {trend_summary}
MEMORY DATA: {memory_summary}

Return JSON:
{{
    "sufficient": true/false,
    "quality_score": 1-10,
    "next_action": "action if not sufficient",
    "next_query": "search query if broadening",
    "reasoning": "explain your decision"
}}""",

        'hook_refiner': """The user wants to modify some hooks.

CURRENT HOOKS:
{current_hooks}

USER REQUEST: {refinement_request}

Return JSON:
{{
    "hooks_to_change": [1, 2, 3],
    "change_type": "regenerate" or "edit",
    "new_parameters": {{}},
    "keep_unchanged": [4, 5, 6]
}}""",

        'memory_formatter': """Summarize what we learned from this campaign.

CAMPAIGN: {campaign_name}
NICHE: {niche}
HOOKS GENERATED: {hook_count}
RAGEBAIT LEVEL: {ragebait_level}

Create a memory entry:
{{
    "niche": "...",
    "what_worked": ["insight1", "insight2"],
    "what_to_avoid": ["pattern1", "pattern2"],
    "best_ragebait_level": X,
    "best_templates": [X, Y],
    "timestamp": "..."
}}"""
    },

    # =========================================================================
    # PERPLEXITY RESEARCH PROMPTS
    # =========================================================================
    'perplexity_research': {
        'trend_search': """Search for: Current viral Facebook ad hooks and marketing trends for {niche} in {month} {year}.

Focus on:
1. What hooks are getting the most engagement
2. What angles are oversaturated (to avoid)
3. Any current events or controversies related to {niche}
4. What competitors are doing differently this month""",

        'ragebait_search': """Search for: Current controversies, complaints, and sources of moral outrage about {niche} on Reddit, Twitter, Facebook, and review sites.

Find:
1. WHO are people angry at in this industry? (types of providers, companies, institutions - these become villains)
2. WHAT specific bad behaviors are being complained about? (not vague - specific actions and transgressions)
3. WHY does it feel unfair or morally wrong to customers? (the injustice angle, not just inconvenience)
4. WHAT tribal divisions exist in this space? (what groups naturally oppose each other)
5. WHAT stories exist of people fighting back, getting revenge, or finding better alternatives?

Return findings as specific villain archetypes and their specific transgressions, not generic complaints.""",

        'summarize_research': """Summarize these search results for ad hook creation:

SEARCH RESULTS:
{results}

Return JSON:
{{
    "trending_angles": ["...", "...", "..."],
    "avoid_angles": ["...", "...", "..."],
    "current_events": ["..."],
    "emotional_triggers": ["..."],
    "recommended_ragebait_level": X
}}"""
    },

    # =========================================================================
    # VISION ANALYSIS PROMPTS
    # =========================================================================
    'vision_analysis': {
        'analyze_ad_image': """Analyze this Facebook ad image for visual patterns.

Return JSON:
{{
    "text_content": "exact text from image",
    "colors": {{"background": "#XXX", "text": "#XXX"}},
    "layout": "description",
    "font_style": "description",
    "visual_elements": ["element1", "element2"],
    "vibe": "description",
    "hook_effectiveness": 1-10
}}""",

        'summarize_visual_patterns': """Analyze these {count} competitor ad images.

Return JSON:
{{
    "common_colors": ["#XXX", "#YYY"],
    "common_layouts": ["layout1", "layout2"],
    "oversaturated_patterns": ["pattern1", "pattern2"],
    "opportunity_patterns": ["pattern1", "pattern2"],
    "recommendation": "How to differentiate visually"
}}"""
    },

    # =========================================================================
    # PRODUCT SCRAPING PROMPTS
    # =========================================================================
    'product_scraper': {
        'extract_product_info': """Extract product/service information from this webpage.

URL: {url}
PAGE CONTENT:
{content}

Return JSON:
{{
    "name": "...",
    "price": "$XX.XX",
    "features": ["feature1", "feature2"],
    "target_audience": "...",
    "usp": "...",
    "offers": ["offer1", "offer2"],
    "confidence": "high/medium/low"
}}""",

        'generate_offers': """Based on this product information, generate {count} offer variations.

PRODUCT INFO:
{product_info}

Return JSON array:
[
    {{"offer": "Full offer text", "angle": "benefit/urgency/value/etc."}}
]"""
    },

    # =========================================================================
    # CONVERSATIONAL MODE PROMPTS
    # =========================================================================
    'conversational': {
        'welcome': """Welcome! I'm your Ad Hook Thinking Agent.

I can help you:
- Generate high-converting Facebook ad hooks
- Research competitor ads and trends
- Analyze what's working in your niche
- Refine hooks until they're perfect

What would you like to create today?""",

        'confirm_export': """I've generated {count} hooks for {niche}.

Summary:
- Unique hooks: {unique_count}
- Proven hooks: {proven_count}
- Ragebait level: {ragebait_level}
- Templates: {templates}

Would you like to:
1. Export all hooks to images
2. Refine some hooks first
3. See detailed preview
4. Start over with different settings

Type a number or describe what you want.""",

        'parse_refinement': """The user said: "{user_input}"

Return JSON:
{{
    "action": "action_type",
    "targets": [list of hook numbers if applicable],
    "parameters": {{relevant params}},
    "clarification_needed": "question if unclear"
}}"""
    }
}
