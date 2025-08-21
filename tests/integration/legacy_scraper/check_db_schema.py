#!/usr/bin/env python3
"""
Script to check the actual database schema
"""
import psycopg2
import os
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from the top-level .env file
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

def check_schema():
    """Check the actual database schema"""
    
    try:
        conn = psycopg2.connect(
            host=os.getenv("DATABASE_HOST", "localhost"),
            port=os.getenv("DATABASE_PORT", "5432"),
            database=os.getenv("DATABASE_NAME", "rental_tracker"),
            user=os.getenv("DATABASE_USER", "user"),
            password=os.getenv("DATABASE_PASSWORD", "password")
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        print("Connected to database successfully!")
        
        # Check what tables exist
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        
        tables = [row[0] for row in cursor.fetchall()]
        print(f"Tables found: {tables}")
        
        # Check apartments table structure
        if 'apartments' in tables:
            print("\n=== APARTMENTS TABLE SCHEMA ===")
            cursor.execute("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns 
                WHERE table_name = 'apartments' 
                ORDER BY ordinal_position
            """)
            
            for row in cursor.fetchall():
                print(f"  {row[0]}: {row[1]} (nullable: {row[2]}, default: {row[3]})")
        
        # Check plans table structure
        if 'plans' in tables:
            print("\n=== PLANS TABLE SCHEMA ===")
            cursor.execute("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns 
                WHERE table_name = 'plans' 
                ORDER BY ordinal_position
            """)
            
            for row in cursor.fetchall():
                print(f"  {row[0]}: {row[1]} (nullable: {row[2]}, default: {row[3]})")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Error checking schema: {e}")

if __name__ == "__main__":
    check_schema()
