from pathlib import Path
import sys
import os

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from hook_generator.image_generator import generate_hook_image, batch_generate_images
from hook_generator import config

def test():
    headlines = [
        "Stop letting one ugly room ruin your entire home's vibe - $350 per room painting",
        "Why your kitchen cabinets make guests judge your entire house instantly",
        "Room-by-room painting at $350 each - finally affordable without the wait"
    ]
    output_dir = Path("test_images")
    
    print(f"Testing batch image generation for {len(headlines)} images...")
    results = batch_generate_images(headlines, output_dir)
    
    success_count = sum(1 for r in results if r['success'])
    print(f"RESULTS: {success_count}/{len(headlines)} successful")
    
    for r in results:
        if not r['success']:
            print(f"FAILED {r['index']}: {r['message']}")

if __name__ == "__main__":
    test()

