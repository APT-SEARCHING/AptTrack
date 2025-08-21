#!/usr/bin/env python3
import json
import re
import os

def extract_apartment_info(text):
    import re
    results = []
    if not isinstance(text, str) or not text.strip():
        return results
    start_idx = text.find("Apt.")
    if start_idx == -1:
        start_idx = 0
    end_idx = len(text)
    for marker in ["Room dimensions", "Load All", "Load More"]:
        idx = text.find(marker, start_idx)
        if idx != -1 and idx < end_idx:
            end_idx = idx
    chunk = text[start_idx:end_idx]
    blocks = re.split(r"(?=Apt\.\s*[^\n]+)", chunk)
    for block in blocks:
        if not block.strip().startswith("Apt."):
            continue
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        spec_line = None
        for ln in lines:
            if re.search(r"\b[\d,]+\s*sqft\b", ln, re.I) and re.search(r"\bbed\b|\bbath\b", ln, re.I):
                spec_line = ln
                break
        size_str = ""
        plan_text = ""
        if spec_line:
            m = re.search(r"([\d,]+\s*sqft)", spec_line, re.I)
            if m:
                size_str = m.group(1).strip()
            plan_text = re.sub(r"•\s*[\d,]+\s*sqft.*", "", spec_line, flags=re.I).strip()
        else:
            for ln in lines:
                m = re.search(r"([\d,]+\s*sqft)", ln, re.I)
                if m:
                    size_str = m.group(1).strip()
                    break
            for ln in lines:
                if re.search(r"\bbed\b", ln, re.I) and re.search(r"\bbath\b", ln, re.I):
                    plan_text = re.sub(r"•\s*[\d,]+\s*sqft.*", "", ln, flags=re.I).strip()
                    break
        block_flat = " ".join(lines)
        price = ""
        m = re.search(r"Starting at(.*?)(?:/|Available|Furnished starting at|View Details|$)", block_flat, re.I)
        if m:
            seg = m.group(1)
            prices = re.findall(r"\$\s*\d{1,3}(?:,\d{3})*(?:\.\d{2})?", seg)
            if prices:
                price = prices[-1].strip()
        if not price:
            m2 = re.search(r"(\$\s*\d{1,3}(?:,\d{3})*(?:\.\d{2})?).{0,60}(?:/|Available|Furnished starting at|View Details)", block_flat, re.I)
            if m2:
                price = m2.group(1).strip()
        avail = ""
        m = re.search(r"Available(?:\s+starting)?\s+(Now|[A-Za-z]{3,9}\s+\d{1,2})", block_flat, re.I)
        if m:
            avail = m.group(1).strip()
        elif re.search(r"\bAvailable Now\b", block_flat, re.I):
            avail = "Now"
        if any([plan_text, price, avail, size_str]):
            results.append({
                "Plan": plan_text,
                "Price": price,
                "Available": avail,
                "Size": size_str
            })
    return results

if __name__ == "__main__":
    # Use absolute paths to ensure files can be found
    raw_content_file = r"/Users/chenximin/AptTrack/tests/integration/data/output_avalon_on_the_alameda.txt"
    results_file = r"/Users/chenximin/AptTrack/tests/integration/result/parser_output_avalon_on_the_alameda.txt"
    
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
