#!/usr/bin/env python3
import json
import re
import os

def extract_apartment_info(text):
    import re
    lines = [l.strip() for l in text.splitlines()]
    results = []
    price_pat = re.compile(r'^\$\d[\d,]*(?:\.\d{2})?$')
    size_pat = re.compile(r'(\d[\d,]*)\s*sq\.\s*ft\.?$', re.IGNORECASE)
    avail_pat = re.compile(r'^Available\s+(.*)$', re.IGNORECASE)

    n = len(lines)
    for i, line in enumerate(lines):
        if line == "Furnished Price":
            price = None
            j = i - 1
            while j >= 0:
                s = lines[j].strip()
                if price_pat.match(s) and s != "$0":
                    price = s
                    break
                j -= 1

            plan = ""
            plan1 = None
            plan2 = None
            size = ""
            available = ""

            # Scan forward for plan, size, available
            forward_limit = min(i + 30, n)
            saw_sqft = False
            t = i + 1
            while t < forward_limit:
                s = lines[t].strip()
                if not plan1 and re.search(r'\bBed\b', s, re.IGNORECASE):
                    if re.search(r'\bBath\b', s, re.IGNORECASE):
                        plan = s
                    else:
                        plan1 = s
                elif plan1 and not plan2 and re.search(r'\bBath\b', s, re.IGNORECASE):
                    plan2 = s
                m_size = size_pat.search(s)
                if m_size and not size:
                    # Normalize size to include "sq. ft."
                    size = f"{m_size.group(1)} sq. ft."
                    saw_sqft = True
                m_av = avail_pat.match(s)
                if m_av and not available:
                    available = m_av.group(1).strip()
                if plan1 and plan2 and plan == "":
                    plan = f"{plan1} / {plan2}"
                # Stop early if we've collected key fields after seeing sqft and availability
                if plan and size and available:
                    break
                t += 1

            if price and plan and size:
                results.append({
                    "Plan": plan,
                    "Price": price,
                    "Available": available,
                    "Size": size
                })
    return results

if __name__ == "__main__":
    # Use absolute paths to ensure files can be found
    raw_content_file = r"/Users/chenximin/AptTrack/tests/integration/data/output_vista_99.txt"
    results_file = r"/Users/chenximin/AptTrack/tests/integration/result/parser_output_vista_99.txt"
    
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
