import sys
import os
from openai import OpenAI

# Get input and output filenames from command line arguments or use defaults
mykey = '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'
client = OpenAI(api_key = mykey)

# print(f"Reading from: {input_file}")
# print(f"Writing to: {output_file}")
output_file = "selected_url.txt"
with open('candidates.txt', "r") as f:
    raw_text = f.read()

response = client.chat.completions.create(
    model="gpt-5-mini",   # or gpt-4o
    messages=[
        {"role": "system", "content": """You are a web crawler assistant for finding floor plans.  

Task: I will give you a list of URLs, you need to find out which one has floor plans.  

Requirements:
- Do not include explanations, comments, or additional functions in the output.  
- Output only one valid url.
"""}, 
        {"role": "user", "content": f"URL list: {raw_text[:4000]}"}
    ]
)

script = response.choices[0].message.content

print(script)

with open(output_file, "w", encoding="utf-8") as f:
    f.write(script)

print(f"Script saved to: {output_file}")