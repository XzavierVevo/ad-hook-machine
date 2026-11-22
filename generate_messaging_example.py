import sys
from pathlib import Path

# Add the project directory to sys.path
sys.path.insert(0, str(Path.cwd()))

from hook_generator import config
from hook_generator.image_generator import generate_hook_image
from hook_generator.templates import get_template

def main():
    print("Generating messaging-style ad example using phone template...")
    
    # Use the phone template image as background
    phone_template_path = Path("phone template (1).png")
    
    if not phone_template_path.exists():
        print(f"ERROR: Phone template not found at: {phone_template_path.absolute()}")
        return
    
    print(f"Using phone template: {phone_template_path}")
    
    # Get the messaging template (ID 9)
    template = get_template(9)
    
    if not template:
        print("ERROR: Could not find messaging template!")
        return
    
    print(f"Using template: {template.name}")
    
    # Generate image with phone template as background
    output_dir = config.OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "messaging_example.png"
    
    # Example text with at least 30 words
    example_text = "Have you shopped Glossier's sale yet? Up to 30% off ends tonight!! This is an amazing opportunity to get your favorite products at incredible prices. Don't miss out on these exclusive deals that won't last long. Shop now before it's too late and stock up on all your beauty essentials."
    
    try:
        # Generate with example text
        success, message = generate_hook_image(
            headline=example_text,
            output_path=output_path,
            template=template,
            background_path=phone_template_path
        )
        if success:
            print(f"\nSUCCESS! Image generated at: {output_path.absolute()}")
            print(f"Full path: {output_path.resolve()}")
        else:
            print(f"Failed to generate image: {message}")
    except Exception as e:
        import traceback
        print(f"Error during image generation: {e}")
        print(traceback.format_exc())

if __name__ == "__main__":
    main()
