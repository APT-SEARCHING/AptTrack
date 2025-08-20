#!/usr/bin/env python3
"""
JSON-based apartment scraper module
Can be used to scrape specific apartments or as a library
"""

import json
import os
from pathlib import Path
from integrated_apartment_scraper import IntegratedApartmentScraper

class JsonApartmentScraper:
    """Scraper class for processing apartments from JSON data"""
    
    def __init__(self, openai_api_key):
        self.openai_api_key = openai_api_key
        self.results = []
    
    def load_apartments_from_json(self, json_file_path):
        """Load and parse apartments from JSON file"""
        try:
            with open(json_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            apartments = []
            for place_id, place_data in data.items():
                name = place_data.get('title', 'Unknown')
                source_url = place_data.get('source_url', '')
                
                # Only include apartments with valid URLs
                if source_url and source_url.startswith('http'):
                    apartments.append({
                        'name': name,
                        'url': source_url,
                        'place_id': place_id,
                        'city': place_data.get('city', ''),
                        'state': place_data.get('state', ''),
                        'rating': place_data.get('rating', 0)
                    })
            
            return apartments
        except Exception as e:
            print(f"❌ Error loading JSON file: {e}")
            return []
    
    def scrape_apartment(self, apartment_data, save_results=True, output_dir="results"):
        """Scrape a single apartment"""
        name = apartment_data['name']
        url = apartment_data['url']
        
        print(f"🔍 Scraping: {name}")
        print(f"   URL: {url}")
        
        try:
            # Create clean key for scraper
            clean_name = name.lower().replace(' ', '_').replace('-', '_').replace(',', '').replace('.', '')
            clean_name = ''.join(c for c in clean_name if c.isalnum() or c == '_')
            
            # Create scraper instance
            scraper = IntegratedApartmentScraper(self.openai_api_key, clean_name)
            
            # Run scraper
            results = scraper.run_full_pipeline(url)
            
            if results:
                print(f"   ✅ Success! Extracted {len(results)} entries")
                
                # Save results if requested
                if save_results:
                    output_path = Path(output_dir)
                    output_path.mkdir(exist_ok=True)
                    
                    result_file = output_path / f"{clean_name}_results.json"
                    with open(result_file, 'w', encoding='utf-8') as f:
                        json.dump({
                            'apartment_name': name,
                            'source_url': url,
                            'place_id': apartment_data['place_id'],
                            'city': apartment_data['city'],
                            'state': apartment_data['state'],
                            'rating': apartment_data['rating'],
                            'scraped_data': results,
                            'scraper_key': clean_name
                        }, f, indent=2, ensure_ascii=False, default=str)
                    
                    print(f"   💾 Results saved to: {result_file}")
                
                return {
                    'success': True,
                    'name': name,
                    'url': url,
                    'entries_count': len(results),
                    'data': results,
                    'result_file': str(result_file) if save_results else None
                }
            else:
                print(f"   ⚠️  No results extracted")
                return {
                    'success': False,
                    'name': name,
                    'url': url,
                    'error': 'No results extracted'
                }
                
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
            return {
                'success': False,
                'name': name,
                'url': url,
                'error': str(e)
            }
    
    def scrape_all_apartments(self, json_file_path, output_dir="results", max_apartments=None):
        """Scrape all apartments from JSON file"""
        apartments = self.load_apartments_from_json(json_file_path)
        
        if not apartments:
            print("❌ No apartments found in JSON file")
            return []
        
        if max_apartments:
            apartments = apartments[:max_apartments]
            print(f"📝 Limiting to {max_apartments} apartments")
        
        print(f"🚀 Starting batch scraping for {len(apartments)} apartments...")
        print("=" * 80)
        
        results = []
        for i, apt_data in enumerate(apartments, 1):
            print(f"\n[{i}/{len(apartments)}] Processing apartment...")
            result = self.scrape_apartment(apt_data, save_results=True, output_dir=output_dir)
            results.append(result)
            print("-" * 60)
        
        # Save batch summary
        summary_file = Path(output_dir) / "batch_summary.json"
        successful = [r for r in results if r['success']]
        failed = [r for r in results if not r['success']]
        
        summary = {
            'total_apartments': len(apartments),
            'successful': len(successful),
            'failed': len(failed),
            'successful_apartments': [{'name': r['name'], 'entries': r['entries_count']} for r in successful],
            'failed_apartments': [{'name': r['name'], 'error': r['error']} for r in failed]
        }
        
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"\n🎯 Batch scraping completed!")
        print(f"📊 Summary: {len(successful)} successful, {len(failed)} failed")
        print(f"📋 Summary saved to: {summary_file}")
        
        return results

def main():
    """Command line interface"""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python json_scraper.py <json_file_path> [output_directory] [max_apartments]")
        print("Example: python json_scraper.py real_service_San_Jose_CA.json results 10")
        return
    
    json_file_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "results"
    max_apts = int(sys.argv[3]) if len(sys.argv) > 3 else None
    
    # Get API key from environment or use default
    api_key = os.environ.get('OPENAI_API_KEY', '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')
    
    scraper = JsonApartmentScraper(api_key)
    scraper.scrape_all_apartments(json_file_path, output_dir, max_apts)

if __name__ == "__main__":
    main()
