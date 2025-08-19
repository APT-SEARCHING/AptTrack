#!/usr/bin/env python3
"""
Environment setup script for AptTrack
"""
import os
from pathlib import Path
from dotenv import load_dotenv

def setup_environment():
    """Set up the environment for AptTrack"""
    print("🚀 Setting up AptTrack environment...")
    
    # Check if .env file exists
    env_file = Path(".env")
    if env_file.exists():
        print("✅ .env file already exists")
        # Load the .env file
        load_dotenv(env_file)
        return
    
    # Check if .env.example exists
    example_file = Path(".env.example")
    if not example_file.exists():
        print("❌ .env.example file not found")
        return
    
    # Copy .env.example to .env
    try:
        with open(example_file, 'r') as src, open(env_file, 'w') as dst:
            dst.write(src.read())
        print("✅ Created .env file from .env.example")
        print("📝 Please edit .env file with your actual values")
        print("🔑 At minimum, set your GOOGLE_MAPS_API_KEY")
        # Load the newly created .env file
        load_dotenv(env_file)
    except Exception as e:
        print(f"❌ Error creating .env file: {e}")

def check_environment():
    """Check if required environment variables are set"""
    print("\n🔍 Checking environment variables...")
    
    required_vars = [
        "GOOGLE_MAPS_API_KEY",
        "DATABASE_URL",
        "BACKEND_PORT",
        "FRONTEND_PORT"
    ]
    
    missing_vars = []
    for var in required_vars:
        value = os.getenv(var)
        if value:
            print(f"✅ {var}: {value[:20]}{'...' if len(value) > 20 else ''}")
        else:
            print(f"❌ {var}: Not set")
            missing_vars.append(var)
    
    if missing_vars:
        print(f"\n⚠️  Missing environment variables: {', '.join(missing_vars)}")
        print("Please set these in your .env file")
    else:
        print("\n🎉 All required environment variables are set!")

if __name__ == "__main__":
    setup_environment()
    check_environment()
