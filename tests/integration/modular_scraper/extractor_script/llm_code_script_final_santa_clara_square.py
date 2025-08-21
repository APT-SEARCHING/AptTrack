#!/usr/bin/env python3
import json
import re
import os

def extract_apartment_info(text):
    import re
    results = []
    plan_pattern = re.compile(r'(?im)^(?:PLAN|Plan)\s+[^\n]+')
    matches = list(plan_pattern.finditer(text))
    for i, m in enumerate(matches):
        plan_name = m.group(0).strip()
        seg_start = m.end()
        seg_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        segment = text[seg_start:seg_end]

        bldg_marker = 'BLDG NO. / APT NO.'
        idx_bldg = segment.find(bldg_marker)
        pre_units = segment[:idx_bldg] if idx_bldg != -1 else segment
        units = segment[idx_bldg:] if idx_bldg != -1 else ''

        size = None
        size_matches = list(re.finditer(r'(?m)^\s*([\d,]{3,5}(?:\s*-\s*[\d,]{3,5})?)\s*$', pre_units))
        if size_matches:
            size = size_matches[-1].group(1)

        if units:
            unit_pattern = re.compile(r'(?im)^\s*\d{1,2}\s*mo\.\s*\n^\s*\$([\d,]+)\s*\n^\s*(Today|\d{2}/\d{2}/\d{4})\s*', re.MULTILINE)
            for price, avail in unit_pattern.findall(units):
                results.append({
                    "Plan": plan_name.upper(),
                    "Price": f"${price}",
                    "Available": avail,
                    "Size": size if size is not None else ""
                })
        else:
            if re.search(r'No Availability', pre_units, re.IGNORECASE):
                results.append({
                    "Plan": plan_name.upper(),
                    "Price": "",
                    "Available": "No Availability",
                    "Size": size if size is not None else ""
                })
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
