#!/usr/bin/env python3
"""
Copy Instagram cookies from local Chrome profile to Playwright profile.

This script copies the sessionid and other Instagram cookies from your
local Chrome browser to the Playwright profile used by Backend Automation.
"""

import sqlite3
import shutil
import os
from pathlib import Path

def copy_instagram_cookies(source_cookies_db, target_cookies_db):
    """Copy Instagram cookies from source to target database."""
    if not os.path.exists(source_cookies_db):
        print(f"❌ Source cookies file not found: {source_cookies_db}")
        return False

    # Backup target database
    if os.path.exists(target_cookies_db):
        backup_path = f"{target_cookies_db}.backup"
        shutil.copy2(target_cookies_db, backup_path)
        print(f"✓ Backed up target cookies to: {backup_path}")

    # Connect to source database
    source_conn = sqlite3.connect(source_cookies_db)
    source_cursor = source_conn.cursor()

    # Get all Instagram cookies from source
    source_cursor.execute("""
        SELECT host_key, name, value, path, expires_utc, is_secure, is_httponly,
               samesite, priority, has_expires, is_persistent, creation_utc
        FROM cookies
        WHERE host_key LIKE '%instagram%'
    """)
    instagram_cookies = source_cursor.fetchall()
    source_conn.close()

    if not instagram_cookies:
        print("❌ No Instagram cookies found in source database")
        return False

    print(f"✓ Found {len(instagram_cookies)} Instagram cookies in source")

    # Connect to target database
    target_conn = sqlite3.connect(target_cookies_db)
    target_cursor = target_conn.cursor()

    # Ensure cookies table exists (should already exist)
    target_cursor.execute("""
        CREATE TABLE IF NOT EXISTS cookies (
            host_key TEXT NOT NULL,
            name TEXT NOT NULL,
            value TEXT NOT NULL,
            path TEXT NOT NULL,
            expires_utc INTEGER NOT NULL,
            is_secure INTEGER NOT NULL,
            is_httponly INTEGER NOT NULL,
            samesite INTEGER NOT NULL,
            priority INTEGER NOT NULL,
            has_expires INTEGER NOT NULL,
            is_persistent INTEGER NOT NULL,
            creation_utc INTEGER NOT NULL,
            last_access_utc INTEGER NOT NULL,
            last_update_utc INTEGER NOT NULL,
            PRIMARY KEY (host_key, name, path)
        )
    """)

    # Delete existing Instagram cookies from target
    target_cursor.execute("DELETE FROM cookies WHERE host_key LIKE '%instagram%'")
    deleted_count = target_cursor.rowcount
    print(f"✓ Deleted {deleted_count} existing Instagram cookies from target")

    # Insert cookies from source
    inserted_count = 0
    for cookie in instagram_cookies:
        try:
            target_cursor.execute("""
                INSERT OR REPLACE INTO cookies (
                    host_key, name, value, path, expires_utc, is_secure, is_httponly,
                    samesite, priority, has_expires, is_persistent, creation_utc,
                    last_access_utc, last_update_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                cookie[0], cookie[1], cookie[2], cookie[3], cookie[4], cookie[5],
                cookie[6], cookie[7], cookie[8], cookie[9], cookie[10], cookie[11],
                cookie[11], cookie[11]  # Use creation_utc for last_access and last_update
            ))
            inserted_count += 1
        except Exception as e:
            print(f"⚠ Warning: Failed to insert cookie {cookie[1]}: {e}")

    target_conn.commit()
    target_conn.close()

    print(f"✓ Inserted {inserted_count} Instagram cookies into target")

    # Check if sessionid was copied
    check_conn = sqlite3.connect(target_cookies_db)
    check_cursor = check_conn.cursor()
    check_cursor.execute("SELECT name FROM cookies WHERE name = 'sessionid' AND host_key LIKE '%instagram%'")
    if check_cursor.fetchone():
        print("✅ sessionid successfully copied!")
    else:
        print("❌ sessionid was not copied (may not exist in source)")
    check_conn.close()

    return True


def main():
    # Source: Local Chrome profile
    chrome_profile = Path.home() / "Library/Application Support/Google/Chrome/Default"
    source_cookies = chrome_profile / "Cookies"

    # Target: Playwright profile
    playwright_profile = Path(__file__).parent.parent / "data" / "ig-browser-profiles" / "default"
    target_cookies = playwright_profile / "Default" / "Cookies"

    print("=" * 60)
    print("Copy Instagram Cookies from Chrome to Playwright")
    print("=" * 60)
    print(f"Source: {source_cookies}")
    print(f"Target: {target_cookies}")
    print()

    if not source_cookies.exists():
        print(f"❌ Source cookies file not found: {source_cookies}")
        print("   Make sure Chrome is installed and you're logged into Instagram")
        return

    if not target_cookies.parent.exists():
        target_cookies.parent.mkdir(parents=True, exist_ok=True)
        print(f"✓ Created target directory: {target_cookies.parent}")

    if copy_instagram_cookies(str(source_cookies), str(target_cookies)):
        print()
        print("=" * 60)
        print("✅ Cookies copied successfully!")
        print("=" * 60)
        print()
        print("You can now use Backend Automation with your Instagram login.")
    else:
        print()
        print("=" * 60)
        print("❌ Failed to copy cookies")
        print("=" * 60)


if __name__ == "__main__":
    main()
