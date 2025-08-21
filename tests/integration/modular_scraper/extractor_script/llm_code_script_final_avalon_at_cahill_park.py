#!/usr/bin/env python3
import json
import re
import os

def extract_apartment_info(text):
    import re
    results = []
    if not isinstance(text, str) or not text:
        return results

    apt_iter = list(re.finditer(r'(^|\n)\s*Apt\.\s*([^\n\r]+)', text, flags=re.IGNORECASE))
    for i, m in enumerate(apt_iter):
        start = m.start()
        end = apt_iter[i + 1].start() if i + 1 < len(apt_iter) else len(text)
        segment = text[start:end]

        plan_id = ("Apt. " + m.group(2).strip()).strip()

        size_match = re.search(r'([0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)\s*sqft', segment, flags=re.IGNORECASE)
        size_val = (size_match.group(0).strip() if size_match else "")

        avail_match = re.search(r'Available\s*(?:starting\s*)?([A-Za-z]{3,9}\s*\d{1,2}|now)', segment, flags=re.IGNORECASE)
        available_val = (avail_match.group(1).strip().title() if avail_match else "")

        price_val = ""
        lower_seg = segment.lower()
        idx = lower_seg.find("starting at")
        if idx != -1:
            sub = segment[idx:]
            stops = []
            for token in ["furnished starting", "available", "\nview details", "view details", "\nvirtual", "/"]:
                pos = sub.lower().find(token)
                if pos != -1:
                    stops.append(pos)
            cut = min(stops) if stops else len(sub)
            sub2 = sub[:cut]
            dollars = re.findall(r'\$[0-9][0-9,]*', sub2)
            if dollars:
                price_val = dollars[-1]
        if not price_val:
            candidates = re.findall(r'\$[0-9][0-9,]*', segment)
            if candidates:
                price_val = candidates[0]
        results.append({
            "Plan": plan_id,
            "Price": price_val,
            "Available": available_val,
            "Size": size_val
        })

    if not results:
        # Fallback to summary "X bedroom From $Y"
        for m in re.finditer(r'(\b(?:studio|townhouse|\d+\+?\s*bedroom|\d+\s*bedroom|[123]\+\s*bedroom|[123]\s*bedroom))\s+From\s+(\$[0-9][0-9,]*)', text, flags=re.IGNORECASE):
            plan = m.group(1).strip().title()
            price = m.group(2).strip()
            results.append({
                "Plan": plan,
                "Price": price,
                "Available": "",
                "Size": ""
            })
    return results

if __name__ == "__main__":
    # Use absolute paths to ensure files can be found
    raw_content_file = r"/Users/chenximin/AptTrack/tests/integration/data/output_avalon_at_cahill_park.txt"
    results_file = r"/Users/chenximin/AptTrack/tests/integration/result/parser_output_avalon_at_cahill_park.txt"
    
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
