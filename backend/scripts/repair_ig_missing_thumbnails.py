#!/usr/bin/env python3
"""Repair missing IG thumbnail cache entries from refs and ig_posts metadata."""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import httpx
from sqlalchemy import create_engine, text as sa_text


def _discover_workspace_roots() -> list[Path]:
    candidates = [
        Path("/root/.mindscape/workspaces"),
        Path("/app/data/workspaces"),
        Path.home() / ".mindscape" / "workspaces",
    ]
    roots: list[Path] = []
    for path in candidates:
        if path.exists() and path not in roots:
            roots.append(path)
    return roots


def _discover_cache_dir() -> Path:
    candidates = [
        Path("/app/data/ig_thumbnails"),
        Path("data/ig_thumbnails"),
    ]
    for path in candidates:
        if path.exists():
            path.mkdir(parents=True, exist_ok=True)
            return path
    fallback = candidates[0]
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def _get_engine():
    from app.database.config import get_postgres_url_core

    return create_engine(get_postgres_url_core())


@dataclass(frozen=True)
class MissingThumb:
    workspace_id: str
    shortcode: str
    ref_json_path: Path


def _iter_reference_jsons(workspace_roots: Iterable[Path], workspace_id: str | None) -> Iterable[tuple[str, Path]]:
    for root in workspace_roots:
        if workspace_id:
            workspace_dir = root / workspace_id
            if not workspace_dir.exists():
                continue
            references_dir = workspace_dir / "ig" / "references"
            if references_dir.exists():
                for ref_json in references_dir.rglob("*.json"):
                    yield workspace_id, ref_json
            continue

        for workspace_dir in root.iterdir():
            if not workspace_dir.is_dir():
                continue
            references_dir = workspace_dir / "ig" / "references"
            if not references_dir.exists():
                continue
            for ref_json in references_dir.rglob("*.json"):
                yield workspace_dir.name, ref_json


def _resolve_thumbnail_url(conn, workspace_id: str, shortcode: str) -> str | None:
    row = conn.execute(
        sa_text(
            "SELECT thumbnail_url "
            "FROM ig_posts "
            "WHERE workspace_id = :wid "
            "  AND post_shortcode = :sc "
            "  AND thumbnail_url IS NOT NULL "
            "ORDER BY captured_at DESC NULLS LAST "
            "LIMIT 1"
        ),
        {"wid": workspace_id, "sc": shortcode},
    ).fetchone()
    if row and row[0]:
        return str(row[0])
    return None


def _load_ref_json(ref_json: Path) -> dict:
    try:
        return json.loads(ref_json.read_text())
    except Exception:
        return {}


def _download_thumbnail(url: str, cache_path: Path) -> bool:
    storage_state = Path("/app/data/ig-browser-profiles/default/storage_state.json")
    cookies: dict[str, str] = {}
    if storage_state.exists():
        try:
            state = json.loads(storage_state.read_text())
            for cookie in state.get("cookies", []):
                if "instagram.com" in cookie.get("domain", ""):
                    cookies[cookie["name"]] = cookie["value"]
        except Exception:
            pass

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "image/avif,image/webp,image/apng,*/*",
        "Referer": "https://www.instagram.com/",
    }
    if cookies:
        headers["Cookie"] = "; ".join(f"{key}={value}" for key, value in cookies.items())
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            cache_path.write_bytes(response.content)
        return True
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-id", help="Restrict repair to one workspace")
    parser.add_argument("--limit", type=int, default=0, help="Stop after N unresolved shortcodes (0 = all)")
    parser.add_argument("--dry-run", action="store_true", help="Report only; do not copy or download")
    args = parser.parse_args()

    workspace_roots = _discover_workspace_roots()
    if not workspace_roots:
        raise SystemExit("No workspace roots found")

    cache_dir = _discover_cache_dir()

    already_cached = 0
    copied_from_refs = 0
    unresolved_map: dict[tuple[str, str], MissingThumb] = {}
    deleted_without_image = 0

    for wid, ref_json in _iter_reference_jsons(workspace_roots, args.workspace_id):
        if ref_json.name.startswith("_"):
            continue
        shortcode = ref_json.stem
        cache_path = cache_dir / f"{shortcode}.jpg"
        if cache_path.exists():
            already_cached += 1
            continue

        local_jpg = ref_json.with_suffix(".jpg")
        if local_jpg.exists():
            if not args.dry_run:
                shutil.copy2(local_jpg, cache_path)
            copied_from_refs += 1
            continue

        ref_data = _load_ref_json(ref_json)
        if ref_data.get("deleted"):
            deleted_without_image += 1
            continue

        key = (wid, shortcode)
        unresolved_map.setdefault(key, MissingThumb(workspace_id=wid, shortcode=shortcode, ref_json_path=ref_json))

    unresolved = list(unresolved_map.values())
    if args.limit > 0:
        unresolved = unresolved[: args.limit]

    fetched_from_db = 0
    missing_thumbnail_url = 0
    failed_download = 0

    engine = _get_engine()
    with engine.connect() as conn:
        for item in unresolved:
            cache_path = cache_dir / f"{item.shortcode}.jpg"
            thumb_url = _resolve_thumbnail_url(conn, item.workspace_id, item.shortcode)
            if not thumb_url:
                missing_thumbnail_url += 1
                continue
            if args.dry_run:
                fetched_from_db += 1
                continue
            if _download_thumbnail(thumb_url, cache_path):
                fetched_from_db += 1
            else:
                failed_download += 1

    print(
        "\n".join(
            [
                f"workspace_roots={','.join(str(p) for p in workspace_roots)}",
                f"cache_dir={cache_dir}",
                f"already_cached={already_cached}",
                f"copied_from_refs={copied_from_refs}",
                f"unresolved_json_only={len(unresolved)}",
                f"deleted_without_image={deleted_without_image}",
                f"fetched_from_db={fetched_from_db}",
                f"missing_thumbnail_url={missing_thumbnail_url}",
                f"failed_download={failed_download}",
            ]
        )
    )

    if unresolved:
        preview = unresolved[: min(20, len(unresolved))]
        print("unresolved_preview=")
        for item in preview:
            print(f"  {item.workspace_id} {item.shortcode} {item.ref_json_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
