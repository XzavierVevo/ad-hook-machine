"""
Thinking Agent - LangGraph-based autonomous agent for ad hook generation.

This module implements an intelligent agent that can:
- Make decisions about when to gather more data
- Automatically broaden searches when data is insufficient
- Remember what worked in past campaigns
- Refine hooks through conversational interaction
"""

import json
from typing import Dict, Any, List, Optional, TypedDict, Annotated, TYPE_CHECKING, Union
from datetime import datetime

if TYPE_CHECKING:
    from langgraph.graph import StateGraph
    from langgraph.graph.message import add_messages
else:
    add_messages = None

try:
    from langgraph.graph import StateGraph, END
    from langgraph.graph.message import add_messages as _add_messages
    if add_messages is None:
        add_messages = _add_messages
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    END = None  # type: ignore
    StateGraph = None  # type: ignore
    print("[WARNING] LangGraph not installed. Run: pip install langgraph langchain-core")

from .. import config
from .. import api_keys
from ..cache_manager import track_cost


class AgentState(TypedDict):
    """State passed between nodes in the agent graph."""
    messages: List[Dict[str, Any]]
    task: str
    context: Dict[str, Any]
    competitor_data: Optional[Dict[str, Any]]
    trend_data: Optional[Dict[str, Any]]
    memory_data: Optional[Dict[str, Any]]
    hooks: Union[Dict[str, List[Dict[str, Any]]], List[Dict[str, Any]]]
    current_step: str
    decision: Optional[str]
    iteration: int
    max_iterations: int


