# Modular Apartment Scraper System

This system provides a modular approach to apartment scraping with two main use cases:

1. **Full Pipeline** (`integrated_apartment_scraper.py`) - Run once per apartment to generate the extractor script
2. **Daily Updates** (`daily_apartment_scraper.py`) - Run daily to get latest apartment data using existing extractors

## File Structure

```
tests/integration/
├── scraper_steps.py                    # All individual step functions
├── integrated_apartment_scraper.py     # Full pipeline (steps 1-6)
├── daily_apartment_scraper.py         # Daily updates (steps 3 & 6 only)
├── run_daily_updates.py               # Batch daily updates for multiple apartments
├── apartments_config.json             # Configuration file for batch updates
└── README_MODULAR_SCRAPER.md          # This file
```

## Usage

### 1. Initial Setup (Full Pipeline)

Run this **once per apartment** to generate the extractor script:

```bash
cd tests/integration
python integrated_apartment_scraper.py <apartment_name> <homepage_url>
```

**Example:**
```bash
python integrated_apartment_scraper.py vista_99 "https://www.equityapartments.com/san-francisco-bay/north-san-jose/vista-99-apartments"
```

**What this does:**
- Step 1: Finds floor plan candidate URLs from homepage
- Step 2: Uses LLM to select the best floor plan page
- Step 3: Crawls the floor plan page
- Step 4: Uses LLM to generate extraction code
- Step 5: Creates the final extractor script
- Step 6: Tests the extraction

**Output files created:**
- `data/output_<apartment_name>.txt` - Raw crawled content
- `extractor_script/llm_code_script_final_<apartment_name>.py` - The extractor script
- `result/parser_output_<apartment_name>.txt` - Initial extraction results

### 2. Daily Updates

Run this **daily** to get the latest apartment data:

```bash
cd tests/integration
python daily_apartment_scraper.py <apartment_name> <floor_plan_url>
```

**Example:**
```bash
python daily_apartment_scraper.py vista_99 "https://www.equityapartments.com/san-francisco-bay/north-san-jose/vista-99-apartments/floor-plans"
```

**What this does:**
- Step 3: Crawls the floor plan page for latest data
- Step 6: Executes the existing extractor script

**Requirements:**
- Must have run the full pipeline first to generate the extractor script
- The extractor script must exist in `extractor_script/llm_code_script_final_<apartment_name>.py`

## Workflow

### First Time Setup
1. Run `integrated_apartment_scraper.py` for each apartment
2. This generates the extractor script for each apartment
3. Save the floor plan URLs for daily use

### Daily Operations
1. Run `daily_apartment_scraper.py` for each apartment, OR
2. Run `run_daily_updates.py` to update all apartments at once
3. Get latest apartment availability and pricing data
4. Results are saved to `result/parser_output_<apartment_name>.txt`

## Benefits of Modular Approach

1. **Efficiency**: Don't need to regenerate extractors daily
2. **Speed**: Daily updates only crawl and extract (no LLM calls)
3. **Cost**: No OpenAI API costs for daily runs
4. **Reliability**: Once an extractor works, it continues to work
5. **Maintenance**: Easy to update individual steps without affecting others

## Troubleshooting

### If Daily Updates Fail

1. **Check if extractor exists:**
   ```bash
   ls extractor_script/llm_code_script_final_<apartment_name>.py
   ```

2. **Regenerate extractor if needed:**
   ```bash
   python integrated_apartment_scraper.py <apartment_name> <homepage_url>
   ```

3. **Check website structure changes:**
   - If the website layout changed significantly, regenerate the extractor
   - The LLM-generated code may need updates for new layouts

### Common Issues

- **File not found errors**: Check if all directories exist
- **Extraction failures**: Verify the website structure hasn't changed
- **API errors**: Check OpenAI API key and quota

## File Dependencies

- `scraper_steps.py` - Contains all step functions
- `integrated_apartment_scraper.py` - Imports from `scraper_steps.py`
- `daily_apartment_scraper.py` - Imports from `scraper_steps.py`

## Configuration

- **OpenAI API Key**: Set in `integrated_apartment_scraper.py` (only needed for full pipeline)
- **Directories**: Automatically created as needed
- **File naming**: Uses apartment name for all file paths

## Example Daily Workflow

### Option 1: Individual Updates
```bash
# Morning routine - get latest data for each apartment
python daily_apartment_scraper.py vista_99 "https://..."
python daily_apartment_scraper.py avalon_cahill "https://..."
python daily_apartment_scraper.py miro_san_jose "https://..."

# Check results
ls -la result/parser_output_*.txt
```

### Option 2: Batch Updates (Recommended)
```bash
# Update all apartments at once
python run_daily_updates.py

# Check results
ls -la result/parser_output_*.txt
cat result/batch_daily_update_results.json
```
