"""
Build style fingerprints and keyword-to-visual-preference mappings from Dataset TSV files.

This script processes conversions.tsv, keywords.tsv, and colors.tsv to build:
1. Style fingerprints (style clusters with visual/semantic/intent signals)
2. Keyword-to-style mappings (keyword → associated styles)
3. Photo-to-style associations (photo → style clusters)

Usage:
    python backend/scripts/build_style_fingerprints.py \
      --conversions conversions.tsv \
      --keywords keywords.tsv \
      --colors colors.tsv \
      --photos photos.tsv \
      --min-keyword-frequency 100 \
      --style-clusters 50
"""
import argparse
import csv
import json
import logging
import os
import sys
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
from collections import defaultdict, Counter
import math

# Add backend directory to path for imports
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


def ensure_tables_exist(conn):
    """Ensure style fingerprint tables exist."""
    cursor = conn.cursor()

    # Style fingerprints table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS style_fingerprints (
            style_id VARCHAR(255) PRIMARY KEY,
            style_name VARCHAR(255),
            color_distribution JSONB,
            dominant_colors JSONB,
            keyword_signatures JSONB,
            ai_description_patterns TEXT[],
            conversion_keywords JSONB,
            top_conversion_photos VARCHAR(255)[],
            photo_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Keyword-to-style mappings table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS keyword_style_mappings (
            keyword VARCHAR(255) PRIMARY KEY,
            associated_styles JSONB,
            top_conversion_photos JSONB,
            total_downloads INTEGER DEFAULT 0,
            unique_photos INTEGER DEFAULT 0,
            avg_confidence FLOAT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Photo-to-style associations table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS photo_style_associations (
            photo_id VARCHAR(255),
            style_id VARCHAR(255),
            relevance_score FLOAT,
            source VARCHAR(50),
            PRIMARY KEY (photo_id, style_id)
        )
    """)

    # Create indexes
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_photo_style_photo_id
        ON photo_style_associations(photo_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_photo_style_style_id
        ON photo_style_associations(style_id)
    """)

    cursor.close()
    logger.info("Style fingerprint tables ensured")


def parse_conversions_tsv(file_path: str, min_frequency: int = 100) -> Dict[str, Dict[str, Any]]:
    """
    Parse conversions.tsv and build keyword → download statistics.

    Returns: {
        keyword: {
            'total_downloads': int,
            'unique_photos': set,
            'photo_downloads': {photo_id: download_count}
        }
    }
    """
    keyword_stats = defaultdict(lambda: {
        'total_downloads': 0,
        'unique_photos': set(),
        'photo_downloads': defaultdict(int)
    })

    logger.info(f"Parsing conversions.tsv: {file_path}")

    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')
        row_count = 0

        for row in reader:
            row_count += 1
            if row_count % 100000 == 0:
                logger.info(f"Processed {row_count} conversion records...")

            keyword = row.get('keyword', '').strip().lower()
            photo_id = row.get('photo_id', '').strip()

            if not keyword or not photo_id:
                continue

            # Count downloads (assuming each row is one download event)
            keyword_stats[keyword]['total_downloads'] += 1
            keyword_stats[keyword]['unique_photos'].add(photo_id)
            keyword_stats[keyword]['photo_downloads'][photo_id] += 1

    logger.info(f"Parsed {row_count} conversion records")

    # Filter by minimum frequency
    filtered_stats = {
        kw: {
            'total_downloads': stats['total_downloads'],
            'unique_photos': len(stats['unique_photos']),
            'photo_downloads': dict(stats['photo_downloads'])
        }
        for kw, stats in keyword_stats.items()
        if stats['total_downloads'] >= min_frequency
    }

    logger.info(f"Filtered to {len(filtered_stats)} keywords with >= {min_frequency} downloads")

    return filtered_stats


