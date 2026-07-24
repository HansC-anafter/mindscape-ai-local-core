import pytest

from backend.app.runner.claim_start_delays import (
    ClaimStartDelayCycle,
    parse_claim_start_delays_ms,
)


def test_parse_claim_start_delays_defaults_to_immediate_start():
    assert parse_claim_start_delays_ms(None) == (0,)
    assert parse_claim_start_delays_ms("") == (0,)


def test_claim_start_delay_cycle_advances_only_after_commit():
    cycle = ClaimStartDelayCycle.from_raw("0,8000,16000")

    assert cycle.peek_ms() == 0
    assert cycle.peek_ms() == 0
    cycle.commit()
    assert cycle.peek_ms() == 8000
    cycle.commit()
    assert cycle.peek_ms() == 16000
    cycle.commit()
    assert cycle.peek_ms() == 0


@pytest.mark.parametrize("raw", ["-1", "120001", "nope"])
def test_parse_claim_start_delays_rejects_unsafe_values(raw):
    with pytest.raises(ValueError):
        parse_claim_start_delays_ms(raw)
