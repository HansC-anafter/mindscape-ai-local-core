"""
Environment variable management endpoints
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any, Optional
from pydantic import BaseModel
import re
from pathlib import Path

router = APIRouter()


class EnvVarUpdateRequest(BaseModel):
    """Request model for updating environment variable in .env file"""
    key: str
    value: str
    comment: Optional[str] = None


@router.put("/env", response_model=Dict[str, Any])
async def update_env_variable(request: EnvVarUpdateRequest):
    """
    Update environment variable in .env file

    This endpoint updates or adds an environment variable in the .env file.
    Changes require service restart to take effect.
    """
    try:
        # Find .env file (in project root, one level up from backend)
        project_root = Path(__file__).parent.parent.parent.parent.parent
        env_file = project_root / ".env"

        # Read existing .env file
        env_content = ""
        if env_file.exists():
            env_content = env_file.read_text(encoding="utf-8")
        else:
            # Create new .env file from example if it doesn't exist
            env_example = project_root / ".env.example"
            if env_example.exists():
                env_content = env_example.read_text(encoding="utf-8")

        # Update or add the variable
        lines = env_content.split("\n")
        updated = False
        new_lines = []

        for line in lines:
            # Skip comments and empty lines when checking
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                new_lines.append(line)
                continue

            # Check if this line contains the key we're updating
            if re.match(rf"^{re.escape(request.key)}\s*=", stripped):
                # Update existing line
                comment_part = ""
                if "#" in line:
                    comment_part = " # " + line.split("#", 1)[1].strip()
                new_lines.append(f"{request.key}={request.value}{comment_part}")
                updated = True
            else:
                new_lines.append(line)

        # If not found, add it at the end
        if not updated:
            if request.comment:
                new_lines.append(f"# {request.comment}")
            new_lines.append(f"{request.key}={request.value}")

        # Write back to file
        env_file.parent.mkdir(parents=True, exist_ok=True)
        env_file.write_text("\n".join(new_lines), encoding="utf-8")

        return {
            "success": True,
            "message": f"Environment variable {request.key} updated in .env file",
            "requires_restart": True,
            "key": request.key,
            "value": request.value
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update .env file: {str(e)}"
        )


@router.get("/env/{key}", response_model=Dict[str, Any])
async def get_env_variable(key: str):
    """
    Get environment variable value from .env file

    Returns the value from .env file (not from current environment).
    """
    try:
        project_root = Path(__file__).parent.parent.parent.parent.parent
        env_file = project_root / ".env"

        if not env_file.exists():
            return {
                "key": key,
                "value": None,
                "exists": False
            }

        env_content = env_file.read_text(encoding="utf-8")
        lines = env_content.split("\n")

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                continue

            match = re.match(rf"^{re.escape(key)}\s*=\s*(.+?)(?:\s*#.*)?$", stripped)
            if match:
                value = match.group(1).strip().strip('"').strip("'")
                return {
                    "key": key,
                    "value": value,
                    "exists": True
                }

        return {
            "key": key,
            "value": None,
            "exists": False
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read .env file: {str(e)}"
        )

