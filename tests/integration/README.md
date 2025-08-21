# AptTrack Integration Testing & Scraping

This directory contains the integration testing and apartment scraping functionality for AptTrack, organized into a clear, maintainable structure.

## 🚀 Quick Start

### Interactive Navigation
```bash
cd tests/integration
python run.py  # Interactive menu to guide you
```

### Daily Apartment Updates (Recommended)
```bash
cd modular_scraper
python daily_apartment_scraper.py vista_99 "https://www.equityapartments.com/san-francisco-bay/north-san-jose/vista-99-apartments/floor-plans"
```

### Batch Process Multiple Apartments
```bash
cd batch_processing
python batch_scraper.py real_service_San_Jose_CA.json results
```

### Full Pipeline (First Time Setup)
```bash
cd modular_scraper
python integrated_apartment_scraper.py vista_99 "https://www.equityapartments.com/san-francisco-bay/north-san-jose/vista-99-apartments"
```

## 📁 Directory Structure

```
tests/integration/
├── 📖 README.md                    # This file - main navigation guide
├── 🚀 run.py                       # Interactive navigation script
├── 📋 requirements.txt             # Main dependencies
├── 🆕 modular_scraper/            # Modern system (RECOMMENDED)
│   ├── scraper_steps.py           # Reusable step functions
│   ├── integrated_apartment_scraper.py  # Full pipeline (steps 1-6)
│   ├── daily_apartment_scraper.py      # Daily updates (steps 3 & 6)
│   ├── run_daily_updates.py            # Batch daily updates
│   ├── apartments_config.json          # Configuration for batch updates
│   ├── README_MODULAR_SCRAPER.md      # Detailed modular system docs
│   ├── data/                           # Intermediate data files
│   ├── result/                          # Final extraction results
│   └── extractor_script/               # Generated extraction scripts
├── 🔄 batch_processing/           # Batch processing for multiple apartments
│   ├── batch_scraper.py          # Process all apartments from JSON
│   ├── json_scraper.py           # Flexible JSON-based scraper
│   ├── test_batch_scraping.py    # Test batch functionality
│   └── BATCH_SCRAPING_README.md  # Batch processing documentation
└── 📜 legacy_scraper/            # Legacy/obsolete scraping code
    ├── run_scraper.py            # Old command-line interface
    ├── test_integration.py       # Old integration tests
    ├── vista99_crawl.py          # Vista 99 specific scraper
    ├── crawl.py                  # Basic crawling utilities
    ├── floor_finder.py           # Floor plan finding logic
    ├── llm_floor_finder.py       # LLM-based floor finder
    ├── check_db_schema.py        # Database schema checker
    ├── run_migration.py          # Database migration runner
    └── requirements.txt          # Legacy dependencies
```

## 🎯 What Each Directory Does

### 1. **modular_scraper/** - 🆕 Modern System (RECOMMENDED)
- **Purpose**: Daily apartment data updates using pre-generated extractors
- **Best for**: Production use, daily operations
- **Key Features**: 
  - Reusable extractor scripts (generate once, use daily)
  - No LLM costs for daily runs
  - Fast execution (steps 3 & 6 only)
  - Batch processing capability
  - Production-ready and maintained

### 2. **batch_processing/** - 🔄 Batch Operations
- **Purpose**: Process multiple apartments from JSON data
- **Best for**: Initial setup, bulk processing
- **Key Features**:
  - Process all apartments from Google Maps JSON
  - Generate extractors for multiple complexes
  - Comprehensive logging and error handling
  - Configurable batch sizes

### 3. **legacy_scraper/** - 📜 Old Code (Reference Only)
- **Purpose**: Reference and historical code
- **Best for**: Understanding evolution, debugging
- **Note**: Not recommended for daily use

## 🔄 Workflow Guide

### Initial Setup (Once per apartment)
1. **Navigate**: `cd modular_scraper`
2. **Run full pipeline**: `python integrated_apartment_scraper.py <name> <url>`
3. **Result**: Generates extractor script for the apartment
4. **Location**: Saved to `extractor_script/` directory

