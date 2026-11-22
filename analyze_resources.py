"""
Script to analyze resource files and calculate average words/characters per headline.
"""

import re
from pathlib import Path
from typing import List, Tuple

# Import the same loading logic
import sys
sys.path.insert(0, str(Path(__file__).parent))

from hook_generator import config

def load_resource_documents() -> dict:
    """Load resource documents using the same method as headline_generator.py"""
    resources = {}
    
    resource_files = {
        'direct_response_headline_engine': 'THE DIRECT RESPONSE HEADLINE ENGINE (1).docx',
        '100_greatest_headlines': '100 Greatest headlines ever used (1).docx',
        'halbert_swipe_file': 'pdfcoffee.com-reference-349-great-headlines.pdf'
    }
    
    for resource_name, filename in resource_files.items():
        resource_path = config.RESOURCES_DIR / filename
        if resource_path.exists():
            try:
                content = None
                
                if filename.endswith('.docx'):
                    try:
                        from docx import Document
                        doc = Document(resource_path)
                        content = '\n'.join([para.text for para in doc.paragraphs])
                    except ImportError:
                        print(f"[WARNING] python-docx not installed")
                        continue
                    except Exception as e:
                        print(f"[WARNING] Could not load {filename}: {e}")
                        continue
                
                elif filename.endswith('.pdf'):
                    try:
                        import PyPDF2
                        with open(resource_path, 'rb') as f:
                            pdf_reader = PyPDF2.PdfReader(f)
                            pages_text = []
                            for page in pdf_reader.pages:
                                page_text = page.extract_text()
                                if page_text:
                                    pages_text.append(page_text)
                            content = '\n'.join(pages_text)
                            if not content or len(content.strip()) < 10:
                                # Try alternative extraction method
                                print(f"[INFO] PDF content seems empty, trying alternative extraction...")
                                content = '\n'.join([page.extract_text(extraction_mode="layout") for page in pdf_reader.pages if page.extract_text()])
                    except ImportError:
                        print(f"[WARNING] PyPDF2 not installed")
                        continue
                    except Exception as e:
                        print(f"[WARNING] Could not load {filename}: {e}")
                        continue
                
                if content:
                    resources[resource_name] = content
                    print(f"[OK] Loaded resource: {filename}")
            
            except Exception as e:
                print(f"[WARNING] Could not load {filename}: {e}")
        else:
            print(f"[INFO] Resource file not found: {filename}")
    
    return resources

def extract_headlines(content: str, resource_name: str) -> List[str]:
    """
    Extract headlines from content. This is a heuristic approach that looks for:
    - Numbered lists (1., 2., etc.)
    - Lines that are likely headlines (short, capitalized, etc.)
    - Lines separated by newlines that look like headlines
    """
    headlines = []
    lines = content.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Skip very long lines (likely paragraphs)
        if len(line) > 150:
            continue
        
        # Skip lines that are clearly not headlines
        if line.lower().startswith(('chapter', 'section', 'page', 'table of', 'introduction', 'contents')):
            continue
        
        # Skip lines that are all numbers or mostly numbers
        if re.match(r'^[\d\s\.\-]+$', line):
            continue
        
        # For "100 Greatest Headlines" - look for numbered entries
        if resource_name == '100_greatest_headlines':
            # Match numbered patterns: "1. Headline" or "1) Headline"
            match = re.match(r'^\d+[\.\)]\s*(.+)$', line)
            if match:
                headline = match.group(1).strip()
                # Remove quotes if present
                headline = headline.strip('"\'')
                if 5 <= len(headline) <= 150 and len(headline.split()) >= 3:
                    headlines.append(headline)
            # Also check for quoted headlines
            elif (line.startswith('"') and line.endswith('"')) or (line.startswith("'") and line.endswith("'")):
                headline = line[1:-1].strip()
                if 5 <= len(headline) <= 150 and len(headline.split()) >= 3:
                    headlines.append(headline)
            # Check for lines that look like headlines (reasonable length, not all caps)
            elif 10 <= len(line) <= 120:
                # Should have some words, not be all punctuation
                words = line.split()
                if len(words) >= 3 and not all(len(w) == 1 for w in words):
                    # Check if it's likely a headline (has some capitalization or is title case)
                    if any(c.isupper() for c in line) or line.istitle():
                        headlines.append(line)
        
        # For "349 Great Headlines" PDF - similar approach
        elif resource_name == 'halbert_swipe_file':
            # Look for numbered entries (more flexible pattern)
            match = re.match(r'^\d+[\.\)\-\s]*(.+)$', line)
            if match:
                headline = match.group(1).strip()
                headline = headline.strip('"\'')
                if 5 <= len(headline) <= 150 and len(headline.split()) >= 3:
                    headlines.append(headline)
            # Check for quoted headlines
            elif (line.startswith('"') and line.endswith('"')) or (line.startswith("'") and line.endswith("'")):
                headline = line[1:-1].strip()
                if 5 <= len(headline) <= 150 and len(headline.split()) >= 3:
                    headlines.append(headline)
            # Check for standalone headline-like lines (more permissive for PDF)
            elif 8 <= len(line) <= 130:
                words = line.split()
                if len(words) >= 2 and not all(len(w) == 1 for w in words):
                    # Should look like a headline
                    # PDFs often have formatting issues, so be more lenient
                    if not line.lower().startswith(('page', 'copyright', 'table of')):
                        # Check if it has reasonable headline characteristics
                        if any(c.isupper() for c in line[:30]) or line.istitle():
                            headlines.append(line)
        
        # For "Direct Response Headline Engine" - extract example headlines
        elif resource_name == 'direct_response_headline_engine':
            # Look for quoted examples
            if (line.startswith('"') and line.endswith('"')) or (line.startswith("'") and line.endswith("'")):
                headline = line[1:-1].strip()
                if 5 <= len(headline) <= 150 and len(headline.split()) >= 3:
                    headlines.append(headline)
            # Look for numbered examples
            elif re.match(r'^\d+[\.\)]\s*(.+)$', line):
                match = re.match(r'^\d+[\.\)]\s*(.+)$', line)
                headline = match.group(1).strip()
                headline = headline.strip('"\'')
                if 5 <= len(headline) <= 150 and len(headline.split()) >= 3:
                    headlines.append(headline)
            # Look for example headlines that might be formatted differently
            elif 10 <= len(line) <= 120:
                words = line.split()
                if len(words) >= 3:
                    # Check if it looks like a headline example (not explanatory text)
                    if not line.lower().startswith(('example', 'note', 'tip', 'remember', 'important')):
                        if any(c.isupper() for c in line[:20]):  # First part should have caps
                            headlines.append(line)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_headlines = []
    for h in headlines:
        h_lower = h.lower().strip()
        if h_lower not in seen and len(h_lower) > 0:
            seen.add(h_lower)
            unique_headlines.append(h)
    
    return unique_headlines

