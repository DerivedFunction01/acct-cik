#!/usr/bin/env python3
"""
Create a test database with 200 randomly sampled URLs from the source database.
This allows for testing the full pipeline on a small subset before running on 265K+ URLs.
"""

import sqlite3
import random
import json
from pathlib import Path
from typing import Optional

# =============================================================================
# CONFIGURATION
# =============================================================================
SOURCE_DB_PATH = "web_data.db"  # Will auto-detect if in parent directory
TEST_DB_PATH = "test_web_data.db"
SAMPLE_SIZE = 200
RANDOM_SEED = 42  # For reproducibility

# =============================================================================
# FUNCTIONS
# =============================================================================


def count_urls_in_db(db_path: str) -> int:
    """Count total number of URLs in the database."""
    if not Path(db_path).exists():
        print(f"❌ Database not found: {db_path}")
        return 0
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM report_data")
        count = cursor.fetchone()[0]
        return count
    except sqlite3.OperationalError as e:
        print(f"❌ Error querying database: {e}")
        return 0
    finally:
        conn.close()


def get_all_urls(db_path: str) -> list[str]:
    """Fetch all URLs from the source database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT url FROM report_data")
        urls = [row[0] for row in cursor.fetchall()]
        return urls
    finally:
        conn.close()


def get_url_data(db_path: str, url: str) -> dict:
    """Fetch all data associated with a URL from the source database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    data = {}
    
    try:
        # Get report_data
        cursor.execute("SELECT cik, year FROM report_data WHERE url = ?", (url,))
        result = cursor.fetchone()
        if result:
            data['cik'], data['year'] = result
        
        # Get webpage_result (matches)
        cursor.execute("SELECT matches FROM webpage_result WHERE url = ?", (url,))
        result = cursor.fetchone()
        if result:
            data['matches'] = result[0]
        
        return data
    finally:
        conn.close()


