#!/usr/bin/env python3
"""
Script to run the Google Maps enhancement migration directly
"""
import psycopg2
import os
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from the top-level .env file
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

def run_migration():
    """Run the migration to add Google Maps API fields"""
    
    # Connect to the database
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
        
        # Check if columns already exist
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'apartments' 
            AND column_name IN ('phone', 'rating', 'user_rating_count', 'business_name')
        """)
        
        existing_columns = [row[0] for row in cursor.fetchall()]
        print(f"Existing columns: {existing_columns}")
        
        # Add missing columns
        columns_to_add = [
            ('phone', 'VARCHAR', 'Phone number for the property'),
            ('rating', 'FLOAT', 'Google rating (0-5)'),
            ('user_rating_count', 'INTEGER', 'Number of user ratings'),
            ('business_name', 'VARCHAR', 'Official business name of the property')
        ]
        
        for column_name, column_type, comment in columns_to_add:
            if column_name not in existing_columns:
                print(f"Adding column: {column_name}")
                cursor.execute(f"""
                    ALTER TABLE apartments 
                    ADD COLUMN {column_name} {column_type} NULL
                """)
                
                # Add comment
                cursor.execute(f"""
                    COMMENT ON COLUMN apartments.{column_name} IS '{comment}'
                """)
                
                print(f"✓ Added column {column_name}")
            else:
                print(f"Column {column_name} already exists, skipping...")
        
        # Verify the changes
        cursor.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns 
            WHERE table_name = 'apartments' 
            AND column_name IN ('phone', 'rating', 'user_rating_count', 'business_name')
            ORDER BY column_name
        """)
        
        print("\nFinal column status:")
        for row in cursor.fetchall():
            print(f"  {row[0]}: {row[1]} (nullable: {row[2]})")
        
        cursor.close()
        conn.close()
        print("\nMigration completed successfully!")
        
    except Exception as e:
        print(f"Error running migration: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_migration()