def parse_keywords_for_style(keywords_file: str, photo_ids: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
    """
    Parse keywords.tsv and aggregate by keyword.

    Returns: {
        keyword: {
            'photos': [photo_id],
            'avg_confidence': float,
            'total_count': int
        }
    }
    """
    keyword_photos = defaultdict(lambda: {
        'photos': [],
        'confidence_sum': 0.0,
        'count': 0
    })

    photo_set = set(photo_ids) if photo_ids else None

    logger.info(f"Parsing keywords.tsv: {keywords_file}")

    with open(keywords_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')
        row_count = 0

        for row in reader:
            row_count += 1
            if row_count % 100000 == 0:
                logger.info(f"Processed {row_count} keyword records...")

            photo_id = row.get('photo_id', '').strip()
            keyword = row.get('keyword', '').strip().lower()

            if not keyword or not photo_id:
                continue

            # Filter by photo_ids if provided
            if photo_set and photo_id not in photo_set:
                continue

            confidence = float(row.get('confidence', 0.5)) if row.get('confidence') else 0.5

            keyword_photos[keyword]['photos'].append(photo_id)
            keyword_photos[keyword]['confidence_sum'] += confidence
            keyword_photos[keyword]['count'] += 1

    logger.info(f"Parsed {row_count} keyword records")

    # Calculate averages
    result = {}
    for keyword, stats in keyword_photos.items():
        result[keyword] = {
            'photos': list(set(stats['photos'])),  # Unique photos
            'avg_confidence': stats['confidence_sum'] / stats['count'] if stats['count'] > 0 else 0.5,
            'total_count': stats['count']
        }

    logger.info(f"Aggregated {len(result)} unique keywords")

    return result


def parse_colors_for_style(colors_file: str, photo_ids: Optional[List[str]] = None) -> Dict[str, List[Dict[str, Any]]]:
    """
    Parse colors.tsv and group by photo_id.

    Returns: {photo_id: [color_entries]}
    """
    photo_colors = defaultdict(list)
    photo_set = set(photo_ids) if photo_ids else None

    logger.info(f"Parsing colors.tsv: {colors_file}")

    with open(colors_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')
        row_count = 0

        for row in reader:
            row_count += 1
            if row_count % 100000 == 0:
                logger.info(f"Processed {row_count} color records...")

            photo_id = row.get('photo_id', '').strip()

            if not photo_id:
                continue

            # Filter by photo_ids if provided
            if photo_set and photo_id not in photo_set:
                continue

            color_entry = {
                'hex': row.get('hex', ''),
                'coverage': float(row.get('coverage', 0)) if row.get('coverage') else 0.0,
                'score': float(row.get('score', 0)) if row.get('score') else 0.0,
            }

            photo_colors[photo_id].append(color_entry)

    logger.info(f"Parsed {row_count} color records for {len(photo_colors)} photos")

    return dict(photo_colors)


def build_keyword_style_mappings(
    conversions_stats: Dict[str, Dict[str, Any]],
    keyword_photos: Dict[str, Dict[str, Any]],
    conn
):
    """Build keyword-to-style mappings from conversions and keywords data."""
    cursor = conn.cursor()

    logger.info("Building keyword-style mappings...")

    # Get top photos for each keyword from conversions
    for keyword, stats in conversions_stats.items():
        # Get top conversion photos
        photo_downloads = stats['photo_downloads']
        top_photos = sorted(
            photo_downloads.items(),
            key=lambda x: x[1],
            reverse=True
        )[:100]  # Top 100 photos

        top_conversion_photos = [
            {'photo_id': photo_id, 'download_count': count}
            for photo_id, count in top_photos
        ]

        # Get keyword metadata
        keyword_meta = keyword_photos.get(keyword, {})
        avg_confidence = keyword_meta.get('avg_confidence', 0.5)
        unique_photos = keyword_meta.get('photos', [])

        # For now, we'll create placeholder style associations
        # In Phase 2, we'll cluster photos into styles
        associated_styles = []  # Will be populated after style clustering

        # Insert or update
        cursor.execute("""
            INSERT INTO keyword_style_mappings
            (keyword, associated_styles, top_conversion_photos, total_downloads, unique_photos, avg_confidence, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (keyword) DO UPDATE SET
                associated_styles = EXCLUDED.associated_styles,
                top_conversion_photos = EXCLUDED.top_conversion_photos,
                total_downloads = EXCLUDED.total_downloads,
                unique_photos = EXCLUDED.unique_photos,
                avg_confidence = EXCLUDED.avg_confidence,
                updated_at = NOW()
        """, (
            keyword,
            json.dumps(associated_styles),
            json.dumps(top_conversion_photos),
            stats['total_downloads'],
            len(unique_photos),
            avg_confidence
        ))

    conn.commit()
    cursor.close()
    logger.info(f"Built {len(conversions_stats)} keyword-style mappings")


def build_style_fingerprints(
    conversions_stats: Dict[str, Dict[str, Any]],
    keyword_photos: Dict[str, Dict[str, Any]],
    photo_colors: Dict[str, List[Dict[str, Any]]],
    num_clusters: int,
    conn
):
    """
    Build style fingerprints by clustering photos based on:
    - Visual signals (colors)
    - Semantic signals (keywords)
    - Intent signals (conversions)
    """
    logger.info(f"Building style fingerprints with {num_clusters} clusters...")

    # Step 1: Collect all photos with their features
    all_photos = set()
    all_photos.update(photo_colors.keys())
    for stats in conversions_stats.values():
        all_photos.update(stats['photo_downloads'].keys())
    for meta in keyword_photos.values():
        all_photos.update(meta['photos'])

    logger.info(f"Total unique photos: {len(all_photos)}")

    # Step 2: For now, create placeholder style fingerprints
    # In full implementation, we'll use clustering algorithm
    # For Phase 2, we'll create styles based on top keywords

    # Group photos by top keywords
    top_keywords = sorted(
        conversions_stats.items(),
        key=lambda x: x[1]['total_downloads'],
        reverse=True
    )[:num_clusters]

    cursor = conn.cursor()

    for idx, (keyword, stats) in enumerate(top_keywords):
        style_id = f"style_{idx + 1}"
        style_name = keyword.replace('_', ' ').title()

        # Get photos for this keyword
        keyword_meta = keyword_photos.get(keyword, {})
        style_photos = keyword_meta.get('photos', [])

        if not style_photos:
            continue

        # Aggregate color distribution
        color_distribution = defaultdict(lambda: {'coverage_sum': 0, 'score_sum': 0, 'count': 0})

        for photo_id in style_photos[:1000]:  # Limit to 1000 photos per style
            colors = photo_colors.get(photo_id, [])
            for color in colors:
                hex_code = color['hex']
                color_distribution[hex_code]['coverage_sum'] += color['coverage']
                color_distribution[hex_code]['score_sum'] += color['score']
                color_distribution[hex_code]['count'] += 1

        # Calculate dominant colors
        dominant_colors = []
        for hex_code, stats_color in color_distribution.items():
            dominant_colors.append({
                'hex': hex_code,
                'avg_coverage': stats_color['coverage_sum'] / stats_color['count'] if stats_color['count'] > 0 else 0,
                'avg_score': stats_color['score_sum'] / stats_color['count'] if stats_color['count'] > 0 else 0,
                'frequency': stats_color['count'] / len(style_photos) if style_photos else 0
            })
        dominant_colors.sort(key=lambda x: x['frequency'], reverse=True)

        # Get keyword signatures
        keyword_signatures = []
        for kw, meta in keyword_photos.items():
            # Check if this keyword appears in style photos
            kw_photos = set(meta['photos'])
            style_photo_set = set(style_photos)
            overlap = len(kw_photos & style_photo_set)

            if overlap > 0:
                keyword_signatures.append({
                    'keyword': kw,
                    'avg_confidence': meta['avg_confidence'],
                    'frequency': overlap / len(style_photos) if style_photos else 0
                })
        keyword_signatures.sort(key=lambda x: x['frequency'], reverse=True)

        # Get top conversion photos
        top_conversion_photos = [
            photo_id for photo_id, _ in sorted(
                stats['photo_downloads'].items(),
                key=lambda x: x[1],
                reverse=True
            )[:50]
        ]

        # Insert style fingerprint
        cursor.execute("""
            INSERT INTO style_fingerprints
            (style_id, style_name, color_distribution, dominant_colors, keyword_signatures,
             conversion_keywords, top_conversion_photos, photo_count, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (style_id) DO UPDATE SET
                style_name = EXCLUDED.style_name,
                color_distribution = EXCLUDED.color_distribution,
                dominant_colors = EXCLUDED.dominant_colors,
                keyword_signatures = EXCLUDED.keyword_signatures,
                conversion_keywords = EXCLUDED.conversion_keywords,
                top_conversion_photos = EXCLUDED.top_conversion_photos,
                photo_count = EXCLUDED.photo_count,
                updated_at = NOW()
        """, (
            style_id,
            style_name,
            json.dumps(dict(color_distribution)),
            json.dumps(dominant_colors[:20]),  # Top 20 colors
            json.dumps(keyword_signatures[:30]),  # Top 30 keywords
            json.dumps({keyword: stats['total_downloads']}),
            top_conversion_photos,
            len(style_photos)
        ))

        # Create photo-style associations
        for photo_id in style_photos[:1000]:
            relevance_score = 1.0  # Will be calculated based on feature similarity in full implementation
            cursor.execute("""
                INSERT INTO photo_style_associations
                (photo_id, style_id, relevance_score, source)
                VALUES (%s, %s, %s, 'keyword')
                ON CONFLICT (photo_id, style_id) DO UPDATE SET
                    relevance_score = EXCLUDED.relevance_score,
                    source = EXCLUDED.source
            """, (photo_id, style_id, relevance_score))

    conn.commit()
    cursor.close()
    logger.info(f"Built {len(top_keywords)} style fingerprints")


def main():
    parser = argparse.ArgumentParser(description="Build style fingerprints from Dataset TSV files")
    parser.add_argument("--conversions", type=str, help="Path to conversions.tsv file")
    parser.add_argument("--keywords", type=str, help="Path to keywords.tsv file")
    parser.add_argument("--colors", type=str, help="Path to colors.tsv file")
    parser.add_argument("--photos", type=str, help="Path to photos.tsv file (optional)")
    parser.add_argument("--min-keyword-frequency", type=int, default=100, help="Minimum downloads for keyword to be included")
    parser.add_argument("--style-clusters", type=int, default=50, help="Number of style clusters to create")

    args = parser.parse_args()

    if not args.conversions or not args.keywords or not args.colors:
        parser.error("--conversions, --keywords, and --colors are required")

    # Connect to database
    conn = get_db_connection()
    ensure_tables_exist(conn)

    try:
        # Step 1: Parse conversions.tsv
        conversions_stats = parse_conversions_tsv(
            args.conversions,
            min_frequency=args.min_keyword_frequency
        )

        # Step 2: Get photo IDs from conversions
        all_photo_ids = set()
        for stats in conversions_stats.values():
            all_photo_ids.update(stats['photo_downloads'].keys())

        # Step 3: Parse keywords.tsv (filtered by conversion photos)
        keyword_photos = parse_keywords_for_style(
            args.keywords,
            photo_ids=list(all_photo_ids)
        )

        # Step 4: Parse colors.tsv (filtered by conversion photos)
        photo_colors = parse_colors_for_style(
            args.colors,
            photo_ids=list(all_photo_ids)
        )

        # Step 5: Build keyword-style mappings
        build_keyword_style_mappings(
            conversions_stats,
            keyword_photos,
            conn
        )

        # Step 6: Build style fingerprints
        build_style_fingerprints(
            conversions_stats,
            keyword_photos,
            photo_colors,
            num_clusters=args.style_clusters,
            conn=conn
        )

        logger.info("Style fingerprint building completed successfully!")

    except Exception as e:
        logger.error(f"Error building style fingerprints: {e}", exc_info=True)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()

