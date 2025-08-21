#!/usr/bin/env python3
"""
Scraper Steps Module
Contains all individual step functions that can be reused independently
"""

import os
import sys
import json
import time
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from openai import OpenAI

def step1_find_homepage_candidates(homepage_url, candidates_file):
    """Step 1: Find homepage and extract candidate URLs for floor plans"""
    print(f"Step 1: Finding floor plan candidates from {homepage_url}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        print("Navigating to the homepage...")
        page.goto(homepage_url)
        time.sleep(5)
        
        print("Extracting candidate URLs...")
        html = page.content()
        soup = BeautifulSoup(html, 'html.parser')
        
        keywords = ["availability", "floor", "plans", "pricing"]
        candidates = set()

        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True).lower()
            href = a["href"]

            if any(kw in text for kw in keywords):
                full_url = urljoin(homepage_url, href)
                candidates.add(full_url)
        
        # Save candidates
        with open(candidates_file, "w", encoding="utf-8") as f:
            f.write('\n'.join(candidates))
        
        print(f"Found {len(candidates)} candidate URLs")
        browser.close()
        
        return list(candidates)

def step2_llm_floor_finder(candidates, openai_api_key, selected_url_file):
    """Step 2: Use LLM to identify the best floor plan page"""
    print("Step 2: Using LLM to identify floor plan page")
    
    client = OpenAI(api_key=openai_api_key)
    candidates_text = '\n'.join(candidates[:10])  # Limit to first 10 URLs
    
    response = client.chat.completions.create(
        model="gpt-5-mini",
        messages=[
            {"role": "system", "content": """You are a web crawler assistant for finding floor plans.  

Task: I will give you a list of URLs, you need to find out which one has floor plans.  

Requirements:
- Do not include explanations, comments, or additional functions in the output.  
- Output only one valid url.
"""}, 
            {"role": "user", "content": f"URL list: {candidates_text}"}
        ]
    )

    selected_url = response.choices[0].message.content.strip()
    
    # Save selected URL
    with open(selected_url_file, "w", encoding="utf-8") as f:
        f.write(selected_url)
    
    print(f"LLM selected: {selected_url}")
    return selected_url

