# AptTrack Tests

This directory contains all test code for the AptTrack project, organized into logical categories.

## Test Structure

### Unit Tests (`tests/unit/`)
- **`test_google_maps.py`** - Tests for Google Maps API integration
- **`test_google_maps_simple.py`** - Simplified Google Maps API tests

### Integration Tests (`tests/integration/`)
- **`crawl.py`** - Web crawling tests for apartment websites
- **`vista99_crawl.py`** - Specific crawling tests for Vista 99 apartments
- **`floor_finder.py`** - Tests for finding floor plan URLs
- **`llm_floor_finder.py`** - AI-powered floor plan URL selection tests
- **`candidates.txt`** - Sample candidate URLs for testing
- **`selected_url.txt`** - Selected URL output for testing

### LLM Tests (`tests/llm/`)
- **`llm_coder.py`** - Tests for AI-powered code generation
- **`llm_code_script_final.py`** - Final apartment parsing script tests
- **`llm_code_script_final_vista_99.py`** - Vista 99 specific parsing tests
- **`dump_func.py`** - Function dumping utility for testing
- **`template.txt`** - Template for LLM-generated code
- **`parser_output_byllm.txt`** - Sample parser output
- **`parser_output_byllm_vista_99.txt`** - Vista 99 parser output
- **`llm_code_script.txt`** - LLM-generated code script
- **`llm_code_script_vista_99.txt`** - Vista 99 specific script

## Running Tests

### Install Test Dependencies
```bash
pip install -r tests/requirements-test.txt
```

### Run All Tests
```bash
python tests/run_tests.py
```

### Run Specific Test Categories
```bash
# Unit tests only
pytest tests/unit/ -v

# Integration tests only
pytest tests/integration/ -v

# LLM tests only
pytest tests/llm/ -v
```

### Run Individual Test Files
```bash
# Run specific test file
pytest tests/unit/test_google_maps.py -v

# Run with coverage
pytest tests/unit/test_google_maps.py --cov=backend.app.services.google_maps
```

## Test Configuration

The `conftest.py` file configures the Python path to include the backend and app directories, allowing tests to import modules from those locations.

## Notes

- Some tests require API keys (Google Maps, OpenAI) - these should be configured via environment variables
- Integration tests use Playwright for web scraping - ensure browsers are installed
- LLM tests require OpenAI API access
- Test output files are preserved for debugging and analysis
