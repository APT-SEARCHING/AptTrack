import sys
import os

apt_name = sys.argv[1] if len(sys.argv) > 1 else "vista_99"

with open("template.txt", "r") as f:
    template = f.read()

with open("llm_code_script_vista_99.txt", "r") as f:
    llm_code_script = f.read()


# Replace the function with the LLM code
llm_code_script_final = template.replace("$$function$$", llm_code_script).replace("$$apt_name$$", apt_name)

# Save the updated script
with open(f"llm_code_script_final_{apt_name}.py", "w", encoding="utf-8") as f:
    f.write(llm_code_script_final)