def step3_crawl_floor_plans(floor_plan_url, raw_content_file):
    """Step 3: Crawl the floor plan page for apartment information"""
    print(f"Step 3: Crawling floor plan page: {floor_plan_url}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        print("Navigating to floor plan page...")
        page.goto(floor_plan_url)
        time.sleep(5)
        
        print("Extracting page content...")
        html = page.content()
        soup = BeautifulSoup(html, 'html.parser')
        
        # Get text content
        txt = soup.get_text(separator="\n", strip=True)
        
        # Save raw content
        with open(raw_content_file, "w", encoding="utf-8") as f:
            f.write(txt)
        
        print(f"Extracted {len(txt)} characters of content")
        browser.close()
        
        return txt

def step4_llm_code_generator(raw_text, openai_api_key, extraction_code_file):
    """Step 4: Use LLM to generate extraction code"""
    print("Step 4: Generating extraction code with LLM")
    
    client = OpenAI(api_key=openai_api_key)
    
    response = client.chat.completions.create(
        model="gpt-5",
        messages=[
            {"role": "system", "content": """You are a Python coding assistant.  

Task: Write a Python script that extracts apartment information from raw website text.  

Requirements:
- Define only one function: extract_apartment_info(text).
- The input is a string `text` containing the crawled website content.
- The function must parse the text and return a JSON object (list of dicts) with the following fields:
  {Plan, Price, Available, Size}.
- be aware number is possible to be seperate by , like 1,034
- Do not include explanations, comments, or additional functions in the output.  
- Output only valid Python code.
"""}, 
            {"role": "user", "content": f"raw website text: {raw_text}"}
        ]
    )

    extraction_code = response.choices[0].message.content
    
    # Save extraction code
    with open(extraction_code_file, "w", encoding="utf-8") as f:
        f.write(extraction_code)
    
    print("Extraction code generated")
    return extraction_code

def step5_create_final_extractor(extraction_code, raw_content_file, results_file, final_extractor_file):
    """Step 5: Create the final extractor script"""
    print("Step 5: Creating final extractor script")
    
    # Get absolute paths for the template
    raw_content_file_abs = os.path.abspath(raw_content_file)
    results_file_abs = os.path.abspath(results_file)
    
    template = f'''#!/usr/bin/env python3
import json
import re
import os

{extraction_code}

if __name__ == "__main__":
    # Use absolute paths to ensure files can be found
    raw_content_file = r"{raw_content_file_abs}"
    results_file = r"{results_file_abs}"
    
    print(f"Reading from: {{raw_content_file}}")
    print(f"Writing to: {{results_file}}")
    
    try:
        # Read the raw content
        with open(raw_content_file, "r", encoding="utf-8") as f:
            raw_text = f.read()
        
        print(f"Read {{len(raw_text)}} characters from raw content file")

        # Extract information from the provided text
        apartments_data = extract_apartment_info(raw_text)
        print(f"Extracted {{len(apartments_data)}} apartment entries")
        print(apartments_data)

        # Save results
        with open(results_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(apartments_data, indent=2))
        
        print(f"Results successfully saved to: {{results_file}}")
        
    except FileNotFoundError as e:
        print(f"Error: File not found - {{e}}")
        print(f"Current working directory: {{os.getcwd()}}")
        print(f"Raw content file exists: {{os.path.exists(raw_content_file)}}")
        print(f"Results directory exists: {{os.path.exists(os.path.dirname(results_file))}}")
    except Exception as e:
        print(f"Error during extraction: {{e}}")
        import traceback
        traceback.print_exc()
'''
    
    # Save final extractor
    with open(final_extractor_file, "w", encoding="utf-8") as f:
        f.write(template)
    
    print("Final extractor script created")
    print(f"Raw content file path: {raw_content_file_abs}")
    print(f"Results file path: {results_file_abs}")
    return final_extractor_file

def step6_execute_extraction(final_extractor_file, results_file):
    """Step 6: Execute the extraction to get apartment data"""
    print("Step 6: Executing extraction")
    
    try:
        import subprocess
        
        # Get the absolute path to the extractor script
        extractor_script_abs = os.path.abspath(final_extractor_file)
        extractor_dir_abs = os.path.dirname(extractor_script_abs)
        
        print(f"Running extractor script: {extractor_script_abs}")
        print(f"Working directory: {extractor_dir_abs}")
        
        # Run the script from its own directory
        result = subprocess.run([sys.executable, extractor_script_abs], 
                             capture_output=True, text=True, cwd=extractor_dir_abs)
        
        if result.returncode == 0:
            print("Extraction successful")
            print(f"Output: {result.stdout}")
            
            # Try to read results
            if os.path.exists(results_file):
                with open(results_file, "r") as f:
                    results = json.load(f)
                return results
            else:
                print("Results file not found after extraction")
                return None
        else:
            print(f"Extraction failed: {result.stderr}")
            return None
            
    except Exception as e:
        print(f"Error during extraction: {e}")
        return None

def run_extractor_manually(final_extractor_file, results_file):
    """Manually run the extractor script for debugging"""
    print(f"\n=== Manual Extraction Debug ===")
    print(f"Running extractor script: {final_extractor_file}")
    
    if not os.path.exists(final_extractor_file):
        print(f"❌ Extractor script not found: {final_extractor_file}")
        return None
        
    try:
        import subprocess
        
        # Get the absolute path to the extractor script
        extractor_script_abs = os.path.abspath(final_extractor_file)
        extractor_dir_abs = os.path.dirname(extractor_script_abs)
        
        print(f"Absolute script path: {extractor_script_abs}")
        print(f"Working directory: {extractor_dir_abs}")
        
        result = subprocess.run([sys.executable, extractor_script_abs], 
                             capture_output=True, text=True, 
                             cwd=extractor_dir_abs)
        
        print(f"Return code: {result.returncode}")
        print(f"STDOUT: {result.stdout}")
        if result.stderr:
            print(f"STDERR: {result.stderr}")
        
        if result.returncode == 0:
            print("✅ Manual extraction completed successfully")
            # Check if results file was created
            if os.path.exists(results_file):
                print(f"✅ Results file found: {results_file}")
                with open(results_file, "r") as f:
                    results = json.load(f)
                return results
            else:
                print(f"❌ Results file not found at expected location: {results_file}")
                return None
        else:
            print("❌ Manual extraction failed")
            return None
            
    except Exception as e:
        print(f"❌ Error during manual extraction: {e}")
        return None

def debug_file_paths(data_dir, resdir, extractor_dir, candidates_file, selected_url_file, 
                     raw_content_file, extraction_code_file, final_extractor_file, results_file):
    """Debug method to show current file paths and working directory"""
    print("\n=== Debug File Paths ===")
    print(f"Current working directory: {os.getcwd()}")
    print(f"Data directory: {os.path.abspath(data_dir)}")
    print(f"Result directory: {os.path.abspath(resdir)}")
    print(f"Extractor directory: {os.path.abspath(extractor_dir)}")
    print(f"Candidates file: {os.path.abspath(candidates_file)}")
    print(f"Selected URL file: {os.path.abspath(selected_url_file)}")
    print(f"Raw content file: {os.path.abspath(raw_content_file)}")
    print(f"Extraction code file: {os.path.abspath(extraction_code_file)}")
    print(f"Final extractor file: {os.path.abspath(final_extractor_file)}")
    print(f"Results file: {os.path.abspath(results_file)}")
    
    # Check which files exist
    print("\n=== File Existence Check ===")
    files_to_check = [
        candidates_file,
        selected_url_file,
        raw_content_file,
        extraction_code_file,
        final_extractor_file,
        results_file
    ]
    
    for file_path in files_to_check:
        exists = os.path.exists(file_path)
        print(f"{'✅' if exists else '❌'} {file_path}")
    
    # Check directories
    print("\n=== Directory Existence Check ===")
    dirs_to_check = [data_dir, resdir, extractor_dir]
    for dir_path in dirs_to_check:
        exists = os.path.exists(dir_path)
        print(f"{'✅' if exists else '❌'} {dir_path}")
    
    print("=" * 40)
