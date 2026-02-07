"""
API endpoints for Unsplash Dataset fingerprints management.
"""
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from app.database.config import get_core_postgres_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/unsplash/fingerprints", tags=["unsplash"])

# Global state for tracking setup progress
_setup_progress: Dict[str, Any] = {
    "status": "idle",
    "message": "",
    "error": None,
}


class SetupRequest(BaseModel):
    """Request model for setting up fingerprints."""
    auto_download: bool = True
    hf_token: Optional[str] = None


def get_project_root() -> Path:
    """Get the project root directory."""
    current_file = Path(__file__).resolve()
    backend_dir = current_file.parent.parent.parent.parent
    return backend_dir.parent


def get_db_connection():
    """Get PostgreSQL database connection for status check."""
    try:
        import psycopg2

        postgres_config = get_core_postgres_config()

        return psycopg2.connect(**postgres_config)
    except ImportError:
        logger.error("psycopg2 not installed")
        return None
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        return None


def run_setup_script(project_root: Path, hf_token: Optional[str] = None):
    """Run the setup script in background."""
    global _setup_progress

    try:
        _setup_progress["status"] = "downloading"
        _setup_progress["message"] = "Downloading Dataset from Hugging Face..."
        _setup_progress["error"] = None

        # Prepare environment
        env = os.environ.copy()
        if hf_token:
            env["HF_TOKEN"] = hf_token

        # Run the setup script
        script_path = project_root / "scripts" / "init_unsplash_fingerprints.py"

        if not script_path.exists():
            _setup_progress["status"] = "failed"
            _setup_progress["error"] = f"Setup script not found at {script_path}"
            return

        cmd = [
            sys.executable,
            str(script_path),
            "--auto-download",
        ]

        logger.info(f"Running setup script: {' '.join(cmd)}")

        process = subprocess.Popen(
            cmd,
            cwd=str(project_root),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # Combine stderr into stdout
            text=True,
            bufsize=1,  # Line buffered
        )

        # Update progress
        _setup_progress["status"] = "processing"
        _setup_progress["message"] = "Processing Dataset files..."

        # Read output line by line to update progress in real-time
        output_lines = []
        for line in process.stdout:
            line = line.strip()
            if line:
                output_lines.append(line)
                logger.info(f"Setup output: {line}")

                # Update progress message based on output
                if "Downloading" in line or "download" in line.lower():
                    _setup_progress["message"] = "Downloading Dataset from Hugging Face..."
                elif "Building" in line or "building" in line.lower():
                    _setup_progress["message"] = "Building fingerprints database..."
                elif "Processed" in line or "processed" in line.lower():
                    _setup_progress["message"] = line  # Show progress line
                elif "Completed" in line or "completed" in line.lower():
                    _setup_progress["message"] = line

        # Wait for completion
        process.wait()

        if process.returncode == 0:
            _setup_progress["status"] = "completed"
            _setup_progress["message"] = "Fingerprints database setup completed successfully!"
            logger.info("Setup completed successfully")
        else:
            _setup_progress["status"] = "failed"
            error_msg = "\n".join(output_lines[-10:]) if output_lines else "Setup failed with unknown error"
            _setup_progress["error"] = error_msg
            logger.error(f"Setup failed: {error_msg}")

    except Exception as e:
        _setup_progress["status"] = "failed"
        _setup_progress["error"] = str(e)
        logger.error(f"Error running setup script: {e}", exc_info=True)


@router.get("/status")
async def get_fingerprint_status():
    """Get the current status of the fingerprints database."""
    conn = get_db_connection()
    if not conn:
        return {
            "has_data": False,
            "total_count": 0,
            "error": "Database connection failed",
        }

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) as total_count, MAX(updated_at) as last_updated
            FROM unsplash_photo_fingerprints
        """)
        result = cursor.fetchone()

        total_count = result[0] if result else 0
        last_updated = result[1] if result and result[1] else None

        cursor.close()
        conn.close()

        return {
            "has_data": total_count > 0,
            "total_count": total_count,
            "last_updated": last_updated.isoformat() if last_updated else None,
        }
    except Exception as e:
        logger.error(f"Error querying fingerprint status: {e}", exc_info=True)
        try:
            conn.close()
        except:
            pass

        # Table might not exist yet
        return {
            "has_data": False,
            "total_count": 0,
            "error": "Table does not exist or query failed",
        }


@router.post("/setup")
async def setup_fingerprints(
    request: SetupRequest,
    background_tasks: BackgroundTasks,
):
    """Start the fingerprints database setup process."""
    global _setup_progress

    # Check if already running
    if _setup_progress["status"] in ["downloading", "processing"]:
        raise HTTPException(
            status_code=409,
            detail="Setup is already in progress"
        )

    project_root = get_project_root()

    # Reset progress
    _setup_progress = {
        "status": "starting",
        "message": "Initializing setup...",
        "error": None,
    }

    # Start background task
    background_tasks.add_task(
        run_setup_script,
        project_root,
        request.hf_token or os.getenv("HF_TOKEN"),
    )

    return {
        "status": "started",
        "message": "Setup process started. Use /progress endpoint to check status.",
    }


@router.get("/progress")
async def get_setup_progress():
    """Get the current progress of the setup process."""
    return _setup_progress


@router.post("/reset")
async def reset_progress():
    """Reset the setup progress (for testing/debugging)."""
    global _setup_progress
    _setup_progress = {
        "status": "idle",
        "message": "",
        "error": None,
    }
    return {"status": "reset"}
