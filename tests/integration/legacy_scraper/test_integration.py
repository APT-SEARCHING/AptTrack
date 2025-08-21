#!/usr/bin/env python3
"""
Test script to verify the integrated scraper works correctly
"""

import sys
import os

def test_imports():
    """Test that all required modules can be imported"""
    try:
        from integrated_apartment_scraper import IntegratedApartmentScraper
        print("✅ Successfully imported IntegratedApartmentScraper")
        return True
    except ImportError as e:
        print(f"❌ Failed to import IntegratedApartmentScraper: {e}")
        return False

def test_instantiation():
    """Test that the scraper can be instantiated"""
    try:
        from integrated_apartment_scraper import IntegratedApartmentScraper
        
        # Test with dummy API key
        scraper = IntegratedApartmentScraper("dummy_key", "test_apt")
        print("✅ Successfully instantiated scraper")
        
        # Check that all required methods exist
        required_methods = [
            'step1_find_homepage_candidates',
            'step2_llm_floor_finder', 
            'step3_crawl_floor_plans',
            'step4_llm_code_generator',
            'step5_create_final_extractor',
            'step6_execute_extraction',
            'run_full_pipeline'
        ]
        
        for method in required_methods:
            if hasattr(scraper, method):
                print(f"✅ Method {method} exists")
            else:
                print(f"❌ Method {method} missing")
                return False
        
        # Check that directories are created
        if os.path.exists(scraper.data_dir):
            print(f"✅ Data directory '{scraper.data_dir}' exists")
        else:
            print(f"❌ Data directory '{scraper.data_dir}' missing")
            return False
            
        if os.path.exists(scraper.extractor_dir):
            print(f"✅ Extractor directory '{scraper.extractor_dir}' exists")
        else:
            print(f"❌ Extractor directory '{scraper.extractor_dir}' missing")
            return False
                
        return True
        
    except Exception as e:
        print(f"❌ Failed to instantiate scraper: {e}")
        return False

def test_file_structure():
    """Test that all required files exist"""
    required_files = [
        'integrated_apartment_scraper.py',
        'run_scraper.py',
        'requirements.txt',
        'README.md'
    ]
    
    all_exist = True
    for file in required_files:
        if os.path.exists(file):
            print(f"✅ {file} exists")
        else:
            print(f"❌ {file} missing")
            all_exist = False
    
    return all_exist

def test_directory_creation():
    """Test that the scraper creates necessary directories"""
    try:
        from integrated_apartment_scraper import IntegratedApartmentScraper
        
        # Create a temporary scraper instance
        scraper = IntegratedApartmentScraper("dummy_key", "test_apt")
        
        # Check if directories exist
        data_dir = scraper.data_dir
        extractor_dir = scraper.extractor_dir
        
        if os.path.exists(data_dir):
            print(f"✅ Data directory '{data_dir}' created successfully")
        else:
            print(f"❌ Data directory '{data_dir}' not created")
            return False
            
        if os.path.exists(extractor_dir):
            print(f"✅ Extractor directory '{extractor_dir}' created successfully")
        else:
            print(f"❌ Extractor directory '{extractor_dir}' not created")
            return False
        
        # Clean up test directories
        if os.path.exists(data_dir):
            import shutil
            shutil.rmtree(data_dir)
        if os.path.exists(extractor_dir):
            import shutil
            shutil.rmtree(extractor_dir)
            
        return True
        
    except Exception as e:
        print(f"❌ Directory creation test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("Testing Integrated Apartment Scraper")
    print("=" * 40)
    
    tests = [
        ("File Structure", test_file_structure),
        ("Module Imports", test_imports),
        ("Class Instantiation", test_instantiation),
        ("Directory Creation", test_directory_creation)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\nRunning: {test_name}")
        if test_func():
            passed += 1
        else:
            print(f"❌ {test_name} failed")
    
    print("\n" + "=" * 40)
    print(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        print("🎉 All tests passed! The integrated scraper is ready to use.")
        print("\nTo get started, run:")
        print("  python run_scraper.py vista_99")
        print("\nFiles will be organized in:")
        print("  📁 data/ - for all intermediate data files")
        print("  📁 extractor_script/ - for final extraction scripts")
    else:
        print("⚠️  Some tests failed. Please check the errors above.")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
