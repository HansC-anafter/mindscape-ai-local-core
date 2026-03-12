"""
Agent Skills API Routes

Lightweight endpoint that scans .agent/skills/ directories and
installed capability SKILL.md files for the Skills page UI.
"""

import logging
import os
import re
import yaml
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/skills", tags=["skills"])


class SkillCard(BaseModel):
    """Skill card data for the Skills page UI"""

    id: str
    name: str
    description: str
    source: str  # "agent" or "capability"
    source_label: str
    file_count: int
    has_scripts: bool
    has_examples: bool
    has_resources: bool
    file_path: str
    last_modified: Optional[str] = None


def _scan_agent_skills(base_dir: Path) -> List[SkillCard]:
    """Scan .agent/skills/ for SKILL.md files"""
    skills_dir = base_dir / ".agent" / "skills"
    if not skills_dir.exists():
        return []

    results = []
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue

        try:
            card = _parse_skill_file(
                skill_md, source="agent", source_label="Agent Skill"
            )
            if card:
                results.append(card)
        except Exception as e:
            logger.warning(f"Failed to parse agent skill {skill_dir.name}: {e}")

    return results


def _scan_capability_skills(base_dir: Path) -> List[SkillCard]:
    """Scan installed capabilities for SKILL.md files"""
    caps_dir = base_dir / "backend" / "app" / "capabilities"
    if not caps_dir.exists():
        return []

    results = []
    for cap_dir in sorted(caps_dir.iterdir()):
        if not cap_dir.is_dir():
            continue
        skill_md = cap_dir / "SKILL.md"
        if not skill_md.exists():
            continue

        try:
            card = _parse_skill_file(
                skill_md, source="capability", source_label="Capability Pack"
            )
            if card:
                results.append(card)
        except Exception as e:
            logger.warning(f"Failed to parse capability skill {cap_dir.name}: {e}")

    return results


def _parse_skill_file(
    skill_md: Path, source: str, source_label: str
) -> Optional[SkillCard]:
    """Parse a SKILL.md file into a SkillCard"""
    content = skill_md.read_text(encoding="utf-8")
    skill_dir = skill_md.parent
    dir_name = skill_dir.name

    # Parse YAML frontmatter
    name = dir_name
    description = ""
    fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if fm_match:
        try:
            fm = yaml.safe_load(fm_match.group(1))
            if isinstance(fm, dict):
                name = fm.get("name", dir_name)
                description = fm.get("description", "")
        except yaml.YAMLError:
            pass

    # Fallback: extract from first heading + blockquote
    if not description:
        desc_match = re.search(r"^>\s+(.+)$", content, re.MULTILINE)
        if desc_match:
            description = desc_match.group(1).strip()

    # Count files in skill directory
    file_count = sum(1 for _ in skill_dir.rglob("*") if _.is_file())

    # Check for subdirectories
    has_scripts = (skill_dir / "scripts").is_dir()
    has_examples = (skill_dir / "examples").is_dir()
    has_resources = (skill_dir / "resources").is_dir()

    # Last modified
    stat = skill_md.stat()
    last_modified = datetime.fromtimestamp(stat.st_mtime).isoformat()

    return SkillCard(
        id=dir_name,
        name=name,
        description=description,
        source=source,
        source_label=source_label,
        file_count=file_count,
        has_scripts=has_scripts,
        has_examples=has_examples,
        has_resources=has_resources,
        file_path=str(skill_dir),
        last_modified=last_modified,
    )


def _get_project_root() -> Path:
    """Resolve the project root directory"""
    # In Docker: /app is the project root
    if Path("/app/.agent").exists():
        return Path("/app")
    # Local development fallback
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / ".agent").exists():
            return parent
    return Path("/app")


@router.get("/", response_model=List[SkillCard])
async def list_skills():
    """
    List all available skills from agent skills and installed capability packs.
    Scans .agent/skills/ and backend/app/capabilities/*/SKILL.md.
    """
    try:
        root = _get_project_root()
        agent_skills = _scan_agent_skills(root)
        capability_skills = _scan_capability_skills(root)
        return agent_skills + capability_skills
    except Exception as e:
        logger.error(f"Failed to list skills: {e}")
        raise HTTPException(status_code=500, detail=str(e))
