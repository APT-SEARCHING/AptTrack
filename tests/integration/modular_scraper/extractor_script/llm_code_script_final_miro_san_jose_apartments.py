#!/usr/bin/env python3
import json
import re
import os

def extract_apartment_info(text):
    import re
    results = []
    current = None
    lines = [re.sub(r'\s+', ' ', l).strip() for l in (text or '').splitlines()]
    plan_regex = re.compile(r'(?i)\b(?:plan\s*[A-Za-z0-9\-]+|\d+\s*bed(?:room)?s?\s*(?:[,/and&]*\s*\d+\s*bath(?:room)?s?)?|\d+\s*br\s*(?:[,/and&]*\s*\d+\s*ba)?|studio(?:\s*\+\s*den)?|penthouse(?:s)?|loft|\d+\s*x\s*\d+)\b')
    money_regex = re.compile(r'\$\s*\d{1,3}(?:,\d{3})*(?:\.\d+)?')
    size_regex = re.compile(r'(?P<min>\d{3,4}(?:,\d{3})?)(?:\s*-\s*(?P<max>\d{3,4}(?:,\d{3})?))?\s*(?:sq\.?\s*ft|square\s*feet|sqft|s\.?\s*f\.?|sf|ft²)\b', re.I)
    def has_content(d):
        return bool((d.get('Price') or '').strip() or (d.get('Available') or '').strip() or (d.get('Size') or '').strip())
    for raw in lines:
        if not raw:
            continue
        line = raw
        low = line.lower()
        m_plan = plan_regex.search(line)
        if m_plan:
            if current and has_content(current):
                results.append(current)
            plan_text = m_plan.group(0).strip()
            current = {'Plan': plan_text, 'Price': '', 'Available': '', 'Size': ''}
        m_size = size_regex.search(line)
        if m_size:
            size_min = m_size.group('min')
            size_max = m_size.group('max')
            if size_min and size_max:
                size_str = f"{size_min} - {size_max} sq ft"
            else:
                size_str = f"{size_min} sq ft"
            if not current:
                current = {'Plan': '', 'Price': '', 'Available': '', 'Size': ''}
            elif current.get('Size') and current['Size'] != size_str and has_content(current):
                results.append(current)
                current = {'Plan': current.get('Plan', ''), 'Price': '', 'Available': '', 'Size': ''}
            current['Size'] = size_str
        money = money_regex.findall(line)
        price_str = ''
        if money:
            money_clean = [re.sub(r'\$\s*', '$', m) for m in money]
            if len(money_clean) == 1:
                qualifiers = ''
                if re.search(r'(?i)\bstarting at\b|\bfrom\b|\bas low as\b', line):
                    q = re.search(r'(?i)\bstarting at\b|\bfrom\b|\bas low as\b', line).group(0)
                    qualifiers = q.title() + ' '
                price_str = qualifiers + money_clean[0]
            else:
                price_str = f"{money_clean[0]} - {money_clean[1]}"
        if price_str:
            if not current:
                current = {'Plan': '', 'Price': '', 'Available': '', 'Size': ''}
            elif current.get('Price') and current['Price'] != price_str and has_content(current):
                results.append(current)
                current = {'Plan': current.get('Plan', ''), 'Price': '', 'Available': '', 'Size': ''}
            current['Price'] = price_str
        avail_val = ''
        if 'waitlist' in low:
            avail_val = 'Waitlist'
        elif 'call for availability' in low or 'contact for availability' in low:
            avail_val = 'Call for availability'
        else:
            m_count_avail = re.search(r'\b(\d+)\s+available\b', low)
            if m_count_avail:
                avail_val = m_count_avail.group(0).title()
            else:
                if 'view availability' not in low:
                    m_av = re.search(r'available(?:\s*(?:on|by|:|-)?\s*)?(now|soon|\d{1,2}/\d{1,2}(?:/\d{2,4})?|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december)\s+\d{1,2}(?:,\s*\d{2,4})?)', low, re.I)
                    if m_av:
                        avail_val = ('Available ' + m_av.group(1)).strip().title()
                    elif 'available' in low:
                        avail_val = 'Available'
        if avail_val:
            if not current:
                current = {'Plan': '', 'Price': '', 'Available': '', 'Size': ''}
            current['Available'] = avail_val
    if current and has_content(current):
        results.append(current)
    cleaned = []
    for r in results:
        cleaned.append({
            'Plan': (r.get('Plan') or '').strip(),
            'Price': (r.get('Price') or '').strip(),
            'Available': (r.get('Available') or '').strip(),
            'Size': (r.get('Size') or '').strip()
        })
    return cleaned

if __name__ == "__main__":
    # Use absolute paths to ensure files can be found
    raw_content_file = r"/Users/chenximin/AptTrack/tests/integration/data/output_miro_san_jose_apartments.txt"
    results_file = r"/Users/chenximin/AptTrack/tests/integration/result/parser_output_miro_san_jose_apartments.txt"
    
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
