# Batch Scraping Scripts for AptTrack

This directory contains scripts to automatically scrape multiple apartments from the Google Maps JSON data.

## Files Overview

### 1. `batch_scraper.py` - Full Batch Processor
- **Purpose**: Process ALL apartments from the JSON file
- **Features**: Comprehensive processing with detailed logging
- **Best for**: Production runs when you want to scrape everything

### 2. `json_scraper.py` - Flexible Scraper Module
- **Purpose**: Modular scraper that can be used as a library or command-line tool
- **Features**: Configurable, can limit number of apartments, reusable
- **Best for**: Development, testing, or when you want control over the process

### 3. `test_batch_scraping.py` - Testing Script
- **Purpose**: Test the batch scraping functionality
- **Features**: Validates JSON loading, single scraping, and batch processing
- **Best for**: Verifying everything works before running on all data

## Quick Start

### Option 1: Scrape All Apartments (Recommended for first run)
```bash
cd tests/integration
python batch_scraper.py real_service_San_Jose_CA.json batch_results
```

### Option 2: Scrape Limited Apartments (Good for testing)
```bash
cd tests/integration
python json_scraper.py real_service_San_Jose_CA.json results 10
```

### Option 3: Test the System First
```bash
cd tests/integration
python test_batch_scraping.py
```

## Usage Examples

### Command Line Usage

#### Scrape All Apartments
```bash
python batch_scraper.py <json_file> [output_directory]
```
Example:
```bash
python batch_scraper.py real_service_San_Jose_CA.json my_results
```

#### Scrape Limited Apartments
```bash
python json_scraper.py <json_file> [output_directory] [max_apartments]
```
Examples:
```bash
# Scrape first 5 apartments
python json_scraper.py real_service_San_Jose_CA.json results 5

# Scrape first 20 apartments
python json_scraper.py real_service_San_Jose_CA.json results 20

# Scrape all apartments (no limit)
python json_scraper.py real_service_San_Jose_CA.json results
```

### Programmatic Usage

```python
from json_scraper import JsonApartmentScraper

# Initialize scraper
api_key = 'your_openai_api_key_here'
scraper = JsonApartmentScraper(api_key)

# Load apartments from JSON
apartments = scraper.load_apartments_from_json('real_service_San_Jose_CA.json')

# Scrape single apartment
result = scraper.scrape_apartment(apartments[0])

# Scrape all apartments with limit
results = scraper.scrape_all_apartments('real_service_San_Jose_CA.json', 'results', max_apartments=10)
```

## Output Structure

### Individual Results
Each apartment gets its own JSON file:
```
results/
├── avalon_on_the_alameda_results.json
├── avalon_morrison_park_results.json
├── eaves_san_jose_results.json
└── ...
```

### Summary Files
- `batch_summary.json` - Overall summary of the batch run
- Individual result files contain:
  - Apartment metadata (name, URL, city, rating)
  - Scraped apartment data
  - Processing information

## Configuration

### API Key
The scripts use the OpenAI API key from:
1. Environment variable `OPENAI_API_KEY`
2. Hardcoded fallback (for testing)

### Output Directories
- Default: `results/` or `batch_results/`
- Customizable via command line arguments
- Automatically created if they don't exist

## Error Handling

The scripts handle various error scenarios:
- **Invalid URLs**: Skipped automatically
- **Scraping failures**: Logged and tracked
- **API errors**: Retried with error reporting
- **File I/O errors**: Graceful fallbacks

## Performance Considerations

### Rate Limiting
- The scripts process apartments sequentially
- No built-in rate limiting (respects API limits)
- Consider adding delays between requests if needed

### Memory Usage
- Processes one apartment at a time
- Results saved to disk immediately
- Minimal memory footprint

### Time Estimates
- **Small batch (10 apartments)**: ~10-30 minutes
- **Medium batch (50 apartments)**: ~1-3 hours
- **Full batch (100+ apartments)**: ~3-8 hours

## Troubleshooting

### Common Issues

1. **JSON file not found**
   - Ensure the JSON file is in the correct directory
   - Check file permissions

2. **No apartments loaded**
   - Verify JSON structure matches expected format
   - Check that apartments have valid `source_url` fields

3. **Scraping failures**
   - Check internet connectivity
   - Verify OpenAI API key is valid
   - Some websites may block automated access

4. **Memory errors**
   - Process smaller batches
   - Ensure sufficient disk space for results

### Debug Mode
For detailed debugging, modify the scripts to add more logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Best Practices

1. **Start Small**: Test with 5-10 apartments first
2. **Monitor Progress**: Watch the console output for issues
3. **Backup Results**: Save results to different directories for different runs
4. **Check Logs**: Review the summary files for failed apartments
5. **Resume Capability**: Failed apartments can be re-run individually

## Integration with Existing Workflow

These scripts integrate seamlessly with your existing `run_scraper.py`:
- Use the same `IntegratedApartmentScraper` class
- Compatible output formats
- Can be run alongside manual scraping

## Support

If you encounter issues:
1. Check the console output for error messages
2. Verify the JSON file structure
3. Test with a single apartment first
4. Check the test script output for validation
