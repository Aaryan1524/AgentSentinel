import json
import os
import stat
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from agent_sentinel.cli import main
from agent_sentinel.installers.hooks import (
    apply_hooks,
    detect_adapters,
    install_codex_alias,
    remove_codex_alias,
    remove_hooks,
    target_for_adapter,
)


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
            if os.name == "posix":
                self.assertEqual(stat.S_IMODE(result.backup_path.stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(settings.stat().st_mode), 0o600)
            configured = json.loads(settings.read_text())
            self.assertEqual(configured["permissions"]["allow"], ["Read"])
            self.assertIn("UserPromptSubmit", configured["hooks"])
            self.assertIn("StopFailure", configured["hooks"])

            repeat = apply_hooks(target)
            self.assertFalse(repeat.changed)
            self.assertIsNone(repeat.backup_path)

    def test_gemini_install_adds_the_pre_agent_window_hook(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            self._settings(home, ".gemini")
            target = detect_adapters(home)[0]

            apply_hooks(target)

            configured = json.loads(target.settings_path.read_text())
            self.assertIn("BeforeAgent", configured["hooks"])
            self.assertEqual(
                configured["hooks"]["BeforeAgent"][0]["hooks"][0]["command"],
                "sentinel-gemini-hook",
            )

    def test_grok_install_creates_a_managed_hook_file(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            (home / ".grok").mkdir()
            target = detect_adapters(home)[0]

            result = apply_hooks(target)

            self.assertTrue(result.changed)
            self.assertIsNone(result.backup_path)
            configured = json.loads(target.settings_path.read_text())
            self.assertEqual(
                configured["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"],
                "sentinel-grok-hook",
            )
            self.assertIn("StopFailure", configured["hooks"])
            self.assertFalse(apply_hooks(target).changed)

    def test_codex_install_creates_notify_and_preserves_existing_config(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            target = target_for_adapter("codex-cli", home)

            created = apply_hooks(target)
            self.assertTrue(created.changed)
            self.assertIsNone(created.backup_path)
            self.assertEqual(target.settings_path.read_text(), 'notify = ["sentinel-codex-notify"]\n')

            target.settings_path.write_text('model = "gpt-5-codex"\n')
            configured = apply_hooks(target)
            self.assertTrue(configured.changed)
            assert configured.backup_path is not None
            self.assertEqual(configured.backup_path.read_text(), 'model = "gpt-5-codex"\n')
            self.assertEqual(
                target.settings_path.read_text(),
                'model = "gpt-5-codex"\n\nnotify = ["sentinel-codex-notify"]\n',
            )
            removed = remove_hooks(target)
            self.assertTrue(removed.changed)
            assert removed.backup_path is not None
            self.assertEqual(target.settings_path.read_text(), 'model = "gpt-5-codex"\n')

    def test_codex_install_refuses_to_replace_a_custom_notification(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            target = target_for_adapter("codex-cli", home)
            target.settings_path.parent.mkdir()
            target.settings_path.write_text('notify = ["my-notifier"]\n')

            with self.assertRaisesRegex(ValueError, "refusing to replace"):
                apply_hooks(target)

            self.assertEqual(target.settings_path.read_text(), 'notify = ["my-notifier"]\n')

    def test_codex_alias_is_explicit_reversible_and_does_not_replace_user_aliases(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            installed = install_codex_alias(home, shell="/bin/zsh")
            self.assertTrue(installed.changed)
            self.assertIn("alias codex='sentinel-codex'", installed.profile_path.read_text())
            removed = remove_codex_alias(home, shell="/bin/zsh")
            self.assertTrue(removed.changed)
            self.assertNotIn("sentinel-codex", installed.profile_path.read_text())

            installed.profile_path.write_text("alias codex='my-codex'\n")
            with self.assertRaisesRegex(ValueError, "refusing to replace"):
                install_codex_alias(home, shell="/bin/zsh")

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

    def test_init_can_create_grok_and_codex_configuration(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            output = StringIO()
            with patch.dict(os.environ, {"SHELL": "/bin/zsh"}):
                with redirect_stdout(output):
                    self.assertEqual(
                        main(
                            [
                                "init",
                                "--adapter",
                                "grok-build",
                                "--adapter",
                                "codex-cli",
                                "--codex-alias",
                                "--home",
                                str(home),
                            ]
                        ),
                        0,
                    )

            result = json.loads(output.getvalue())
            self.assertEqual(
                {entry["adapter"] for entry in result["configured"]},
                {"grok-build", "codex-cli"},
            )
            self.assertTrue(result["codex_alias"]["changed"])
            self.assertTrue((home / ".grok" / "hooks" / "agent-sentinel.json").exists())
            self.assertTrue((home / ".codex" / "config.toml").exists())

    def test_uninstall_removes_only_sentinel_commands_and_keeps_other_hooks(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            settings = self._settings(home, ".claude")
            target = detect_adapters(home)[0]
            apply_hooks(target)
            configured = json.loads(settings.read_text())
            configured["hooks"]["Stop"][0]["hooks"].append(
                {"type": "command", "command": "my-stop-observer"}
            )
            settings.write_text(json.dumps(configured))

            result = remove_hooks(target)

            self.assertTrue(result.changed)
            assert result.backup_path is not None
            remaining = json.loads(settings.read_text())
            self.assertEqual(
                remaining["hooks"]["Stop"][0]["hooks"],
                [{"type": "command", "command": "my-stop-observer"}],
            )
            self.assertNotIn("UserPromptSubmit", remaining["hooks"])
            self.assertNotIn("PermissionRequest", remaining["hooks"])
            self.assertFalse(remove_hooks(target).changed)
