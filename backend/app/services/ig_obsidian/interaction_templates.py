"""
Interaction Templates System for IG Post

Manages interaction templates including common comment replies,
DM scripts, and tone switching for customer engagement.
"""
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import json

logger = logging.getLogger(__name__)


class InteractionTemplates:
    """
    Manages interaction templates for IG engagement

    Supports:
    - Common comment reply library
    - DM sales scripts
    - Tone switching
    - Template categorization
    """

    def __init__(self, vault_path: str):
        """
        Initialize Interaction Templates System

        Args:
            vault_path: Path to Obsidian Vault
        """
        self.vault_path = Path(vault_path).expanduser().resolve()
        self.templates_dir = self.vault_path / ".obsidian" / "interaction_templates"
        self.templates_index_path = self.templates_dir / "templates_index.json"
        self.templates_dir.mkdir(parents=True, exist_ok=True)

    def create_template(
        self,
        template_id: str,
        template_type: str,
        content: str,
        tone: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        variables: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Create a new interaction template

        Args:
            template_id: Unique template identifier
            template_type: Type of template (e.g., "comment_reply", "dm_script", "story_reply")
            content: Template content (supports variable placeholders like {{name}})
            tone: Tone of the template (e.g., "friendly", "professional", "casual")
            category: Category (e.g., "greeting", "product_inquiry", "complaint")
            tags: List of tags for categorization
            variables: List of variable names used in template

        Returns:
            Template information dictionary
        """
        templates_index = self._load_templates_index()

        if template_id in templates_index:
            raise ValueError(f"Template {template_id} already exists")

        template = {
            "template_id": template_id,
            "template_type": template_type,
            "content": content,
            "tone": tone or "friendly",
            "category": category,
            "tags": tags or [],
            "variables": variables or [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "usage_count": 0
        }

        templates_index[template_id] = template
        self._save_templates_index(templates_index)

        return template

    def get_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        """
        Get template by ID

        Args:
            template_id: Template identifier

        Returns:
            Template information dictionary or None if not found
        """
        templates_index = self._load_templates_index()
        return templates_index.get(template_id)

    def list_templates(
        self,
        template_type: Optional[str] = None,
        tone: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        List templates with optional filters

        Args:
            template_type: Filter by template type
            tone: Filter by tone
            category: Filter by category
            tags: Filter by tags (templates must have all specified tags)

        Returns:
            List of matching templates
        """
        templates_index = self._load_templates_index()
        templates = list(templates_index.values())

        if template_type:
            templates = [t for t in templates if t.get("template_type") == template_type]

        if tone:
            templates = [t for t in templates if t.get("tone") == tone]

        if category:
            templates = [t for t in templates if t.get("category") == category]

        if tags:
            templates = [
                t for t in templates
                if all(tag in t.get("tags", []) for tag in tags)
            ]

        return templates

    def render_template(
        self,
        template_id: str,
        variables: Dict[str, str]
    ) -> str:
        """
        Render template with provided variables

        Args:
            template_id: Template identifier
            variables: Dictionary of variable values (e.g., {"name": "John", "product": "Coffee"})

        Returns:
            Rendered template content
        """
        template = self.get_template(template_id)

        if not template:
            raise ValueError(f"Template {template_id} not found")

        content = template["content"]

        for var_name, var_value in variables.items():
            placeholder = f"{{{{{var_name}}}}}"
            content = content.replace(placeholder, str(var_value))

        self._increment_usage_count(template_id)

        return content

    def suggest_template(
        self,
        context: str,
        template_type: Optional[str] = None,
        tone: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Suggest a template based on context

        Args:
            context: Context description or keywords
            template_type: Preferred template type (optional)
            tone: Preferred tone (optional)

        Returns:
            Suggested template or None
        """
        templates = self.list_templates(
            template_type=template_type,
            tone=tone
        )

        if not templates:
            return None

        context_lower = context.lower()

        best_match = None
        best_score = 0

        for template in templates:
            score = 0

            category = template.get("category", "").lower()
            tags = [tag.lower() for tag in template.get("tags", [])]
            content = template.get("content", "").lower()

            if category and category in context_lower:
                score += 3

            for tag in tags:
                if tag in context_lower:
                    score += 2

            if any(word in content for word in context_lower.split()):
                score += 1

            if score > best_score:
                best_score = score
                best_match = template

        return best_match

    def switch_tone(
        self,
        template_id: str,
        new_tone: str
    ) -> Dict[str, Any]:
        """
        Switch template tone (creates a variant)

        Args:
            template_id: Original template identifier
            new_tone: New tone to apply

        Returns:
            New template variant with updated tone
        """
        original_template = self.get_template(template_id)

        if not original_template:
            raise ValueError(f"Template {template_id} not found")

        new_template_id = f"{template_id}_{new_tone}"

        new_template = original_template.copy()
        new_template["template_id"] = new_template_id
        new_template["tone"] = new_tone
        new_template["created_at"] = datetime.now().isoformat()
        new_template["updated_at"] = datetime.now().isoformat()
        new_template["usage_count"] = 0
        new_template["based_on"] = template_id

        templates_index = self._load_templates_index()
        templates_index[new_template_id] = new_template
        self._save_templates_index(templates_index)

        return new_template

    def update_template(
        self,
        template_id: str,
        updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update template

        Args:
            template_id: Template identifier
            updates: Dictionary of fields to update

        Returns:
            Updated template
        """
        templates_index = self._load_templates_index()

        if template_id not in templates_index:
            raise ValueError(f"Template {template_id} not found")

        template = templates_index[template_id]

        allowed_updates = ["content", "tone", "category", "tags", "variables"]
        for key, value in updates.items():
            if key in allowed_updates:
                template[key] = value

        template["updated_at"] = datetime.now().isoformat()

        templates_index[template_id] = template
        self._save_templates_index(templates_index)

        return template

    def _increment_usage_count(self, template_id: str) -> None:
        """Increment usage count for a template"""
        templates_index = self._load_templates_index()

        if template_id in templates_index:
            templates_index[template_id]["usage_count"] = (
                templates_index[template_id].get("usage_count", 0) + 1
            )
            self._save_templates_index(templates_index)

    def _load_templates_index(self) -> Dict[str, Any]:
        """Load templates index from file"""
        if self.templates_index_path.exists():
            try:
                with open(self.templates_index_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load templates index: {e}")

        return {}

    def _save_templates_index(self, templates_index: Dict[str, Any]) -> None:
        """Save templates index to file"""
        try:
            with open(self.templates_index_path, "w", encoding="utf-8") as f:
                json.dump(templates_index, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save templates index: {e}")
            raise

