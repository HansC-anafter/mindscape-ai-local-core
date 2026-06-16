from pathlib import Path
import sys

import pytest

TEST_DIR = Path(__file__).resolve().parent
test_dir_str = str(TEST_DIR)
if test_dir_str not in sys.path:
    sys.path.insert(0, test_dir_str)

from artifact_review_route_review_decision_scenario import run_review_decision_scenario
from artifact_review_route_rerender_dispatch_scenario import run_rerender_dispatch_scenario
from artifact_review_route_laf_patch_dispatch_scenario import run_laf_patch_dispatch_scenario
from artifact_review_route_capability_handoff_scenario import run_capability_handoff_scenario
from artifact_review_route_local_scene_review_scenario import run_local_scene_review_scenario

@pytest.mark.asyncio
async def test_artifact_review_route_persists_decision_and_syncs_run(monkeypatch, tmp_path):
    await run_review_decision_scenario(monkeypatch, tmp_path)

@pytest.mark.asyncio
async def test_dispatch_followup_route_executes_rerender_request(monkeypatch, tmp_path):
    await run_rerender_dispatch_scenario(monkeypatch, tmp_path)

@pytest.mark.asyncio
async def test_dispatch_followup_route_executes_laf_patch_request(monkeypatch, tmp_path):
    await run_laf_patch_dispatch_scenario(monkeypatch, tmp_path)

@pytest.mark.asyncio
async def test_dispatch_followup_route_handoffs_capability_consumer_handoff_to_capability_owned_consumer(monkeypatch, tmp_path):
    await run_capability_handoff_scenario(monkeypatch, tmp_path)

@pytest.mark.asyncio
async def test_dispatch_followup_route_queues_local_scene_review_artifact(monkeypatch, tmp_path):
    await run_local_scene_review_scenario(monkeypatch, tmp_path)
