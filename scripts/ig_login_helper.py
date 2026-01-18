#!/usr/bin/env python3
"""
IG Login Helper - Create a logged-in browser profile for IG Following Analyzer

This script opens a browser window where you can manually log into Instagram.
After login, the profile is saved and can be used for automated analysis.

Usage:
    python scripts/ig_login_helper.py

The browser profile will be saved to: data/ig-browser-profiles/default
"""

import asyncio
import os
from pathlib import Path

# Check playwright is installed
try:
    from playwright.async_api import async_playwright
except ImportError:
    print("Playwright not installed. Installing...")
    os.system("pip install playwright && playwright install chromium")
    from playwright.async_api import async_playwright


async def main():
    profile_dir = Path(__file__).parent.parent / "data" / "ig-browser-profiles" / "default"
    profile_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("IG Login Helper")
    print("=" * 60)
    print(f"Browser profile will be saved to: {profile_dir}")
    print()
    print("Instructions:")
    print("1. A browser window will open to Instagram")
    print("2. Log in to your Instagram account")
    print("3. After successful login, close the browser window")
    print("4. Your login session will be saved for future use")
    print("=" * 60)
    print()

    async with async_playwright() as p:
        # Launch persistent context (saves cookies/session)
        context = await p.chromium.launch_persistent_context(
            str(profile_dir),
            headless=False,  # Must be visible for manual login
            viewport={"width": 1280, "height": 800},
            locale="en-US"
        )

        page = await context.new_page()

        print("Opening Instagram...")
        await page.goto("https://www.instagram.com/")

        print()
        print(">>> Browser opened. Please log in to Instagram.")
        print(">>> After login, keep the window open for a moment.")
        print(">>> This script will auto-save storage_state as soon as it detects sessionid.")
        print(">>> Then you can close the browser window.")
        print()

        storage_state_path = profile_dir / "storage_state.json"
        saved_once = asyncio.Event()

        async def _auto_save_storage_state_when_logged_in() -> None:
            """
            Save storage_state ASAP after detecting a valid sessionid cookie.

            Why:
            - Instagram's sessionid can be session-only and may be cleared on close.
            - Saving *after* window close can miss it. We save as soon as it's present.
            """
            for _ in range(300):  # ~10 minutes (300 * 2s)
                try:
                    cookies = await context.cookies("https://www.instagram.com/")
                    if any(c.get("name") == "sessionid" for c in cookies):
                        await context.storage_state(path=str(storage_state_path))
                        print(f">>> Detected sessionid. storage_state saved: {storage_state_path}")
                        saved_once.set()
                        return
                except Exception:
                    # Ignore transient read/save errors; keep polling.
                    pass
                await asyncio.sleep(2)

        autosave_task = asyncio.create_task(_auto_save_storage_state_when_logged_in())

        # Wait for user to close the browser (or timeout)
        try:
            await page.wait_for_event("close", timeout=600000)  # 10 minutes timeout
        except Exception:
            pass
        finally:
            if not autosave_task.done():
                autosave_task.cancel()
                try:
                    await autosave_task
                except Exception:
                    pass

        # Best-effort final write (in case cookie is still present)
        if not saved_once.is_set():
            try:
                await context.storage_state(path=str(storage_state_path))
                print(f">>> storage_state saved (final attempt): {storage_state_path}")
            except Exception as e:
                print(f">>> Failed to save storage_state (final attempt): {e}")

        await context.close()

    print()
    print("=" * 60)
    print("Login session saved!")
    print(f"Profile location: {profile_dir}")
    print()
    print("You can now use the IG Following Analyzer with this profile.")
    print("The profile path to use: /app/data/ig-browser-profiles/default")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
