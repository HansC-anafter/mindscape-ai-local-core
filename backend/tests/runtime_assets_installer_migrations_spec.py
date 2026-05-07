from app.services.runtime_assets_installer_core import migrations


class _FakeOrchestrator:
    def __init__(self, applied):
        self.applied = applied
        self.calls = []

    def _get_applied_revisions(self, db_type, current_revisions):
        self.calls.append((db_type, current_revisions))
        return self.applied


class _FailingOrchestrator:
    def _get_applied_revisions(self, db_type, current_revisions):
        raise RuntimeError("script directory unavailable")


def test_pending_revisions_excludes_applied_ancestry():
    orchestrator = _FakeOrchestrator({"rev_1", "rev_2", "rev_3"})

    applied = migrations._resolve_applied_revisions(orchestrator, {"rev_3"})
    pending = migrations._pending_revisions(
        ["rev_1", "rev_2", "rev_3", "rev_4"],
        applied,
    )

    assert orchestrator.calls == [("postgres", {"rev_3"})]
    assert pending == ["rev_4"]


def test_applied_revision_resolution_falls_back_to_current_heads():
    applied = migrations._resolve_applied_revisions(
        _FailingOrchestrator(),
        {"head_a", "head_b"},
    )

    assert applied == {"head_a", "head_b"}
