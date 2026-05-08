import pytest

from backend.app.models.request_contract import RequestContract


def test_compile_from_agenda_ignores_tracking_ids_dates_and_duration() -> None:
    contract = RequestContract.compile_from_agenda(
        user_message=(
            "使用 real IG refs 構思一組 90s reels，輸出 45 scenes，"
            "逐鏡完成 storyboard 指令與分鏡圖製作。"
        ),
        agenda=[
            "E2E-PD-20260505-REAL-IG-001 real IG refs 90s reels storyboard acceptance"
        ],
        workspace_id="ws_demo",
    )

    assert contract.deliverables
    assert contract.deliverables[0].quantity == 45
    assert "E-PD-" not in contract.deliverables[0].name
    assert all(deliverable.quantity != 20260505 for deliverable in contract.deliverables)
    assert all(deliverable.quantity != 90 for deliverable in contract.deliverables)


def test_compile_from_agenda_treats_90s_reels_as_one_deliverable_without_scene_count() -> None:
    contract = RequestContract.compile_from_agenda(
        user_message="Generate a 90s reels storyboard from the selected references.",
        agenda=[
            "E2E-PD-20260505-REAL-IG-001 real IG refs 90s reels storyboard acceptance"
        ],
        workspace_id="ws_demo",
    )

    assert len(contract.deliverables) == 1
    assert contract.deliverables[0].quantity == 1


@pytest.mark.asyncio
async def test_compile_with_llm_prioritizes_user_request_over_tracking_agenda() -> None:
    captured = {}

    async def _fake_generate(messages, model):
        captured["user_content"] = messages[1]["content"]
        return '[{"name":"Storyboard scene instructions","quantity":45,"requires":["ig_refs"]}]'

    contract = await RequestContract.compile_with_llm(
        user_message="Create a 90s reels storyboard with 45 scenes.",
        agenda=[
            "E2E-PD-20260505-REAL-IG-001 real IG refs 90s reels storyboard acceptance"
        ],
        workspace_id="ws_demo",
        model_name="codex_cli",
        llm_generate_fn=_fake_generate,
    )

    assert "Create a 90s reels storyboard with 45 scenes." in captured["user_content"]
    assert contract.deliverables[0].name == "Storyboard scene instructions"
    assert contract.deliverables[0].quantity == 45
