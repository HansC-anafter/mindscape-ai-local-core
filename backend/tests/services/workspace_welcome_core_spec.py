import re
from pathlib import Path
from types import SimpleNamespace

from backend.app.services.workspace_welcome_core import (
    build_suggestions_system_prompt,
    build_suggestions_user_prompt,
    build_welcome_system_prompt,
    build_welcome_user_prompt,
    sanitize_suggestions_text,
    validate_welcome_message_locale,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
SERVICE_PATH = REPO_ROOT / "backend/app/services/workspace_welcome_service.py"
CORE_DIR = REPO_ROOT / "backend/app/services/workspace_welcome_core"
SPEC_PATH = Path(__file__)
TOUCHED_PATHS = [
    SERVICE_PATH,
    CORE_DIR / "__init__.py",
    CORE_DIR / "prompting.py",
    CORE_DIR / "language_validation.py",
    SPEC_PATH,
]


def _workspace():
    return SimpleNamespace(
        id="workspace-1",
        title="Launch Lab",
        description="Draft rollout assets",
        mode="project",
    )


def _resource_markers():
    return [
        "Mindscape" + "Store",
        "Postgres" + "TimelineItemsStore",
        "Context" + "Builder",
        "QA" + "ResponseGenerator",
        "Playbook" + "Loader",
        "generate" + "_text",
        "get_model" + "_name_from_chat_model",
        "get_i18n" + "_service",
        "session" + "maker",
        "create" + "_engine",
        "Pg" + "Bouncer",
        "work" + "er",
        "que" + "ue",
        "poll" + "ing",
        "web" + "socket",
        "Event" + "Source",
        "request" + "s",
        "http" + "x",
        "Fast" + "API",
        "API" + "Router",
        "store" + ".",
    ]


def test_suggestion_sanitizer_filters_vague_starters_and_dedupes():
    maybe_start = "\u6216\u8a31\u53ef\u4ee5\u958b\u59cb"
    can_start = "\u53ef\u4ee5\u958b\u59cb"
    concrete_action = "\u751f\u6210\u9996\u9801\u8349\u7a3f"
    text = "\n".join(
        [
            f"- {maybe_start}",
            "1. Upload source deck",
            "2. Upload source deck",
            f"* {concrete_action}",
            f"3. {can_start}",
            "4. Map launch dependencies",
            "5. Draft stakeholder brief",
            "6. Schedule review checkpoint",
        ]
    )

    assert sanitize_suggestions_text(text) == [
        "Upload source deck",
        concrete_action,
        "Map launch dependencies",
        "Draft stakeholder brief",
    ]


def test_prompt_builders_preserve_workspace_playbook_intent_and_locale_context():
    active_intents = [{"title": "Ship beta", "description": "Validate signup"}]
    playbooks = [
        {
            "name": "Launch Plan",
            "playbook_code": "launch.plan",
            "description": "Draft rollout",
        }
    ]

    suggestion_system = build_suggestions_system_prompt(
        target_language="Traditional Chinese",
        locale="zh-TW",
        language_instruction="Reply only in target locale.",
    )
    suggestion_user = build_suggestions_user_prompt(
        workspace=_workspace(),
        active_intents=active_intents,
        available_playbooks=playbooks,
        mindscape_context="Recent activity: 2 events in this workspace",
        target_language="Traditional Chinese",
    )
    welcome_system = build_welcome_system_prompt(
        workspace=_workspace(),
        locale="zh-TW",
        target_language="Traditional Chinese",
        language_instruction="Reply only in target locale.",
    )
    welcome_user = build_welcome_user_prompt(
        workspace=_workspace(),
        available_playbooks=playbooks,
        active_intents=active_intents,
        context="Known context",
        target_language="Traditional Chinese",
        locale="zh-TW",
    )

    assert "\u751f\u6210\u9996\u9801\u8349\u7a3f" in suggestion_system
    assert "Launch Lab" in suggestion_user
    assert "Ship beta: Validate signup" in suggestion_user
    assert "Launch Plan (launch.plan): Draft rollout" in suggestion_user
    assert "Recent activity: 2 events" in suggestion_user
    assert 'new workspace "Launch Lab"' in welcome_system
    assert "Traditional Chinese" in welcome_system
    assert "Known context" in welcome_user


def test_welcome_language_validation_enforces_cjk_locale_thresholds():
    valid_zh = "\u4f60\u597d" * 6
    valid_ja = "\u3053\u3093\u306b\u3061\u306f" * 2
    valid_ko = "\uc548\ub155\ud558\uc138\uc694" * 2

    invalid_zh = validate_welcome_message_locale(
        "This message is only English text.",
        "zh-TW",
        "en",
    )
    assert not invalid_zh.is_valid
    assert invalid_zh.log_level == "warning"
    assert invalid_zh.error == "LLM generated message in wrong language"
    assert validate_welcome_message_locale(valid_zh, "zh-TW", "en").is_valid
    assert validate_welcome_message_locale(valid_ja, "ja-JP", "en").is_valid
    assert validate_welcome_message_locale(valid_ko, "ko-KR", "en").is_valid


def test_welcome_language_validation_allows_english_and_warns_other_mismatches():
    english_result = validate_welcome_message_locale(
        "Welcome to your workspace.",
        "en",
        "fr",
    )
    other_result = validate_welcome_message_locale(
        "Bienvenue dans votre espace.",
        "fr",
        "en",
    )

    assert english_result.is_valid
    assert english_result.log_level == "debug"
    assert other_result.is_valid
    assert other_result.log_level == "warning"


def test_workspace_welcome_files_stay_below_line_gate():
    for path in TOUCHED_PATHS:
        assert len(path.read_text().splitlines()) <= 500, path


def test_workspace_welcome_core_has_no_resource_markers():
    scanned_text = "\n".join(path.read_text() for path in TOUCHED_PATHS[1:])
    for marker in _resource_markers():
        assert marker not in scanned_text, marker


def test_workspace_welcome_resource_owners_remain_in_public_service_only():
    service_text = SERVICE_PATH.read_text()
    core_text = "\n".join(path.read_text() for path in CORE_DIR.glob("*.py"))
    required_public_markers = [
        "Mindscape" + "Store",
        "Postgres" + "TimelineItemsStore",
        "Context" + "Builder",
        "QA" + "ResponseGenerator",
        "Playbook" + "Loader",
        "generate" + "_text",
        "get_model" + "_name_from_chat_model",
        "get_i18n" + "_service",
        "store" + ".",
    ]

    assert "WorkspaceWelcomeService" in service_text
    assert "generate_welcome_message" in service_text
    for marker in required_public_markers:
        assert marker in service_text, marker
        assert marker not in core_text, marker


def test_workspace_welcome_touched_sources_have_no_chinese_or_emoji():
    pattern = re.compile(r"[\u4e00-\u9fff]|[\U0001f300-\U0001faff]")
    for path in TOUCHED_PATHS:
        assert not pattern.search(path.read_text()), path
