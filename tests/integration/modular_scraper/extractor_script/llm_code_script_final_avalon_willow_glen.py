#!/usr/bin/env python3
import json
import re
import os

def extract_apartment_info(text):
    import re
    results = []
    matches = list(re.finditer(r'\bApt\.\s*[^\n]+', text))
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end]
        apt_line = m.group(0).strip()
        plan_match = re.search(r'(\d[\d,]*)\s*bed\s*•\s*(\d[\d,]*)\s*bath', block, re.IGNORECASE)
        if plan_match:
            plan = f"{plan_match.group(1)} bed • {plan_match.group(2)} bath"
        else:
            plan = apt_line
        size_match = re.search(r'(\d[\d,]*)\s*sqft', block, re.IGNORECASE)
        size = f"{size_match.group(1)} sqft" if size_match else None
        avail = None
        avail_match = re.search(r'Available\s*starting\s*([A-Za-z]+\.?\s*\d{1,2}|Now|Today)', block, re.IGNORECASE)
        if avail_match:
            avail = avail_match.group(1).strip()
        else:
            if re.search(r'\bAvailable\b', block, re.IGNORECASE):
                avail = "Available"
        price = None
        sa = re.search(r'Starting at', block, re.IGNORECASE)
        if sa:
            after = block[sa.end():]
            lease = re.search(r'/\s*\d+\s*mo\.\s*lease', after, re.IGNORECASE)
            segment = after[:lease.start()] if lease else after
            dollars = re.findall(r'\$\s*\d[\d,]*', segment)
            if dollars:
                price = dollars[-1].replace(' ', '')
        results.append({"Plan": plan, "Price": price, "Available": avail, "Size": size})
    return results

if __name__ == "__main__":
    # Use absolute paths to ensure files can be found
    raw_content_file = r"/Users/chenximin/AptTrack/tests/integration/data/output_avalon_willow_glen.txt"
    results_file = r"/Users/chenximin/AptTrack/tests/integration/result/parser_output_avalon_willow_glen.txt"
    
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
