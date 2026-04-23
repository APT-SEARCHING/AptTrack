import sys
import os
from openai import OpenAI

# Get input and output filenames from command line arguments or use defaults
mykey = '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'
client = OpenAI(api_key = mykey)

output_file = "selection_actions.txt"
with open('output.txt', "r") as f:
    raw_text = f.read()

prompt_1 = '''
  You are a web crawler assistant specialized in extracting apartment floor plans.
  I will provide you with the raw HTML/text of an apartment website or iframe content. 
  Determine whether any user interaction (like clicking a tab or button) is required to reveal the full floor plan list.
  Requirements:
  - If no click is needed, return exactly: []
  - If clicks are required, output a JSON list of Python Playwright click commands. 
  Use the format: [page.click("selector")]
  - If the clickable element is inside an iframe, prepend the click command with the iframe locator, e.g. "page.frame_locator('iframe[src*='rentcafe.com']').locator('button:has-text('Floor Plans')').click()"
  - Do not include explanations, comments, or any extra text—only the JSON output.
  '''

prompt_2 = '''
You are a web crawler assistant specialized in extracting apartment floor plans.

Task: I will give you the raw HTML/text of an apartment website. Determine if clicking is required to reveal the full floor plan list.  

Requirements:
- If no click is needed, return an empty list [].
- If clicks are required, output a list of Python Playwright click commands.  
- Use the format: [page.click("selector")]  
- Do not include explanations, comments, or extra text in the output.
'''




response = client.chat.completions.create(
    model="gpt-5-mini",   # or gpt-4o
    messages=[
        {"role": "system", "content": prompt_1}, 
        {"role": "user", "content": f"URL list: {raw_text[:]}"}
    ]
)





script = response.choices[0].message.content

print(script)

with open(output_file, "w", encoding="utf-8") as f:
    f.write(script)

print(f"Script saved to: {output_file}")