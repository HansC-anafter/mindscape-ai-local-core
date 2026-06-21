import importlib
import sys
from pathlib import Path

from backend.app.models import memory_contract as facade
from backend.app.models import memory_contract_edges as edge_seam
from backend.app.models import memory_contract_evidence as evidence_seam
from backend.app.models import memory_contract_items as item_seam
from backend.app.models import memory_contract_types as type_seam
from backend.app.models.memory_contract import (
    MemoryEdge,
    MemoryEdgeType,
    MemoryEvidenceLink,
    MemoryItem,
    MemoryKind,
    MemoryLayer,
    MemoryLifecycleStatus,
    MemoryUpdateMode,
    MemoryVerificationStatus,
    MemoryVersion,
    MemoryWritebackRun,
    MemoryWritebackRunStatus,
    _utc_now,
)


IMPLEMENTATION_FILES = [
    Path("backend/app/models/memory_contract.py"),
    Path("backend/app/models/memory_contract_types.py"),
    Path("backend/app/models/memory_contract_items.py"),
    Path("backend/app/models/memory_contract_excerpts.py"),
    Path("backend/app/models/memory_contract_evidence.py"),
    Path("backend/app/models/memory_contract_edges.py"),
    Path("backend/tests/models/memory_contract_seams_spec.py"),
]


def test_public_facade_preserves_representative_imports():
    assert MemoryLayer.EPISODIC.value == "episodic"
    assert MemoryKind.SESSION_EPISODE.value == "session_episode"
    assert MemoryVerificationStatus.OBSERVED.value == "observed"
    assert MemoryLifecycleStatus.CANDIDATE.value == "candidate"
    assert MemoryUpdateMode.APPEND.value == "append"
    assert MemoryEdgeType.SUPERSEDES.value == "supersedes"
    assert MemoryWritebackRunStatus.RUNNING.value == "running"

    assert facade.MemoryItem is item_seam.MemoryItem
    assert facade.MemoryVersion is item_seam.MemoryVersion
    assert facade.MemoryEvidenceLink is evidence_seam.MemoryEvidenceLink
    assert facade.MemoryEdge is edge_seam.MemoryEdge
    assert facade.MemoryWritebackRun is edge_seam.MemoryWritebackRun
    assert facade.MemoryLayer is type_seam.MemoryLayer


def test_app_model_facade_import_path_remains_compatible():
    backend_root = Path(__file__).resolve().parents[2]
    backend_path = str(backend_root)
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)

    app_module = importlib.import_module("app.models.memory_contract")

    assert app_module.MemoryItem.__name__ == MemoryItem.__name__
    assert app_module.MemoryEvidenceLink.__name__ == MemoryEvidenceLink.__name__
    assert app_module.MemoryWritebackRun.__name__ == MemoryWritebackRun.__name__
    assert app_module.MemoryKind.SESSION_EPISODE.value == MemoryKind.SESSION_EPISODE.value


def test_item_version_edge_and_run_factories_preserve_contract():
    now = _utc_now()
    assert now.tzinfo is not None
    assert now.utcoffset().total_seconds() == 0

    item = MemoryItem(
        id="mem-1",
        claim="Original claim",
        summary="Original summary",
        metadata={"source_id": "src-1"},
        created_from_run_id="run-1",
    )
    assert item.kind == MemoryKind.SESSION_EPISODE.value
    assert item.layer == MemoryLayer.EPISODIC.value
    assert item.verification_status == MemoryVerificationStatus.OBSERVED.value
    assert item.lifecycle_status == MemoryLifecycleStatus.CANDIDATE.value
    assert item.update_mode == MemoryUpdateMode.APPEND.value

    version = MemoryVersion.initial_from_item(item)
    assert version.memory_item_id == "mem-1"
    assert version.version_no == 1
    assert version.claim_snapshot == "Original claim"
    assert version.summary_snapshot == "Original summary"
    assert version.metadata_snapshot == {"source_id": "src-1"}
    assert version.created_from_run_id == "run-1"

    edge = MemoryEdge.supersedes(
        "mem-new",
        "mem-old",
        reason="updated",
        run_id="run-2",
    )
    assert edge.from_memory_id == "mem-new"
    assert edge.to_memory_id == "mem-old"
    assert edge.edge_type == MemoryEdgeType.SUPERSEDES.value
    assert edge.evidence_strength == 1.0
    assert edge.metadata == {
        "reason": "updated",
        "source_writeback_run_id": "run-2",
    }

    run = MemoryWritebackRun.new(
        run_type="promotion",
        source_scope="memory",
        source_id="mem-1",
        idempotency_key="promotion:mem-1",
        metadata={"actor": "test"},
    )
    assert run.status == MemoryWritebackRunStatus.RUNNING.value
    assert run.last_stage == "created"
    assert run.metadata == {"actor": "test"}
    assert run.created_at == run.started_at == run.updated_at


def test_execution_trace_evidence_factory_preserves_metadata_and_excerpt():
    link = MemoryEvidenceLink.from_execution_trace(
        "mem-1",
        {
            "execution_id": "exec-1",
            "output_summary": "  Completed   with details. ",
            "tool_calls": [{"name": "tool-a"}, {"name": "tool-b"}],
            "files_created": ["a.md"],
            "files_modified": ["b.md"],
            "file_changes": ["a.md", "b.md"],
            "sandbox_path": "/tmp/run-a",
            "agent": "runtime-agent",
            "success": True,
        },
    )

    assert link.memory_item_id == "mem-1"
    assert link.evidence_type == "execution_trace"
    assert link.evidence_id == "exec-1"
    assert link.link_role == "supports"
    assert link.excerpt == "Completed with details."
    assert link.confidence == 0.77
    assert link.metadata["execution_id"] == "exec-1"
    assert link.metadata["tool_call_count"] == 2
    assert link.metadata["files_created_count"] == 1
    assert link.metadata["files_modified_count"] == 1
    assert link.metadata["file_change_count"] == 2
    assert link.metadata["sandbox_path"] == "/tmp/run-a"


def test_touched_files_stay_under_line_gate():
    repo_root = Path(__file__).resolve().parents[3]
    line_counts = {
        path.as_posix(): len((repo_root / path).read_text().splitlines())
        for path in IMPLEMENTATION_FILES
    }

    assert line_counts["backend/app/models/memory_contract.py"] < 120
    assert all(count <= 500 for count in line_counts.values())


def test_touched_files_do_not_add_runtime_resource_owners():
    repo_root = Path(__file__).resolve().parents[3]
    markers = [
        "create_" + "engine",
        "session" + "maker",
        "Fast" + "API",
        "APIR" + "outer",
        "pg" + "bouncer",
        "http" + "x",
        "re" + "quests",
        "aio" + "http",
        "async" + "io",
        "sub" + "process",
        "thread" + "ing",
        "time." + "sl" + "eep",
        "Web" + "Socket",
        "Event" + "Source",
        "set" + "Interval",
    ]
    hits = {}
    for path in IMPLEMENTATION_FILES:
        text = (repo_root / path).read_text()
        found = [marker for marker in markers if marker in text]
        if found:
            hits[path.as_posix()] = found

    assert hits == {}
