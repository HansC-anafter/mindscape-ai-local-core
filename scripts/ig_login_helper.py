#!/usr/bin/env python3
"""
IG Login Helper - Create a logged-in browser profile for IG Following Analyzer

This script opens a browser window where you can manually log into Instagram.
After login, the profile is saved and can be used for automated analysis.

Usage:
    python scripts/ig_login_helper.py
    python scripts/ig_login_helper.py --profile-name client-a
    python scripts/ig_login_helper.py --user-data-dir /absolute/path/to/profile

The browser profile will be saved to the selected profile directory.
"""

import asyncio
import argparse
import os
import re
from pathlib import Path

def load_async_playwright():
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("Playwright not installed. Installing...")
        os.system("pip install playwright && playwright install chromium")
        from playwright.async_api import async_playwright
    return async_playwright


def normalize_profile_name(raw: str) -> str:
    trimmed = (raw or "").strip().lower()
    if not trimmed:
        return "default"
    normalized = re.sub(r"\s+", "-", trimmed)
    normalized = re.sub(r"[^a-z0-9._-]+", "-", normalized)
    normalized = re.sub(r"-{2,}", "-", normalized)
    normalized = normalized.strip("-.")
    return normalized or "default"


def _read_dotenv_value(dotenv_path: Path, key: str) -> str | None:
    try:
        for line in dotenv_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            current_key, raw_value = stripped.split("=", 1)
            if current_key.strip() != key:
                continue
            value = raw_value.strip().strip('"').strip("'")
            return value or None
    except Exception:
        return None
    return None


def _expand_host_path(raw_path: str, repo_root: Path) -> Path:
    expanded = os.path.expandvars(os.path.expanduser((raw_path or "").strip()))
    path = Path(expanded)
    if path.is_absolute():
        return path.resolve()
    return (repo_root / path).resolve()


def resolve_local_core_data_root(repo_root: Path) -> tuple[Path, str]:
    env_value = (os.environ.get("LOCAL_CORE_DATA_HOST_DIR") or "").strip()
    if env_value:
        return _expand_host_path(env_value, repo_root), "env:LOCAL_CORE_DATA_HOST_DIR"

    dotenv_value = _read_dotenv_value(repo_root / ".env", "LOCAL_CORE_DATA_HOST_DIR")
    if dotenv_value:
        return _expand_host_path(dotenv_value, repo_root), ".env:LOCAL_CORE_DATA_HOST_DIR"

    return (repo_root / "data").resolve(), "fallback:repo_data"


def _resolve_user_data_dir(user_data_dir: str, repo_root: Path, data_root: Path) -> Path:
    raw = (user_data_dir or "").strip()
    if not raw:
        return data_root

    expanded = os.path.expandvars(os.path.expanduser(raw))
    if expanded == "/app/data":
        return data_root.resolve()
    if expanded.startswith("/app/data/"):
        suffix = expanded[len("/app/data/"):].strip("/")
        return (data_root / suffix).resolve()

    path = Path(expanded)
    if path.is_absolute():
        return path.resolve()
    return (repo_root / path).resolve()


def resolve_profile_dir(profile_name: str, user_data_dir: str | None, data_root: Path) -> tuple[Path, str]:
    repo_root = Path(__file__).parent.parent
    if user_data_dir:
        profile_dir = _resolve_user_data_dir(user_data_dir, repo_root, data_root)
        profile_label = profile_dir.name or normalize_profile_name(profile_name)
        return profile_dir, profile_label

    normalized_name = normalize_profile_name(profile_name)
    profile_dir = data_root / "ig-browser-profiles" / normalized_name
    return profile_dir, normalized_name


def to_app_profile_path(profile_dir: Path, data_root: Path) -> str:
    try:
        relative = profile_dir.resolve().relative_to(data_root.resolve())
    except ValueError:
        return str(profile_dir.resolve())
    return f"/app/data/{relative.as_posix()}"


async def main():
    parser = argparse.ArgumentParser(description="Create or update an IG browser profile session")
    parser.add_argument(
        "--profile-name",
        default="default",
        help="Named IG browser profile under data/ig-browser-profiles (default: default)",
    )
    parser.add_argument(
        "--user-data-dir",
        default="",
        help="Optional explicit profile directory. Overrides --profile-name when provided.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).parent.parent
    data_root, data_root_source = resolve_local_core_data_root(repo_root)
    profile_dir, profile_label = resolve_profile_dir(
        args.profile_name,
        (args.user_data_dir or "").strip() or None,
        data_root,
    )
    profile_dir.mkdir(parents=True, exist_ok=True)
    app_profile_path = to_app_profile_path(profile_dir, data_root)

    print("=" * 60)
    print("IG Login Helper")
    print("=" * 60)
    print(f"Access profile: {profile_label}")
    print(f"Host data root: {data_root} ({data_root_source})")
    print(f"Browser profile will be saved to: {profile_dir}")
    print(f"Container path: {app_profile_path}")
    print()
    print("Instructions:")
    print("1. A browser window will open to Instagram")
    print("2. Log in to your Instagram account")
    print("3. After successful login, close the browser window")
    print("4. Your login session will be saved for future use")
    print("=" * 60)
    print()

    async_playwright = load_async_playwright()
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
    print(f"Access profile: {profile_label}")
    print(f"Profile location: {profile_dir}")
    print()
    print("You can now use the IG Following Analyzer with this profile.")
    print(f"The profile path to use: {app_profile_path}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
