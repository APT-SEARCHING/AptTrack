#!/usr/bin/env python3
"""
Main test runner for AptTrack
"""
import subprocess
import sys
from pathlib import Path

def run_tests():
    """Run all tests using pytest"""
    test_dir = Path(__file__).parent
    
    # Run unit tests
    print("Running unit tests...")
    result = subprocess.run([
        sys.executable, "-m", "pytest", 
        str(test_dir / "unit"), 
        "-v"
    ], cwd=test_dir.parent)
    
    if result.returncode != 0:
        print("Unit tests failed!")
        return False
    
    # Run integration tests
    print("\nRunning integration tests...")
    result = subprocess.run([
        sys.executable, "-m", "pytest", 
        str(test_dir / "integration"), 
        "-v"
    ], cwd=test_dir.parent)
    
    if result.returncode != 0:
        print("Integration tests failed!")
        return False
    
    print("\nAll tests passed!")
    return True

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
