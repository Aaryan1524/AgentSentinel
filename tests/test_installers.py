import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from agent_sentinel.cli import main
from agent_sentinel.installers.hooks import apply_hooks, detect_adapters


class HookInstallerTests(unittest.TestCase):
    def _settings(self, home: Path, adapter_dir: str) -> Path:
        path = home / adapter_dir / "settings.json"
        path.parent.mkdir()
        path.write_text('{"permissions":{"allow":["Read"]}}\n')
        return path

    def test_detect_and_apply_preserve_existing_settings_with_backup(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            settings = self._settings(home, ".claude")
            target = detect_adapters(home)[0]

            preview = apply_hooks(target, dry_run=True)
            self.assertTrue(preview.changed)
            self.assertEqual(settings.read_text(), '{"permissions":{"allow":["Read"]}}\n')

            result = apply_hooks(target)
            self.assertTrue(result.changed)
            assert result.backup_path is not None
            self.assertEqual(result.backup_path.read_text(), '{"permissions":{"allow":["Read"]}}\n')
            configured = json.loads(settings.read_text())
            self.assertEqual(configured["permissions"]["allow"], ["Read"])
            self.assertIn("StopFailure", configured["hooks"])

            repeat = apply_hooks(target)
            self.assertFalse(repeat.changed)
            self.assertIsNone(repeat.backup_path)

    def test_invalid_settings_are_not_backed_up_or_overwritten(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            path = home / ".gemini" / "settings.json"
            path.parent.mkdir()
            path.write_text("not json")
            target = detect_adapters(home)[0]

            with self.assertRaisesRegex(ValueError, "invalid JSON"):
                apply_hooks(target)

            self.assertEqual(path.read_text(), "not json")
            self.assertEqual(list(path.parent.glob("*.bak")), [])

    def test_init_detect_dry_run_reports_both_supported_clis(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            claude = self._settings(home, ".claude")
            gemini = self._settings(home, ".gemini")
            output = StringIO()

            with redirect_stdout(output):
                self.assertEqual(main(["init", "--detect", "--dry-run", "--home", str(home)]), 0)

            result = json.loads(output.getvalue())
            self.assertEqual({entry["adapter"] for entry in result["configured"]}, {"claude-code", "gemini-cli"})
            self.assertEqual(claude.read_text(), '{"permissions":{"allow":["Read"]}}\n')
            self.assertEqual(gemini.read_text(), '{"permissions":{"allow":["Read"]}}\n')
