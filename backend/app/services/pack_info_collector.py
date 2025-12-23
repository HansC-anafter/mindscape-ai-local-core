"""
Pack Info Collector

Collects complete information about installed packs from database and registry.
Used for generating dynamic pack lists in LLM prompts.
"""

import logging
import sqlite3
import json
import os
from typing import List, Dict, Any, Optional
from pathlib import Path

from backend.app.capabilities.registry import get_registry

logger = logging.getLogger(__name__)


class PackInfoCollector:
    """Collects pack information from database and registry for LLM prompt generation"""

    def __init__(self, db_path: str):
        """
        Initialize PackInfoCollector

        Args:
            db_path: Path to SQLite database containing installed_packs table
        """
        self.db_path = db_path

    def get_all_installed_packs(self, workspace_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all installed packs with complete information

        Args:
            workspace_id: Optional workspace ID for workspace-specific packs

        Returns:
            List of pack dictionaries containing pack_id, manifest, metadata, etc.
        """
        installed_packs = []

        if not self.db_path or not os.path.exists(self.db_path):
            logger.warning(f"Database not found at {self.db_path}")
            return installed_packs

        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            try:
                cursor = conn.cursor()
                cursor.execute('SELECT pack_id, metadata FROM installed_packs')
                rows = cursor.fetchall()

                registry = get_registry()

                for row in rows:
                    pack_id = row['pack_id']
                    metadata_str = row['metadata']
                    metadata = {}
                    if metadata_str:
                        try:
                            metadata = json.loads(metadata_str)
                        except json.JSONDecodeError:
                            logger.warning(f"Failed to parse metadata for pack {pack_id}")

                    capability_info = registry.capabilities.get(pack_id)
                    if not capability_info:
                        logger.debug(f"Pack {pack_id} not found in registry, skipping")
                        continue

                    manifest = capability_info.get('manifest', {})
                    installed_packs.append({
                        'pack_id': pack_id,
                        'display_name': manifest.get('display_name', pack_id),
                        'description': manifest.get('description', ''),
                        'side_effect_level': metadata.get('side_effect_level') or manifest.get('side_effect_level', 'readonly'),
                        'manifest': manifest,
                        'metadata': metadata
                    })

            finally:
                conn.close()

        except Exception as e:
            logger.error(f"Failed to get installed packs: {e}", exc_info=True)

        logger.info(f"Found {len(installed_packs)} installed packs")
        return installed_packs

    def build_pack_description_list(self, packs: List[Dict[str, Any]]) -> str:
        """
        Build formatted pack description list for LLM prompt

        Args:
            packs: List of pack dictionaries from get_all_installed_packs()

        Returns:
            Formatted string listing all packs with descriptions and side_effect_level
        """
        if not packs:
            return "No packs available"

        descriptions = []
        for pack in packs:
            pack_id = pack.get('pack_id', '')
            display_name = pack.get('display_name', pack_id)
            description = pack.get('description', '')
            side_effect = pack.get('side_effect_level', 'readonly')

            # Add use cases for better LLM understanding
            use_cases = self._get_pack_use_cases(pack_id)
            use_cases_str = f"Use cases: {', '.join(use_cases)}" if use_cases else ""

            descriptions.append(
                f"- {pack_id} ({display_name}): {description} [{side_effect}]\n"
                f"  {use_cases_str}"
            )

        return '\n'.join(descriptions)

    def _get_pack_use_cases(self, pack_id: str) -> List[str]:
        """Get use cases for a pack to help LLM understand when to use it"""
        use_cases_map = {
            "storyboard": [
                "生成教学脚本和故事板",
                "创建视频拍摄脚本",
                "制作课程逐字稿",
                "设计教学画面和镜头"
            ],
            "content_drafting": [
                "课程设计和规划",
                "内容创作和起草",
                "文档编写",
                "流程设计"
            ],
            "daily_planning": [
                "任务规划和管理",
                "项目管理和时间线",
                "创建任务列表和检查清单",
                "开课准备清单"
            ],
            "habit_learning": [
                "习惯养成和支持",
                "长期目标追踪",
                "执行教练和持续推进",
                "行为改变支持"
            ],
            "semantic_seeds": [
                "从文件或消息中提取意图",
                "识别主题和关键词",
                "分析内容结构"
            ],
            "ig": [
                # Note: IG capability has been migrated to cloud (capabilities/ig/)
                # Complete workflow (for new post creation)
                "Create complete IG post (use 'ig_complete_workflow' playbook - for 'create IG post' / '創建 IG 貼文' requests)",
                # Individual playbooks (for specific tasks on existing posts)
                "Generate IG post hashtags only (use 'ig_hashtag_manager' playbook - for 'just generate hashtags' / '只生成 hashtag' requests)",
                "Validate IG post content only (use 'ig_content_checker' playbook - for 'validate content' / '驗證內容' requests)",
                "Generate IG post templates only (use 'ig_template_engine' playbook - for 'generate template' / '生成模板' requests)",
                "Validate IG post assets only (use 'ig_asset_manager' playbook - for 'validate assets' / '驗證素材' requests)",
                "Generate IG post export pack only (use 'ig_export_pack_generator' playbook - for 'generate export pack' / '生成發文包' requests)",
                # Other use cases
                "Review and update IG posts",
                "Batch process multiple IG posts"
            ],
            "web_generation": [
                # Complete workflow (for new page creation)
                "Generate complete web page (use 'multi_page_assembly' or 'page_assembly' playbook - for 'create web page' / '生成網頁' requests)",
                # Individual playbooks (for specific tasks)
                "Generate page outline only (use 'page_outline' playbook - for 'just create outline' / '只生成頁面結構' requests)",
                "Generate page sections only (use 'page_sections' playbook - for 'generate sections only' / '只生成區塊' requests)",
                "Assemble complete page (use 'page_assembly' playbook - for 'assemble page' / '組裝頁面' requests)",
                "Generate site specification (use 'site_spec_generation' playbook)",
                "Generate style system (use 'style_system_gen' playbook)",
                "Generate component library (use 'component_library_gen' playbook)"
            ]
        }
        return use_cases_map.get(pack_id, [])
