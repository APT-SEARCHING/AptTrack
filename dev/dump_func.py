with open("template.txt", "r") as f:
    template = f.read()


with open("llm_code_script.txt", "r") as f:
    llm_code_script = f.read()


# Replace the function with the LLM code
llm_code_script_final = template.replace("$$function$$", llm_code_script)

# Save the updated script
with open("llm_code_script_final.py", "w", encoding="utf-8") as f:
    f.write(llm_code_script_final)