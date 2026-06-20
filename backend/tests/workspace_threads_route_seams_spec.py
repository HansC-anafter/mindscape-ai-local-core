from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FEATURE_ROOT = ROOT / "features" / "workspace"
THREADS_PATH = FEATURE_ROOT / "threads.py"
CORE_ROOT = FEATURE_ROOT / "threads_core"
CRUD_PATH = CORE_ROOT / "crud.py"
BUNDLE_PATH = CORE_ROOT / "bundle.py"
REFERENCES_PATH = CORE_ROOT / "references.py"
SCHEMAS_PATH = CORE_ROOT / "schemas.py"
VALIDATION_PATH = CORE_ROOT / "validation.py"


def test_threads_route_facade_keeps_public_paths_and_response_models():
    source = THREADS_PATH.read_text()

    assert '@router.post("/{workspace_id}/threads", response_model=ConversationThread)' in source
    assert '@router.get("/{workspace_id}/threads", response_model=List[ConversationThread])' in source
    assert '@router.get("/{workspace_id}/threads/{thread_id}", response_model=ConversationThread)' in source
    assert '@router.put("/{workspace_id}/threads/{thread_id}", response_model=ConversationThread)' in source
    assert '@router.delete("/{workspace_id}/threads/{thread_id}")' in source
    assert '@router.get("/{workspace_id}/threads/{thread_id}/bundle", response_model=ThreadBundle)' in source
    assert '"/{workspace_id}/threads/{thread_id}/references"' in source
    assert '"/{workspace_id}/threads/{thread_id}/references/{reference_id}"' in source


def test_threads_route_facade_has_no_direct_db_store_owner_calls():
    source = THREADS_PATH.read_text()

    forbidden = [
        "store.conversation_threads",
        "store.thread_references",
        "store.artifacts",
        "store.playbook_executions",
        "TasksStore",
        "store.create_event",
    ]
    for pattern in forbidden:
        assert pattern not in source


def test_threads_helpers_preserve_limits_and_status_mapping():
    bundle_source = BUNDLE_PATH.read_text()
    reference_source = REFERENCES_PATH.read_text()

    assert "limit=100" in bundle_source
    assert "limit=20" in bundle_source
    assert '"SUCCEEDED": "completed"' in bundle_source
    assert '"FAILED": "failed"' in bundle_source
    assert '"RUNNING": "running"' in bundle_source
    assert '"PENDING": "running"' in bundle_source
    assert "limit=100" in reference_source


def test_threads_language_cleanup_preserves_user_visible_title_strings_only():
    paths = [
        THREADS_PATH,
        CRUD_PATH,
        BUNDLE_PATH,
        REFERENCES_PATH,
        SCHEMAS_PATH,
        VALIDATION_PATH,
        Path(__file__),
    ]
    allowed_fragments = ['return f"與 {project.title} 的對話"', 'return "新對話"']
    cjk_lines = []
    for path in paths:
        for line in path.read_text().splitlines():
            if any("\u4e00" <= char <= "\u9fff" for char in line):
                cjk_lines.append(line.strip())

    assert cjk_lines
    assert all(
        any(allowed in line for allowed in allowed_fragments)
        for line in cjk_lines
    )


def test_threads_seam_files_stay_below_line_gate():
    paths = [
        THREADS_PATH,
        CORE_ROOT / "__init__.py",
        CRUD_PATH,
        BUNDLE_PATH,
        REFERENCES_PATH,
        SCHEMAS_PATH,
        VALIDATION_PATH,
        Path(__file__),
    ]

    for path in paths:
        assert len(path.read_text().splitlines()) <= 500, path
