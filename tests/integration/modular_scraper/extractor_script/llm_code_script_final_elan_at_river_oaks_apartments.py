#!/usr/bin/env python3
import json
import re
import os

def extract_apartment_info(text):
    import re

    # Remove sections that are clearly not the current property's pricing/availability (e.g., nearby communities)
    cleaned = re.sub(r'Nearby Communities.*?Back to top', '', text, flags=re.S | re.I)

    # Normalize and split into lines
    lines = [ln.strip() for ln in cleaned.splitlines() if ln.strip()]
    n = len(lines)

    # Regex patterns
    currency_re = re.compile(r'\$\s*\d{1,3}(?:,\d{3})*(?:\.\d{2})?(?:\s*\+)?', re.I)
    size_range_re = re.compile(r'(\d{3,4}(?:,\d{3})?)\s*(?:to|-|–|—)\s*(\d{3,4}(?:,\d{3})?)\s*(?:sq\.?\s*ft|square\s*feet|sf)\b', re.I)
    size_single_re = re.compile(r'(?<!\d)(\d{3,4}(?:,\d{3})?)\s*(?:sq\.?\s*ft|square\s*feet|sf)\b', re.I)
    avail_re = re.compile(r'\b(Available\s*(?:Now|Today|Soon|Waitlist|Waitlisted|TBD|:?\s*\d{1,2}/\d{1,2}/\d{2,4}|:?\s*[A-Za-z]{3,9}\s*\d{1,2}(?:,\s*\d{2,4})?))\b', re.I)
    plan_label_re = re.compile(r'\b(?:Plan|Floor\s*Plan)\s*([A-Za-z0-9\.\-]+)\b', re.I)
    plan_xx_re = re.compile(r'\b(\d)\s*[xX]\s*(\d)\b')
    bed_bath_pair_re = re.compile(
        r'\b(?P<bed>(?:\d+|one|two|three|four|five|six|seven|eight|nine))\s*[- ]?(?:bed(?:room)?s?)\s*(?:[/&\-]?\s*(?P<bath>(?:\d+|one|two|three|four|five|six|seven|eight|nine))\s*[- ]?(?:bath(?:room)?s?|ba))?',
        re.I
    )

    words_to_num = {
        'zero': '0', 'one': '1', 'two': '2', 'three': '3', 'four': '4',
        'five': '5', 'six': '6', 'seven': '7', 'eight': '8', 'nine': '9'
    }

    def normalize_count(token):
        t = token.lower()
        return words_to_num.get(t, token)

    items = []
    seen = set()

    for i in range(n):
        context = ' '.join(lines[i:i+3])

        # Extract shared attributes from context window
        price_match = currency_re.search(context)
        price = price_match.group(0).replace(' ', '') if price_match else ''

        size = ''
        m_range = size_range_re.search(context)
        if m_range:
            a, b = m_range.group(1), m_range.group(2)
            size = f"{a} - {b} sq ft"
        else:
            m_single = size_single_re.search(context)
            if m_single:
                size = f"{m_single.group(1)} sq ft"

        avail_match = avail_re.search(context)
        available = avail_match.group(1).strip() if avail_match else ''

        plan_label = ''
        plm = plan_label_re.search(context)
        if plm:
            plan_label = f"Plan {plm.group(1)}"

        # Collect plans from patterns in context
        plans_in_context = []

        # 1x1 style
        for mx in plan_xx_re.finditer(context):
            bed = normalize_count(mx.group(1))
            bath = normalize_count(mx.group(2))
            plans_in_context.append(f"{bed} Bed {bath} Bath")

        # "X bed Y bath" or "X bedroom"
        for mp in bed_bath_pair_re.finditer(context):
            bed_token = mp.group('bed')
            bath_token = mp.group('bath')
            if bed_token:
                bed_count = normalize_count(bed_token)
                if bath_token:
                    bath_count = normalize_count(bath_token)
                    plans_in_context.append(f"{bed_count} Bed {bath_count} Bath")
                else:
                    # Only bed found => "X Bedroom"
                    plans_in_context.append(f"{bed_count} Bedroom")

        # Studio
        if re.search(r'\bstudio\b', context, re.I):
            plans_in_context.append("Studio")

        # If we have a plan label, prepend it to specific plans or use as standalone
        if plan_label:
            if plans_in_context:
                plans_in_context = [f"{plan_label} - {p}" for p in plans_in_context]
            else:
                plans_in_context = [plan_label]

        # If nothing detected but we have other attributes, create a generic entry
        if not plans_in_context and (price or size or available):
            plans_in_context = ['']

        # Create items for each detected plan
        for plan in plans_in_context:
            record = {
                'Plan': plan.strip(),
                'Price': price.strip(),
                'Available': available.strip(),
                'Size': size.strip()
            }
            key = (record['Plan'], record['Price'], record['Available'], record['Size'])
            if any(record.values()) and key not in seen:
                seen.add(key)
                items.append(record)

    # If still empty, try a last-pass extraction for a comma-separated list like "Studio, one-, and two-bedroom"
    if not items:
        for ln in lines:
            if re.search(r'\bStudio\b', ln, re.I) or re.search(r'bedroom', ln, re.I):
                # Extract studios
                if re.search(r'\bStudio\b', ln, re.I):
                    rec = {'Plan': 'Studio', 'Price': '', 'Available': '', 'Size': ''}
                    key = tuple(rec.values())
                    if key not in seen:
                        seen.add(key)
                        items.append(rec)
                # Extract numeric bedrooms
                for m in re.finditer(r'\b(one|two|three|four|five|six|seven|eight|nine|\d+)\s*[- ]?bedroom', ln, re.I):
                    bed = normalize_count(m.group(1))
                    rec = {'Plan': f'{bed} Bedroom', 'Price': '', 'Available': '', 'Size': ''}
                    key = tuple(rec.values())
                    if key not in seen:
                        seen.add(key)
                        items.append(rec)
                if items:
                    break

    return items

if __name__ == "__main__":
    # Use absolute paths to ensure files can be found
    raw_content_file = r"/Users/chenximin/AptTrack/tests/integration/data/output_elan_at_river_oaks_apartments.txt"
    results_file = r"/Users/chenximin/AptTrack/tests/integration/result/parser_output_elan_at_river_oaks_apartments.txt"
    
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
