from backend.app.egb.services import data_policy as data_policy_module
from backend.app.egb.services.data_policy import (
    DataPolicy,
    DataPolicyConfig,
    PIIRedactor,
    RedactionRule,
)
from backend.app.egb.services.data_policy_payloads import fingerprint_payload


def test_default_redaction_rules_cover_sensitive_values():
    redactor = PIIRedactor()

    redacted = redactor.redact(
        "Contact owner@example.com at 0912345678 with Bearer abc123."
    )

    assert "owner@example.com" not in redacted
    assert "0912345678" not in redacted
    assert "Bearer abc123" not in redacted
    assert "[EMAIL]" in redacted
    assert "[PHONE]" in redacted
    assert "Bearer [TOKEN]" in redacted


def test_custom_rule_and_safe_keys_are_preserved():
    policy = DataPolicy(
        DataPolicyConfig(
            custom_rules=[
                RedactionRule(
                    name="project_code",
                    pattern=r"project-[0-9]+",
                    replacement="[PROJECT]",
                )
            ]
        )
    )

    result = policy.redact_dict(
        {
            "status": "project-123 active",
            "note": "project-123 owner@example.com",
            "nested": {"note": "project-456"},
            "items": ["project-789", {"note": "project-000"}],
        },
        safe_keys={"status"},
    )

    assert result["status"] == "project-123 active"
    assert result["note"] == "[PROJECT] [EMAIL]"
    assert result["nested"]["note"] == "[PROJECT]"
    assert result["items"] == ["[PROJECT]", {"note": "project-000"}]


def test_safe_summary_filters_fields_and_redacts_llm_explanation():
    policy = DataPolicy()

    summary = policy.create_safe_summary(
        {
            "run_id": "run-1",
            "workspace_id": "workspace-1",
            "raw_output": "secret",
            "llm_explanation": "Email owner@example.com",
        },
        include_llm_explanation=True,
    )

    assert summary == {
        "run_id": "run-1",
        "workspace_id": "workspace-1",
        "llm_explanation": "Email [EMAIL]",
    }
    assert policy.should_store_in_egb("raw_output") is False
    assert policy.should_store_in_egb("run_id") is True


def test_external_payload_deep_link_keeps_raw_payload_out():
    policy = DataPolicy(DataPolicyConfig(store_raw_output=True))

    result = policy.process_external_job_payload(
        {"email": "owner@example.com"},
        tool_name="external-tool",
        deep_link="external-log://logs/1",
    )

    assert result["store_strategy"] == "deep_link_only"
    assert result["deep_link_to_external_log"] == "external-log://logs/1"
    assert "redacted_payload" not in result
    assert "raw_payload" not in result
    assert "output_fingerprint" not in result


def test_external_payload_raw_redacts_when_enabled():
    policy = DataPolicy(DataPolicyConfig(store_raw_output=True))

    result = policy.process_external_job_payload(
        {
            "tool_name": "external-tool",
            "status": "ok",
            "email": "owner@example.com",
            "token": "Bearer abc123",
        },
        tool_name="external-tool",
    )

    assert result["store_strategy"] == "fingerprint_with_optional_raw"
    assert result["output_fingerprint_type"] == "sha256"
    assert result["redacted_payload"]["tool_name"] == "external-tool"
    assert result["redacted_payload"]["status"] == "ok"
    assert result["redacted_payload"]["email"] == "[EMAIL]"
    assert result["redacted_payload"]["token"] == "Bearer [TOKEN]"
    assert "raw_payload" not in result


def test_external_payload_pii_redaction_override_keeps_raw_payload_behavior():
    policy = DataPolicy(DataPolicyConfig(store_raw_output=True))
    policy.EXTERNAL_JOB_PAYLOAD_PII_REDACTION = False

    result = policy.process_external_job_payload(
        {"email": "owner@example.com"},
        tool_name="external-tool",
    )

    assert result["store_strategy"] == "fingerprint_with_optional_raw"
    assert result["raw_payload"] == {"email": "owner@example.com"}
    assert "redacted_payload" not in result


def test_external_payload_fingerprint_is_order_stable():
    left = {"b": 2, "a": "owner@example.com"}
    right = {"a": "owner@example.com", "b": 2}

    assert fingerprint_payload(left) == fingerprint_payload(right)


def test_public_facade_imports_and_singleton_remain_available():
    data_policy_module._global_policy = None
    first = data_policy_module.get_data_policy()
    second = data_policy_module.get_data_policy()

    assert first is second
    assert isinstance(first, DataPolicy)
    assert data_policy_module.DataPolicy is DataPolicy
    assert data_policy_module.PIIRedactor is PIIRedactor
    assert data_policy_module.DataPolicyConfig is DataPolicyConfig
