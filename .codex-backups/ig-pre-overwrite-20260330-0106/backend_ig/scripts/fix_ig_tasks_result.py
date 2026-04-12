import os
import json
import logging
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL_CORE")
if not DATABASE_URL:
    logger.error("DATABASE_URL_CORE not set")
    exit(1)

engine = create_engine(DATABASE_URL)


def fix_tasks():
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            # Find tasks with NULL result or empty params
            query = text(
                """
                SELECT id, execution_context, params
                FROM tasks
                WHERE pack_id = 'ig_analyze_following'
                AND status = 'succeeded'
                AND (result IS NULL OR params::text = '{}')
            """
            )
            result = conn.execute(query)
            tasks = result.fetchall()

            logger.info(f"Found {len(tasks)} tasks to fix...")

            fixed_count = 0
            for row in tasks:
                task_id = row[0]
                context = row[1]
                params = row[2]

                # Extract seed from context inputs
                seed = None
                workspace_id = "default"
                inputs = {}

                if isinstance(context, dict):
                    inputs = context.get("inputs", {})
                    seed = inputs.get("target_username") or inputs.get("target_seed")
                    workspace_id = inputs.get("workspace_id") or "default"

                    if not seed:
                        # Fallback to metadata in outputs?
                        meta = context.get("outputs", {}).get("metadata", {})
                        seed = meta.get("target_username")

                if not seed:
                    logger.warning(
                        f"Skipping task {task_id}: Could not find seed in inputs or outputs"
                    )
                    continue

                # Construct updates
                new_result = json.dumps(
                    {"status": "succeeded", "playbook_code": "ig_analyze_following"}
                )

                # If params is empty, try to populate it
                if not params or params == {}:
                    new_params = json.dumps(
                        {"input": inputs, "playbook_code": "ig_analyze_following"}
                    )
                else:
                    new_params = json.dumps(params)

                update_query = text(
                    """
                    UPDATE tasks
                    SET result = :result, params = :params
                    WHERE id = :id
                """
                )

                conn.execute(
                    update_query,
                    {"result": new_result, "params": new_params, "id": task_id},
                )
                fixed_count += 1

            trans.commit()
            logger.info(f"Fixed {fixed_count} tasks.")

        except Exception as e:
            trans.rollback()
            logger.error(f"Failed to fix tasks: {e}")


if __name__ == "__main__":
    fix_tasks()
