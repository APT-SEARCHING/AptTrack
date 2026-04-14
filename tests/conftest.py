"""
Pytest configuration for AptTrack tests
"""
import sys
import os
from pathlib import Path

import pytest

# Add the backend directory to the Python path for imports
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

# Add the app directory to the Python path for imports
app_path = Path(__file__).parent.parent / "app"
sys.path.insert(0, str(app_path))


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: marks tests that require a live internet connection and API keys",
    )
