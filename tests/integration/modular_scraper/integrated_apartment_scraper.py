#!/usr/bin/env python3
"""
Integrated Apartment Scraper
Combines all the individual functions into one cohesive workflow:
1. Find homepage and extract candidate URLs
2. Use LLM to identify floor plan page
3. Crawl the floor plan page
4. Use LLM to generate extraction code
5. Create the final extractor script
6. Execute the extraction to get apartment data

This is the full pipeline that should be run once per apartment to generate the extractor script.
"""

import sys
import os
import json
from scraper_steps import (
    step1_find_homepage_candidates,
    step2_llm_floor_finder,
    step3_crawl_floor_plans,
    step4_llm_code_generator,
    step5_create_final_extractor,
    step6_execute_extraction,
    run_extractor_manually,
    debug_file_paths
)

class IntegratedApartmentScraper:
    def __init__(self, openai_api_key, apartment_name="apartment"):
        self.openai_api_key = openai_api_key
        self.apartment_name = apartment_name
        
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
    
    def run_full_pipeline(self, homepage_url):
        """Run the complete pipeline from homepage to extracted data"""
        print(f"Starting full pipeline for {self.apartment_name}")
        print("=" * 50)
        
        try:
            # Step 1: Find candidates
            candidates = step1_find_homepage_candidates(homepage_url, self.candidates_file)
            if not candidates:
                print("No candidates found, using homepage as floor plan URL")
                selected_url = homepage_url
            else:
                # Step 2: LLM selects best URL
                selected_url = step2_llm_floor_finder(candidates, self.openai_api_key, self.selected_url_file)
            
            # Step 3: Crawl floor plans
            raw_content = step3_crawl_floor_plans(selected_url, self.raw_content_file)
            
            # Step 4: Generate extraction code
            extraction_code = step4_llm_code_generator(raw_content, self.openai_api_key, self.extraction_code_file)
            
            # Step 5: Create final extractor
            step5_create_final_extractor(extraction_code, self.raw_content_file, self.results_file, self.final_extractor_file)
            
            # Step 6: Execute extraction
            results = step6_execute_extraction(self.final_extractor_file, self.results_file)
            
            print("=" * 50)
            print("Pipeline completed successfully!")
            print(f"Results saved to: {self.results_file}")
            print(f"Extractor script saved to: {self.final_extractor_file}")
            
            return results
            
        except Exception as e:
            print(f"Pipeline failed: {e}")
            return None
    
    def debug_file_paths(self):
        """Debug method to show current file paths and working directory"""
        debug_file_paths(
            self.data_dir, 
            self.resdir, 
            self.extractor_dir, 
            self.candidates_file,
            self.selected_url_file,
            self.raw_content_file,
            self.extraction_code_file,
            self.final_extractor_file,
            self.results_file
        )

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
        print(f"\n✅ Full pipeline completed! You can now use daily_apartment_scraper.py for daily updates.")
    else:
        print("No results extracted")
        print("\nTroubleshooting tips:")
        print("1. Check if all required files were created")
        print("2. Verify the OpenAI API key is valid")
        print("3. Check the generated extractor script for errors")
        print("4. Run the extractor script manually to see detailed errors")
        
        # Try manual extraction as a last resort
        print("\nAttempting manual extraction...")
        manual_results = run_extractor_manually(scraper.final_extractor_file, scraper.results_file)
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
