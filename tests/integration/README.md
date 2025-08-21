# AptTrack Integration Testing & Scraping

This directory contains the integration testing and apartment scraping functionality for AptTrack.

## 📁 Directory Structure

```
tests/integration/
├── modular_scraper/           # 🆕 Modern modular scraping system
│   ├── scraper_steps.py      # Reusable step functions
│   ├── integrated_apartment_scraper.py  # Full pipeline (steps 1-6)
│   ├── daily_apartment_scraper.py       # Daily updates (steps 3 & 6)
│   ├── run_daily_updates.py  # Batch daily updates
│   ├── apartments_config.json # Configuration for batch updates
│   ├── README_MODULAR_SCRAPER.md # Detailed modular system docs
│   ├── data/                 # Intermediate data files
│   ├── result/               # Final extraction results
│   └── extractor_script/     # Generated extraction scripts
├── batch_processing/          # 🔄 Batch processing for multiple apartments
│   ├── batch_scraper.py      # Process all apartments from JSON
│   ├── json_scraper.py       # Flexible JSON-based scraper
│   ├── test_batch_scraping.py # Test batch functionality
│   └── BATCH_SCRAPING_README.md # Batch processing documentation
├── legacy_scraper/            # 📜 Legacy/obsolete scraping code
│   ├── run_scraper.py        # Old command-line interface
│   ├── test_integration.py   # Old integration tests
│   ├── vista99_crawl.py      # Vista 99 specific scraper
│   ├── crawl.py              # Basic crawling utilities
│   ├── floor_finder.py       # Floor plan finding logic
│   ├── llm_floor_finder.py   # LLM-based floor finder
│   ├── check_db_schema.py    # Database schema checker
│   ├── run_migration.py      # Database migration runner
│   └── requirements.txt      # Legacy dependencies
└── README.md                 # This file
```

## 🚀 Quick Start

### For Daily Apartment Updates (Recommended)
```bash
cd modular_scraper
python daily_apartment_scraper.py vista_99 "https://..."
```

### For Batch Processing Multiple Apartments
```bash
cd batch_processing
python batch_scraper.py real_service_San_Jose_CA.json results
```

### For Full Pipeline (First Time Setup)
```bash
cd modular_scraper
python integrated_apartment_scraper.py vista_99 "https://..."
```

## 🎯 What Each Directory Does

### 1. **modular_scraper/** - 🆕 Modern System
- **Purpose**: Daily apartment data updates using pre-generated extractors
- **Best for**: Production use, daily operations
- **Features**: 
  - Reusable extractor scripts (run once, use daily)
  - No LLM costs for daily runs
  - Fast execution (steps 3 & 6 only)
  - Batch processing capability

### 2. **batch_processing/** - 🔄 Batch Operations
- **Purpose**: Process multiple apartments from JSON data
- **Best for**: Initial setup, bulk processing
- **Features**:
  - Process all apartments from Google Maps JSON
  - Generate extractors for multiple complexes
  - Comprehensive logging and error handling

### 3. **legacy_scraper/** - 📜 Old Code
- **Purpose**: Reference and historical code
- **Best for**: Understanding evolution, debugging
- **Features**: 
  - Original implementation
  - Various utility scripts
  - Database integration code

## 🔄 Workflow

### Initial Setup (Once per apartment)
1. Use `modular_scraper/integrated_apartment_scraper.py`
2. Generates extractor script for the apartment
3. Saves to `modular_scraper/extractor_script/`

### Daily Operations
1. Use `modular_scraper/daily_apartment_scraper.py`
2. Crawls latest data and runs existing extractor
3. Results saved to `modular_scraper/result/`

### Batch Processing
1. Use `batch_processing/batch_scraper.py`
2. Processes multiple apartments from JSON
3. Generates extractors for all complexes

## 📊 Current Status

- **✅ Modular System**: Fully functional, production-ready
- **✅ Batch Processing**: Functional for bulk operations
- **📜 Legacy Code**: Preserved for reference
- **📁 Data**: Organized by apartment complex
- **🔧 Extractors**: Pre-generated for 13+ apartment complexes

## 🛠️ Maintenance

### Adding New Apartments
1. Run full pipeline: `modular_scraper/integrated_apartment_scraper.py`
2. Add to config: `modular_scraper/apartments_config.json`

### Updating Existing Apartments
1. Daily updates: `modular_scraper/daily_apartment_scraper.py`
2. Batch updates: `modular_scraper/run_daily_updates.py`

### Troubleshooting
1. Check `modular_scraper/README_MODULAR_SCRAPER.md`
2. Verify extractor scripts exist
3. Check website structure changes

## 🔗 Related Documentation

- **Modular System**: `modular_scraper/README_MODULAR_SCRAPER.md`
- **Batch Processing**: `batch_processing/BATCH_SCRAPING_README.md`
- **Main Project**: `../../README.md`

## 📝 Notes

- The modular system is the **recommended approach** for daily use
- Legacy code is preserved for reference and debugging
- All data and results are organized by apartment complex
- Extractors are generated once and reused daily