### Daily Operations
1. **Navigate**: `cd modular_scraper`
2. **Single update**: `python daily_apartment_scraper.py <name> <url>`
3. **Batch updates**: `python run_daily_updates.py`
4. **Result**: Latest apartment data in `result/` directory

### Batch Processing
1. **Navigate**: `cd batch_processing`
2. **Process all**: `python batch_scraper.py <json_file> <output_dir>`
3. **Process limited**: `python json_scraper.py <json_file> <output_dir> [max_count]`
4. **Result**: Extractors generated for multiple complexes

## 📊 Current Status

- **✅ Modular System**: Fully functional, production-ready
- **✅ Batch Processing**: Functional for bulk operations
- **📜 Legacy Code**: Preserved for reference
- **📁 Data**: Organized by apartment complex
- **🔧 Extractors**: Pre-generated for 13+ apartment complexes

## 🛠️ Setup & Dependencies

### Install Dependencies
```bash
# Main dependencies
pip install -r requirements.txt

# Legacy dependencies (if needed)
pip install -r legacy_scraper/requirements.txt

# Install Playwright browsers
playwright install
```

### Required Environment Variables
```bash
# OpenAI API key (for full pipeline only)
export OPENAI_API_KEY="your_api_key_here"
```

## 📝 Examples

### Example 1: Daily Update for Vista 99
```bash
cd modular_scraper
python daily_apartment_scraper.py vista_99 "https://www.equityapartments.com/san-francisco-bay/north-san-jose/vista-99-apartments/floor-plans"
```

### Example 2: Generate Extractor for New Apartment
```bash
cd modular_scraper
python integrated_apartment_scraper.py avalon_new "https://www.avaloncommunities.com/california/san-jose-apartments/avalon-new"
```

### Example 3: Batch Process All Apartments
```bash
cd batch_processing
python batch_scraper.py real_service_San_Jose_CA.json batch_results
```

### Example 4: Interactive Navigation
```bash
cd tests/integration
python run.py  # Choose from menu
```

## 🔧 Maintenance

### Adding New Apartments
1. **Run full pipeline**: `modular_scraper/integrated_apartment_scraper.py`
2. **Add to config**: `modular_scraper/apartments_config.json`
3. **Test daily update**: `modular_scraper/daily_apartment_scraper.py`

### Updating Existing Apartments
1. **Daily updates**: `modular_scraper/daily_apartment_scraper.py`
2. **Batch updates**: `modular_scraper/run_daily_updates.py`
3. **Regenerate if needed**: `modular_scraper/integrated_apartment_scraper.py`

### Troubleshooting
1. **Check extractors exist**: `ls modular_scraper/extractor_script/`
2. **Verify file paths**: Use debug functions in scripts
3. **Check website changes**: May need to regenerate extractors
4. **Review logs**: Check console output for errors

## 📚 Documentation

- **This Guide**: `README.md` (main navigation)
- **Modular System**: `modular_scraper/README_MODULAR_SCRAPER.md`
- **Batch Processing**: `batch_processing/BATCH_SCRAPING_README.md`
- **Organization Summary**: `ORGANIZATION_SUMMARY.md`

## 🚨 Important Notes

- **Daily updates require pre-generated extractors** - run full pipeline first
- **Full pipeline uses OpenAI API** - costs apply only during setup
- **Daily updates are fast and free** - no API costs
- **Legacy code is preserved** - but not recommended for production
- **Data is organized by apartment** - each complex has its own files

## 🆘 Getting Help

### Quick Help
```bash
python run.py  # Interactive help menu
```

### Common Issues
1. **"Extractor not found"** → Run full pipeline first
2. **"API key error"** → Set OPENAI_API_KEY environment variable
3. **"File not found"** → Check directory structure and file paths
4. **"Extraction failed"** → Website structure may have changed

### Support Resources
- Check console output for detailed error messages
- Review the specific README files in each subdirectory
- Verify file paths and directory structure
- Test with a single apartment before batch processing

---

**🎯 Recommendation**: Start with the modular system for daily operations, use batch processing for initial setup, and refer to legacy code only when debugging or understanding the system evolution.
