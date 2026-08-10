import asyncio
import sys
import types
import unittest
from unittest import mock

import server


class WhisperServerThreadBudgetSpec(unittest.TestCase):
    def setUp(self):
        server._model = None
        server._model_size = None

    def tearDown(self):
        server._model = None
        server._model_size = None

    def test_parse_cpu_threads_accepts_only_bounded_integers(self):
        self.assertEqual(server.parse_cpu_threads("1"), 1)
        self.assertEqual(server.parse_cpu_threads("8"), 8)
        self.assertEqual(server.parse_cpu_threads("14"), 14)
        for value in ("0", "15", "invalid", "4.5"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(RuntimeError, "integer from 1 to 14"):
                    server.parse_cpu_threads(value)

    def test_model_constructor_receives_exact_cpu_thread_budget(self):
        constructor = mock.Mock(return_value=object())
        fake_module = types.SimpleNamespace(WhisperModel=constructor)
        with mock.patch.dict(sys.modules, {"faster_whisper": fake_module}):
            model = server.get_model("openai/whisper-small", "cpu")

        self.assertIs(model, constructor.return_value)
        constructor.assert_called_once_with(
            "small",
            device="cpu",
            compute_type="int8",
            cpu_threads=server.WHISPER_CPU_THREADS,
        )

    def test_health_projects_threads_and_busy_state(self):
        result = asyncio.run(server.health())

        self.assertEqual(result["cpu_threads"], server.WHISPER_CPU_THREADS)
        self.assertFalse(result["model_loaded"])
        self.assertFalse(result["busy"])


if __name__ == "__main__":
    unittest.main()
