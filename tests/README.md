# AptTrack Tests & Integration

This directory contains comprehensive testing and integration functionality for the AptTrack project, organized into logical categories for easy navigation and maintenance.

## 🏗️ Test Structure Overview

```
tests/
├── 📖 README.md                    # This file - main navigation guide
├── 🧪 unit/                        # Unit tests for individual components
│   ├── test_google_maps.py        # Google Maps API integration tests
│   ├── test_google_maps_simple.py # Simplified Google Maps tests
│   └── run_google_maps.py         # Standalone Google Maps service runner
├── 🔗 integration/                 # Integration testing & apartment scraping
│   ├── 📖 README.md               # Integration system guide
│   ├── 🚀 run.py                  # Interactive navigation script
│   ├── 🆕 modular_scraper/       # Modern scraping system (RECOMMENDED)
│   ├── 🔄 batch_processing/       # Batch apartment processing
│   ├── 📜 legacy_scraper/         # Legacy scraping tools
│   └── 📋 requirements.txt        # Integration dependencies
├── 🤖 llm/                        # LLM-powered testing & code generation
│   ├── llm_coder.py               # AI-powered code generation tests
│   ├── llm_code_script_final.py   # Final apartment parsing scripts
│   ├── dump_func.py                # Function dumping utilities
│   └── template.txt                # LLM code generation templates
├── conftest.py                     # Test configuration & path setup
├── run_tests.py                    # Main test runner
└── requirements-test.txt            # Test dependencies
```

## 🚀 Quick Start

### Interactive Integration Testing
```bash
cd tests/integration
python run.py  # Interactive menu for scraping operations
```

### Run All Tests
```bash
cd tests
python run_tests.py
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

## 📁 Detailed Directory Guide

### 1. **unit/** - 🧪 Component Testing
- **Purpose**: Test individual components and services in isolation
- **Best for**: Development, debugging, CI/CD pipelines
- **Key Files**:
  - `test_google_maps.py` - Google Maps API integration tests
  - `test_google_maps_simple.py` - Simplified API tests
  - `run_google_maps.py` - Standalone service testing

### 2. **integration/** - 🔗 System Integration & Scraping
- **Purpose**: End-to-end testing and apartment data scraping
- **Best for**: Production scraping, daily operations, system validation
- **Key Systems**:
  - **🆕 Modular Scraper**: Modern, production-ready scraping system
  - **🔄 Batch Processing**: Bulk apartment processing from JSON data
  - **📜 Legacy Tools**: Reference and debugging utilities

### 3. **llm/** - 🤖 AI-Powered Testing
- **Purpose**: LLM-based code generation and testing
- **Best for**: AI-powered scraping, code generation, advanced parsing
- **Key Files**:
  - `llm_coder.py` - AI code generation tests
  - `llm_code_script_final.py` - Generated parsing scripts
  - `template.txt` - LLM prompt templates

## 🔧 Setup & Dependencies

### Install Test Dependencies
```bash
# Main test dependencies
pip install -r tests/requirements-test.txt

# Integration dependencies
pip install -r tests/integration/requirements.txt

# Legacy dependencies (if needed)
pip install -r tests/integration/legacy_scraper/requirements.txt

# Install Playwright browsers for web scraping
playwright install
```

### Required Environment Variables
```bash
# OpenAI API key (for LLM tests and scraping)
export OPENAI_API_KEY="your_api_key_here"

# Google Maps API key (for unit tests)
export GOOGLE_MAPS_API_KEY="your_google_maps_key_here"
```

## 🧪 Running Tests

### Unit Tests
```bash
# Run all unit tests
pytest tests/unit/ -v

# Run specific test file
pytest tests/unit/test_google_maps.py -v

# Run with coverage
pytest tests/unit/test_google_maps.py --cov=backend.app.services.google_maps

# Run standalone service
python tests/unit/run_google_maps.py
```

### Integration Tests
```bash
# Interactive scraping menu
cd tests/integration
python run.py

# Daily apartment updates (recommended)
cd tests/integration/modular_scraper
python daily_apartment_scraper.py vista_99 "https://..."

# Batch processing
cd tests/integration/batch_processing
python batch_scraper.py real_service_San_Jose_CA.json results

# Full pipeline (first time setup)
cd tests/integration/modular_scraper
python integrated_apartment_scraper.py vista_99 "https://..."
```

### LLM Tests
```bash
# Run LLM-powered tests
pytest tests/llm/ -v

# Test code generation
python tests/llm/llm_coder.py
```

## 📊 Current Status

- **✅ Unit Tests**: Google Maps API integration testing
- **✅ Integration Tests**: Modern modular scraping system
- **✅ LLM Tests**: AI-powered code generation
- **✅ Batch Processing**: Multi-apartment processing capability
- **✅ Legacy Support**: Historical tools preserved for reference

## 🎯 Use Case Scenarios

### For Developers
1. **Unit Testing**: Use `tests/unit/` for component testing
2. **Integration Testing**: Use `tests/integration/` for system validation
3. **LLM Testing**: Use `tests/llm/` for AI-powered features

### For Data Scientists
1. **Daily Updates**: Use modular scraper for apartment data
2. **Batch Processing**: Use batch tools for multiple complexes
3. **Data Validation**: Use integration tests for data quality

### For Operations
1. **Production Scraping**: Use modular scraper daily
2. **Monitoring**: Use test runners for system health
3. **Troubleshooting**: Use legacy tools for debugging

## 🛠️ Maintenance & Development

### Adding New Tests
1. **Unit Tests**: Add to `tests/unit/` directory
2. **Integration Tests**: Add to appropriate `tests/integration/` subdirectory
3. **LLM Tests**: Add to `tests/llm/` directory

### Updating Test Dependencies
1. **Main Tests**: Update `requirements-test.txt`
2. **Integration**: Update `tests/integration/requirements.txt`
3. **Legacy**: Update `tests/integration/legacy_scraper/requirements.txt`

### Test Configuration
- **conftest.py**: Configures Python paths for imports
- **Environment Variables**: Set API keys and configuration
- **Test Data**: Preserved in appropriate directories

## 📚 Documentation

- **This Guide**: `tests/README.md` (main navigation)
- **Integration System**: `tests/integration/README.md`
- **Modular Scraper**: `tests/integration/modular_scraper/README_MODULAR_SCRAPER.md`
- **Batch Processing**: `tests/integration/batch_processing/BATCH_SCRAPING_README.md`
- **Organization Summary**: `tests/integration/ORGANIZATION_SUMMARY.md`

## 🚨 Important Notes

- **Integration tests require Playwright browsers** - install with `playwright install`
- **LLM tests require OpenAI API access** - set `OPENAI_API_KEY`
- **Unit tests require Google Maps API** - set `GOOGLE_MAPS_API_KEY`
- **Test output files are preserved** for debugging and analysis
- **Legacy tools are preserved** but not recommended for production

## 🆘 Getting Help

### Quick Navigation
```bash
cd tests/integration
python run.py  # Interactive help for scraping operations
```

### Common Issues
1. **Import errors** → Check `conftest.py` and Python paths
2. **API key errors** → Set required environment variables
3. **Browser errors** → Install Playwright browsers
4. **Scraping failures** → Check website structure changes

### Support Resources
- Check console output for detailed error messages
- Review specific README files in each subdirectory
- Verify environment variables and dependencies
- Test with simple examples before complex operations

---

**🎯 Recommendation**: Start with unit tests for development, use integration tests for system validation, and leverage the modular scraping system for production apartment data collection.