def analyze_headlines(headlines: List[str]) -> Tuple[float, float, dict]:
    """
    Calculate statistics for headlines.
    Returns: (avg_words, avg_chars, stats_dict)
    """
    if not headlines:
        return 0, 0, {}
    
    word_counts = []
    char_counts = []
    
    for headline in headlines:
        words = headline.split()
        word_count = len(words)
        char_count = len(headline)  # Includes spaces
        
        word_counts.append(word_count)
        char_counts.append(char_count)
    
    avg_words = sum(word_counts) / len(word_counts)
    avg_chars = sum(char_counts) / len(char_counts)
    
    sorted_words = sorted(word_counts)
    sorted_chars = sorted(char_counts)
    mid = len(sorted_words) // 2
    
    stats = {
        'total_headlines': len(headlines),
        'min_words': min(word_counts),
        'max_words': max(word_counts),
        'min_chars': min(char_counts),
        'max_chars': max(char_counts),
        'median_words': sorted_words[mid] if sorted_words else 0,
        'median_chars': sorted_chars[mid] if sorted_chars else 0,
    }
    
    return avg_words, avg_chars, stats

def main():
    print("=" * 60)
    print("RESOURCE HEADLINE ANALYSIS")
    print("=" * 60)
    print()
    
    resources = load_resource_documents()
    
    if not resources:
        print("No resources loaded. Make sure python-docx and PyPDF2 are installed.")
        return
    
    all_headlines = []
    file_stats = {}
    
    for resource_name, content in resources.items():
        print(f"\nAnalyzing: {resource_name}")
        print("-" * 60)
        
        headlines = extract_headlines(content, resource_name)
        print(f"Extracted {len(headlines)} potential headlines")
        
        if headlines:
            avg_words, avg_chars, stats = analyze_headlines(headlines)
            
            file_stats[resource_name] = {
                'headlines': headlines,
                'avg_words': avg_words,
                'avg_chars': avg_chars,
                'stats': stats
            }
            
            all_headlines.extend(headlines)
            
            print(f"Average words per headline: {avg_words:.2f}")
            print(f"Average characters per headline (including spaces): {avg_chars:.2f}")
            print(f"Word range: {stats['min_words']} - {stats['max_words']}")
            print(f"Character range: {stats['min_chars']} - {stats['max_chars']}")
            print(f"Median words: {stats['median_words']}")
            print(f"Median characters: {stats['median_chars']}")
            
            # Show first 5 examples
            print(f"\nFirst 5 examples:")
            for i, h in enumerate(headlines[:5], 1):
                print(f"  {i}. \"{h}\" ({len(h.split())} words, {len(h)} chars)")
        else:
            print("No headlines extracted.")
            if content:
                print(f"Content length: {len(content)} characters")
                print("Content preview (first 1000 chars):")
                print(content[:1000])
                print("\nFirst 20 lines:")
                for i, line in enumerate(content.split('\n')[:20], 1):
                    print(f"  {i}: {repr(line[:80])}")
            else:
                print("Content is empty or None")
    
    # Overall statistics
    if all_headlines:
        print("\n" + "=" * 60)
        print("OVERALL STATISTICS (All Resources Combined)")
        print("=" * 60)
        
        avg_words, avg_chars, stats = analyze_headlines(all_headlines)
        
        print(f"Total headlines analyzed: {stats['total_headlines']}")
        print(f"Average words per headline: {avg_words:.2f}")
        print(f"Average characters per headline (including spaces): {avg_chars:.2f}")
        print(f"Word range: {stats['min_words']} - {stats['max_words']}")
        print(f"Character range: {stats['min_chars']} - {stats['max_chars']}")
        print(f"Median words: {stats['median_words']}")
        print(f"Median characters: {stats['median_chars']}")
        
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"Average words per hook: {avg_words:.2f}")
        print(f"Average characters per hook (including spaces): {avg_chars:.2f}")

if __name__ == '__main__':
    main()

