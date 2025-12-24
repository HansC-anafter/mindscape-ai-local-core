"""
Template Engine for IG Post generation

Supports template loading, variable substitution, and multi-variant generation.
"""
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
import json

logger = logging.getLogger(__name__)


class IGTemplateEngine:
    """
    Template Engine for IG Post generation

    Supports:
    - Template loading from files
    - Variable substitution
    - Multi-variant generation (different tones, CTAs)
    """

    def __init__(self, templates_dir: Optional[str] = None):
        """
        Initialize Template Engine

        Args:
            templates_dir: Path to templates directory (default: built-in templates)
        """
        if templates_dir:
            self.templates_dir = Path(templates_dir)
        else:
            # Use built-in templates directory
            current_file = Path(__file__)
            self.templates_dir = current_file.parent / "templates"

        self.templates_dir.mkdir(parents=True, exist_ok=True)

    def load_template(
        self,
        template_type: str,
        style_tone: str = "friendly",
        purpose: str = "save"
    ) -> Dict[str, Any]:
        """
        Load template by type, style_tone, and purpose

        Args:
            template_type: Template type (carousel, reel, story)
            style_tone: Style tone (high_brand, friendly, coach, sponsored)
            purpose: Purpose (save, comment, dm, share)

        Returns:
            Template dictionary
        """
        template_file = self.templates_dir / f"{template_type}_{style_tone}_{purpose}.json"

        if template_file.exists():
            with open(template_file, "r", encoding="utf-8") as f:
                template = json.load(f)
            return template

        # Return default template if file doesn't exist
        return self._get_default_template(template_type, style_tone, purpose)

    def _get_default_template(
        self,
        template_type: str,
        style_tone: str,
        purpose: str
    ) -> Dict[str, Any]:
        """
        Get default template structure

        Args:
            template_type: Template type
            style_tone: Style tone
            purpose: Purpose

        Returns:
            Default template dictionary
        """
        return {
            "template_type": template_type,
            "style_tone": style_tone,
            "purpose": purpose,
            "structure": self._get_default_structure(template_type),
            "tone_guidelines": self._get_tone_guidelines(style_tone),
            "cta_templates": self._get_cta_templates(purpose)
        }

    def _get_default_structure(self, template_type: str) -> Dict[str, Any]:
        """Get default structure for template type"""
        structures = {
            "carousel": {
                "hook": "{{hook}}",
                "body": "{{body}}",
                "cta": "{{cta}}",
                "hashtags": "{{hashtags}}"
            },
            "reel": {
                "hook": "{{hook}}",
                "body": "{{body}}",
                "cta": "{{cta}}",
                "hashtags": "{{hashtags}}"
            },
            "story": {
                "text": "{{text}}",
                "cta": "{{cta}}"
            }
        }
        return structures.get(template_type, structures["carousel"])

    def _get_tone_guidelines(self, style_tone: str) -> Dict[str, Any]:
        """Get tone guidelines for style_tone"""
        guidelines = {
            "high_brand": {
                "tone": "professional, polished, brand-focused",
                "emoji_usage": "minimal, strategic",
                "language": "formal, refined"
            },
            "friendly": {
                "tone": "warm, approachable, conversational",
                "emoji_usage": "moderate, friendly",
                "language": "casual, relatable"
            },
            "coach": {
                "tone": "encouraging, educational, supportive",
                "emoji_usage": "motivational, positive",
                "language": "inspiring, actionable"
            },
            "sponsored": {
                "tone": "professional, clear, value-focused",
                "emoji_usage": "minimal, professional",
                "language": "clear, benefit-oriented"
            }
        }
        return guidelines.get(style_tone, guidelines["friendly"])

    def _get_cta_templates(self, purpose: str) -> List[str]:
        """Get CTA templates for purpose"""
        ctas = {
            "save": [
                "💾 儲存這篇貼文，隨時回來看！",
                "📌 收藏起來，別錯過！",
                "🔖 存起來，之後慢慢看"
            ],
            "comment": [
                "💬 在留言區分享你的想法！",
                "👇 留言告訴我你的經驗",
                "💭 你覺得呢？留言聊聊"
            ],
            "dm": [
                "📩 私訊我了解更多",
                "💌 想了解更多？DM 我",
                "🔗 私訊連結在個人檔案"
            ],
            "share": [
                "📤 分享給需要的朋友",
                "🔄 轉發給更多人看到",
                "👥 標記你的朋友一起看"
            ]
        }
        return ctas.get(purpose, ctas["save"])

    def generate_posts(
        self,
        template: Dict[str, Any],
        source_content: str,
        generate_variants: bool = True
    ) -> Dict[str, Any]:
        """
        Generate posts from template and source content

        Args:
            template: Template dictionary
            source_content: Source content to transform
            generate_variants: Whether to generate multiple variants

        Returns:
            {
                "generated_posts": List[Dict],
                "template_applied": Dict
            }
        """
        structure = template.get("structure", {})
        tone_guidelines = template.get("tone_guidelines", {})
        cta_templates = template.get("cta_templates", [])

        generated_posts = []

        if generate_variants:
            # Generate multiple variants with different CTAs
            for cta in cta_templates:
                post = self._apply_template(
                    structure=structure,
                    source_content=source_content,
                    tone_guidelines=tone_guidelines,
                    cta=cta
                )
                generated_posts.append(post)
        else:
            # Generate single post with first CTA
            post = self._apply_template(
                structure=structure,
                source_content=source_content,
                tone_guidelines=tone_guidelines,
                cta=cta_templates[0] if cta_templates else ""
            )
            generated_posts.append(post)

        return {
            "generated_posts": generated_posts,
            "template_applied": {
                "template_type": template.get("template_type"),
                "style_tone": template.get("style_tone"),
                "purpose": template.get("purpose"),
                "variant_count": len(generated_posts)
            }
        }

    def _apply_template(
        self,
        structure: Dict[str, Any],
        source_content: str,
        tone_guidelines: Dict[str, Any],
        cta: str
    ) -> Dict[str, Any]:
        """
        Apply template to source content

        Args:
            structure: Template structure
            source_content: Source content
            tone_guidelines: Tone guidelines
            cta: CTA text

        Returns:
            Generated post dictionary
        """
        # Simple template application (will be enhanced with LLM in future)
        # For now, return structured post with placeholders

        post_text = ""

        if "hook" in structure:
            post_text += f"{structure['hook']}\n\n"

        if "body" in structure:
            post_text += f"{source_content[:200]}...\n\n"

        if "cta" in structure:
            post_text += f"{cta}\n\n"

        if "hashtags" in structure:
            post_text += f"{structure['hashtags']}"

        return {
            "text": post_text.strip(),
            "length": len(post_text),
            "has_emoji": "💾" in post_text or "💬" in post_text or "📩" in post_text,
            "has_cta": bool(cta),
            "tone": tone_guidelines.get("tone", "friendly")
        }





