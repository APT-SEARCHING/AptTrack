import re
import json

with open("output_1.txt", "r") as f:
        text = f.read()
# text = """... your pasted website text ..."""

apartments = []
current_plan = None
current_size = None
current_bedbath = None
current_base_price = None


lines = text.splitlines()

for i, line in enumerate(lines):
    line = line.strip()

    # Detect a new plan
    plan_match = re.match(r"(PLAN\s+\d+)", line)
    if plan_match:
        current_plan = plan_match.group(1)
        # Next line should have bed/bath
        if i+1 < len(lines):
            current_bedbath = lines[i+1].strip()
        # Next next line should have base price
        if i+2 < len(lines):
            price_line = lines[i+2].strip()
            if price_line.startswith("$"):
                current_base_price = price_line
        # Next next next line should have size
        if i+3 < len(lines):
            current_size = lines[i+3].strip()
        continue

    # Detect apartment unit info: usually like "02 124"
    unit_match = re.match(r"^\d{2}\s+\d{3}", line)
    if unit_match and current_plan:
        # Extract info in the next few lines
        unit = line
        term = lines[i+1].strip() if i+1 < len(lines) else None
        price = lines[i+2].strip() if i+2 < len(lines) else None
        available = lines[i+3].strip() if i+3 < len(lines) else None

        # Append to result
        apartments.append({
            "plan": current_plan,
            "bed_bath": current_bedbath,
            "size": current_size,
            "unit": unit,
            "term": term,
            "price": price,
            "available_date": available
        })

# Output JSON
with open("parser_output.txt", "w", encoding="utf-8") as f:
    f.write(json.dumps(apartments, indent=2))
# print(json.dumps(apartments, indent=2))


# if __name__ == "__main__":
#     with open("output_1.txt", "r") as f:
#         raw_text = f.read()
    
#     # Extract information from the provided text
#     apartments_data = parse_apartments(raw_text)

#     # Convert the data to JSON format
#     # apartments_json = convert_to_json(apartments_data)
#     with open("parser_output.txt", "w", encoding="utf-8") as f:
#         f.write(json.dumps(apartments_data, indent=2))