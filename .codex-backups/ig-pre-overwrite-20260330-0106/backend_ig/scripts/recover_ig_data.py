import os
import json
import glob
import uuid
import logging
from datetime import datetime
from sqlalchemy import create_engine, text

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database connection
DATABASE_URL = os.environ.get("DATABASE_URL_CORE")
if not DATABASE_URL:
    logger.error("DATABASE_URL_CORE not set")
    exit(1)

engine = create_engine(DATABASE_URL)


def recover_data():
    # Find all analysis files
    search_path = "/app/data/sandboxes/**/ig_following_analysis_*.json"
    files = glob.glob(search_path, recursive=True)

    logger.info(f"Found {len(files)} analysis files")

    total_seeds = set()
    total_accounts = 0

    # Use connection context
    with engine.connect() as conn:
        for file_path in files:
            # Begin transaction for this file
            trans = conn.begin()
            try:
                with open(file_path, "r") as f:
                    data = json.load(f)

                metadata = data.get("metadata", {})
                accounts = data.get("accounts", [])

                seed_handle = metadata.get("target_username")
                workspace_id = metadata.get("workspace_id", "default")

                if not seed_handle:
                    logger.warning(f"Skipping {file_path}: No target_username")
                    trans.commit()  # Nothing changed
                    continue

                total_seeds.add(seed_handle)

                file_account_count = 0

                # Check if accounts list is empty
                if not accounts:
                    trans.commit()
                    continue

                for acc in accounts:
                    handle = acc.get("username")
                    if not handle:
                        continue

                    record_id = str(uuid.uuid4())

                    params = {
                        "id": record_id,
                        "workspace_id": workspace_id,
                        "seed": seed_handle,
                        "source_handle": seed_handle,
                        "source_profile_ref": None,
                        "handle": handle,
                        "name": acc.get("display_name"),
                        "is_verified": acc.get("is_verified", False),
                        "follower_count": None,
                        "following_count": None,
                        "post_count": None,
                        "bio": acc.get("bio"),
                        "external_url": acc.get("account_link"),
                        "profile_picture_url": acc.get("avatar_url"),
                        "category": None,
                        "tags_json": "[]",
                        "captured_at": metadata.get("analyzed_at")
                        or datetime.utcnow().isoformat(),
                        "execution_id": None,
                        "trace_id": metadata.get("trace_id"),
                        "artifact_id": None,
                        "schema_version": "1.0",
                        "seed_version": "1.0",
                        "capture_method": "legacy_recovery",
                        "run_mode": "recovery",
                    }

                    query = text(
                        """
                        INSERT INTO ig_accounts_flat (
                            id, workspace_id, seed, source_handle, source_profile_ref,
                            handle, name, is_verified, follower_count, following_count,
                            post_count, bio, external_url, profile_picture_url, category,
                            tags_json, captured_at, execution_id, trace_id, artifact_id,
                            schema_version, seed_version, capture_method, run_mode
                        ) VALUES (
                            :id, :workspace_id, :seed, :source_handle, :source_profile_ref,
                            :handle, :name, :is_verified, :follower_count, :following_count,
                            :post_count, :bio, :external_url, :profile_picture_url, :category,
                            :tags_json, :captured_at, :execution_id, :trace_id, :artifact_id,
                            :schema_version, :seed_version, :capture_method, :run_mode
                        )
                        ON CONFLICT DO NOTHING
                    """
                    )

                    conn.execute(query, params)
                    file_account_count += 1

                # Insert Seed Record
                seed_id = str(uuid.uuid4())
                seed_params = {
                    "id": seed_id,
                    "workspace_id": workspace_id,
                    "seed": seed_handle,  # Self-reference
                    "source_handle": None,
                    "source_profile_ref": None,
                    "handle": seed_handle,
                    "name": seed_handle,  # Fallback
                    "is_verified": False,
                    "follower_count": None,
                    "following_count": None,
                    "post_count": None,
                    "bio": "Recovered Seed",
                    "external_url": f"https://www.instagram.com/{seed_handle}/",
                    "profile_picture_url": None,
                    "category": "Seed",
                    "tags_json": '["seed"]',
                    "captured_at": datetime.utcnow().isoformat(),
                    "execution_id": None,
                    "trace_id": None,
                    "artifact_id": None,
                    "schema_version": "1.0",
                    "seed_version": "1.0",
                    "capture_method": "legacy_recovery",
                    "run_mode": "recovery",
                }

                conn.execute(query, seed_params)

                # Commit explicitly per file
                trans.commit()
                total_accounts += file_account_count

            except Exception as e:
                # Rollback only this transaction
                trans.rollback()
                logger.error(f"Failed to process {file_path}: {e}")

    logger.info(f"Recovery Complete.")
    logger.info(f"Unique Seeds Found: {len(total_seeds)}")
    logger.info(f"Seeds: {total_seeds}")
    logger.info(f"Total Accounts Inserted: {total_accounts}")


if __name__ == "__main__":
    recover_data()
