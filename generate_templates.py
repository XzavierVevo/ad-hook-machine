#!/usr/bin/env python3
"""
Command-line tool for generating ad images using different templates.

Usage:
    python generate_templates.py --hook "Your hook text" --template 1,2,3
    python generate_templates.py --hook "Your hook text" --all-templates
    python generate_templates.py --hook "Your hook text" --template 0 --emoji
    python generate_templates.py --hook "Your hook text" --all-templates --output ./my_ads/
"""

import argparse
import sys
from pathlib import Path

# Add the project root to the path for imports
sys.path.insert(0, str(Path(__file__).parent))

from hook_generator.templates import (
    get_template,
    get_all_templates,
    list_templates,
    TemplateConfig
)
from hook_generator.image_generator import generate_hook_image


def parse_template_ids(template_str: str) -> list:
    """Parse comma-separated template IDs into a list of integers."""
    if not template_str:
        return []
    
    ids = []
    for part in template_str.split(','):
        part = part.strip()
        if part:
            try:
                ids.append(int(part))
            except ValueError:
                print(f"[WARNING] Invalid template ID: {part}")
    return ids


def generate_with_templates(
    hook_text: str,
    template_ids: list,
    output_dir: Path,
    use_emoji: bool = False
) -> dict:
    """
    Generate images for the given hook using specified templates.
    
    Args:
        hook_text: The hook/headline text
        template_ids: List of template IDs to use
        output_dir: Directory to save generated images
        use_emoji: Whether to enable emoji rendering
        
    Returns:
        Dictionary with generation results
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    results = {
        'success': [],
        'failed': [],
        'skipped': []
    }
    
    for template_id in template_ids:
        template = get_template(template_id)
        
        if template is None:
            print(f"[WARNING] Template {template_id} not found, skipping")
            results['skipped'].append({
                'template_id': template_id,
                'reason': 'Template not found'
            })
            continue
        
        # Generate output filename
        filename = f"template_{template_id}_{template.name}.png"
        output_path = output_dir / filename
        
        print(f"[INFO] Generating template {template_id} ({template.name})...")
        
        success, message = generate_hook_image(
            headline=hook_text,
            output_path=output_path,
            template=template,
            use_emoji=use_emoji
        )
        
        if success:
            print(f"  [OK] Saved: {output_path}")
            results['success'].append({
                'template_id': template_id,
                'template_name': template.name,
                'path': str(output_path)
            })
        else:
            print(f"  [FAIL] {message}")
            results['failed'].append({
                'template_id': template_id,
                'template_name': template.name,
                'error': message
            })
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Generate ad images using different templates",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python generate_templates.py --hook "Stop Overpaying for Home Painting" --template 1,2,3
  python generate_templates.py --hook "Best deals ever!" --all-templates
  python generate_templates.py --hook "Limited Time Offer" --template 4 --emoji
  python generate_templates.py --list
        """
    )
    
    parser.add_argument(
        '--hook', '-H',
        type=str,
        help='The hook/headline text to render on the image'
    )
    
    parser.add_argument(
        '--template', '-t',
        type=str,
        help='Comma-separated list of template IDs (e.g., 0,1,2)'
    )
    
    parser.add_argument(
        '--all-templates', '-a',
        action='store_true',
        help='Generate images using all available templates'
    )
    
    parser.add_argument(
        '--emoji', '-e',
        action='store_true',
        help='Enable emoji rendering (requires pilmoji library)'
    )
    
    parser.add_argument(
        '--output', '-o',
        type=str,
        default='output/template_examples',
        help='Output directory for generated images (default: output/template_examples)'
    )
    
    parser.add_argument(
        '--list', '-l',
        action='store_true',
        help='List all available templates and exit'
    )
    
    args = parser.parse_args()
    
    # Handle --list flag
    if args.list:
        print(list_templates())
        return 0
    
    # Validate required arguments
    if not args.hook:
        parser.error("--hook is required unless using --list")
    
    if not args.template and not args.all_templates:
        parser.error("Either --template or --all-templates is required")
    
    # Determine which templates to use
    if args.all_templates:
        templates = get_all_templates()
        template_ids = [t.id for t in templates]
        print(f"[INFO] Using all {len(template_ids)} templates")
    else:
        template_ids = parse_template_ids(args.template)
        if not template_ids:
            parser.error("No valid template IDs provided")
        print(f"[INFO] Using templates: {template_ids}")
    
    # Set up output directory
    output_dir = Path(args.output)
    print(f"[INFO] Output directory: {output_dir.absolute()}")
    
    # Generate images
    print(f"\n[INFO] Hook text: \"{args.hook}\"")
    print(f"[INFO] Emoji rendering: {'enabled' if args.emoji else 'disabled'}")
    print("=" * 60)
    
    results = generate_with_templates(
        hook_text=args.hook,
        template_ids=template_ids,
        output_dir=output_dir,
        use_emoji=args.emoji
    )
    
    # Print summary
    print("\n" + "=" * 60)
    print("GENERATION SUMMARY")
    print("=" * 60)
    print(f"  Success: {len(results['success'])}")
    print(f"  Failed:  {len(results['failed'])}")
    print(f"  Skipped: {len(results['skipped'])}")
    
    if results['success']:
        print(f"\n  Output directory: {output_dir.absolute()}")
        print("  Generated files:")
        for item in results['success']:
            print(f"    - {Path(item['path']).name}")
    
    if results['failed']:
        print("\n  Failed generations:")
        for item in results['failed']:
            print(f"    - Template {item['template_id']}: {item['error'][:50]}...")
    
    print("=" * 60)
    
    # Return appropriate exit code
    if results['failed']:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
