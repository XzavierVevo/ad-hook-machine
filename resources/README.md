# Resources Folder

This folder contains copywriting resources that the bot references when generating headlines.

## Expected Files

The bot looks for these specific files in this folder:

1. **`THE DIRECT RESPONSE HEADLINE ENGINE (1).docx`**
   - The Direct Response Headline Engine principles
   - Core headline writing principles and frameworks
   - Supports .docx format

2. **`100 Greatest headlines ever used (1).docx`**
   - 100 Greatest Headlines Ever Used
   - Proven headline patterns and examples
   - Supports .docx format

3. **`pdfcoffee.com-reference-349-great-headlines.pdf`**
   - Halbert Swipe File (349 Great Headlines)
   - Additional headline examples and patterns
   - Supports .pdf format

## How It Works

When generating headlines, the bot will:
- Automatically load these files if they exist (supports .txt, .docx, and .pdf)
- Extract text content from documents
- Include their content in the prompt to Claude
- Use the principles and patterns to inform headline generation
- Continue working even if some files are missing (with a warning)

## File Format Support

- **Text files** (`.txt`): Plain text, UTF-8 encoding recommended
- **Word documents** (`.docx`): Automatically extracts text from paragraphs
- **PDF files** (`.pdf`): Extracts text from all pages

## Dependencies

The bot requires these packages for document reading:
- `python-docx` - For reading .docx files
- `PyPDF2` - For reading .pdf files

Install with: `pip install python-docx PyPDF2`

## Content Limits

- The bot will include up to 4000 characters from each file in the prompt
- Larger files will be truncated with a note that more content is available

## Notes

- If a file is missing, the bot will continue but may show an info message
- The bot prioritizes uniqueness and tailoring to your specific offers, even when using these resources
- These resources inform the generation but don't override the specific requirements for your campaign

