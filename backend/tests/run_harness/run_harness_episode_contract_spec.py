from backend.app.models.run_harness import RunHarnessAttempt, RunHarnessEpisode


def test_episode_contract_is_in_memory_and_attempt_addressable() -> None:
    episode = RunHarnessEpisode(
        episode_id="episode-1",
        intent_envelope_ref="intent-1",
        selection_ref="selection-1",
        attempts=[RunHarnessAttempt(attempt_id="attempt-1", attempt_number=1)],
    )
    assert episode.attempts[0].attempt_number == 1
    assert episode.model_dump(mode="json")["status"] == "pending"

