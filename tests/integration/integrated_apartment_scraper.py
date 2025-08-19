#!/usr/bin/env python3
"""
Integrated Apartment Scraper
Combines all the individual functions into one cohesive workflow:
1. Find homepage and extract candidate URLs
2. Use LLM to identify floor plan page
3. Crawl the floor plan page
4. Use LLM to generate extraction code
5. Execute the extraction to get apartment data
"""

import sys
import os
import json
import time
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from openai import OpenAI

class IntegratedApartmentScraper:
    def __init__(self, openai_api_key, apartment_name="apartment"):
        self.openai_api_key = openai_api_key
        self.apartment_name = apartment_name
        self.client = OpenAI(api_key=openai_api_key)
        
        # Create necessary directories
        self.data_dir = "data"
        self.resdir = "result"
        self.extractor_dir = "extractor_script"
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.extractor_dir, exist_ok=True)
        os.makedirs(self.resdir, exist_ok=True)
        
        # File paths for intermediate results
        self.candidates_file = os.path.join(self.data_dir, f"candidates_{apartment_name}.txt")
        self.selected_url_file = os.path.join(self.data_dir, f"selected_url_{apartment_name}.txt")
        self.raw_content_file = os.path.join(self.data_dir, f"output_{apartment_name}.txt")
        self.extraction_code_file = os.path.join(self.data_dir, f"llm_code_script_{apartment_name}.txt")
        self.final_extractor_file = os.path.join(self.extractor_dir, f"llm_code_script_final_{apartment_name}.py")
        self.results_file = os.path.join(self.resdir, f"parser_output_{apartment_name}.txt")
        
    def step1_find_homepage_candidates(self, homepage_url):
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
            with open(self.candidates_file, "w", encoding="utf-8") as f:
                f.write('\n'.join(candidates))
            
            print(f"Found {len(candidates)} candidate URLs")
            browser.close()
            
            return list(candidates)
    
    def step2_llm_floor_finder(self, candidates):
        """Step 2: Use LLM to identify the best floor plan page"""
        print("Step 2: Using LLM to identify floor plan page")
        
        candidates_text = '\n'.join(candidates[:10])  # Limit to first 10 URLs
        
        response = self.client.chat.completions.create(
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
        with open(self.selected_url_file, "w", encoding="utf-8") as f:
            f.write(selected_url)
        
        print(f"LLM selected: {selected_url}")
        return selected_url
    
    def step3_crawl_floor_plans(self, floor_plan_url):
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
            with open(self.raw_content_file, "w", encoding="utf-8") as f:
                f.write(txt)
            
            print(f"Extracted {len(txt)} characters of content")
            browser.close()
            
            return txt
    
    def step4_llm_code_generator(self, raw_text):
        """Step 4: Use LLM to generate extraction code"""
        print("Step 4: Generating extraction code with LLM")
        
        response = self.client.chat.completions.create(
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
        with open(self.extraction_code_file, "w", encoding="utf-8") as f:
            f.write(extraction_code)
        
        print("Extraction code generated")
        return extraction_code
    
    def step5_create_final_extractor(self, extraction_code):
        """Step 5: Create the final extractor script"""
        print("Step 5: Creating final extractor script")
        
        # Get absolute paths for the template
        raw_content_file_abs = os.path.abspath(self.raw_content_file)
        results_file_abs = os.path.abspath(self.results_file)
        
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
        with open(self.final_extractor_file, "w", encoding="utf-8") as f:
            f.write(template)
        
        print("Final extractor script created")
        print(f"Raw content file path: {raw_content_file_abs}")
        print(f"Results file path: {results_file_abs}")
        return self.final_extractor_file
    
    def step6_execute_extraction(self):
        """Step 6: Execute the extraction to get apartment data"""
        print("Step 6: Executing extraction")
        
        # Import and run the generated extractor
        # try:
        #     # Create a temporary module to run the extraction
        #     import importlib.util
        #     spec = importlib.util.spec_from_file_location("extractor", self.final_extractor_file)
        #     extractor_module = importlib.util.module_from_spec(spec)
        #     spec.loader.exec_module(extractor_module)
            
        #     # The module should have run and saved results
        #     print("Extraction completed successfully")
            
        #     # Wait a moment for file writing to complete
        #     import time
        #     time.sleep(1)
            
        #     # Read and return results
        #     if os.path.exists(self.results_file):
        #         with open(self.results_file, "r") as f:
        #             results = json.load(f)
        #         return results
        #     else:
        #         print(f"Warning: Results file not found at {self.results_file}")
        #         print("Checking if results were saved to a different location...")
                
                # # Try to find the results file in the data directory
                # data_dir = self.data_dir
                # if os.path.exists(data_dir):
                #     for file in os.listdir(data_dir):
                #         if file.startswith("parser_output_") and file.endswith(".txt"):
                #             results_file = os.path.join(data_dir, file)
                #             print(f"Found results file in data directory: {results_file}")
                #             with open(results_file, "r") as f:
                #                 results = json.load(f)
                #             return results
                
                # print("No results file found. Extraction may have failed.")
                # return None
            
        # except Exception as e:
        #     print(f"Error during extraction: {e}")
        print("Attempting to run extraction manually...")
        
        # Try to run the extraction script directly
        try:
            import subprocess
            
            # Get the absolute path to the extractor script
            extractor_script_abs = os.path.abspath(self.final_extractor_file)
            extractor_dir_abs = os.path.dirname(extractor_script_abs)
            
            print(f"Running extractor script: {extractor_script_abs}")
            print(f"Working directory: {extractor_dir_abs}")
            
            # Run the script from its own directory
            result = subprocess.run([sys.executable, extractor_script_abs], 
                                 capture_output=True, text=True, cwd=extractor_dir_abs)
            
            if result.returncode == 0:
                print("Manual extraction successful")
                print(f"Output: {result.stdout}")
                # Try to read results again
                if os.path.exists(self.results_file):
                    with open(self.results_file, "r") as f:
                        results = json.load(f)
                    return results
                else:
                    print("Results file still not found after manual extraction")
                    # Check if it was created in result directory
                    if os.path.exists(self.resdir):
                        for file in os.listdir(self.resdir):
                            if file.startswith("parser_output_") and file.endswith(".txt"):
                                results_file = os.path.join(self.resdir, file)
                                print(f"Found results file in result directory after manual extraction: {results_file}")
                                with open(results_file, "r") as f:
                                    results = json.load(f)
                                return results
                    
                    # Check data directory as fallback
                    data_dir = self.data_dir
                    if os.path.exists(data_dir):
                        for file in os.listdir(data_dir):
                            if file.startswith("parser_output_") and file.endswith(".txt"):
                                results_file = os.path.join(data_dir, file)
                                print(f"Found results file in data directory after manual extraction: {results_file}")
                                with open(results_file, "r") as f:
                                    results = json.load(f)
                                return results
            else:
                print(f"Manual extraction failed: {result.stderr}")
                
        except Exception as manual_error:
            print(f"Manual extraction also failed: {manual_error}")
        
        return None
    
    def run_extractor_manually(self):
        """Manually run the extractor script for debugging"""
        print(f"\n=== Manual Extraction Debug ===")
        print(f"Running extractor script: {self.final_extractor_file}")
        
        if not os.path.exists(self.final_extractor_file):
            print(f"❌ Extractor script not found: {self.final_extractor_file}")
            return None
            
        try:
            import subprocess
            
            # Get the absolute path to the extractor script
            extractor_script_abs = os.path.abspath(self.final_extractor_file)
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
                # Check if results file was created in result directory
                if os.path.exists(self.results_file):
                    print(f"✅ Results file found: {self.results_file}")
                    with open(self.results_file, "r") as f:
                        results = json.load(f)
                    return results
                else:
                    print(f"❌ Results file not found at expected location: {self.results_file}")
                    # Check result directory
                    if os.path.exists(self.resdir):
                        for file in os.listdir(self.resdir):
                            if file.startswith("parser_output_") and file.endswith(".txt"):
                                results_file = os.path.join(self.resdir, file)
                                print(f"✅ Found results file in result directory: {results_file}")
                                with open(results_file, "r") as f:
                                    results = json.load(f)
                                return results
                    
                    # Check data directory as fallback
                    data_dir = self.data_dir
                    if os.path.exists(data_dir):
                        for file in os.listdir(data_dir):
                            if file.startswith("parser_output_") and file.endswith(".txt"):
                                results_file = os.path.join(data_dir, file)
                                print(f"✅ Found results file in data directory: {results_file}")
                                with open(results_file, "r") as f:
                                    results = json.load(f)
                                return results
                    
                    print("❌ No results file found in any location")
                    return None
            else:
                print("❌ Manual extraction failed")
                return None
                
        except Exception as e:
            print(f"❌ Error during manual extraction: {e}")
            return None
    
    def debug_file_paths(self):
        """Debug method to show current file paths and working directory"""
        print("\n=== Debug File Paths ===")
        print(f"Current working directory: {os.getcwd()}")
        print(f"Data directory: {os.path.abspath(self.data_dir)}")
        print(f"Result directory: {os.path.abspath(self.resdir)}")
        print(f"Extractor directory: {os.path.abspath(self.extractor_dir)}")
        print(f"Candidates file: {os.path.abspath(self.candidates_file)}")
        print(f"Selected URL file: {os.path.abspath(self.selected_url_file)}")
        print(f"Raw content file: {os.path.abspath(self.raw_content_file)}")
        print(f"Extraction code file: {os.path.abspath(self.extraction_code_file)}")
        print(f"Final extractor file: {os.path.abspath(self.final_extractor_file)}")
        print(f"Results file: {os.path.abspath(self.results_file)}")
        
        # Check which files exist
        print("\n=== File Existence Check ===")
        files_to_check = [
            self.candidates_file,
            self.selected_url_file,
            self.raw_content_file,
            self.extraction_code_file,
            self.final_extractor_file,
            self.results_file
        ]
        
        for file_path in files_to_check:
            exists = os.path.exists(file_path)
            print(f"{'✅' if exists else '❌'} {file_path}")
        
        # Check directories
        print("\n=== Directory Existence Check ===")
        dirs_to_check = [self.data_dir, self.resdir, self.extractor_dir]
        for dir_path in dirs_to_check:
            exists = os.path.exists(dir_path)
            print(f"{'✅' if exists else '❌'} {dir_path}")
        
        print("=" * 40)
    
    def run_full_pipeline(self, homepage_url):
        """Run the complete pipeline from homepage to extracted data"""
        print(f"Starting full pipeline for {self.apartment_name}")
        print("=" * 50)
        
        try:
            # Step 1: Find candidates
            candidates = self.step1_find_homepage_candidates(homepage_url)
            if not candidates:
                selected_url = homepage_url
            else:
                 # Step 2: LLM selects best URL
                selected_url = self.step2_llm_floor_finder(candidates)
                # print("No candidates found. Exiting.")
                # return None
            
            # Step 3: Crawl floor plans
            raw_content = self.step3_crawl_floor_plans(selected_url)
            
            # Step 4: Generate extraction code
            extraction_code = self.step4_llm_code_generator(raw_content)
            # with open(self.extraction_code_file, "r") as f:
            #     extraction_code = f.read()
            # Step 5: Create final extractor
            self.step5_create_final_extractor(extraction_code)
            
            # Step 6: Execute extraction
            results = self.step6_execute_extraction()
            
            print("=" * 50)
            print("Pipeline completed successfully!")
            print(f"Results saved to: {self.results_file}")
            print(f"Extractor script saved to: {self.final_extractor_file}")
            
            return results
            
        except Exception as e:
            print(f"Pipeline failed: {e}")
            return None

def main():
    # Configuration
    OPENAI_API_KEY = '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'
    
    # Get apartment name from command line or use default
    apartment_name = sys.argv[1] if len(sys.argv) > 1 else "vista_99"
    
    # Get homepage URL from command line or use default
    homepage_url = sys.argv[2] if len(sys.argv) > 2 else "https://www.equityapartments.com/san-francisco-bay/north-san-jose/vista-99-apartments"
    
    # Create scraper instance
    scraper = IntegratedApartmentScraper(OPENAI_API_KEY, apartment_name)
    
    # Show debug information
    scraper.debug_file_paths()
    
    # Run the full pipeline
    results = scraper.run_full_pipeline(homepage_url)
    
    # Show final debug information
    print("\n=== Final Status ===")
    scraper.debug_file_paths()
    
    if results:
        print(f"\nExtracted {len(results)} apartment entries:")
        for apt in results:
            print(f"  {apt}")
    else:
        print("No results extracted")
        print("\nTroubleshooting tips:")
        print("1. Check if all required files were created")
        print("2. Verify the OpenAI API key is valid")
        print("3. Check the generated extractor script for errors")
        print("4. Run the extractor script manually to see detailed errors")
        
        # Try manual extraction as a last resort
        print("\nAttempting manual extraction...")
        manual_results = scraper.run_extractor_manually()
        if manual_results:
            print(f"\n✅ Manual extraction successful! Found {len(manual_results)} apartment entries:")
            for apt in manual_results:
                print(f"  {apt}")
        else:
            print("❌ Manual extraction also failed")
            print("\nTo debug further, you can:")
            print(f"1. Check the generated script: {scraper.final_extractor_file}")
            print(f"2. Run it manually: python {scraper.final_extractor_file}")
            print(f"3. Check the data directory: {scraper.data_dir}")
            print(f"4. Check the result directory: {scraper.resdir}")

if __name__ == "__main__":
    main()
