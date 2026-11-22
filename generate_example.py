import sys
import os
from pathlib import Path

# Add the project directory to sys.path
sys.path.insert(0, str(Path.cwd()))

from hook_generator import api_keys, config
from hook_generator.quote_scraper import scrape_quotes
from hook_generator.headline_generator import generate_headlines
from hook_generator.image_generator import generate_hook_image

def main():
    print("Initializing example generation...")
    # Load API keys
    api_keys.load_api_keys()
    api_keys.initialize_clients()
    
    # Topic and Offer
    topic = "residential painting"
    offers = ["Fresh Paint in Every Room by Saturday for $350 Each"]
    
    print(f"Generating quote for topic: {topic}...")
    # Step 1: Generate 1 quote
    try:
        quotes = scrape_quotes(topic=topic, num_quotes=1, offers=offers)
        if not quotes:
            print("Failed to generate quote. Please check your API keys.")
            return
    except Exception as e:
        print(f"Error during quote generation: {e}")
        return

    print("Generating headline (hook) from quote...")
    # Step 2: Generate 1 headline
    try:
        headlines = generate_headlines(num_hooks=1, offers=offers)
        if not headlines:
            print("Failed to generate headline.")
            return
    except Exception as e:
        print(f"Error during headline generation: {e}")
        return
    
    headline_text = headlines[0]['headline']
    print(f"\nSUCCESS! Generated Hook:")
    print(f"\" {headline_text} \"")
    
    # Step 3: Generate image
    print("\nGenerating image for the hook...")
    output_dir = config.OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "example_hook_single.png"
    
    try:
        success, message = generate_hook_image(headline_text, output_path)
        if success:
            print(f"SUCCESS! Image generated at: {output_path.absolute()}")
        else:
            print(f"Failed to generate image: {message}")
    except Exception as e:
        print(f"Error during image generation: {e}")

if __name__ == "__main__":
    main()