class ThinkingAgent:
    """
    Autonomous thinking agent for ad hook generation.
    
    Uses LangGraph to implement decision loops that can:
    - Evaluate data sufficiency
    - Automatically broaden searches
    - Apply learnings from memory
    - Generate and refine hooks
    """
    
    def __init__(
        self,
        min_ads: int = 10,
        max_iterations: int = 3,
        use_memory: bool = False
    ):
        """
        Initialize the thinking agent.
        
        Args:
            min_ads: Minimum number of competitor ads required
            max_iterations: Maximum search iterations before giving up
            use_memory: Whether to use Vertex AI Memory Bank
        """
        self.min_ads = min_ads
        self.max_iterations = max_iterations
        self.use_memory = use_memory
        self.tools = {}
        
        if not LANGGRAPH_AVAILABLE:
            raise ImportError(
                "LangGraph is required for the thinking agent. "
                "Install with: pip install langgraph langchain-core"
            )
        
        # Build the agent graph
        self.graph = self._build_graph()
    
    def _build_graph(self) -> Any:  # CompiledStateGraph[AgentState, ...]
        """Build the LangGraph state machine."""
        
        if not LANGGRAPH_AVAILABLE or StateGraph is None:
            raise ImportError("LangGraph is required")
        
        # Create the graph
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("plan", self._plan_node)
        workflow.add_node("gather_data", self._gather_data_node)
        workflow.add_node("evaluate", self._evaluate_node)
        workflow.add_node("generate", self._generate_node)
        workflow.add_node("refine", self._refine_node)
        
        # Set entry point
        workflow.set_entry_point("plan")
        
        # Add edges
        workflow.add_edge("plan", "gather_data")
        workflow.add_conditional_edges(
            "gather_data",
            self._should_gather_more,
            {
                "evaluate": "evaluate",
                "generate": "generate"
            }
        )
        if END is None:
            raise ImportError("LangGraph END is not available")
        
        workflow.add_conditional_edges(
            "evaluate",
            self._evaluate_decision,
            {
                "gather_more": "gather_data",
                "generate": "generate",
                "end": END
            }
        )
        workflow.add_edge("generate", "refine")
        workflow.add_edge("refine", END)
        
        return workflow.compile()
    
    def _plan_node(self, state: AgentState) -> AgentState:
        """Plan the task execution."""
        print("\n[AGENT] Planning task execution...")
        
        task = state.get('task', '')
        context = state.get('context', {})
        
        # Get system prompt from config
        system_prompt = config.AI_PROMPTS['thinking_agent']['system'].format(
            min_ads=self.min_ads
        )
        
        # Get task planner prompt
        planner_prompt = config.AI_PROMPTS['thinking_agent']['task_planner'].format(
            user_request=task,
            context=json.dumps(context, indent=2)
        )
        
        # Call AI to plan
        if api_keys.ANTHROPIC_CLIENT:
            try:
                response = api_keys.ANTHROPIC_CLIENT.messages.create(
                    model=api_keys.get_model_for_task('ad_analysis'),
                    max_tokens=1000,
                    system=system_prompt,
                    messages=[{"role": "user", "content": planner_prompt}]
                )
                
                if hasattr(response, 'usage'):
                    track_cost(
                        api_keys.get_model_for_task('ad_analysis'),
                        response.usage.input_tokens,
                        response.usage.output_tokens
                    )
                
                # Safely extract text from response
                if response.content and len(response.content) > 0:
                    content_item = response.content[0]
                    if hasattr(content_item, 'text'):
                        plan_text = getattr(content_item, 'text', str(content_item))
                    else:
                        plan_text = str(content_item)
                else:
                    plan_text = ""
                print(f"[AGENT] Plan created")
                
                # Parse plan
                try:
                    if "```" in plan_text:
                        plan_text = plan_text.split("```")[1]
                        if plan_text.startswith("json"):
                            plan_text = plan_text[4:]
                    plan = json.loads(plan_text.strip())
                    state['context']['plan'] = plan
                except json.JSONDecodeError:
                    state['context']['plan'] = {'understood_goal': task, 'steps': []}
                    
            except Exception as e:
                print(f"[AGENT] Planning failed: {e}")
                state['context']['plan'] = {'understood_goal': task, 'steps': []}
        
        state['current_step'] = 'plan_complete'
        state['messages'].append({
            'role': 'assistant',
            'content': f"I understand. Let me gather data about {context.get('topic', 'your request')}."
        })
        
        return state
    
    def _gather_data_node(self, state: AgentState) -> AgentState:
        """Gather competitor and trend data."""
        print("\n[AGENT] Gathering data...")
        
        context = state.get('context', {})
        iteration = state.get('iteration', 0)
        
        # Import tools lazily
        from .facebook_tool import search_facebook_ads
        from .perplexity_tool import research_trends
        
        topic = context.get('topic', '')
        offers = context.get('offers', [])
        positive_keywords = context.get('positive_keywords')
        negative_keywords = context.get('negative_keywords')
        auto_generate_keywords = context.get('auto_generate_keywords', True)
        skip_offer_filters = context.get('skip_offer_filters', False)
        
        # Broaden search on subsequent iterations
        if iteration > 0:
            # Broaden the topic
            topic = self._broaden_topic(topic, iteration)
            print(f"[AGENT] Broadened search to: {topic}")
        
        # Search Facebook Ad Library
        print(f"[AGENT] Searching Facebook Ad Library for '{topic}'...")
        if skip_offer_filters:
            print(f"[AGENT] Offer filters disabled - no keyword filtering")
        elif positive_keywords or negative_keywords:
            kw_info = []
            if positive_keywords:
                kw_info.append(f"positive: {', '.join(positive_keywords)}")
            if negative_keywords:
                kw_info.append(f"negative: {', '.join(negative_keywords)}")
            print(f"[AGENT] Using keywords: {', '.join(kw_info)}")
        
        # Use unique_offer_count as the limit for Facebook scraping
        # This is how many unique offers to find (not total hooks)
        unique_offer_limit = context.get('unique_offer_count', context.get('count', 20))
        max_ads = context.get('max_ads', 30)
        
        competitor_data = search_facebook_ads(
            topic=topic,
            offers=offers,
            limit=unique_offer_limit,
            non_interactive=True,
            positive_keywords=positive_keywords,
            negative_keywords=negative_keywords,
            auto_generate_keywords=auto_generate_keywords,
            skip_offer_filters=skip_offer_filters,
            max_ads=max_ads
        )
        state['competitor_data'] = competitor_data
        
        # Research trends with Perplexity (if available)
        if api_keys.PERPLEXITY_API_KEY:
            print(f"[AGENT] Researching current trends...")
            trend_data = research_trends(
                niche=topic,
                ragebait_level=context.get('ragebait_level', 3)
            )
            state['trend_data'] = trend_data
        
        # Load memory if enabled
        if self.use_memory:
            from .agent_memory import recall_memory
            memory_data = recall_memory(topic)
            state['memory_data'] = memory_data
        
        state['iteration'] = iteration + 1
        state['current_step'] = 'data_gathered'
        
        ad_count = len(competitor_data.get('hooks', [])) if competitor_data else 0
        state['messages'].append({
            'role': 'assistant',
            'content': f"Found {ad_count} competitor ads. Evaluating data quality..."
        })
        
        return state
    
    def _should_gather_more(self, state: AgentState) -> str:
        """Decide if we should gather more data or proceed."""
        competitor_data = state.get('competitor_data', {})
        iteration = state.get('iteration', 0)
        max_iterations = state.get('max_iterations', self.max_iterations)
        
        ad_count = len(competitor_data.get('hooks', [])) if competitor_data else 0
        
        if ad_count >= self.min_ads or iteration >= max_iterations:
            return "generate" if ad_count > 0 else "evaluate"
        
        return "evaluate"
    
    def _evaluate_node(self, state: AgentState) -> AgentState:
        """Evaluate if we have enough data to generate quality hooks."""
        print("\n[AGENT] Evaluating data sufficiency...")
        
        competitor_data = state.get('competitor_data', {})
        trend_data = state.get('trend_data', {})
        memory_data = state.get('memory_data', {})
        iteration = state.get('iteration', 0)
        max_iterations = state.get('max_iterations', self.max_iterations)
        
        ad_count = len(competitor_data.get('hooks', [])) if competitor_data else 0
        hooks_list = competitor_data.get('hooks', []) if competitor_data else []
        ads_with_offers = len([h for h in hooks_list if isinstance(h, dict) and h.get('offer') and h.get('offer') != 'N/A'])
        
        # Get evaluator prompt from config
        eval_prompt = config.AI_PROMPTS['thinking_agent']['data_evaluator'].format(
            ad_count=ad_count,
            min_required=self.min_ads,
            ads_with_offers=ads_with_offers,
            unique_angles=len(set(h.get('angle', '') for h in hooks_list if isinstance(h, dict) and h.get('angle'))),
            trend_summary=json.dumps(trend_data, indent=2) if trend_data else "No trend data",
            memory_summary=json.dumps(memory_data, indent=2) if memory_data else "No memory data"
        )
        
        decision = "generate"  # Default
        
        if api_keys.ANTHROPIC_CLIENT:
            try:
                response = api_keys.ANTHROPIC_CLIENT.messages.create(
                    model=api_keys.get_model_for_task('ad_analysis'),
                    max_tokens=500,
                    messages=[{"role": "user", "content": eval_prompt}]
                )
                
                # Safely extract text from response
                if response.content and len(response.content) > 0:
                    content_item = response.content[0]
                    if hasattr(content_item, 'text'):
                        eval_text = getattr(content_item, 'text', str(content_item))
                    else:
                        eval_text = str(content_item)
                else:
                    eval_text = ""
                
                try:
                    if "```" in eval_text:
                        eval_text = eval_text.split("```")[1]
                        if eval_text.startswith("json"):
                            eval_text = eval_text[4:]
                    evaluation = json.loads(eval_text.strip())
                    
                    if not evaluation.get('sufficient', True) and iteration < max_iterations:
                        decision = "gather_more"
                        state['context']['next_query'] = evaluation.get('next_query', '')
                    elif ad_count == 0:
                        decision = "end"
                        
                except json.JSONDecodeError:
                    pass
                    
            except Exception as e:
                print(f"[AGENT] Evaluation failed: {e}")
        
        state['decision'] = decision
        state['current_step'] = 'evaluated'
        
        if decision == "gather_more":
            state['messages'].append({
                'role': 'assistant',
                'content': f"Not enough data ({ad_count} ads). Broadening search..."
            })
        elif decision == "end":
            state['messages'].append({
                'role': 'assistant',
                'content': "Could not find enough competitor data. Please try a different topic."
            })
        else:
            state['messages'].append({
                'role': 'assistant',
                'content': f"Data quality is sufficient ({ad_count} ads). Generating hooks..."
            })
        
        return state
    
    def _evaluate_decision(self, state: AgentState) -> str:
        """Return the decision from evaluation."""
        decision = state.get('decision')
        return decision if decision is not None else 'generate'
    
    def _generate_node(self, state: AgentState) -> AgentState:
        """Generate hooks based on gathered data."""
        print("\n[AGENT] Generating hooks...")
        
        context = state.get('context', {})
        competitor_data = state.get('competitor_data', {})
        trend_data = state.get('trend_data', {})
        
        # Import headline generator
        from ..headline_generator import generate_headlines, generate_proven_hooks
        
        offers = context.get('offers', [])
        total_count = context.get('count', 20)  # Total hooks to generate across all ragebait levels
        unique_offer_count = context.get('unique_offer_count', total_count)
        ragebait_levels = context.get('ragebait_levels', [context.get('ragebait_level', 3)])  # Support list or single value
        offer_type = context.get('offer_type', 'service')
        
        # If ragebait_levels is a single int, convert to list
        if isinstance(ragebait_levels, int):
            ragebait_levels = [ragebait_levels]
        
        # Calculate count per ragebait level
        num_ragebait_levels = len(ragebait_levels)
        count_per_level = total_count // num_ragebait_levels
        remainder = total_count % num_ragebait_levels
        
        # Calculate hooks per source offer per ragebait level for even distribution
        # This ensures each unique offer is represented equally at each ragebait level
        hooks_per_source_offer_per_level = None
        if unique_offer_count != total_count:
            hooks_per_offer = total_count / unique_offer_count
            hooks_per_source_offer_per_level = int(hooks_per_offer / num_ragebait_levels)
            # Ensure at least 1 hook per source per level
            hooks_per_source_offer_per_level = max(1, hooks_per_source_offer_per_level)
            print(f"[AGENT] Unique offer mode: {unique_offer_count} unique offers")
            print(f"[AGENT] Distribution: {hooks_per_offer:.1f} total hooks per offer, {hooks_per_source_offer_per_level} per ragebait level")
        
        if num_ragebait_levels > 1:
            print(f"[AGENT] Multi-ragebait mode: {num_ragebait_levels} levels")
            print(f"[AGENT] Base count per level: {count_per_level} (remainder: {remainder})")
        
        # Collect hooks from all ragebait levels
        all_unique_hooks = []
        all_proven_hooks = []
        
        # Generate hooks for each ragebait level using the same competitor_data
        for level_idx, ragebait_level in enumerate(ragebait_levels):
            # Distribute remainder to first levels
            level_count = count_per_level + (1 if level_idx < remainder else 0)
            
            if level_count == 0:
                continue
            
            if num_ragebait_levels > 1:
                print(f"\n[AGENT] RAGEBAIT LEVEL {ragebait_level} ({level_count} hooks)")
            
            # Count applies to BOTH types: unique hooks (research-based) AND proven hooks (competitor-based)
            # If level_count=25: generates 25 unique + 25 proven = 50 total for this level
            num_unique = level_count
            num_proven = level_count
            
            # Generate unique hooks using Perplexity research data to find untargeted pain points
            print(f"[AGENT] Generating {num_unique} unique hooks at ragebait level {ragebait_level}...")
            level_unique_hooks = generate_headlines(
                num_hooks=num_unique,
                offers=offers,
                offer_type=offer_type,
                trend_data=trend_data,  # Pass research data to find gaps
                ragebait_level=ragebait_level,
                competitor_data=competitor_data  # Pass competitor data for enhanced gap analysis
            )
            
            # Tag each hook with its ragebait level
            if isinstance(level_unique_hooks, list):
                for h in level_unique_hooks:
                    h['ragebait_level'] = ragebait_level
                all_unique_hooks.extend(level_unique_hooks)
            
            # Generate proven hooks using Facebook competitor data
            level_proven_hooks = []
            if competitor_data and competitor_data.get('hooks'):
                print(f"[AGENT] Generating {num_proven} proven fusion hooks at ragebait level {ragebait_level}...")
                level_proven_hooks = generate_proven_hooks(
                    competitor_data=competitor_data,
                    num_hooks=num_proven,
                    offers=offers,
                    offer_type=offer_type,
                    ragebait_level=ragebait_level,
                    hooks_per_source_offer=hooks_per_source_offer_per_level
                )
                
                # Tag each proven hook with its ragebait level
                if isinstance(level_proven_hooks, list):
                    for h in level_proven_hooks:
                        h['ragebait_level'] = ragebait_level
                    all_proven_hooks.extend(level_proven_hooks)
            else:
                print(f"[WARNING] No competitor data available, skipping proven hooks generation for level {ragebait_level}")
            
            print(f"[AGENT] Ragebait {ragebait_level}: {len(level_unique_hooks) if isinstance(level_unique_hooks, list) else 0} unique, {len(level_proven_hooks)} proven")
        
        # Ensure hooks is a dict structure
        hooks_dict: Dict[str, List[Dict[str, Any]]] = {
            'unique': all_unique_hooks if isinstance(all_unique_hooks, list) else [],
            'proven': all_proven_hooks if isinstance(all_proven_hooks, list) else []
        }
        state['hooks'] = hooks_dict  # type: ignore
        state['current_step'] = 'generated'
        
        total = len(all_unique_hooks) + len(all_proven_hooks)
        state['messages'].append({
            'role': 'assistant',
            'content': f"Generated {total} hooks ({len(all_unique_hooks)} unique, {len(all_proven_hooks)} proven) across {num_ragebait_levels} ragebait level(s)."
        })
        
        return state
    
    def _refine_node(self, state: AgentState) -> AgentState:
        """Offer to refine hooks."""
        print("\n[AGENT] Ready for refinement...")
        
        hooks = state.get('hooks', {})
        context = state.get('context', {})
        
        # Save to memory if enabled
        if self.use_memory and hooks:
            from .agent_memory import save_memory
            
            # Handle hooks as dict or list
            if isinstance(hooks, dict):
                unique_list = hooks.get('unique', []) if isinstance(hooks.get('unique'), list) else []
                proven_list = hooks.get('proven', []) if isinstance(hooks.get('proven'), list) else []
            else:
                unique_list = []
                proven_list = []
            
            memory_entry = {
                'niche': context.get('topic', ''),
                'hooks_generated': len(unique_list) + len(proven_list),
                'ragebait_level': context.get('ragebait_level', 3),
                'timestamp': datetime.now().isoformat()
            }
            save_memory(context.get('topic', ''), memory_entry)
        
        # Handle hooks as dict or list for message formatting
        if isinstance(hooks, dict):
            unique_list = hooks.get('unique', []) if isinstance(hooks.get('unique'), list) else []
            proven_list = hooks.get('proven', []) if isinstance(hooks.get('proven'), list) else []
        else:
            unique_list = []
            proven_list = []
        
        state['current_step'] = 'complete'
        state['messages'].append({
            'role': 'assistant',
            'content': config.AI_PROMPTS['conversational']['confirm_export'].format(
                count=len(unique_list) + len(proven_list),
                niche=context.get('topic', 'your niche'),
                unique_count=len(unique_list),
                proven_count=len(proven_list),
                ragebait_level=context.get('ragebait_level', 3),
                templates=context.get('templates', 'default')
            )
        })
        
        return state
    
    def _broaden_topic(self, topic: str, iteration: int) -> str:
        """Broaden the search topic for subsequent iterations."""
        # Simple broadening strategies
        broaden_strategies = [
            lambda t: t,  # Original
            lambda t: t.split()[0] if ' ' in t else t,  # First word only
            lambda t: f"{t} services",  # Add "services"
            lambda t: t.replace('exterior', '').replace('interior', '').strip(),  # Remove specifics
        ]
        
        if iteration < len(broaden_strategies):
            return broaden_strategies[iteration](topic)
        return topic
    
    def run(
        self,
        task: str,
        topic: str,
        offers: Optional[List[str]] = None,
        count: int = 20,
        unique_offer_count: Optional[int] = None,
        ragebait_level: Optional[Union[int, List[int]]] = None,
        offer_type: str = "service",
        templates: Optional[List[int]] = None,
        positive_keywords: Optional[List[str]] = None,
        negative_keywords: Optional[List[str]] = None,
        auto_generate_keywords: bool = True,
        skip_offer_filters: bool = False,
        max_ads: int = 30
    ) -> Dict[str, Any]:
        """
        Run the thinking agent.
        
        Args:
            task: Description of what to do
            topic: Topic/niche for research
            offers: List of offers
            count: Total number of hooks to generate (divided across ragebait levels)
            unique_offer_count: Number of unique offers to find from Facebook.
                               Defaults to count. If different, hooks are distributed across offers.
            ragebait_level: Ragebait intensity (0-10) or list of levels. Defaults to [3] if None.
            offer_type: Type of offer
            templates: Template IDs to use
            positive_keywords: List of positive/required keywords (max 2)
            negative_keywords: List of negative/exclusion keywords (max 5)
            auto_generate_keywords: Whether to auto-generate keywords with Claude
            skip_offer_filters: Skip generating and using filters for offers
            max_ads: Maximum number of ads to scrape (controls scroll_limit, default: 30)
            
        Returns:
            Final state with generated hooks
        """
        # Normalize ragebait_level to list
        if ragebait_level is None:
            ragebait_levels = [3]
        elif isinstance(ragebait_level, int):
            ragebait_levels = [ragebait_level]
        else:
            ragebait_levels = ragebait_level
        
        # Default unique_offer_count to count if not specified
        unique_offer_count = unique_offer_count or count
        
        initial_state: AgentState = {
            'messages': [{'role': 'user', 'content': task}],
            'task': task,
            'context': {
                'topic': topic,
                'offers': offers or [],
                'count': count,  # Total count - will be divided across ragebait levels in _generate_node
                'unique_offer_count': unique_offer_count,  # How many unique offers to find
                'ragebait_levels': ragebait_levels,  # Pass as list
                'ragebait_level': ragebait_levels[0] if ragebait_levels else 3,  # Keep for backward compatibility
                'offer_type': offer_type,
                'templates': templates or [],
                'positive_keywords': positive_keywords or [],
                'negative_keywords': negative_keywords or [],
                'auto_generate_keywords': auto_generate_keywords,
                'skip_offer_filters': skip_offer_filters,
                'max_ads': max_ads
            },
            'competitor_data': None,
            'trend_data': None,
            'memory_data': None,
            'hooks': {'unique': [], 'proven': []},  # type: ignore
            'current_step': 'start',
            'decision': None,
            'iteration': 0,
            'max_iterations': self.max_iterations
        }
        
        # Run the graph
        final_state = self.graph.invoke(initial_state)
        
        return final_state
