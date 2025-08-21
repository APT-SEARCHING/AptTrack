#!/usr/bin/env python3
"""
AptTrack Integration Runner
Simple navigation script to help you choose which system to use
"""

import sys
import os

def show_menu():
    """Display the main menu"""
    print("🏠 AptTrack Integration Testing & Scraping")
    print("=" * 50)
    print()
    print("Choose your operation:")
    print()
    print("1. 🆕 Daily Apartment Updates (Recommended)")
    print("   - Use existing extractors for daily data")
    print("   - Fast, no LLM costs")
    print()
    print("2. 🔄 Batch Process Multiple Apartments")
    print("   - Process all apartments from JSON file")
    print("   - Generate extractors for multiple complexes")
    print()
    print("3. 🚀 Full Pipeline (First Time Setup)")
    print("   - Generate extractor for new apartment")
    print("   - One-time setup per apartment")
    print()
    print("4. 📜 Legacy Scraping Tools")
    print("   - Old scraping utilities")
    print("   - Database tools")
    print()
    print("5. 📚 View Documentation")
    print("   - Read detailed guides")
    print()
    print("0. Exit")
    print()

def run_daily_updates():
    """Navigate to daily updates"""
    print("\n🆕 Daily Apartment Updates")
    print("=" * 30)
    print("This system uses pre-generated extractors for fast daily updates.")
    print()
    print("Available commands:")
    print("cd modular_scraper")
    print()
    print("# Update single apartment:")
    print("python daily_apartment_scraper.py <apartment_name> <floor_plan_url>")
    print()
    print("# Update all apartments:")
    print("python run_daily_updates.py")
    print()
    print("Example:")
    print("python daily_apartment_scraper.py vista_99 \"https://www.equityapartments.com/san-francisco-bay/north-san-jose/vista-99-apartments/floor-plans\"")
    print()
    input("Press Enter to continue...")

def run_batch_processing():
    """Navigate to batch processing"""
    print("\n🔄 Batch Processing")
    print("=" * 20)
    print("This system processes multiple apartments from JSON data.")
    print()
    print("Available commands:")
    print("cd batch_processing")
    print()
    print("# Process all apartments:")
    print("python batch_scraper.py <json_file> <output_dir>")
    print()
    print("# Process limited apartments:")
    print("python json_scraper.py <json_file> <output_dir> [max_count]")
    print()
    print("Example:")
    print("python batch_scraper.py real_service_San_Jose_CA.json results")
    print()
    input("Press Enter to continue...")

def run_full_pipeline():
    """Navigate to full pipeline"""
    print("\n🚀 Full Pipeline (First Time Setup)")
    print("=" * 40)
    print("This system generates extractors for new apartments.")
    print()
    print("Available commands:")
    print("cd modular_scraper")
    print()
    print("# Generate extractor for new apartment:")
    print("python integrated_apartment_scraper.py <apartment_name> <homepage_url>")
    print()
    print("Example:")
    print("python integrated_apartment_scraper.py vista_99 \"https://www.equityapartments.com/san-francisco-bay/north-san-jose/vista-99-apartments\"")
    print()
    print("Note: This should only be run once per apartment!")
    print()
    input("Press Enter to continue...")

def show_legacy_tools():
    """Show legacy tools"""
    print("\n📜 Legacy Scraping Tools")
    print("=" * 25)
    print("These are older tools preserved for reference.")
    print()
    print("Available in legacy_scraper/ directory:")
    print("- run_scraper.py: Old command-line interface")
    print("- test_integration.py: Old integration tests")
    print("- crawl.py: Basic crawling utilities")
    print("- check_db_schema.py: Database schema checker")
    print("- run_migration.py: Database migration runner")
    print()
    print("Note: These tools are not recommended for daily use.")
    print()
    input("Press Enter to continue...")

def show_documentation():
    """Show documentation"""
    print("\n📚 Documentation")
    print("=" * 15)
    print("Available documentation:")
    print()
    print("📖 Main Guide:")
    print("   README.md (this directory)")
    print()
    print("🆕 Modular System:")
    print("   modular_scraper/README_MODULAR_SCRAPER.md")
    print()
    print("🔄 Batch Processing:")
    print("   batch_processing/BATCH_SCRAPING_README.md")
    print()
    print("📁 Directory Structure:")
    print("   tests/integration/")
    print("   ├── modular_scraper/     # Modern system")
    print("   ├── batch_processing/    # Batch operations")
    print("   └── legacy_scraper/      # Old tools")
    print()
    input("Press Enter to continue...")

def main():
    """Main menu loop"""
    while True:
        os.system('clear' if os.name == 'posix' else 'cls')
        show_menu()
        
        try:
            choice = input("Enter your choice (0-5): ").strip()
            
            if choice == '0':
                print("\n👋 Goodbye!")
                break
            elif choice == '1':
                run_daily_updates()
            elif choice == '2':
                run_batch_processing()
            elif choice == '3':
                run_full_pipeline()
            elif choice == '4':
                show_legacy_tools()
            elif choice == '5':
                show_documentation()
            else:
                print("\n❌ Invalid choice. Please enter 0-5.")
                input("Press Enter to continue...")
                
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")
            input("Press Enter to continue...")

if __name__ == "__main__":
    main()
