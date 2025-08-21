#!/usr/bin/env python3
"""
Batch Daily Updates Runner
Run daily updates for multiple apartments at once
"""

import sys
import os
import json
from daily_apartment_scraper import DailyApartmentScraper

def run_batch_daily_updates(apartments_config):
    """
    Run daily updates for multiple apartments
    
    apartments_config: list of dicts with 'name' and 'floor_plan_url' keys
    """
    print("Starting batch daily updates...")
    print("=" * 60)
    
    results = {}
    
    for i, apt_config in enumerate(apartments_config, 1):
        print(f"\n[{i}/{len(apartments_config)}] Processing {apt_config['name']}...")
        print("-" * 40)
        
        try:
            scraper = DailyApartmentScraper(apt_config['name'], apt_config['floor_plan_url'])
            apt_results = scraper.run_daily_update()
            
            if apt_results:
                results[apt_config['name']] = {
                    'status': 'success',
                    'count': len(apt_results),
                    'data': apt_results
                }
                print(f"✅ {apt_config['name']}: {len(apt_results)} apartments found")
            else:
                results[apt_config['name']] = {
                    'status': 'failed',
                    'count': 0,
                    'data': None
                }
                print(f"❌ {apt_config['name']}: Update failed")
                
        except Exception as e:
            results[apt_config['name']] = {
                'status': 'error',
                'count': 0,
                'error': str(e),
                'data': None
            }
            print(f"❌ {apt_config['name']}: Error - {e}")
    
    # Summary
    print("\n" + "=" * 60)
    print("BATCH UPDATE SUMMARY")
    print("=" * 60)
    
    successful = 0
    failed = 0
    total_apartments = 0
    
    for apt_name, result in results.items():
        if result['status'] == 'success':
            successful += 1
            total_apartments += result['count']
            print(f"✅ {apt_name}: {result['count']} apartments")
        else:
            failed += 1
            error_msg = result.get('error', 'Unknown error')
            print(f"❌ {apt_name}: Failed - {error_msg}")
    
    print(f"\nTotal: {len(results)} apartments processed")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"Total apartment entries found: {total_apartments}")
    
    # Save batch results
    batch_results_file = "result/batch_daily_update_results.json"
    os.makedirs("result", exist_ok=True)
    
    with open(batch_results_file, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\nBatch results saved to: {batch_results_file}")
    
    return results

def main():
    # Example configuration - modify this with your actual apartments
    apartments_config = [
        {
            "name": "vista_99",
            "floor_plan_url": "https://www.equityapartments.com/san-francisco-bay/north-san-jose/vista-99-apartments/floor-plans"
        },
        {
            "name": "avalon_cahill_park",
            "floor_plan_url": "https://www.avaloncommunities.com/california/san-jose-apartments/avalon-at-cahill-park/floor-plans"
        },
        {
            "name": "miro_san_jose",
            "floor_plan_url": "https://www.miroapartments.com/floor-plans"
        }
        # Add more apartments as needed
    ]
    
    # Check if config file exists
    config_file = "apartments_config.json"
    if os.path.exists(config_file):
        try:
            with open(config_file, "r") as f:
                apartments_config = json.load(f)
            print(f"Loaded configuration from {config_file}")
        except Exception as e:
            print(f"Error loading config file: {e}")
            print("Using default configuration")
    else:
        print(f"No config file found. Create {config_file} with your apartment list.")
        print("Using example configuration")
    
    # Run batch updates
    run_batch_daily_updates(apartments_config)

if __name__ == "__main__":
    main()
