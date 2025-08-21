#!/usr/bin/env python3
import json
import re
import os

def extract_apartment_info(text):
    import re
    if not isinstance(text, str) or not text.strip():
        return []
    price_re = re.compile(r'\$\s*\d{1,3}(?:,\d{3})*(?:\.\d{2})?(?:\s*-\s*\$\s*\d{1,3}(?:,\d{3})*(?:\.\d{2})?)?', re.I)
    size_re = re.compile(r'\b\d{3,4}(?:,\d{3})?\s*(?:sq\.?\s*ft\.?|square\s*feet|sf)\b', re.I)
    avail_re = re.compile(r'(?:available\s*(?:now|today|soon|immediately|on\s*[A-Za-z]{3,9}\s*\d{1,2}(?:,\s*\d{4})?|:?\s*\d{1,2}/\d{1,2}/\d{2,4}|:?\s*\d+\s*units?\s*left)|wait\s*list|waitlist)', re.I)
    plan_explicit_re = re.compile(r'(?:^|\b)(?:floor\s*plan|floorplan|plan)\s*[:#\-]?\s*([A-Za-z0-9][A-Za-z0-9 .\-/]{0,30})', re.I)
    plan_token_re = re.compile(r'\b(?:Studio|[1-4]\s*(?:bed(?:rooms?)?|br)|[1-4]\s*x\s*[1-3]|[A-H]\d{1,2}[A-Za-z]?|S\d{1,2})\b', re.I)
    text_len = len(text)
    prices = [(m.start(), m.end(), m.group(0).strip()) for m in price_re.finditer(text)]
    if not prices:
        return []
    sizes = [(m.start(), m.end(), m.group(0).strip()) for m in size_re.finditer(text)]
    avails = [(m.start(), m.end(), m.group(0).strip()) for m in avail_re.finditer(text)]
    plans_explicit = [(m.start(), m.end(), m.group(1).strip()) for m in plan_explicit_re.finditer(text)]
    def nearest(match_list, center, window=200):
        best = None
        best_dist = None
        left = max(0, center - window)
        right = min(text_len, center + window)
        for s, e, val in match_list:
            if s >= left and e <= right:
                d = min(abs(center - s), abs(center - e))
                if best is None or d < best_dist:
                    best = (s, e, val)
                    best_dist = d
        return best[2] if best else ""
    results = []
    seen = set()
    for s, e, price in prices:
        plan = ""
        size = ""
        avail = ""
        explicit_plan_val = nearest(plans_explicit, (s + e) // 2, 220)
        if explicit_plan_val:
            plan = explicit_plan_val
        else:
            window_left = max(0, s - 220)
            window_right = min(text_len, e + 220)
            snippet = text[window_left:window_right]
            token_match = None
            closest_dist = None
            for m in plan_token_re.finditer(snippet):
                token = m.group(0).strip()
                token_start_global = window_left + m.start()
                dist = min(abs(s - token_start_global), abs(e - token_start_global))
                if token and (closest_dist is None or dist < closest_dist):
                    token_match = token
                    closest_dist = dist
            if token_match:
                plan = token_match
        if plan:
            plan = re.sub(r'^(?:floor\s*plan|floorplan|plan)\s*[:#\-]?\s*', '', plan, flags=re.I).strip()
            plan = re.split(r'\s*[|,\n;·•]\s*', plan)[0].strip()
        size = nearest(sizes, (s + e) // 2, 220)
        avail = nearest(avails, (s + e) // 2, 220)
        plan = plan.strip()
        price = ' '.join(price.split())
        size = ' '.join(size.split()) if size else ""
        avail = ' '.join(avail.split()) if avail else ""
        key = (plan.lower(), price.lower(), avail.lower(), size.lower())
        if key not in seen:
            seen.add(key)
            results.append({"Plan": plan, "Price": price, "Available": avail, "Size": size})
    return results

if __name__ == "__main__":
    # Use absolute paths to ensure files can be found
    raw_content_file = r"/Users/chenximin/AptTrack/tests/integration/data/output_the_benton.txt"
    results_file = r"/Users/chenximin/AptTrack/tests/integration/result/parser_output_the_benton.txt"
    
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
