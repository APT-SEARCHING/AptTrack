#!/usr/bin/env python3
"""
Daily Apartment Scraper
For daily use cases when you already have the extractor script.
Only runs step 3 (crawl) and step 6 (extract) to get latest apartment data.
"""

import sys
import os
import json
from scraper_steps import step3_crawl_floor_plans, step6_execute_extraction, debug_file_paths

class DailyApartmentScraper:
    def __init__(self, apartment_name, floor_plan_url):
        self.apartment_name = apartment_name
        self.floor_plan_url = floor_plan_url
        
        # Create necessary directories
        self.data_dir = "data"
        self.resdir = "result"
        self.extractor_dir = "extractor_script"
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.extractor_dir, exist_ok=True)
        os.makedirs(self.resdir, exist_ok=True)
        
        # File paths for daily run
        self.raw_content_file = os.path.join(self.data_dir, f"output_{apartment_name}.txt")
        self.final_extractor_file = os.path.join(self.extractor_dir, f"llm_code_script_final_{apartment_name}.py")
        self.results_file = os.path.join(self.resdir, f"parser_output_{apartment_name}.txt")
        
    def check_extractor_exists(self):
        """Check if the extractor script exists for this apartment"""
        if not os.path.exists(self.final_extractor_file):
            print(f"❌ Extractor script not found: {self.final_extractor_file}")
            print("Please run the full pipeline first to generate the extractor script.")
            return False
        return True
    
    def run_daily_update(self):
        """Run the daily update pipeline (steps 3 and 6 only)"""
        print(f"Starting daily update for {self.apartment_name}")
        print("=" * 50)
        
        # Check if extractor exists
        if not self.check_extractor_exists():
            return None
        
        try:
            # Step 3: Crawl floor plans (get latest data)
            print("Step 3: Crawling floor plan page for latest data...")
            raw_content = step3_crawl_floor_plans(self.floor_plan_url, self.raw_content_file)
            
            # Step 6: Execute extraction using existing extractor
            print("Step 6: Executing extraction with existing extractor...")
            results = step6_execute_extraction(self.final_extractor_file, self.results_file)
            
            print("=" * 50)
            if results:
                print("Daily update completed successfully!")
                print(f"Results saved to: {self.results_file}")
                print(f"Extracted {len(results)} apartment entries")
                return results
            else:
                print("Daily update failed during extraction")
                return None
                
        except Exception as e:
            print(f"Daily update failed: {e}")
            return None
    
    def debug_file_paths(self):
        """Debug method to show current file paths"""
        debug_file_paths(
            self.data_dir, 
            self.resdir, 
            self.extractor_dir, 
            "",  # candidates_file not used in daily run
            "",  # selected_url_file not used in daily run
            self.raw_content_file,
            "",  # extraction_code_file not used in daily run
            self.final_extractor_file,
            self.results_file
        )

def main():
    # Configuration
    if len(sys.argv) < 3:
        print("Usage: python daily_apartment_scraper.py <apartment_name> <floor_plan_url>")
        print("Example: python daily_apartment_scraper.py vista_99 https://www.equityapartments.com/san-francisco-bay/north-san-jose/vista-99-apartments/floor-plans")
        sys.exit(1)
    
    apartment_name = sys.argv[1]
    floor_plan_url = sys.argv[2]
    
    # Create scraper instance
    scraper = DailyApartmentScraper(apartment_name, floor_plan_url)
    
    # Show debug information
    scraper.debug_file_paths()
    
    # Run the daily update
    results = scraper.run_daily_update()
    
    # Show final status
    print("\n=== Final Status ===")
    scraper.debug_file_paths()
    
    if results:
        print(f"\n✅ Daily update successful! Found {len(results)} apartment entries:")
        for apt in results:
            print(f"  {apt}")
    else:
        print("❌ Daily update failed")
        print("\nTroubleshooting tips:")
        print("1. Make sure the extractor script exists in the extractor_script directory")
        print("2. Verify the floor plan URL is correct and accessible")
        print("3. Check if the website structure has changed (may need to regenerate extractor)")
        print("4. Run the full pipeline again if needed")

if __name__ == "__main__":
    main()
