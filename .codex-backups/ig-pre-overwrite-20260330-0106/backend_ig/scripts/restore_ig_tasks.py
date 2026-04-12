import os
import json
import glob
import uuid
import re
import logging
from datetime import datetime
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL_CORE")
if not DATABASE_URL:
    logger.error("DATABASE_URL_CORE not set")
    exit(1)

engine = create_engine(DATABASE_URL)


def restore_tasks():
    search_path = "/app/data/sandboxes/**/ig_following_analysis_*.json"
    files = glob.glob(search_path, recursive=True)

    logger.info(f"Scanning {len(files)} analysis files for missing TASKS...")

    restored_count = 0
    restored_seeds = set()

    with engine.connect() as conn:
        for file_path in files:
            trans = conn.begin()
            try:
                project_id = None
                match = re.search(r"/project_repo/([^/]+)/", file_path)
                if match:
                    project_id = match.group(1)

                with open(file_path, "r") as f:
                    data = json.load(f)

                metadata = data.get("metadata", {})
                seed_handle = metadata.get("target_username") or metadata.get(
                    "target_seed"
                )
                workspace_id = metadata.get("workspace_id", "default")
                execution_id = (
                    metadata.get("execution_id")
                    or metadata.get("trace_id")
                    or str(uuid.uuid4())
                )
                analyzed_at = (
                    metadata.get("analyzed_at") or datetime.utcnow().isoformat()
                )

                if not seed_handle:
                    trans.rollback()
                    continue

                check_query = text("SELECT id FROM tasks WHERE execution_id = :eid")
                existing = conn.execute(check_query, {"eid": execution_id}).fetchone()

                if existing:
                    trans.rollback()
                    continue

                if project_id:
                    check_proj = text("SELECT id FROM projects WHERE id = :pid")
                    proj_exists = conn.execute(
                        check_proj, {"pid": project_id}
                    ).fetchone()
                    if not proj_exists:
                        logger.warning(
                            f"Project {project_id} not found, setting to None"
                        )
                        project_id = None

                task_id = str(uuid.uuid4())

                # Mock message_id
                message_id = str(uuid.uuid4())

                context = {
                    "metadata": metadata,
                    "users": [],
                    "summary": data.get("summary", {}),
                }

                params = {
                    "input": {
                        "target_username": seed_handle,
                        "workspace_id": workspace_id,
                        "project_id": project_id,
                    },
                    "playbook_code": "ig_analyze_following",
                }

                insert_query = text(
                    """
                    INSERT INTO tasks (
                        id, workspace_id, project_id, message_id, execution_id, pack_id,
                        task_type, status, params, result, execution_context,
                        created_at, started_at, completed_at
                    ) VALUES (
                        :id, :workspace_id, :project_id, :message_id, :execution_id, 'ig_analyze_following',
                        'playbook_execution', 'succeeded', :params, :result, :context,
                        :created_at, :created_at, :created_at
                    )
                """
                )

                conn.execute(
                    insert_query,
                    {
                        "id": task_id,
                        "workspace_id": workspace_id,
                        "project_id": project_id,
                        "message_id": message_id,
                        "execution_id": execution_id,
                        "params": json.dumps(params),
                        "result": json.dumps(
                            {
                                "status": "succeeded",
                                "playbook_code": "ig_analyze_following",
                            }
                        ),
                        "context": json.dumps(context),
                        "created_at": analyzed_at,
                    },
                )

                trans.commit()
                restored_seeds.add(seed_handle)
                restored_count += 1
                logger.info(
                    f"Restored Task for seed: {seed_handle} (ExecID: {execution_id})"
                )

            except Exception as e:
                trans.rollback()
                logger.error(f"Failed to process {file_path}: {e}")

    logger.info(f"Restoration Complete. Restored {restored_count} tasks.")
    logger.info(f"Seeds: {restored_seeds}")


if __name__ == "__main__":
    restore_tasks()
