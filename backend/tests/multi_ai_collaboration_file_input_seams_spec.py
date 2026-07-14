import base64
from pathlib import Path

import pytest

from backend.app.services.multi_ai_collaboration_core import (
    build_file_info,
    extract_content_preview,
    infer_intents_from_filename,
    is_media_transcription_file,
)
from backend.app.services.multi_ai_collaboration import MultiAICollaborationService


class FakeFileProcessor:
    def __init__(self):
        self.calls = []

    async def process_file(self, *, file_data, file_name, file_type, file_size):
        self.calls.append(
            {
                "file_data": file_data,
                "file_name": file_name,
                "file_type": file_type,
                "file_size": file_size,
            }
        )
        return {
            "name": file_name,
            "type": file_type,
            "size": file_size or 0,
            "detected_type": "document",
            "processed": True,
        }


@pytest.mark.asyncio
async def test_collaboration_accepts_host_file_info_without_a_second_parse(monkeypatch):
    processor = FakeFileProcessor()
    service = MultiAICollaborationService(file_processor=processor)

    async def fake_analysis(**_kwargs):
        return {"enabled": False}

    monkeypatch.setattr(service, "_analyze_semantic_seeds", fake_analysis)
    monkeypatch.setattr(service, "_analyze_daily_planning", fake_analysis)
    monkeypatch.setattr(service, "_analyze_content_drafting", fake_analysis)
    override = {
        "name": "sample.pdf",
        "detected_type": "document",
        "text_content": "compiled once",
    }

    result = await service.analyze_file(
        file_data="file-1",
        file_name="sample.pdf",
        file_type="application/pdf",
        file_size=100,
        profile_id="user-1",
        workspace_id="workspace-1",
        file_path="/tmp/sample.pdf",
        file_info_override=override,
    )

    assert processor.calls == []
    assert result["file_info"] == override


class FakeToolExecutor:
    def __init__(self, result=None, error=None):
        self.result = result or {}
        self.error = error
        self.calls = []

    async def execute_tool(self, tool_name, **kwargs):
        self.calls.append({"tool_name": tool_name, "kwargs": kwargs})
        if self.error:
            raise self.error
        return self.result


class FakeSttProvider:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def transcribe(self, file_path):
        self.calls.append(file_path)
        return self.result


@pytest.mark.asyncio
async def test_pdf_file_path_uses_injected_text_extractor_without_file_processor():
    processor = FakeFileProcessor()
    executor = FakeToolExecutor(
        result={"text": "Extracted PDF text", "ocr_used": True, "quality": "high"}
    )

    file_info = await build_file_info(
        file_processor=processor,
        file_data="data:application/pdf;base64,AAAA",
        file_name="contract.pdf",
        file_type=None,
        file_size=128,
        file_path="/tmp/contract.pdf",
        tool_executor_factory=lambda: executor,
    )

    assert processor.calls == []
    assert executor.calls == [
        {
            "tool_name": "core_files.extract_text",
            "kwargs": {"file_path": "/tmp/contract.pdf", "file_type": "pdf"},
        }
    ]
    assert file_info["text_content"] == "Extracted PDF text"
    assert file_info["ocr_used"] is True
    assert file_info["quality"] == "high"
    assert file_info["file_path"] == "/tmp/contract.pdf"


@pytest.mark.asyncio
async def test_pdf_file_path_falls_back_to_file_processor_when_text_extractor_fails():
    processor = FakeFileProcessor()
    executor = FakeToolExecutor(error=RuntimeError("tool unavailable"))

    file_info = await build_file_info(
        file_processor=processor,
        file_data="data:application/pdf;base64,AAAA",
        file_name="contract.pdf",
        file_type="application/pdf",
        file_size=256,
        file_path="/tmp/contract.pdf",
        tool_executor_factory=lambda: executor,
    )

    assert len(processor.calls) == 1
    assert executor.calls[0]["tool_name"] == "core_files.extract_text"
    assert file_info["processed"] is True
    assert file_info["name"] == "contract.pdf"


@pytest.mark.asyncio
async def test_media_file_path_transcribes_after_file_processor():
    processor = FakeFileProcessor()
    stt = FakeSttProvider(
        {
            "text": "This recording contains enough transcribed text for analysis.",
            "language": "en",
            "segments": [{"start": 0, "end": 1, "text": "This recording"}],
        }
    )

    file_info = await build_file_info(
        file_processor=processor,
        file_data="data:audio/wav;base64,AAAA",
        file_name="meeting.wav",
        file_type="audio/wav",
        file_size=512,
        file_path="/tmp/meeting.wav",
        stt_provider_factory=lambda: stt,
    )

    assert is_media_transcription_file("meeting.wav") is True
    assert len(processor.calls) == 1
    assert stt.calls == ["/tmp/meeting.wav"]
    assert file_info["text_content"].startswith("This recording contains")
    assert file_info["transcription_language"] == "en"
    assert file_info["transcription_segments"][0]["text"] == "This recording"
    assert file_info["file_path"] == "/tmp/meeting.wav"


def test_content_preview_and_filename_intent_helpers_preserve_existing_outputs(
    monkeypatch,
):
    class FakeI18n:
        def t(self, _module, _key, *, default):
            return default

    monkeypatch.setattr(
        "backend.app.services.i18n_service.get_i18n_service",
        lambda default_locale: FakeI18n(),
    )
    payload = base64.b64encode(b"Write a product research proposal").decode("ascii")

    assert (
        extract_content_preview(f"data:text/plain;base64,{payload}", max_length=12)
        == "Write a prod"
    )
    assert infer_intents_from_filename("market-research-plan.pdf") == [
        "Research and Analysis"
    ]


def test_multi_ai_collaboration_files_stay_below_line_gate():
    repo_root = Path(__file__).resolve().parents[2]
    paths = [
        repo_root / "backend/app/services/multi_ai_collaboration.py",
        repo_root / "backend/app/services/multi_ai_collaboration_core/__init__.py",
        repo_root / "backend/app/services/multi_ai_collaboration_core/file_inputs.py",
        repo_root / "backend/tests/multi_ai_collaboration_file_input_seams_spec.py",
    ]

    for path in paths:
        assert sum(1 for _ in path.open()) <= 500, path


def test_multi_ai_private_seam_has_no_background_resource_markers():
    repo_root = Path(__file__).resolve().parents[2]
    source = (
        repo_root / "backend/app/services/multi_ai_collaboration_core/file_inputs.py"
    ).read_text()

    forbidden = (
        "create_task",
        "Queue(",
        "Thread(",
        "Process(",
        "sessionmaker",
        "create_engine",
        "PgBouncer",
        "redis",
        "polling",
        "EventSource",
        "WebSocket",
        "websocket",
        "setInterval",
        "setTimeout",
        "subprocess",
    )
    for token in forbidden:
        assert token not in source
