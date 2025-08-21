#!/usr/bin/env python3
"""
Batch scraper script that processes all apartments from the Google Maps JSON file
"""

import json
import sys
import os
from pathlib import Path
from integrated_apartment_scraper import IntegratedApartmentScraper

def load_apartments_from_json(json_file_path):
    """Load apartment data from the JSON file"""
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        apartments = {}
        for place_id, place_data in data.items():
            # Extract apartment name and source URL
            name = place_data.get('title', 'Unknown')
            source_url = place_data.get('source_url', '')
            
            # Only include apartments with valid URLs
            if source_url and source_url.startswith('http'):
                # Clean the name for use as a key
                clean_name = name.lower().replace(' ', '_').replace('-', '_').replace(',', '').replace('.', '')
                clean_name = ''.join(c for c in clean_name if c.isalnum() or c == '_')
                
                apartments[clean_name] = {
                    'name': name,
                    'url': source_url,
                    'place_id': place_id
                }
        
        return apartments
    except Exception as e:
        print(f"❌ Error loading JSON file: {e}")
        return {}

def run_batch_scraper(json_file_path, output_dir="batch_results"):
    """Run the scraper for all apartments in the JSON file"""
    
    # Load apartments from JSON
    print("📖 Loading apartments from JSON file...")
    apartments = load_apartments_from_json(json_file_path)
    
    if not apartments:
        print("❌ No apartments found in JSON file")
        return
    
    print(f"✅ Found {len(apartments)} apartments with valid URLs")
    
    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    # Configuration
    OPENAI_API_KEY = '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'
    
    # Track results
    results = {
        'successful': [],
        'failed': [],
        'skipped': []
    }
    
    print(f"\n🚀 Starting batch scraping for {len(apartments)} apartments...")
    print("=" * 80)
    
    for i, (apt_key, apt_data) in enumerate(apartments.items(), 1):
        apt_name = apt_data['name']
        apt_url = apt_data['url']
        place_id = apt_data['place_id']
        
        print(f"\n[{i}/{len(apartments)}] Processing: {apt_name}")
        print(f"   URL: {apt_url}")
        print(f"   Place ID: {place_id}")
        
        try:
            # Create scraper instance
            scraper = IntegratedApartmentScraper(OPENAI_API_KEY, apt_key)
            
            # Run the full pipeline
            print(f"   🔍 Running scraper...")
            apt_results = scraper.run_full_pipeline(apt_url)
            
            if apt_results:
                # Save individual results
                result_file = output_path / f"{apt_key}_results.json"
                with open(result_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        'apartment_name': apt_name,
                        'source_url': apt_url,
                        'place_id': place_id,
                        'scraped_data': apt_results,
                        'scraper_key': apt_key
                    }, f, indent=2, ensure_ascii=False, default=str)
                
                print(f"   ✅ Success! Extracted {len(apt_results)} entries")
                print(f"   💾 Results saved to: {result_file}")
                
                results['successful'].append({
                    'name': apt_name,
                    'key': apt_key,
                    'url': apt_url,
                    'entries_count': len(apt_results),
                    'result_file': str(result_file)
                })
            else:
                print(f"   ⚠️  No results extracted")
                results['failed'].append({
                    'name': apt_name,
                    'key': apt_key,
                    'url': apt_url,
                    'error': 'No results extracted'
                })
                
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
            results['failed'].append({
                'name': apt_name,
                'key': apt_key,
                'url': apt_url,
                'error': str(e)
            })
        
        print("-" * 60)
    
    # Save summary report
    summary_file = output_path / "batch_summary.json"
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump({
            'total_apartments': len(apartments),
            'successful': len(results['successful']),
            'failed': len(results['failed']),
            'successful_apartments': results['successful'],
            'failed_apartments': results['failed']
        }, f, indent=2, ensure_ascii=False, default=str)
    
    # Print final summary
    print("\n" + "=" * 80)
    print("🎯 BATCH SCRAPING COMPLETED!")
    print(f"📊 Summary:")
    print(f"   Total apartments: {len(apartments)}")
    print(f"   ✅ Successful: {len(results['successful'])}")
    print(f"   ❌ Failed: {len(results['failed'])}")
    print(f"   📁 Results saved to: {output_path}")
    print(f"   📋 Summary report: {summary_file}")
    
    if results['successful']:
        print(f"\n✅ Successfully scraped apartments:")
        for apt in results['successful']:
            print(f"   • {apt['name']} ({apt['entries_count']} entries)")
    
    if results['failed']:
        print(f"\n❌ Failed apartments:")
        for apt in results['failed']:
            print(f"   • {apt['name']}: {apt['error']}")
    
    return results

def main():
    """Main function"""
    if len(sys.argv) < 2:
        print("Usage: python batch_scraper.py <json_file_path> [output_directory]")
        print("Example: python batch_scraper.py real_service_San_Jose_CA.json batch_results")
        return
    
    json_file_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "batch_results"
    
    if not os.path.exists(json_file_path):
        print(f"❌ JSON file not found: {json_file_path}")
        return
    
    print("🚀 AptTrack Batch Scraper")
    print("=" * 50)
    print(f"Input JSON: {json_file_path}")
    print(f"Output directory: {output_dir}")
    
    # Run batch scraper
    results = run_batch_scraper(json_file_path, output_dir)
    
    if results:
        print(f"\n🎉 Batch processing completed!")
        print(f"Check the '{output_dir}' directory for results.")
    else:
        print(f"\n💥 Batch processing failed!")

if __name__ == "__main__":
    main()
