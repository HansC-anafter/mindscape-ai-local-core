#!/usr/bin/env python3
"""
Batch re-export images into fresh files to drop embedded metadata.

This script intentionally re-saves pixel data into new files without carrying
over EXIF/XMP/ICC/text chunks. It reduces the chance that source-side embedded
AI/provenance metadata survives, but it cannot guarantee that downstream
platforms will not add their own labels or detect AI content heuristically.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from PIL import Image


SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Re-export images into fresh files without carrying source metadata."
    )
    parser.add_argument("input_dir", type=Path, help="Directory containing source images.")
    parser.add_argument(
        "output_dir",
        type=Path,
        nargs="?",
        help="Directory to write cleaned images into. Defaults to <input_dir>_clean.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite output files if they already exist.",
    )
    parser.add_argument(
        "--format",
        choices=["keep", "jpeg", "png", "webp"],
        default="keep",
        help="Output format. 'keep' preserves the original extension when supported.",
    )
    parser.add_argument(
        "--jpeg-quality",
        type=int,
        default=95,
        help="JPEG quality when output format is jpeg. Default: 95.",
    )
    return parser.parse_args()


def ensure_output_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def iter_source_files(input_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in input_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def target_suffix(source: Path, format_mode: str) -> str:
    if format_mode == "keep":
        return source.suffix.lower()
    if format_mode == "jpeg":
        return ".jpg"
    if format_mode == "png":
        return ".png"
    if format_mode == "webp":
        return ".webp"
    raise ValueError(f"unsupported format mode: {format_mode}")


def build_target_path(source: Path, output_dir: Path, format_mode: str) -> Path:
    suffix = target_suffix(source, format_mode)
    return output_dir / f"{source.stem}{suffix}"


def load_pixels(path: Path) -> Image.Image:
    with Image.open(path) as img:
        img.load()
        # Copy the decoded pixels into a fresh in-memory image object so we
        # don't carry over info/exif/text chunks from the source container.
        fresh = Image.new(img.mode, img.size)
        fresh.putdata(list(img.getdata()))
        return fresh


def normalize_for_format(image: Image.Image, suffix: str) -> Image.Image:
    if suffix in {".jpg", ".jpeg"} and image.mode not in {"RGB", "L"}:
        if image.mode in {"RGBA", "LA"}:
            background = Image.new("RGB", image.size, (255, 255, 255))
            alpha = image.getchannel("A")
            background.paste(image.convert("RGB"), mask=alpha)
            return background
        return image.convert("RGB")
    return image


def save_clean_image(image: Image.Image, output_path: Path, jpeg_quality: int) -> None:
    suffix = output_path.suffix.lower()
    image = normalize_for_format(image, suffix)
    save_kwargs: dict[str, object] = {}

    if suffix in {".jpg", ".jpeg"}:
        save_kwargs.update(
            {
                "format": "JPEG",
                "quality": jpeg_quality,
                "optimize": True,
                "subsampling": 0,
            }
        )
    elif suffix == ".png":
        save_kwargs.update({"format": "PNG", "optimize": True})
    elif suffix == ".webp":
        save_kwargs.update({"format": "WEBP", "quality": 95, "method": 6})
    elif suffix == ".bmp":
        save_kwargs.update({"format": "BMP"})
    elif suffix in {".tif", ".tiff"}:
        save_kwargs.update({"format": "TIFF"})
    else:
        raise ValueError(f"unsupported output suffix: {suffix}")

    image.save(output_path, **save_kwargs)


def main() -> int:
    args = parse_args()
    input_dir = args.input_dir.expanduser().resolve()
    output_dir = (args.output_dir or Path(f"{input_dir}_clean")).expanduser().resolve()

    if not input_dir.exists():
        print(f"Input directory not found: {input_dir}", file=sys.stderr)
        return 1
    if not input_dir.is_dir():
        print(f"Input path is not a directory: {input_dir}", file=sys.stderr)
        return 1

    ensure_output_dir(output_dir)
    source_files = iter_source_files(input_dir)
    if not source_files:
        print(f"No supported images found in: {input_dir}", file=sys.stderr)
        return 1

    converted = 0
    skipped = 0
    failed = 0

    for source in source_files:
        target = build_target_path(source, output_dir, args.format)
        if target.exists() and not args.overwrite:
            print(f"SKIP {source.name} -> {target.name} (exists)")
            skipped += 1
            continue

        try:
            image = load_pixels(source)
            save_clean_image(image, target, args.jpeg_quality)
            try:
                shutil.copystat(source, target, follow_symlinks=True)
            except OSError:
                pass
            print(f"OK   {source.name} -> {target.name}")
            converted += 1
        except Exception as exc:  # pragma: no cover - exercised in live use
            print(f"FAIL {source.name}: {exc}", file=sys.stderr)
            failed += 1

    print(
        f"\nDone. converted={converted} skipped={skipped} failed={failed} output={output_dir}"
    )
    return 0 if converted > 0 and failed == 0 else (1 if failed else 0)


if __name__ == "__main__":
    raise SystemExit(main())
