#!/usr/bin/env python3
"""
Simple command-line interface for running the integrated apartment scraper
"""

import sys
from integrated_apartment_scraper import IntegratedApartmentScraper

def main():
    # Configuration
    OPENAI_API_KEY = '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'
    
    # Predefined apartment complexes
    apartments = {
        "vista_99": "https://www.equityapartments.com/san-francisco-bay/north-san-jose/vista-99-apartments",
        "santa_clara_square": "https://www.irvinecompanyapartments.com/locations/northern-california/santa-clara/santa-clara-square.html",
        "the_benton": "https://prometheusapartments.com/ca/santa-clara-apartments/the-benton"
    }
    
    print("Available apartment complexes:")
    for key, url in apartments.items():
        print(f"  {key}: {url}")
    
    if len(sys.argv) < 2:
        print("\nUsage: python run_scraper.py <apartment_name> [custom_url]")
        print("Examples:")
        print("  python run_scraper.py vista_99")
        print("  python run_scraper.py custom_apt https://example.com/apartments")
        return
    
    apartment_name = sys.argv[1]
    
    if len(sys.argv) > 2:
        # Custom URL provided
        homepage_url = sys.argv[2]
    elif apartment_name in apartments:
        # Use predefined URL
        homepage_url = apartments[apartment_name]
    else:
        print(f"Unknown apartment: {apartment_name}")
        print("Available options:", list(apartments.keys()))
        return
    
    print(f"\nStarting scraper for: {apartment_name}")
    print(f"URL: {homepage_url}")
    
    # Create scraper instance
    scraper = IntegratedApartmentScraper(OPENAI_API_KEY, apartment_name)
    
    # Run the full pipeline
    results = scraper.run_full_pipeline(homepage_url)
    
    if results:
        print(f"\n✅ Successfully extracted {len(results)} apartment entries:")
        for i, apt in enumerate(results, 1):
            print(f"  {i}. {apt}")
    else:
        print("\n❌ No results extracted")

if __name__ == "__main__":
    main()
