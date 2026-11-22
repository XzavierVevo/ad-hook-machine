import json
import sys
import asyncio
from pathlib import Path

# Add the project root to the path for imports
sys.path.insert(0, str(Path(__file__).parent))

from hook_generator.image_generator import batch_generate_images
from hook_generator.campaign_setup import update_campaign_status

async def regenerate_campaign_images(metadata_path: str):
    """
    Load a campaign's metadata and headlines to (re)generate all images.
    """
    path = Path(metadata_path)
    
    # If a directory is provided, look for campaign_metadata.json inside it
    if path.is_dir():
        path = path / "campaign_metadata.json"
        
    if not path.exists():
        print(f"[ERROR] Metadata file not found at: {path}")
        return

    # 1. Load Metadata
    try:
        with open(path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
    except Exception as e:
        print(f"[ERROR] Failed to read metadata at {path}: {e}")
        return

    campaign_folder = path.parent
    headlines_dir = campaign_folder / "headlines"
    images_dir = campaign_folder / "images"
    
    print(f"\n[PROCESS] Regenerating images for campaign: {metadata.get('campaign_name')}")
    print(f"[PROCESS] Folder: {campaign_folder}")

    # 2. Find the latest headlines file
    headline_files = list(headlines_dir.glob("headlines_*.json"))
    if not headline_files:
        print(f"[ERROR] No headlines found in {headlines_dir}")
        return
    
    # Use the most recent headlines file
    latest_headlines_file = sorted(headline_files)[-1]
    print(f"[INFO] Using headlines from: {latest_headlines_file.name}")

    with open(latest_headlines_file, 'r', encoding='utf-8') as f:
        headlines_data = json.load(f)

    headline_texts = [h.get('headline', '') for h in headlines_data]
    
    if not headline_texts:
        print("[ERROR] No headline text found in the file.")
        return

    # 3. Generate Images
    print(f"[INFO] Generating {len(headline_texts)} images...")
    images_dir.mkdir(exist_ok=True)
    
    # We use asyncio.to_thread because batch_generate_images uses multiprocessing
    results = await asyncio.to_thread(
        batch_generate_images,
        headlines=headline_texts,
        output_dir=images_dir
    )

    success_count = sum(1 for r in results if r['success'])
    fail_count = len(headline_texts) - success_count

    # 4. Update Metadata
    update_campaign_status(campaign_folder, "images_regenerated", {
        'images_generated': success_count,
        'images_failed': fail_count
    })

    print("\n" + "="*60)
    print(f"  IMAGE GENERATION COMPLETE")
    print(f"  Success: {success_count}")
    print(f"  Failed:  {fail_count}")
    print(f"  Output:  {images_dir}")
    print("="*60 + "\n")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python regenerate_images.py path/to/campaign_metadata.json")
        sys.exit(1)
    
    metadata_file = sys.argv[1]
    asyncio.run(regenerate_campaign_images(metadata_file))

