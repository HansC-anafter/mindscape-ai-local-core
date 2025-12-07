"""
Fix current_step_index for existing executions

This script updates current_step_index in execution_context based on
the latest step event for each execution.
"""

import sys
import os
import json
import logging
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.models.mindscape import EventType

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fix_current_step_index():
    """Fix current_step_index for all running executions"""
    store = MindscapeStore()
    tasks_store = TasksStore(db_path=store.db_path)
    
    # Get all running executions
    import sqlite3
    conn = sqlite3.connect(store.db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, execution_id, execution_context, status
        FROM tasks
        WHERE execution_id IS NOT NULL 
          AND execution_id != ''
          AND status = 'running'
    ''')
    
    tasks = cursor.fetchall()
    logger.info(f"Found {len(tasks)} running executions to check")
    
    fixed_count = 0
    skipped_count = 0
    
    for task_id, exec_id, exec_context_json, status in tasks:
        try:
            exec_context = json.loads(exec_context_json) if exec_context_json else {}
            current_step_index = exec_context.get('current_step_index', 0)
            
            # Query step events for this execution
            cursor.execute('''
                SELECT payload
                FROM mind_events
                WHERE event_type = 'playbook_step'
                AND payload LIKE ?
                ORDER BY timestamp DESC
            ''', (f'%{exec_id}%',))
            
            step_events = cursor.fetchall()
            if not step_events:
                logger.debug(f"No step events found for {exec_id[:16]}...")
                skipped_count += 1
                continue
            
            # Get latest step index
            latest_payload = json.loads(step_events[0][0]) if step_events[0][0] else {}
            latest_step_index = latest_payload.get('step_index', 0)  # 1-based
            
            # Convert to 0-based (current_step_index represents completed step)
            should_be_index = max(0, latest_step_index - 1)
            
            if current_step_index == should_be_index:
                logger.debug(f"{exec_id[:16]}...: Already correct ({current_step_index})")
                skipped_count += 1
                continue
            
            # Update execution_context
            exec_context['current_step_index'] = should_be_index
            tasks_store.update_task(task_id, execution_context=exec_context)
            
            logger.info(f"Fixed {exec_id[:16]}...: {current_step_index} -> {should_be_index} (latest step: {latest_step_index})")
            fixed_count += 1
            
        except Exception as e:
            logger.error(f"Failed to fix {exec_id[:16]}...: {e}", exc_info=True)
    
    conn.close()
    
    logger.info(f"Fix completed: {fixed_count} fixed, {skipped_count} skipped")
    return fixed_count, skipped_count


if __name__ == "__main__":
    fixed, skipped = fix_current_step_index()
    print(f"\n✅ Fixed {fixed} executions, skipped {skipped} executions")

