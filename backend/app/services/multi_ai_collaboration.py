"""
Multi-AI Collaboration Service

Coordinates multiple AI capabilities to analyze uploaded files:
- Semantic Seeds extraction
- Daily Planning analysis
- Content Drafting suggestions
"""

import logging
import base64
from typing import Dict, Any, List, Optional
from datetime import datetime

from backend.app.services.file_processor import FileProcessor
from backend.app.services.playbook_runner import PlaybookRunner

logger = logging.getLogger(__name__)


class MultiAICollaborationService:
    """Service for coordinating multiple AI capabilities on file analysis"""

    def __init__(
        self,
        file_processor: Optional[FileProcessor] = None,
        playbook_runner: Optional[PlaybookRunner] = None
    ):
        self.file_processor = file_processor or FileProcessor()
        self.playbook_runner = playbook_runner or PlaybookRunner()

    async def analyze_file(
        self,
        file_data: str,
        file_name: str,
        file_type: Optional[str],
        file_size: Optional[int],
        profile_id: str,
        workspace_id: str,
        file_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze file with multiple AI capabilities

        Returns collaboration results from:
        - Semantic Seeds Pack
        - Daily Planning Pack
        - Content Drafting Pack
        """
        try:
            # If file_path is provided, use extract_text tool for OCR integration
            if file_path and file_name.lower().endswith('.pdf'):
                logger.info(f"Using file path for extraction with OCR support: {file_path}")
                try:
                    from backend.app.shared.tool_executor import ToolExecutor
                    executor = ToolExecutor()
                    extract_result = await executor.execute_tool(
                        "core_files.extract_text",
                        file_path=file_path,
                        file_type="pdf"
                    )
                    # Add extracted text to file_info
                    file_info = {
                        "name": file_name,
                        "size": file_size or 0,
                        "type": file_type or "application/pdf",
                        "text_content": extract_result.get("text", ""),
                        "ocr_used": extract_result.get("ocr_used", False),
                        "quality": extract_result.get("quality"),
                        "file_path": file_path
                    }
                    logger.info(f"Extracted text using OCR-aware extraction: {len(file_info.get('text_content', ''))} chars, OCR used: {file_info.get('ocr_used', False)}")
                except Exception as e:
                    logger.warning(f"Failed to extract text with OCR integration: {e}, falling back to standard processing")
                    file_info = await self.file_processor.process_file(
                        file_data=file_data,
                        file_name=file_name,
                        file_type=file_type,
                        file_size=file_size
                    )
            else:
                file_info = await self.file_processor.process_file(
                    file_data=file_data,
                    file_name=file_name,
                    file_type=file_type,
                    file_size=file_size
                )

            collaboration_results = {
                "semantic_seeds": await self._analyze_semantic_seeds(
                    file_info=file_info,
                    file_data=file_data,
                    file_name=file_name,
                    profile_id=profile_id,
                    workspace_id=workspace_id,
                    file_path=file_path or file_info.get("file_path")
                ),
                "daily_planning": await self._analyze_daily_planning(
                    file_info=file_info,
                    file_data=file_data,
                    profile_id=profile_id,
                    workspace_id=workspace_id
                ),
                "content_drafting": await self._analyze_content_drafting(
                    file_info=file_info,
                    file_data=file_data,
                    profile_id=profile_id,
                    workspace_id=workspace_id
                )
            }

            return {
                "file_info": file_info,
                "collaboration_results": collaboration_results
            }
        except Exception as e:
            logger.error(f"Failed to analyze file: {e}", exc_info=True)
            return {
                "file_info": {
                    "name": file_name,
                    "error": str(e)
                },
                "collaboration_results": {
                    "semantic_seeds": {"enabled": False, "error": str(e)},
                    "daily_planning": {"enabled": False, "error": str(e)},
                    "content_drafting": {"enabled": False, "error": str(e)}
                }
            }

    async def _analyze_semantic_seeds(
        self,
        file_info: Dict[str, Any],
        file_data: str,
        file_name: str,
        profile_id: str,
        workspace_id: str,
        file_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """Analyze file for semantic seeds"""
        try:
            detected_type = file_info.get("detected_type")
            logger.info(f"Analyzing semantic seeds for file type: {detected_type}")

            if detected_type in ["proposal", "document", "text"] or file_name.lower().endswith('.pdf'):
                # Try to get text content from file_info first (FileProcessor should have extracted it)
                content_preview = None
                if file_info.get("text_content"):
                    content_preview = file_info.get("text_content", "")[:5000]  # Use more text for better analysis
                    logger.info(f"Using text_content from file_info: {len(content_preview)} chars")
                elif file_info.get("extracted_text"):
                    content_preview = file_info.get("extracted_text", "")[:5000]
                    logger.info(f"Using extracted_text from file_info: {len(content_preview)} chars")
                else:
                    # For PDF, try to extract using PyPDF2
                    if file_name.lower().endswith('.pdf'):
                        logger.warning(f"PDF file but no text_content in file_info, attempting direct extraction")
                        # Try to extract from file_path first (if available)
                        pdf_file_path = file_path or file_info.get("file_path")
                        if pdf_file_path:
                            content_preview = await self._extract_pdf_from_path(pdf_file_path, max_length=5000)
                            logger.info(f"PDF extraction from path: {len(content_preview) if content_preview else 0} chars")
                        else:
                            # Fallback to extracting from file_data (base64)
                            content_preview = await self._extract_pdf_text_direct(file_data, max_length=5000)
                            logger.info(f"Direct PDF extraction from data: {len(content_preview) if content_preview else 0} chars")
                    else:
                        # Fallback to extracting from file_data (for text files)
                        content_preview = self._extract_content_preview(file_data, max_length=5000)
                        logger.info(f"Content preview extracted from file_data: {len(content_preview) if content_preview else 0} chars")

                if content_preview and len(content_preview.strip()) > 100:  # Require at least 100 chars for real content
                    try:
                        from backend.app.capabilities.semantic_seeds.services.seed_extractor import SeedExtractor
                        from backend.app.services.agent_runner import LLMProviderManager
                        from backend.app.services.config_store import ConfigStore
                        from backend.app.shared.i18n_loader import get_locale_from_context
                        from backend.app.services.mindscape_store import MindscapeStore
                        import os

                        # Get locale from context (workspace/profile)
                        store = MindscapeStore()
                        profile = None
                        workspace = None
                        try:
                            if profile_id:
                                profile = store.get_profile(profile_id)
                            if workspace_id:
                                workspace = store.get_workspace(workspace_id)
                        except Exception as e:
                            logger.debug(f"Could not get profile/workspace for locale: {e}")

                        locale = get_locale_from_context(profile=profile, workspace=workspace) or "en"

                        # Initialize LLM provider for SeedExtractor
                        from backend.app.shared.llm_provider_helper import get_llm_provider_from_settings
                        from backend.app.services.system_settings_store import SystemSettingsStore
                        import json
                        config_store = ConfigStore()
                        config = config_store.get_or_create_config(profile_id)
                        openai_key = config.agent_backend.openai_api_key or os.getenv("OPENAI_API_KEY")
                        anthropic_key = config.agent_backend.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")

                        # Get Vertex AI config from system settings (like core_llm does)
                        settings_store = SystemSettingsStore()
                        vertex_service_account_json = None
                        vertex_project_id = None
                        try:
                            service_account_setting = settings_store.get_setting("vertex_ai_service_account_json")
                            project_id_setting = settings_store.get_setting("vertex_ai_project_id")
                            if service_account_setting and service_account_setting.value:
                                if isinstance(service_account_setting.value, dict):
                                    vertex_service_account_json = json.dumps(service_account_setting.value)
                                else:
                                    vertex_service_account_json = str(service_account_setting.value)
                            else:
                                vertex_service_account_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
                            vertex_project_id = project_id_setting.value if project_id_setting and project_id_setting.value else os.getenv("GOOGLE_CLOUD_PROJECT")
                        except Exception as e:
                            logger.debug(f"Failed to get Vertex AI from system settings: {e}, using env vars")
                            vertex_service_account_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
                            vertex_project_id = os.getenv("GOOGLE_CLOUD_PROJECT")

                        # Fallback to user config if system settings not available
                        if not vertex_service_account_json:
                            vertex_service_account_json = config.agent_backend.vertex_api_key
                        if not vertex_project_id:
                            vertex_project_id = config.agent_backend.vertex_project_id

                        from backend.app.shared.llm_provider_helper import create_llm_provider_manager

                        llm_manager = create_llm_provider_manager(
                            openai_key=openai_key,
                            anthropic_key=anthropic_key,
                            vertex_api_key=vertex_service_account_json,
                            vertex_project_id=vertex_project_id,
                            vertex_location=config.agent_backend.vertex_location or os.getenv("VERTEX_LOCATION", "us-central1")
                        )
                        try:
                            llm_provider = get_llm_provider_from_settings(llm_manager)
                        except (ValueError, Exception) as e:
                            logger.warning(f"Failed to get LLM provider from settings: {e}, trying direct provider")
                            if vertex_service_account_json and vertex_project_id:
                                llm_provider = llm_manager.get_provider("vertex-ai")
                            elif openai_key:
                                llm_provider = llm_manager.get_provider("openai")
                            elif anthropic_key:
                                llm_provider = llm_manager.get_provider("anthropic")
                            else:
                                llm_provider = None

                        seed_extractor = SeedExtractor(llm_provider=llm_provider)
                        logger.info(f"Initialized SeedExtractor with LLM provider and locale={locale} for file: {file_info.get('name')}")

                        seeds = await seed_extractor.extract_seeds_from_content(
                            user_id=profile_id,
                            content=content_preview,
                            source_type="file_upload",
                            source_id=file_info.get("name"),
                            source_context=f"File: {file_info.get('name')}",
                            locale=locale
                        )

                        themes = [s.get("text") for s in seeds if s.get("type") in ["project", "principle", "entity"]]
                        intents = [s.get("text") for s in seeds if s.get("type") == "intent"]

                        logger.info(f"Extracted from seeds: {len(themes)} themes, {len(intents)} intents")
                        logger.info(f"Themes: {themes[:3]}, Intents: {intents[:3]}")

                        return {
                            "enabled": True,
                            "themes": themes[:5] if themes else [],
                            "intents": intents[:3] if intents else [],
                            "action": "add_to_mindscape"
                        }
                    except ImportError:
                        logger.warning("SeedExtractor not available, using simple heuristic")
                        inferred_intents = self._infer_intents_from_filename(file_info.get("name", ""), locale=locale)
                        return {
                            "enabled": True,
                            "themes": [file_info.get("detected_type", "document")],
                            "intents": inferred_intents,
                            "action": "add_to_mindscape"
                        }
                    except Exception as e:
                        logger.warning(f"SeedExtractor failed: {e}, trying filename-based inference")
                        inferred_intents = self._infer_intents_from_filename(file_info.get("name", ""), locale=locale)
                        return {
                            "enabled": True,
                            "themes": [file_info.get("detected_type", "document")],
                            "intents": inferred_intents,
                            "action": "add_to_mindscape"
                        }
                else:
                    from backend.app.services.i18n_service import get_i18n_service
                    from backend.app.shared.i18n_loader import get_locale_from_context
                    from backend.app.services.mindscape_store import MindscapeStore

                    store = MindscapeStore()
                    workspace = None
                    profile = None
                    try:
                        workspace = store.get_workspace(workspace_id)
                        if workspace and workspace.owner_user_id:
                            try:
                                profile = store.get_profile(workspace.owner_user_id)
                            except Exception:
                                pass
                    except Exception:
                        pass

                    locale = get_locale_from_context(profile=profile, workspace=workspace) or "en"
                    i18n = get_i18n_service(default_locale=locale)

                    reason = i18n.t(
                        "multi_ai_collaboration",
                        "error.no_content_preview",
                        default="Cannot extract text content from file, cannot perform semantic seed analysis"
                    )

                    logger.warning(f"No content preview available for file {file_info.get('name')}. Cannot extract semantic seeds from content.")
                    return {
                        "enabled": False,
                        "reason": reason
                    }

            from backend.app.services.i18n_service import get_i18n_service
            from backend.app.shared.i18n_loader import get_locale_from_context
            from backend.app.services.mindscape_store import MindscapeStore

            store = MindscapeStore()
            workspace = None
            profile = None
            try:
                workspace = store.get_workspace(workspace_id)
                if workspace and workspace.owner_user_id:
                    try:
                        profile = store.get_profile(workspace.owner_user_id)
                    except Exception:
                        pass
            except Exception:
                pass

            locale = get_locale_from_context(profile=profile, workspace=workspace) or "en"
            i18n = get_i18n_service(default_locale=locale)

            reason = i18n.t(
                "multi_ai_collaboration",
                "error.file_type_not_suitable",
                default="File type not suitable for semantic seed extraction"
            )

            return {
                "enabled": False,
                "reason": reason
            }
        except Exception as e:
            logger.warning(f"Semantic seeds analysis failed: {e}")
            return {
                "enabled": False,
                "error": str(e)
            }

    async def _analyze_daily_planning(
        self,
        file_info: Dict[str, Any],
        file_data: str,
        profile_id: str,
        workspace_id: str
    ) -> Dict[str, Any]:
        """Analyze file for daily planning tasks"""
        try:
            if file_info.get("detected_type") in ["proposal", "document", "text"]:
                content_preview = self._extract_content_preview(file_data, max_length=2000)

                if content_preview:
                    suggested_steps = self._extract_suggested_steps(content_preview)
                    today_actions = suggested_steps[:2] if len(suggested_steps) >= 2 else suggested_steps

                    return {
                        "enabled": True,
                        "suggested_steps": len(suggested_steps),
                        "today_actions": len(today_actions),
                        "action": "view_task_list"
                    }

            return {
                "enabled": False,
                "reason": "File type not suitable for daily planning analysis"
            }
        except Exception as e:
            logger.warning(f"Daily planning analysis failed: {e}")
            return {
                "enabled": False,
                "error": str(e)
            }

    async def _analyze_content_drafting(
        self,
        file_info: Dict[str, Any],
        file_data: str,
        profile_id: str,
        workspace_id: str
    ) -> Dict[str, Any]:
        """Analyze file for content drafting suggestions"""
        try:
            if file_info.get("detected_type") in ["proposal", "document", "text"]:
                file_type = file_info.get("detected_type")
                suggested_formats = []

                if file_type == "proposal":
                    suggested_formats = ["募資頁", "官方部落格文", "提案簡報框架"]
                elif file_type == "document":
                    suggested_formats = ["官方部落格文", "產品說明頁", "新聞稿"]
                else:
                    suggested_formats = ["官方部落格文", "內容摘要"]

                return {
                    "enabled": True,
                    "suggested_formats": suggested_formats,
                    "action": "create_draft"
                }

            return {
                "enabled": False,
                "reason": "File type not suitable for content drafting"
            }
        except Exception as e:
            logger.warning(f"Content drafting analysis failed: {e}")
            return {
                "enabled": False,
                "error": str(e)
            }

    def _extract_content_preview(self, file_data: str, max_length: int = 2000) -> Optional[str]:
        """Extract text preview from file data (for text files only)"""
        try:
            if file_data.startswith('data:'):
                base64_data = file_data.split(',')[1] if ',' in file_data else file_data
                decoded = base64.b64decode(base64_data)
                text = decoded.decode('utf-8', errors='ignore')
                return text[:max_length]
            return None
        except Exception as e:
            logger.warning(f"Failed to extract content preview: {e}")
            return None

    async def _extract_pdf_from_path(self, file_path: str, max_length: int = 10000) -> Optional[str]:
        """Extract text from PDF file path"""
        try:
            import PyPDF2
            import os

            if not os.path.exists(file_path):
                logger.warning(f"PDF file path does not exist: {file_path}")
                return None

            with open(file_path, 'rb') as pdf_file:
                pdf_reader = PyPDF2.PdfReader(pdf_file)

                text_parts = []
                # Extract text from first 20 pages (to get meaningful content)
                for page_num in range(min(20, len(pdf_reader.pages))):
                    page = pdf_reader.pages[page_num]
                    text = page.extract_text()
                    if text and text.strip():
                        text_parts.append(text.strip())

                extracted_text = '\n\n'.join(text_parts)
                if extracted_text:
                    logger.info(f"Extracted {len(extracted_text)} chars from PDF file ({len(pdf_reader.pages)} pages)")
                    return extracted_text[:max_length]

            return None
        except ImportError:
            logger.error("PyPDF2 not installed. Cannot extract PDF text.")
            return None
        except Exception as e:
            logger.warning(f"Failed to extract PDF text from path {file_path}: {e}")
            return None

    async def _extract_pdf_text_direct(self, file_data: str, max_length: int = 10000) -> Optional[str]:
        """Extract text directly from PDF base64 data"""
        try:
            import PyPDF2
            from io import BytesIO

            if not file_data.startswith('data:'):
                return None

            base64_data = file_data.split(',')[1] if ',' in file_data else file_data
            pdf_bytes = base64.b64decode(base64_data)

            pdf_file = BytesIO(pdf_bytes)
            pdf_reader = PyPDF2.PdfReader(pdf_file)

            text_parts = []
            # Extract text from first 20 pages (to get meaningful content)
            for page_num in range(min(20, len(pdf_reader.pages))):
                page = pdf_reader.pages[page_num]
                text = page.extract_text()
                if text and text.strip():
                    text_parts.append(text.strip())

            extracted_text = '\n\n'.join(text_parts)
            if extracted_text:
                logger.info(f"Extracted {len(extracted_text)} chars from PDF ({len(pdf_reader.pages)} pages)")
                return extracted_text[:max_length]

            return None
        except ImportError:
            logger.error("PyPDF2 not installed. Cannot extract PDF text.")
            return None
        except Exception as e:
            logger.warning(f"Failed to extract PDF text directly: {e}")
            return None

    def _extract_suggested_steps(self, content: str) -> List[str]:
        """Extract suggested steps from content (simple heuristic)"""
        steps = []
        lines = content.split('\n')

        for line in lines:
            line = line.strip()
            if any(marker in line for marker in ['步驟', 'step', '任務', 'task', '1.', '2.', '3.']):
                if len(line) > 10 and len(line) < 200:
                    steps.append(line)
                    if len(steps) >= 5:
                        break

        return steps

    def _infer_intents_from_filename(self, file_name: str, locale: str = "en") -> List[str]:
        """Infer potential intents from filename when content extraction fails"""
        from backend.app.services.i18n_service import get_i18n_service

        if not file_name:
            return []

        i18n = get_i18n_service(default_locale=locale)

        intents = []
        file_name_lower = file_name.lower()

        intent_keywords_str = i18n.t(
            "multi_ai_collaboration",
            "intent_keywords.mapping",
            default="research:Research and Analysis,analysis:Analysis and Evaluation,plan:Planning,strategy:Strategy Development,development:Product Development,management:Project Management,writing:Content Writing,proposal:Proposal Development,report:Report Writing,marketing:Marketing Strategy,product:Product Development,project:Project Management"
        )

        intent_keywords = {}
        for pair in intent_keywords_str.split(","):
            if ":" in pair:
                keyword, intent = pair.split(":", 1)
                intent_keywords[keyword.strip()] = intent.strip()

        has_non_ascii = any(ord(char) > 127 for char in file_name)

        for keyword, intent in intent_keywords.items():
            if keyword in file_name_lower:
                intents.append(intent)
                break

        if not intents:
            name_without_ext = file_name.rsplit('.', 1)[0] if '.' in file_name else file_name
            cleaned = name_without_ext.replace('-', ' ').replace('_', ' ').replace('(', '').replace(')', '')
            words = cleaned.split()
            if words:
                first_phrase = ' '.join(words[:3]) if len(words) > 1 else words[0]
                if len(first_phrase) > 3:
                    intents.append(first_phrase[:50])

        return intents[:2]
