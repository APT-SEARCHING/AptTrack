#!/usr/bin/env python3
import json
import re
import os

def extract_apartment_info(text):
    import re

    results = []
    if not text or not isinstance(text, str):
        return results

    starts = [m.start() for m in re.finditer(r'\bApt\.\s', text)]
    if not starts:
        return results
    starts.append(len(text))

    for i in range(len(starts) - 1):
        chunk = text[starts[i]:starts[i + 1]]

        # Plan
        plan = None
        m_plan = re.search(r'\b(Studio|[0-9]+\s*bedroom)\b', chunk, re.IGNORECASE)
        if m_plan:
            raw_plan = m_plan.group(1).strip()
            if re.match(r'^\s*studio\s*$', raw_plan, re.IGNORECASE):
                plan = "Studio"
            else:
                num = re.search(r'\d+', raw_plan)
                if num:
                    plan = f"{num.group()} bedroom"
                else:
                    plan = raw_plan.title()

        # Size
        size = None
        m_size = re.search(r'([\d,]+)\s*sqft', chunk, re.IGNORECASE)
        if m_size:
            try:
                size = int(m_size.group(1).replace(',', ''))
            except:
                size = None

        # Price (base "Starting at $X")
        price = None
        m_price = re.search(r'Starting at[^$]*\$\s*([\d,]+)', chunk, re.IGNORECASE | re.DOTALL)
        if m_price:
            try:
                price = int(m_price.group(1).replace(',', ''))
            except:
                price = None

        # Available
        available = ""
        m_avail = re.search(r'Available.*?starting.*?([A-Za-z]{3}\s*\d{1,2})', chunk, re.IGNORECASE | re.DOTALL)
        if m_avail:
            available = m_avail.group(1).strip()
        else:
            m_now = re.search(r'Available\s*now', chunk, re.IGNORECASE)
            if m_now:
                available = "Now"

        if any([plan, price is not None, size is not None, available]):
            results.append({
                "Plan": plan or "",
                "Price": price,
                "Available": available,
                "Size": size
            })

    return results

if __name__ == "__main__":
    # Use absolute paths to ensure files can be found
    raw_content_file = r"/Users/chenximin/AptTrack/tests/integration/data/output_eaves_west_valley.txt"
    results_file = r"/Users/chenximin/AptTrack/tests/integration/result/parser_output_eaves_west_valley.txt"
    
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
