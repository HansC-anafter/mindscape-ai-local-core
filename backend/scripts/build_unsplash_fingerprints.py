"""
Build Unsplash photo fingerprints from Dataset TSV files.

This script processes Unsplash Dataset TSV files and creates fingerprint records
in the database for enhancing Visual Lens extraction.

Usage:
    python backend/scripts/build_unsplash_fingerprints.py --colors colors.tsv --keywords keywords.tsv --photos photos.tsv --collections collections.tsv
"""
import argparse
import csv
import json
import logging
import os
import sys
from typing import Dict, List, Any, Optional
from pathlib import Path

# Add backend directory to path for imports
# Use resolve() to get absolute path, ensuring it works from any directory
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

try:
    import psycopg2
    from psycopg2.extras import execute_values
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
except ImportError:
    print("Error: psycopg2 is required. Install with: pip install psycopg2-binary")
    sys.exit(1)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_db_connection():
    """Get PostgreSQL database connection."""
    postgres_config = {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "database": os.getenv("POSTGRES_DB", "mindscape_vectors"),
        "user": os.getenv("POSTGRES_USER", "mindscape"),
        "password": os.getenv("POSTGRES_PASSWORD", "mindscape_password"),
    }

    conn = psycopg2.connect(**postgres_config)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    return conn


