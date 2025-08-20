#!/usr/bin/env python3
"""
Test script for batch scraping functionality
"""

import json
from pathlib import Path
from json_scraper import JsonApartmentScraper

def test_json_loading():
    """Test loading apartments from JSON file"""
    print("🧪 Testing JSON loading...")
    
    # Test with the real JSON file
    json_file = "real_service_San_Jose_CA.json"
    
    if not Path(json_file).exists():
        print(f"❌ JSON file not found: {json_file}")
        print("Please make sure the JSON file is in the current directory")
        return False
    
    # Create scraper instance
    api_key = 'sk-proj-YweniZRmK5tKWgCwZ-RaL_wJxSt2VRuZ-RaL_wJxSt2VRuZ0C7KrU-orzFzAGYxjXwly8du7u5urkaokd0r3s4LjOT3BlbkFJhhi3UAyaU91iqEFI563AHSbZvq389WnDtsvK7SXjzaSEgjzQlahmvNd3cZtjgkTEnaAWSBd5wA'
    scraper = JsonApartmentScraper(api_key)
    
    # Load apartments
    apartments = scraper.load_apartments_from_json(json_file)
    
    if not apartments:
        print("❌ No apartments loaded")
        return False
    
    print(f"✅ Successfully loaded {len(apartments)} apartments")
    
    # Show sample apartments
    print("\n📋 Sample apartments:")
    for i, apt in enumerate(apartments[:5], 1):
        print(f"  {i}. {apt['name']}")
        print(f"     URL: {apt['url']}")
        print(f"     City: {apt['city']}, {apt['state']}")
        print(f"     Rating: {apt['rating']}")
        print()
    
    return True

def test_single_apartment_scraping():
    """Test scraping a single apartment"""
    print("\n🧪 Testing single apartment scraping...")
    
    json_file = "real_service_San_Jose_CA.json"
    
    if not Path(json_file).exists():
        print(f"❌ JSON file not found: {json_file}")
        return False
    
    # Create scraper instance
    api_key = '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'
    scraper = JsonApartmentScraper(api_key)
    
    # Load apartments
    apartments = scraper.load_apartments_from_json(json_file)
    
    if not apartments:
        print("❌ No apartments loaded")
        return False
    
    # Test with first apartment
    test_apt = apartments[0]
    print(f"🔍 Testing with: {test_apt['name']}")
    
    # Scrape single apartment
    result = scraper.scrape_apartment(test_apt, save_results=True, output_dir="test_results")
    
    if result['success']:
        print(f"✅ Successfully scraped {result['entries_count']} entries")
        return True
    else:
        print(f"❌ Failed to scrape: {result['error']}")
        return False

def test_batch_scraping_limited():
    """Test batch scraping with limited apartments"""
    print("\n🧪 Testing limited batch scraping...")
    
    json_file = "real_service_San_Jose_CA.json"
    
    if not Path(json_file).exists():
        print(f"❌ JSON file not found: {json_file}")
        return False
    
    # Create scraper instance
    api_key = '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'
    scraper = JsonApartmentScraper(api_key)
    
    # Test with limited apartments (first 3)
    results = scraper.scrape_all_apartments(json_file, "test_batch_results", max_apartments=3)
    
    if results:
        successful = [r for r in results if r['success']]
        print(f"✅ Batch scraping completed: {len(successful)} successful, {len(results) - len(successful)} failed")
        return True
    else:
        print("❌ Batch scraping failed")
        return False

def main():
    """Main test function"""
    print("🚀 Testing Batch Scraping Functionality")
    print("=" * 60)
    
    # Test 1: JSON loading
    test1_success = test_json_loading()
    
    # Test 2: Single apartment scraping
    test2_success = test_single_apartment_scraping()
    
    # Test 3: Limited batch scraping
    test3_success = test_batch_scraping_limited()
    
    print("\n" + "=" * 60)
    print("🎯 TEST RESULTS:")
    print(f"  JSON Loading: {'✅ PASS' if test1_success else '❌ FAIL'}")
    print(f"  Single Scraping: {'✅ PASS' if test2_success else '❌ FAIL'}")
    print(f"  Batch Scraping: {'✅ PASS' if test3_success else '❌ FAIL'}")
    
    if all([test1_success, test2_success, test3_success]):
        print("\n🎉 All tests passed! Batch scraping is working correctly.")
        print("\n📖 Usage examples:")
        print("  1. Scrape all apartments:")
        print("     python json_scraper.py real_service_San_Jose_CA.json results")
        print("  2. Scrape limited apartments:")
        print("     python json_scraper.py real_service_San_Jose_CA.json results 10")
        print("  3. Use as a module:")
        print("     from json_scraper import JsonApartmentScraper")
    else:
        print("\n💥 Some tests failed. Please check the errors above.")

if __name__ == "__main__":
    main()
