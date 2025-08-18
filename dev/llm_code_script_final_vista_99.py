import json
import re

def extract_apartment_info(text):
    import re
    s = text or ""
    avail = ""
    if re.search(r'\bView Availability\b|\bAvailability\b|\bCheck Availability\b', s, re.I):
        avail = "View Availability"
    size_match = re.search(r'(\d{2,4})\s*(?:sqft|sq\. ?ft|sq ft|ft2|sq feet)', s, re.I)
    default_size = size_match.group(1) if size_match else ""
    results = []
    seen = set()
    for m in re.finditer(r'\$[\d,]+(?:\+)?', s):
        price = m.group()
        start = max(0, m.start() - 80)
        before = s[start:m.start()]
        after = s[m.end():m.end() + 80]
        plan = None
        pm = re.search(r'(\d+\s*Bed|Studio|Shared)\b', before, re.I)
        if not pm:
            pm = re.search(r'(\d+\s*Bed|Studio|Shared)\b', after, re.I)
        if pm:
            plan = pm.group(1).strip()
        else:
            lines_before = before.strip().splitlines()
            if lines_before:
                last = lines_before[-1].strip()
                if last and not last.startswith('$'):
                    plan = last
        if not plan:
            plan = "Unknown"
        key = (plan.lower(), price)
        if key in seen:
            continue
        seen.add(key)
        results.append({"Plan": plan, "Price": price, "Available": avail, "Size": default_size})
    if not results:
        for pm in re.findall(r'(\d+\s*Bed|Studio|Shared)\s*\$[\d,]+(?:\+)?', s, re.I):
            price_m = re.search(r'\$[\d,]+(?:\+)?', s)
            price = price_m.group() if price_m else ""
            key = (pm.lower(), price)
            if key in seen:
                continue
            seen.add(key)
            results.append({"Plan": pm, "Price": price, "Available": avail, "Size": default_size})
    return results

if __name__ == "__main__":
    with open("output_vista_99.txt", "r") as f:
        raw_text = f.read()

    # Extract information from the provided text
    apartments_data = extract_apartment_info(raw_text)
    print(apartments_data)

    # Convert the data to JSON format
    # apartments_json = convert_to_json(apartments_data)
    with open("parser_output_byllm_vista_99.txt", "w", encoding="utf-8") as f:
        f.write(json.dumps(apartments_data, indent=2))