def create_test_db(
    source_db: str,
    test_db: str,
    sample_size: int = 200,
    seed: Optional[int] = None
) -> bool:
    """
    Create a test database by randomly sampling URLs from the source database.
    
    Args:
        source_db: Path to the source database
        test_db: Path to the test database to create
        sample_size: Number of URLs to sample
        seed: Random seed for reproducibility
    
    Returns:
        True if successful, False otherwise
    """
    if seed is not None:
        random.seed(seed)
    
    # Check source database exists
    if not Path(source_db).exists():
        print(f"❌ Source database not found: {source_db}")
        return False
    
    # Get all URLs
    print(f"📖 Reading URLs from {source_db}...")
    all_urls = get_all_urls(source_db)
    total_urls = len(all_urls)
    
    if total_urls == 0:
        print("❌ No URLs found in source database")
        return False
    
    print(f"✓ Found {total_urls:,} total URLs")
    
    # Sample URLs
    if sample_size > total_urls:
        print(f"⚠️  Requested sample size ({sample_size}) exceeds available URLs ({total_urls})")
        sample_size = total_urls
    
    sampled_urls = random.sample(all_urls, sample_size)
    print(f"✓ Sampled {len(sampled_urls):,} random URLs")
    
    # Create test database with same schema
    print(f"\n🔨 Creating test database: {test_db}")
    conn = sqlite3.connect(test_db)
    cursor = conn.cursor()
    
    try:
        # Create tables
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS webpage_result (
                url TEXT PRIMARY KEY,
                matches TEXT NOT NULL
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS category (
                url TEXT PRIMARY KEY,
                categories TEXT NOT NULL,
                FOREIGN KEY (url) REFERENCES webpage_result(url)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS report_data (
                url TEXT PRIMARY KEY,
                cik INTEGER,
                year INTEGER,
                FOREIGN KEY (url) REFERENCES webpage_result(url)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS server_result (
                url TEXT PRIMARY KEY,
                server_response TEXT,
                FOREIGN KEY (url) REFERENCES webpage_result(url)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS discarded_sentences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT,
                sentence TEXT,
                discard_reason TEXT,
                FOREIGN KEY (url) REFERENCES webpage_result(url)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS discard_reasons (
                reason TEXT PRIMARY KEY
            )
        """)
        
        # Create indices
        cursor.execute("CREATE INDEX IF NOT EXISTS url_idx ON webpage_result (url)")
        cursor.execute("CREATE INDEX IF NOT EXISTS discard_reason_idx ON discarded_sentences (discard_reason)")
        cursor.execute("CREATE INDEX IF NOT EXISTS server_url_idx ON server_result (url)")
        cursor.execute("CREATE INDEX IF NOT EXISTS cat_url_idx ON category (url)")
        cursor.execute("PRAGMA journal_mode=WAL")
        
        print("✓ Tables created")
        
        # Copy data for sampled URLs
        print(f"\n📥 Copying data for {len(sampled_urls):,} sampled URLs...")
        source_conn = sqlite3.connect(source_db)
        source_cursor = source_conn.cursor()
        
        inserted_count = 0
        for i, url in enumerate(sampled_urls, 1):
            data = get_url_data(source_db, url)
            
            # Insert into webpage_result if matches exist
            if 'matches' in data:
                cursor.execute(
                    "INSERT OR IGNORE INTO webpage_result (url, matches) VALUES (?, ?)",
                    (url, data['matches'])
                )
            
            # Insert into category if exists
            if 'categories' in data:
                cursor.execute(
                    "INSERT OR IGNORE INTO category (url, categories) VALUES (?, ?)",
                    (url, data['categories'])
                )
            
            # Insert into report_data
            if 'cik' in data and 'year' in data:
                cursor.execute(
                    "INSERT OR IGNORE INTO report_data (url, cik, year) VALUES (?, ?, ?)",
                    (url, data['cik'], data['year'])
                )
            
            # Insert into server_result if exists
            if 'server_response' in data:
                cursor.execute(
                    "INSERT OR IGNORE INTO server_result (url, server_response) VALUES (?, ?)",
                    (url, data['server_response'])
                )
            
            inserted_count += 1
            if (i) % 50 == 0:
                print(f"  ... processed {i}/{len(sampled_urls)}")
        
        conn.commit()
        source_conn.close()
        print(f"✓ Inserted {inserted_count:,} records")
        
        # Verify
        cursor.execute("SELECT COUNT(*) FROM webpage_result")
        webpage_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM report_data")
        report_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM category")
        category_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM server_result")
        server_count = cursor.fetchone()[0]
        
        print(f"\n✅ Test database created successfully!")
        print(f"\nDatabase Statistics:")
        print(f"  - webpage_result: {webpage_count:,} records")
        print(f"  - report_data: {report_count:,} records")
        print(f"  - category: {category_count:,} records")
        print(f"  - server_result: {server_count:,} records")
        print(f"  - Total URLs sampled: {len(sampled_urls):,}")
        print(f"\n📊 Reduction: {len(sampled_urls):,} / {total_urls:,} = {100*len(sampled_urls)/total_urls:.1f}%")
        
        return True
        
    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
        return False
    finally:
        conn.close()


def main():
    """Main entry point."""
    print("=" * 70)
    print("TEST DATABASE CREATION")
    print("=" * 70)
    
    # Check source database
    source_exists = Path(SOURCE_DB_PATH).exists()
    if not source_exists:
        return False
    
    
    print(f"\nSource DB: {SOURCE_DB_PATH}")
    print(f"Test DB: {TEST_DB_PATH}")
    print(f"Sample size: {SAMPLE_SIZE:,} URLs")
    
    # Remove existing test database if it exists
    if Path(TEST_DB_PATH).exists():
        print(f"\n⚠️  {TEST_DB_PATH} already exists. Removing...")
        Path(TEST_DB_PATH).unlink()
    
    # Create test database
    success = create_test_db(
        SOURCE_DB_PATH,
        TEST_DB_PATH,
        SAMPLE_SIZE,
        RANDOM_SEED
    )
    
    return success


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
