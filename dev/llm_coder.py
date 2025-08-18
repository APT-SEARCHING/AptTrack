mykey = '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'
from openai import OpenAI
client = OpenAI(api_key = mykey)

with open("output_1.txt", "r") as f:
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
        {"role": "user", "content": f"raw website text: {raw_text}"}
    ]
)

script = response.choices[0].message.content

print(script)

with open("llm_code_script.txt", "w", encoding="utf-8") as f:
    f.write(script)