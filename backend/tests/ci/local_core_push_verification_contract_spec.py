from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
VERIFIER = REPO_ROOT / "scripts" / "ci" / "verify_local_core_push.sh"
PRE_PUSH = REPO_ROOT / "scripts" / "git-hooks" / "pre-push.template"


def test_push_verifier_owns_required_release_gates() -> None:
    source = VERIFIER.read_text(encoding="utf-8")

    required_markers = (
        "require_clean_git_scope",
        "reject_secret_literals",
        "validate_product_semantic_helper_parity.py",
        "validate_compose_topology.py",
        "validate_modular_entrypoints.py",
        "validate_product_semantics.py",
        "run_backend_tests",
        "run_architecture_tests",
        "run_frontend_tests",
        "runtime_secret_disposable_integration.sh",
        "install.sh",
        "install.ps1",
        "run_cached_gate",
        "contract_root_is_complete",
        "--explain",
        "mindscape.local-core-push-gate.v1",
        "mindscape.local-core-push-verification.v1",
    )
    for marker in required_markers:
        assert marker in source

    assert "git rev-parse --git-common-dir" in source
    assert "--path-format=absolute" not in source


def test_push_verifier_rejects_incomplete_contract_roots_before_selection() -> None:
    source = VERIFIER.read_text(encoding="utf-8")

    assert (
        'contract_root_is_complete "$REPO_ROOT/.contract-sources/mindscape-ai-cloud"'
        in source
    )
    assert 'contract_root_is_complete "$REPO_ROOT/../mindscape-ai-cloud"' in source
    assert "configured mindscape-ai-cloud contract source is incomplete" in source


def test_pre_push_hook_delegates_to_canonical_verifier() -> None:
    source = PRE_PUSH.read_text(encoding="utf-8")

    assert 'VERIFICATION_SCRIPT="$REPO_ROOT/scripts/ci/verify_local_core_push.sh"' in source
    assert '--base-sha "$verification_base"' in source
    assert '--head-sha "$verification_head"' in source
