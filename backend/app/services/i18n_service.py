"""
i18n Service for Conversation Orchestrator

Modular i18n service that loads locale-specific strings from separate files.
Each module has its own i18n file to avoid large monolithic language files.
"""

import logging
from typing import Dict, Any, Optional
from pathlib import Path
import yaml

logger = logging.getLogger(__name__)

# Cache for loaded i18n files
_i18n_cache: Dict[str, Dict[str, Any]] = {}


class I18nService:
    """
    Modular i18n service for Conversation Orchestrator

    Loads locale-specific strings from module-specific i18n files.
    Each module (conversation_orchestrator, workspace, etc.) has its own i18n file.
    """

    def __init__(self, default_locale: str = "zh-TW"):
        self.default_locale = default_locale
        self.i18n_base_dir = Path(__file__).parent.parent / "i18n"

    def t(
        self,
        module: str,
        key: str,
        locale: Optional[str] = None,
        default: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Translate a key from a module's i18n file

        Args:
            module: Module name (e.g., "conversation_orchestrator", "workspace")
            key: Translation key (e.g., "workflow_started", "workflow_failed")
            locale: Locale code (defaults to self.default_locale)
            default: Default value if key not found
            **kwargs: Format parameters for string interpolation

        Returns:
            Translated string
        """
        if locale is None:
            locale = self.default_locale

        try:
            # Load module's i18n file
            i18n_data = self._load_module_i18n(module, locale)

            # Get value from nested dict (support dot notation)
            value = i18n_data
            for part in key.split("."):
                if isinstance(value, dict) and part in value:
                    value = value[part]
                else:
                    # Try fallback locales
                    return self._get_with_fallback(module, key, locale, default, **kwargs)

            if value is not None:
                result = str(value)
                # Format string if kwargs provided
                if kwargs:
                    try:
                        result = result.format(**kwargs)
                    except KeyError as e:
                        logger.warning(f"Missing format parameter {e} in i18n key {module}.{key}")
                return result

            return self._get_with_fallback(module, key, locale, default, **kwargs)

        except Exception as e:
            logger.error(f"Failed to translate {module}.{key} (locale: {locale}): {e}")
            return default or key

    def _get_with_fallback(
        self,
        module: str,
        key: str,
        locale: str,
        default: Optional[str],
        **kwargs
    ) -> str:
        """Get translation with fallback chain"""
        fallback_locales = []

        if locale != "en":
            fallback_locales.append("en")
        if locale != "zh-TW" and "zh-TW" not in fallback_locales:
            fallback_locales.append("zh-TW")

        for fallback_locale in fallback_locales:
            try:
                i18n_data = self._load_module_i18n(module, fallback_locale)
                value = i18n_data
                for part in key.split("."):
                    if isinstance(value, dict) and part in value:
                        value = value[part]
                    else:
                        break
                else:
                    if value is not None:
                        result = str(value)
                        if kwargs:
                            try:
                                result = result.format(**kwargs)
                            except KeyError:
                                pass
                        return result
            except Exception:
                continue

        return default or key

    def _load_module_i18n(self, module: str, locale: str) -> Dict[str, Any]:
        """
        Load i18n file for a specific module and locale

        File structure:
        backend/app/i18n/{module}/{locale}.yaml

        Args:
            module: Module name
            locale: Locale code

        Returns:
            i18n data dictionary
        """
        cache_key = f"{module}:{locale}"

        if cache_key in _i18n_cache:
            return _i18n_cache[cache_key]

        i18n_file = self.i18n_base_dir / module / f"{locale}.yaml"

        if not i18n_file.exists():
            logger.debug(f"i18n file not found: {i18n_file}")
            _i18n_cache[cache_key] = {}
            return {}

        try:
            with open(i18n_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
                _i18n_cache[cache_key] = data
                return data
        except Exception as e:
            logger.error(f"Failed to load i18n file {i18n_file}: {e}")
            _i18n_cache[cache_key] = {}
            return {}


# Global instance
_i18n_service: Optional[I18nService] = None


def get_i18n_service(default_locale: str = "zh-TW") -> I18nService:
    """Get global i18n service instance"""
    global _i18n_service
    if _i18n_service is None:
        _i18n_service = I18nService(default_locale=default_locale)
    return _i18n_service
