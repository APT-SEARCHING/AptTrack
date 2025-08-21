#!/usr/bin/env python3
import json
import re
import os

def extract_apartment_info(text):
    import re
    lines = [ln.strip() for ln in text.replace('\r', '').split('\n') if ln.strip()]
    plan_idxs = []
    for i, ln in enumerate(lines):
        if re.fullmatch(r'[A-Z]', ln):
            if i + 1 < len(lines) and (lines[i+1].lower() == 'studio' or re.fullmatch(r'\d+\s+bed', lines[i+1].lower())):
                plan_idxs.append(i)
    results = []
    for idx_i, start in enumerate(plan_idxs):
        end = plan_idxs[idx_i + 1] if idx_i + 1 < len(plan_idxs) else len(lines)
        block = lines[start:end]
        plan = block[0]
        size = None
        price = None
        available = None
        for ln in block[1:]:
            m_size = re.search(r'([\d,]+(?:\s*-\s*[\d,]+)?)\s*sq\.\s*ft\.', ln, flags=re.I)
            if m_size and size is None:
                size = m_size.group(0)
            m_price = re.search(r'Starting\s+at\s*\$\s*([\d,]+)', ln, flags=re.I)
            if m_price and price is None:
                price = f"${m_price.group(1)}"
                available = "Available"
            if (not m_price) and price is None and re.fullmatch(r'Contact Us', ln, flags=re.I):
                price = "Contact Us"
                available = "Contact Us"
            if size and price:
                break
        results.append({
            "Plan": plan,
            "Price": price if price is not None else "",
            "Available": available if available is not None else "",
            "Size": size if size is not None else ""
        })
    return results

if __name__ == "__main__":
    # Use absolute paths to ensure files can be found
    raw_content_file = r"/Users/chenximin/AptTrack/tests/integration/data/output_hanover_winchester.txt"
    results_file = r"/Users/chenximin/AptTrack/tests/integration/result/parser_output_hanover_winchester.txt"
    
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
