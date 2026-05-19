import asyncio

from backend.app.services.conversation.message_generator import (
    MessageGenerator as CanonicalMessageGenerator,
)
from backend.app.services.message_generator import MessageGenerator as CompatMessageGenerator


def test_message_generator_imports_share_same_class():
    assert CanonicalMessageGenerator is CompatMessageGenerator


def test_message_generator_preserves_method_surface():
    required = [
        "_ensure_llm_provider",
        "generate_readonly_feedback",
        "generate_suggestion_message",
        "generate_confirmation_message",
        "_get_confirm_button_label",
        "_get_cancel_button_label",
        "generate_workflow_response",
        "_generate_single_step_response",
        "_format_workflow_summary",
        "generate_workflow_summary",
    ]

    assert [name for name in required if not hasattr(CanonicalMessageGenerator, name)] == []


def test_confirmation_no_provider_preserves_response_shape():
    generator = CanonicalMessageGenerator(llm_provider=None, default_locale="en")

    result = asyncio.run(
        generator.generate_confirmation_message(
            action_type="publish_to_wordpress",
            action_params={"title": "Launch Note", "url": "https://example.test"},
            timeline_item={"title": "Launch Note", "summary": "Ready to publish"},
        )
    )

    assert isinstance(result["message"], str)
    assert result["message"]
    assert result["confirm_buttons"][0]["action"] == "publish_to_wordpress"
    assert result["confirm_buttons"][0]["confirm"] is True
    assert result["confirm_buttons"][1]["action"] == "cancel"


def test_readonly_feedback_no_provider_returns_non_empty_text():
    generator = CanonicalMessageGenerator(llm_provider=None, default_locale="en")

    result = asyncio.run(
        generator.generate_readonly_feedback(
            timeline_item={"title": "Analysis", "summary": "Three insights found"},
            task_result={"summary": "Three insights found"},
        )
    )

    assert isinstance(result, str)
    assert result


def test_button_labels_keep_action_specific_fallbacks():
    generator = CanonicalMessageGenerator(llm_provider=None, default_locale="en")

    assert generator._get_confirm_button_label("publish_to_wordpress")
    assert generator._get_confirm_button_label("export_pdf")
    assert generator._get_cancel_button_label()