def ensure_table_exists(conn):
    """Ensure unsplash_photo_fingerprints table exists."""
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS unsplash_photo_fingerprints (
            photo_id VARCHAR(255) PRIMARY KEY,
            colors JSONB,
            keywords JSONB,
            collections JSONB,
            exif_data JSONB,
            ai_description TEXT,
            aspect_ratio FLOAT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_unsplash_fingerprint_photo_id
        ON unsplash_photo_fingerprints(photo_id)
    """)

    cursor.close()
    logger.info("Table unsplash_photo_fingerprints ensured")


def parse_colors_tsv(file_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Parse colors.tsv and group by photo_id.

    Expected columns: photo_id, hex, coverage, score, ...
    Returns: {photo_id: [{hex, coverage, score, ...}]}
    """
    colors_by_photo: Dict[str, List[Dict[str, Any]]] = {}

    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            photo_id = row.get('photo_id')
            if not photo_id:
                continue

            color_entry = {
                'hex': row.get('hex', ''),
                'coverage': float(row.get('coverage', 0)) if row.get('coverage') else 0.0,
                'score': float(row.get('score', 0)) if row.get('score') else 0.0,
            }

            if photo_id not in colors_by_photo:
                colors_by_photo[photo_id] = []
            colors_by_photo[photo_id].append(color_entry)

    logger.info(f"Parsed {len(colors_by_photo)} photos with color data from {file_path}")
    return colors_by_photo


def parse_keywords_tsv(file_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Parse keywords.tsv and group by photo_id.

    Expected columns: photo_id, keyword, confidence, source, ...
    Returns: {photo_id: [{value, confidence, source, ...}]}
    """
    keywords_by_photo: Dict[str, List[Dict[str, Any]]] = {}

    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            photo_id = row.get('photo_id')
            if not photo_id:
                continue

            keyword_entry = {
                'value': row.get('keyword', '') or row.get('value', ''),
                'confidence': float(row.get('confidence', 0)) if row.get('confidence') else None,
                'source': row.get('source', '') or row.get('keyword_source', ''),
            }

            if photo_id not in keywords_by_photo:
                keywords_by_photo[photo_id] = []
            keywords_by_photo[photo_id].append(keyword_entry)

    logger.info(f"Parsed {len(keywords_by_photo)} photos with keyword data from {file_path}")
    return keywords_by_photo


def parse_collections_tsv(file_path: str) -> Dict[str, List[str]]:
    """
    Parse collections.tsv and group by photo_id.

    Expected columns: photo_id, collection_id, title, ...
    Returns: {photo_id: [collection_title, ...]}
    """
    collections_by_photo: Dict[str, List[str]] = {}

    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            photo_id = row.get('photo_id')
            if not photo_id:
                continue

            title = row.get('title', '') or row.get('collection_title', '')
            if title:
                if photo_id not in collections_by_photo:
                    collections_by_photo[photo_id] = []
                collections_by_photo[photo_id].append(title)

    logger.info(f"Parsed {len(collections_by_photo)} photos with collection data from {file_path}")
    return collections_by_photo


def parse_photos_tsv(file_path: str) -> Dict[str, Dict[str, Any]]:
    """
    Parse photos.tsv and extract relevant fields.

    Expected columns: photo_id, ai_description, exif_camera, exif_focal_length, ...
    Returns: {photo_id: {exif_json, ai_description, aspect_ratio}}
    """
    photos_data: Dict[str, Dict[str, Any]] = {}

    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            photo_id = row.get('photo_id')
            if not photo_id:
                continue

            # Extract EXIF data
            exif_json = {}
            if row.get('exif_focal_length'):
                exif_json['focal_length'] = row.get('exif_focal_length')
            if row.get('exif_aperture'):
                exif_json['aperture'] = row.get('exif_aperture')
            if row.get('exif_iso'):
                exif_json['iso'] = row.get('exif_iso')
            if row.get('exif_exposure_time'):
                exif_json['exposure_time'] = row.get('exif_exposure_time')

            # Extract aspect ratio
            aspect_ratio = None
            if row.get('width') and row.get('height'):
                try:
                    width = float(row.get('width'))
                    height = float(row.get('height'))
                    if height > 0:
                        aspect_ratio = width / height
                except (ValueError, TypeError):
                    pass

            photos_data[photo_id] = {
                'exif_json': exif_json if exif_json else None,
                'ai_description': row.get('ai_description', '') or row.get('description', ''),
                'aspect_ratio': aspect_ratio,
            }

    logger.info(f"Parsed {len(photos_data)} photos with metadata from {file_path}")
    return photos_data


def build_fingerprints(
    colors_file: Optional[str] = None,
    keywords_file: Optional[str] = None,
    photos_file: Optional[str] = None,
    collections_file: Optional[str] = None,
    batch_size: int = 1000
):
    """Build fingerprints from TSV files and insert into database."""
    # Parse TSV files
    colors_by_photo = {}
    keywords_by_photo = {}
    collections_by_photo = {}
    photos_data = {}

    if colors_file:
        colors_by_photo = parse_colors_tsv(colors_file)

    if keywords_file:
        keywords_by_photo = parse_keywords_tsv(keywords_file)

    if collections_file:
        collections_by_photo = parse_collections_tsv(collections_file)

    if photos_file:
        photos_data = parse_photos_tsv(photos_file)

    # Collect all unique photo IDs
    all_photo_ids = set()
    all_photo_ids.update(colors_by_photo.keys())
    all_photo_ids.update(keywords_by_photo.keys())
    all_photo_ids.update(collections_by_photo.keys())
    all_photo_ids.update(photos_data.keys())

    logger.info(f"Total unique photo IDs: {len(all_photo_ids)}")

    # Connect to database
    conn = get_db_connection()
    ensure_table_exists(conn)
    cursor = conn.cursor()

    inserted_count = 0
    updated_count = 0

    try:
        for i, photo_id in enumerate(all_photo_ids):
            # Check if photo exists
            cursor.execute(
                "SELECT photo_id FROM unsplash_photo_fingerprints WHERE photo_id = %s",
                (photo_id,)
            )
            exists = cursor.fetchone()

            colors_json = json.dumps(colors_by_photo.get(photo_id, [])) if colors_by_photo.get(photo_id) else None
            keywords_json = json.dumps(keywords_by_photo.get(photo_id, [])) if keywords_by_photo.get(photo_id) else None
            collections_json = json.dumps(collections_by_photo.get(photo_id, [])) if collections_by_photo.get(photo_id) else None

            photo_info = photos_data.get(photo_id, {})
            exif_json = json.dumps(photo_info.get('exif_json')) if photo_info.get('exif_json') else None
            ai_description = photo_info.get('ai_description') or None
            aspect_ratio = photo_info.get('aspect_ratio')

            if exists:
                # Update existing
                update_fields = []
                update_values = []

                if colors_json is not None:
                    update_fields.append("colors = %s")
                    update_values.append(colors_json)
                if keywords_json is not None:
                    update_fields.append("keywords = %s")
                    update_values.append(keywords_json)
                if collections_json is not None:
                    update_fields.append("collections = %s")
                    update_values.append(collections_json)
                if exif_json is not None:
                    update_fields.append("exif_data = %s")
                    update_values.append(exif_json)
                if ai_description is not None:
                    update_fields.append("ai_description = %s")
                    update_values.append(ai_description)
                if aspect_ratio is not None:
                    update_fields.append("aspect_ratio = %s")
                    update_values.append(aspect_ratio)

                if update_fields:
                    update_fields.append("updated_at = NOW()")
                    update_values.append(photo_id)

                    cursor.execute(
                        f"UPDATE unsplash_photo_fingerprints SET {', '.join(update_fields)} WHERE photo_id = %s",
                        update_values
                    )
                    updated_count += 1
            else:
                # Insert new
                cursor.execute("""
                    INSERT INTO unsplash_photo_fingerprints
                    (photo_id, colors, keywords, collections, exif_data, ai_description, aspect_ratio)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    photo_id,
                    colors_json,
                    keywords_json,
                    collections_json,
                    exif_json,
                    ai_description,
                    aspect_ratio,
                ))
                inserted_count += 1

            # Commit in batches
            if (i + 1) % batch_size == 0:
                conn.commit()
                logger.info(f"Processed {i + 1}/{len(all_photo_ids)} photos (inserted: {inserted_count}, updated: {updated_count})")

        # Final commit
        conn.commit()
        logger.info(f"Completed: inserted {inserted_count}, updated {updated_count} fingerprints")

    except Exception as e:
        conn.rollback()
        logger.error(f"Error building fingerprints: {e}", exc_info=True)
        raise
    finally:
        cursor.close()
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Build Unsplash photo fingerprints from Dataset TSV files")
    parser.add_argument("--colors", type=str, help="Path to colors.tsv file")
    parser.add_argument("--keywords", type=str, help="Path to keywords.tsv file")
    parser.add_argument("--photos", type=str, help="Path to photos.tsv file")
    parser.add_argument("--collections", type=str, help="Path to collections.tsv file")
    parser.add_argument("--batch-size", type=int, default=1000, help="Batch size for database inserts")

    args = parser.parse_args()

    if not any([args.colors, args.keywords, args.photos, args.collections]):
        parser.error("At least one TSV file must be provided")

    build_fingerprints(
        colors_file=args.colors,
        keywords_file=args.keywords,
        photos_file=args.photos,
        collections_file=args.collections,
        batch_size=args.batch_size
    )


if __name__ == "__main__":
    main()

