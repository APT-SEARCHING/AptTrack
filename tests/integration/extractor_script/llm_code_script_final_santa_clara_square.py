#!/usr/bin/env python3
import json
import re
import os

def extract_apartment_info(text):
    import re
    results = []
    pattern = re.compile(r'(?i)^\s*(PLAN\s*\d+[A-Z0-9]*)\b', re.MULTILINE)
    matches = list(pattern.finditer(text))
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        block = text[start:end]
        plan = ' '.join(m.group(1).strip().split()).upper()
        price = ""
        pm = re.search(r'\$\s*[\d,]+', block)
        if pm:
            price = pm.group(0).replace(' ', '')
        else:
            if re.search(r'No Availability', block, re.IGNORECASE):
                price = "No Availability"
        size = ""
        search_start = pm.end() if pm else 0
        size_re = re.compile(r'([\d,]{2,5}(?:\s*-\s*[\d,]{2,5})?)')
        srm = size_re.search(block, search_start)
        if not srm:
            srm = size_re.search(block)
        if srm:
            size = srm.group(1).replace(' ', '')
        available = ""
        if re.search(r'No Availability', block, re.IGNORECASE):
            available = "No Availability"
        else:
            t = re.search(r'\bToday\b', block)
            if t:
                available = "Today"
            else:
                d = re.search(r'\b(\d{1,2}/\d{1,2}/\d{4})\b', block)
                if d:
                    available = d.group(1)
        results.append({"Plan": plan, "Price": price, "Available": available, "Size": size})
    return results

if __name__ == "__main__":
    # Use absolute paths to ensure files can be found
    raw_content_file = r"/Users/chenximin/AptTrack/tests/integration/data/output_santa_clara_square.txt"
    results_file = r"/Users/chenximin/AptTrack/tests/integration/result/parser_output_santa_clara_square.txt"
    
    print(f"Reading from: {raw_content_file}")
    print(f"Writing to: {results_file}")
    
    try:
        # Read the raw content
        with open(raw_content_file, "r", encoding="utf-8") as f:
            raw_text = f.read()
        
        print(f"Read {len(raw_text)} characters from raw content file")

        # Extract information from the provided text
        apartments_data = extract_apartment_info(raw_text)
        print(f"Extracted {len(apartments_data)} apartment entries")
        print(apartments_data)

        # Save results
        with open(results_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(apartments_data, indent=2))
        
        print(f"Results successfully saved to: {results_file}")
        
    except FileNotFoundError as e:
        print(f"Error: File not found - {e}")
        print(f"Current working directory: {os.getcwd()}")
        print(f"Raw content file exists: {os.path.exists(raw_content_file)}")
        print(f"Results directory exists: {os.path.exists(os.path.dirname(results_file))}")
    except Exception as e:
        print(f"Error during extraction: {e}")
        import traceback
        traceback.print_exc()
