import sys
import os
from openai import OpenAI

# Get input and output filenames from command line arguments or use defaults
input_file = sys.argv[1] if len(sys.argv) > 1 else "output_vista_99.txt"
output_file = sys.argv[2] if len(sys.argv) > 2 else "llm_code_script_vista_99.txt"

mykey = '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'
client = OpenAI(api_key = mykey)

print(f"Reading from: {input_file}")
print(f"Writing to: {output_file}")

with open(input_file, "r") as f:
    raw_text = f.read()

response = client.chat.completions.create(
    model="gpt-5-mini",   # or gpt-4o
    messages=[
        {"role": "system", "content": """You are a Python coding assistant.  

Task: Write a Python script that extracts apartment information from raw website text.  

Requirements:
- Define only one function: extract_apartment_info(text).
- The input is a string `text` containing the crawled website content.
- The function must parse the text and return a JSON object (list of dicts) with the following fields:
  {Plan, Price, Available, Size}.
- Do not include explanations, comments, or additional functions in the output.  
- Output only valid Python code.
"""}, 
        {"role": "user", "content": f"raw website text: {raw_text[:4000]}"}
    ]
)

script = response.choices[0].message.content

print(script)

with open(output_file, "w", encoding="utf-8") as f:
    f.write(script)

print(f"Script saved to: {output_file}")