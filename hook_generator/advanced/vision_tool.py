"""
Vision Analysis Tool - AI-powered image analysis for competitor ads.

This tool uses multimodal AI (Gemini Flash or GPT-4 Vision) to analyze
competitor ad images for visual patterns, text extraction, and style analysis.
"""

import json
import base64
from pathlib import Path
from typing import Dict, Any, List, Optional
import requests

from .agent_tools import register_tool
from .. import api_keys
from .. import config
from ..cache_manager import get_cached, set_cached, track_cost


def _encode_image_to_base64(image_path: str) -> str:
    """Encode an image file to base64."""
    with open(image_path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def _get_image_media_type(image_path: str) -> str:
    """Get the media type for an image file."""
    suffix = Path(image_path).suffix.lower()
    media_types = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.webp': 'image/webp'
    }
    return media_types.get(suffix, 'image/jpeg')


@register_tool(
    name="analyze_ad_image",
    description="Analyze a competitor ad image to extract text, colors, layout, and visual patterns.",
    parameters={
        "image_path": {"type": "string", "description": "Path to the image file to analyze"},
        "image_url": {"type": "string", "description": "URL of the image to analyze (alternative to path)"}
    }
)
def analyze_ad_image(
    image_path: Optional[str] = None,
    image_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Analyze a single ad image for visual patterns.
    
    Args:
        image_path: Local path to image file
        image_url: URL of image (used if path not provided)
        
    Returns:
        Dictionary with visual analysis results
    """
    if not image_path and not image_url:
        return {
            'success': False,
            'error': 'Either image_path or image_url must be provided'
        }
    
    source = image_path or image_url
    print(f"\n[TOOL: analyze_ad_image] Analyzing image...")
    
    # Check cache
    cache_key = f"vision:{source}"
    cached = get_cached('vision_analysis', cache_key)
    if cached:
        print(f"[TOOL] Using cached vision analysis")
        return cached
    
    # Get analysis prompt from config
    analysis_prompt = config.AI_PROMPTS['vision_analysis']['analyze_ad_image']
    
    # Try to use OpenAI Vision (GPT-4o) first
    if api_keys.OPENAI_CLIENT:
        try:
            # Build message content
            content = [{"type": "text", "text": analysis_prompt}]
            
            if image_path and Path(image_path).exists():
                base64_image = _encode_image_to_base64(image_path)
                media_type = _get_image_media_type(image_path)
                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{media_type};base64,{base64_image}"
                    }
                })
            elif image_url:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": image_url}
                })
            
            response = api_keys.OPENAI_CLIENT.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "user", "content": content}
                ],
                max_tokens=500
            )
            
            # Track cost
            if hasattr(response, 'usage'):
                track_cost('gpt-4o', response.usage.prompt_tokens, response.usage.completion_tokens)
            
            result_text_raw = response.choices[0].message.content
            if result_text_raw is None:
                return {'success': False, 'error': 'No content in response'}
            result_text = result_text_raw
            
            # Parse JSON
            try:
                if "```" in result_text:
                    result_text = result_text.split("```")[1]
                    if result_text.startswith("json"):
                        result_text = result_text[4:]
                analysis = json.loads(result_text.strip())
            except json.JSONDecodeError:
                analysis = {
                    'text_content': '',
                    'colors': {},
                    'layout': 'unknown',
                    'font_style': 'unknown',
                    'visual_elements': [],
                    'vibe': 'unknown',
                    'hook_effectiveness': 5,
                    'raw_analysis': result_text
                }
            
            result = {
                'success': True,
                'source': source,
                **analysis
            }
            
            # Cache result
            set_cached('vision_analysis', cache_key, result)
            
            return result
            
        except Exception as e:
            print(f"[TOOL WARNING] OpenAI vision failed: {e}")

    # Try Gemini Vision via Vertex AI as fallback
    if api_keys.GOOGLE_CLOUD_PROJECT:
        try:
            import vertexai
            from vertexai.generative_models import GenerativeModel, Image, Part
            
            # Initialize Vertex AI
            vertexai.init(project=api_keys.GOOGLE_CLOUD_PROJECT)
            model = GenerativeModel("gemini-1.5-flash")
            
            # Prepare content
            content_parts = [analysis_prompt]
            
            if image_path and Path(image_path).exists():
                image_data = Image.load_from_file(image_path)
                content_parts.append(image_data)
            elif image_url:
                # Vertex AI prefers GCS URIs for images, but can handle raw bytes
                response = requests.get(image_url)
                if response.status_code == 200:
                    image_data = Image.from_bytes(response.content)
                    content_parts.append(image_data)
                else:
                    raise Exception(f"Failed to download image from {image_url}")
            
            # Generate content
            response = model.generate_content(content_parts)
            
            # Track cost (Gemini 1.5 Flash is cheap)
            track_cost('gemini-1.5-flash', 0, 0) # Flash cost tracking is complex, use placeholder
            
            result_text = response.text
            
            # Parse JSON
            try:
                if "```" in result_text:
                    result_text = result_text.split("```")[1]
                    if result_text.startswith("json"):
                        result_text = result_text[4:]
                analysis = json.loads(result_text.strip())
            except json.JSONDecodeError:
                analysis = {
                    'text_content': '',
                    'colors': {},
                    'layout': 'unknown',
                    'font_style': 'unknown',
                    'visual_elements': [],
                    'vibe': 'unknown',
                    'hook_effectiveness': 5,
                    'raw_analysis': result_text
                }
            
            result = {
                'success': True,
                'source': source,
                **analysis
            }
            
            # Cache result
            set_cached('vision_analysis', cache_key, result)
            
            return result
            
        except Exception as e:
            print(f"[TOOL WARNING] Gemini vision failed: {e}")

    # Fallback: Return empty analysis
    return {
        'success': False,
        'error': 'No vision API available',
        'text_content': '',
        'colors': {},
        'layout': 'unknown'
    }


@register_tool(
    name="summarize_visual_patterns",
    description="Analyze multiple competitor ad images to identify common visual patterns and differentiation opportunities.",
    parameters={
        "image_paths": {"type": "array", "description": "List of image file paths to analyze"},
        "image_urls": {"type": "array", "description": "List of image URLs to analyze"}
    }
)
def summarize_visual_patterns(
    image_paths: Optional[List[str]] = None,
    image_urls: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Analyze multiple images to find common patterns.
    
    Args:
        image_paths: List of local image paths
        image_urls: List of image URLs
        
    Returns:
        Dictionary with pattern summary
    """
    sources = (image_paths or []) + (image_urls or [])
    
    if not sources:
        return {
            'success': False,
            'error': 'No images provided'
        }
    
    print(f"\n[TOOL: summarize_visual_patterns] Analyzing {len(sources)} images...")
    
    # Analyze each image
    analyses = []
    for source in sources[:10]:  # Limit to 10 images
        if source.startswith('http'):
            result = analyze_ad_image(image_url=source)
        else:
            result = analyze_ad_image(image_path=source)
        
        if result.get('success'):
            analyses.append(result)
    
    if not analyses:
        return {
            'success': False,
            'error': 'No images could be analyzed',
            'common_colors': [],
            'common_layouts': []
        }
    
    # Aggregate patterns
    all_colors = []
    all_layouts = []
    all_elements = []
    
    for a in analyses:
        if a.get('colors'):
            all_colors.extend(list(a['colors'].values()))
        if a.get('layout'):
            all_layouts.append(a['layout'])
        if a.get('visual_elements'):
            all_elements.extend(a['visual_elements'])
    
    # Find common patterns
    from collections import Counter
    
    color_counts = Counter(all_colors)
    layout_counts = Counter(all_layouts)
    element_counts = Counter(all_elements)
    
    return {
        'success': True,
        'images_analyzed': len(analyses),
        'common_colors': [c for c, _ in color_counts.most_common(5)],
        'common_layouts': [l for l, _ in layout_counts.most_common(3)],
        'common_elements': [e for e, _ in element_counts.most_common(5)],
        'oversaturated_patterns': [l for l, count in layout_counts.most_common(2) if count > len(analyses) * 0.5],
        'opportunity_patterns': [],
        'recommendation': 'Differentiate by using contrasting colors and unique layouts'
    }
