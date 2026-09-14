import json
import os
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from agent_sentinel.cli import main


class CliTests(unittest.TestCase):
    def test_emit_and_json_status(self) -> None:
        with TemporaryDirectory() as directory:
            state = str(Path(directory) / "state.sqlite3")
            with patch.dict(os.environ, {"AGENT_SENTINEL_STATE": state}):
                with patch("sys.stdout") as output:
                    self.assertEqual(
                        main(
                            [
                                "emit",
                                "--agent",
                                "claude-code",
                                "--kind",
                                "rate_limited",
                                "--id",
                                "hook-42",
                                "--at",
                                "2026-09-14T12:00:00Z",
                                "--reset-at",
                                "2026-09-14T17:00:00Z",
                                "--confidence",
                                "confirmed",
                            ]
                        ),
                        0,
                    )
                    first_output = json.loads(output.write.call_args_list[0].args[0])
                    self.assertTrue(first_output["recorded"])

                with patch("sys.stdout") as output:
                    self.assertEqual(main(["status", "--json"]), 0)
                    status = json.loads(output.write.call_args_list[0].args[0])
                    self.assertEqual(status["events"][0]["event_id"], "hook-42")

    def test_invalid_metadata_is_a_cli_error(self) -> None:
        with TemporaryDirectory() as directory:
            state = str(Path(directory) / "state.sqlite3")
            with patch.dict(os.environ, {"AGENT_SENTINEL_STATE": state}):
                with self.assertRaises(SystemExit) as exit_code:
                    main(["emit", "--agent", "claude-code", "--kind", "agent_finished", "--metadata", "[]"])
        self.assertEqual(exit_code.exception.code, 2)

    def test_schedule_and_dry_run_due_delivery_need_no_credentials(self) -> None:
        with TemporaryDirectory() as directory:
            state = str(Path(directory) / "state.sqlite3")
            with patch.dict(os.environ, {"AGENT_SENTINEL_STATE": state}, clear=True):
                with redirect_stdout(StringIO()):
                    main(
                        [
                            "emit",
                            "--agent",
                            "claude-code",
                            "--kind",
                            "reset_available",
                            "--id",
                            "reset-42",
                            "--at",
                            "2000-01-01T12:00:00Z",
                        ]
                    )
                with redirect_stdout(StringIO()):
                    self.assertEqual(
                        main(["schedule", "--id", "reset-42", "--at", "2000-01-01T11:00:00Z"]),
                        0,
                    )
                output = StringIO()
                with redirect_stdout(output):
                    self.assertEqual(main(["run-due", "--dry-run"]), 0)

        self.assertEqual(json.loads(output.getvalue())["deliveries"][0]["outcome"], "would_deliver")
