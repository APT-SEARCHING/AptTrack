#!/usr/bin/env python3
import json
import re
import os

def extract_apartment_info(text):
    import re
    lines = text.splitlines()
    idx = None
    for i, l in enumerate(lines):
        if 'List View' in l:
            idx = i
            break
    if idx is None:
        segment = text
    else:
        segment_lines = lines[idx + 1:]
        end_idx = None
        for j, l in enumerate(segment_lines):
            if 'Floor plans are artist' in l:
                end_idx = j
                break
        if end_idx is not None:
            segment_lines = segment_lines[:end_idx]
        segment = '\n'.join(segment_lines)
    seg_lines = [l.strip() for l in segment.splitlines() if l.strip() != '']
    plan_indices = []
    for i, l in enumerate(seg_lines):
        if re.fullmatch(r'[A-Z][0-9]{1,3}', l):
            plan_indices.append(i)
    results = []
    for k, start in enumerate(plan_indices):
        end = plan_indices[k + 1] if k + 1 < len(plan_indices) else len(seg_lines)
        block = '\n'.join(seg_lines[start:end])
        plan = seg_lines[start]
        m_price = re.search(r'Base\s+Rent\s*\$?\s*([\d,]+)', block, re.I)
        price = f'${m_price.group(1)}' if m_price else None
        m_av = re.search(r'(Available[^\n]*)', block, re.I)
        available = m_av.group(1).strip() if m_av else None
        m_size = re.search(r'([\d,]+(?:\s*-\s*[\d,]+)?)\s*sq\.?\s*ft\.?', block, re.I)
        size = m_size.group(0).strip() if m_size else None
        results.append({'Plan': plan, 'Price': price, 'Available': available, 'Size': size})
    return results

if __name__ == "__main__":
    # Use absolute paths to ensure files can be found
    raw_content_file = r"/Users/chenximin/AptTrack/tests/integration/data/output_diridon_west.txt"
    results_file = r"/Users/chenximin/AptTrack/tests/integration/result/parser_output_diridon_west.txt"
    
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
