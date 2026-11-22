import sys
from pathlib import Path

# Add the current directory to the path so we can import hook_generator
sys.path.append(str(Path.cwd()))

from hook_generator.image_generator import generate_hook_image

def create_example():
    headline = "Stop overpaying for home painting services in your local area today. Get a professional quote in seconds and save thousands on your next project."
    output_path = Path.cwd() / "long_text_auto_fit.png"
    
    print(f"Generating example image with LONG headline: '{headline}'")
    success, message = generate_hook_image(headline, output_path)
    
    if success:
        print(f"SUCCESS: Example image created at {output_path}")
    else:
        print(f"FAILED: {message}")

if __name__ == "__main__":
    create_example()

