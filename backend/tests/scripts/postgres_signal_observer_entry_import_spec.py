from __future__ import annotations

import json
import subprocess
import sys


def test_observer_entry_does_not_import_formal_drill_sequence() -> None:
    code = """
import json
import sys
import scripts.maintenance.postgres_signal_observer

print(json.dumps({
    "formal_sequence_loaded": (
        "scripts.maintenance.postgres_signal_observer_core.drill_formal_sequence"
        in sys.modules
    ),
    "formal_cli_loaded": (
        "scripts.maintenance.postgres_signal_observer_core.drill_formal_cli"
        in sys.modules
    ),
}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert completed.returncode == 0
    assert json.loads(completed.stdout) == {
        "formal_cli_loaded": False,
        "formal_sequence_loaded": False,
    }
