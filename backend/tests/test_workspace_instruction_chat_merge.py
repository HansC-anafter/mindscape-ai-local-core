from backend.app.services.workspace_instruction_chat_merge import merge_instruction_patch


def test_merge_omitted_fields_are_not_changed():
    current = {
        "persona": "Old persona",
        "goals": ["goal-a"],
        "anti_goals": ["anti-a"],
        "style_rules": ["style-a"],
        "domain_context": "old context",
    }
    patch = {"persona": "New persona"}

    merged, changed_fields = merge_instruction_patch(current, patch)

    assert merged["persona"] == "New persona"
    assert merged["goals"] == ["goal-a"]
    assert merged["anti_goals"] == ["anti-a"]
    assert merged["style_rules"] == ["style-a"]
    assert merged["domain_context"] == "old context"
    assert changed_fields == ["persona"]


def test_merge_null_clears_scalar_fields():
    current = {
        "persona": "Old persona",
        "goals": ["goal-a"],
        "anti_goals": [],
        "style_rules": [],
        "domain_context": "old context",
    }
    patch = {"persona": None, "domain_context": None}

    merged, changed_fields = merge_instruction_patch(current, patch)

    assert merged["persona"] is None
    assert merged["domain_context"] is None
    assert changed_fields == ["persona", "domain_context"]


def test_merge_empty_list_clears_list_field():
    current = {
        "persona": None,
        "goals": ["goal-a", "goal-b"],
        "anti_goals": ["anti-a"],
        "style_rules": ["style-a"],
        "domain_context": None,
    }
    patch = {"goals": []}

    merged, changed_fields = merge_instruction_patch(current, patch)

    assert merged["goals"] == []
    assert merged["anti_goals"] == ["anti-a"]
    assert changed_fields == ["goals"]


def test_merge_null_list_also_clears_list_field():
    current = {
        "persona": None,
        "goals": ["goal-a"],
        "anti_goals": ["anti-a"],
        "style_rules": ["style-a"],
        "domain_context": None,
    }
    patch = {"style_rules": None}

    merged, changed_fields = merge_instruction_patch(current, patch)

    assert merged["style_rules"] == []
    assert merged["goals"] == ["goal-a"]
    assert changed_fields == ["style_rules"]
