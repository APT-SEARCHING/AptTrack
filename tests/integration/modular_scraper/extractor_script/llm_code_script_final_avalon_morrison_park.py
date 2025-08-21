#!/usr/bin/env python3
import json
import re
import os

def extract_apartment_info(text):
    import re

    results = []
    block_pattern = re.compile(r"(Apt\.\s*[^\n]+)(.*?)(?=(?:\nApt\.\s*[^\n]+)|\Z)", re.S | re.I)

    for m in block_pattern.finditer(text):
        apt_line = m.group(1).strip()
        block = m.group(0)

        plan = apt_line
        bedbath_match = re.search(r"(\d+\s*beds?\s*•\s*[\d\.]+\s*baths?)", block, re.I)
        if not bedbath_match:
            bedbath_match = re.search(r"(\d+\s*bed\s*•\s*[\d\.]+\s*bath[s]?)", block, re.I)
        if bedbath_match:
            plan = bedbath_match.group(1).strip()

        size_match = re.search(r"([\d,]+)\s*sqft", block, re.I)
        size = f"{size_match.group(1)} sqft" if size_match else ""

        prices = re.findall(r"\$\s*\d{1,3}(?:,\d{3})*(?:\.\d{2})?", block)
        price = re.sub(r"\s+", "", prices[-1]) if prices else ""

        avail_match = re.search(r"Available\s*starting\s*([A-Za-z]{3,9}\s*\d{1,2})", block, re.I | re.S)
        if not avail_match:
            avail_match = re.search(r"Available\s*(?:starting\s*)?(Now|[A-Za-z]{3,9}\s*\d{1,2})", block, re.I | re.S)
        available = avail_match.group(1).strip() if avail_match else ""

        results.append({
            "Plan": plan,
            "Price": price,
            "Available": available,
            "Size": size
        })

    return results

if __name__ == "__main__":
    # Use absolute paths to ensure files can be found
    raw_content_file = r"/Users/chenximin/AptTrack/tests/integration/data/output_avalon_morrison_park.txt"
    results_file = r"/Users/chenximin/AptTrack/tests/integration/result/parser_output_avalon_morrison_park.txt"
    
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
