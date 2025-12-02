"""
i18n Loader
Load internationalized strings for Playbooks and capabilities
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
import yaml

logger = logging.getLogger(__name__)

# Cache for loaded i18n files
_i18n_cache: Dict[str, Dict[str, Any]] = {}


def load_i18n_string(
    key: str,
    locale: str = "zh-TW",
    default: Optional[str] = None,
    supported_locales: Optional[List[str]] = None,
    auto_localize: bool = True
) -> str:
    """
    Load internationalized string by key and locale with fallback strategy

    Fallback order:
    1. Requested locale (e.g., "ja-JP")
    2. English ("en")
    3. Traditional Chinese ("zh-TW")
    4. Default value

    Args:
        key: i18n key (e.g., "major_proposal.ask_overview.ui")
        locale: Locale code (e.g., "zh-TW", "en", "ja-JP")
        default: Default value if key not found in any locale
        supported_locales: List of officially supported locales (default: ["zh-TW", "en"])
        auto_localize: If True, allow fallback to English for unsupported locales

    Returns:
        Localized string
    """
    if supported_locales is None:
        supported_locales = ["zh-TW", "en"]

    try:
        # Parse key to get namespace and file
        parts = key.split(".")
        if len(parts) < 2:
            logger.warning(f"Invalid i18n key format: {key}")
            return default or key

        namespace = parts[0]  # e.g., "major_proposal"
        subkey = ".".join(parts[1:])  # e.g., "ask_overview.ui"

        # Fallback strategy: try locales in order
        locales_to_try = [locale]

        # If requested locale is not in supported_locales, add fallback chain
        if locale not in supported_locales and auto_localize:
            # Add English as primary fallback
            if "en" not in locales_to_try:
                locales_to_try.append("en")
            # Add zh-TW as secondary fallback
            if "zh-TW" not in locales_to_try:
                locales_to_try.append("zh-TW")
        else:
            # If locale is supported, still try en and zh-TW as fallbacks
            for fallback_locale in ["en", "zh-TW"]:
                if fallback_locale not in locales_to_try:
                    locales_to_try.append(fallback_locale)

        # Try each locale in fallback order
        for try_locale in locales_to_try:
            i18n_data = _load_i18n_file(namespace, try_locale)

            # Get value from nested dict
            value = i18n_data
            found = True
            for part in subkey.split("."):
                if isinstance(value, dict) and part in value:
                    value = value[part]
                else:
                    found = False
                    break

            if found and value is not None:
                logger.debug(f"Loaded i18n key {key} from locale {try_locale} (requested: {locale})")
                return str(value)

        # Not found in any locale
        logger.debug(f"i18n key not found in any locale: {key} (tried: {locales_to_try})")
        return default or key

    except Exception as e:
        logger.error(f"Failed to load i18n string {key} (locale: {locale}): {e}")
        return default or key


def _load_i18n_file(namespace: str, locale: str) -> Dict[str, Any]:
    """
    Load i18n YAML file for namespace and locale

    Search order:
    1. Capability pack's resources/i18n/ directory (for installed packs)
    2. Backend's i18n/playbooks/ directory (for built-in packs)

    Args:
        namespace: Namespace (e.g., "major_proposal", "storyboard")
        locale: Locale code (e.g., "zh-TW", "en")

    Returns:
        i18n data dictionary
    """
    cache_key = f"{namespace}:{locale}"

    # Check cache
    if cache_key in _i18n_cache:
        return _i18n_cache[cache_key]

    backend_dir = Path(__file__).parent.parent
    i18n_file = None

    # Try 1: Capability pack's resources/i18n/ directory
    capabilities_dir = backend_dir / "capabilities"
    if capabilities_dir.exists():
        for capability_dir in capabilities_dir.iterdir():
            if not capability_dir.is_dir() or capability_dir.name.startswith('_'):
                continue

            # Check if this capability matches the namespace
            manifest_path = capability_dir / "manifest.yaml"
            if manifest_path.exists():
                try:
                    with open(manifest_path, 'r', encoding='utf-8') as f:
                        manifest = yaml.safe_load(f)
                        capability_code = manifest.get('code', capability_dir.name)
                        pack_id = manifest.get('id', capability_code)

                        # Match by code or id
                        if capability_code == namespace or pack_id == namespace or pack_id.endswith(f".{namespace}"):
                            pack_i18n_file = capability_dir / "resources" / "i18n" / f"{locale}.yaml"
                            if pack_i18n_file.exists():
                                i18n_file = pack_i18n_file
                                logger.debug(f"Found i18n file in capability pack: {pack_i18n_file}")
                                break
                except Exception as e:
                    logger.debug(f"Failed to check manifest in {capability_dir}: {e}")
                    continue

    # Try 2: Backend's i18n/playbooks/ directory (built-in packs)
    if not i18n_file or not i18n_file.exists():
        i18n_file = backend_dir / "i18n" / "playbooks" / f"{namespace}.{locale}.yaml"

    # Fallback to default locale (zh-TW) if not found
    if not i18n_file.exists():
        if locale != "zh-TW":
            logger.debug(f"i18n file not found for {namespace}.{locale}, trying zh-TW")

            # Try capability pack's zh-TW
            if capabilities_dir.exists():
                for capability_dir in capabilities_dir.iterdir():
                    if not capability_dir.is_dir() or capability_dir.name.startswith('_'):
                        continue

                    manifest_path = capability_dir / "manifest.yaml"
                    if manifest_path.exists():
                        try:
                            with open(manifest_path, 'r', encoding='utf-8') as f:
                                manifest = yaml.safe_load(f)
                                capability_code = manifest.get('code', capability_dir.name)
                                pack_id = manifest.get('id', capability_code)

                                if capability_code == namespace or pack_id == namespace or pack_id.endswith(f".{namespace}"):
                                    pack_i18n_file = capability_dir / "resources" / "i18n" / "zh-TW.yaml"
                                    if pack_i18n_file.exists():
                                        i18n_file = pack_i18n_file
                                        break
                        except Exception:
                            continue

            # Try backend's zh-TW
            if not i18n_file.exists():
                i18n_file = backend_dir / "i18n" / "playbooks" / f"{namespace}.zh-TW.yaml"

    # If still not found, return empty dict
    if not i18n_file.exists():
        logger.debug(f"i18n file not found: {namespace}.{locale} (searched capability packs and backend)")
        _i18n_cache[cache_key] = {}
        return {}

    # Load YAML file
    try:
        with open(i18n_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
            _i18n_cache[cache_key] = data
            return data
    except Exception as e:
        logger.error(f"Failed to load i18n file {i18n_file}: {e}")
        _i18n_cache[cache_key] = {}
        return {}


def get_locale_from_context(
    profile: Optional[Any] = None,
    workspace: Optional[Any] = None,
    project: Optional[Any] = None,
    playbook_metadata: Optional[Any] = None
) -> str:
    """
    Determine locale from context following multi-cluster architecture hierarchy

    Priority order:
    1. project.working_language (if project exists) - highest priority
    2. workspace.default_locale (if workspace exists) - workspace-level preference
    3. profile.preferences.preferred_content_language (if profile exists) - profile-level preference
    4. profile.preferences.language (legacy field, if exists)
    5. playbook_metadata.default_locale (if playbook metadata exists)
    6. Default: "zh-TW" - system default

    Args:
        profile: MindscapeProfile object (optional)
        workspace: Workspace object (optional)
        project: Project object (optional, e.g., ProposalProject)
        playbook_metadata: PlaybookMetadata object (optional)

    Returns:
        Locale code (e.g., "zh-TW", "en")
    """
    # Priority 1: Check project working language (highest priority)
    if project and hasattr(project, 'working_language'):
        return project.working_language

    # Priority 2: Check workspace default locale (workspace-level preference)
    if workspace and hasattr(workspace, 'default_locale') and workspace.default_locale:
        return workspace.default_locale

    # Priority 3: Fallback to profile preferences
    if profile and hasattr(profile, 'preferences'):
        prefs = profile.preferences
        if hasattr(prefs, 'preferred_content_language') and prefs.preferred_content_language:
            return prefs.preferred_content_language
        # Legacy: check old language field
        if hasattr(prefs, 'language') and prefs.language:
            return prefs.language

    # Priority 4: Fallback to playbook default
    if playbook_metadata and hasattr(playbook_metadata, 'default_locale') and playbook_metadata.default_locale:
        return playbook_metadata.default_locale

    # Priority 5: System default
    return "zh-TW"
