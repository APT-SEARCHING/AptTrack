#!/usr/bin/env python3
"""
Setup script for AptTrack tests
"""
import subprocess
import sys
from pathlib import Path

def install_test_dependencies():
    """Install test dependencies"""
    print("Installing test dependencies...")
    requirements_file = Path(__file__).parent / "requirements-test.txt"
    
    result = subprocess.run([
        sys.executable, "-m", "pip", "install", "-r", str(requirements_file)
    ])
    
    if result.returncode == 0:
        print("Test dependencies installed successfully!")
    else:
        print("Failed to install test dependencies!")
        return False
    
    return True

def install_playwright_browsers():
    """Install Playwright browsers for integration tests"""
    print("Installing Playwright browsers...")
    
    result = subprocess.run([
        sys.executable, "-m", "playwright", "install"
    ])
    
    if result.returncode == 0:
        print("Playwright browsers installed successfully!")
    else:
        print("Failed to install Playwright browsers!")
        return False
    
    return True

def main():
    """Main setup function"""
    print("Setting up AptTrack test environment...")
    
    # Install test dependencies
    if not install_test_dependencies():
        sys.exit(1)
    
    # Install Playwright browsers
    if not install_playwright_browsers():
        sys.exit(1)
    
    print("\nTest environment setup complete!")
    print("\nYou can now run tests using:")
    print("  python tests/run_tests.py")

if __name__ == "__main__":
    main()
