import asyncio
import logging
import uuid
import httpx
from sqlalchemy import select
from app.db.session import SessionLocal
from app.db.models.playbooks import PlaybookExecution

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def run_in_docker():
    workspace_id = "bac7ce63-e768-454d-96f3-3a00e8e1df69"
    playbook_code = "ig_analyze_following"
    execution_id = uuid.uuid4()
    
    async with SessionLocal() as db:
        execution = PlaybookExecution(
            id=execution_id,
            playbook_id=playbook_code,
            workspace_id=workspace_id,
            status="pending",
            inputs={"text": "@dearruigallery only visit page"}
        )
        db.add(execution)
        await db.commit()
        logger.info(f"Execution DB record created: {execution_id}")
        
    async with httpx.AsyncClient() as client:
        try:
            url = f"http://localhost:8200/api/v1/playbooks/{playbook_code}/executions/{execution_id}/start"
            logger.info(f"Triggering start API: {url}")
            resp = await client.post(url)
            logger.info(f"Start Triggered: {resp.status_code} - {resp.text}")
        except Exception as e:
            logger.error(f"API Error: {e}")

if __name__ == "__main__":
    asyncio.run(run_in_docker())
