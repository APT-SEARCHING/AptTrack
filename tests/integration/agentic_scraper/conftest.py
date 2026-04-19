import sys
from pathlib import Path

# Allow test file to import browser_tools, agent, etc. from this directory
sys.path.insert(0, str(Path(__file__).parent))
